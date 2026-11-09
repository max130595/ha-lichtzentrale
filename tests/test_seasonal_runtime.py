# Geändert für Lichtzentrale
"""Independent concrete-run, restart and scope checks for seasonal wrappers."""

from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from custom_components.lichtzentrale.dynamic_scenes import DynamicSceneManager
from custom_components.lichtzentrale.rooms import async_set_light, async_toggle_room
from custom_components.lichtzentrale.scenes import (
    async_apply_scene,
    async_apply_scene_draft,
    async_apply_scene_subset,
    async_save_scene,
)
from custom_components.lichtzentrale.storage import LichtzentraleStore


@pytest.fixture
async def seasonal_run(hass, store, monkeypatch):
    monkeypatch.setattr("custom_components.lichtzentrale.command_limiter.COMMAND_SPACING", 0)
    areas = [ar.async_get(hass).async_create(f"Synthetic seasonal runtime {i}") for i in range(2)]
    ids = []
    for index in range(4):
        entry = er.async_get(hass).async_get_or_create("light", "synthetic", f"seasonal-runtime-{index}")
        er.async_get(hass).async_update_entity(entry.entity_id, area_id=areas[index % 2].id)
        hass.states.async_set(entry.entity_id, "on", {
            "supported_color_modes": ["xy"], "color_mode": "xy", "brightness": 100,
            "xy_color": [0.4, 0.3],
        })
        ids.append(entry.entity_id)
    await store.async_set_lights(ids)
    zone = await store.async_save_zone({"name": "Synthetic seasonal runtime zone", "entity_ids": ids[:3]})
    area = "zone:" + zone["id"]
    concrete = {}
    for season, palette in (("autumn", "kupfernest"), ("winter", "frostsaum")):
        concrete[season] = await async_save_scene(hass, store, {
            "name": f"Synthetic dynamic {season}", "area_id": area, "kind": "palette",
            "palette_id": palette, "brightness": 150,
            "dynamic": {"enabled": True, "tempo": "fast"},
            "lamp_settings": {ids[0]: {"mode": "cycle", "brightness": 31}},
        })
    wrapper = await async_save_scene(hass, store, {
        "name": "Synthetic seasonal runtime", "area_id": area, "kind": "seasonal",
        "seasonal": {"scenes": {key: item["id"] for key, item in concrete.items()}},
    })
    managers = []

    def make_manager(persistent_store=store):
        manager = DynamicSceneManager(hass, persistent_store)
        hass.data.setdefault("lichtzentrale", {}).update(store=persistent_store, dynamic=manager)
        managers.append(manager)
        return manager

    manager = make_manager()
    hass.services.async_register("light", "turn_off", lambda _: None)
    day = [datetime(2026, 10, 15, 12, tzinfo=UTC)]
    with patch("custom_components.lichtzentrale.seasonal_scenes.dt_util.utcnow", side_effect=lambda: day[0]):
        yield SimpleNamespace(ids=ids, area=area, concrete=concrete, wrapper=wrapper,
                              manager=manager, make_manager=make_manager, day=day)
    for manager in managers:
        await manager.shutdown()


async def test_restart_keeps_concrete_then_next_trigger_reselects(hass, store, seasonal_run, light_calls):
    case = seasonal_run
    result = await async_apply_scene(hass, store, case.wrapper["id"])
    assert result["requested_scene_id"] == case.wrapper["id"]
    assert result["resolved_scene_id"] == case.concrete["autumn"]["id"]
    run = case.manager.active[case.area]
    assert run["scene"]["id"] == case.concrete["autumn"]["id"]
    saved = store.data["active_dynamic"][case.area]
    assert saved["scene_id"] == saved["scene"]["id"] == case.concrete["autumn"]["id"]
    assert store.data["rooms"][case.area]["last_scene_id"] == case.wrapper["id"]
    await case.manager.shutdown()
    reloaded = LichtzentraleStore(hass)
    await reloaded.async_load()
    case.day[0] = datetime(2026, 12, 30, 12, tzinfo=UTC)
    resumed = case.make_manager(reloaded)
    light_calls.clear()
    await resumed.restore(wait_for_start=False)
    assert not light_calls
    restored_run = resumed.active[case.area]
    assert restored_run["scene"]["id"] == case.concrete["autumn"]["id"]
    assert await resumed.tick(restored_run, 1)
    assert {call.data["entity_id"] for call in light_calls} == set(case.ids[:3])
    light_calls.clear()
    result = await async_apply_scene(hass, reloaded, case.wrapper["id"])
    assert result["resolved_scene_id"] == case.concrete["winter"]["id"]
    assert restored_run["task"].done()
    assert resumed.active[case.area]["scene"]["id"] == case.concrete["winter"]["id"]
    assert reloaded.data["active_dynamic"][case.area]["scene_id"] == case.concrete["winter"]["id"]
    assert {call.data["entity_id"] for call in light_calls} == set(case.ids[:3])


