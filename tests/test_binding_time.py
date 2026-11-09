# Geändert für Lichtzentrale
# ruff: noqa: F811 -- shared native HA fixtures are injected by name
"""Synthetic button time-of-day rules, using the common solar/DST window resolver."""

from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from test_bindings import press, raw, rig, scene  # noqa: F401

from custom_components.lichtzentrale.bindings import validate_binding
from custom_components.lichtzentrale.storage import LichtzentraleStore

ZONE = ZoneInfo("Europe/Berlin")


def clock_window(after, before, brightness, kelvin=None):
    return {"window": {"after": {"type": "time", "value": after},
                       "before": {"type": "time", "value": before}},
            "mode": "brightness", "brightness": brightness,
            **({"color_temp_kelvin": kelvin} if kelvin is not None else {})}


def time_binding(hass, store, rig, windows, action="turn_on_lights"):
    return validate_binding(hass, store, raw(rig, action, params={
        **({"entity_ids": rig["lights"]} if action.endswith("lights") else {}),
        "on_behavior": {"mode": "time", "windows": windows},
    }))


@pytest.mark.parametrize("hour,minute,expected,kelvin", [
    (0, 0, 13, 2000), (5, 59, 13, 2000), (6, 0, 255, 4000),
    (17, 59, 255, 4000), (18, 0, 76, 2200), (22, 0, 13, 2000),
])
async def test_clock_local_boundaries_and_binary_safety(hass, store, rig, hour, minute, expected, kelvin):
    dt_util.set_default_time_zone(ZONE)
    target = rig["lights"][0]
    state = hass.states.get(target)
    hass.states.async_set(target, "off", {**state.attributes, "supported_color_modes": ["color_temp"],
                                          "color_mode": "color_temp", "min_color_temp_kelvin": 2000,
                                          "max_color_temp_kelvin": 6500})
    value = time_binding(hass, store, rig, [clock_window("06:00", "18:00", 255, 4000),
                                          clock_window("18:00", "22:00", 76, 2200),
                                          clock_window("22:00", "06:00", 13, 2000)])
    now = datetime(2026, 11, 9, hour, minute, tzinfo=ZONE)
    with patch("custom_components.lichtzentrale.schedule_windows.dt_util.now", return_value=now), patch.object(type(hass.services), "async_call", AsyncMock()) as calls:
        await rig["manager"]._action(value, Context())
    data = {call.args[2]["entity_id"]: call.args[2] for call in calls.await_args_list}
    assert data[target]["brightness"] == expected
    assert data[target]["color_temp_kelvin"] == kelvin
    for binary in rig["lights"][2:]:
        assert data[binary] == {"entity_id": binary}


async def test_window_order_first_match_and_reload(hass, store, rig):
    first = clock_window("00:00", "00:00", 40)
    second = clock_window("00:00", "00:00", 200)
    value = time_binding(hass, store, rig, [first, second])
    saved = await store.async_save_binding({key: item for key, item in value.items() if key != "id"})
    reload = LichtzentraleStore(hass)
    await reload.async_load()
    assert reload.data["bindings"][-1] == saved
    with patch.object(type(hass.services), "async_call", AsyncMock()) as calls:
        await rig["manager"]._action(saved, Context())
    assert calls.await_args_list[0].args[2]["brightness"] == 40


async def test_gap_preserves_legacy_room_behavior(hass, store, rig):
    for entity in rig["lights"]:
        state = hass.states.get(entity)
        hass.states.async_set(entity, "off", state.attributes)
    value = time_binding(hass, store, rig, [clock_window("06:00", "18:00", 255)], "toggle_room")
    now = datetime(2026, 11, 9, 23, tzinfo=ZONE)
    with patch("custom_components.lichtzentrale.schedule_windows.dt_util.now", return_value=now), patch("custom_components.lichtzentrale.bindings.async_toggle_room", AsyncMock()) as call:
        await rig["manager"]._action(value, Context())
    assert call.await_args.kwargs["on"] is None


