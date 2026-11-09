# Geändert für Lichtzentrale
"""Zones retain existing dynamic, layout and optional-rule behavior safely."""

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from custom_components.lichtzentrale.brightness_config import validate_brightness
from custom_components.lichtzentrale.dynamic_scenes import DynamicSceneManager, async_stop_room
from custom_components.lichtzentrale.motion_config import validate_motion
from custom_components.lichtzentrale.palettes import list_palettes
from custom_components.lichtzentrale.scenes import async_apply_scene, async_save_scene
from custom_components.lichtzentrale.selected_lights import async_control_lights


@pytest.fixture
async def zone_runtime(hass, store):
    areas = [ar.async_get(hass).async_create(f"Synthetic zone room {i}") for i in range(2)]
    ids = []
    for i, area in enumerate(areas):
        entry = er.async_get(hass).async_get_or_create("light", "fixture", f"zone-runtime-{i}")
        er.async_get(hass).async_update_entity(entry.entity_id, area_id=area.id)
        hass.states.async_set(entry.entity_id, "on", {
            "supported_color_modes": ["xy"], "color_mode": "xy", "brightness": 100,
            "xy_color": [0.4, 0.3],
        })
        ids.append(entry.entity_id)
    await store.async_set_lights(ids)
    zone = await store.async_save_zone({"name": "Synthetic shared zone", "entity_ids": ids})
    area_id = "zone:" + zone["id"]
    scene = await async_save_scene(hass, store, {
        "name": "Synthetic zone colors", "area_id": area_id, "kind": "palette",
        "palette_id": "kupfernest", "verteilung": "verlauf_links_rechts",
        "dynamic": {"enabled": True, "interval": 5, "transition": 2},
    })
    manager = DynamicSceneManager(hass, store)
    hass.data["lichtzentrale"] = {"store": store, "dynamic": manager}
    yield areas, ids, area_id, scene, manager
    await manager.shutdown()


async def test_zone_palette_uses_zone_positions_initially_and_on_ticks(hass, store, zone_runtime, light_calls):
    _, ids, zone, scene, manager = zone_runtime
    await store.async_set_position(zone, ids[0], {"cell": [2, 0], "height": "boden"})
    await store.async_set_position(zone, ids[1], {"cell": [0, 0], "height": "boden"})
    await async_apply_scene(hass, store, scene["id"], Context())
    colors = next(p for p in list_palettes() if p["id"] == "kupfernest")["colors"]
    by_id = {c.data["entity_id"]: c.data["xy_color"] for c in light_calls}
    assert tuple(by_id[ids[0]]) == (colors[-1]["x"], colors[-1]["y"])
    assert tuple(by_id[ids[1]]) == (colors[0]["x"], colors[0]["y"])
    light_calls.clear()
    assert await manager.tick(manager.active[zone], 1)
    assert {c.data["entity_id"] for c in light_calls} == set(ids)
    # Removing membership mid-run must not expand or command an old target.
    saved_zone = store.data["zones"][0]
    await store.async_save_zone({**saved_zone, "entity_ids": [ids[0]]})
    light_calls.clear()
    assert await manager.tick(manager.active[zone], 2)
    assert [c.data["entity_id"] for c in light_calls] == [ids[0]]


async def test_single_lamp_action_preserves_intersecting_zone_peers(hass, store, zone_runtime):
    _, ids, zone, scene, manager = zone_runtime
    await manager.start(scene, Context())
    task = manager.active[zone]["task"]
    hass.services.async_register("light", "turn_off", lambda call: None)
    await async_control_lights(hass, store, [ids[0]], on=False)
    assert manager.active[zone]["excluded"] == {ids[0]}
    assert not task.done()


async def test_zone_stop_freezes_only_on_members_and_stops_overlapping_room_loop(hass, store, zone_runtime, light_calls):
    areas, ids, zone, _, manager = zone_runtime
    room_scene = await async_save_scene(hass, store, {
        "name": "Synthetic room colors", "area_id": areas[0].id, "kind": "palette",
        "palette_id": "kupfernest", "dynamic": {"enabled": True, "interval": 5, "transition": 2},
    })
    await manager.start(room_scene, Context())
    hass.states.async_set(ids[1], "off", {"supported_color_modes": ["xy"]})
    result = await async_stop_room(hass, store, zone)
    assert result["stopped"] and not manager.active
    assert result["applied"] == [ids[0]]
    assert [c.data["entity_id"] for c in light_calls] == [ids[0]]


async def test_optional_motion_and_brightness_accept_zone_members_not_unrelated_lights(hass, store, zone_runtime):
    _, ids, zone, _, _ = zone_runtime
    hass.states.async_set("sensor.synthetic_zone_lux", "40", {"device_class": "illuminance", "unit_of_measurement": "lx"})
    hass.states.async_set("binary_sensor.synthetic_zone_motion", "off", {"device_class": "motion"})
    raw = {
        "enabled": False, "lux_sensor_entity_id": "sensor.synthetic_zone_lux",
        "target_lux": 100, "hysteresis_lux": 10, "min_interval_seconds": 180,
        "time_window": None, "person_entity_ids": [],
        "stages": [{"entity_ids": ids, "brightness": 100}],
    }
    assert validate_brightness(hass, store, zone, raw) == raw
    motion = {
        "enabled": False, "sensor_entity_ids": ["binary_sensor.synthetic_zone_motion"],
        "timeout_seconds": 180, "dim_before_off": False, "lux_sensor_entity_id": None,
        "lux_below": None, "windows": [{"start": {"type": "time", "value": "00:00"},
        "end": {"type": "time", "value": "23:59"},
        "action": {"type": "lights", "entity_ids": None, "brightness": 100}}],
    }
    assert validate_motion(hass, store, zone, motion) == motion
    await store.async_save_zone({**store.data["zones"][0], "entity_ids": [ids[0]]})
    with pytest.raises(ServiceValidationError):
        validate_brightness(hass, store, zone, raw)
