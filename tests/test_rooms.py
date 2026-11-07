"""Room controls never escape the explicit lighting selection."""

import asyncio
from unittest.mock import patch

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from custom_components.lichtzentrale.rooms import (
    async_room_brightness,
    async_set_light,
    async_toggle_room,
    list_rooms,
    room_targets,
)


async def fixtures(hass, store):
    area = ar.async_get(hass).async_create("Fixture room")
    ids = []
    for domain, platform, name, mode in [
        ("light", "synthetic", "Fixture color", "xy"),
        ("light", "synthetic", "Fixture dimmer", "brightness"),
        ("switch", "shelly", "Fixture Deckenlicht", None),
    ]:
        entry = er.async_get(hass).async_get_or_create(
            domain,
            platform,
            name,
            original_name=name,
        )
        er.async_get(hass).async_update_entity(entry.entity_id, area_id=area.id)
        hass.states.async_set(
            entry.entity_id,
            "on",
            {
                "supported_color_modes": [mode] if mode else [],
                "brightness": 100,
            },
        )
        ids.append(entry.entity_id)
    await store.async_set_lights(ids)
    return area, ids


async def test_rooms_only_include_approved_assigned_lighting(hass, store):
    area, ids = await fixtures(hass, store)
    ar.async_get(hass).async_create("Empty area")
    hass.states.async_set("light.fixture_unassigned", "on")
    await store.async_set_lights(ids + ["light.fixture_unassigned"])
    rooms = list_rooms(hass, store)
    assert len(rooms) == 1
    assert rooms[0]["area_id"] == area.id
    assert len(rooms[0]["lights"]) == 3
    assert rooms[0]["brightness"] == 100
    assert rooms[0]["available_count"] == 3
    assert rooms[0]["last_scene_id"] is None
    assert room_targets(hass, store, area.id) == ids
    with pytest.raises(ServiceValidationError):
        room_targets(hass, store, "not-a-room")


async def test_toggle_is_parallel_and_isolates_failures(hass, store):
    area, ids = await fixtures(hass, store)
    entered = []
    ready = asyncio.Event()
    context = Context()

    async def call(domain, service, data, blocking, context):
        entered.append((domain, service, data, context))
        if len(entered) == 2:
            ready.set()
        await asyncio.wait_for(ready.wait(), 1)
        if data["entity_id"] == ids[1]:
            raise RuntimeError("Synthetic failure")

    with patch.object(type(hass.services), "async_call", side_effect=call):
        result = await async_toggle_room(hass, store, area.id, context=context)
    assert result == {"applied": [ids[0]], "skipped": [ids[2]], "failed": [ids[1]]}
    assert all(item[1] == "turn_off" and item[3] == context for item in entered)
    assert all(item[0] == "light" for item in entered)


async def test_brightness_leaves_off_and_binary_lights_untouched(hass, store, light_calls):
    area, ids = await fixtures(hass, store)
    hass.states.async_set(ids[1], "off", {"supported_color_modes": ["brightness"]})
    result = await async_room_brightness(hass, store, area.id, 150)
    assert result == {"applied": [ids[0]], "skipped": ids[1:]}
    assert light_calls[0].data["brightness"] == 150


@pytest.mark.parametrize(
    "options",
    [
        {"brightness": 0},
        {"brightness": True},
        {"xy": [1, float("nan")]},
        {"xy": [0.1]},
        {"xy": [0.1, 0.2], "color_temp_kelvin": 3000},
        {"on": False, "brightness": 200},
        {"on": "on"},
        {"color_temp_kelvin": -1},
    ],
)
async def test_invalid_control_values_are_atomic(hass, store, light_calls, options):
    _, ids = await fixtures(hass, store)
    with pytest.raises(ServiceValidationError):
        await async_set_light(hass, store, ids[0], **options)
    assert not light_calls


