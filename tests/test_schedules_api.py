# Geändert für Lichtzentrale
"""Authenticated schedule CRUD, atomic persistence and lifecycle boundaries."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.lichtzentrale.const import DOMAIN
from custom_components.lichtzentrale.storage import LichtzentraleStore
from custom_components.lichtzentrale.websocket_api import async_setup_websocket_api


@pytest.fixture
async def schedule_setup(hass, store):
    hass.states.async_set("light.synthetic_schedule", "off", {"supported_color_modes": ["brightness"]})
    await store.async_set_lights(["light.synthetic_schedule"])
    return {
        "name": "Synthetischer Abend", "enabled": False,
        "trigger": {"type": "time", "value": "20:30"},
        "condition": {"weekdays": list(range(7)), "person_entity_ids": [], "light_state": "any"},
        "action": {"type": "lights", "entity_ids": ["light.synthetic_schedule"], "on": True,
                   "brightness": 140}, "transition": 1800,
    }


@pytest.fixture
async def schedule_client(hass, store, hass_ws_client):
    hass.data[DOMAIN] = {"store": store}
    client = await hass_ws_client(hass)
    async_setup_websocket_api(hass)
    return client


async def request(client, command, **data):
    await client.send_json_auto_id({"type": f"lichtzentrale/{command}", **data})
    return await client.receive_json()


async def test_schedule_roundtrip_reload_toggle_delete(hass, store, schedule_setup, schedule_client):
    assert (await request(schedule_client, "schedules/list"))["result"]["schedules"] == []
    result = await request(schedule_client, "schedule/save", schedule=schedule_setup)
    assert result["success"]
    assert result["result"]["time_zone"] == hass.config.time_zone
    saved = result["result"]["schedules"][0]
    assert saved["name"] == schedule_setup["name"] and saved["next_run"] is None
    restored = LichtzentraleStore(hass)
    await restored.async_load()
    assert restored.data == store.data
    result = await request(schedule_client, "schedule/set_enabled", schedule_id=saved["id"], enabled=True)
    assert result["result"]["schedules"][0]["enabled"]
    assert (await request(schedule_client, "schedule/delete", schedule_id=saved["id"]))["result"]["schedules"] == []
    assert not (await request(schedule_client, "schedule/delete", schedule_id=saved["id"]))["success"]


@pytest.mark.parametrize("command,data", [
    ("schedules/list", {}), ("schedule/save", {"schedule": {}}),
    ("schedule/delete", {"schedule_id": "missing"}),
    ("schedule/set_enabled", {"schedule_id": "missing", "enabled": True}),
    ("schedule/test", {"schedule_id": "missing"}),
])
async def test_schedule_requires_admin(hass, store, hass_ws_client, hass_read_only_access_token, command, data):
    hass.data[DOMAIN] = {"store": store}
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    async_setup_websocket_api(hass)
    response = await request(client, command, **data)
    assert response["error"]["code"] == "unauthorized"
    assert not store.data["schedules"]


async def test_schedule_failed_writes_do_not_cancel_or_mutate(hass, store, schedule_setup):
    manager = Mock()
    hass.data[DOMAIN] = {"store": store, "schedules": manager}
    saved = await store.async_save_schedule(schedule_setup)
    manager.refresh_config.assert_called_once_with(saved["id"])
    manager.reset_mock()
    original = store.data
    with patch.object(store._store, "async_save", AsyncMock(side_effect=HomeAssistantError("Synthetic disk"))):
        with pytest.raises(HomeAssistantError):
            await store.async_save_schedule({**saved, "name": "Nicht gespeichert"})
        with pytest.raises(HomeAssistantError):
            await store.async_set_schedule_enabled(saved["id"], True)
        with pytest.raises(HomeAssistantError):
            await store.async_delete_schedule(saved["id"])
    assert store.data == original
    manager.refresh_config.assert_not_called()


async def test_disable_stale_schedule_and_reject_stale_updates(hass, store, schedule_setup):
    saved = await store.async_save_schedule({**schedule_setup, "enabled": True})
    await store.async_set_lights([])
    assert not (await store.async_set_schedule_enabled(saved["id"], False))["enabled"]
    with pytest.raises(ServiceValidationError):
        await store.async_set_schedule_enabled(saved["id"], True)
    await store.async_delete_schedule(saved["id"])
    await store.async_set_lights(["light.synthetic_schedule"])
    with pytest.raises(ServiceValidationError):
        await store.async_save_schedule(saved)
    assert not store.data["schedules"]


async def test_validation_inside_store_lock(hass, store, schedule_setup):
    await store._lock.acquire()
    pending = asyncio.create_task(store.async_save_schedule(schedule_setup))
    await asyncio.sleep(0)
    store._data["settings"]["light_entity_ids"] = []
    store._lock.release()
    with pytest.raises(ServiceValidationError):
        await pending
    assert not store.data["schedules"]


async def test_test_command_forwards_context_and_reports_unloaded(hass, store, schedule_client):
    result = await request(schedule_client, "schedule/test", schedule_id="synthetic")
    assert not result["success"]
    manager = Mock()
    manager.async_test = AsyncMock(return_value={"condition_met": False, "applied": [], "skipped": []})
    hass.data[DOMAIN]["schedules"] = manager
    result = await request(schedule_client, "schedule/test", schedule_id="synthetic")
    assert result["success"] and not result["result"]["condition_met"]
    assert manager.async_test.call_args.args[0] == "synthetic"
    assert manager.async_test.call_args.args[1].user_id


async def test_legacy_store_without_schedules_needs_no_migration(hass, store):
    original = deepcopy(store.data)
    original.pop("schedules")
    await store._store.async_save(original)
    restored = LichtzentraleStore(hass)
    await restored.async_load()
    assert restored.data["schedules"] == []


@pytest.mark.parametrize("window", [
    None,
    {"after": {"type": "sun", "event": "sunset", "offset_min": -30},
     "before": {"type": "time", "value": "01:00"}},
    {"after": None, "before": {"type": "time", "value": "09:00"}},
])
async def test_schedule_time_window_api_roundtrip(hass, store, schedule_setup, schedule_client, window):
    schedule_setup["condition"]["time_window"] = window
    response = await request(schedule_client, "schedule/save", schedule=schedule_setup)
    assert response["success"]
    saved = response["result"]["schedules"][0]
    assert saved["condition"]["time_window"] == window
    restored = LichtzentraleStore(hass)
    await restored.async_load()
    assert restored.data == store.data
    response = await request(schedule_client, "schedule/set_enabled", schedule_id=saved["id"], enabled=True)
    assert response["success"]
    assert response["result"]["schedules"][0]["condition"]["time_window"] == window


async def test_invalid_saved_window_cannot_enable_but_can_disable(hass, store, schedule_setup):
    saved = await store.async_save_schedule(schedule_setup)
    store._data["schedules"][0]["condition"]["time_window"] = {
        "after": {"type": "time", "value": "25:00"}, "before": None}
    before = store.data
    with pytest.raises(ServiceValidationError):
        await store.async_set_schedule_enabled(saved["id"], True)
    assert store.data == before
    assert not (await store.async_set_schedule_enabled(saved["id"], False))["enabled"]


async def test_daily_claim_is_atomic_persistent_and_cleared_on_delete(hass, store, schedule_setup):
    saved = await store.async_save_schedule({**schedule_setup, "enabled": True})
    claims = await asyncio.gather(*(
        store.async_claim_schedule_day(saved["id"], "2026-11-07") for _ in range(3)))
    assert claims.count(True) == 1
    restored = LichtzentraleStore(hass)
    await restored.async_load()
    assert not await restored.async_claim_schedule_day(saved["id"], "2026-11-07")
    assert await restored.async_claim_schedule_day(saved["id"], "2026-11-08")
    await restored.async_delete_schedule(saved["id"])
    assert saved["id"] not in restored.data["settings"]["schedule_last_run_dates"]
    assert not await restored.async_claim_schedule_day(saved["id"], "2026-11-09")


async def test_daily_claim_failure_and_disabled_plan_do_not_mutate(hass, store, schedule_setup):
    saved = await store.async_save_schedule(schedule_setup)
    assert not await store.async_claim_schedule_day(saved["id"], "2026-11-07")
    await store.async_set_schedule_enabled(saved["id"], True)
    before = store.data
    with patch.object(store._store, "async_save", AsyncMock(side_effect=HomeAssistantError("disk"))):
        with pytest.raises(HomeAssistantError):
            await store.async_claim_schedule_day(saved["id"], "2026-11-07")
    assert store.data == before
    restored = LichtzentraleStore(hass)
    await restored.async_load()
    assert restored.data == before
    assert await store.async_claim_schedule_day(saved["id"], "2026-11-07")
