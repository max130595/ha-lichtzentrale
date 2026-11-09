# Geändert für Lichtzentrale
"""Ordered automation actions use only synthetic devices, never a live installation."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from custom_components.lichtzentrale.schedule_config import validate_schedule
from custom_components.lichtzentrale.schedules import ScheduleManager


@pytest.fixture
async def ordered_plan(hass, store):
    area = ar.async_get(hass).async_create("Synthetic corridor").id
    lamps = []
    for suffix in ("shared", "other"):
        entity = er.async_get(hass).async_get_or_create(
            "light", "synthetic", f"sequence-{suffix}", suggested_object_id=f"synthetic_{suffix}")
        if suffix == "shared":
            er.async_get(hass).async_update_entity(entity.entity_id, area_id=area)
        hass.states.async_set(entity.entity_id, "on", {
            "supported_color_modes": ["brightness"], "brightness": 200})
        lamps.append(entity.entity_id)
    await store.async_set_lights(lamps)
    store._data["zones"] = [{"id": "synthetic_zone", "name": "Synthetic zone", "entity_ids": lamps}]
    store._data["scenes"] = [{"id": "synthetic_night", "name": "Synthetic night", "area_id": area,
        "kind": "snapshot", "night": True, "lights": {lamps[0]: {"on": True, "brightness": 31}}}]
    raw = {"name": "Ordered synthetic automation", "enabled": False,
        "trigger": {"type": "time", "value": "22:30"}, "transition": None,
        "condition": {"weekdays": list(range(7)), "person_entity_ids": [], "light_state": "any"},
        "actions": [{"type": "off", "area_ids": ["zone:synthetic_zone"]},
                    {"type": "night", "area_ids": [area]}]}
    plan = validate_schedule(hass, store, raw)
    store._data["schedules"] = [plan]
    manager = ScheduleManager(hass, store)
    yield manager, plan, lamps
    await manager.shutdown()


@pytest.mark.parametrize("reverse", [False, True])
async def test_overlap_later_action_wins(hass, store, ordered_plan, reverse):
    manager, plan, lamps = ordered_plan
    if reverse:
        plan["actions"].reverse()
    calls = []

    async def simulate(domain, service, data, **kwargs):
        # Yield to expose incorrect concurrent action dispatch.
        await asyncio.sleep(0)
        entity = data["entity_id"]
        calls.append((service, entity))
        state = hass.states.get(entity)
        attrs = dict(state.attributes)
        attrs.update({key: value for key, value in data.items() if key != "entity_id"})
        hass.states.async_set(entity, "off" if service == "turn_off" else "on", attrs)

    with patch.object(type(hass.services), "async_call", side_effect=simulate):
        result = await manager.async_test(plan["id"])
    assert result["condition_met"]
    assert result["applied"].count(lamps[0]) == 2  # No cross-action deduplication.
    assert hass.states.get(lamps[0]).state == ("off" if reverse else "on")
    if not reverse:
        assert hass.states.get(lamps[0]).attributes["brightness"] == 31
    assert hass.states.get(lamps[1]).state == "off"
    shared_calls = [service for service, entity in calls if entity == lamps[0]]
    assert shared_calls == (["turn_on", "turn_off"] if reverse else ["turn_off", "turn_on"])


async def test_awaits_action_and_serializes_test_clicks(hass, ordered_plan):
    manager, plan, lamps = ordered_plan
    entered, release = asyncio.Event(), asyncio.Event()
    events = []

    async def execute(*args, **kwargs):
        kind = args[2]["type"]
        events.append(kind)
        if len(events) == 1:
            entered.set()
            await release.wait()
        return {"applied": [lamps[0]], "skipped": []}

    with patch("custom_components.lichtzentrale.target_actions.async_execute_action", side_effect=execute):
        first = asyncio.create_task(manager.async_test(plan["id"]))
        await entered.wait()
        second = asyncio.create_task(manager.async_test(plan["id"]))
        await asyncio.sleep(0)
        assert events == ["off"]
        release.set()
        await asyncio.gather(first, second)
    assert events == ["off", "night", "off", "night"]


async def test_condition_checked_before_sequence_not_after_own_off(hass, ordered_plan):
    manager, plan, lamps = ordered_plan
    plan["condition"]["light_state"] = "on"
    calls = []

    async def execute(*args, **kwargs):
        assert kwargs["guard"]()
        calls.append(args[2]["type"])
        for entity in lamps:
            state = hass.states.get(entity)
            hass.states.async_set(entity, "off", dict(state.attributes))
        return {"applied": lamps, "skipped": []}

    with patch("custom_components.lichtzentrale.target_actions.async_execute_action", side_effect=execute):
        await manager.async_test(plan["id"])
    assert calls == ["off", "night"]


async def test_disabled_and_failure_reporting(hass, ordered_plan):
    manager, plan, lamps = ordered_plan
    with patch("custom_components.lichtzentrale.target_actions.async_execute_action", new_callable=AsyncMock) as execute:
        result = await manager._execute(plan["id"], manager._state(plan["id"])["generation"])
        assert result["reason"] == "disabled"
        execute.assert_not_awaited()
        execute.side_effect = ServiceValidationError("Synthetic failure")
        with pytest.raises(ServiceValidationError, match="Synthetic failure"):
            await manager.async_test(plan["id"])
        assert execute.await_count == 1
        assert manager.list_schedules()[0]["last_error"] == "Synthetic failure"
        execute.side_effect = None
        execute.return_value = {"applied": [], "skipped": lamps, "failed": []}
        result = await manager.async_test(plan["id"])
        assert result["skipped"] == lamps + lamps
        assert manager.list_schedules()[0]["last_error"]


async def test_closed_actions_and_original_plan_untouched(hass, store, ordered_plan):
    _, plan, _ = ordered_plan
    old = deepcopy(plan)
    assert validate_schedule(hass, store, plan) == plan
    for change in ({"actions": []}, {"actions": "bad"}, {"action": {"type": "room_off", "area_id": "bad"}},
                   {"actions": [{"type": "off", "area_ids": ["zone:missing"]}]}):
        with pytest.raises(ServiceValidationError):
            validate_schedule(hass, store, {**plan, **change})
    assert plan == old


async def test_stored_extensions_preserved_without_accepting_unknown_changes(hass, store, ordered_plan):
    manager, plan, lamps = ordered_plan
    plan["future_metadata"] = {"retained": True}
    plan["condition"]["future_condition"] = "retained"
    assert validate_schedule(hass, store, plan)["future_metadata"] == {"retained": True}
    changed = deepcopy(plan)
    changed["future_metadata"] = "not authorized"
    with pytest.raises(ServiceValidationError):
        validate_schedule(hass, store, changed)
    with patch("custom_components.lichtzentrale.target_actions.async_execute_action", return_value={"applied": lamps, "skipped": []}):
        assert (await manager.async_test(plan["id"]))["condition_met"]


async def test_changed_plan_stops_remaining_actions(hass, store, ordered_plan):
    manager, plan, lamps = ordered_plan

    async def execute(*args, **kwargs):
        store._data["schedules"][0]["enabled"] = True
        return {"applied": lamps, "skipped": []}

    with patch("custom_components.lichtzentrale.target_actions.async_execute_action", side_effect=execute) as action:
        with pytest.raises(ServiceValidationError, match="zwischenzeitlich"):
            await manager.async_test(plan["id"])
        assert action.await_count == 1


async def test_save_reload_order_disabled_state_and_unknown_metadata(hass, store, ordered_plan):
    _, plan, _ = ordered_plan
    store._data["schedules"][0]["future_metadata"] = {"keep": [1, 2]}
    edited = deepcopy(plan)
    edited["name"] = "Edited synthetic plan"
    edited["actions"].reverse()
    saved = await store.async_save_schedule(edited)
    assert not saved["enabled"]
    assert saved["future_metadata"] == {"keep": [1, 2]}
    assert [action["type"] for action in saved["actions"]] == ["night", "off"]
    assert "action" not in saved
    again = await store.async_save_schedule(saved)
    assert again == saved
    assert len(store.data["schedules"]) == 1
