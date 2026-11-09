# Geändert für Lichtzentrale
"""Local-date scene selection without nesting, timers, or new device targets."""

import calendar
import logging
import re
from copy import deepcopy
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

SEASONS = ("spring", "summer", "autumn", "winter")
LABELS = {"spring": "Frühling", "summer": "Sommer", "autumn": "Herbst", "winter": "Winter", "christmas": "Weihnachten"}
DEFAULT_BOUNDARIES = {"spring": "03-01", "summer": "06-01", "autumn": "09-01", "winter": "12-01"}
DEFAULT_CHRISTMAS = {"enabled": False, "scene_id": None, "start": "12-01", "end": "12-26"}


def _month_day(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}-\d{2}", value):
        raise ServiceValidationError("Bitte Monat und Tag als MM-TT angeben.")
    try:
        month, day = (int(part) for part in value.split("-"))
        date(2000, month, day)
    except ValueError as error:
        raise ServiceValidationError("Dieses Kalenderdatum gibt es nicht.") from error
    return value


def _ordinal(year, month_day):
    month, day = (int(part) for part in month_day.split("-"))
    # A configured leap day begins on the last February day in non-leap years.
    return date(year, month, min(day, calendar.monthrange(year, month)[1])).timetuple().tm_yday - 1


def normalize_seasonal(value):
    if not isinstance(value, dict) or set(value) - {"scenes", "boundaries", "christmas"}:
        raise ServiceValidationError("Ungültige Jahreszeiten-Einstellungen.")
    assignments = value.get("scenes", {})
    boundaries = value.get("boundaries", {})
    christmas = value.get("christmas", {})
    if (not isinstance(assignments, dict) or set(assignments) - set(SEASONS)
            or not isinstance(boundaries, dict) or set(boundaries) - set(SEASONS)
            or not isinstance(christmas, dict) or set(christmas) - set(DEFAULT_CHRISTMAS)):
        raise ServiceValidationError("Ungültige Jahreszeiten-Zuordnung.")
    assignments = {key: assignments.get(key) for key in SEASONS}
    if any(v is not None and (not isinstance(v, str) or not v) for v in assignments.values()):
        raise ServiceValidationError("Bitte gespeicherte Szenen für die Jahreszeiten auswählen.")
    boundaries = {key: _month_day(boundaries.get(key, default)) for key, default in DEFAULT_BOUNDARIES.items()}
    for year in (2000, 2001):
        length = 366 if calendar.isleap(year) else 365
        starts = [_ordinal(year, boundaries[key]) for key in SEASONS]
        relative = [(day - starts[0]) % length for day in starts]
        if len(set(relative)) != 4 or relative != sorted(relative):
            raise ServiceValidationError("Die Grenzen müssen in der Reihenfolge Frühling, Sommer, Herbst, Winter liegen und verschieden sein.")
    christmas = {**DEFAULT_CHRISTMAS, **christmas}
    if (type(christmas["enabled"]) is not bool or
            christmas["scene_id"] is not None and (not isinstance(christmas["scene_id"], str) or not christmas["scene_id"])):
        raise ServiceValidationError("Ungültige Weihnachts-Zuordnung.")
    christmas["start"] = _month_day(christmas["start"])
    christmas["end"] = _month_day(christmas["end"])
    return {"scenes": assignments, "boundaries": boundaries, "christmas": christmas}


def validate_seasonal(store, scene, *, existing=None):
    """Check reference scope both before and inside the Store's write lock."""
    value = normalize_seasonal(scene.get("seasonal"))
    peers = store.data["scenes"]
    if any(p.get("kind") == "seasonal" and p.get("area_id") == scene["area_id"] and p["id"] != scene["id"] for p in peers):
        raise ServiceValidationError("Für diesen Raum oder diese Zone gibt es bereits eine Jahreszeiten-Szene.")
    previous = normalize_seasonal(existing["seasonal"]) if existing and existing.get("kind") == "seasonal" else None
    refs = {**value["scenes"], "christmas": value["christmas"]["scene_id"]}
    old_refs = ({**previous["scenes"], "christmas": previous["christmas"]["scene_id"]} if previous else {})
    usable = 0
    for season, identifier in refs.items():
        if identifier is None:
            continue
        selected = next((s for s in peers if s["id"] == identifier), None)
        if selected is None:
            if identifier == old_refs.get(season):
                continue  # Keep stale selections visible, never silently erase them.
            raise ServiceValidationError("Eine ausgewählte Jahreszeiten-Szene wurde inzwischen gelöscht. Bitte neu auswählen.")
        if (identifier == scene["id"] or selected.get("kind") not in {"snapshot", "palette", "hue"}
                or selected.get("area_id") != scene["area_id"]):
            raise ServiceValidationError("Jahreszeiten dürfen nur normale Szenen desselben Raums oder derselben Zone verwenden.")
        if season in SEASONS:
            usable += 1
    if not usable:
        raise ServiceValidationError("Bitte mindestens einer Jahreszeit eine vorhandene Szene zuordnen.")
    return value


