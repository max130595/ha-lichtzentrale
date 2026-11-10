# Geändert für Lichtzentrale
"""Vacation planning uses only synthetic rooms and a deterministic solar clock."""

from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.util import dt as dt_util

from custom_components.lichtzentrale.vacation_config import ROOM_DURATIONS, default_vacation_config
from custom_components.lichtzentrale.vacation_planner import (
    build_plan,
    section_bounds,
    until_instant,
)

ZONE = ZoneInfo("Europe/Berlin")


def sun(hass, event, day):
    return datetime.combine(day, datetime.min.time(), ZONE).replace(
        hour=8 if event == "sunrise" else 17)


@pytest.fixture
def config():
    dt_util.set_default_time_zone(ZONE)
    value = default_vacation_config()
    value["rooms"] = [
        {"area_id": f"test_{kind}_{index}", "type": kind, "weight": index + 1,
         "on_behavior": {"mode": "last"}}
        for kind in ROOM_DURATIONS for index in range(3)
    ]
    return value


@pytest.fixture(autouse=True)
def solar():
    with patch("custom_components.lichtzentrale.schedule_windows.get_astral_event_date", side_effect=sun), patch(
        "custom_components.lichtzentrale.vacation_planner.get_astral_event_date", side_effect=sun
    ):
        yield


def instant(value):
    return datetime.fromisoformat(value)


def test_seed_daily_variation_and_durations(hass, config):
    now = datetime(2026, 11, 9, 10, tzinfo=ZONE)
    plan = build_plan(hass, config, now, seed=8)
    assert plan and plan == build_plan(hass, config, now, seed=8)
    assert plan != build_plan(hass, config, now, seed=9)
    assert plan != build_plan(hass, config, now + timedelta(days=1), seed=8)
    by_area = {room["area_id"]: room for room in config["rooms"]}
    kinds = []
    for entry in plan:
        start, end = instant(entry["start"]), instant(entry["end"])
        kind = by_area[entry["area_id"]]["type"]
        minimum, maximum = ROOM_DURATIONS[kind]
        assert minimum <= (end - start).total_seconds() / 60 <= maximum
        assert start.astimezone(ZONE).hour >= 16
        assert end.astimezone(ZONE).hour <= 23
        kinds.append(list(ROOM_DURATIONS).index(kind))
    assert kinds == sorted(kinds)


@pytest.mark.parametrize("maximum", [1, 2, 3, 10])
def test_concurrency_and_no_same_room_overlap(hass, config, maximum):
    config["max_rooms"] = maximum
    for seed in range(20):
        plan = build_plan(hass, config, datetime(2026, 11, 9, 10, tzinfo=ZONE), seed=seed)
        for event in plan:
            moment = instant(event["start"])
            active = [row for row in plan if instant(row["start"]) <= moment < instant(row["end"])]
            assert len(active) <= maximum
            assert len({row["area_id"] for row in active}) == len(active)


def test_morning_dark_short_and_bright_skipped(hass, config):
    config["morning"]["enabled"] = True
    now = datetime(2026, 11, 9, 5, tzinfo=ZONE)
    for seed in range(20):
        morning = [entry for entry in build_plan(hass, config, now, seed=seed) if entry["section"] == "morning"]
        assert 1 <= len(morning) <= 2
        assert 10 <= sum((instant(item["end"]) - instant(item["start"])).total_seconds() / 60 for item in morning) <= 30
        assert all(instant(item["start"]).astimezone(ZONE).hour == 6 or instant(item["start"]).astimezone(ZONE).hour == 7 for item in morning)
    config["morning"]["start"] = {"type": "time", "value": "09:00"}
    config["morning"]["end"] = {"type": "time", "value": "10:00"}
    assert not any(item["section"] == "morning" for item in build_plan(hass, config, now))


