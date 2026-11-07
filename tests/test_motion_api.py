# Geändert für Lichtzentrale
"""Motion configuration is atomic, admin-only and installation independent."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from custom_components.lichtzentrale.const import DOMAIN
from custom_components.lichtzentrale.motion_config import (
    list_lux_sensors,
    list_motion_sensors,
    validate_boundary,
    validate_motion,
)
from custom_components.lichtzentrale.storage import LichtzentraleStore
from custom_components.lichtzentrale.websocket_api import async_setup_websocket_api


@pytest.fixture
async def motion_setup(hass, store):
    area = ar.async_get(hass).async_create("Synthetic motion room")
    registry = er.async_get(hass)
    lamp = registry.async_get_or_create("light", "synthetic", "motion-api-lamp")
    registry.async_update_entity(lamp.entity_id, area_id=area.id)
    hass.states.async_set(lamp.entity_id, "off", {"supported_color_modes": ["brightness"]})
    sensor = "binary_sensor.synthetic_motion_api"
    hass.states.async_set(sensor, "off", {"device_class": "motion"})
    await store.async_set_lights([lamp.entity_id])
    config = {
        "enabled": False, "sensor_entity_ids": [sensor], "timeout_seconds": 60,
        "dim_before_off": True, "lux_sensor_entity_id": None, "lux_below": None,
        "windows": [{"start": {"type": "time", "value": "00:00"},
                     "end": {"type": "time", "value": "00:00"},
                     "action": {"type": "lights", "entity_ids": None, "brightness": 77}}],
    }
    return area.id, lamp.entity_id, config


@pytest.fixture
async def motion_client(hass, hass_ws_client, store):
    hass.data[DOMAIN] = {"store": store}
    client = await hass_ws_client(hass)
    async_setup_websocket_api(hass)
    return client


async def request(client, command, **data):
    await client.send_json_auto_id({"type": f"lichtzentrale/{command}", **data})
    return await client.receive_json()


async def test_motion_roundtrip_reload_and_enable(hass, store, motion_setup, motion_client):
    area, _, config = motion_setup
    assert (await request(motion_client, "motion/get", area_id=area))["result"]["config"] is None
    manager = Mock()
    manager.status.return_value = {"enabled": False, "paused": False, "active": False}
    hass.data[DOMAIN]["motion"] = manager
    result = await request(motion_client, "motion/save", area_id=area, config=config)
    assert result["success"]
    assert result["result"]["config"] == config
    manager.refresh_config.assert_called_once_with(area)
    result = await request(motion_client, "motion/set_enabled", area_id=area, enabled=True)
    assert result["result"]["config"]["enabled"] is True
    restored = LichtzentraleStore(hass)
    await restored.async_load()
    assert restored.data == store.data
    assert (await request(motion_client, "motion/get", area_id=area))["result"]["sensors"]


@pytest.mark.parametrize("command,data", [
    ("motion/get", {}), ("motion/save", {"config": {}}),
    ("motion/set_enabled", {"enabled": False}),
])
async def test_motion_requires_admin(hass, store, hass_ws_client, hass_read_only_access_token, command, data):
    hass.data[DOMAIN] = {"store": store}
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    async_setup_websocket_api(hass)
    response = await request(client, command, area_id="synthetic", **data)
    assert response["error"]["code"] == "unauthorized"
    assert store.data["rooms"] == {}


async def test_motion_failed_store_write_keeps_state_and_pending_tasks(hass, store, motion_setup):
    area, _, config = motion_setup
    manager = Mock()
    hass.data[DOMAIN] = {"store": store, "motion": manager}
    await store.async_set_motion(area, config)
    manager.reset_mock()
    before = store.data
    with patch.object(store._store, "async_save", AsyncMock(side_effect=HomeAssistantError("synthetic disk"))):
        with pytest.raises(HomeAssistantError):
            await store.async_set_motion_enabled(area, True)
        with pytest.raises(HomeAssistantError):
            await store.async_set_motion(area, {**config, "timeout_seconds": 90})
    assert store.data == before
    manager.refresh_config.assert_not_called()


async def test_motion_disable_is_possible_after_sensor_disappears(hass, store, motion_setup):
    area, _, config = motion_setup
    await store.async_set_motion(area, {**config, "enabled": True})
    hass.states.async_remove(config["sensor_entity_ids"][0])
    assert not (await store.async_set_motion_enabled(area, False))["enabled"]
    with pytest.raises(ServiceValidationError):
        await store.async_set_motion_enabled(area, True)
    assert not store.data["rooms"][area]["motion"]["enabled"]


async def test_motion_write_rechecks_after_lock(hass, store, motion_setup):
    area, _, config = motion_setup
    await store._lock.acquire()
    task = asyncio.create_task(store.async_set_motion(area, config))
    await asyncio.sleep(0)
    store._data["settings"]["light_entity_ids"] = []
    store._lock.release()
    with pytest.raises(ServiceValidationError):
        await task
    assert "motion" not in store.data["rooms"].get(area, {})


@pytest.mark.parametrize("field,value", [
    ("enabled", 1), ("dim_before_off", "yes"), ("timeout_seconds", True),
    ("timeout_seconds", 0), ("timeout_seconds", 86401), ("timeout_seconds", 20),
    ("sensor_entity_ids", []), ("sensor_entity_ids", ["sensor.synthetic"]),
    ("sensor_entity_ids", [None]), ("windows", []), ("windows", [None]),
    ("windows", [{"start": {}}]), ("lux_below", 10), ("lux_sensor_entity_id", "sensor.missing"),
])
async def test_invalid_motion_configuration_does_not_persist(hass, store, motion_setup, field, value):
    area, _, config = motion_setup
    with pytest.raises(ServiceValidationError):
        await store.async_set_motion(area, {**config, field: value})
    assert "motion" not in store.data["rooms"].get(area, {})


@pytest.mark.parametrize("boundary", [
    None, {}, {"type": "time", "value": "24:00"}, {"type": "time", "value": "1:05"},
    {"type": "time", "value": "12:60"}, {"type": "time", "value": "12:00", "extra": 1},
    {"type": "sun", "event": "sunrise", "offset_min": True},
    {"type": "sun", "event": "sunset", "offset_min": 1441},
    {"type": "sun", "event": [], "offset_min": 0},
])
def test_boundary_rejects_malformed_values(boundary):
    with pytest.raises(ServiceValidationError):
        validate_boundary(boundary)


@pytest.mark.parametrize("offset", [-1440, -15, 0, 60, 1440])
def test_solar_boundary(offset):
    raw = {"type": "sun", "event": "sunset", "offset_min": offset}
    assert validate_boundary(raw) == raw


async def test_sensor_discovery_accepts_three_classes_but_not_unsafe_lux(hass):
    for device_class in ("motion", "occupancy", "presence", "door", "smoke"):
        hass.states.async_set(f"binary_sensor.synthetic_{device_class}", "off", {"device_class": device_class})
    for suffix, attributes in {
        "lux": {"device_class": "illuminance", "unit_of_measurement": "lx"},
        "wrong_unit": {"device_class": "illuminance", "unit_of_measurement": "%"},
        "wrong_type": {"unit_of_measurement": "lx"},
    }.items():
        hass.states.async_set(f"sensor.synthetic_{suffix}", "12", attributes)
    assert len(list_motion_sensors(hass)) == 3
    assert [item["entity_id"] for item in list_lux_sensors(hass)] == ["sensor.synthetic_lux"]


@pytest.mark.parametrize("threshold", [True, -1, float("nan"), float("inf"), "30", None])
async def test_invalid_lux_threshold(hass, store, motion_setup, threshold):
    area, _, config = motion_setup
    hass.states.async_set("sensor.synthetic_lux", "12", {"device_class": "illuminance", "unit_of_measurement": "lx"})
    with pytest.raises(ServiceValidationError):
        validate_motion(hass, store, area, {**config, "lux_sensor_entity_id": "sensor.synthetic_lux", "lux_below": threshold})


async def test_unlimited_sensor_selection_and_cross_room_targets(hass, store, motion_setup):
    area, lamp, config = motion_setup
    sensors = [f"binary_sensor.synthetic_multiple_{n}" for n in range(501)]
    for entity_id in sensors:
        hass.states.async_set(entity_id, "off", {"device_class": "presence"})
    hass.states.async_set("light.synthetic_unassigned", "off", {"supported_color_modes": ["onoff"]})
    await store.async_set_lights([lamp, "light.synthetic_unassigned"])
    config["sensor_entity_ids"] = sensors + sensors[:1]
    config["windows"][0]["action"]["entity_ids"] = [lamp, "light.synthetic_unassigned"]
    validated = validate_motion(hass, store, area, config)
    assert len(validated["sensor_entity_ids"]) == 501
    assert validated["windows"][0]["action"]["entity_ids"] == [lamp, "light.synthetic_unassigned"]


@pytest.mark.parametrize("action", [
    {"type": "lights", "entity_ids": [], "brightness": 80},
    {"type": "lights", "entity_ids": ["lock.synthetic"], "brightness": 80},
    {"type": "lights", "entity_ids": None, "brightness": True},
    {"type": "lights", "entity_ids": None, "brightness": 256},
    {"type": "lights", "entity_ids": None, "brightness": 80, "extra": True},
    {"type": "scene", "scene_id": "missing"}, {"type": "adaptive"}, {"type": []},
])
async def test_action_validation(hass, store, motion_setup, action):
    area, _, config = motion_setup
    config = deepcopy(config)
    config["windows"][0]["action"] = action
    with pytest.raises(ServiceValidationError):
        validate_motion(hass, store, area, config)
