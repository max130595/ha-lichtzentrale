# Geändert für Lichtzentrale
"""Closed vacation settings; all persisted targets remain subject to runtime checks."""

import math
import re
from copy import deepcopy
from datetime import date

from homeassistant.exceptions import ServiceValidationError

from .motion_config import validate_boundary

DEFAULT_VACATION_CONFIG = {
    "rooms": [],
    "evening": {
        "start": {"type": "sun", "event": "sunset", "offset_min": -15},
        "end_earliest": {"type": "time", "value": "22:30"},
        "end_latest": {"type": "time", "value": "23:30"},
    },
    "morning": {
        "enabled": False,
        "start": {"type": "time", "value": "06:30"},
        "end": {"type": "time", "value": "07:30"},
    },
    "max_rooms": 3,
    "learn_history": False,
    "notify_service": None,
}
ROOM_DURATIONS = {"living": (45, 150), "passage": (2, 12), "bedroom": (10, 40)}


def default_vacation_config():
    """Return an independent default without enabling vacation automatically."""
    return deepcopy(DEFAULT_VACATION_CONFIG)


def validate_until(raw):
    """End dates include the chosen local calendar day."""
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raise ServiceValidationError("Bitte ein gültiges Enddatum wählen.")
    try:
        parsed = date.fromisoformat(raw)
        # A following local midnight must be representable.
        if parsed == date.max:
            raise ValueError
    except ValueError as err:
        raise ServiceValidationError("Bitte ein gültiges Enddatum wählen.") from err
    return parsed.isoformat()


def validate_vacation_config(hass, store, raw):
    """Validate complete settings, references and notify service before saving."""
    from .bindings import validate_on_behavior
    from .rooms import room_targets
    from .zones import validate_area

    if not isinstance(raw, dict) or set(raw) != set(DEFAULT_VACATION_CONFIG):
        raise ServiceValidationError("Ungültige Einstellungen für den Urlaubsmodus.")
    result = deepcopy(raw)
    if type(raw["max_rooms"]) is not int or not 1 <= raw["max_rooms"] <= 20:
        raise ServiceValidationError("Bitte 1 bis 20 gleichzeitige Räume wählen.")
    if type(raw["learn_history"]) is not bool:
        raise ServiceValidationError("Verlauf lernen muss ein Ein/Aus-Wert sein.")
    rooms = raw["rooms"]
    if not isinstance(rooms, list) or len(rooms) > 100:
        raise ServiceValidationError("Bitte höchstens 100 Räume wählen.")
    seen = set()
    for room in rooms:
        if not isinstance(room, dict) or set(room) != {"area_id", "type", "weight", "on_behavior"}:
            raise ServiceValidationError("Ungültiger Urlaubsraum.")
        area = room["area_id"]
        if not isinstance(area, str) or not area or area in seen:
            raise ServiceValidationError("Bitte jeden Raum nur einmal wählen.")
        seen.add(area)
        validate_area(hass, store, area)
        if not room_targets(hass, store, area):
            raise ServiceValidationError("Der Raum benötigt freigegebene Lampen.")
        if not isinstance(room["type"], str) or room["type"] not in ROOM_DURATIONS:
            raise ServiceValidationError("Bitte Wohnraum, Durchgang oder Schlafraum wählen.")
        weight = room["weight"]
        if type(weight) not in (int, float) or not math.isfinite(weight) or not 0 <= weight <= 100:
            raise ServiceValidationError("Das Gewicht muss zwischen 0 und 100 liegen.")
        behavior = room["on_behavior"]
        if not isinstance(behavior, dict) or behavior.get("mode") not in ("last", "brightness", "scene"):
            raise ServiceValidationError("Bitte Szene, feste Helligkeit oder letzten Zustand wählen.")
        validate_on_behavior(hass, store, behavior, area)
    for name, keys in (("evening", {"start", "end_earliest", "end_latest"}),
                       ("morning", {"enabled", "start", "end"})):
        window = raw[name]
        if not isinstance(window, dict) or set(window) != keys:
            raise ServiceValidationError("Ungültiges Urlaubszeitfenster.")
        for key in keys - {"enabled"}:
            result[name][key] = validate_boundary(window[key])
    if type(raw["morning"]["enabled"]) is not bool:
        raise ServiceValidationError("Das Morgenfenster muss ein Ein/Aus-Wert sein.")
    service = raw["notify_service"]
    if service is not None and (
        not isinstance(service, str)
        or service == "notify.send_message"
        or not re.fullmatch(r"notify\.[a-z0-9_]+", service)
        or not hass.services.has_service("notify", service.split(".", 1)[1])
    ):
        raise ServiceValidationError("Bitte einen vorhandenen Benachrichtigungsdienst wählen.")
    return result