async def test_single_light_allowlist_and_unsupported_modes(hass, store, light_calls):
    _, ids = await fixtures(hass, store)
    await store.async_set_lights(ids[1:])
    with pytest.raises(ServiceValidationError):
        await async_set_light(hass, store, ids[0], on=True)
    assert await async_set_light(hass, store, ids[2], brightness=120) == {
        "applied": [],
        "skipped": [ids[2]],
    }
    assert not light_calls


async def test_ct_clamping_and_unavailable_skip(hass, store, light_calls):
    _, ids = await fixtures(hass, store)
    attrs = {
        "supported_color_modes": ["color_temp"],
        "min_color_temp_kelvin": 2700,
        "max_color_temp_kelvin": 4000,
    }
    hass.states.async_set(ids[0], "on", attrs)
    await async_set_light(hass, store, ids[0], color_temp_kelvin=6500)
    assert light_calls[0].data["color_temp_kelvin"] == 4000
    hass.states.async_set(ids[0], "unavailable", attrs)
    assert (await async_set_light(hass, store, ids[0], on=True))["skipped"] == [ids[0]]
    assert len(light_calls) == 1


async def test_room_rejects_group_before_dispatch(hass, store, light_calls):
    area, ids = await fixtures(hass, store)
    hass.states.async_set(ids[1], "on", {"entity_id": [ids[0]]})
    with pytest.raises(ServiceValidationError):
        await async_toggle_room(hass, store, area.id, on=True)
    assert not light_calls


async def test_switch_only_room_and_onoff_light(hass, store):
    area, ids = await fixtures(hass, store)
    await store.async_set_lights([ids[2]])
    room = list_rooms(hass, store)[0]
    assert room["area_id"] == area.id
    assert room["brightness"] is None
    assert not room["on"]
    with patch.object(type(hass.services), "async_call") as call:
        await async_toggle_room(hass, store, area.id, on=False)
        call.assert_not_called()
    await store.async_set_lights([ids[0]])
    hass.states.async_set(ids[0], "on", {"supported_color_modes": ["onoff"]})
    with patch.object(type(hass.services), "async_call") as call:
        assert (await async_set_light(hass, store, ids[0], brightness=120))["skipped"]
        call.assert_not_called()
        await async_set_light(hass, store, ids[0], on=True, xy=[0.3, 0.3], brightness=120)
        assert call.call_args.args == ("light", "turn_on", {"entity_id": ids[0]})


async def test_restore_mixed_lights_survives_reload_and_repeated_off(hass, store, light_calls):
    from custom_components.lichtzentrale.storage import LichtzentraleStore

    area, ids = await fixtures(hass, store)
    attrs = {
        "supported_color_modes": ["xy"],
        "color_mode": "xy",
        "xy_color": [0.3, 0.4],
        "brightness": 75,
    }
    hass.states.async_set(ids[0], "on", attrs)
    hass.states.async_set(ids[1], "off", {"supported_color_modes": ["brightness"]})
    await store.async_update_room(
        area.id, {"positions": {ids[0]: {"cell": [1, 1], "height": "boden"}}}
    )
    with patch.object(type(hass.services), "async_call"):
        await async_toggle_room(hass, store, area.id, on=False)
    for entity in ids:
        hass.states.async_set(entity, "off", attrs if entity == ids[0] else {})
    with patch.object(type(hass.services), "async_call"):
        await async_toggle_room(hass, store, area.id, on=False)
    reloaded = LichtzentraleStore(hass)
    await reloaded.async_load()
    assert reloaded.data["rooms"][area.id]["positions"]
    assert ids[2] not in reloaded.data["rooms"][area.id]["pre_off_lights"]
    result = await async_toggle_room(hass, reloaded, area.id, on=True)
    assert result == {"applied": [ids[0]], "skipped": ids[1:]}
    assert dict(light_calls[0].data) == {
        "entity_id": ids[0],
        "brightness": 75,
        "xy_color": [0.3, 0.4],
    }


async def test_first_on_never_enables_new_lights_or_switches(hass, store, light_calls):
    area, ids = await fixtures(hass, store)
    result = await async_toggle_room(hass, store, area.id, on=True)
    assert result == {"applied": [], "skipped": ids}
    assert not light_calls


