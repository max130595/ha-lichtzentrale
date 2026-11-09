# Geändert für Lichtzentrale
"""Synthetic overlapping targets and local-day automation persistence."""
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.lichtzentrale.automatic_state import current_action, local_day
from custom_components.lichtzentrale.rooms import async_toggle_room, list_rooms, room_targets
from custom_components.lichtzentrale.scenes import async_apply_scene, async_save_scene
from custom_components.lichtzentrale.storage import LichtzentraleStore
from custom_components.lichtzentrale.target_actions import async_execute_action, validate_action
from tests.test_rooms import fixtures


async def test_zones_overlap_preserve_grants_and_stale_references(hass, store):
    area, ids = await fixtures(hass, store)
    first = await store.async_save_zone({"name": "Synthetic first", "entity_ids": ids[:2]})
    second = await store.async_save_zone({"name": "Synthetic second", "entity_ids": ids[1:]})
    target = "zone:" + first["id"]
    assert room_targets(hass, store, target) == ids[:2]
    assert room_targets(hass, store, area.id) == ids
    assert len(list_rooms(hass, store)) == 3
    scene = await async_save_scene(hass, store, {"name": "Synthetic zone scene", "area_id": target, "kind": "snapshot", "lights": {ids[0]: {"on": True}}})
    await store.async_delete_zone(first["id"])
    assert store.data["scenes"][0]["id"] == scene["id"]
    assert store.data["settings"]["light_entity_ids"] == ids
    assert room_targets(hass, store, "zone:" + second["id"]) == ids[1:]
    with pytest.raises(ServiceValidationError):
        await async_apply_scene(hass, store, scene["id"])


async def test_night_unique_and_scene_unknown_fields_survive(hass, store):
    area, ids = await fixtures(hass, store)
    raw = {"name": "Synthetic night", "area_id": area.id, "kind": "snapshot", "night": True, "lights": {ids[0]: {"on": True, "brightness": 22}}}
    first = await async_save_scene(hass, store, raw)
    await store.async_save_scene({**first, "future_field": {"keep": True}})
    await async_save_scene(hass, store, {**raw, "id": first["id"], "name": "Synthetic edited"})
    second = await async_save_scene(hass, store, raw)
    saved = {s["id"]: s for s in store.data["scenes"]}
    assert saved[first["id"]]["future_field"] == {"keep": True}
    assert saved[first["id"]]["night"] is False
    assert saved[second["id"]]["night"] is True


async def test_common_full_brightness_dedup_and_switch_capabilities(hass, store):
    area, ids = await fixtures(hass, store)
    zone = await store.async_save_zone({"name": "Synthetic overlap", "entity_ids": ids})
    with patch.object(type(hass.services), "async_call") as calls:
        result = await async_execute_action(hass, store, {"type": "full_brightness", "area_ids": [area.id, "zone:" + zone["id"]], "entity_ids": ids})
    assert sorted(result["applied"]) == sorted(ids)
    assert calls.call_count == 3
    for call in calls.call_args_list:
        if call.args[0] == "switch":
            assert call.args[2] == {"entity_id": ids[2]}
        else:
            assert call.args[2]["brightness"] == 255


async def test_automatic_persists_manual_does_not_replace_and_expires_local_day(hass, store):
    area, ids = await fixtures(hass, store)
    hass.config.time_zone = "Europe/Berlin"
    scene = await async_save_scene(hass, store, {"name": "Synthetic auto", "area_id": area.id, "kind": "snapshot", "lights": {ids[0]: {"on": True, "brightness": 50}}})
    with patch("homeassistant.util.dt.utcnow", return_value=datetime(2026, 10, 24, 20, tzinfo=UTC)), patch.object(type(hass.services), "async_call"):
        await async_execute_action(hass, store, {"type": "scene", "scene_id": scene["id"]}, automatic=True)
        await async_execute_action(hass, store, {"type": "off", "area_id": area.id})
        assert current_action(hass, store, area.id)["type"] == "scene"
        restored = LichtzentraleStore(hass)
        await restored.async_load()
        assert current_action(hass, restored, area.id)["scene_id"] == scene["id"]
        await async_execute_action(hass, restored, {"type": "off", "area_id": area.id}, automatic=True)
        assert current_action(hass, restored, area.id)["type"] == "off"
    with patch("homeassistant.util.dt.utcnow", return_value=datetime(2026, 10, 24, 22, tzinfo=UTC)):
        assert local_day(hass) == "2026-10-25"
        assert current_action(hass, restored, area.id) is None
        await restored.async_expire_automatic_state(local_day(hass))
        assert restored.data["automatic_state"] == {}