def test_restart_no_catchup_end_date_and_midnight(hass, config):
    config["evening"] = {"start": {"type": "time", "value": "22:00"},
                         "end_earliest": {"type": "time", "value": "02:30"},
                         "end_latest": {"type": "time", "value": "03:30"}}
    now = datetime(2026, 11, 10, 0, 25, tzinfo=ZONE)
    plan = build_plan(hass, config, now, seed=42, until="2026-11-10")
    assert any(item["section_id"] == "2026-11-09:evening" for item in plan)
    assert all(instant(item["start"]) >= now for item in plan)
    assert all(instant(item["end"]) <= until_instant("2026-11-10", ZONE) for item in plan)
    assert build_plan(hass, config, now, until="2026-11-09") == []


def test_dst_gaps_folds_and_deadline(hass, config):
    import random

    config["evening"] = {"start": {"type": "time", "value": "01:30"},
                         "end_earliest": {"type": "time", "value": "02:30"},
                         "end_latest": {"type": "time", "value": "02:30"}}
    assert section_bounds(hass, config, datetime(2026, 3, 29).date(), ZONE, "evening", random.Random(1)) is None
    start, end = section_bounds(hass, config, datetime(2026, 10, 25).date(), ZONE, "evening", random.Random(1))
    assert end - start == timedelta(hours=1)
    assert until_instant("2026-03-29", ZONE) - until_instant("2026-03-28", ZONE) == timedelta(hours=23)
    assert until_instant("2026-10-25", ZONE) - until_instant("2026-10-24", ZONE) == timedelta(hours=25)


def test_zero_weight_and_missing_solar(hass, config):
    config["rooms"][0]["weight"] = 0
    now = datetime(2026, 11, 9, 10, tzinfo=ZONE)
    assert all(entry["area_id"] != config["rooms"][0]["area_id"] for entry in build_plan(hass, config, now))
    with patch("custom_components.lichtzentrale.schedule_windows.get_astral_event_date", return_value=None):
        assert build_plan(hass, config, now) == []


def test_learned_time_and_no_mutation(hass, config):
    config["rooms"] = config["rooms"][:1]
    config["learn_history"] = True
    original = deepcopy(config)
    now = datetime(2026, 11, 9, 10, tzinfo=ZONE)
    learned = {config["rooms"][0]["area_id"]: 18 * 60}
    plan = build_plan(hass, config, now, seed=1, learned=learned)
    first = instant(plan[0]["start"]).astimezone(ZONE)
    assert abs(first.hour * 60 + first.minute - 18 * 60) <= 20
    assert config == original
    plan[0]["on_behavior"]["mode"] = "changed"
    assert config == original


def test_section_metadata_covers_restart_and_gaps(hass, config):
    now = datetime(2026, 11, 9, 18, 25, tzinfo=ZONE)
    plan = build_plan(hass, config, now, seed=42)
    assert plan
    section_starts = {row["section_start"] for row in plan}
    section_ends = {row["section_end"] for row in plan}
    assert len(section_starts) == len(section_ends) == 1
    beginning = instant(plan[0]["section_start"])
    ending = instant(plan[0]["section_end"])
    assert beginning == datetime(2026, 11, 9, 16, 45, tzinfo=ZONE)
    assert beginning < now <= instant(plan[0]["start"])
    assert all(beginning <= instant(row["start"]) < instant(row["end"]) <= ending for row in plan)
    # Metadata covers empty slots as well as the room visits themselves.
    assert ending > max(instant(row["end"]) for row in plan)


def test_section_metadata_deadline_and_previous_anchor(hass, config):
    config["evening"] = {"start": {"type": "time", "value": "22:00"},
                         "end_earliest": {"type": "time", "value": "02:30"},
                         "end_latest": {"type": "time", "value": "03:30"}}
    now = datetime(2026, 11, 10, 0, 25, tzinfo=ZONE)
    plan = build_plan(hass, config, now, seed=42, until="2026-11-10")
    previous = [row for row in plan if row["section_id"] == "2026-11-09:evening"]
    assert previous
    assert all(instant(row["section_start"]) == datetime(2026, 11, 9, 22, tzinfo=ZONE)
               for row in previous)
    assert all(instant(row["section_end"]) <= until_instant("2026-11-10", ZONE) for row in plan)
