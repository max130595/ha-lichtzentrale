# Geändert für Lichtzentrale
"""Optional Recorder learning with no hard dependency or stored private history."""

import logging
from datetime import timedelta
from statistics import median

from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)
MIN_SAMPLE_DAYS = 3


def learn_typical_times(history, room_entities, now):
    """Find a repeated daily switch-on cluster; sparse/unreliable data is ignored.

    Only real off-to-on edges within 14 days count, never Recorder's synthetic
    initial state or repeated brightness updates. Rooms/zones aggregate their
    permitted entities and each date contributes at most one sample per cluster.
    """
    lower = dt_util.as_utc(now) - timedelta(days=14)
    upper = dt_util.as_utc(now)
    zone = dt_util.as_local(now).tzinfo
    learned = {}
    for area_id, entities in room_entities.items():
        samples = []
        for entity_id in entities:
            previous = None
            for state in sorted(history.get(entity_id, []), key=lambda item: item.last_changed):
                when = dt_util.as_utc(state.last_changed)
                if state.state == "on" and previous == "off" and lower < when < upper:
                    local = when.astimezone(zone)
                    samples.append((local.hour * 60 + local.minute, local.date()))
                previous = state.state
        best = []
        for center, _ in samples:
            by_day = {}
            for minute, day in samples:
                distance = (minute - center + 720) % 1440 - 720
                if abs(distance) <= 60:
                    value = center + distance
                    if day not in by_day or abs(value - center) < abs(by_day[day] - center):
                        by_day[day] = value
            cluster = list(by_day.values())
            if len(cluster) > len(best):
                best = cluster
        if len(best) >= MIN_SAMPLE_DAYS:
            learned[area_id] = round(median(best)) % 1440
    return learned


async def async_learn_history(hass, store, config, now):
    """Read 14 days on Recorder's executor, gracefully falling back if absent."""
    if not config.get("learn_history") or "recorder" not in hass.config.components:
        return {}
    from .rooms import room_targets

    room_entities = {}
    for room in config["rooms"]:
        if room["weight"] <= 0:
            continue
        try:
            room_entities[room["area_id"]] = room_targets(hass, store, room["area_id"])
        except ServiceValidationError:
            # Rooms can disappear or lose approval between saving and learning.
            continue
    entity_ids = sorted({entity for entities in room_entities.values() for entity in entities})
    if not entity_ids:
        return {}
    try:
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.history import get_significant_states

        start = dt_util.as_utc(now) - timedelta(days=14)
        end = dt_util.as_utc(now)
        history = await get_instance(hass).async_add_executor_job(
            lambda: get_significant_states(
                hass, start, end, entity_ids=entity_ids,
                include_start_time_state=True, significant_changes_only=False,
                minimal_response=False, no_attributes=True,
            )
        )
        return learn_typical_times(history, room_entities, now)
    except Exception:  # Optional database failure must never block vacation mode.
        _LOGGER.debug("Urlaubsverlauf nicht verfügbar; verwende Zufallsplan", exc_info=True)
        return {}
