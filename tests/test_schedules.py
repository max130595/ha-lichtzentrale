# Geändert für Lichtzentrale
# ruff: noqa: F811  -- imported pytest fixture is injected by name
"""Timer and action tests never contact a real Home Assistant installation."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from test_adaptive import adaptive  # noqa: F401
from test_schedule_config import schedule  # noqa: F401

from custom_components.lichtzentrale.schedule_config import validate_schedule
from custom_components.lichtzentrale.schedules import ScheduleManager, next_run


@pytest.fixture
async def manager(hass, store, schedule):
    plan = validate_schedule(hass, store, schedule)
    store._data["schedules"] = [plan]
    result = ScheduleManager(hass, store)
    result._start(hass)
    yield result, plan
    await result.shutdown()


async def test_disabled_manual_test_and_conditions(hass, manager):
    manager, plan = manager
    with patch("custom_components.lichtzentrale.selected_lights.async_control_lights",
               new_callable=AsyncMock) as action:
        assert (await manager.async_test(plan["id"]))["condition_met"]
        action.assert_awaited_once()
        plan["condition"]["light_state"] = "on"
        assert not (await manager.async_test(plan["id"]))["condition_met"]
        plan["condition"]["light_state"] = "any"
        hass.states.async_set("light.synthetic_schedule", "unavailable")
        assert not (await manager.async_test(plan["id"]))["condition_met"]
        assert action.await_count == 1


async def test_presence_unknown_and_weekdays(hass, manager):
    manager, plan = manager
    plan["condition"]["person_entity_ids"] = ["person.synthetic_occupant"]
    with patch("custom_components.lichtzentrale.selected_lights.async_control_lights",
               new_callable=AsyncMock) as action:
        for state in ("not_home", "unknown", "unavailable"):
            hass.states.async_set("person.synthetic_occupant", state)
            assert not (await manager.async_test(plan["id"]))["condition_met"]
        hass.states.async_set("person.synthetic_occupant", "home")
        plan["condition"]["weekdays"] = []
        assert not (await manager.async_test(plan["id"]))["condition_met"]
        action.assert_not_awaited()


async def test_revoked_grant_rejected(hass, store, manager):
    manager, plan = manager
    await store.async_set_lights([])
    with pytest.raises(ServiceValidationError):
        await manager.async_test(plan["id"])
    assert manager.list_schedules()[0]["last_error"]


async def test_lux_continuity_latch_and_stale_generation(hass, manager):
    manager, plan = manager
    plan.update(enabled=True, trigger={"type": "lux", "sensor_entity_id": "sensor.synthetic_lux",
                                      "comparison": "below", "threshold": 50, "duration_seconds": 300})
    manager.refresh_config(plan["id"])
    runtime = manager._state(plan["id"])
    generation = runtime["generation"]
    initial_timer = runtime["cancel"]
    assert initial_timer and manager.list_schedules()[0]["next_run"]
    manager._arm(plan["id"])
    assert runtime["cancel"] is initial_timer
    with patch("custom_components.lichtzentrale.selected_lights.async_control_lights",
               new_callable=AsyncMock) as action:
        manager._fire(plan["id"], generation)
        await hass.async_block_till_done()
        assert action.await_count == 1
        assert runtime["latched"]
        manager._arm(plan["id"])
        assert runtime["cancel"] is None
        hass.states.async_set("sensor.synthetic_lux", "unavailable", {
            "device_class": "illuminance", "unit_of_measurement": "lx"})
        await hass.async_block_till_done()
        assert not runtime["latched"]
        hass.states.async_set("sensor.synthetic_lux", "10", {
            "device_class": "illuminance", "unit_of_measurement": "lx"})
        await hass.async_block_till_done()
        assert runtime["cancel"]
        manager.refresh_config(plan["id"])
        manager._fire(plan["id"], generation)
        await hass.async_block_till_done()
        assert action.await_count == 1


async def test_edit_cancels_inflight_manual_test(manager):
    manager, plan = manager
    started = asyncio.Event()

    async def blocked(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    with patch("custom_components.lichtzentrale.selected_lights.async_control_lights", blocked):
        task = asyncio.create_task(manager.async_test(plan["id"]))
        await started.wait()
        manager.refresh_config(plan["id"])
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_next_clock_dst_and_weekday(hass, schedule):
    zone = ZoneInfo("Europe/Berlin")
    dt_util.set_default_time_zone(zone)
    schedule["trigger"]["value"] = "02:30"
    result = next_run(hass, schedule, datetime(2026, 3, 29, 0, tzinfo=zone))
    assert result == datetime(2026, 3, 30, 2, 30, tzinfo=zone)
    result = next_run(hass, schedule, datetime(2026, 10, 25, 2, 45, tzinfo=zone, fold=0))
    assert result == datetime(2026, 10, 26, 2, 30, tzinfo=zone)
    schedule["condition"]["weekdays"] = []
    assert next_run(hass, schedule) is None


async def test_solar_offset_uses_execution_weekday(hass, schedule):
    zone = ZoneInfo("UTC")
    dt_util.set_default_time_zone(zone)
    schedule["trigger"] = {"type": "sun", "event": "sunset", "offset_min": 480}
    schedule["condition"]["weekdays"] = [1]
    now = datetime(2026, 11, 2, 21, tzinfo=zone)

    def sunset(hass, event, day):
        return datetime.combine(day, datetime.min.time(), zone) + timedelta(hours=20)

    with patch("custom_components.lichtzentrale.schedules.get_astral_event_date", sunset):
        assert next_run(hass, schedule, now) == datetime(2026, 11, 3, 4, tzinfo=zone)
    with patch("custom_components.lichtzentrale.schedules.get_astral_event_date", return_value=None):
        assert next_run(hass, schedule, now) is None


async def test_time_timer_disable_and_shutdown(manager):
    manager, plan = manager
    plan["enabled"] = True
    manager.refresh_config()
    runtime = manager._state(plan["id"])
    assert runtime["next_run"] > dt_util.now()
    plan["enabled"] = False
    manager.refresh_config()
    assert runtime["cancel"] is None
    assert manager.list_schedules()[0]["next_run"] is None
    await manager.shutdown()
    with pytest.raises(ServiceValidationError):
        await manager.async_test(plan["id"])


async def test_cancelled_lux_callback_cannot_shorten_new_duration(hass, manager):
    manager, plan = manager
    plan.update(enabled=True, trigger={"type": "lux", "sensor_entity_id": "sensor.synthetic_lux",
                                      "comparison": "below", "threshold": 50, "duration_seconds": 300})
    manager.refresh_config()
    runtime = manager._state(plan["id"])
    token, generation = runtime["timer_token"], runtime["generation"]
    attrs = {"device_class": "illuminance", "unit_of_measurement": "lx"}
    hass.states.async_set("sensor.synthetic_lux", "70", attrs)
    await hass.async_block_till_done()
    hass.states.async_set("sensor.synthetic_lux", "10", attrs)
    await hass.async_block_till_done()
    timer = runtime["cancel"]
    assert timer
    with patch("custom_components.lichtzentrale.selected_lights.async_control_lights",
               new_callable=AsyncMock) as action:
        manager._fire(plan["id"], generation, token)
        await hass.async_block_till_done()
        action.assert_not_awaited()
        assert runtime["cancel"] is timer


async def test_guard_rechecks_conditions_after_destination_wait(hass, manager):
    manager, plan = manager
    entered, release = asyncio.Event(), asyncio.Event()
    plan["condition"]["light_state"] = "off"

    async def delayed(*args, guard, **kwargs):
        entered.set()
        await release.wait()
        if not guard():
            raise ServiceValidationError("Bedingung nicht mehr erfüllt")
        return {"applied": ["light.synthetic_schedule"], "skipped": []}

    with patch("custom_components.lichtzentrale.selected_lights.async_control_lights", delayed):
        task = asyncio.create_task(manager.async_test(plan["id"]))
        await entered.wait()
        hass.states.async_set("light.synthetic_schedule", "on")
        release.set()
        with pytest.raises(ServiceValidationError):
            await task


async def test_partial_result_exposes_error(manager):
    manager, plan = manager
    with patch("custom_components.lichtzentrale.selected_lights.async_control_lights",
               new=AsyncMock(return_value={"applied": [], "skipped": ["light.synthetic_schedule"]})):
        result = await manager.async_test(plan["id"])
        assert result == {"condition_met": True, "applied": [], "skipped": ["light.synthetic_schedule"]}
        assert manager.list_schedules()[0]["last_error"]


async def test_real_selected_light_dispatch(hass, manager, light_calls):
    manager, plan = manager
    plan["action"]["brightness"] = 80
    plan["transition"] = 120
    result = await manager.async_test(plan["id"])
    assert result["applied"] == ["light.synthetic_schedule"]
    assert light_calls[0].data["brightness"] == 80
    assert "transition" not in light_calls[0].data


async def test_per_plan_execution_serialized(manager):
    manager, plan = manager
    entered, release = asyncio.Event(), asyncio.Event()
    running = 0
    maximum = 0

    async def action(*args, **kwargs):
        nonlocal running, maximum
        running += 1
        maximum = max(maximum, running)
        entered.set()
        await release.wait()
        running -= 1
        return {"applied": [], "skipped": []}

    with patch("custom_components.lichtzentrale.selected_lights.async_control_lights", action):
        first = asyncio.create_task(manager.async_test(plan["id"]))
        await entered.wait()
        second = asyncio.create_task(manager.async_test(plan["id"]))
        await asyncio.sleep(0)
        assert maximum == 1
        release.set()
        await asyncio.gather(first, second)
        assert maximum == 1


async def test_scene_and_room_action_route_with_current_targets(hass, store, manager):
    from homeassistant.helpers import area_registry as ar
    from homeassistant.helpers import entity_registry as er

    manager, plan = manager
    area = ar.async_get(hass).async_create("Synthetic schedule room").id
    entity = er.async_get(hass).async_get("light.synthetic_schedule")
    er.async_get(hass).async_update_entity(entity.entity_id, area_id=area)
    store._data["scenes"] = [{"id": "synthetic-scene", "name": "Synthetic scene",
        "kind": "snapshot", "area_id": area,
        "lights": {entity.entity_id: {"on": True, "brightness": 90}}}]
    plan["transition"] = 600
    plan["action"] = {"type": "scene", "scene_id": "synthetic-scene"}
    with patch("custom_components.lichtzentrale.scenes.async_apply_scene",
               new=AsyncMock(return_value={"applied": [entity.entity_id], "skipped": []})) as action:
        assert (await manager.async_test(plan["id"]))["applied"] == [entity.entity_id]
        assert action.call_args.args[2] == "synthetic-scene"
        assert action.call_args.kwargs["transition"] == 600
        assert action.call_args.kwargs["guard"]()
    plan = store._data["schedules"][0]
    plan["action"] = {"type": "room_off", "area_id": area}
    with patch("custom_components.lichtzentrale.rooms.async_toggle_room",
               new=AsyncMock(return_value={"applied": [entity.entity_id], "skipped": []})) as action:
        assert (await manager.async_test(plan["id"]))["condition_met"]
        assert action.call_args.kwargs["on"] is False
        assert action.call_args.kwargs["guard"]()
    store._data["scenes"] = []
    plan = store._data["schedules"][0]
    plan["action"] = {"type": "scene", "scene_id": "synthetic-scene"}
    with pytest.raises(ServiceValidationError):
        await manager.async_test(plan["id"])


async def test_motion_toggle_uses_persisted_room_config(hass, store, manager):
    from homeassistant.helpers import area_registry as ar
    from homeassistant.helpers import entity_registry as er

    manager, plan = manager
    area = ar.async_get(hass).async_create("Synthetic schedule motion room").id
    entity = er.async_get(hass).async_get("light.synthetic_schedule")
    er.async_get(hass).async_update_entity(entity.entity_id, area_id=area)
    hass.states.async_set("binary_sensor.synthetic_schedule_motion", "off", {"device_class": "motion"})
    store._data["rooms"][area] = {"motion": {
        "enabled": False, "sensor_entity_ids": ["binary_sensor.synthetic_schedule_motion"],
        "timeout_seconds": 60, "dim_before_off": False,
        "lux_sensor_entity_id": None, "lux_below": None,
        "windows": [{"start": {"type": "time", "value": "00:00"},
                     "end": {"type": "time", "value": "00:00"},
                     "action": {"type": "lights", "entity_ids": [entity.entity_id], "brightness": 80}}]}}
    plan["action"] = {"type": "motion", "area_id": area, "enabled": True}
    result = await manager.async_test(plan["id"])
    assert result == {"condition_met": True, "applied": [], "skipped": []}
    assert store.data["rooms"][area]["motion"]["enabled"]


async def test_lux_invalid_values_reset_duration(hass, manager):
    manager, plan = manager
    plan.update(enabled=True, trigger={"type": "lux", "sensor_entity_id": "sensor.synthetic_lux",
                                      "comparison": "above", "threshold": 5, "duration_seconds": 300})
    attrs = {"device_class": "illuminance", "unit_of_measurement": "lx"}
    for value in ("nan", "inf", "-1", "unknown", "unavailable", "5"):
        hass.states.async_set("sensor.synthetic_lux", "10", attrs)
        manager.refresh_config()
        assert manager._state(plan["id"])["cancel"]
        hass.states.async_set("sensor.synthetic_lux", value, attrs)
        await hass.async_block_till_done()
        assert manager._state(plan["id"])["cancel"] is None


async def test_delete_and_unload_cancel_pending_actions(hass, store, manager):
    manager, plan = manager
    plan["enabled"] = True
    manager.refresh_config()
    runtime = manager._state(plan["id"])
    generation, token = runtime["generation"], runtime["timer_token"]
    store._data["schedules"] = []
    manager.refresh_config(plan["id"])
    with patch("custom_components.lichtzentrale.selected_lights.async_control_lights",
               new_callable=AsyncMock) as action:
        manager._fire(plan["id"], generation, token)
        await hass.async_block_till_done()
        action.assert_not_awaited()
    assert runtime["cancel"] is None
    assert manager.list_schedules() == []


async def test_adaptive_toggle_reuses_validated_mapping(hass, store, manager, adaptive):
    manager, plan = manager
    area, light, switch, _, calls = adaptive
    store._data["rooms"][area] = {"adaptive_switch": switch}
    plan["action"] = {"type": "adaptive", "area_id": area, "enabled": False}
    store._data["schedules"] = [plan]
    result = await manager.async_test(plan["id"])
    assert result == {"condition_met": True, "applied": [], "skipped": []}
    assert any(call.domain == "switch" and call.service == "turn_off" for call in calls)
    assert not any(call.domain == "light" for call in calls)