async def test_solar_offset_applies_scene_only_to_selected_members(hass, store, rig, light_calls):
    saved = await scene(hass, store, rig)
    value = validate_binding(hass, store, raw(rig, "turn_on_lights", params={
        "entity_ids": [rig["lights"][0]], "on_behavior": {"mode": "time", "windows": [{
            "window": {"after": {"type": "sun", "event": "sunset", "offset_min": -30},
                       "before": {"type": "time", "value": "23:00"}},
            "mode": "scene", "scene_id": saved["id"],
        }]},
    }))
    now = datetime(2026, 11, 9, 17, 30, tzinfo=ZONE)
    def sunset(hass, event, day):
        assert event == "sunset"
        return datetime.combine(day, datetime.min.time(), ZONE).replace(hour=18)
    with patch("custom_components.lichtzentrale.schedule_windows.dt_util.now", return_value=now), patch("custom_components.lichtzentrale.schedule_windows.get_astral_event_date", side_effect=sunset):
        await rig["manager"]._action(value, Context())
    assert [call.data["entity_id"] for call in light_calls] == [rig["lights"][0]]
    assert light_calls[0].data["brightness"] == 100


async def test_time_toggle_on_only_never_colors_off(hass, store, rig):
    value = time_binding(hass, store, rig, [clock_window("00:00", "00:00", 255, 4000)], "toggle_lights")
    with patch.object(type(hass.services), "async_call", AsyncMock()) as calls:
        await rig["manager"]._action(value, Context())
    assert all(call.args[1] == "turn_off" and set(call.args[2]) == {"entity_id"} for call in calls.await_args_list)


@pytest.mark.parametrize("windows", [[], [{}], [{"window": None, "mode": "brightness", "brightness": 20}],
    [clock_window("24:00", "01:00", 20)], [clock_window("00:00", "01:00", 0)],
    [clock_window("00:00", "01:00", 20, 999)], [clock_window("00:00", "01:00", 20, True)],
    [{**clock_window("00:00", "01:00", 20), "mode": "last"}],
    [clock_window("00:00", "01:00", 20)] * 25,
    [{**clock_window("00:00", "01:00", 20), "unexpected": 1}],
])
async def test_time_schema_rejects_invalid_or_unbounded_config(hass, store, rig, windows):
    with pytest.raises(ServiceValidationError):
        time_binding(hass, store, rig, windows)


async def test_deleted_on_scene_does_not_block_runtime_toggle_off(hass, store, rig):
    saved = await scene(hass, store, rig)
    await store.async_save_binding(raw(rig, "toggle_lights", params={
        "entity_ids": [rig["lights"][0]],
        "on_behavior": {"mode": "scene", "scene_id": saved["id"]},
    }))
    await store.async_delete_scene(saved["id"])
    with patch.object(type(hass.services), "async_call", AsyncMock()) as calls:
        await press(hass, rig)
    assert len(calls.await_args_list) == 1
    assert calls.await_args.args[:2] == ("light", "turn_off")
    assert calls.await_args.args[2] == {"entity_id": rig["lights"][0]}


async def test_stale_inactive_window_does_not_block_current_brightness(hass, store, rig):
    saved = await scene(hass, store, rig)
    value = time_binding(hass, store, rig, [clock_window("00:00", "00:00", 90)])
    value["params"]["entity_ids"] = [rig["lights"][0]]
    value["params"]["on_behavior"]["windows"].append({
        "window": {"after": {"type": "time", "value": "00:00"},
                   "before": {"type": "time", "value": "00:00"}},
        "mode": "scene", "scene_id": saved["id"],
    })
    await store.async_save_binding({key: item for key, item in value.items() if key != "id"})
    await store.async_delete_scene(saved["id"])
    with patch.object(type(hass.services), "async_call", AsyncMock()) as calls:
        await press(hass, rig)
    assert calls.await_args_list[0].args[2]["brightness"] == 90