@pytest.mark.parametrize("mutation", ["revoked", "moved", "unavailable", "binary"])
async def test_restore_revalidates_saved_lights(hass, store, light_calls, mutation):
    area, ids = await fixtures(hass, store)
    with patch.object(type(hass.services), "async_call"):
        await async_toggle_room(hass, store, area.id, on=False)
    if mutation == "revoked":
        await store.async_set_lights(ids[1:])
    elif mutation == "moved":
        other = ar.async_get(hass).async_create("Other restore fixture")
        er.async_get(hass).async_update_entity(ids[0], area_id=other.id)
    elif mutation == "unavailable":
        hass.states.async_set(ids[0], "unavailable")
    else:
        hass.states.async_set(ids[0], "off", {"supported_color_modes": ["onoff"]})
    await async_toggle_room(hass, store, area.id, on=True)
    calls = [call for call in light_calls if call.data["entity_id"] == ids[0]]
    if mutation == "binary":
        assert dict(calls[0].data) == {"entity_id": ids[0]}
    else:
        assert not calls
    assert all(call.data["entity_id"] != ids[2] for call in light_calls)


@pytest.mark.parametrize("yield_point", ["stop", "save"])
async def test_room_off_revalidates_after_await(hass, store, yield_point):
    area, ids = await fixtures(hass, store)

    async def revoke(*args):
        await store.async_set_lights(ids[1:])

    target = (
        patch("custom_components.lichtzentrale.dynamic_scenes.stop_dynamic", side_effect=revoke)
        if yield_point == "stop"
        else patch.object(store, "async_update_room", side_effect=revoke)
    )
    with target, patch.object(type(hass.services), "async_call") as call:
        await async_toggle_room(hass, store, area.id, on=False)
    assert all(item.args[2]["entity_id"] != ids[0] for item in call.call_args_list)


async def test_snapshot_save_failure_does_not_switch_off(hass, store):
    area, _ = await fixtures(hass, store)
    with patch.object(store, "async_update_room", side_effect=OSError("fixture")):
        with patch.object(type(hass.services), "async_call") as call:
            with pytest.raises(OSError):
                await async_toggle_room(hass, store, area.id, on=False)
    call.assert_not_called()


async def test_restore_temperature_rechecks_device_limits(hass, store, light_calls):
    area, ids = await fixtures(hass, store)
    attrs = {
        "supported_color_modes": ["color_temp"],
        "color_mode": "color_temp",
        "color_temp_kelvin": 3000,
        "brightness": 42,
    }
    hass.states.async_set(ids[0], "on", attrs)
    with patch.object(type(hass.services), "async_call"):
        await async_toggle_room(hass, store, area.id, on=False)
    hass.states.async_set(ids[0], "off", {**attrs, "min_color_temp_kelvin": 3500})
    await async_toggle_room(hass, store, area.id, on=True)
    assert dict(light_calls[0].data) == {
        "entity_id": ids[0],
        "brightness": 42,
        "color_temp_kelvin": 3500,
    }


@pytest.mark.parametrize("mutation", ["revoked", "moved", "missing", "group"])
async def test_restore_revalidates_at_dispatch_boundary(hass, store, light_calls, mutation):
    from custom_components.lichtzentrale import rooms

    area, ids = await fixtures(hass, store)
    await store.async_update_room(area.id, {"pre_off_lights": {ids[0]: {"on": True}}})
    other = ar.async_get(hass).async_create("Dispatch boundary fixture")
    dispatch = rooms.async_dispatch

    def mutate():
        if mutation == "revoked":
            store._data["settings"]["light_entity_ids"] = ids[1:]
        elif mutation == "moved":
            er.async_get(hass).async_update_entity(ids[0], area_id=other.id)
        elif mutation == "missing":
            hass.states.async_remove(ids[0])
        else:
            hass.states.async_set(ids[0], "off", {"entity_id": [ids[1]]})

    async def at_boundary(*args, **kwargs):
        asyncio.get_running_loop().call_soon(mutate)
        return await dispatch(*args, **kwargs)

    with patch.object(rooms, "async_dispatch", side_effect=at_boundary):
        result = await async_toggle_room(hass, store, area.id, on=True)
    assert not result["applied"] and ids[0] in result["skipped"]
    assert not light_calls


