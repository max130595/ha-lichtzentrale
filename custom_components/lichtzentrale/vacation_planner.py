# Geändert für Lichtzentrale
"""Seeded, side-effect-free vacation plans in absolute time, never catch-up jobs."""

import random
from copy import deepcopy
from datetime import date, datetime, timedelta

from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.util import dt as dt_util

from .schedule_windows import boundary_instant
from .vacation_config import ROOM_DURATIONS, validate_until

SAFETY_RETRY_DELAY = timedelta(minutes=10)
# Permit a delayed timer or short restart, but never replay days-old shutdowns.
SAFETY_LATE_GRACE = timedelta(minutes=10)


def until_instant(until, zone):
    """Exclusive UTC deadline following the selected local end date."""
    value = validate_until(until)
    if value is None:
        return None
    return dt_util.as_utc(datetime.combine(date.fromisoformat(value) + timedelta(days=1),
                                          datetime.min.time(), zone))


def section_bounds(hass, config, day, zone, section, rng):
    """Resolve midnight-crossing boundaries using real next-day solar events."""
    window = config[section]
    if section == "morning" and not window["enabled"]:
        return None
    start = boundary_instant(hass, window["start"], day, zone)
    if start is None:
        return None

    def following(boundary, floor):
        for offset in range(4):
            value = boundary_instant(hass, boundary, day + timedelta(days=offset), zone)
            if value is None:
                return None
            if value > floor:
                return value
        return None

    if section == "morning":
        end = following(window["end"], start)
    else:
        earliest = following(window["end_earliest"], start)
        if earliest is None:
            return None
        latest = following(window["end_latest"], earliest - timedelta(microseconds=1))
        if latest is None:
            return None
        end = earliest + timedelta(seconds=rng.uniform(0, (latest - earliest).total_seconds()))
    return (start, end) if end is not None and end > start else None


def _dark_until(hass, instant, zone):
    """Return next sunrise only when the planned instant is actually at night."""
    day = instant.astimezone(zone).date()
    events = []
    for offset in range(-2, 3):
        for event in ("sunrise", "sunset"):
            value = get_astral_event_date(hass, event, day + timedelta(days=offset))
            if value is not None:
                events.append((dt_util.as_utc(value), event))
    previous = sorted(item for item in events if item[0] <= instant)
    if not previous or previous[-1][1] != "sunset":
        return None
    return min((value for value, event in events if event == "sunrise" and value > instant),
               default=None)


def build_sections(hass, config, now, *, seed=0, until=None, existing=None):
    """Keep section boundaries independently of visits, including the retry window.

    Existing boundaries are fixed for their anchor day, even after replanning or
    midnight. Retaining completed records also prevents a new random end from
    resurrecting an already completed section.
    """
    local, now = dt_util.as_local(now), dt_util.as_utc(now)
    deadline = until_instant(until, local.tzinfo)
    result = {key: deepcopy(value) for key, value in (existing or {}).items()
              if _section_end(value) + timedelta(days=4) >= now}
    if deadline is not None:
        for value in result.values():
            if datetime.fromisoformat(value["start"]) < deadline < _section_end(value):
                value["end"] = deadline.isoformat()
    for offset in range(-3, 1):
        day = local.date() + timedelta(days=offset)
        for section in ("morning", "evening"):
            if section == "morning" and not config["morning"]["enabled"]:
                continue
            key = f"{day.isoformat()}:{section}"
            if key in result:
                continue
            rng = random.Random(f"{seed}:{day.isoformat()}:{section}")
            bounds = section_bounds(hass, config, day, local.tzinfo, section, rng)
            if bounds is None:
                continue
            start, end = bounds
            if deadline is not None:
                end = min(end, deadline)
            if end <= start or end + SAFETY_RETRY_DELAY + SAFETY_LATE_GRACE < now or (offset < 0 and start > now):
                continue
            result[key] = {"section": section, "start": start.isoformat(), "end": end.isoformat(),
                           "end_done": False, "retry_done": False}
    return result


def _section_end(section):
    return dt_util.as_utc(datetime.fromisoformat(section["end"]))


