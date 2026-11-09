# Geändert für Lichtzentrale
"""Calendar boundaries, seasonal CRUD, and every existing scene entry path."""

import asyncio
from copy import deepcopy
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from custom_components.lichtzentrale.bindings import (
    BindingManager,
    _check_scene,
    validate_on_behavior,
)
from custom_components.lichtzentrale.palette_catalogue import list_palettes
from custom_components.lichtzentrale.scenes import (
    async_apply_scene,
    async_apply_scene_subset,
    async_delete_scene,
    async_save_scene,
    list_scenes,
    validate_scene,
)
from custom_components.lichtzentrale.seasonal_scenes import (
    DEFAULT_BOUNDARIES,
    normalize_seasonal,
    resolve_scene,
)
from custom_components.lichtzentrale.storage import LichtzentraleStore
from custom_components.lichtzentrale.target_actions import action_targets, async_execute_action


@pytest.fixture
async def seasonal(hass, store):
    areas = [ar.async_get(hass).async_create(f"Synthetic seasonal area {i}") for i in range(2)]
    ids = []
    for index in range(3):
        entry = er.async_get(hass).async_get_or_create("light", "synthetic", f"seasonal-{index}")
        er.async_get(hass).async_update_entity(entry.entity_id, area_id=areas[0 if index < 2 else 1].id)
        hass.states.async_set(entry.entity_id, "on", {"supported_color_modes": ["xy"], "color_mode": "xy", "brightness": 100, "xy_color": [.4, .3]})
        ids.append(entry.entity_id)
    await store.async_set_lights(ids)
    children = {}
    for index, key in enumerate(("spring", "summer", "autumn", "winter", "christmas")):
        children[key] = await async_save_scene(hass, store, {"name": f"Synthetic {key}", "area_id": areas[0].id, "kind": "snapshot", "lights": {ids[0]: {"on": True, "brightness": 60 + index * 20}, ids[1]: {"on": False}}})
    raw = {"name": "Synthetic seasons", "area_id": areas[0].id, "kind": "seasonal", "favorite": True,
           "seasonal": {"scenes": {key: children[key]["id"] for key in ("spring", "summer", "autumn", "winter")},
                        "christmas": {"enabled": True, "scene_id": children["christmas"]["id"]}}}
    wrapper = await async_save_scene(hass, store, raw)
    return SimpleNamespace(areas=areas, ids=ids, children=children, wrapper=wrapper, raw=raw)


@pytest.mark.parametrize("day,expected", [("2026-02-28", "winter"), ("2026-03-01", "spring"), ("2026-05-31", "spring"), ("2026-06-01", "summer"), ("2026-09-01", "autumn"), ("2026-11-30", "autumn"), ("2026-12-01", "christmas"), ("2026-12-26", "christmas"), ("2026-12-27", "winter"), ("2027-01-01", "winter")])
async def test_meteorological_and_christmas_boundaries(hass, store, seasonal, day, expected):
    concrete, info = resolve_scene(hass, store, seasonal.wrapper, now=date.fromisoformat(day))
    assert concrete["id"] == seasonal.children[expected]["id"]
    assert info["resolved_season"] == expected and info["resolution_note"] is None


async def test_local_date_not_utc_and_wrapped_christmas(hass, store, seasonal):
    hass.config.time_zone = "Europe/Berlin"
    concrete, _ = resolve_scene(hass, store, seasonal.wrapper, now=datetime(2026, 2, 28, 23, 30, tzinfo=UTC))
    assert concrete["id"] == seasonal.children["spring"]["id"]
    raw = deepcopy(seasonal.wrapper)
    raw["seasonal"]["christmas"].update(start="12-20", end="01-05")
    saved = await async_save_scene(hass, store, raw)
    assert resolve_scene(hass, store, saved, now=date(2027, 1, 5))[1]["resolved_season"] == "christmas"
    assert resolve_scene(hass, store, saved, now=date(2027, 1, 6))[1]["resolved_season"] == "winter"


