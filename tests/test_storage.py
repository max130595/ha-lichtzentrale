"""Server-side Store persistence and failure safety."""

from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.lichtzentrale.const import STORAGE_KEY
from custom_components.lichtzentrale.storage import LichtzentraleStore, empty_data


async def test_create_reload_and_independent_snapshots(hass, hass_storage, store):
    assert hass_storage[STORAGE_KEY]["version"] == 1
    assert hass_storage[STORAGE_KEY]["data"] == empty_data()
    await store.async_set_lights(["light.fixture_a", "light.fixture_a", "light.fixture_b"])
    reloaded = LichtzentraleStore(hass)
    await reloaded.async_load()
    assert reloaded.data["settings"]["light_entity_ids"] == ["light.fixture_a", "light.fixture_b"]
    snapshot = reloaded.data
    snapshot["settings"]["light_entity_ids"].clear()
    assert reloaded.data == store.data
    assert empty_data()["scenes"] is not empty_data()["scenes"]


async def test_preserve_future_fields_and_fill_defaults(hass, hass_storage):
    saved = {
        "scenes": [{"id": "synthetic-scene", "future": True}],
        "settings": {"future_option": "kept"},
        "future_stage": {"value": 42},
    }
    hass_storage[STORAGE_KEY] = {"version": 1, "data": deepcopy(saved)}
    store = LichtzentraleStore(hass)
    await store.async_load()
    await store.async_set_lights(["light.fixture_a"])
    persisted = hass_storage[STORAGE_KEY]["data"]
    assert persisted["scenes"] == saved["scenes"]
    assert persisted["future_stage"] == saved["future_stage"]
    assert persisted["settings"]["future_option"] == "kept"
    assert persisted["rooms"] == {}
    assert persisted["bindings"] == []
    assert persisted["schedules"] == []


async def test_save_failure_does_not_mutate_memory_or_disk(store, hass_storage):
    before = store.data
    disk_before = deepcopy(hass_storage[STORAGE_KEY])
    with patch.object(
        store._store, "async_save", AsyncMock(side_effect=HomeAssistantError("disk"))
    ):
        with pytest.raises(HomeAssistantError):
            await store.async_set_lights(["light.fixture_a"])
    assert store.data == before
    assert hass_storage[STORAGE_KEY] == disk_before


async def test_remove_deletes_persisted_data(store, hass_storage):
    await store.async_remove()
    assert STORAGE_KEY not in hass_storage
