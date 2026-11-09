# Geändert für Lichtzentrale
"""Synthetic native HA events exercise button safety, ordering and lifecycle."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import Context, CoreState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lichtzentrale.bindings import (
    ACTIONS,
    DOUBLE_RELEASE,
    BindingManager,
    async_save_binding,
    list_buttons,
    validate_binding,
)
from custom_components.lichtzentrale.scenes import async_save_scene
from custom_components.lichtzentrale.storage import LichtzentraleStore

MODULE = "custom_components.lichtzentrale.bindings"
EVENT_TYPES = ["initial_press", "repeat", "short_release", "clock_wise", "counter_clock_wise"]


@pytest.fixture
async def rig(hass, store):
    area = ar.async_get(hass).async_create("Synthetic buttons room")
    other = ar.async_get(hass).async_create("Synthetic other room")
    config = MockConfigEntry(domain="synthetic")
    config.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config.entry_id,
        identifiers={("synthetic", "button-device")},
        name="Synthetic controller",
    )
    dr.async_get(hass).async_update_device(device.id, area_id=area.id)
    registry = er.async_get(hass)
    button = registry.async_get_or_create(
        "event",
        "synthetic",
        "button-one",
        device_id=device.id,
        original_name="Synthetic key",
    )
    hass.states.async_set(button.entity_id, "unknown", {"event_types": EVENT_TYPES})
    ids = []
    for index, mode in enumerate(["xy", "brightness", "onoff"]):
        lamp = registry.async_get_or_create("light", "synthetic", f"button-lamp-{index}")
        registry.async_update_entity(lamp.entity_id, area_id=area.id)
        hass.states.async_set(
            lamp.entity_id,
            "on",
            {
                "supported_color_modes": [mode],
                "brightness": 100,
            },
        )
        ids.append(lamp.entity_id)
    switch = registry.async_get_or_create(
        "switch",
        "shelly",
        "button-ceiling",
        original_name="Synthetic Deckenlicht",
    )
    registry.async_update_entity(switch.entity_id, area_id=area.id)
    hass.states.async_set(switch.entity_id, "on")
    ids.append(switch.entity_id)
    await store.async_set_lights(ids)
    await hass.async_block_till_done()
    old_state = hass.state
    hass.set_state(CoreState.running)
    manager = BindingManager(hass, store)
    hass.data.setdefault("lichtzentrale", {})["bindings"] = manager
    manager.start()
    yield {
        "area": area.id,
        "other": other.id,
        "button": button.entity_id,
        "device": device.id,
        "lights": ids,
        "manager": manager,
    }
    await manager.shutdown()
    hass.set_state(old_state)


def raw(rig, action="toggle_room", event_type="short_release", **extra):
    return {
        "event_entity": rig["button"],
        "event_type": event_type,
        "action": action,
        "area_id": rig["area"],
        "params": {},
        **extra,
    }


async def bind(hass, store, rig, action="toggle_room", event_type="short_release", **extra):
    return await async_save_binding(hass, store, raw(rig, action, event_type, **extra))


async def press(hass, rig, event_type="short_release", context=None, **attributes):
    state = hass.states.get(rig["button"])
    old = (
        datetime.fromisoformat(state.state)
        if state.state not in {"unknown", "unavailable"}
        else None
    )
    stamp = (
        max(datetime.now(timezone.utc), old + timedelta(microseconds=1))
        if old
        else datetime.now(timezone.utc)
    )
    hass.states.async_set(
        rig["button"],
        stamp.isoformat(),
        {
            "event_types": EVENT_TYPES,
            "event_type": event_type,
            **attributes,
        },
        context=context,
    )
    await hass.async_block_till_done()


async def scene(hass, store, rig, name="Synthetic scene"):
    return await async_save_scene(
        hass,
        store,
        {
            "name": name,
            "kind": "snapshot",
            "area_id": rig["area"],
            "lights": {rig["lights"][0]: {"on": True, "brightness": 100}},
        },
    )


async def test_discovery_metadata_and_synthetic_event_scope(hass, store, rig):
    buttons = list_buttons(hass)
    assert buttons == [
        {
            "entity_id": rig["button"],
            "name": hass.states.get(rig["button"]).name,
            "device_id": rig["device"],
            "device_name": "Synthetic controller",
            "area_id": rig["area"],
            "event_types": [*EVENT_TYPES, DOUBLE_RELEASE],
            "available": True,
            "manufacturer": None,
            "model": None,
        }
    ]
    hass.states.async_set(
        "event.synthetic_native",
        "unknown",
        {
            "event_types": ["single_push", "double_push", "single_push", DOUBLE_RELEASE],
        },
    )
    native = next(b for b in list_buttons(hass) if b["entity_id"] == "event.synthetic_native")
    assert native["event_types"] == ["single_push", "double_push"]
    hass.states.async_set("sensor.synthetic_fake", "on", {"event_types": EVENT_TYPES})
    assert len(list_buttons(hass)) == 2
    er.async_get(hass).async_update_entity(rig["button"], disabled_by=er.RegistryEntryDisabler.USER)
    assert len(list_buttons(hass)) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"action": "unlock"},
        {"action": ["toggle_room"]},
        {"area_id": "missing"},
        {"event_entity": "light.synthetic_button"},
        {"event_type": "unsupported"},
        {"params": {"entity_id": "lock.synthetic"}},
        {"params": {"service": "turn_on"}},
        {"domain": "light"},
        {"params": []},
        {"id": 4},
        {"id": "stale"},
        {"action": "scene", "params": {}},
        {"action": "scene", "params": {"scene_id": "missing"}},
    ],
)
async def test_closed_schema_rejects_unsafe_and_stale_data(hass, store, rig, change):
    with pytest.raises(ServiceValidationError):
        validate_binding(hass, store, raw(rig, **change))
    assert store.data["bindings"] == []


async def test_binding_storage_reload_unique_and_update(hass, store, rig):
    saved = await bind(hass, store, rig)
    assert set(saved) == {"id", "event_entity", "event_type", "action", "area_id", "params"}
    with pytest.raises(ServiceValidationError):
        await bind(hass, store, rig, "dim_up")
    updated = await async_save_binding(hass, store, {**saved, "action": "turn_off_room"})
    reloaded = LichtzentraleStore(hass)
    await reloaded.async_load()
    assert reloaded.data["bindings"] == [updated]
    await store.async_delete_binding(saved["id"])
    with pytest.raises(ServiceValidationError):
        await async_save_binding(hass, store, updated)


async def test_scene_binding_rejects_other_room(hass, store, rig):
    saved = await scene(hass, store, rig)
    value = raw(rig, "scene", params={"scene_id": saved["id"]})
    assert validate_binding(hass, store, value)["params"] == {"scene_id": saved["id"]}
    await store.async_save_scene({**saved, "area_id": rig["other"]}, is_update=True)
    with pytest.raises(ServiceValidationError):
        validate_binding(hass, store, value)


async def test_single_is_immediate_without_double_binding_and_has_context(hass, store, rig):
    await bind(hass, store, rig)
    context = Context()
    with patch(f"{MODULE}.async_toggle_room", AsyncMock()) as action:
        await press(hass, rig, context=context)
    action.assert_awaited_once_with(hass, store, rig["area"], on=None, context=context)
    assert rig["manager"]._pending == {}


async def test_single_delays_and_double_replaces_it(hass, store, rig):
    await bind(hass, store, rig, "turn_on_room")
    await bind(hass, store, rig, "turn_off_room", DOUBLE_RELEASE)
    first, second = Context(), Context()
    with patch(f"{MODULE}.async_toggle_room", AsyncMock()) as action:
        await press(hass, rig, context=first)
        action.assert_not_awaited()
        await press(hass, rig, context=second)
        action.assert_awaited_once_with(hass, store, rig["area"], on=False, context=second)
        assert not rig["manager"]._pending
        action.reset_mock()
        await press(hass, rig, context=first)
        await asyncio.sleep(0.52)
        await hass.async_block_till_done()
        action.assert_awaited_once_with(hass, store, rig["area"], on=True, context=first)


async def test_configured_window_and_triple_click(hass, store, rig):
    await store.async_set_double_click(200)
    await bind(hass, store, rig, "turn_on_room")
    await bind(hass, store, rig, "turn_off_room", DOUBLE_RELEASE)
    with patch(f"{MODULE}.async_toggle_room", AsyncMock()) as action:
        await press(hass, rig)
        await press(hass, rig)
        await press(hass, rig)
        assert [call.kwargs["on"] for call in action.await_args_list] == [False]
        await asyncio.sleep(0.22)
        await hass.async_block_till_done()
        assert [call.kwargs["on"] for call in action.await_args_list] == [False, True]


@pytest.mark.parametrize("change", ["deleted", "edited", "unavailable", "revoked"])
async def test_pending_action_does_not_execute_stale_authority(hass, store, rig, change):
    await store.async_set_double_click(200)
    single = await bind(hass, store, rig, "turn_on_room")
    await bind(hass, store, rig, "turn_off_room", DOUBLE_RELEASE)
    with patch(f"{MODULE}.async_toggle_room", AsyncMock()) as action:
        await press(hass, rig)
        if change == "deleted":
            await store.async_delete_binding(single["id"])
        elif change == "edited":
            await async_save_binding(hass, store, {**single, "action": "turn_off_room"})
        elif change == "unavailable":
            hass.states.async_set(rig["button"], "unavailable", {"event_types": EVENT_TYPES})
        else:
            await store.async_set_lights([])
        await asyncio.sleep(0.22)
        await hass.async_block_till_done()
    action.assert_not_awaited()


async def test_startup_restore_attribute_changes_and_replays_ignored(hass, store, rig):
    await bind(hass, store, rig)
    with patch(f"{MODULE}.async_toggle_room", AsyncMock()) as action:
        hass.set_state(CoreState.starting)
        await press(hass, rig)
        hass.set_state(CoreState.running)
        await press(hass, rig, restored=True)
        await press(hass, rig)  # Old state still has the restored marker.
        original = hass.states.get(rig["button"])
        hass.states.async_set(
            rig["button"],
            original.state,
            {
                "event_types": EVENT_TYPES,
                "event_type": "short_release",
                "extra": True,
            },
        )
        await hass.async_block_till_done()
        hass.states.async_set(
            rig["button"],
            "2020-01-01T00:00:00+00:00",
            {
                "event_types": EVENT_TYPES,
                "event_type": "short_release",
            },
        )
        await hass.async_block_till_done()
        hass.states.async_set(rig["button"], "unavailable", {"event_types": EVENT_TYPES})
        await hass.async_block_till_done()
        await press(hass, rig)  # Availability recovery must not replay the last event.
        action.assert_not_awaited()
        await press(hass, rig)
        action.assert_awaited_once()


@pytest.mark.parametrize("event_type", ["repeat", "clock_wise", "counter_clock_wise"])
async def test_rotation_and_repeat_dim_only_on_approved_dimmable_lights(
    hass, store, rig, event_type
):
    await bind(hass, store, rig, "dim_up", event_type)
    hass.states.async_set(
        rig["lights"][1],
        "off",
        {
            "supported_color_modes": ["brightness"],
            "brightness": 100,
        },
    )
    context = Context()
    with patch.object(type(hass.services), "async_call", AsyncMock()) as call:
        await press(hass, rig, event_type, context=context)
    call.assert_awaited_once_with(
        "light",
        "turn_on",
        {
            "entity_id": rig["lights"][0],
            "brightness_step_pct": 10,
        },
        blocking=True,
        context=context,
    )


async def test_dim_down_uses_relative_steps_and_preserves_context(hass, store, rig):
    await bind(hass, store, rig, "dim_down", "repeat")
    context = Context()
    with patch.object(type(hass.services), "async_call", AsyncMock()) as call:
        await press(hass, rig, "repeat", context=context)
        await press(hass, rig, "repeat", context=context)
    assert len(call.await_args_list) == 4
    assert all(c.args[2]["brightness_step_pct"] == -10 for c in call.await_args_list)
    assert all(c.kwargs["context"] == context for c in call.await_args_list)


async def test_all_action_dispatch_is_explicit(hass, store, rig):
    saved = await scene(hass, store, rig)
    context = Context()
    manager = rig["manager"]
    for action in ACTIONS:
        params = {"scene_id": saved["id"]} if action == "scene" else {}
        if action in {"toggle_lights", "turn_on_lights", "turn_off_lights"}:
            params = {"entity_ids": rig["lights"]}
        value = raw(rig, action, params=params)
        with (
            patch(f"{MODULE}.async_toggle_room", AsyncMock()) as toggle,
            patch(f"{MODULE}.async_control_lights", AsyncMock()) as selected,
            patch(f"{MODULE}.async_set_adaptive", AsyncMock()) as adaptive,
            patch(f"{MODULE}.async_stop_room", AsyncMock()) as stop,
            patch(f"{MODULE}.async_apply_scene", AsyncMock()) as apply,
            patch("custom_components.lichtzentrale.target_actions.async_execute_action", AsyncMock()) as shared,
            patch.object(manager, "_dim", AsyncMock()) as dim,
            patch.object(manager, "_next_scene", AsyncMock()) as next_scene,
        ):
            await manager._action(value, context)
            calls = [m for m in (toggle, selected, adaptive, stop, apply, dim, next_scene, shared) if m.await_count]
            assert len(calls) == 1
            assert calls[0].call_args.kwargs.get("context", calls[0].call_args.args[-1]) == context
            if action.startswith("adaptive_"):
                assert adaptive.call_args.kwargs["enabled"] == (action == "adaptive_on")


async def test_cycle_order_wrap_reset_and_context(hass, store, rig, light_calls):
    scenes = [await scene(hass, store, rig, f"Synthetic scene {i}") for i in range(3)]
    await store.async_update_room(rig["area"], {"cycle": [s["id"] for s in scenes]})
    manager, context = rig["manager"], Context()
    with patch(f"{MODULE}.monotonic", return_value=100):
        result = [await manager.async_next_scene(rig["area"], context) for _ in range(4)]
    assert [r["scene_id"] for r in result] == [s["id"] for s in scenes] + [scenes[0]["id"]]
    with patch(f"{MODULE}.monotonic", return_value=699):
        assert (await manager.async_next_scene(rig["area"], context))["scene_id"] == scenes[1]["id"]
    with patch(f"{MODULE}.monotonic", return_value=1299):
        assert (await manager.async_next_scene(rig["area"], context))["scene_id"] == scenes[0]["id"]
    assert all(call.context == context for call in light_calls)
    assert store.data["rooms"][rig["area"]]["cycle"] == [s["id"] for s in scenes]


async def test_cycle_skips_removed_wrong_room_and_revoked_targets(hass, store, rig, light_calls):
    valid = await scene(hass, store, rig)
    obsolete = await scene(hass, store, rig, "Synthetic obsolete")
    moved = await scene(hass, store, rig, "Synthetic moved")
    await store.async_save_scene({**moved, "area_id": rig["other"]}, is_update=True)
    await store.async_save_scene(
        {**obsolete, "lights": {rig["lights"][1]: {"on": True}}}, is_update=True
    )
    await store.async_set_lights([rig["lights"][0]])
    await store.async_update_room(
        rig["area"], {"cycle": ["missing", moved["id"], obsolete["id"], valid["id"]]}
    )
    result = await rig["manager"].async_next_scene(rig["area"])
    assert result["scene_id"] == valid["id"]
    assert len(light_calls) == 1
    await store.async_delete_scene(valid["id"])
    with pytest.raises(ServiceValidationError):
        await rig["manager"].async_next_scene(rig["area"])


@pytest.mark.parametrize(
    "result",
    [
        {"applied": [], "skipped": []},
        {"applied": ["light.synthetic"], "skipped": [], "failed": ["light.synthetic_other"]},
        {"applied": ["light.synthetic"], "skipped": ["light.synthetic_other"]},
    ],
)
async def test_cycle_does_not_advance_on_incomplete_recall(hass, store, rig, result):
    scenes = [await scene(hass, store, rig, f"Synthetic scene {i}") for i in range(2)]
    await store.async_update_room(rig["area"], {"cycle": [s["id"] for s in scenes]})
    with patch(f"{MODULE}.async_apply_scene", AsyncMock(return_value=result)) as apply:
        await rig["manager"].async_next_scene(rig["area"])
        await rig["manager"].async_next_scene(rig["area"])
    assert [c.args[2] for c in apply.await_args_list] == [scenes[0]["id"]] * 2
    assert not rig["manager"]._cycles


async def test_cycle_concurrent_calls_serialize(hass, store, rig):
    scenes = [await scene(hass, store, rig, f"Synthetic scene {i}") for i in range(2)]
    await store.async_update_room(rig["area"], {"cycle": [s["id"] for s in scenes]})
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def apply(hass, store, scene_id, **kwargs):
        calls.append(scene_id)
        entered.set()
        await release.wait()
        return {"applied": [rig["lights"][0]], "skipped": []}

    with patch(f"{MODULE}.async_apply_scene", side_effect=apply):
        first = asyncio.create_task(rig["manager"].async_next_scene(rig["area"]))
        await entered.wait()
        second = asyncio.create_task(rig["manager"].async_next_scene(rig["area"]))
        await asyncio.sleep(0)
        assert calls == [scenes[0]["id"]]
        release.set()
        await asyncio.gather(first, second)
    assert calls == [s["id"] for s in scenes]


async def test_unload_cancels_pending_timer_listener_and_running_action(hass, store, rig):
    manager = rig["manager"]
    manager.start()  # Idempotent setup never doubles event dispatch.
    await bind(hass, store, rig, "turn_on_room")
    await bind(hass, store, rig, "turn_off_room", DOUBLE_RELEASE)
    await press(hass, rig)
    assert manager._pending
    with patch(f"{MODULE}.async_toggle_room", AsyncMock()) as action:
        await manager.shutdown()
        await asyncio.sleep(0.52)
        await press(hass, rig)
    action.assert_not_awaited()
    assert not manager._pending and not manager._tasks and manager._unsubscribe is None
    with pytest.raises(ServiceValidationError):
        manager.start()
    with pytest.raises(ServiceValidationError):
        await manager.async_next_scene(rig["area"])


async def test_shutdown_cancels_inflight_and_queued_button_tasks(hass, store, rig):
    await bind(hass, store, rig)
    manager = rig["manager"]
    entered, release = asyncio.Event(), asyncio.Event()

    async def wait(*args, **kwargs):
        entered.set()
        await release.wait()

    with patch(f"{MODULE}.async_toggle_room", side_effect=wait) as action:
        context = Context()
        # The state need only be an actual event timestamp for queued execution.
        hass.states.async_set(
            rig["button"],
            datetime.now(timezone.utc).isoformat(),
            {
                "event_types": EVENT_TYPES,
            },
        )
        manager._queue(store.data["bindings"], context)
        await entered.wait()
        manager._queue(store.data["bindings"], context)
        await asyncio.sleep(0)
        await manager.shutdown()
        assert action.await_count == 1
        assert not manager._tasks


async def test_dim_final_dispatch_rechecks_grants(hass, store, rig):
    manager = rig["manager"]
    # The final guard is evaluated inside gathered dispatch children, not before yielding.
    from custom_components.lichtzentrale.rooms import async_dispatch as dispatch

    async def revoke_before_dispatch(hass, calls, skipped=None, context=None, guard=None):
        await store.async_set_lights([])
        return await dispatch(hass, calls, skipped, context, guard)

    with (
        patch(f"{MODULE}.async_dispatch", side_effect=revoke_before_dispatch),
        patch.object(type(hass.services), "async_call", AsyncMock()) as call,
    ):
        result = await manager._dim(rig["area"], 1, Context())
    assert not result["applied"]
    call.assert_not_awaited()


@pytest.mark.parametrize("mutation", ["delete", "edit"])
async def test_binding_change_cancels_action_waiting_on_scene_lock(hass, store, rig, mutation):
    binding = await bind(hass, store, rig, "turn_off_room")
    lock = asyncio.Lock()
    hass.data["lichtzentrale"]["scene_locks"] = {rig["area"]: lock}
    await lock.acquire()
    # Establish the event timestamp without creating another actual button action.
    hass.states.async_set(
        rig["button"],
        datetime.now(timezone.utc).isoformat(),
        {
            "event_types": EVENT_TYPES,
        },
    )
    manager = rig["manager"]
    with patch.object(type(hass.services), "async_call", AsyncMock()) as call:
        manager._queue([binding], Context())
        await asyncio.sleep(0)
        assert manager._tasks
        if mutation == "delete":
            await store.async_delete_binding(binding["id"])
        else:
            await async_save_binding(hass, store, {**binding, "action": "turn_on_room"})
        lock.release()
        await hass.async_block_till_done()
        await asyncio.sleep(0)
    call.assert_not_awaited()
    assert not manager._tasks and not manager._task_bindings


async def test_service_cycle_is_cancelled_on_unload_while_waiting_scene_lock(hass, store, rig):
    saved = await scene(hass, store, rig)
    await store.async_update_room(rig["area"], {"cycle": [saved["id"]]})
    lock = asyncio.Lock()
    hass.data["lichtzentrale"]["scene_locks"] = {rig["area"]: lock}
    await lock.acquire()
    manager = rig["manager"]
    with patch.object(type(hass.services), "async_call", AsyncMock()) as call:
        service = asyncio.create_task(manager.async_next_scene(rig["area"]))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert manager._tasks
        await manager.shutdown()
        lock.release()
        with pytest.raises(asyncio.CancelledError):
            await service
    call.assert_not_awaited()
    assert not manager._tasks and not manager._cycles


async def test_refresh_cancels_window_after_double_binding_changes(hass, store, rig):
    await bind(hass, store, rig, "turn_on_room")
    double = await bind(hass, store, rig, "turn_off_room", DOUBLE_RELEASE)
    await press(hass, rig)
    assert rig["manager"]._pending
    await store.async_delete_binding(double["id"])
    assert not rig["manager"]._pending


async def test_action_partial_failures_are_logged(hass, store, rig, caplog):
    await bind(hass, store, rig)
    with patch(
        f"{MODULE}.async_toggle_room",
        AsyncMock(
            return_value={
                "applied": [rig["lights"][0]],
                "failed": [rig["lights"][1]],
                "skipped": [],
            }
        ),
    ):
        await press(hass, rig)
    assert "Tasteraktion teilweise fehlgeschlagen: 1 Fehler, 0 übersprungen" in caplog.text


async def test_learning_captures_runtime_attributes_without_running_actions(hass, store, rig):
    manager = rig["manager"]
    await bind(hass, store, rig)
    token = manager.learn_start(rig["button"])["token"]
    assert manager.learn_status(token)["status"] == "waiting"
    with patch.object(manager, "_action", AsyncMock()) as action:
        await press(hass, rig, invented_key="left", movement={"direction": -1}, speed=3)
        action.assert_not_awaited()
    result = manager.learn_status(token)
    assert result["status"] == "captured"
    assert result["observation"] == {
        "event_entity": rig["button"], "event_type": "short_release",
        "event_attributes": {"invented_key": "left", "movement": {"direction": -1}, "speed": 3},
    }
    await press(hass, rig, invented_key="right")
    assert manager.learn_status(token) == result
    assert manager.learn_cancel(token) == {"cancelled": True}
    assert manager.learn_cancel(token) == {"cancelled": True}
    with pytest.raises(ServiceValidationError, match="abgelaufen"):
        manager.learn_status(token)


async def test_learned_same_type_buttons_do_not_cross_fire_and_survive_reload(hass, store, rig):
    left = await bind(hass, store, rig, event_attributes={"runtime_selector": "left"}, control_label="Links")
    right = await bind(hass, store, rig, event_attributes={"runtime_selector": "right"}, control_label="Rechts")
    assert left["id"] != right["id"]
    # A new manager reads the persisted binding schema; no learning session is required.
    await rig["manager"].shutdown()
    manager = BindingManager(hass, store)
    rig["manager"] = manager
    manager.start()
    try:
        with patch.object(manager, "_action", AsyncMock()) as action:
            await press(hass, rig, runtime_selector="left")
            await press(hass, rig, runtime_selector="right")
            await press(hass, rig, runtime_selector="right")
            await press(hass, rig)  # Missing identifying key must not run either action.
            await press(hass, rig, runtime_selector="left", added=True)
            assert [call.args[0]["id"] for call in action.await_args_list] == [left["id"], right["id"], right["id"]]
    finally:
        await manager.shutdown()


async def test_learning_ignores_attributes_only_and_unavailable_sources(hass, store, rig):
    manager = rig["manager"]
    await press(hass, rig)
    token = manager.learn_start(rig["button"])["token"]
    state = hass.states.get(rig["button"])
    hass.states.async_set(rig["button"], state.state, {**state.attributes, "runtime_selector": "other"})
    await hass.async_block_till_done()
    assert manager.learn_status(token)["status"] == "waiting"
    hass.states.async_set(rig["button"], "unavailable", {"event_types": EVENT_TYPES})
    await hass.async_block_till_done()
    with pytest.raises(ServiceValidationError, match="nicht mehr verfügbar"):
        manager.learn_status(token)
    with pytest.raises(ServiceValidationError, match="nicht verfügbar"):
        manager.learn_start(rig["button"])


async def test_learning_expiry_and_payload_validation(hass, store, rig):
    manager = rig["manager"]
    with patch(f"{MODULE}.monotonic", return_value=100):
        token = manager.learn_start(rig["button"])["token"]
    with patch(f"{MODULE}.monotonic", return_value=221):
        with pytest.raises(ServiceValidationError, match="abgelaufen"):
            manager.learn_status(token)
    for attrs in [[], {"event_type": "press"}, {"x": float("nan")}, {"x": "a" * 9000}]:
        with pytest.raises(ServiceValidationError):
            validate_binding(hass, store, raw(rig, event_attributes=attrs))
    assert "event_attributes" not in validate_binding(hass, store, raw(rig))


async def test_generic_z2m_press_release_and_unknown_rotation_remain_distinct(hass, store, rig):
    manager = rig["manager"]
    with patch(f"{__name__}.EVENT_TYPES", ["press_release", "unexpected_rotation"]):
        await press(hass, rig, "press_release", synthetic_physical_key=1)
        one = await bind(hass, store, rig, event_type="press_release", event_attributes={"synthetic_physical_key": 1})
        two = await bind(hass, store, rig, event_type="press_release", event_attributes={"synthetic_physical_key": 2})
        rotation = await bind(hass, store, rig, event_type="unexpected_rotation", event_attributes={"synthetic_direction": -1, "synthetic_rate": 7})
        with patch.object(manager, "_action", AsyncMock()) as action:
            await press(hass, rig, "press_release", synthetic_physical_key=1)
            await press(hass, rig, "press_release", synthetic_physical_key=2)
            await press(hass, rig, "unexpected_rotation", synthetic_direction=-1, synthetic_rate=7)
            await press(hass, rig, "unexpected_rotation", synthetic_direction=1, synthetic_rate=7)
            await press(hass, rig, "unexpected_rotation", synthetic_direction=-1, synthetic_rate=8)
            assert [call.args[0]["id"] for call in action.await_args_list] == [one["id"], two["id"], rotation["id"]]


async def test_zone_binding_and_full_brightness_explicit_lamps_validate(hass, store, rig):
    zone = await store.async_save_zone({"name": "Synthetic zone", "entity_ids": rig["lights"]})
    saved = await bind(hass, store, rig, action="dim_up", area_id="zone:" + zone["id"])
    assert saved["area_id"] == "zone:" + zone["id"]
    full = validate_binding(hass, store, raw(rig, action="full_brightness", area_id=None, params={"entity_ids": rig["lights"]}))
    assert full["params"]["entity_ids"] == rig["lights"]
    for action in ("night", "night_auto", "return_auto"):
        with pytest.raises(ServiceValidationError):
            validate_binding(hass, store, raw(rig, action=action, area_id=None, params={"entity_ids": rig["lights"]}))