def build_plan(hass, config, now, *, seed=0, until=None, learned=None, sections=None):
    """Build today's/ongoing sections; restart produces only future commands.

    Each entry contains UTC ISO start/end and section_start/section_end,
    area_id, section, section_id and on_behavior. Weights drive weighted sampling with replacement in evening
    phases, and without replacement in the short morning visit.
    """
    local = dt_util.as_local(now)
    now = dt_util.as_utc(now)
    zone = local.tzinfo
    deadline = until_instant(until, zone)
    if deadline is not None and deadline <= now:
        return []
    rooms = [room for room in config["rooms"] if room["weight"] > 0]
    if not rooms:
        return []
    result = []
    for offset in range(-3, 1):
        day = local.date() + timedelta(days=offset)
        for section in ("morning", "evening"):
            rng = random.Random(f"{seed}:{day.isoformat()}:{section}")
            bounds = section_bounds(hass, config, day, zone, section, rng)
            if bounds is None:
                continue
            start, end = bounds
            section_id = f"{day.isoformat()}:{section}"
            if sections is not None:
                saved = sections.get(section_id)
                if saved is None:
                    continue
                start = dt_util.as_utc(datetime.fromisoformat(saved["start"]))
                end = _section_end(saved)
            section_start = start
            # Previous anchors are considered only when their section is active.
            if end <= now or (offset < 0 and start > now):
                continue
            start = max(start, now)
            if deadline is not None:
                end = min(end, deadline)
            if end <= start:
                continue
            section_id = f"{day.isoformat()}:{section}"

            def add(room, begin, finish):
                result.append({"area_id": room["area_id"], "section": section,
                               "section_id": section_id,
                               "section_start": section_start.isoformat(),
                               "section_end": end.isoformat(), "start": begin.isoformat(),
                               "end": finish.isoformat(), "on_behavior": deepcopy(room["on_behavior"])})

            if section == "morning":
                minutes = min(30, int((end - start).total_seconds() // 60))
                if minutes < 10:
                    continue
                count = rng.randint(1, min(2, len(rooms)))
                available = list(rooms)
                chosen = []
                for _ in range(count):
                    room = rng.choices(available, weights=[r["weight"] for r in available])[0]
                    available.remove(room)
                    chosen.append(room)
                # Morning explicitly shortens living visits; passage and bedroom
                # visits still respect their own minimum/maximum durations.
                limits = [(2, 12) if room["type"] == "passage" else (10, 30)
                          for room in chosen]
                minimum = max(10, sum(low for low, _ in limits))
                maximum = min(minutes, sum(high for _, high in limits))
                if maximum < minimum:
                    continue
                total = rng.randint(minimum, maximum)
                begin = start + timedelta(seconds=rng.uniform(0, (end - start).total_seconds() - total * 60))
                sunrise = _dark_until(hass, begin, zone)
                if sunrise is None or sunrise < begin + timedelta(minutes=total):
                    continue
                remaining = total
                for index, room in enumerate(chosen):
                    low, high = limits[index]
                    after = limits[index + 1:]
                    low = max(low, remaining - sum(item[1] for item in after))
                    high = min(high, remaining - sum(item[0] for item in after))
                    duration = rng.randint(low, high)
                    finish = begin + timedelta(minutes=duration)
                    add(room, begin, finish)
                    begin, remaining = finish, remaining - duration
                continue
            # Ordered phases: living, then passage, finally bedroom. No overlap
            # between phases; within each phase up to max_rooms distinct rooms.
            types = [kind for kind in ROOM_DURATIONS if any(r["type"] == kind for r in rooms)]
            total_seconds = (end - start).total_seconds()
            shares = {"living": 0.75, "passage": 0.05, "bedroom": 0.20}
            normalization = sum(shares[kind] for kind in types)
            cursor = start
            for kind in types:
                phase_end = end if kind == types[-1] else cursor + timedelta(
                    seconds=total_seconds * shares[kind] / normalization)
                available = [r for r in rooms if r["type"] == kind]
                slots = [cursor] * min(config["max_rooms"], len(available))
                last_end = {}
                minimum, maximum = ROOM_DURATIONS[kind]
                for _ in range(500):
                    slot = min(range(len(slots)), key=slots.__getitem__)
                    begin = slots[slot]
                    eligible = [r for r in available if last_end.get(r["area_id"], cursor) <= begin]
                    if not eligible:
                        slots[slot] = min(last_end.values())
                        continue
                    room = rng.choices(eligible, weights=[r["weight"] for r in eligible])[0]
                    if learned and config["learn_history"] and room["area_id"] in learned and room["area_id"] not in last_end:
                        minute = int(learned[room["area_id"]])
                        target = boundary_instant(hass, {"type": "time", "value": f"{minute // 60:02}:{minute % 60:02}"}, day, zone)
                        if target is not None:
                            candidate = target + timedelta(minutes=rng.randint(-20, 20))
                            if begin <= candidate <= phase_end - timedelta(minutes=minimum):
                                begin = candidate
                    remaining = int((phase_end - begin).total_seconds() // 60)
                    if remaining < minimum:
                        slots[slot] = phase_end
                        if min(slots) >= phase_end - timedelta(minutes=minimum):
                            break
                        continue
                    duration = rng.randint(minimum, min(maximum, remaining))
                    finish = begin + timedelta(minutes=duration)
                    add(room, begin, finish)
                    last_end[room["area_id"]] = finish
                    slots[slot] = finish + timedelta(minutes=rng.randint(1, 5))
                cursor = phase_end
    # Configurable windows may overlap: admit only entries that obey the global
    # room cap, and never duplicate one room across competing sections.
    accepted = []
    for entry in sorted(result, key=lambda item: (item["start"], item["area_id"])):
        begin, end = datetime.fromisoformat(entry["start"]), datetime.fromisoformat(entry["end"])
        overlapping = [item for item in accepted if datetime.fromisoformat(item["start"]) < end
                       and datetime.fromisoformat(item["end"]) > begin]
        if any(item["area_id"] == entry["area_id"] for item in overlapping):
            continue
        points = {begin} | {datetime.fromisoformat(item["start"]) for item in overlapping}
        if any(sum(datetime.fromisoformat(item["start"]) <= point < datetime.fromisoformat(item["end"])
                   for item in overlapping) >= config["max_rooms"] for point in points if begin <= point < end):
            continue
        accepted.append(entry)
    return accepted
