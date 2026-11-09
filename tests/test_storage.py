# Geändert für Lichtzentrale
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


async def position_fixtures(hass, store):
    from homeassistant.helpers import area_registry as ar
    from homeassistant.helpers import entity_registry as er

    area = ar.async_get(hass).async_create("Fixture layout")
    ids = []
    for index in range(2):
        entry = er.async_get(hass).async_get_or_create("light", "synthetic", f"layout-{index}")
        er.async_get(hass).async_update_entity(entry.entity_id, area_id=area.id)
        hass.states.async_set(entry.entity_id, "off", {"supported_color_modes": ["xy"]})
        ids.append(entry.entity_id)
    await store.async_set_lights(ids)
    return area.id, ids


async def test_positions_concurrent_writes_roundtrip_and_remove(hass, store):
    import asyncio

    area, ids = await position_fixtures(hass, store)
    value = {"cell": [0, 2], "height": "boden"}
    await asyncio.gather(
        *(store.async_set_position(area, entity, value) for entity in ids),
        store.async_update_room(area, {"default_on": "last"}),
    )
    value["cell"][0] = 2
    assert store.data["rooms"][area]["positions"][ids[0]]["cell"] == [0, 2]
    assert set(store.data["rooms"][area]["positions"]) == set(ids)
    await store.async_set_position(area, ids[0], None)
    reloaded = LichtzentraleStore(hass)
    await reloaded.async_load()
    assert reloaded.data == store.data
    assert reloaded.data["rooms"][area] == {
        "positions": {ids[1]: {"cell": [0, 2], "height": "boden"}}, "default_on": "last"
    }


async def test_position_storage_failure_keeps_previous_position(hass, store, hass_storage):
    area, ids = await position_fixtures(hass, store)
    await store.async_set_position(area, ids[0], {"cell": [0, 0], "height": "decke"})
    before = store.data
    with patch.object(store._store, "async_save", AsyncMock(side_effect=HomeAssistantError("disk"))):
        with pytest.raises(HomeAssistantError):
            await store.async_set_position(area, ids[0], None)
    assert store.data == before == hass_storage[STORAGE_KEY]["data"]


async def test_missing_peer_does_not_block_position_edit(hass, store):
    area, ids = await position_fixtures(hass, store)
    hass.states.async_remove(ids[1])
    value = {"cell": [1, 1], "height": "moebel"}
    assert await store.async_set_position(area, ids[0], value) == value


@pytest.mark.parametrize("change", ["grant", "area"])
async def test_position_checks_membership_after_waiting_for_lock(hass, store, change):
    import asyncio

    from homeassistant.exceptions import ServiceValidationError
    from homeassistant.helpers import entity_registry as er

    area, ids = await position_fixtures(hass, store)
    await store._lock.acquire()
    task = asyncio.create_task(store.async_set_position(area, ids[0], {"cell": [0, 0], "height": "boden"}))
    await asyncio.sleep(0)
    if change == "grant":
        store._data["settings"]["light_entity_ids"] = ids[1:]
    else:
        er.async_get(hass).async_update_entity(ids[0], area_id=None)
    store._lock.release()
    with pytest.raises(ServiceValidationError):
        await task
    assert area not in store.data["rooms"]


async def test_schedule_window_migration_preserves_nested_data_and_runs_once(hass, hass_storage):
    saved = empty_data()
    saved.update({
        "schedules": [
            {"id": "synthetic-legacy", "condition": {
                "weekdays": [1, 4], "person_entity_ids": [], "light_state": "on",
                "future_condition": {"nested": [1, 2]}},
             "action": {"type": "lights", "entity_ids": ["light.synthetic_migration"]},
             "future_schedule": {"nested": [3]}},
            {"id": "synthetic-current", "condition": {"time_window": {
                "after": {"type": "time", "value": "18:00"}, "before": None}}},
        ],
        "rooms": {"synthetic-room": {"positions": {"light.synthetic_migration": {
            "cell": [0, 2], "height": "boden"}}, "motion": {"windows": []}}},
        "scenes": [{"id": "synthetic-scene", "lights": {"light.synthetic_migration": {"on": True}}}],
        "bindings": [{"id": "synthetic-binding", "params": {"entity_ids": ["light.synthetic_migration"]}}],
        "settings": {"light_entity_ids": ["light.synthetic_migration"], "future": {"nested": [4]}},
        "future": {"nested": [5]},
    })
    original = deepcopy(saved)
    hass_storage[STORAGE_KEY] = {"version": 1, "data": deepcopy(saved)}
    expected = deepcopy(saved)
    expected["settings"].setdefault("dim_min_pct", 1)
    expected["schedules"][0]["condition"]["time_window"] = None
    store = LichtzentraleStore(hass)
    with patch.object(store._store, "async_save", wraps=store._store.async_save) as save:
        await store.async_load()
        save.assert_awaited_once_with(expected)
    assert store.data == expected == hass_storage[STORAGE_KEY]["data"]
    assert saved == original
    reloaded = LichtzentraleStore(hass)
    with patch.object(reloaded._store, "async_save", wraps=reloaded._store.async_save) as save:
        await reloaded.async_load()
        save.assert_not_awaited()
    assert reloaded.data == expected


async def test_schedule_window_failed_migration_is_atomic_and_retryable(hass, hass_storage):
    saved = empty_data()
    saved["schedules"] = [{"id": "synthetic-legacy", "condition": {"weekdays": [0]}}]
    hass_storage[STORAGE_KEY] = {"version": 1, "data": deepcopy(saved)}
    store = LichtzentraleStore(hass)
    before = store.data
    with patch.object(store._store, "async_save", AsyncMock(side_effect=HomeAssistantError("disk"))):
        with pytest.raises(HomeAssistantError):
            await store.async_load()
    assert store.data == before
    assert hass_storage[STORAGE_KEY]["data"] == saved
    await store.async_load()
    expected = deepcopy(saved)
    expected["settings"].setdefault("dim_min_pct", 1)
    expected["schedules"][0]["condition"]["time_window"] = None
    assert store.data == expected == hass_storage[STORAGE_KEY]["data"]
