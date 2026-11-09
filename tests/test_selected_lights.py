# Geändert für Lichtzentrale
"""Selected light actions use synthetic HA states and never contact devices."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from custom_components.lichtzentrale.bindings import validate_binding
from custom_components.lichtzentrale.selected_lights import (
    async_control_lights,
    async_dim_lights,
    validate_selected_lights,
)
from custom_components.lichtzentrale.storage import LichtzentraleStore

DYNAMIC = "custom_components.lichtzentrale.dynamic_scenes.async_exclude_targets"


@pytest.fixture
async def selection(hass, store):
    areas = [ar.async_get(hass).async_create(f"Synthetic selected room {i}").id for i in range(2)]
    registry = er.async_get(hass)
    ids = []
    for i, mode in enumerate(["xy", "color_temp", "brightness", "onoff", None]):
        domain = "switch" if mode is None else "light"
        entry = registry.async_get_or_create(
            domain, "shelly" if mode is None else "synthetic", f"selected-{i}",
            original_name=f"Synthetic light {i}",
        )
        if i < 4:
            registry.async_update_entity(entry.entity_id, area_id=areas[i % 2])
        attrs = {} if mode is None else {
            "supported_color_modes": [mode], "color_mode": mode, "brightness": 123,
        }
        if mode == "xy":
            attrs["xy_color"] = [0.31, 0.42]
        elif mode == "color_temp":
            attrs.update(color_temp_kelvin=2700, min_color_temp_kelvin=2200,
                         max_color_temp_kelvin=6000)
        hass.states.async_set(entry.entity_id, "on", attrs)
        ids.append(entry.entity_id)
    button = registry.async_get_or_create("event", "synthetic", "selected-button")
    hass.states.async_set(button.entity_id, "unknown", {"event_types": ["short_release"]})
    await store.async_set_lights(ids)
    return {"ids": ids, "areas": areas, "button": button.entity_id}


def state(hass, entity_id, value, **attrs):
    previous = hass.states.get(entity_id)
    hass.states.async_set(entity_id, value, {**previous.attributes, **attrs})


def payloads(call):
    return {c.args[2]["entity_id"]: c.args[2] for c in call.await_args_list}


@pytest.mark.parametrize("invalid", [None, [], "light.synthetic", [1], [True], [{}]])
async def test_selection_requires_nonempty_list_of_strings(hass, store, selection, invalid):
    with pytest.raises(ServiceValidationError):
        validate_selected_lights(hass, store, invalid)


async def test_selection_deduplicates_and_accepts_cross_room_and_no_room(hass, store, selection):
    ids = selection["ids"]
    assert validate_selected_lights(hass, store, ids + [ids[0]]) == ids


@pytest.mark.parametrize("kind", ["lock", "group", "unsafe_switch", "revoked", "removed"])
async def test_invalid_member_rejects_entire_batch_without_effects(hass, store, selection, kind):
    valid = selection["ids"][0]
    registry = er.async_get(hass)
    if kind == "revoked":
        invalid = selection["ids"][1]
        await store.async_set_lights([valid])
    elif kind == "removed":
        invalid = selection["ids"][1]
        hass.states.async_remove(invalid)
    else:
        domain = {"lock": "lock", "group": "light", "unsafe_switch": "switch"}[kind]
        entry = registry.async_get_or_create(domain, "group" if kind == "group" else "shelly",
                                             f"unsafe-{kind}", original_name="Synthetic appliance")
        invalid = entry.entity_id
        hass.states.async_set(invalid, "on")
        # Deliberately stale/corrupt persisted grants must not bypass eligibility.
        await store.async_set_lights([valid, invalid])
    with (patch(DYNAMIC, AsyncMock()) as stop,
          patch.object(type(hass.services), "async_call", AsyncMock()) as call):
        with pytest.raises(ServiceValidationError):
            await async_control_lights(hass, store, [valid, invalid], on=False)
    stop.assert_not_awaited()
    call.assert_not_awaited()


@pytest.mark.parametrize("action", ["toggle_lights", "turn_on_lights", "turn_off_lights", "dim_up", "dim_down"])
async def test_explicit_binding_accepts_null_room_and_cross_room_selection(hass, store, selection, action):
    ids = selection["ids"]
    value = validate_binding(hass, store, {
        "event_entity": selection["button"], "event_type": "short_release",
        "action": action, "area_id": None, "params": {"entity_ids": ids},
    })
    assert value["params"]["entity_ids"] == ids


@pytest.mark.parametrize("action", ["toggle_lights", "turn_on_lights", "turn_off_lights"])
@pytest.mark.parametrize("params", [{}, {"entity_ids": []}, {"entity_ids": "light.synthetic"},
                                   {"entity_ids": [True]}, {"entity_ids": [], "service": "unlock"}])
async def test_selected_binding_rejects_bad_params(hass, store, selection, action, params):
    with pytest.raises(ServiceValidationError):
        validate_binding(hass, store, {
            "event_entity": selection["button"], "event_type": "short_release",
            "action": action, "area_id": selection["areas"][0], "params": params,
        })


async def test_toggle_any_on_turns_every_selected_target_off_with_context(hass, store, selection):
    ids = selection["ids"]
    for entity_id in ids[:-1]:
        state(hass, entity_id, "off")
    context = Context()
    with patch.object(type(hass.services), "async_call", AsyncMock()) as call:
        result = await async_control_lights(hass, store, ids, context=context)
    assert set(result["applied"]) == set(ids)
    assert all(c.args[1] == "turn_off" for c in call.await_args_list)
    assert all(c.kwargs["context"] == context for c in call.await_args_list)
    assert set(payloads(call)) == set(ids)


async def test_off_snapshot_persists_and_repeat_off_does_not_erase(hass, store, selection):
    ids = selection["ids"]
    with patch.object(type(hass.services), "async_call", AsyncMock()):
        await async_control_lights(hass, store, ids, on=False)
        saved = deepcopy(store.data["settings"]["last_light_states"])
        for entity_id in ids:
            state(hass, entity_id, "off", brightness=None)
        await async_control_lights(hass, store, ids, on=False)
    assert store.data["settings"]["last_light_states"] == saved
    reloaded = LichtzentraleStore(hass)
    await reloaded.async_load()
    assert reloaded.data["settings"]["last_light_states"] == saved
    assert saved[ids[0]]["brightness"] == 123
    assert saved[ids[0]]["xy"] == [0.31, 0.42]
    assert saved[ids[1]]["color_temp_kelvin"] == 2700
    assert ids[4] not in saved  # Switches always use bare turn_on, with no snapshot.


async def test_restore_xy_ct_brightness_and_switch_payloads(hass, store, selection):
    ids = selection["ids"]
    with patch.object(type(hass.services), "async_call", AsyncMock()) as call:
        await async_control_lights(hass, store, ids, on=False)
        for entity_id in ids:
            state(hass, entity_id, "off", brightness=None)
        call.reset_mock()
        await async_control_lights(hass, store, ids)
    data = payloads(call)
    assert data[ids[0]] == {"entity_id": ids[0], "brightness": 123, "xy_color": [0.31, 0.42]}
    assert data[ids[1]] == {"entity_id": ids[1], "brightness": 123, "color_temp_kelvin": 2700}
    assert data[ids[2]] == {"entity_id": ids[2], "brightness": 123}
    assert data[ids[3]] == {"entity_id": ids[3]}
    assert data[ids[4]] == {"entity_id": ids[4]}
    assert all(c.args[1] == "turn_on" for c in call.await_args_list)


async def test_restore_filters_changed_capabilities_and_preserves_already_on(hass, store, selection):
    ids = selection["ids"][:2]
    with patch.object(type(hass.services), "async_call", AsyncMock()) as call:
        await async_control_lights(hass, store, ids, on=False)
        state(hass, ids[0], "off", supported_color_modes=["onoff"])
        state(hass, ids[1], "on", brightness=222, color_temp_kelvin=5000)
        call.reset_mock()
        await async_control_lights(hass, store, ids, on=True)
    data = payloads(call)
    assert data[ids[0]] == {"entity_id": ids[0]}
    if ids[1] in data:
        assert data[ids[1]] == {"entity_id": ids[1]}


async def test_missing_snapshot_uses_native_on_and_unavailable_is_skipped(hass, store, selection):
    ids = selection["ids"]
    for entity_id in ids:
        state(hass, entity_id, "off")
    state(hass, ids[1], "unavailable")
    state(hass, ids[2], "unknown")
    with patch.object(type(hass.services), "async_call", AsyncMock()) as call:
        result = await async_control_lights(hass, store, ids)
    assert set(result["skipped"]) == set(ids[1:3])
    assert set(result["applied"]) == {ids[0], ids[3], ids[4]}
    assert all(c.args[2] == {"entity_id": c.args[2]["entity_id"]} for c in call.await_args_list)


async def test_off_save_failure_prevents_service_dispatch(hass, store, selection):
    with (patch.object(store._store, "async_save", AsyncMock(side_effect=OSError("synthetic disk error"))),
          patch.object(type(hass.services), "async_call", AsyncMock()) as call):
        with pytest.raises((OSError, HomeAssistantError)):
            await async_control_lights(hass, store, selection["ids"], on=False)
    call.assert_not_awaited()


async def test_service_failure_does_not_block_other_targets(hass, store, selection):
    ids = selection["ids"][:2]

    async def dispatch(domain, service, data, **kwargs):
        if data["entity_id"] == ids[0]:
            raise HomeAssistantError("Synthetic device offline")

    with patch.object(type(hass.services), "async_call", side_effect=dispatch):
        result = await async_control_lights(hass, store, ids, on=True)
    assert result["failed"] == [ids[0]]
    assert result["applied"] == [ids[1]]


@pytest.mark.parametrize("direction", [-1, 1])
async def test_explicit_dim_only_on_selected_dimmable_lights(hass, store, selection, direction):
    ids = selection["ids"]
    state(hass, ids[2], "off")
    context = Context()
    with patch.object(type(hass.services), "async_call", AsyncMock()) as call:
        result = await async_dim_lights(hass, store, ids[1:], direction, context=context)
    assert result["applied"] == [ids[1]]
    call.assert_awaited_once_with("light", "turn_on", {
        "entity_id": ids[1], "brightness_step_pct": direction * 10,
    }, blocking=True, context=context)


async def test_revocation_while_waiting_for_room_lock_prevents_calls(hass, store, selection):
    ids = selection["ids"][:1]
    lock = asyncio.Lock()
    hass.data.setdefault("lichtzentrale", {}).setdefault("scene_locks", {})[selection["areas"][0]] = lock
    await lock.acquire()
    with patch.object(type(hass.services), "async_call", AsyncMock()) as call:
        task = asyncio.create_task(async_control_lights(hass, store, ids, on=True))
        await asyncio.sleep(0)
        await store.async_set_lights([])
        lock.release()
        try:
            await task
        except ServiceValidationError:
            pass
    call.assert_not_awaited()


async def test_revocation_during_dynamic_stop_prevents_calls(hass, store, selection):
    async def stop(*args, **kwargs):
        await store.async_set_lights([])

    with (patch(DYNAMIC, side_effect=stop),
          patch.object(type(hass.services), "async_call", AsyncMock()) as call):
        try:
            await async_control_lights(hass, store, selection["ids"], on=True)
        except ServiceValidationError:
            pass
    call.assert_not_awaited()


async def test_room_move_while_waiting_does_not_control_unlocked_area(hass, store, selection):
    ids = selection["ids"][:1]
    lock = asyncio.Lock()
    hass.data.setdefault("lichtzentrale", {}).setdefault("scene_locks", {})[selection["areas"][0]] = lock
    await lock.acquire()
    with patch.object(type(hass.services), "async_call", AsyncMock()) as call:
        task = asyncio.create_task(async_control_lights(hass, store, ids, on=True))
        await asyncio.sleep(0)
        er.async_get(hass).async_update_entity(ids[0], area_id=selection["areas"][1])
        lock.release()
        try:
            await task
        except ServiceValidationError:
            pass
    call.assert_not_awaited()


async def test_final_dispatch_rechecks_revocation(hass, store, selection):
    from custom_components.lichtzentrale.rooms import async_dispatch

    async def revoke_then_dispatch(*args, **kwargs):
        await store.async_set_lights([])
        return await async_dispatch(*args, **kwargs)

    with (patch("custom_components.lichtzentrale.selected_lights.async_dispatch",
                side_effect=revoke_then_dispatch),
          patch.object(type(hass.services), "async_call", AsyncMock()) as call):
        result = await async_control_lights(hass, store, selection["ids"], on=True)
    call.assert_not_awaited()
    assert set(result["skipped"]) == set(selection["ids"])


async def test_only_selected_lights_leave_dynamics(hass, store, selection):
    ids = [selection["ids"][0], selection["ids"][4]]
    with (patch(DYNAMIC, AsyncMock()) as stop,
          patch.object(type(hass.services), "async_call", AsyncMock()) as call):
        await async_control_lights(hass, store, ids, on=True)
    stop.assert_awaited_once_with(hass, ids)
    assert set(payloads(call)) == set(ids)


async def test_revocation_during_snapshot_save_prevents_off(hass, store, selection):
    original = store._store.async_save

    async def save_then_revoke(data):
        await original(data)
        # A concurrent grant update at the persistence await boundary.
        data["settings"]["light_entity_ids"] = []

    with (patch.object(store._store, "async_save", side_effect=save_then_revoke),
          patch.object(type(hass.services), "async_call", AsyncMock()) as call):
        try:
            await async_control_lights(hass, store, selection["ids"], on=False)
        except ServiceValidationError:
            pass
    call.assert_not_awaited()


@pytest.mark.parametrize("change", ["capability", "state", "area", "removed"])
async def test_final_dispatch_drops_changed_target(hass, store, selection, change):
    from custom_components.lichtzentrale.rooms import async_dispatch

    ids = selection["ids"][:2]

    async def change_then_dispatch(*args, **kwargs):
        if change == "capability":
            state(hass, ids[0], "on", supported_color_modes=["onoff"])
        elif change == "state":
            state(hass, ids[0], "unavailable")
        elif change == "area":
            er.async_get(hass).async_update_entity(ids[0], area_id=selection["areas"][1])
        else:
            hass.states.async_remove(ids[0])
        return await async_dispatch(*args, **kwargs)

    with (patch("custom_components.lichtzentrale.selected_lights.async_dispatch",
                side_effect=change_then_dispatch),
          patch.object(type(hass.services), "async_call", AsyncMock()) as call):
        result = await async_control_lights(hass, store, ids, on=False)
    assert result["skipped"] == [ids[0]]
    assert result["applied"] == [ids[1]]
    assert set(payloads(call)) == {ids[1]}


async def test_final_dim_dispatch_rechecks_dimmability(hass, store, selection):
    from custom_components.lichtzentrale.rooms import async_dispatch

    ids = selection["ids"][:2]

    async def change_then_dispatch(*args, **kwargs):
        state(hass, ids[0], "on", supported_color_modes=["onoff"])
        return await async_dispatch(*args, **kwargs)

    with (patch("custom_components.lichtzentrale.selected_lights.async_dispatch",
                side_effect=change_then_dispatch),
          patch.object(type(hass.services), "async_call", AsyncMock()) as call):
        result = await async_dim_lights(hass, store, ids, 1)
    assert result["skipped"] == [ids[0]]
    assert set(payloads(call)) == {ids[1]}


async def test_overlapping_cross_room_selections_serialize_without_deadlock(hass, store, selection):
    ids = selection["ids"][:2]
    entered, release = asyncio.Event(), asyncio.Event()
    invocations = []

    async def dispatch(domain, service, data, **kwargs):
        invocations.append((service, data["entity_id"]))
        entered.set()
        await release.wait()

    with patch.object(type(hass.services), "async_call", side_effect=dispatch):
        first = asyncio.create_task(async_control_lights(hass, store, ids, on=True))
        await asyncio.wait_for(entered.wait(), 1)
        second = asyncio.create_task(async_control_lights(hass, store, list(reversed(ids)), on=False))
        await asyncio.sleep(0)
        assert all(service == "turn_on" for service, _ in invocations)
        release.set()
        results = await asyncio.wait_for(asyncio.gather(first, second), 1)
    assert all(set(result["applied"]) == set(ids) for result in results)
    assert [service for service, _ in invocations] == ["turn_on", "turn_on", "turn_off", "turn_off"]


async def test_newer_room_off_snapshot_replaces_selected_off_snapshot(hass, store, selection):
    from custom_components.lichtzentrale.rooms import async_toggle_room

    entity_id = selection["ids"][0]
    with patch.object(type(hass.services), "async_call", AsyncMock()) as call:
        await async_control_lights(hass, store, [entity_id], on=False)
        state(hass, entity_id, "off")
        await async_control_lights(hass, store, [entity_id], on=True)
        state(hass, entity_id, "on", brightness=210, xy_color=[0.17, 0.19])
        await async_toggle_room(hass, store, selection["areas"][0], on=False)
        state(hass, entity_id, "off")
        call.reset_mock()
        await async_control_lights(hass, store, [entity_id], on=True)
    assert payloads(call)[entity_id] == {
        "entity_id": entity_id, "brightness": 210, "xy_color": [0.17, 0.19],
    }


async def prepare_other_off_path(hass, store, selection, path):
    """Build an integration-owned single-light or snapshot-scene off action."""
    from custom_components.lichtzentrale.rooms import async_set_light
    from custom_components.lichtzentrale.scenes import async_apply_scene, async_save_scene

    entity_id = selection["ids"][0]
    if path == "single_light":
        async def turn_off():
            return await async_set_light(hass, store, entity_id, on=False)
    else:
        scene = await async_save_scene(hass, store, {
            "name": "Synthetic selected off scene", "kind": "snapshot",
            "area_id": selection["areas"][0], "lights": {entity_id: {"on": False}},
        })

        async def turn_off():
            return await async_apply_scene(hass, store, scene["id"])
    return turn_off


@pytest.mark.parametrize("path", ["single_light", "snapshot_scene"])
async def test_newer_other_off_path_replaces_selected_off_snapshot(hass, store, selection, path):
    entity_id = selection["ids"][0]
    turn_off = await prepare_other_off_path(hass, store, selection, path)
    with patch.object(type(hass.services), "async_call", AsyncMock()) as call:
        state(hass, entity_id, "on", brightness=90, xy_color=[0.6, 0.3])
        await async_control_lights(hass, store, [entity_id], on=False)
        state(hass, entity_id, "off")
        await async_control_lights(hass, store, [entity_id], on=True)
        state(hass, entity_id, "on", brightness=210, xy_color=[0.17, 0.19])
        call.reset_mock()
        await turn_off()
        assert any(c.args[1] == "turn_off" for c in call.await_args_list)
        state(hass, entity_id, "off")
        # Reload proves the newer cross-path snapshot is persisted, not just cached.
        reloaded = LichtzentraleStore(hass)
        await reloaded.async_load()
        call.reset_mock()
        await async_control_lights(hass, reloaded, [entity_id], on=True)
    assert payloads(call)[entity_id] == {
        "entity_id": entity_id, "brightness": 210, "xy_color": [0.17, 0.19],
    }


@pytest.mark.parametrize("path", ["single_light", "snapshot_scene"])
async def test_other_off_path_save_failure_prevents_dispatch(hass, store, selection, path):
    entity_id = selection["ids"][0]
    turn_off = await prepare_other_off_path(hass, store, selection, path)
    with patch.object(type(hass.services), "async_call", AsyncMock()):
        await async_control_lights(hass, store, [entity_id], on=False)
    saved = deepcopy(store.data["settings"]["last_light_states"])
    state(hass, entity_id, "on", brightness=210, xy_color=[0.17, 0.19])
    with (patch.object(store._store, "async_save", AsyncMock(side_effect=OSError("synthetic disk error"))),
          patch.object(type(hass.services), "async_call", AsyncMock()) as call):
        with pytest.raises((OSError, HomeAssistantError)):
            await turn_off()
    call.assert_not_awaited()
    assert store.data["settings"]["last_light_states"] == saved


@pytest.mark.parametrize("action", ["dim_up", "dim_down"])
@pytest.mark.parametrize("power", ["on", "off"])
async def test_binding_dim_always_skips_switch_even_with_dimmable_attributes(
    hass, store, selection, action, power,
):
    from custom_components.lichtzentrale.bindings import BindingManager

    switch = selection["ids"][-1]
    state(hass, switch, power, brightness=123, supported_color_modes=["brightness"])
    binding = validate_binding(hass, store, {
        "event_entity": selection["button"], "event_type": "short_release",
        "action": action, "area_id": None, "params": {"entity_ids": [switch]},
    })
    with patch.object(type(hass.services), "async_call", AsyncMock()) as call:
        result = await BindingManager(hass, store)._action(binding, Context())
    assert result == {"applied": [], "skipped": [switch]}
    call.assert_not_awaited()


async def test_room_off_does_not_dispatch_after_snapshot_state_changes(hass, store, selection):
    from custom_components.lichtzentrale.rooms import async_toggle_room

    lamp = selection["ids"][0]
    original = store._store.async_save

    async def save_then_change(data):
        await original(data)
        state(hass, lamp, "on", brightness=210, xy_color=[0.17, 0.19])

    with (patch.object(store._store, "async_save", side_effect=save_then_change),
          patch.object(type(hass.services), "async_call", AsyncMock()) as call):
        result = await async_toggle_room(hass, store, selection["areas"][0], on=False)
    assert lamp in result["skipped"]
    assert lamp not in payloads(call)