async def test_configurable_boundaries_and_leap_day(hass, store, seasonal):
    raw = deepcopy(seasonal.wrapper)
    raw["seasonal"]["boundaries"]["spring"] = "04-15"
    saved = await async_save_scene(hass, store, raw)
    assert resolve_scene(hass, store, saved, now=date(2026, 4, 14))[1]["resolved_season"] == "winter"
    assert resolve_scene(hass, store, saved, now=date(2026, 4, 15))[1]["resolved_season"] == "spring"
    raw["seasonal"]["boundaries"]["spring"] = "02-29"
    saved = await async_save_scene(hass, store, raw)
    assert resolve_scene(hass, store, saved, now=date(2027, 2, 28))[1]["resolved_season"] == "spring"
    assert resolve_scene(hass, store, saved, now=date(2028, 2, 28))[1]["resolved_season"] == "winter"
    assert resolve_scene(hass, store, saved, now=date(2028, 2, 29))[1]["resolved_season"] == "spring"


@pytest.mark.parametrize("value", [None, [], {"unknown": True}, {"boundaries": {"spring": "03-40"}}, {"boundaries": {"spring": None}}, {"boundaries": {"spring": "09-01"}}, {"boundaries": {"spring": "07-01"}}, {"scenes": {"spring": []}}, {"christmas": {"enabled": 1}}, {"christmas": {"end": "02-30"}}, {"boundaries": {"spring": "02-28", "summer": "02-29"}}])
def test_malformed_seasonal_schema_rejected(value):
    with pytest.raises(ServiceValidationError):
        normalize_seasonal(value)


async def test_fallback_nearest_interval_deleted_refs_preserved_and_notice(hass, store, seasonal):
    await async_delete_scene(store, seasonal.children["winter"]["id"], hass)
    concrete, info = resolve_scene(hass, store, seasonal.wrapper, now=date(2026, 1, 15))
    assert concrete["id"] == seasonal.children["spring"]["id"]
    assert "Winter" in info["resolution_note"] and "Frühling" in info["resolution_note"]
    await async_delete_scene(store, seasonal.children["christmas"]["id"], hass)
    concrete, info = resolve_scene(hass, store, seasonal.wrapper, now=date(2026, 12, 10))
    assert concrete["id"] == seasonal.children["autumn"]["id"]
    assert "Weihnachten" in info["resolution_note"]
    saved = await async_save_scene(hass, store, {**seasonal.wrapper, "name": "Renamed seasonal"})
    assert saved["seasonal"]["scenes"]["winter"] == seasonal.children["winter"]["id"]
    reloaded = LichtzentraleStore(hass)
    await reloaded.async_load()
    assert next(s for s in reloaded.data["scenes"] if s["id"] == saved["id"])["seasonal"] == saved["seasonal"]


async def test_foreign_nested_self_and_new_stale_refs_refused(hass, store, seasonal):
    other = await async_save_scene(hass, store, {"name": "Foreign scene", "area_id": seasonal.areas[1].id, "kind": "snapshot", "lights": {seasonal.ids[2]: {"on": True}}})
    before = store.data
    for identifier in (other["id"], seasonal.wrapper["id"], "missing-synthetic-id"):
        raw = deepcopy(seasonal.wrapper)
        raw["seasonal"]["scenes"]["spring"] = identifier
        with pytest.raises(ServiceValidationError):
            await async_save_scene(hass, store, raw)
        assert store.data == before


async def test_one_seasonal_per_target_under_concurrent_writes(hass, store, seasonal):
    with pytest.raises(ServiceValidationError, match="bereits"):
        await async_save_scene(hass, store, seasonal.raw)
    await async_delete_scene(store, seasonal.wrapper["id"], hass)
    result = await asyncio.gather(async_save_scene(hass, store, seasonal.raw), async_save_scene(hass, store, seasonal.raw), return_exceptions=True)
    assert sum(isinstance(r, ServiceValidationError) for r in result) == 1
    assert len([s for s in store.data["scenes"] if s["kind"] == "seasonal"]) == 1


async def test_reference_deleted_between_validation_and_commit_fails_closed(hass, store, seasonal):
    await async_delete_scene(store, seasonal.wrapper["id"], hass)
    raw = deepcopy(seasonal.raw)
    raw["seasonal"]["scenes"] = {"spring": seasonal.children["spring"]["id"]}
    validated = validate_scene(hass, store, raw)
    await async_delete_scene(store, seasonal.children["spring"]["id"], hass)
    with pytest.raises(ServiceValidationError):
        await store.async_save_scene(validated)
    assert not any(s["kind"] == "seasonal" for s in store.data["scenes"])