async def test_failed_scene_never_records_success_and_missing_auto_is_noop(hass, store):
    area, ids = await fixtures(hass, store)
    scene = await async_save_scene(hass, store, {"name": "Synthetic failed", "area_id": area.id, "kind": "snapshot", "lights": {ids[0]: {"on": True}}})
    with patch.object(type(hass.services), "async_call", side_effect=RuntimeError("Synthetic failure")):
        result = await async_execute_action(hass, store, {"type": "scene", "scene_id": scene["id"]}, automatic=True)
    assert result["failed"] == [ids[0]]
    assert current_action(hass, store, area.id) is None
    with patch.object(type(hass.services), "async_call") as calls:
        result = await async_execute_action(hass, store, {"type": "return_auto", "area_id": area.id})
    assert result["notes"] and not result["applied"]
    calls.assert_not_called()
    with pytest.raises(ServiceValidationError):
        validate_action(hass, store, {"type": "scene", "scene_id": scene["id"], "entity_ids": [ids[1]]})


async def test_zone_room_off_and_snapshot_recall(hass, store):
    area, ids = await fixtures(hass, store)
    zone = await store.async_save_zone({"name": "Synthetic zone", "entity_ids": ids})
    target = "zone:" + zone["id"]
    scene = await async_save_scene(hass, store, {"name": "Synthetic scene", "area_id": target, "kind": "snapshot", "lights": {ids[0]: {"on": True}}})
    with patch.object(type(hass.services), "async_call"):
        assert (await async_apply_scene(hass, store, scene["id"]))["applied"] == [ids[0]]
        assert len((await async_toggle_room(hass, store, target, on=False))["applied"]) == 3


async def test_brightness_turns_on_dimmable_lamps_and_night_toggle_records(hass, store):
    area, ids = await fixtures(hass, store)
    state = hass.states.get(ids[0])
    hass.states.async_set(ids[0], "off", dict(state.attributes))
    with patch.object(type(hass.services), "async_call") as calls:
        await async_execute_action(hass, store, {"type": "brightness", "area_id": area.id, "brightness": 80})
    assert len(calls.call_args_list) == 2
    assert all(call.args[1] == "turn_on" and call.args[2]["brightness"] == 80 for call in calls.call_args_list)
    night = await async_save_scene(hass, store, {"name": "Synthetic night", "area_id": area.id, "kind": "snapshot", "night": True, "lights": {ids[0]: {"on": True, "brightness": 22}}})
    with patch.object(type(hass.services), "async_call"):
        await async_execute_action(hass, store, {"type": "night_auto", "area_id": area.id}, automatic=True)
    assert current_action(hass, store, area.id) == {"type": "night", "area_id": area.id}
    assert store.data["rooms"][area.id]["last_scene_id"] == night["id"]


async def test_zone_recall_serializes_with_physical_room(hass, store):
    import asyncio

    area, ids = await fixtures(hass, store)
    zone = await store.async_save_zone({"name": "Synthetic serial zone", "entity_ids": ids[:1]})
    scene = await async_save_scene(hass, store, {"name": "Synthetic serial scene", "area_id": "zone:" + zone["id"], "kind": "snapshot", "lights": {ids[0]: {"on": True}}})
    from custom_components.lichtzentrale.rooms import locked_room

    with patch.object(type(hass.services), "async_call") as calls:
        async with locked_room(hass, store, area.id):
            task = asyncio.create_task(async_apply_scene(hass, store, scene["id"]))
            await asyncio.sleep(0)
            assert not task.done()
            calls.assert_not_called()
        assert (await task)["applied"] == ids[:1]


