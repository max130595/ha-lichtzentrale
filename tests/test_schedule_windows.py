# Geändert für Lichtzentrale
# ruff: noqa: F811 -- imported pytest fixtures are injected by name
"""Synthetic clock, solar and deferred-lux windows; never contact devices."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from test_schedule_config import schedule  # noqa: F401
from test_schedules import manager  # noqa: F401

from custom_components.lichtzentrale.schedule_windows import next_window_run, window_is_open
from custom_components.lichtzentrale.schedules import ScheduleManager, next_run
from custom_components.lichtzentrale.storage import LichtzentraleStore

ZONE = ZoneInfo("Europe/Berlin")
ATTRS = {"device_class": "illuminance", "unit_of_measurement": "lx"}


def clock(value):
    return {"type": "time", "value": value} if value else None


def window(after="18:00", before="23:00"):
    return {"after": clock(after), "before": clock(before)}


def local(day, hour, minute=0, *, fold=0):
    return datetime.fromisoformat(f"{day}T{hour:02}:{minute:02}:00").replace(tzinfo=ZONE, fold=fold)


@pytest.mark.parametrize("after,before,hour,minute,expected", [
    ("18:00", "23:00", 17, 59, False), ("18:00", "23:00", 18, 0, True),
    ("18:00", "23:00", 23, 0, False), ("22:00", "06:00", 23, 0, True),
    ("22:00", "06:00", 0, 0, True), ("22:00", "06:00", 5, 59, True),
    ("22:00", "06:00", 6, 0, False), ("22:00", "06:00", 21, 59, False),
    (None, "06:00", 0, 0, True), (None, "06:00", 6, 0, False),
    ("18:00", None, 18, 0, True), ("18:00", None, 0, 0, False),
    ("06:00", "06:00", 3, 0, True), (None, None, 12, 0, True),
])
async def test_clock_windows(hass, after, before, hour, minute, expected):
    dt_util.set_default_time_zone(ZONE)
    assert window_is_open(hass, window(after, before), local("2026-11-02", hour, minute)) is expected


@pytest.mark.parametrize("day", ["2026-03-29", "2026-10-25"])
async def test_overnight_window_spans_dst(hass, day):
    dt_util.set_default_time_zone(ZONE)
    assert window_is_open(hass, window("22:00", "06:00"), local(day, 3))
    assert not window_is_open(hass, window("22:00", "06:00"), local(day, 6))


async def test_clock_gap_is_skipped_and_fold_stays_one_interval(hass):
    dt_util.set_default_time_zone(ZONE)
    value = window("02:30", "03:30")
    assert not window_is_open(hass, value, local("2026-03-29", 3))
    assert next_window_run(hass, value, local("2026-03-29", 0), list(range(7))) == local("2026-03-30", 2, 30)
    assert not window_is_open(hass, value, local("2026-10-25", 2, 15, fold=0))
    assert window_is_open(hass, value, local("2026-10-25", 2, 15, fold=1))
    assert window_is_open(hass, value, local("2026-10-25", 2, 45, fold=1))
    assert not window_is_open(hass, value, local("2026-10-25", 3, 30))
    assert next_window_run(hass, window("22:00", "06:00"), local("2026-11-02", 23), [1]) == local("2026-11-03", 0)


async def test_solar_offsets_missing_events_and_elapsed_dst(hass):
    dt_util.set_default_time_zone(ZONE)
    value = {"after": {"type": "sun", "event": "sunset", "offset_min": -60}, "before": clock("23:00")}

    def sun(hass, event, day):
        return datetime.combine(day, datetime.min.time(), ZONE).replace(hour=20 if event == "sunset" else 7)

    with patch("custom_components.lichtzentrale.schedule_windows.get_astral_event_date", sun):
        assert not window_is_open(hass, value, local("2026-11-02", 18, 59))
        assert window_is_open(hass, value, local("2026-11-02", 19))
        value["after"]["offset_min"] = 480
        assert window_is_open(hass, value, local("2026-11-03", 4))
        value = {"after": {"type": "sun", "event": "sunrise", "offset_min": -240}, "before": clock("08:00")}
        # 07:00 CEST minus four elapsed hours is 02:00 CET, not nonexistent 03:00.
        assert window_is_open(hass, value, local("2026-03-29", 1, 59)) is False
        assert window_is_open(hass, value, local("2026-03-29", 3))
    with patch("custom_components.lichtzentrale.schedule_windows.get_astral_event_date", return_value=None):
        assert not window_is_open(hass, value, local("2026-11-02", 20))
        assert next_window_run(hass, value, local("2026-11-02", 20), list(range(7))) is None


def setup_lux(manager, plan, value=None):
    plan.update(enabled=True, trigger={"type": "lux", "sensor_entity_id": "sensor.synthetic_lux",
                                      "comparison": "below", "threshold": 50, "duration_seconds": 300})
    plan["condition"]["time_window"] = value or window()
    manager.refresh_config(plan["id"])
    return manager._state(plan["id"])


async def advance(hass, freezer, instant):
    freezer.move_to(instant)
    async_fire_time_changed(hass, dt_util.as_utc(instant))
    await hass.async_block_till_done()


async def test_case_three_deferred_lux_without_another_sensor_event(hass, store, manager, freezer):
    manager, plan = manager
    dt_util.set_default_time_zone(ZONE)
    freezer.move_to(local("2026-11-02", 17))
    runtime = setup_lux(manager, plan)
    with patch("custom_components.lichtzentrale.selected_lights.async_control_lights", new_callable=AsyncMock) as action:
        freezer.move_to(local("2026-11-02", 17, 5))
        manager._fire(plan["id"], runtime["generation"], runtime["timer_token"])
        await hass.async_block_till_done()
        action.assert_not_awaited()
        assert runtime["next_run"] == local("2026-11-02", 18)
        await advance(hass, freezer, local("2026-11-02", 18))
        action.assert_awaited_once()
        assert store.data["settings"]["schedule_last_run_dates"][plan["id"]] == "2026-11-02"
        assert runtime["next_run"] == local("2026-11-03", 18)
        # A fresh threshold crossing may not cause a second run on the same local day.
        hass.states.async_set("sensor.synthetic_lux", "80", ATTRS)
        await hass.async_block_till_done()
        hass.states.async_set("sensor.synthetic_lux", "10", ATTRS)
        await hass.async_block_till_done()
        manager._fire(plan["id"], runtime["generation"], runtime["timer_token"])
        await hass.async_block_till_done()
        assert action.await_count == 1
        await advance(hass, freezer, local("2026-11-03", 18))
        assert action.await_count == 2


@pytest.mark.parametrize("value", ["80", "50", "unknown", "unavailable"])
async def test_lux_recovery_or_unknown_cancels_window_wait(hass, manager, freezer, value):
    manager, plan = manager
    dt_util.set_default_time_zone(ZONE)
    freezer.move_to(local("2026-11-02", 17))
    runtime = setup_lux(manager, plan)
    manager._fire(plan["id"], runtime["generation"])
    assert runtime["lux_ready"]
    hass.states.async_set("sensor.synthetic_lux", value, ATTRS)
    await hass.async_block_till_done()
    assert runtime["cancel"] is None and not runtime["lux_ready"]
    with patch("custom_components.lichtzentrale.selected_lights.async_control_lights", new_callable=AsyncMock) as action:
        await advance(hass, freezer, local("2026-11-02", 18))
        action.assert_not_awaited()


async def test_lux_duration_must_finish_even_when_window_opens(hass, manager, freezer):
    manager, plan = manager
    dt_util.set_default_time_zone(ZONE)
    freezer.move_to(local("2026-11-02", 17, 59))
    runtime = setup_lux(manager, plan)
    assert runtime["next_run"] == local("2026-11-02", 18, 4)
    with patch("custom_components.lichtzentrale.selected_lights.async_control_lights", new_callable=AsyncMock) as action:
        await advance(hass, freezer, local("2026-11-02", 18))
        action.assert_not_awaited()


async def test_daily_limit_survives_reload_and_manual_test_still_checks_window(hass, store, manager, freezer):
    manager, plan = manager
    dt_util.set_default_time_zone(ZONE)
    freezer.move_to(local("2026-11-02", 19))
    runtime = setup_lux(manager, plan)
    with patch("custom_components.lichtzentrale.selected_lights.async_control_lights", new_callable=AsyncMock) as action:
        manager._fire(plan["id"], runtime["generation"])
        await hass.async_block_till_done()
        await manager.shutdown()
        restored = LichtzentraleStore(hass)
        await restored.async_load()
        second = ScheduleManager(hass, restored)
        second._start(hass)
        try:
            other = second._state(plan["id"])
            second._fire(plan["id"], other["generation"])
            await hass.async_block_till_done()
            assert action.await_count == 1
            assert other["next_run"] == local("2026-11-03", 18)
            assert (await second.async_test(plan["id"]))["condition_met"]
            freezer.move_to(local("2026-11-02", 23))
            assert not (await second.async_test(plan["id"]))["condition_met"]
            assert action.await_count == 2
        finally:
            await second.shutdown()


async def test_overnight_daily_limit_and_execution_weekday(hass, manager, freezer):
    manager, plan = manager
    dt_util.set_default_time_zone(ZONE)
    freezer.move_to(local("2026-11-02", 21))
    runtime = setup_lux(manager, plan, window("22:00", "06:00"))
    plan["condition"]["weekdays"] = [1]
    with patch("custom_components.lichtzentrale.selected_lights.async_control_lights", new_callable=AsyncMock) as action:
        manager._fire(plan["id"], runtime["generation"])
        assert runtime["next_run"] == local("2026-11-03", 0)
        await advance(hass, freezer, local("2026-11-03", 0))
        assert action.await_count == 1
        await advance(hass, freezer, local("2026-11-03", 22))
        assert action.await_count == 1


async def test_pending_action_rechecks_window_after_wait(hass, manager, freezer):
    manager, plan = manager
    dt_util.set_default_time_zone(ZONE)
    freezer.move_to(local("2026-11-02", 22, 59))
    plan["condition"]["time_window"] = window()
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed(*args, guard, **kwargs):
        entered.set()
        await release.wait()
        if not guard():
            raise ServiceValidationError("Window closed")

    with patch("custom_components.lichtzentrale.selected_lights.async_control_lights", delayed):
        task = asyncio.create_task(manager.async_test(plan["id"]))
        await entered.wait()
        freezer.move_to(local("2026-11-02", 23))
        release.set()
        with pytest.raises(ServiceValidationError, match="Window closed"):
            await task


async def test_stale_window_callback_cannot_fire_after_edit(hass, manager, freezer):
    manager, plan = manager
    dt_util.set_default_time_zone(ZONE)
    freezer.move_to(local("2026-11-02", 17))
    runtime = setup_lux(manager, plan)
    manager._fire(plan["id"], runtime["generation"])
    generation, token = runtime["generation"], runtime["timer_token"]
    plan["condition"]["time_window"] = window("20:00", "21:00")
    manager.refresh_config(plan["id"])
    with patch("custom_components.lichtzentrale.selected_lights.async_control_lights", new_callable=AsyncMock) as action:
        freezer.move_to(local("2026-11-02", 18))
        manager._fire(plan["id"], generation, token)
        await hass.async_block_till_done()
        action.assert_not_awaited()


async def test_non_lux_next_run_and_manual_test_respect_window(hass, manager, freezer):
    manager, plan = manager
    dt_util.set_default_time_zone(ZONE)
    freezer.move_to(local("2026-11-02", 12))
    plan["condition"]["time_window"] = window("21:00", "22:00")
    assert next_run(hass, plan) is None
    with patch("custom_components.lichtzentrale.selected_lights.async_control_lights", new_callable=AsyncMock) as action:
        assert not (await manager.async_test(plan["id"]))["condition_met"]
        action.assert_not_awaited()
    plan["trigger"]["value"] = "21:30"
    assert next_run(hass, plan) == local("2026-11-02", 21, 30)


async def test_lux_episode_change_during_claim_cannot_dispatch(hass, store, manager, freezer):
    manager, plan = manager
    dt_util.set_default_time_zone(ZONE)
    freezer.move_to(local("2026-11-02", 19))
    runtime = setup_lux(manager, plan)
    entered, release = asyncio.Event(), asyncio.Event()
    original = store.async_claim_schedule_day

    async def delayed_claim(*args):
        entered.set()
        await release.wait()
        return await original(*args)

    with patch.object(store, "async_claim_schedule_day", delayed_claim), patch(
        "custom_components.lichtzentrale.selected_lights._stop_dynamics", new_callable=AsyncMock
    ), patch("homeassistant.core.ServiceRegistry.async_call", new_callable=AsyncMock) as call:
        manager._fire(plan["id"], runtime["generation"])
        await entered.wait()
        hass.states.async_set("sensor.synthetic_lux", "80", ATTRS)
        await asyncio.sleep(0)
        hass.states.async_set("sensor.synthetic_lux", "10", ATTRS)
        await asyncio.sleep(0)
        release.set()
        await hass.async_block_till_done()
        assert not runtime["lux_ready"]
        call.assert_not_awaited()


async def test_fall_back_does_not_fire_twice_same_local_day(hass, manager, freezer):
    manager, plan = manager
    dt_util.set_default_time_zone(ZONE)
    freezer.move_to(local("2026-10-25", 1))
    runtime = setup_lux(manager, plan, window("02:30", "03:30"))
    with patch("custom_components.lichtzentrale.selected_lights.async_control_lights", new_callable=AsyncMock) as action:
        manager._fire(plan["id"], runtime["generation"])
        await advance(hass, freezer, local("2026-10-25", 2, 30, fold=0))
        assert action.await_count == 1
        await advance(hass, freezer, local("2026-10-25", 2, 30, fold=1))
        assert action.await_count == 1
        assert runtime["next_run"] == local("2026-10-26", 2, 30)