async def test_no_assignments_cannot_save_all_deleted_cannot_apply_but_lists(hass, store, seasonal):
    raw = deepcopy(seasonal.wrapper)
    raw["seasonal"]["scenes"] = {}
    with pytest.raises(ServiceValidationError):
        await async_save_scene(hass, store, raw)
    for child in seasonal.children.values():
        await async_delete_scene(store, child["id"], hass)
    with patch.object(type(hass.services), "async_call") as calls:
        with pytest.raises(ServiceValidationError):
            await async_apply_scene(hass, store, seasonal.wrapper["id"])
    calls.assert_not_called()
    item = list_scenes(store)[0]
    assert item["resolved_scene_id"] is None and item["resolution_note"]
    await async_delete_scene(store, seasonal.wrapper["id"], hass)
    assert not store.data["scenes"]


async def test_scene_service_binding_schedule_and_automatic_entrypoints(hass, store, seasonal):
    from custom_components.lichtzentrale.schedule_config import action_targets as schedule_targets

    chosen = seasonal.children["autumn"]
    wrapper_id = seasonal.wrapper["id"]
    manager = BindingManager(hass, store)
    with patch("custom_components.lichtzentrale.seasonal_scenes.dt_util.utcnow", return_value=datetime(2026, 10, 10, tzinfo=UTC)), patch.object(type(hass.services), "async_call") as calls:
        result = await async_apply_scene(hass, store, wrapper_id)
        assert result["resolved_scene_id"] == chosen["id"]
        assert store.data["rooms"][seasonal.areas[0].id]["last_scene_id"] == wrapper_id
        assert {c.args[2]["entity_id"] for c in calls.call_args_list} == set(seasonal.ids[:2])
        assert schedule_targets(hass, store, {"type": "scene", "scene_id": wrapper_id}) == seasonal.ids[:2]
        assert action_targets(hass, store, {"type": "scene", "scene_id": wrapper_id}) == seasonal.ids[:2]
        assert _check_scene(hass, store, wrapper_id, seasonal.areas[0].id)["id"] == chosen["id"]
        binding = {"action": "scene", "area_id": seasonal.areas[0].id, "params": {"scene_id": wrapper_id}}
        result = await manager._action(binding, Context())
        assert result["requested_scene_id"] == wrapper_id
        result = await async_execute_action(hass, store, {"type": "scene", "scene_id": wrapper_id}, automatic=True)
        assert result["resolved_scene_id"] == chosen["id"]
        assert store.data["automatic_state"][seasonal.areas[0].id]["action"]["scene_id"] == wrapper_id


async def test_subset_and_selected_on_behavior_never_expand_scope(hass, store, seasonal):
    with patch.object(type(hass.services), "async_call") as calls:
        result = await async_apply_scene_subset(hass, store, seasonal.wrapper["id"], [seasonal.ids[0]])
        assert result["applied"] == [seasonal.ids[0]]
        assert [c.args[2]["entity_id"] for c in calls.call_args_list] == [seasonal.ids[0]]
    option = {"mode": "scene", "scene_id": seasonal.wrapper["id"]}
    assert validate_on_behavior(hass, store, option, None, [seasonal.ids[0]]) == option
    with pytest.raises(ServiceValidationError):
        validate_on_behavior(hass, store, option, None, [seasonal.ids[2]])


async def test_zone_seasonal_and_foreign_room_child_rejected(hass, store, seasonal):
    zone = await store.async_save_zone({"name": "Synthetic seasonal zone", "entity_ids": [seasonal.ids[0], seasonal.ids[2]]})
    area = "zone:" + zone["id"]
    child = await async_save_scene(hass, store, {"name": "Zone palette", "area_id": area, "kind": "palette", "palette_id": "herbstglut"})
    wrapper = await async_save_scene(hass, store, {"name": "Zone seasons", "area_id": area, "kind": "seasonal", "seasonal": {"scenes": {"autumn": child["id"]}}})
    with patch.object(type(hass.services), "async_call") as calls:
        result = await async_apply_scene(hass, store, wrapper["id"])
    assert set(result["applied"]) == {seasonal.ids[0], seasonal.ids[2]}
    assert {c.args[2]["entity_id"] for c in calls.call_args_list} == set(result["applied"])
    assert wrapper["seasonal"]["boundaries"] == DEFAULT_BOUNDARIES