def _within(day, start, end):
    return start <= day <= end if start <= end else day >= start or day <= end


def resolve_scene(hass, store, scene, *, now=None):
    """Resolve exactly once per trigger; existing dynamic runs retain their concrete scene."""
    if scene.get("kind") != "seasonal":
        return deepcopy(scene), {}
    settings = normalize_seasonal(scene.get("seasonal"))
    now = now if now is not None else dt_util.utcnow()
    if isinstance(now, datetime):
        today = (now if now.tzinfo else now.replace(tzinfo=UTC)).astimezone(ZoneInfo(hass.config.time_zone)).date()
    elif isinstance(now, date):
        today = now
    else:
        raise ServiceValidationError("Das lokale Datum konnte nicht bestimmt werden.")
    day = today.timetuple().tm_yday - 1
    length = 366 if calendar.isleap(today.year) else 365
    starts = {key: _ordinal(today.year, value) for key, value in settings["boundaries"].items()}
    ends = {key: (starts[SEASONS[(index + 1) % 4]] - 1) % length for index, key in enumerate(SEASONS)}
    current = next(key for key in SEASONS if _within(day, starts[key], ends[key]))
    christmas = settings["christmas"]
    holiday = christmas["enabled"] and _within(day, _ordinal(today.year, christmas["start"]), _ordinal(today.year, christmas["end"]))
    wanted = "christmas" if holiday else current
    requested = christmas["scene_id"] if holiday else settings["scenes"][current]

    def concrete(identifier):
        return next((s for s in store.data["scenes"] if s["id"] == identifier
                     and s.get("kind") in {"snapshot", "palette", "hue"}
                     and s.get("area_id") == scene["area_id"]), None)

    selected, season, note = concrete(requested), wanted, None
    if selected is None:
        def distance(key):
            return 0 if _within(day, starts[key], ends[key]) else min((starts[key] - day) % length, (day - ends[key]) % length)
        candidates = sorted(SEASONS, key=lambda key: (distance(key), SEASONS.index(key)))
        for season in candidates:
            if selected := concrete(settings["scenes"][season]):
                break
        if selected is None:
            raise ServiceValidationError("Für diese Jahreszeiten-Szene ist keine zugeordnete Szene mehr verfügbar. Bitte die Zuordnung bearbeiten.")
        note = f"Für {LABELS[wanted]} fehlt eine Szene. Stattdessen wird {LABELS[season]} mit „{selected['name']}“ verwendet."
    return deepcopy(selected), {"resolved_scene_id": selected["id"], "resolved_name": selected["name"],
                                "resolved_season": season, "resolution_note": note}


def guard_resolution(hass, store, wrapper, concrete_id, previous=None):
    """A concurrent edit/deletion or date-boundary change cannot expand the prepared recall."""
    from .rooms import check_execution_guard

    check_execution_guard(previous)
    current = next((s for s in store.data["scenes"] if s["id"] == wrapper["id"]), None)
    if current != wrapper or resolve_scene(hass, store, current)[0]["id"] != concrete_id:
        raise ServiceValidationError("Die Jahreszeiten-Zuordnung hat sich geändert. Bitte erneut versuchen.")
    return True


def decorate_result(result, wrapper, info):
    result = {**result, **info, "requested_scene_id": wrapper["id"]}
    if info.get("resolution_note"):
        result.setdefault("notes", []).append(info["resolution_note"])
        _LOGGER.info("%s", info["resolution_note"])
    return result
