# Geändert für Lichtzentrale
"""Local schedule windows with absolute-time comparisons across DST changes."""

from datetime import datetime, timedelta

from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.util import dt as dt_util


def boundary_instant(hass, boundary, day, zone):
    """Resolve a boundary in UTC; skip clock gaps, choose the first clock fold."""
    if boundary["type"] == "sun":
        event = get_astral_event_date(hass, boundary["event"], day)
        return (dt_util.as_utc(event) + timedelta(minutes=boundary["offset_min"])
                if event is not None else None)
    hour, minute = map(int, boundary["value"].split(":"))
    local = datetime.combine(day, datetime.min.time(), zone).replace(hour=hour, minute=minute, fold=0)
    utc = dt_util.as_utc(local)
    return utc if utc.astimezone(zone).replace(tzinfo=None) == local.replace(tzinfo=None) else None


def _midnight(day, zone):
    return dt_util.as_utc(datetime.combine(day, datetime.min.time(), zone))


def _interval(hass, window, day, zone):
    after, before = window["after"], window["before"]
    start = boundary_instant(hass, after, day, zone) if after else None
    end = boundary_instant(hass, before, day, zone) if before else None
    if (after and start is None) or (before and end is None):
        return None
    if after is None:
        start = _midnight(end.astimezone(zone).date() if end else day, zone)
    if before is None:
        end = _midnight(start.astimezone(zone).date() + timedelta(days=1), zone)
    elif after:
        # Resolve tomorrow's solar event, never add a fixed 24 hours across DST.
        for offset in (1, 2, 3):
            if end > start:
                break
            end = boundary_instant(hass, before, day + timedelta(days=offset), zone)
            if end is None:
                return None
    return (start, end) if end > start else None


def window_is_open(hass, window, now=None):
    """Start is inclusive, end exclusive; equal boundaries span a full day."""
    if not window or not any(window.values()):
        return True
    now = dt_util.as_local(now) if now is not None else dt_util.now()
    instant = dt_util.as_utc(now)
    for offset in range(-3, 3):
        interval = _interval(hass, window, now.date() + timedelta(days=offset), now.tzinfo)
        if interval and interval[0] <= instant < interval[1]:
            return True
    return False


def next_window_run(hass, window, now, weekdays):
    """First permitted instant at/after now, including midnight within a window.

    Weekdays follow the actual local execution date, not the solar anchor date.
    One-sided windows run to/from local midnight on the resolved boundary date.
    Missing solar events and nonexistent clock boundaries fail closed.
    """
    if not weekdays:
        return None
    now = dt_util.as_local(now)
    instant = dt_util.as_utc(now)
    candidates = []
    for offset in range(-3, 370):
        day = now.date() + timedelta(days=offset)
        interval = _interval(hass, window, day, now.tzinfo)
        if interval:
            start, end = interval
            candidate = max(start, instant)
            while candidate < end:
                local = candidate.astimezone(now.tzinfo)
                if local.weekday() in weekdays:
                    candidates.append(candidate)
                    break
                candidate = _midnight(local.date() + timedelta(days=1), now.tzinfo)
        if candidates and offset > 3:
            break
    return min(candidates).astimezone(now.tzinfo) if candidates else None