def test_four_dark_original_romantic_palettes():
    romantic = [p for p in list_palettes() if p["category"] == "Romantik"]
    assert len(romantic) >= 4
    assert all(p["bri"] <= 110 and p["tempo"] in {"slow", "very_slow"} for p in romantic)
    assert next(p for p in romantic if p["id"] == "glutseide")["preview"] == ["#9C2533", "#D36A25", "#E8A347", "#614074"]


async def test_room_default_cycle_and_time_window_scene_keep_wrapper(hass, store, seasonal):
    from custom_components.lichtzentrale.rooms import async_toggle_room

    area, wrapper = seasonal.areas[0].id, seasonal.wrapper["id"]
    await store.async_update_room(area, {"default_on": wrapper, "cycle": [wrapper]})
    manager = BindingManager(hass, store)
    with patch.object(type(hass.services), "async_call") as calls:
        result = await async_toggle_room(hass, store, area, True)
        assert result["requested_scene_id"] == wrapper
        result = await manager._next_scene(area, Context())
        assert result["requested_scene_id"] == result["scene_id"] == wrapper
        calls.reset_mock()
        binding = {"action": "turn_on_lights", "area_id": area, "params": {"entity_ids": [seasonal.ids[0]], "on_behavior": {"mode": "time", "windows": [{"window": {"after": {"type": "time", "value": "00:00"}, "before": {"type": "time", "value": "00:00"}}, "mode": "scene", "scene_id": wrapper}]}}}
        result = await manager._action(binding, Context())
        assert result["requested_scene_id"] == wrapper
        assert [c.args[2]["entity_id"] for c in calls.call_args_list] == [seasonal.ids[0]]


async def test_motion_configuration_and_activation_resolve_same_snapshot(hass, store, seasonal):
    from custom_components.lichtzentrale.motion import MotionManager

    sensor = "binary_sensor.synthetic_seasonal_motion"
    hass.states.async_set(sensor, "on", {"device_class": "motion"})
    config = {"enabled": True, "sensor_entity_ids": [sensor], "timeout_seconds": 60,
              "dim_before_off": False, "lux_sensor_entity_id": None, "lux_below": None,
              "windows": [{"start": {"type": "time", "value": "00:00"}, "end": {"type": "time", "value": "00:00"}, "action": {"type": "scene", "scene_id": seasonal.wrapper["id"]}}]}
    await store.async_set_motion(seasonal.areas[0].id, config)
    manager = MotionManager(hass, store)
    try:
        assert manager._targets(seasonal.areas[0].id) == set(seasonal.ids[:2])
        with patch.object(type(hass.services), "async_call") as calls:
            await manager._activate(seasonal.areas[0].id)
        assert {c.args[2]["entity_id"] for c in calls.call_args_list} == set(seasonal.ids[:2])
        assert store.data["rooms"][seasonal.areas[0].id]["last_scene_id"] == seasonal.wrapper["id"]
    finally:
        await manager.shutdown()


async def test_seasonal_reference_fences_concurrent_deletion_before_dispatch(hass, store, seasonal):
    async def deleted(_hass, _area):
        await store.async_delete_scene(seasonal.wrapper["id"])
        return {"stopped": False}

    with patch("custom_components.lichtzentrale.scenes.stop_dynamic", side_effect=deleted), patch.object(type(hass.services), "async_call") as calls:
        result = await async_apply_scene(hass, store, seasonal.wrapper["id"])
    assert not result["applied"]
    calls.assert_not_called()


async def test_seasonal_entity_migration_keeps_wrapper_reference_intact(hass, store, seasonal):
    from custom_components.lichtzentrale.entity_references import build_reference_replacement

    original = deepcopy(seasonal.wrapper["seasonal"])
    updated, report = build_reference_replacement(store.data, seasonal.ids[0], "light.synthetic_seasonal_replacement")
    assert report["can_replace"]
    assert next(s for s in updated["scenes"] if s["id"] == seasonal.wrapper["id"])["seasonal"] == original
    child = next(s for s in updated["scenes"] if s["id"] == seasonal.children["autumn"]["id"])
    assert "light.synthetic_seasonal_replacement" in child["lights"]
