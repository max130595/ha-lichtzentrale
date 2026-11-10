# Geändert für Lichtzentrale
# ruff: noqa: F811
"""Vacation fences automatic work without replaying stale sensor triggers."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from test_brightness import brightness  # noqa: F401
from test_motion import change, motion  # noqa: F401
from test_schedule_config import schedule  # noqa: F401
from test_schedules import manager  # noqa: F401


async def test_vacation_pauses_motion_and_drops_deadline(hass, motion):
    automation, area, targets, sensors, calls = motion
    await change(hass, sensors[0], "on")
    await change(hass, sensors[0], "off")
    assert automation.status(area)["remaining_seconds"]
    before = len(calls)
    with patch("custom_components.lichtzentrale.motion.vacation_paused", return_value=True):
        automation.vacation_changed(True)
        await automation._expire(area)
        await change(hass, sensors[0], "on")
        await automation._activate(area)
        assert automation.status(area)["paused"]
        assert not automation.status(area)["active_targets"]
        assert len(calls) == before
    automation.vacation_changed(False)
    await hass.async_block_till_done()
    assert len(calls) == before
    await change(hass, sensors[0], "off")
    await change(hass, sensors[0], "on")
    assert len(calls) == before + len(targets)


async def test_vacation_discards_brightness_learning_and_ownership(hass, brightness):
    t = brightness
    await t.manager.async_evaluate(t.area)
    await hass.async_block_till_done()
    before = len(t.calls)
    with patch("custom_components.lichtzentrale.brightness.vacation_paused", return_value=True):
        t.manager.vacation_changed(True)
        assert t.manager.status(t.area)["paused"]
        assert t.manager._runtime(t.area)["pending"] is None
        assert not t.manager._runtime(t.area)["active"]
        t.time[0] += 1000
        await t.manager.async_evaluate(t.area)
        await t.manager._async_turn_off_owned(t.area)
        assert len(t.calls) == before
    t.manager.vacation_changed(False)
    await t.manager.async_evaluate(t.area)
    assert len(t.calls) == before


async def test_vacation_blocks_schedule_tests_and_rearms_only_future(manager):
    automation, plan = manager
    plan["enabled"] = True
    automation.refresh_config()
    runtime = automation._state(plan["id"])
    generation = runtime["generation"]
    with patch("custom_components.lichtzentrale.schedules.vacation_paused", return_value=True):
        automation.vacation_changed(True)
        assert runtime["cancel"] is None
        automation._fire(plan["id"], generation)
        with pytest.raises(ServiceValidationError):
            await automation.async_test(plan["id"])
    automation.vacation_changed(False)
    assert runtime["cancel"] is not None
    assert runtime["generation"] > generation


async def test_vacation_resume_waits_for_new_lux_crossing(hass, manager):
    automation, plan = manager
    plan.update(enabled=True, trigger={"type": "lux", "sensor_entity_id": "sensor.synthetic_lux",
                                      "comparison": "below", "threshold": 50, "duration_seconds": 300})
    automation.refresh_config()
    runtime = automation._state(plan["id"])
    assert runtime["cancel"]
    with patch("custom_components.lichtzentrale.schedules.vacation_paused", return_value=True):
        automation.vacation_changed(True)
    with patch("custom_components.lichtzentrale.selected_lights.async_control_lights", new_callable=AsyncMock) as action:
        automation.vacation_changed(False)
        automation._arm(plan["id"])
        assert runtime["cancel"] is None
        hass.states.async_set("sensor.synthetic_lux", "60", {
            "device_class": "illuminance", "unit_of_measurement": "lx"})
        await hass.async_block_till_done()
        hass.states.async_set("sensor.synthetic_lux", "10", {
            "device_class": "illuminance", "unit_of_measurement": "lx"})
        await hass.async_block_till_done()
        assert runtime["cancel"]
        action.assert_not_awaited()


async def test_schedule_records_context_for_dynamic_pause(manager):
    automation, plan = manager
    with patch("custom_components.lichtzentrale.selected_lights.async_control_lights", new_callable=AsyncMock) as action:
        await automation.async_test(plan["id"])
        assert action.await_args.kwargs["context"].id in automation._contexts