async def test_missing_or_revoked_zone_member_cannot_broaden_grants(hass, store):
    area, ids = await fixtures(hass, store)
    zone = await store.async_save_zone({"name": "Synthetic grants", "entity_ids": ids})
    await store.async_set_lights(ids[:1])
    assert room_targets(hass, store, "zone:" + zone["id"]) == ids[:1]
    with pytest.raises(ServiceValidationError):
        await store.async_save_zone({**zone, "name": "Synthetic stale update"})
    assert store.data["settings"]["light_entity_ids"] == ids[:1]


@pytest.mark.parametrize("instant,expected", [
    (datetime(2026, 3, 28, 23, tzinfo=UTC), "2026-03-29"),
    (datetime(2026, 3, 29, 22, tzinfo=UTC), "2026-03-30"),
    (datetime(2026, 10, 25, 0, 30, tzinfo=UTC), "2026-10-25"),
    (datetime(2026, 10, 25, 1, 30, tzinfo=UTC), "2026-10-25"),
    (datetime(2026, 10, 25, 23, tzinfo=UTC), "2026-10-26"),
])
async def test_automatic_local_day_across_summer_and_winter_time(hass, store, instant, expected):
    hass.config.time_zone = "Europe/Berlin"
    await store.async_set_automatic_state("synthetic", {"type": "off", "area_id": "synthetic"}, "2026-10-25")
    restored = LichtzentraleStore(hass)
    await restored.async_load()
    with patch("homeassistant.util.dt.utcnow", return_value=instant):
        assert local_day(hass) == expected
        assert bool(current_action(hass, restored, "synthetic")) == (expected == "2026-10-25")
        await restored.async_expire_automatic_state(local_day(hass))
        assert bool(restored.data["automatic_state"]) == (expected == "2026-10-25")


async def test_legacy_store_additions_are_idempotent_and_preserve_every_collection(hass, hass_storage):
    from copy import deepcopy

    from custom_components.lichtzentrale.const import STORAGE_KEY

    original = {
        "scenes": [{"id": "synthetic_old_scene", "area_id": "synthetic_room", "kind": "snapshot", "lights": {"light.synthetic_legacy": {"on": True}}, "extension": [1]}],
        "palettes": [{"id": "synthetic_palette", "colors": [[0.2, 0.3]], "extension": [2]}],
        "bindings": [{"id": "synthetic_button", "entity_id": "event.synthetic_button", "event_type": "short_release", "action": "room_off", "params": {"area_id": "synthetic_room"}, "extension": [3]}],
        "schedules": [{"id": "synthetic_schedule", "enabled": False, "action": {"type": "room_off", "area_id": "synthetic_room"}, "condition": {"time_window": None, "extension": [4]}, "extension": [5]}],
        "rooms": {"synthetic_room": {"motion": {"enabled": True, "windows": [], "extension": [6]}, "brightness": {"enabled": False, "stages": [], "extension": [7]}, "brightness_learned": [None, 12], "default_on": "synthetic_old_scene", "cycle": ["synthetic_old_scene"]}},
        "settings": {"light_entity_ids": ["light.synthetic_legacy"], "extension": [8]},
        "extension": {"unchanged": [9]},
    }
    hass_storage[STORAGE_KEY] = {"version": 1, "data": deepcopy(original)}
    expected = {**deepcopy(original), "zones": [], "automatic_state": {}, "active_dynamic": {}}
    expected["settings"]["dim_min_pct"] = 1
    first = LichtzentraleStore(hass)
    await first.async_load()
    assert first.data == expected
    await first.async_load()
    assert first.data == expected
    await first.async_set_lights(original["settings"]["light_entity_ids"])
    assert hass_storage[STORAGE_KEY]["data"] == expected
    reloaded = LichtzentraleStore(hass)
    await reloaded.async_load()
    assert reloaded.data == expected