async def test_partial_off_retry_keeps_original_snapshot_and_new_cycle_refreshes(hass, store):
    from custom_components.lichtzentrale.storage import LichtzentraleStore

    area, ids = await fixtures(hass, store)
    failed_once = False
    calls = []

    async def control(domain, service, data, **kwargs):
        nonlocal failed_once
        entity = data["entity_id"]
        calls.append((service, entity))
        if service == "turn_off" and entity == ids[1] and not failed_once:
            failed_once = True
            raise RuntimeError("Temporary device failure")
        attrs = dict(hass.states.get(entity).attributes)
        hass.states.async_set(entity, "on" if service == "turn_on" else "off", attrs)

    with patch.object(type(hass.services), "async_call", side_effect=control):
        first = await async_toggle_room(hass, store, area.id, on=False)
        assert first["failed"] == [ids[1]]
        reloaded = LichtzentraleStore(hass)
        await reloaded.async_load()
        await async_toggle_room(hass, reloaded, area.id, on=False)
        assert not reloaded.data["rooms"][area.id]["pre_off_pending"]
        restored = await async_toggle_room(hass, reloaded, area.id, on=True)
        assert restored["applied"] == ids[:2]
        # A genuinely new mixed cycle must not retain the old on lamp.
        hass.states.async_set(ids[0], "off", {"supported_color_modes": ["xy"]})
        await async_toggle_room(hass, reloaded, area.id, on=False)
        restored = await async_toggle_room(hass, reloaded, area.id, on=True)
        assert restored["applied"] == [ids[1]]
    assert all(entity != ids[2] for _, entity in calls)
    assert hass.states.get(ids[2]).state == "on"


async def test_switch_on_does_not_drive_room_toggle(hass, store, light_calls):
    area, ids = await fixtures(hass, store)
    for entity in ids[:2]:
        hass.states.async_set(entity, "off", {"supported_color_modes": ["brightness"]})
    await store.async_update_room(area.id, {"pre_off_lights": {ids[0]: {"on": True}}})
    assert not list_rooms(hass, store)[0]["on"]
    result = await async_toggle_room(hass, store, area.id)
    assert result["applied"] == [ids[0]]
    assert hass.states.get(ids[2]).state == "on"
    assert light_calls[0].service == "turn_on"


async def test_off_result_save_failure_retains_durable_retry_context(hass, store):
    from custom_components.lichtzentrale.storage import LichtzentraleStore

    area, ids = await fixtures(hass, store)
    update = store.async_update_room
    writes = 0

    async def fail_result_write(*args, **kwargs):
        nonlocal writes
        writes += 1
        if writes == 2:
            raise OSError("Result persistence failure")
        await update(*args, **kwargs)

    async def partial_off(domain, service, data, **kwargs):
        entity = data["entity_id"]
        if entity == ids[1]:
            raise RuntimeError("Device failure")
        hass.states.async_set(entity, "off", {"supported_color_modes": ["xy"]})

    with patch.object(store, "async_update_room", side_effect=fail_result_write):
        with patch.object(type(hass.services), "async_call", side_effect=partial_off):
            with pytest.raises(OSError):
                await async_toggle_room(hass, store, area.id, on=False)
    reloaded = LichtzentraleStore(hass)
    await reloaded.async_load()
    assert reloaded.data["rooms"][area.id]["pre_off_pending"] == ids[:2]
    with patch.object(type(hass.services), "async_call"):
        await async_toggle_room(hass, reloaded, area.id, on=False)
        assert (await async_toggle_room(hass, reloaded, area.id, on=True))["applied"] == ids[:2]
