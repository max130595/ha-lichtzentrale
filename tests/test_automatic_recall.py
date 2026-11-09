# Geändert für Lichtzentrale
"""Synthetic automatic inheritance, partial outcomes and device rounding."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lichtzentrale.automatic_state import (
    current_action,
    local_day,
    recall_actions,
)
from custom_components.lichtzentrale.dynamic_scenes import DynamicSceneManager
from custom_components.lichtzentrale.scenes import async_save_scene
from custom_components.lichtzentrale.storage import LichtzentraleStore
from custom_components.lichtzentrale.target_actions import _night_active, async_execute_action

NOW = datetime(2026, 11, 9, 12, tzinfo=UTC)


@pytest.fixture
async def overlap(hass, store):
    rooms = [ar.async_get(hass).async_create(f"Synthetic recall room {i}") for i in range(2)]
    ids = []
    for i in range(4):
        entry = er.async_get(hass).async_get_or_create("light", "synthetic", f"recall-{i}")
        er.async_get(hass).async_update_entity(entry.entity_id, area_id=rooms[i // 2].id)
        hass.states.async_set(entry.entity_id, "on", {
            "supported_color_modes": ["xy", "color_temp"], "brightness": 100,
            "xy_color": [0.4, 0.3], "color_temp_kelvin": 2500,
        })
        ids.append(entry.entity_id)
    await store.async_set_lights(ids)
    zone = await store.async_save_zone({"name": "Synthetic recall zone", "entity_ids": ids[1:3]})
    return rooms, ids, "zone:" + zone["id"]


async def scene_for(hass, store, area, ids, brightness=80, night=False):
    return await async_save_scene(hass, store, {
        "name": "Synthetic recall scene", "area_id": area, "kind": "snapshot", "night": night,
        "lights": {e: {"on": True, "brightness": brightness} for e in ids},
    })


def set_brightness(hass, entity, brightness):
    hass.states.async_set(entity, "on", {**hass.states.get(entity).attributes, "brightness": brightness})


@pytest.mark.parametrize("inverse", [False, True])
@pytest.mark.parametrize("kind", ["scene", "off", "night"])
async def test_night_auto_inherits_both_directions_only_shared_lamps(hass, store, overlap, inverse, kind):
    rooms, ids, zone = overlap
    source, recipient = (rooms[0].id, zone) if inverse else (zone, rooms[0].id)
    source_ids = ids[:2] if inverse else ids[1:3]
    automatic_scene = await scene_for(hass, store, source, source_ids, night=kind == "night")
    night = await scene_for(hass, store, recipient, [ids[1]], 22, True)
    automatic = {"type": "scene", "scene_id": automatic_scene["id"]} if kind == "scene" else {"type": kind, "area_id": source}
    with patch.object(type(hass.services), "async_call") as calls:
        await async_execute_action(hass, store, automatic, automatic=True)
        saved = deepcopy(store.data["automatic_state"])
        calls.reset_mock()
        first = await async_execute_action(hass, store, {"type": "night_auto", "area_id": recipient})
        assert first["applied"] == [ids[1]]
        assert calls.call_args.args[2]["brightness"] == 22
        # A rounded physical-device report still identifies the first press.
        set_brightness(hass, ids[1], 25)
        assert store.data["rooms"][recipient]["last_scene_id"] == night["id"]
        calls.reset_mock()
        second = await async_execute_action(hass, store, {"type": "night_auto", "area_id": recipient})
    assert second["applied"] == [ids[1]]
    assert calls.call_count == 1
    assert calls.call_args.args[:2] == ("light", "turn_off" if kind == "off" else "turn_on")
    assert calls.call_args.args[2]["entity_id"] == ids[1]
    if kind != "off":
        assert calls.call_args.args[2]["brightness"] == 80
    assert store.data["automatic_state"] == saved
    assert current_action(hass, store, recipient) is None


async def test_each_lamp_uses_newest_matching_source_and_equal_time_sequence(hass, store, overlap):
    rooms, ids, zone = overlap
    first = await store.async_save_zone({"name": "Synthetic older", "entity_ids": ids[:3]})
    older = "zone:" + first["id"]
    old_scene = await scene_for(hass, store, older, ids[:3], 60)
    newer_scene = await scene_for(hass, store, zone, ids[1:3], 160)
    with patch("homeassistant.util.dt.utcnow", return_value=NOW), patch.object(type(hass.services), "async_call") as calls:
        for scene in (old_scene, newer_scene):
            await async_execute_action(hass, store, {"type": "scene", "scene_id": scene["id"]}, automatic=True)
        values = store.data["automatic_state"]
        assert values[older]["updated_at"] == values[zone]["updated_at"]
        assert values[older]["sequence"] < values[zone]["sequence"]
        restored = LichtzentraleStore(hass)
        await restored.async_load()
        calls.reset_mock()
        result = await async_execute_action(hass, restored, {"type": "return_auto", "area_id": rooms[0].id})
    assert set(result["applied"]) == set(ids[:2])
    assert calls.call_count == 2
    assert {c.args[2]["entity_id"]: c.args[2]["brightness"] for c in calls.call_args_list} == {ids[0]: 60, ids[1]: 160}


async def test_newer_snapshot_does_not_claim_other_lamps_in_its_zone(hass, store, overlap):
    rooms, ids, _ = overlap
    zones = [await store.async_save_zone({"name": f"Synthetic subset {i}", "entity_ids": ids[:3]}) for i in range(2)]
    scenes = [await scene_for(hass, store, "zone:" + zones[i]["id"], ids[:2] if i == 0 else [ids[1]], 60 + i * 100) for i in range(2)]
    with patch.object(type(hass.services), "async_call") as calls:
        for scene in scenes:
            await async_execute_action(hass, store, {"type": "scene", "scene_id": scene["id"]}, automatic=True)
        calls.reset_mock()
        await async_execute_action(hass, store, {"type": "return_auto", "area_id": rooms[0].id})
    assert {c.args[2]["entity_id"]: c.args[2]["brightness"] for c in calls.call_args_list} == {ids[0]: 60, ids[1]: 160}


async def test_own_current_day_state_wins_even_against_newer_foreign_state(hass, store, overlap):
    rooms, ids, zone = overlap
    own = await scene_for(hass, store, rooms[0].id, [ids[0]], 70)
    with patch.object(type(hass.services), "async_call") as calls:
        await async_execute_action(hass, store, {"type": "scene", "scene_id": own["id"]}, automatic=True)
        await async_execute_action(hass, store, {"type": "off", "area_id": zone}, automatic=True)
        calls.reset_mock()
        result = await async_execute_action(hass, store, {"type": "return_auto", "area_id": rooms[0].id})
    assert result["applied"] == [ids[0]]
    assert calls.call_count == 1
    assert calls.call_args.args[2] == {"entity_id": ids[0], "brightness": 70, "color_temp_kelvin": 2000}


async def test_old_own_state_does_not_hide_current_foreign_state_and_both_expire(hass, store, overlap):
    rooms, ids, zone = overlap
    with patch("homeassistant.util.dt.utcnow", return_value=NOW - timedelta(days=1)):
        await store.async_set_automatic_state(rooms[0].id, {"type": "off", "area_id": rooms[0].id}, local_day(hass))
    with patch("homeassistant.util.dt.utcnow", return_value=NOW):
        await store.async_set_automatic_state(zone, {"type": "off", "area_id": zone}, local_day(hass))
        assert recall_actions(hass, store, rooms[0].id) == [({"type": "off", "area_id": zone}, [ids[1]])]
    with patch("homeassistant.util.dt.utcnow", return_value=NOW + timedelta(days=1)), patch.object(type(hass.services), "async_call") as calls:
        result = await async_execute_action(hass, store, {"type": "return_auto", "area_id": rooms[0].id})
    assert result["notes"] and not result["applied"]
    calls.assert_not_called()


async def test_legacy_states_are_preserved_with_stable_ties_and_dated_state_wins(hass, store, overlap):
    rooms, ids, zone = overlap
    peer = await store.async_save_zone({"name": "Synthetic legacy peer", "entity_ids": ids[1:3]})
    peer = "zone:" + peer["id"]
    old_scene = await scene_for(hass, store, peer, ids[1:3], 70)
    data = store.data
    legacy = {
        zone: {"day": local_day(hass), "action": {"type": "off", "area_id": zone}},
        peer: {"day": local_day(hass), "action": {"type": "scene", "scene_id": old_scene["id"]}},
    }
    data["automatic_state"] = deepcopy(legacy)
    await store._store.async_save(data)
    await store.async_load()
    assert store.data["automatic_state"] == legacy
    selected = recall_actions(hass, store, rooms[0].id)
    assert selected == [(legacy[max(zone, peer)]["action"], [ids[1]])]
    await store.async_set_automatic_state(peer, legacy[peer]["action"], local_day(hass))
    assert recall_actions(hass, store, rooms[0].id) == [(legacy[peer]["action"], [ids[1]])]


@pytest.mark.parametrize("key,expected,actual,active", [
    ("brightness", 22, 19, True), ("brightness", 22, 25, True),
    ("brightness", 22, 18, False), ("brightness", 22, 26, False),
    ("color_temp_kelvin", 2500, 2450, True), ("color_temp_kelvin", 2500, 2550, True),
    ("color_temp_kelvin", 2500, 2449, False), ("color_temp_kelvin", 2500, 2551, False),
    ("xy", [0.4, 0.3], [0.39, 0.31], True),
    ("xy", [0.4, 0.3], [0.411, 0.3], False),
    ("xy", [0.4, 0.3], [0.4, 0.289], False),
    ("brightness", 22, None, False), ("brightness", 22, float("nan"), False),
    ("xy", [0.4, 0.3], None, False), ("xy", [0.4, 0.3], [0.4], False),
])
async def test_night_device_rounding_tolerances(hass, store, overlap, key, expected, actual, active):
    rooms, ids, _ = overlap
    scene = await async_save_scene(hass, store, {
        "name": "Synthetic rounded night", "area_id": rooms[0].id, "kind": "snapshot", "night": True,
        "lights": {ids[0]: {"on": True, key: expected}},
    })
    await store.async_set_last_scene(rooms[0].id, scene["id"])
    hass.states.async_set(ids[0], "on", {**hass.states.get(ids[0]).attributes, "xy_color" if key == "xy" else key: actual})
    assert _night_active(hass, store, rooms[0].id, scene) is active
    hass.states.async_set(ids[0], "off", dict(hass.states.get(ids[0]).attributes))
    assert not _night_active(hass, store, rooms[0].id, scene)


async def test_partial_scene_records_and_retries_intended_targets(hass, store, overlap, caplog):
    _, ids, _ = overlap
    zone = await store.async_save_zone({"name": "Synthetic partial", "entity_ids": ids[:3]})
    area = "zone:" + zone["id"]
    scene = await scene_for(hass, store, area, ids[:3])
    attributes = dict(hass.states.get(ids[2]).attributes)
    hass.states.async_set(ids[2], "unavailable", attributes)

    async def fail_one(domain, service, data, **kwargs):
        if data["entity_id"] == ids[1]:
            raise RuntimeError("Synthetic partial failure")

    with patch.object(type(hass.services), "async_call", side_effect=fail_one):
        result = await async_execute_action(hass, store, {"type": "scene", "scene_id": scene["id"]}, automatic=True)
    assert result == {"applied": [ids[0]], "skipped": [ids[2]], "failed": [ids[1]]}
    assert current_action(hass, store, area)["scene_id"] == scene["id"]
    assert "1 angewendet, 1 übersprungen, 1 fehlgeschlagen" in caplog.text
    hass.states.async_set(ids[2], "on", attributes)
    with patch.object(type(hass.services), "async_call") as calls:
        result = await async_execute_action(hass, store, {"type": "return_auto", "area_id": area})
    assert result["applied"] == ids[:3] and calls.call_count == 3


async def test_fully_failed_area_is_not_recorded_by_partial_multi_area_action(hass, store, overlap):
    rooms, ids, _ = overlap
    async def fail_room(domain, service, data, **kwargs):
        if data["entity_id"] in ids[2:]:
            raise RuntimeError("Synthetic failed room")
    with patch.object(type(hass.services), "async_call", side_effect=fail_room):
        await async_execute_action(hass, store, {"type": "off", "area_ids": [r.id for r in rooms]}, automatic=True)
    assert current_action(hass, store, rooms[0].id)["type"] == "off"
    assert current_action(hass, store, rooms[1].id) is None


@pytest.mark.parametrize("dynamic", [False, True])
async def test_palette_inheritance_preserves_source_assignment_without_broader_dynamic_loop(hass, store, overlap, dynamic):
    rooms, ids, zone = overlap
    scene = await async_save_scene(hass, store, {
        "name": "Synthetic inherited palette", "area_id": rooms[0].id, "kind": "palette",
        "palette_id": "kupfernest", "dynamic": {"enabled": dynamic, "interval": 5, "transition": 1},
    })
    manager = DynamicSceneManager(hass, store)
    hass.data["lichtzentrale"] = {"store": store, "dynamic": manager}
    try:
        with patch.object(type(hass.services), "async_call") as calls:
            await async_execute_action(hass, store, {"type": "scene", "scene_id": scene["id"]}, automatic=True)
            original = {c.args[2]["entity_id"]: c.args[2] for c in calls.call_args_list}
            calls.reset_mock()
            result = await async_execute_action(hass, store, {"type": "return_auto", "area_id": zone})
        assert result["applied"] == [ids[1]]
        assert calls.call_count == 1 and calls.call_args.args[2] == original[ids[1]]
        if dynamic:
            assert set(manager.active) == {rooms[0].id}
            assert manager.active[rooms[0].id]["excluded"] == {ids[1]}
            assert set(manager.active[rooms[0].id]["targets"]) == {ids[0], ids[1]}
        else:
            assert manager.active == {}
        assert bool(result.get("notes")) is dynamic
    finally:
        await manager.shutdown()


async def test_hue_inheritance_projects_on_off_and_color_without_full_bridge_scene(hass, store):
    rooms = [ar.async_get(hass).async_create(f"Synthetic Hue recall {i}") for i in range(2)]
    config = MockConfigEntry(domain="hue", data={})
    config.add_to_hass(hass)
    registry = er.async_get(hass)
    lamps = [registry.async_get_or_create("light", "hue", f"synthetic-hue-recall-{i}", config_entry=config) for i in range(3)]
    for i, lamp in enumerate(lamps):
        registry.async_update_entity(lamp.entity_id, area_id=rooms[0 if i < 2 else 1].id)
        hass.states.async_set(lamp.entity_id, "on", {"supported_color_modes": ["xy", "color_temp"]})
    hue = registry.async_get_or_create("scene", "hue", "synthetic-hue-recall", config_entry=config)
    hass.states.async_set(hue.entity_id, "unknown", {"is_dynamic": True})
    actions = [SimpleNamespace(
        target=SimpleNamespace(rtype="light", rid=lamp.unique_id),
        action=SimpleNamespace(on=SimpleNamespace(on=i != 1), dimming=SimpleNamespace(brightness=50), color=SimpleNamespace(xy=SimpleNamespace(x=0.4, y=0.3))),
    ) for i, lamp in enumerate(lamps)]
    config.runtime_data = SimpleNamespace(api=SimpleNamespace(scenes={hue.unique_id: SimpleNamespace(actions=actions)}))
    ids = [lamp.entity_id for lamp in lamps]
    await store.async_set_lights(ids)
    zone = await store.async_save_zone({"name": "Synthetic Hue overlap", "entity_ids": ids})
    scene = await async_save_scene(hass, store, {"name": "Synthetic Hue scene", "area_id": "zone:" + zone["id"], "kind": "hue", "hue_scene": hue.entity_id})
    with patch.object(type(hass.services), "async_call") as calls:
        await async_execute_action(hass, store, {"type": "scene", "scene_id": scene["id"]}, automatic=True)
        calls.reset_mock()
        result = await async_execute_action(hass, store, {"type": "return_auto", "area_id": rooms[0].id})
    assert result["applied"] == ids[:2] and result["notes"]
    assert calls.call_count == 2 and all(c.args[0] == "light" for c in calls.call_args_list)
    by_id = {c.args[2]["entity_id"]: c.args for c in calls.call_args_list}
    assert by_id[ids[0]][2] == {"entity_id": ids[0], "brightness": 128, "xy_color": [0.4, 0.3]}
    assert by_id[ids[1]][1:] == ("turn_off", {"entity_id": ids[1]})
    # Unprojectable native actions never fall back to broad Hue activation.
    actions[0].action = SimpleNamespace(on=SimpleNamespace(on=True), gradient=object())
    actions[1].action = None
    with patch.object(type(hass.services), "async_call") as calls:
        result = await async_execute_action(hass, store, {"type": "return_auto", "area_id": rooms[0].id})
    assert result["skipped"] == ids[:2] and not result["applied"] and result["notes"]
    calls.assert_not_called()


async def test_missing_source_zone_does_not_block_valid_overlap(hass, store, overlap):
    rooms, ids, zone = overlap
    valid = await scene_for(hass, store, zone, ids[1:3])
    with patch.object(type(hass.services), "async_call") as calls:
        await async_execute_action(hass, store, {"type": "scene", "scene_id": valid["id"]}, automatic=True)
        await store.async_set_automatic_state("zone:synthetic-deleted", {"type": "off", "area_id": "zone:synthetic-deleted"}, local_day(hass))
        calls.reset_mock()
        result = await async_execute_action(hass, store, {"type": "return_auto", "area_id": rooms[0].id})
    assert result["applied"] == [ids[1]] and calls.call_count == 1


@pytest.mark.parametrize("kind", ["scene", "palette", "off"])
@pytest.mark.parametrize("change", ["missing", "revoked", "unavailable"])
async def test_unrelated_source_lamp_cannot_block_valid_shared_targets(hass, store, overlap, kind, change):
    rooms, ids, zone = overlap
    if kind == "palette":
        scene = await async_save_scene(hass, store, {"name": "Synthetic stale palette", "area_id": zone, "kind": "palette", "palette_id": "kupfernest"})
    else:
        scene = await scene_for(hass, store, zone, ids[1:3])
    action = {"type": "off", "area_id": zone} if kind == "off" else {"type": "scene", "scene_id": scene["id"]}
    with patch.object(type(hass.services), "async_call") as calls:
        await async_execute_action(hass, store, action, automatic=True)
        if change == "missing":
            hass.states.async_remove(ids[2])
        elif change == "revoked":
            await store.async_set_lights([e for e in ids if e != ids[2]])
        else:
            hass.states.async_set(ids[2], "unavailable", dict(hass.states.get(ids[2]).attributes))
        calls.reset_mock()
        result = await async_execute_action(hass, store, {"type": "return_auto", "area_id": rooms[0].id})
    assert result["applied"] == [ids[1]] and calls.call_count == 1
    assert calls.call_args.args[2]["entity_id"] == ids[1]


async def test_changed_recipient_membership_during_subset_recall_prevents_dispatch(hass, store, overlap):
    from homeassistant.exceptions import ServiceValidationError

    rooms, ids, zone = overlap
    scene = await scene_for(hass, store, rooms[0].id, ids[:2])
    with patch.object(type(hass.services), "async_call"):
        await async_execute_action(hass, store, {"type": "scene", "scene_id": scene["id"]}, automatic=True)

    async def change_membership(*args, **kwargs):
        await store.async_save_zone({**store.data["zones"][0], "entity_ids": [ids[2]]})

    with patch.object(type(hass.services), "async_call") as calls, patch(
        "custom_components.lichtzentrale.scenes._async_pause_subset_adaptive", side_effect=change_membership,
    ), pytest.raises(ServiceValidationError):
        await async_execute_action(hass, store, {"type": "return_auto", "area_id": zone})
    calls.assert_not_called()


async def test_new_palette_does_not_override_older_automatic_switch_state(hass, store):
    from tests.test_rooms import fixtures

    area, ids = await fixtures(hass, store)
    zones = [await store.async_save_zone({"name": f"Synthetic switch zone {i}", "entity_ids": ids}) for i in range(2)]
    old, new = ["zone:" + z["id"] for z in zones]
    palette = await async_save_scene(hass, store, {"name": "Synthetic switch palette", "area_id": new, "kind": "palette", "palette_id": "kupfernest"})
    with patch.object(type(hass.services), "async_call") as calls:
        await async_execute_action(hass, store, {"type": "off", "area_id": old}, automatic=True)
        await async_execute_action(hass, store, {"type": "scene", "scene_id": palette["id"]}, automatic=True)
        calls.reset_mock()
        result = await async_execute_action(hass, store, {"type": "return_auto", "area_id": area.id})
    assert set(result["applied"]) == set(ids) and calls.call_count == 3
    switches = [c.args for c in calls.call_args_list if c.args[0] == "switch"]
    assert switches == [("switch", "turn_off", {"entity_id": ids[2]})]


async def test_missing_lamp_during_partial_dispatch_does_not_erase_successful_record(hass, store, overlap):
    rooms, ids, _ = overlap
    scene = await scene_for(hass, store, rooms[0].id, ids[:2])

    async def remove_failed_peer(domain, service, data, **kwargs):
        if data["entity_id"] == ids[0]:
            hass.states.async_remove(ids[1])
        else:
            raise RuntimeError("Synthetic removed peer")

    with patch.object(type(hass.services), "async_call", side_effect=remove_failed_peer):
        result = await async_execute_action(hass, store, {"type": "scene", "scene_id": scene["id"]}, automatic=True)
    assert result["applied"] == [ids[0]]
    assert current_action(hass, store, rooms[0].id)["scene_id"] == scene["id"]
