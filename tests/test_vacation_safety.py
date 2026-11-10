# Geändert für Lichtzentrale
"""Review regressions: connectivity is not manual control; section-wide safety."""

import asyncio
import logging
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import test_vacation_runtime as runtime_tests
from homeassistant.core import Context
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.lichtzentrale.vacation import VacationManager
from custom_components.lichtzentrale.vacation_planner import build_plan, build_sections

rig = runtime_tests.rig
vacation = runtime_tests.vacation
NOW = datetime(2026, 11, 9, 18, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fast_commands(monkeypatch):
    # Keep the actual shared, guarded dispatch path, without its real-time delay.
    monkeypatch.setattr("custom_components.lichtzentrale.command_limiter.COMMAND_SPACING", 0)


def set_state(hass, entity, value="on", **attributes):
    hass.states.async_set(entity, value, {**hass.states.get(entity).attributes, **attributes}, context=Context())


async def prepare(manager, store, *, start=NOW, end=None, section="evening"):
    end = end or start + timedelta(hours=1)
    section_id = f"{start.date().isoformat()}:{section}"
    await store.async_update_vacation({"enabled": True})
    manager._day = dt_util.as_local(end).date()
    manager._sections = {section_id: {"section": section, "start": start.isoformat(),
        "end": end.isoformat(), "end_done": False, "retry_done": False}}
    manager._arm = lambda seconds: None
    await manager._persist()
    return section_id, end


async def tick(manager, now):
    with patch("custom_components.lichtzentrale.vacation.dt_util.utcnow", return_value=now):
        await manager._tick()


@pytest.mark.parametrize("gaps", [("unavailable",), ("unknown",), ("unavailable", "unknown")])
async def test_same_state_reconnection_keeps_owned_until_interval_end(hass, rig, vacation, gaps):
    manager, _ = vacation
    await manager.async_test()
    entity = rig["lights"][0]
    for state in (*gaps, "on"):
        set_state(hass, entity, state)
        await hass.async_block_till_done()
        assert entity in manager._owned
    await tick(manager, manager._test_until)
    assert hass.states.get(entity).state == "off"


@pytest.mark.parametrize("gap", [None, "unavailable", "unknown"])
async def test_actual_off_releases_ownership_after_any_connectivity_state(hass, rig, vacation, gap):
    manager, _ = vacation
    await manager.async_test()
    entity = rig["lights"][0]
    if gap:
        set_state(hass, entity, gap)
        await hass.async_block_till_done()
    set_state(hass, entity, "off")
    await hass.async_block_till_done()
    assert entity not in manager._owned
    set_state(hass, entity)
    await manager.async_set_enabled(False)
    assert hass.states.get(entity).state == "on"


async def test_foreign_on_service_still_releases_after_reconnection(hass, rig, vacation):
    manager, _ = vacation
    await manager.async_test()
    entity = rig["lights"][0]
    set_state(hass, entity, "unavailable")
    await hass.async_block_till_done()
    await hass.services.async_call("light", "turn_on", {"entity_id": entity}, blocking=True, context=Context())
    await hass.async_block_till_done()
    assert entity not in manager._owned
    await manager.async_set_enabled(False)
    assert hass.states.get(entity).state == "on"


async def test_cleanup_while_unavailable_retains_owned_for_recovery(hass, rig, vacation):
    manager, _ = vacation
    await manager.async_test()
    entity = rig["lights"][0]
    set_state(hass, entity, "unavailable")
    await hass.async_block_till_done()
    await manager.async_set_enabled(False)
    assert entity in manager._owned
    set_state(hass, entity)
    await hass.async_block_till_done()
    assert entity in manager._owned
    await manager.async_set_enabled(False)
    assert hass.states.get(entity).state == "off"
    assert not manager._owned


async def test_section_end_not_last_visit_controls_all_selected_only(hass, store, rig, vacation, caplog):
    manager, calls = vacation
    outside = rig["lights"].pop()
    er.async_get(hass).async_update_entity(outside, area_id=rig["other"])
    for entity in [*rig["lights"], outside]:
        set_state(hass, entity)
    section, end = await prepare(manager, store)
    manager._plan = [{"section_id": section, "section": "evening", "area_id": rig["area"],
        "start": NOW.isoformat(), "end": (end - timedelta(minutes=20)).isoformat(),
        "section_start": NOW.isoformat(), "section_end": end.isoformat(), "on_behavior": {"mode": "last"}}]
    await tick(manager, end - timedelta(minutes=1))
    assert not calls
    caplog.set_level(logging.INFO, logger="custom_components.lichtzentrale.vacation")
    await tick(manager, end)
    assert all(hass.states.get(entity).state == "off" for entity in rig["lights"])
    assert hass.states.get(outside).state == "on"
    assert len(calls) == len(rig["lights"])
    assert len([record for record in caplog.records if "nicht von der Simulation" in record.message]) == len(rig["lights"])


async def test_retry_uses_original_end_plus_ten_once_including_clock_jitter(hass, store, rig, vacation):
    manager, calls = vacation
    section, end = await prepare(manager, store)
    for entity in rig["lights"]:
        set_state(hass, entity)
    await tick(manager, end)
    assert len(calls) == len(rig["lights"])
    for entity in rig["lights"]:
        set_state(hass, entity)
    await tick(manager, end + timedelta(minutes=9, seconds=59))
    assert len(calls) == len(rig["lights"])
    # Event-loop callbacks normally arrive slightly after their due instant.
    await tick(manager, end + timedelta(minutes=10, seconds=1))
    assert len(calls) == 2 * len(rig["lights"])
    for entity in rig["lights"]:
        set_state(hass, entity)
    await tick(manager, end + timedelta(minutes=20))
    assert len(calls) == 2 * len(rig["lights"])
    assert store.data["vacation"]["runtime"]["sections"][section]["retry_done"]


@pytest.mark.parametrize("mode", ["trial", "disabled", "option_off"])
async def test_safety_never_applies_in_trial_disabled_mode_or_disabled_option(hass, store, rig, vacation, mode):
    manager, calls = vacation
    _, end = await prepare(manager, store)
    for entity in rig["lights"]:
        set_state(hass, entity)
    if mode == "trial":
        manager._test_until = end + timedelta(minutes=5)
    elif mode == "disabled":
        await store.async_update_vacation({"enabled": False})
    else:
        config = manager.config
        config["safety_off"] = False
        await store.async_update_vacation({"config": config})
    await tick(manager, end)
    await tick(manager, end + timedelta(minutes=10))
    assert not calls
    assert all(hass.states.get(entity).state == "on" for entity in rig["lights"])


async def test_manual_disable_still_only_cleans_own_lamps(hass, store, rig, vacation):
    manager, calls = vacation
    await prepare(manager, store)
    for entity in rig["lights"]:
        set_state(hass, entity)
    await manager.async_set_enabled(False)
    assert not calls
    assert all(hass.states.get(entity).state == "on" for entity in rig["lights"])


async def test_button_exclusion_applies_to_both_passes_only_current_section(hass, store, rig, vacation):
    manager, calls = vacation
    section, end = await prepare(manager, store)
    for entity in rig["lights"]:
        set_state(hass, entity)
    with patch("custom_components.lichtzentrale.vacation.dt_util.utcnow", return_value=NOW + timedelta(minutes=5)):
        await manager.manual_targets(rig["area"])
    assert (section, rig["area"]) in manager._excluded  # There are no visits.
    await tick(manager, end)
    await tick(manager, end + timedelta(minutes=10))
    assert not calls
    following = "2026-11-10:morning"
    config = manager.config
    config["morning"]["enabled"] = True
    await store.async_update_vacation({"config": config})
    manager._sections[following] = {"section": "morning", "start": end.isoformat(),
        "end": (end + timedelta(hours=1)).isoformat(), "end_done": False, "retry_done": False}
    await tick(manager, end + timedelta(hours=1))
    assert len(calls) == len(rig["lights"])


async def test_overlapping_zone_cannot_bypass_excluded_physical_room(hass, store, rig, vacation):
    manager, calls = vacation
    first, second = rig["lights"][:2]
    er.async_get(hass).async_update_entity(second, area_id=rig["other"])
    zone = await store.async_save_zone({"name": "Synthetic overlap", "entity_ids": [first, second]})
    config = manager.config
    config["rooms"].append({**config["rooms"][0], "area_id": "zone:" + zone["id"]})
    await store.async_update_vacation({"config": config})
    section, end = await prepare(manager, store)
    # Keep the physical room exclusion while a selected overlapping zone remains.
    manager._excluded.add((section, rig["area"]))
    set_state(hass, first)
    set_state(hass, second)
    await tick(manager, end)
    assert hass.states.get(first).state == "on"
    assert hass.states.get(second).state == "off"
    assert [call.data["entity_id"] for call in calls] == [second]


@pytest.mark.parametrize("change", ["grant", "membership", "selection", "stop", "button"])
async def test_safety_rechecks_after_each_physical_effect_command(hass, store, rig, vacation, change, caplog):
    manager, calls = vacation
    first, second = rig["lights"][:2]
    zone = await store.async_save_zone({"name": "Synthetic safety zone", "entity_ids": [first, second]})
    config = manager.config
    config["rooms"][0]["area_id"] = "zone:" + zone["id"]
    await store.async_update_vacation({"config": config})
    section, end = await prepare(manager, store)
    set_state(hass, first, effect_list=["candle", "stop_hue_effect"], effect="candle")
    stopped = []

    async def stop_and_change(call):
        stopped.append(call)
        state = hass.states.get(first)
        hass.states.async_set(first, "on", {**state.attributes, "effect": call.data["effect"]}, context=call.context)
        if change == "grant":
            await store.async_set_lights([entity for entity in rig["lights"] if entity != first])
        elif change == "membership":
            await store.async_save_zone({**zone, "entity_ids": [second]})
        elif change == "selection":
            altered = manager.config
            altered["rooms"] = []
            await store.async_update_vacation({"config": altered})
        elif change == "button":
            manager._excluded.add((section, "zone:" + zone["id"]))
        else:
            manager._stop_requested = True
            manager._generation += 1

    hass.services.async_register("light", "turn_on", stop_and_change)
    caplog.set_level(logging.INFO, logger="custom_components.lichtzentrale.vacation")
    await tick(manager, end)
    assert stopped and stopped[0].data["effect"] == "stop_hue_effect"
    assert not calls  # No OFF slipped through the final physical dispatch guard.
    assert hass.states.get(first).state == "on"
    assert not any("nicht von der Simulation" in record.message for record in caplog.records)


async def test_disable_immediately_fences_safety_waiting_on_runtime_lock(hass, store, rig, vacation):
    manager, calls = vacation
    _, end = await prepare(manager, store)
    set_state(hass, rig["lights"][0])
    started, resume = asyncio.Event(), asyncio.Event()
    observed = {}

    async def blocked_control(*args, **kwargs):
        observed["guard"] = kwargs["dispatch_guard"]
        started.set()
        await resume.wait()
        assert not kwargs["dispatch_guard"]()
        return {"applied": [], "skipped": args[2]}

    with patch("custom_components.lichtzentrale.selected_lights.async_control_lights", side_effect=blocked_control):
        safety = asyncio.create_task(tick(manager, end))
        await started.wait()
        disable = asyncio.create_task(manager.async_set_enabled(False))
        await asyncio.sleep(0)
        assert not disable.done()
        assert not observed["guard"]()
        resume.set()
        await safety
        await disable
    assert not calls
    assert not manager.paused


@pytest.mark.parametrize("restart_at", [NOW + timedelta(minutes=20), NOW + timedelta(hours=1, minutes=5)])
async def test_restart_unknown_on_lamps_preserves_boundary_and_runs_safety(hass, store, rig, vacation, restart_at):
    manager, calls = vacation
    section, end = await prepare(manager, store)
    for entity in rig["lights"]:
        set_state(hass, entity)
    await manager.shutdown()
    replacement = VacationManager(hass, store)
    replacement._arm = lambda seconds: None
    hass.data["lichtzentrale"]["vacation"] = replacement
    try:
        with patch("custom_components.lichtzentrale.vacation.dt_util.utcnow", return_value=restart_at), patch(
            "custom_components.lichtzentrale.vacation_planner.build_plan", return_value=[]
        ):
            await replacement._startup()
        assert replacement._sections[section]["end"] == end.isoformat()
        assert not replacement._owned
        if restart_at < end:
            assert not calls
            await tick(replacement, end)
        assert len(calls) == len(rig["lights"])
        for entity in rig["lights"]:
            set_state(hass, entity)
        await tick(replacement, end + timedelta(minutes=10))
        assert len(calls) == 2 * len(rig["lights"])
    finally:
        await replacement.shutdown()


async def test_restart_after_first_pass_keeps_retry_marker_and_exclusions(hass, store, rig, vacation):
    manager, calls = vacation
    section, end = await prepare(manager, store)
    manager._excluded.add((section, rig["area"]))
    for entity in rig["lights"]:
        set_state(hass, entity)
    await tick(manager, end)
    assert manager._sections[section]["end_done"]
    await manager.shutdown()
    replacement = VacationManager(hass, store)
    replacement._arm = lambda seconds: None
    hass.data["lichtzentrale"]["vacation"] = replacement
    try:
        with patch("custom_components.lichtzentrale.vacation.dt_util.utcnow", return_value=end + timedelta(minutes=5)), patch(
            "custom_components.lichtzentrale.vacation_planner.build_plan", return_value=[]
        ):
            await replacement._startup()
        assert replacement._sections[section]["end_done"]
        assert (section, rig["area"]) in replacement._excluded
        await tick(replacement, end + timedelta(minutes=10))
        assert not calls
        assert all(hass.states.get(entity).state == "on" for entity in rig["lights"])
    finally:
        await replacement.shutdown()


async def test_config_replan_and_midnight_keep_endpoints_and_exclusion(hass, store, rig, vacation):
    manager, _ = vacation
    start = NOW.replace(hour=22)
    end = start + timedelta(hours=4)
    section, _ = await prepare(manager, store, start=start, end=end)
    manager._excluded.add((section, rig["area"]))
    original = deepcopy(manager._sections[section])
    with patch("custom_components.lichtzentrale.vacation.dt_util.utcnow", return_value=start + timedelta(minutes=30)):
        await manager.async_save_config(manager.config)
    assert manager._sections[section] == original
    assert (section, rig["area"]) in manager._excluded
    await tick(manager, start + timedelta(hours=2, minutes=1))
    assert manager._sections[section] == original
    assert (section, rig["area"]) in manager._excluded
    assert all(datetime.fromisoformat(entry["section_end"]) == end for entry in manager._plan if entry["section_id"] == section)


@pytest.mark.parametrize("case", ["weight_zero", "bright_morning", "too_short"])
async def test_no_visits_does_not_remove_configured_safety_boundary(hass, store, rig, vacation, case):
    manager, calls = vacation
    config = manager.config
    if case == "weight_zero":
        config["rooms"][0]["weight"] = 0
    section = "evening"
    if case == "bright_morning":
        section = "morning"
        config["morning"] = {"enabled": True, "start": {"type": "time", "value": "18:00"},
                              "end": {"type": "time", "value": "19:00"}}
    else:
        config["evening"] = {"start": {"type": "time", "value": "18:00"},
            "end_earliest": {"type": "time", "value": "18:05" if case == "too_short" else "19:00"},
            "end_latest": {"type": "time", "value": "18:05" if case == "too_short" else "19:00"}}
    await store.async_update_vacation({"config": config, "enabled": True})
    dt_util.set_default_time_zone(timezone.utc)
    manager._arm = lambda seconds: None
    with patch("custom_components.lichtzentrale.vacation_planner._dark_until", return_value=None):
        await manager._build(NOW)
    key = f"{NOW.date().isoformat()}:{section}"
    assert key in manager._sections
    assert not [entry for entry in manager._plan if entry["section_id"] == key]
    for entity in rig["lights"]:
        set_state(hass, entity)
    await tick(manager, datetime.fromisoformat(manager._sections[key]["end"]))
    assert len([call for call in calls if call.service == "turn_off"]) == len(rig["lights"])
    assert all(hass.states.get(entity).state == "off" for entity in rig["lights"])


def test_disabled_morning_has_no_section_and_late_start_has_retry_window(hass):
    config = runtime_tests.default_vacation_config()
    dt_util.set_default_time_zone(timezone.utc)
    config["evening"] = {"start": {"type": "time", "value": "18:00"},
        "end_earliest": {"type": "time", "value": "19:00"},
        "end_latest": {"type": "time", "value": "19:00"}}
    sections = build_sections(hass, config, NOW + timedelta(hours=1, minutes=5))
    assert "2026-11-09:evening" in sections
    assert not any(value["section"] == "morning" for value in sections.values())
    assert build_plan(hass, config, NOW, sections=sections) == []


@pytest.mark.parametrize("delay, expected", [(timedelta(minutes=10, seconds=1), True),
                                            (timedelta(minutes=21), False)])
async def test_restart_retry_has_bounded_grace_and_is_once(hass, store, rig, vacation, delay, expected):
    manager, calls = vacation
    section, end = await prepare(manager, store)
    await tick(manager, end)
    for entity in rig["lights"]:
        set_state(hass, entity)
    await manager.shutdown()
    replacement = VacationManager(hass, store)
    replacement._arm = lambda seconds: None
    hass.data["lichtzentrale"]["vacation"] = replacement
    try:
        with patch("custom_components.lichtzentrale.vacation.dt_util.utcnow", return_value=end + delay), patch(
            "custom_components.lichtzentrale.vacation_planner.build_plan", return_value=[]
        ):
            await replacement._startup()
        assert len(calls) == (len(rig["lights"]) if expected else 0)
        assert replacement._sections[section]["retry_done"]
        for entity in rig["lights"]:
            set_state(hass, entity)
        await tick(replacement, end + delay + timedelta(seconds=1))
        assert len(calls) == (len(rig["lights"]) if expected else 0)
    finally:
        await replacement.shutdown()


async def test_reapplying_enabled_preserves_active_boundary_and_button_exception(hass, store, rig, vacation):
    manager, calls = vacation
    section, end = await prepare(manager, store)
    manager._excluded.add((section, rig["area"]))
    original = deepcopy(manager._sections[section])
    for entity in rig["lights"]:
        set_state(hass, entity)
    with patch("custom_components.lichtzentrale.vacation.dt_util.utcnow", return_value=NOW + timedelta(minutes=5)):
        await manager.async_set_enabled(True, until="2026-11-10")
    assert manager._sections[section] == original
    assert (section, rig["area"]) in manager._excluded
    await tick(manager, end)
    assert not calls
    assert all(hass.states.get(entity).state == "on" for entity in rig["lights"])


async def test_enddate_midnight_safety_precedes_disable_without_later_retry(hass, store, rig, vacation):
    manager, calls = vacation
    dt_util.set_default_time_zone(timezone.utc)
    config = manager.config
    config["rooms"][0]["weight"] = 0
    config["evening"] = {"start": {"type": "time", "value": "22:00"},
        "end_earliest": {"type": "time", "value": "02:00"},
        "end_latest": {"type": "time", "value": "02:00"}}
    await store.async_update_vacation({"config": config, "enabled": True, "until": "2026-11-09"})
    manager._arm = lambda seconds: None
    await manager._build(NOW.replace(hour=22))
    midnight = (NOW + timedelta(days=1)).replace(hour=0)
    assert manager._sections["2026-11-09:evening"]["end"] == midnight.isoformat()
    for entity in rig["lights"]:
        set_state(hass, entity)
    await tick(manager, midnight)
    assert not manager.paused
    assert len(calls) == len(rig["lights"])
    for entity in rig["lights"]:
        set_state(hass, entity)
    await tick(manager, midnight + timedelta(minutes=10))
    assert len(calls) == len(rig["lights"])
    assert all(hass.states.get(entity).state == "on" for entity in rig["lights"])


@pytest.mark.parametrize("missing", ["removed", "ineligible"])
@pytest.mark.parametrize("manual", [False, True])
async def test_stale_zone_sibling_cannot_bypass_exclusion(hass, store, rig, vacation, missing, manual):
    manager, calls = vacation
    first, second = rig["lights"][:2]
    zone = await store.async_save_zone({"name": "Synthetic stale overlap", "entity_ids": [first, second]})
    overlap = await store.async_save_zone({"name": "Synthetic valid overlap", "entity_ids": [first]})
    config = manager.config
    config["rooms"] = [{**config["rooms"][0], "area_id": "zone:" + item["id"]} for item in (zone, overlap)]
    await store.async_update_vacation({"config": config})
    section, end = await prepare(manager, store)
    set_state(hass, first)
    if missing == "removed":
        hass.states.async_remove(second)
    else:
        set_state(hass, second, entity_id=[first])
    if manual:
        with patch("custom_components.lichtzentrale.vacation.dt_util.utcnow", return_value=NOW + timedelta(minutes=5)):
            await manager.manual_targets(entity_ids=[first])
        assert (section, "zone:" + zone["id"]) in manager._excluded
    else:
        manager._excluded.add((section, "zone:" + zone["id"]))
    await tick(manager, end)
    await tick(manager, end + timedelta(minutes=10))
    assert not calls
    assert hass.states.get(first).state == "on"


@pytest.mark.parametrize("missing", ["removed", "ineligible"])
async def test_stale_zone_sibling_does_not_hide_other_valid_safety_targets(hass, store, rig, vacation, missing):
    manager, calls = vacation
    first, second = rig["lights"][:2]
    zone = await store.async_save_zone({"name": "Synthetic stale safety", "entity_ids": [first, second]})
    config = manager.config
    config["rooms"][0]["area_id"] = "zone:" + zone["id"]
    await store.async_update_vacation({"config": config})
    _, end = await prepare(manager, store)
    set_state(hass, first)
    if missing == "removed":
        hass.states.async_remove(second)
    else:
        set_state(hass, second, entity_id=[first])
    await tick(manager, end)
    assert [call.data["entity_id"] for call in calls] == [first]
    assert hass.states.get(first).state == "off"


async def test_future_window_edit_replaces_only_unstarted_boundary(hass, store, rig, vacation):
    manager, calls = vacation
    dt_util.set_default_time_zone(timezone.utc)
    config = manager.config
    config["rooms"][0]["weight"] = 0
    config["evening"] = {"start": {"type": "time", "value": "18:00"},
        "end_earliest": {"type": "time", "value": "22:00"},
        "end_latest": {"type": "time", "value": "22:00"}}
    await store.async_update_vacation({"config": config, "enabled": True})
    manager._arm = lambda seconds: None
    await manager._build(NOW.replace(hour=10))
    section = "2026-11-09:evening"
    assert manager._sections[section]["end"] == NOW.replace(hour=22).isoformat()
    config["evening"] = {"start": {"type": "time", "value": "19:00"},
        "end_earliest": {"type": "time", "value": "23:00"},
        "end_latest": {"type": "time", "value": "23:00"}}
    with patch("custom_components.lichtzentrale.vacation.dt_util.utcnow", return_value=NOW.replace(hour=10)):
        await manager.async_save_config(config)
    assert manager._sections[section]["start"] == NOW.replace(hour=19).isoformat()
    assert manager._sections[section]["end"] == NOW.replace(hour=23).isoformat()
    for entity in rig["lights"]:
        set_state(hass, entity)
    await tick(manager, NOW.replace(hour=22))
    assert not calls
    await tick(manager, NOW.replace(hour=23))
    assert len(calls) == len(rig["lights"])


async def test_active_window_edit_keeps_boundary_and_exclusion(hass, store, rig, vacation):
    manager, calls = vacation
    section, end = await prepare(manager, store)
    manager._excluded.add((section, rig["area"]))
    config = manager.config
    config["evening"] = {"start": {"type": "time", "value": "19:00"},
        "end_earliest": {"type": "time", "value": "23:00"},
        "end_latest": {"type": "time", "value": "23:00"}}
    with patch("custom_components.lichtzentrale.vacation.dt_util.utcnow", return_value=NOW + timedelta(minutes=5)):
        await manager.async_save_config(config)
    assert manager._sections[section]["end"] == end.isoformat()
    assert (section, rig["area"]) in manager._excluded
    for entity in rig["lights"]:
        set_state(hass, entity)
    await tick(manager, end)
    assert not calls


async def test_earlier_enddate_caps_existing_active_boundary(hass, store, rig, vacation):
    manager, calls = vacation
    dt_util.set_default_time_zone(timezone.utc)
    start = NOW.replace(hour=22)
    section, _ = await prepare(manager, store, start=start, end=start + timedelta(hours=4))
    with patch("custom_components.lichtzentrale.vacation.dt_util.utcnow", return_value=start + timedelta(minutes=5)):
        await manager.async_set_enabled(True, until="2026-11-09")
    midnight = start + timedelta(hours=2)
    assert manager._sections[section]["end"] == midnight.isoformat()
    calls.clear()
    for entity in rig["lights"]:
        set_state(hass, entity)
    await tick(manager, midnight)
    assert not manager.paused
    assert len(calls) == len(rig["lights"])
