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
        if len(entered) == 3:
            ready.set()
        await asyncio.wait_for(ready.wait(), 1)
        if data["entity_id"] == ids[1]:
            raise RuntimeError("Synthetic failure")

    with patch.object(type(hass.services), "async_call", side_effect=call):
        result = await async_toggle_room(hass, store, area.id, context=context)
    assert result == {"applied": [ids[0], ids[2]], "skipped": [], "failed": [ids[1]]}
    assert all(item[1] == "turn_off" and item[3] == context for item in entered)
    assert entered[2][0] == "switch"


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
    assert room["on"]
    with patch.object(type(hass.services), "async_call") as call:
        await async_toggle_room(hass, store, area.id, on=False)
        assert call.call_args.args == ("switch", "turn_off", {"entity_id": ids[2]})
    await store.async_set_lights([ids[0]])
    hass.states.async_set(ids[0], "on", {"supported_color_modes": ["onoff"]})
    with patch.object(type(hass.services), "async_call") as call:
        assert (await async_set_light(hass, store, ids[0], brightness=120))["skipped"]
        call.assert_not_called()
        await async_set_light(hass, store, ids[0], on=True, xy=[0.3, 0.3], brightness=120)
        assert call.call_args.args == ("light", "turn_on", {"entity_id": ids[0]})
