# Geändert für Lichtzentrale
"""Dynamic palettes remain scoped, cancellable and observable."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from custom_components.lichtzentrale.dynamic_scenes import DynamicSceneManager, validate_dynamic
from custom_components.lichtzentrale.rooms import async_toggle_room
from custom_components.lichtzentrale.scenes import async_apply_scene, async_save_scene


@pytest.fixture
async def running(hass, store):
    area = ar.async_get(hass).async_create("Synthetic dynamic room")
    ids = []
    for i in range(3):
        entry = er.async_get(hass).async_get_or_create("light", "fixture", f"dynamic-{i}")
        er.async_get(hass).async_update_entity(entry.entity_id, area_id=area.id)
        hass.states.async_set(entry.entity_id, "on", {"supported_color_modes": ["xy"]})
        ids.append(entry.entity_id)
    await store.async_set_lights(ids)
    scene = await async_save_scene(
        hass,
        store,
        {
            "name": "Synthetic loop",
            "area_id": area.id,
            "kind": "palette",
            "palette_id": "kupfernest",
            "dynamic": {"enabled": True, "interval": 5, "transition": 2},
        },
    )
    manager = DynamicSceneManager(hass, store)
    hass.data["lichtzentrale"] = {"store": store, "dynamic": manager}
    yield manager, scene, ids
    await manager.shutdown()


@pytest.mark.parametrize(
    "value,kind",
    [
        ({"enabled": 1}, "palette"),
        ({"interval": float("nan")}, "palette"),
        ({"interval": 4}, "palette"),
        ({"transition": 61}, "palette"),
        ({"interval": 5, "transition": 6}, "palette"),
        ({"enabled": True}, "snapshot"),
        ({"enabled": True}, "hue"),
        ({"unknown": 1}, "palette"),
    ],
)
def test_invalid(value, kind):
    with pytest.raises(ServiceValidationError):
        validate_dynamic(value, kind)


async def test_ticks_rotate_and_never_rekindle_or_expand(hass, store, running, light_calls):
    manager, scene, ids = running
    context = Context()
    await manager.start(store.data["scenes"][0], context)
    run = manager.active[scene["area_id"]]
    assert await manager.tick(run, 1)
    first_color = light_calls[0].data["xy_color"]
    light_calls.clear()
    hass.states.async_set(ids[1], "off", {"supported_color_modes": ["xy"]})
    await store.async_set_lights(ids[:2])
    assert await manager.tick(run, 2)
    assert [c.data["entity_id"] for c in light_calls] == [ids[0]]
    assert light_calls[0].data["xy_color"] != first_color
    assert light_calls[0].context == context


async def test_replace_stop_external_off_and_shutdown(hass, store, running):
    manager, scene, ids = running
    raw = store.data["scenes"][0]
    await manager.start(raw, None)
    old = manager.active[scene["area_id"]]["task"]
    await manager.start(raw, None)
    assert old.done()
    for entity in ids:
        hass.states.async_set(entity, "off")
    await hass.async_block_till_done()
    assert manager.list() == []
    await manager.start(raw, None)
    await manager.shutdown()
    assert manager.list() == []
    with pytest.raises(ServiceValidationError):
        await manager.start(raw, None)


async def test_deleted_or_changed_scene_stops(hass, store, running):
    manager, scene, _ = running
    await manager.start(store.data["scenes"][0], None)
    run = manager.active[scene["area_id"]]
    await store.async_delete_scene(scene["id"])
    assert not await manager.tick(run, 1)


async def test_recall_starts_and_room_off_cancels(hass, store, running, light_calls):
    manager, scene, ids = running
    hass.services.async_register("light", "turn_off", lambda call: None)
    await async_apply_scene(hass, store, scene["id"])
    assert manager.list()[0]["scene_id"] == scene["id"]
    await async_toggle_room(hass, store, scene["area_id"], False)
    assert manager.list() == []


async def test_failed_tick_stops(hass, store, running):
    manager, scene, _ = running
    await manager.start(store.data["scenes"][0], None)
    with patch(
        "custom_components.lichtzentrale.palettes._async_dispatch_tick",
        AsyncMock(return_value={"failed": ["fixture"]}),
    ):
        assert not await manager.tick(manager.active[scene["area_id"]], 1)


async def test_partial_initial_targets_never_expand(hass, store, running, light_calls):
    manager, scene, ids = running
    await manager.start(store.data["scenes"][0], None, [ids[0]])
    assert await manager.tick(manager.active[scene["area_id"]], 1)
    assert [call.data["entity_id"] for call in light_calls] == [ids[0]]


async def test_malformed_restored_snapshot_has_no_side_effects(hass, store, running):
    manager, scene, ids = running
    invalid = {
        **store.data["scenes"][0],
        "kind": "snapshot",
        "dynamic": {"enabled": False},
        "lights": {ids[0]: {"on": True, "xy": [float("nan"), 0.2]}},
    }
    await store.async_save_scene(invalid, is_update=True)
    with patch(
        "custom_components.lichtzentrale.adaptive.async_pause_adaptive", AsyncMock()
    ) as pause:
        with pytest.raises(ServiceValidationError):
            await async_apply_scene(hass, store, scene["id"])
    pause.assert_not_awaited()


async def test_palette_rechecks_allowlist_after_pause(hass, store, running, light_calls):
    from custom_components.lichtzentrale.palettes import async_apply_palette

    _, _, ids = running

    async def revoke(*args, **kwargs):
        await store.async_set_lights([])

    with patch("custom_components.lichtzentrale.adaptive.async_pause_adaptive", side_effect=revoke):
        with pytest.raises(ServiceValidationError):
            await async_apply_palette(hass, store, "kupfernest", ids)
    assert not light_calls


async def test_palette_and_room_off_serialize(hass, store, running, light_calls):
    import asyncio

    from custom_components.lichtzentrale.palettes import async_apply_palette

    _, scene, ids = running
    started, proceed = asyncio.Event(), asyncio.Event()
    order = []

    async def pause(*args, **kwargs):
        started.set()
        await proceed.wait()

    async def dispatch(domain, service, params, **kwargs):
        order.append(service)

    with (
        patch("custom_components.lichtzentrale.adaptive.async_pause_adaptive", side_effect=pause),
        patch.object(type(hass.services), "async_call", side_effect=dispatch),
    ):
        palette = asyncio.create_task(async_apply_palette(hass, store, "kupfernest", ids))
        await started.wait()
        off = asyncio.create_task(async_toggle_room(hass, store, scene["area_id"], False))
        await asyncio.sleep(0)
        assert not order
        proceed.set()
        await asyncio.gather(palette, off)
    assert order == ["turn_on"] * len(ids) + ["turn_off"] * len(ids)


async def test_room_toggle_revalidates_after_stop(hass, store, running, light_calls):
    _, scene, ids = running
    await store.async_update_room(
        scene["area_id"], {"pre_off_lights": {entity: {"on": True} for entity in ids}}
    )

    async def revoke(*args):
        await store.async_set_lights(ids[1:])

    with patch("custom_components.lichtzentrale.dynamic_scenes.stop_dynamic", side_effect=revoke):
        await async_toggle_room(hass, store, scene["area_id"], True)
    assert [call.data["entity_id"] for call in light_calls] == ids[1:]


async def test_cosmetic_edits_keep_playback(hass, store, running, light_calls):
    manager, scene, _ = running
    await manager.start(store.data["scenes"][0], None)
    changed = {**store.data["scenes"][0], "favorite": True, "order": 17, "name": "New title"}
    await store.async_save_scene(changed, is_update=True)
    assert await manager.tick(manager.active[scene["area_id"]], 1)
    assert manager.list()[0]["name"] == "New title"
    assert light_calls


async def test_delete_immediately_stops_only_matching_run(hass, store, running):
    from custom_components.lichtzentrale.scenes import async_delete_scene

    manager, scene, _ = running
    original = store.data["scenes"][0]
    other = {**original, "id": "synthetic-other"}
    await store.async_save_scene(other)
    await manager.start(original, None)
    await async_delete_scene(store, other["id"], hass)
    assert manager.list()[0]["scene_id"] == original["id"]
    await async_delete_scene(store, original["id"], hass)
    assert manager.list() == []


@pytest.mark.parametrize(
    "value,kind",
    [({"welle": 1}, "palette"), ({"welle": True}, "hue"), ({"welle": True}, "snapshot")],
)
def test_invalid_wave(value, kind):
    with pytest.raises(ServiceValidationError):
        validate_dynamic(value, kind)


async def test_wave_preserves_axis_when_lamp_disappears(hass, store, running, light_calls):
    manager, scene, ids = running
    raw = {**store.data["scenes"][0], "verteilung": "verlauf_links_rechts"}
    raw["dynamic"]["welle"] = True
    await store.async_save_scene(raw, is_update=True)
    for i, e in enumerate(ids):
        await store.async_set_position(scene["area_id"], e, {"cell": [i, 0], "height": "boden"})
    await manager.start(raw, None)
    run = manager.active[scene["area_id"]]
    assert await manager.tick(run, 1)
    expected = {c.data["entity_id"]: c.data["xy_color"] for c in light_calls}
    light_calls.clear()
    hass.states.async_remove(ids[0])
    assert await manager.tick(run, 1)
    assert {c.data["entity_id"]: c.data["xy_color"] for c in light_calls} == {
        e: expected[e] for e in ids[1:]
    }


@pytest.mark.parametrize(
    "mode,value",
    [
        ("xy", [0.3, 0.4]),
        ("hs", [120, 70]),
        ("rgb", [12, 34, 56]),
        ("rgbw", [12, 34, 56, 78]),
        ("rgbww", [12, 34, 56, 78, 90]),
        ("color_temp", 3000),
    ],
)
async def test_stop_freezes_native_mode(hass, store, running, light_calls, mode, value):
    from custom_components.lichtzentrale.dynamic_scenes import async_stop_room

    manager, scene, ids = running
    field = "color_temp_kelvin" if mode == "color_temp" else f"{mode}_color"
    attrs = {
        "color_mode": mode,
        "supported_color_modes": [mode],
        "brightness": 111,
        "xy_color": [0.1, 0.1],
        field: value,
    }
    hass.states.async_set(ids[0], "on", attrs)
    hass.states.async_set(ids[1], "off", attrs)
    hass.states.async_set(ids[2], "unavailable", attrs)
    await manager.start(store.data["scenes"][0], None)
    context = Context()
    result = await async_stop_room(hass, store, scene["area_id"], context=context)
    assert result == {"stopped": True, "applied": ids[:1], "skipped": ids[1:]}
    assert manager.list() == []
    assert light_calls[0].context == context
    assert light_calls[0].data == {
        "entity_id": ids[0],
        "brightness": 111,
        field: tuple(value) if isinstance(value, list) else value,
    }


async def test_stop_revalidates_grants_and_state_after_stop(hass, store, running, light_calls):
    from custom_components.lichtzentrale.dynamic_scenes import async_stop_room

    _, scene, ids = running
    attrs = {
        "supported_color_modes": ["xy"],
        "color_mode": "xy",
        "brightness": 111,
        "xy_color": [0.3, 0.4],
    }
    for e in ids:
        hass.states.async_set(e, "on", attrs)

    async def stop(*args):
        await store.async_set_lights(ids[1:])
        hass.states.async_set(ids[1], "off", attrs)
        hass.states.async_set(ids[2], "on", {**attrs, "xy_color": [0.5, 0.4]})
        return {"stopped": True}

    with patch("custom_components.lichtzentrale.dynamic_scenes.stop_dynamic", side_effect=stop):
        result = await async_stop_room(hass, store, scene["area_id"])
    assert result == {"stopped": True, "applied": ids[2:], "skipped": ids[1:2]}
    assert light_calls[0].data["xy_color"] == (0.5, 0.4)


async def test_stop_partial_failure(hass, store, running):
    from custom_components.lichtzentrale.dynamic_scenes import async_stop_room

    _, scene, ids = running
    for e in ids:
        hass.states.async_set(
            e,
            "on",
            {
                "color_mode": "brightness",
                "supported_color_modes": ["brightness"],
                "brightness": 100,
            },
        )

    async def call(domain, service, data, **kwargs):
        if data["entity_id"] == ids[0]:
            raise RuntimeError("Synthetic failure")

    with patch.object(type(hass.services), "async_call", side_effect=call):
        result = await async_stop_room(hass, store, scene["area_id"])
    assert result == {"stopped": False, "applied": ids[1:], "skipped": [], "failed": ids[:1]}


@pytest.mark.parametrize(
    "attrs",
    [
        {"color_mode": "xy", "supported_color_modes": ["hs"], "xy_color": [0.3, 0.4]},
        {"color_mode": "xy", "supported_color_modes": ["xy"], "xy_color": [float("nan"), 0.4]},
        {"color_mode": "rgbw", "supported_color_modes": ["rgbw"], "xy_color": [0.3, 0.4]},
        {
            "color_mode": "xy",
            "supported_color_modes": ["xy"],
            "xy_color": [0.3, 0.4],
            "brightness": True,
        },
    ],
)
def test_freeze_skips_missing_or_invalid_native_state(attrs):
    from homeassistant.core import State

    from custom_components.lichtzentrale.dynamic_scenes import freeze_payload

    assert freeze_payload(State("light.synthetic", "on", {"brightness": 100, **attrs})) is None
    assert freeze_payload(State("switch.synthetic", "on", attrs)) is None


async def test_stop_checks_each_payload_immediately_before_dispatch(hass, store, running):
    from custom_components.lichtzentrale.dynamic_scenes import async_stop_room

    _, scene, ids = running
    attrs = {"color_mode": "brightness", "supported_color_modes": ["brightness"], "brightness": 100}
    for e in ids:
        hass.states.async_set(e, "on", attrs)
    called = []

    async def call(domain, service, data, **kwargs):
        called.append(data)
        if data["entity_id"] == ids[0]:
            hass.states.async_set(ids[1], "off", attrs)
            hass.states.async_set(ids[2], "on", {**attrs, "brightness": 150})

    with patch.object(type(hass.services), "async_call", side_effect=call):
        result = await async_stop_room(hass, store, scene["area_id"])
    assert result["applied"] == [ids[0], ids[2]]
    assert result["skipped"] == [ids[1]]
    assert called[1]["brightness"] == 150


@pytest.mark.parametrize("change", ["off", "revoke", "move", "missing", "group", "disabled"])
async def test_tick_revalidates_after_dispatch_scheduling(
    hass, store, running, light_calls, change
):
    """A registry/state change after payload preparation cannot rekindle or target a peer."""
    import asyncio

    from custom_components.lichtzentrale.palettes import _async_dispatch_tick

    manager, scene, ids = running
    context = Context()
    await manager.start(store.data["scenes"][0], context)
    run = manager.active[scene["area_id"]]
    other_area = ar.async_get(hass).async_create("Synthetic other room")

    async def change_at_boundary(*args):
        # This callback is queued before gather schedules child service calls,
        # exactly where payload preparation alone leaves a race.
        def mutate():
            if change == "off":
                hass.states.async_set(ids[0], "off", {"supported_color_modes": ["xy"]})
            elif change == "revoke":
                store._data["settings"]["light_entity_ids"] = ids[1:]
            elif change == "move":
                er.async_get(hass).async_update_entity(ids[0], area_id=other_area.id)
            elif change == "missing":
                hass.states.async_remove(ids[0])
            elif change == "group":
                hass.states.async_set(
                    ids[0], "on", {"is_hue_group": True, "supported_color_modes": ["xy"]}
                )
            else:
                er.async_get(hass).async_update_entity(
                    ids[0], disabled_by=er.RegistryEntryDisabler.USER
                )

        asyncio.get_running_loop().call_soon(mutate)
        return await _async_dispatch_tick(*args)

    with patch(
        "custom_components.lichtzentrale.palettes._async_dispatch_tick",
        side_effect=change_at_boundary,
    ):
        assert await manager.tick(run, 1)
    assert [call.data["entity_id"] for call in light_calls] == ids[1:]
    assert all(call.context == context for call in light_calls)


async def test_switch_cannot_keep_dynamic_run_alive(hass, store, running):
    manager, scene, ids = running
    switch = er.async_get(hass).async_get_or_create(
        "switch", "shelly", "fixture-dynamic-switch", original_name="Fixture Licht"
    )
    er.async_get(hass).async_update_entity(switch.entity_id, area_id=scene["area_id"])
    hass.states.async_set(switch.entity_id, "on")
    await store.async_set_lights([*ids, switch.entity_id])
    await manager.start(store.data["scenes"][0], None)
    run = manager.active[scene["area_id"]]
    assert run["targets"] == ids
    assert run["layout_targets"] == ids
    for e in ids:
        hass.states.async_set(e, "off")
    await hass.async_block_till_done()
    assert manager.list() == []
    await store.async_set_lights([switch.entity_id])
    await manager.start(store.data["scenes"][0], None)
    assert manager.list() == []
