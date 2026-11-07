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


async def test_scene_transactions_preserve_concurrent_updates(store, hass):
    import asyncio

    scenes = [
        {"id": f"fixture-{index}", "area_id": "fixture-area", "order": index} for index in range(8)
    ]
    await asyncio.gather(
        *(store.async_save_scene(scene) for scene in scenes),
        store.async_set_lights(["light.fixture_concurrent"]),
    )
    assert store.data["scenes"] == scenes
    assert store.data["settings"]["light_entity_ids"] == ["light.fixture_concurrent"]
    await asyncio.gather(
        store.async_set_last_scene("fixture-area", scenes[0]["id"]),
        store.async_reorder_scenes("fixture-area", [s["id"] for s in reversed(scenes)]),
    )
    reloaded = LichtzentraleStore(hass)
    await reloaded.async_load()
    assert reloaded.data == store.data
    assert [s["order"] for s in store.data["scenes"]] == list(reversed(range(8)))
    assert store.data["rooms"]["fixture-area"]["last_scene_id"] == scenes[0]["id"]


@pytest.mark.parametrize(
    "ids", [["fixture-a", "fixture-a"], ["fixture-a"], ["fixture-b", "fixture-c"]]
)
async def test_scene_reorder_rejects_duplicates_missing_and_foreign(store, ids):
    from homeassistant.exceptions import ServiceValidationError

    for name in ("a", "b"):
        await store.async_save_scene(
            {"id": f"fixture-{name}", "area_id": "fixture-area", "order": 0}
        )
    before = store.data
    with pytest.raises(ServiceValidationError):
        await store.async_reorder_scenes("fixture-area", ids)
    assert store.data == before


@pytest.mark.parametrize("operation", ["save", "delete", "reorder", "last"])
async def test_scene_write_failure_preserves_memory_and_disk(store, hass_storage, operation):
    scene = {"id": "fixture-scene", "area_id": "fixture-area", "order": 0}
    await store.async_save_scene(scene)
    before = store.data
    disk_before = deepcopy(hass_storage[STORAGE_KEY])
    with patch.object(
        store._store, "async_save", AsyncMock(side_effect=HomeAssistantError("disk"))
    ):
        with pytest.raises(HomeAssistantError):
            if operation == "save":
                await store.async_save_scene({**scene, "name": "Changed"})
            elif operation == "delete":
                await store.async_delete_scene(scene["id"])
            elif operation == "reorder":
                await store.async_reorder_scenes(scene["area_id"], [scene["id"]])
            else:
                await store.async_set_last_scene(scene["area_id"], scene["id"])
    assert store.data == before
    assert hass_storage[STORAGE_KEY] == disk_before


async def test_delete_cleans_references_and_late_recall_cannot_resurrect(store, hass_storage):
    scene = {"id": "fixture-scene", "area_id": "fixture-area", "order": 0}
    await store.async_save_scene(scene)
    await store.async_set_last_scene(scene["area_id"], scene["id"])
    # Simulate future-stage fields already stored by another integration version.
    store._data["rooms"][scene["area_id"]].update(
        cycle=[scene["id"], "other-fixture"], default_on=scene["id"], future_option=True
    )
    await store.async_delete_scene(scene["id"])
    await store.async_set_last_scene(scene["area_id"], scene["id"])
    room = store.data["rooms"][scene["area_id"]]
    assert room == {"cycle": ["other-fixture"], "default_on": "last", "future_option": True}
    assert hass_storage[STORAGE_KEY]["data"] == store.data