async def test_wrapper_edit_does_not_change_existing_concrete_loop(hass, store, seasonal_run, light_calls):
    case = seasonal_run
    await async_apply_scene(hass, store, case.wrapper["id"])
    run = case.manager.active[case.area]
    edit = deepcopy(case.wrapper)
    edit["seasonal"]["scenes"]["autumn"] = case.concrete["winter"]["id"]
    await async_save_scene(hass, store, edit)
    light_calls.clear()
    assert await case.manager.tick(run, 1)
    assert case.manager.active[case.area] is run
    assert run["scene"]["id"] == case.concrete["autumn"]["id"]
    await async_apply_scene(hass, store, case.wrapper["id"])
    assert run["task"].done()
    assert case.manager.active[case.area]["scene"]["id"] == case.concrete["winter"]["id"]


async def test_manual_exclusion_survives_season_change_restart(hass, store, seasonal_run, light_calls):
    case = seasonal_run
    await async_apply_scene(hass, store, case.wrapper["id"])
    await async_set_light(hass, store, case.ids[0], brightness=44)
    assert case.manager.active[case.area]["excluded"] == {case.ids[0]}
    await case.manager.shutdown()
    case.day[0] = datetime(2027, 1, 10, 12, tzinfo=UTC)
    resumed = case.make_manager()
    await resumed.restore(wait_for_start=False)
    run = resumed.active[case.area]
    assert run["excluded"] == {case.ids[0]}
    assert run["scene"]["id"] == case.concrete["autumn"]["id"]
    light_calls.clear()
    assert await resumed.tick(run, 2)
    assert {call.data["entity_id"] for call in light_calls} == set(case.ids[1:3])
    await async_apply_scene(hass, store, case.wrapper["id"])
    assert not resumed.active[case.area]["excluded"]
    assert resumed.active[case.area]["scene"]["id"] == case.concrete["winter"]["id"]


@pytest.mark.parametrize("replacement", ["off", "static_scene"])
async def test_explicit_off_or_new_scene_cannot_resurrect_seasonal_run(hass, store, seasonal_run, replacement, light_calls):
    case = seasonal_run
    await async_apply_scene(hass, store, case.wrapper["id"])
    task = case.manager.active[case.area]["task"]
    if replacement == "off":
        await async_toggle_room(hass, store, case.area, False)
    else:
        snapshot = await async_save_scene(hass, store, {
            "name": "Synthetic static replacement", "area_id": case.area, "kind": "snapshot",
            "lights": {entity: {"on": True, "brightness": 80} for entity in case.ids[:3]},
        })
        await async_apply_scene(hass, store, snapshot["id"])
    assert task.done() and not case.manager.active
    assert not store.data["active_dynamic"]
    await case.manager.shutdown()
    case.day[0] = datetime(2027, 1, 10, 12, tzinfo=UTC)
    resumed = case.make_manager()
    light_calls.clear()
    await resumed.restore(wait_for_start=False)
    assert not resumed.active and not light_calls


async def test_seasonal_subset_preserves_unselected_dynamic_peers(hass, store, seasonal_run, light_calls):
    case = seasonal_run
    await async_apply_scene(hass, store, case.wrapper["id"])
    run = case.manager.active[case.area]
    case.day[0] = datetime(2027, 1, 10, 12, tzinfo=UTC)
    light_calls.clear()
    result = await async_apply_scene_subset(hass, store, case.wrapper["id"], [case.ids[0]])
    assert result["resolved_scene_id"] == case.concrete["winter"]["id"]
    assert result["applied"] == [case.ids[0]]
    assert [call.data["entity_id"] for call in light_calls] == [case.ids[0]]
    assert case.manager.active[case.area] is run
    assert run["excluded"] == {case.ids[0]}
    assert run["scene"]["id"] == case.concrete["autumn"]["id"]
    light_calls.clear()
    assert await case.manager.tick(run, 1)
    assert {call.data["entity_id"] for call in light_calls} == set(case.ids[1:3])


@pytest.mark.parametrize("mutation", ["date", "wrapper", "concrete", "revoke"])
async def test_subset_revalidates_wrapper_concrete_and_scope_after_await(hass, store, seasonal_run, mutation, light_calls):
    case = seasonal_run

    async def mutate(*args):
        if mutation == "date":
            case.day[0] = datetime(2027, 1, 10, 12, tzinfo=UTC)
        elif mutation == "wrapper":
            changed = deepcopy(case.wrapper)
            changed["seasonal"]["scenes"]["autumn"] = case.concrete["winter"]["id"]
            await async_save_scene(hass, store, changed)
        elif mutation == "concrete":
            changed = deepcopy(case.concrete["autumn"])
            changed["brightness"] = 200
            await async_save_scene(hass, store, changed)
        else:
            await store.async_set_lights(case.ids[1:])

    with patch("custom_components.lichtzentrale.dynamic_scenes.async_exclude_targets", side_effect=mutate):
        with pytest.raises(ServiceValidationError):
            await async_apply_scene_subset(hass, store, case.wrapper["id"], [case.ids[0]])
    assert not light_calls
    assert not case.manager.active


async def test_seasonal_saved_draft_retains_preview_target_cap(hass, store, seasonal_run, light_calls):
    case = seasonal_run
    result = await async_apply_scene_draft(hass, store, case.wrapper, Context(), targets=[case.ids[0]])
    assert result["applied"] == [case.ids[0]]
    assert [call.data["entity_id"] for call in light_calls] == [case.ids[0]]
    run = case.manager.active[case.area]
    assert run["targets"] == [case.ids[0]] and not run["persist"]
    assert not store.data["active_dynamic"]
