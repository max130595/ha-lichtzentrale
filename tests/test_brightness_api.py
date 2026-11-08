# Geändert für Lichtzentrale
"""Admin-only brightness API and atomic persistent learning."""
import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
import test_brightness_config as config_tests
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.lichtzentrale.const import DOMAIN
from custom_components.lichtzentrale.storage import LichtzentraleStore
from custom_components.lichtzentrale.websocket_api import async_setup_websocket_api

brightness_setup = config_tests.brightness_setup


async def request(client, command, **data):
    await client.send_json_auto_id({"type": f"lichtzentrale/brightness/{command}", **data})
    return await client.receive_json()


async def test_api_roundtrip(hass, store, brightness_setup, hass_ws_client):
    area, _, config = brightness_setup
    hass.data[DOMAIN] = {"store": store}
    client = await hass_ws_client(hass)
    async_setup_websocket_api(hass)
    assert (await request(client, "get", area_id=area))["result"]["config"] is None
    manager = Mock()
    manager.config_lock.return_value = asyncio.Lock()
    manager.async_prepare_config = AsyncMock(return_value=False)
    manager.status.return_value = {"enabled": False, "paused": False, "current_lux": 40,
                                   "active_stage": 0, "learned_lux": [], "last_error": None}
    hass.data[DOMAIN]["brightness"] = manager
    response = await request(client, "save", area_id=area, config=config)
    assert response["success"]
    assert response["result"]["config"] == config
    assert response["result"]["lux_sensors"] and response["result"]["persons"]
    manager.refresh_config.assert_called_once_with(
        area, preserve_active=False, previous={}, learned=[])
    response = await request(client, "set_enabled", area_id=area, enabled=True)
    assert response["result"]["config"]["enabled"] is True
    restored = LichtzentraleStore(hass)
    await restored.async_load()
    assert restored.data == store.data


@pytest.mark.parametrize("command,data", [("get", {}), ("save", {"config": {}}),
                                         ("set_enabled", {"enabled": False})])
async def test_admin_required(hass, store, hass_ws_client, hass_read_only_access_token, command, data):
    hass.data[DOMAIN] = {"store": store}
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    async_setup_websocket_api(hass)
    response = await request(client, command, area_id="synthetic", **data)
    assert response["error"]["code"] == "unauthorized"
    assert store.data["rooms"] == {}


async def test_learning_persistence_reset_and_stale_guard(hass, store, brightness_setup):
    area, _, config = brightness_setup
    manager = Mock()
    manager.config_lock.return_value = asyncio.Lock()
    manager.async_prepare_config = AsyncMock(return_value=False)
    hass.data[DOMAIN] = {"store": store, "brightness": manager}
    await store.async_set_brightness(area, config)
    manager.reset_mock()
    assert await store.async_learn_brightness(area, config, 0, 40)
    assert await store.async_learn_brightness(area, config, 0, 80)
    assert store.data["rooms"][area]["brightness_learned"] == [50, None]
    manager.refresh_config.assert_not_called()
    changed = {**config, "target_lux": 200}
    await store.async_set_brightness(area, changed)
    assert not await store.async_learn_brightness(area, config, 0, 100)
    assert store.data["rooms"][area]["brightness_learned"] == [50, None]
    await store.async_set_brightness_enabled(area, True)
    assert store.data["rooms"][area]["brightness_learned"] == [50, None]
    restored = LichtzentraleStore(hass)
    await restored.async_load()
    assert restored.data == store.data
    changed["stages"] = changed["stages"][::-1]
    await store.async_set_brightness(area, changed)
    assert store.data["rooms"][area]["brightness_learned"] == [None, None]
    await store.async_learn_brightness(area, changed, 0, 20)
    hass.states.async_set("sensor.synthetic_alternative", "0",
                         {"device_class": "illuminance", "unit_of_measurement": "lx"})
    await store.async_set_brightness(area, {**changed, "lux_sensor_entity_id": "sensor.synthetic_alternative"})
    assert store.data["rooms"][area]["brightness_learned"] == [None, None]


async def test_failed_writes_and_stale_disable(hass, store, brightness_setup):
    area, _, config = brightness_setup
    manager = Mock()
    manager.config_lock.return_value = asyncio.Lock()
    manager.async_prepare_config = AsyncMock(return_value=False)
    hass.data[DOMAIN] = {"store": store, "brightness": manager}
    await store.async_set_brightness(area, config)
    manager.reset_mock()
    before = store.data
    with patch.object(store._store, "async_save", AsyncMock(side_effect=HomeAssistantError("disk"))):
        for action in (store.async_set_brightness(area, {**config, "target_lux": 200}),
                       store.async_set_brightness_enabled(area, True),
                       store.async_learn_brightness(area, config, 0, 40)):
            with pytest.raises(HomeAssistantError):
                await action
            assert store.data == before
    manager.refresh_config.assert_not_called()
    hass.states.async_remove(config["lux_sensor_entity_id"])
    with pytest.raises(ServiceValidationError):
        await store.async_set_brightness_enabled(area, True)
    await store.async_set_brightness_enabled(area, False)
    assert not store.data["rooms"][area]["brightness"]["enabled"]


async def test_concurrent_learning_and_room_edits(store, brightness_setup):
    area, _, config = brightness_setup
    await store.async_set_brightness(area, config)
    await asyncio.gather(store.async_learn_brightness(area, config, 0, 40),
                         store.async_learn_brightness(area, config, 1, 80),
                         store.async_update_room(area, {"default_on": "last"}))
    room = store.data["rooms"][area]
    assert room["brightness_learned"] == [40, 80]
    assert room["default_on"] == "last"


@pytest.mark.parametrize("index,rise", [(True, 5), (-1, 5), (0, -1), (0, float("nan")),
                                       (0, float("inf")), (0, True)])
async def test_invalid_samples(store, brightness_setup, index, rise):
    area, _, config = brightness_setup
    await store.async_set_brightness(area, config)
    with pytest.raises(ServiceValidationError):
        await store.async_learn_brightness(area, config, index, rise)


async def test_validation_after_waiting_for_lock(store, brightness_setup):
    area, _, config = brightness_setup
    async with store._lock:
        pending = asyncio.create_task(store.async_set_brightness(area, config))
        await asyncio.sleep(0)
        # Simulate the previous transaction committing a revoked allowlist.
        store._data["settings"]["light_entity_ids"] = []
    with pytest.raises(ServiceValidationError):
        await pending
    assert area not in store.data["rooms"]


async def test_learning_checks_config_under_lock(store, brightness_setup):
    area, _, config = brightness_setup
    await store.async_set_brightness(area, config)
    async with store._lock:
        pending = asyncio.create_task(store.async_learn_brightness(area, config, 0, 40))
        await asyncio.sleep(0)
        store._data["rooms"][area]["brightness"]["target_lux"] = 200
    assert not await pending
    assert store.data["rooms"][area]["brightness_learned"] == [None, None]


async def test_learning_guard_after_waiting_for_lock(store, brightness_setup):
    area, _, config = brightness_setup
    await store.async_set_brightness(area, config)
    valid = True
    async with store._lock:
        pending = asyncio.create_task(store.async_learn_brightness(
            area, config, 0, 40, guard=lambda: valid))
        await asyncio.sleep(0)
        valid = False
    assert not await pending
    assert store.data["rooms"][area]["brightness_learned"] == [None, None]
