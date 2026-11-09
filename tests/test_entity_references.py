# Geändert für Lichtzentrale
"""Synthetic exact-reference, collision, confirmation, and registry rename tests."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from custom_components.lichtzentrale.const import DOMAIN
from custom_components.lichtzentrale.entity_references import (
    EntityReferenceManager,
    build_reference_replacement,
    referenced_lights,
)
from custom_components.lichtzentrale.storage import empty_data

OLD, NEW, OTHER = "light.fixture_old", "light.fixture_new", "light.fixture_other"


def populated():
    data = empty_data()
    scene = {"id": "fixture_scene", "name": "Testszene", "area_id": "fixture_area",
             "lights": {OLD: {"on": True, "brightness": 60}},
             "lamp_settings": {OLD: {"behavior": "fixed", "brightness": 50}},
             "dynamic": {"wave_order": [OLD, OTHER]}}
    data.update({
        "settings": {"light_entity_ids": [OLD, NEW],
                     "last_light_states": {OLD: {"brightness": 60}},
                     "unrelated_text": OLD},
        "zones": [{"id": "fixture_zone", "name": "Testzone", "entity_ids": [OLD, OTHER]}],
        "scenes": [scene],
        "rooms": {"fixture_area": {
            "positions": {OLD: {"cell": [1, 1], "height": "moebel"}},
            "pre_off_lights": {OLD: {"on": True}}, "pre_off_pending": [OLD],
            "motion": {"sensor_entity_ids": ["binary_sensor.fixture_motion"],
                       "windows": [{"action": {"type": "lights", "entity_ids": [OLD]}}]},
            "brightness": {"stages": [{"entity_ids": [OLD], "brightness": 40}]},
        }},
        "bindings": [{"id": "fixture_binding", "event_entity": "event.fixture_button",
                      "params": {"entity_ids": [OLD]}, "control_label": OLD,
                      "event_attributes": {"entity_id": OLD, "entity_ids": [OLD]}}],
        "schedules": [{"id": "fixture_schedule", "name": "Testzeitplan",
                       "actions": [{"type": "lights", "entity_ids": [OLD]}],
                       "action": {"type": "lights", "entity_ids": [OLD]}}],
        "automatic_state": {"fixture_area": {"action": {"entity_ids": [OLD], "entity_id": OLD}}},
        "active_dynamic": {"fixture_area": {"scene": deepcopy(scene),
                                              "targets": [OLD, OTHER], "excluded": [OLD]}},
        "future": {"entity_ids": [OLD], "name": OLD},
    })
    return data


def test_all_declared_lamp_references_move_without_mutating_names_or_input():
    data = populated()
    original = deepcopy(data)
    updated, result = build_reference_replacement(data, OLD, NEW)
    assert data == original
    assert result["can_replace"] is True
    assert {entry["kind"] for entry in result["entries"]} == {
        "settings", "zones", "scenes", "rooms", "bindings", "schedules",
        "automatic_state", "active_dynamic",
    }
    assert OLD not in referenced_lights(updated)
    assert updated["settings"]["light_entity_ids"] == [NEW]
    assert updated["rooms"]["fixture_area"]["pre_off_pending"] == [NEW]
    assert updated["scenes"][0]["lamp_settings"][NEW] == {"behavior": "fixed", "brightness": 50}
    assert updated["active_dynamic"]["fixture_area"]["excluded"] == [NEW]
    assert updated["bindings"][0]["event_attributes"] == original["bindings"][0]["event_attributes"]
    assert updated["bindings"][0]["control_label"] == OLD
    assert updated["settings"]["unrelated_text"] == OLD
    assert updated["future"] == original["future"]
    assert result["warnings"]  # Old and already-approved new merge visibly.


def test_exact_references_only_and_unrelated_duplicates_preserved():
    data = empty_data()
    data["zones"] = [{"entity_ids": [f"{OLD}_suffix", OTHER, OLD, OTHER, NEW]}]
    updated, report = build_reference_replacement(data, OLD, NEW)
    assert updated["zones"][0]["entity_ids"] == [f"{OLD}_suffix", OTHER, NEW, OTHER]
    assert report["entries"][0]["count"] == 1


@pytest.mark.parametrize("kind,key", [("scenes", "lights"), ("scenes", "lamp_settings"),
                                     ("scenes", "light_settings")])
def test_different_scene_values_block_whole_transaction(kind, key):
    data = populated()
    data[kind][0][key] = {OLD: {"brightness": 40}, NEW: {"brightness": 80}}
    updated, report = build_reference_replacement(data, OLD, NEW)
    assert updated == data
    assert not report["can_replace"]
    assert "Testszene" in report["conflicts"][0]


@pytest.mark.parametrize("key", ["positions", "pre_off_lights"])
def test_different_room_values_block_whole_transaction(key):
    data = populated()
    data["rooms"]["fixture_area"][key] = {OLD: {"value": 1}, NEW: {"value": 2}}
    updated, report = build_reference_replacement(data, OLD, NEW)
    assert updated == data
    assert report["conflicts"]


def test_identical_map_entries_merge_but_different_stage_membership_blocks():
    data = populated()
    data["scenes"][0]["lights"][NEW] = deepcopy(data["scenes"][0]["lights"][OLD])
    updated, report = build_reference_replacement(data, OLD, NEW)
    assert report["can_replace"]
    assert list(updated["scenes"][0]["lights"]) == [NEW]
    data["rooms"]["fixture_area"]["brightness"]["stages"].append(
        {"entity_ids": [NEW], "brightness": 40})
    updated, report = build_reference_replacement(data, OLD, NEW)
    assert updated == data
    assert "verschiedenen Helligkeitsstufen" in report["conflicts"][0]


@pytest.mark.parametrize("old,new", [(OLD, OLD), ("sensor.fixture_a", NEW),
                                    (OLD, "lock.fixture_a"), (None, NEW), (OLD, [])])
def test_only_distinct_lighting_domains_are_accepted(old, new):
    with pytest.raises(ServiceValidationError):
        build_reference_replacement(populated(), old, new)


@pytest.fixture
async def manager(hass, store):
    for entity_id, label in ((OLD, "Alte Testlampe"), (NEW, "Neue Testlampe")):
        hass.states.async_set(entity_id, "on", {"friendly_name": label,
                                               "supported_color_modes": ["xy"]})
    store._data = populated()
    return EntityReferenceManager(hass, store)


async def test_preview_is_read_only_and_commit_calls_runtime_refresh(hass, store, manager):
    save = AsyncMock()
    store._store.async_save = save
    runtimes = {"bindings": Mock(), "schedules": Mock(), "brightness": Mock(), "motion": Mock(),
                "live_preview": SimpleNamespace(async_invalidate=AsyncMock()),
                "dynamic": SimpleNamespace(entity_references_changed=AsyncMock())}
    hass.data[DOMAIN] = runtimes
    before = store.data
    result = manager.preview(OLD, NEW)
    assert result["source_name"] == "Alte Testlampe"
    assert result["target_name"] == "Neue Testlampe"
    assert store.data == before
    save.assert_not_awaited()
    result = await manager.async_replace(OLD, NEW, result["preview_token"])
    assert result["replaced"]
    save.assert_awaited_once()
    assert OLD not in referenced_lights(store.data)
    runtimes["bindings"].refresh_bindings.assert_called_once()
    runtimes["schedules"].refresh_config.assert_called_once()
    runtimes["motion"].refresh_config.assert_called_once_with("fixture_area")
    runtimes["brightness"].refresh_config.assert_called_once_with("fixture_area")
    runtimes["dynamic"].entity_references_changed.assert_awaited_once_with(OLD, NEW)
    runtimes["live_preview"].async_invalidate.assert_awaited_once_with([OLD, NEW])


async def test_missing_old_light_still_offered_and_no_new_grants(hass, store, manager):
    hass.states.async_remove(OLD)
    assert any(source["entity_id"] == OLD for source in manager.options()["sources"])
    assert all(OLD not in item["name"] for item in manager.options()["sources"])
    store._data["settings"]["light_entity_ids"].remove(NEW)
    assert not any(target["entity_id"] == NEW for target in manager.options()["targets"])
    with pytest.raises(ServiceValidationError, match="Freigaben"):
        manager.preview(OLD, NEW)


@pytest.mark.parametrize("change", ["data", "capability", "grant", "identity"])
async def test_stale_preview_rejected_before_save(hass, store, manager, change):
    preview = manager.preview(OLD, NEW)
    if change == "data":
        store._data["scenes"][0]["name"] = "Anderer Name"
    elif change == "capability":
        hass.states.async_set(NEW, "on", {"supported_color_modes": ["onoff"]})
    elif change == "grant":
        store._data["settings"]["light_entity_ids"].remove(NEW)
    else:
        hass.states.async_remove(NEW)
        er.async_get(hass).async_get_or_create("light", "synthetic", "fixture-new-identity",
                                              suggested_object_id="fixture_new")
        hass.states.async_set(NEW, "on", {"supported_color_modes": ["xy"]})
    before = store.data
    store._store.async_save = AsyncMock()
    with pytest.raises(ServiceValidationError):
        await manager.async_replace(OLD, NEW, preview["preview_token"])
    assert store.data == before
    store._store.async_save.assert_not_awaited()


async def test_disk_failure_does_not_publish_any_migration(hass, store, manager):
    token = manager.preview(OLD, NEW)["preview_token"]
    store._store.async_save = AsyncMock(side_effect=OSError("synthetic disk failure"))
    before = store.data
    with pytest.raises(OSError):
        await manager.async_replace(OLD, NEW, token)
    assert store.data == before


async def test_validation_repeated_after_waiting_for_store_lock(hass, store, manager):
    import asyncio

    token = manager.preview(OLD, NEW)["preview_token"]
    await store._lock.acquire()
    task = hass.async_create_task(manager.async_replace(OLD, NEW, token))
    await asyncio.sleep(0)
    store._data["scenes"][0]["name"] = "Parallel bearbeitet"
    store._lock.release()
    with pytest.raises(ServiceValidationError, match="nicht mehr aktuell"):
        await task
    assert OLD in referenced_lights(store.data)


async def test_switch_replacement_preserves_config_with_visible_capability_warning(hass, store, manager):
    registry = er.async_get(hass)
    switch = registry.async_get_or_create("switch", "shelly", "synthetic-switch",
                                          suggested_object_id="fixture_lamp", original_name="Testlicht")
    hass.states.async_set(switch.entity_id, "on", {"friendly_name": "Testlicht"})
    store._data["settings"]["light_entity_ids"].append(switch.entity_id)
    preview = manager.preview(OLD, switch.entity_id)
    assert any("An/Aus" in warning for warning in preview["warnings"])
    await manager.async_replace(OLD, switch.entity_id, preview["preview_token"])
    assert store.data["scenes"][0]["lights"][switch.entity_id]["brightness"] == 60
    assert store.data["scenes"][0]["lamp_settings"][switch.entity_id]["brightness"] == 50


async def test_real_registry_rename_moves_all_references_without_requiring_new_grant(hass, store):
    registry = er.async_get(hass)
    entity = registry.async_get_or_create("light", "synthetic", "fixture-stable-identity",
                                          suggested_object_id="fixture_old")
    store._data = populated()
    store._data["settings"]["light_entity_ids"] = [OLD]
    manager = EntityReferenceManager(hass, store)
    manager.start()
    await hass.async_block_till_done()
    registry.async_update_entity(entity.entity_id, new_entity_id=NEW)
    await hass.async_block_till_done()
    assert OLD not in referenced_lights(store.data)
    assert store.data["settings"]["light_entity_ids"] == [NEW]
    await manager.shutdown()


async def test_forged_unrelated_registry_event_cannot_transfer_grants(hass, store):
    registry = er.async_get(hass)
    registry.async_get_or_create("light", "synthetic", "fixture-a", suggested_object_id="fixture_old")
    registry.async_get_or_create("light", "synthetic", "fixture-b", suggested_object_id="fixture_new")
    store._data = populated()
    store._data["settings"]["light_entity_ids"] = [OLD]
    before = store.data
    manager = EntityReferenceManager(hass, store)
    manager.start()
    await manager._registry_updated(SimpleNamespace(data={"action": "update", "entity_id": NEW,
                                                          "old_entity_id": OLD}))
    assert store.data == before
    await manager.shutdown()


async def test_registry_collision_preserves_whole_store_and_logs_repair(hass, store, caplog):
    registry = er.async_get(hass)
    entity = registry.async_get_or_create("light", "synthetic", "fixture-stable-identity",
                                          suggested_object_id="fixture_old")
    store._data = populated()
    store._data["scenes"][0]["lights"][NEW] = {"brightness": 2}
    before = store.data
    manager = EntityReferenceManager(hass, store)
    manager.start()
    await hass.async_block_till_done()
    registry.async_update_entity(entity.entity_id, new_entity_id=NEW)
    await hass.async_block_till_done()
    assert store.data == before
    assert "Lampe ersetzen" in caplog.text
    await manager.shutdown()


async def test_rapid_registry_renames_follow_same_identity_to_latest_id(hass, store):
    registry = er.async_get(hass)
    entity = registry.async_get_or_create("light", "synthetic", "fixture-rapid-identity",
                                          suggested_object_id="fixture_old")
    store._data = populated()
    store._data["settings"]["light_entity_ids"] = [OLD]
    manager = EntityReferenceManager(hass, store)
    manager.start()
    await hass.async_block_till_done()
    registry.async_update_entity(entity.entity_id, new_entity_id="light.fixture_intermediate")
    registry.async_update_entity("light.fixture_intermediate", new_entity_id=NEW)
    await hass.async_block_till_done()
    assert OLD not in referenced_lights(store.data)
    assert store.data["settings"]["light_entity_ids"] == [NEW]
    await manager.shutdown()


async def test_unrelated_runtime_ownership_is_not_invalidated(hass, store, manager):
    store._data["rooms"]["unrelated_fixture_area"] = {"positions": {OTHER: {"cell": [0, 0]}}}
    motion, brightness = Mock(), Mock()
    hass.data[DOMAIN] = {"motion": motion, "brightness": brightness}
    preview = manager.preview(OLD, NEW)
    await manager.async_replace(OLD, NEW, preview["preview_token"])
    motion.refresh_config.assert_called_once_with("fixture_area")
    brightness.refresh_config.assert_called_once_with("fixture_area")


async def test_non_lighting_registry_rename_does_not_rewrite_event_content(hass, store):
    registry = er.async_get(hass)
    entity = registry.async_get_or_create("event", "synthetic", "fixture-event",
                                          suggested_object_id="fixture_button")
    store._data = populated()
    before = store.data
    manager = EntityReferenceManager(hass, store)
    manager.start()
    await hass.async_block_till_done()
    registry.async_update_entity(entity.entity_id, new_entity_id="event.fixture_renamed")
    await hass.async_block_till_done()
    assert store.data == before
    await manager.shutdown()


async def test_migration_rotates_dynamic_token_to_fence_queued_old_persistence(hass, store, manager):
    store._data["active_dynamic"]["fixture_area"]["token"] = "synthetic-old-token"
    stale = deepcopy(store._data["active_dynamic"]["fixture_area"])
    token = manager.preview(OLD, NEW)["preview_token"]
    await manager.async_replace(OLD, NEW, token)
    current = store.data["active_dynamic"]["fixture_area"]
    assert current["token"] != stale["token"]
    assert not await store.async_set_dynamic_run("fixture_area", stale, expected_token=stale["token"])
    assert OLD not in referenced_lights(store.data)


async def test_runtime_refresh_failure_reports_committed_migration_not_failed_save(hass, store, manager):
    hass.data[DOMAIN] = {"dynamic": SimpleNamespace(
        entity_references_changed=AsyncMock(side_effect=RuntimeError("synthetic refresh failure")))}
    token = manager.preview(OLD, NEW)["preview_token"]
    result = await manager.async_replace(OLD, NEW, token)
    assert result["replaced"]
    assert "Dynamik" in result["runtime_warnings"][0]
    assert OLD not in referenced_lights(store.data)


def register_target_area(hass, area_id):
    """Register the existing synthetic target without reserving another entity ID."""
    hass.states.async_remove(NEW)
    registry = er.async_get(hass)
    entry = registry.async_get_or_create("light", "synthetic", "fixture-new-room-target",
                                         suggested_object_id="fixture_new")
    registry.async_update_entity(entry.entity_id, area_id=area_id)
    hass.states.async_set(NEW, "on", {"supported_color_modes": ["xy"]})


@pytest.mark.parametrize("target_room", [None, "other"])
@pytest.mark.parametrize("reference", ["position", "brightness", "scene", "automatic", "dynamic"])
async def test_physical_room_mismatch_blocks_preview_and_atomic_commit(
    hass, store, manager, target_room, reference
):
    area = ar.async_get(hass).async_create("Fixture Area")
    other = ar.async_get(hass).async_create("Other Fixture Area")
    register_target_area(hass, other.id if target_room else None)
    data = empty_data()
    data["settings"]["light_entity_ids"] = [OLD, NEW]
    if reference == "position":
        data["rooms"][area.id] = {"positions": {OLD: {"cell": [1, 1], "height": "moebel"}}}
    elif reference == "brightness":
        data["rooms"][area.id] = {"brightness": {"stages": [{"entity_ids": [OLD], "brightness": 40}]}}
    elif reference == "scene":
        data["scenes"] = [{"area_id": area.id, "name": "Testszene", "lights": {OLD: {"on": True}}}]
    elif reference == "automatic":
        data["automatic_state"][area.id] = {"action": {"entity_ids": [OLD]}}
    else:
        data["active_dynamic"][area.id] = {"targets": [OLD]}
    store._data = data
    before = store.data
    store._store.async_save = AsyncMock()
    preview = manager.preview(OLD, NEW)
    assert not preview["can_replace"]
    assert any("Fixture Area" in conflict and "demselben Raum zuordnen" in conflict
               for conflict in preview["conflicts"])
    with pytest.raises(ServiceValidationError):
        await manager.async_replace(OLD, NEW, preview["preview_token"])
    assert store.data == before
    store._store.async_save.assert_not_awaited()


async def test_same_physical_room_is_valid_but_reassignment_invalidates_preview(hass, store, manager):
    area = ar.async_get(hass).async_create("Fixture Area")
    register_target_area(hass, area.id)
    preview = manager.preview(OLD, NEW)
    assert preview["can_replace"]
    er.async_get(hass).async_update_entity(NEW, area_id=None)
    with pytest.raises(ServiceValidationError, match="nicht mehr aktuell"):
        await manager.async_replace(OLD, NEW, preview["preview_token"])
    assert OLD in referenced_lights(store.data)
    er.async_get(hass).async_update_entity(NEW, area_id=area.id)
    preview = manager.preview(OLD, NEW)
    await manager.async_replace(OLD, NEW, preview["preview_token"])
    assert OLD not in referenced_lights(store.data)


async def test_zones_and_explicit_cross_room_motion_targets_remain_transferable(hass, store, manager):
    area = ar.async_get(hass).async_create("Fixture Area")
    other = ar.async_get(hass).async_create("Other Fixture Area")
    register_target_area(hass, other.id)
    store._data = empty_data()
    store._data["settings"]["light_entity_ids"] = [OLD, NEW]
    store._data["zones"] = [{"id": "fixture_zone", "name": "Testzone", "entity_ids": [OLD]}]
    store._data["rooms"] = {
        "zone:fixture_zone": {"positions": {OLD: {"cell": [1, 1], "height": "moebel"}}},
        area.id: {"motion": {"windows": [{"action": {"entity_ids": [OLD]}}]}},
    }
    store._data["scenes"] = [{"area_id": "zone:fixture_zone", "lights": {OLD: {"on": True}}}]
    store._data["active_dynamic"]["zone:fixture_zone"] = {"targets": [OLD]}
    preview = manager.preview(OLD, NEW)
    assert preview["can_replace"]
    assert preview["conflicts"] == []
    await manager.async_replace(OLD, NEW, preview["preview_token"])
    assert OLD not in referenced_lights(store.data)
