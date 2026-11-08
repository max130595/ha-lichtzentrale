# Geändert für Lichtzentrale
"""Closed room brightness configuration; all devices are runtime discoveries."""

import math
from copy import deepcopy

from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar

from .lights import entity_area_id
from .motion_config import list_lux_sensors
from .schedule_config import list_persons, validate_time_window
from .selected_lights import validate_selected_lights


def validate_brightness(hass, store, area_id, raw):
    """Validate references and grants before persistence and runtime dispatch."""
    def require(value, message="Ungültige Grundhelligkeit."):
        if not value:
            raise ServiceValidationError(message)

    require(isinstance(area_id, str) and ar.async_get(hass).async_get_area(area_id),
            "Der Raum wurde nicht gefunden. Bitte neu laden.")
    require(isinstance(raw, dict) and set(raw) == {
        "enabled", "lux_sensor_entity_id", "target_lux", "hysteresis_lux",
        "min_interval_seconds", "time_window", "person_entity_ids", "stages",
    })
    require(type(raw["enabled"]) is bool)
    require(isinstance(raw["lux_sensor_entity_id"], str) and raw["lux_sensor_entity_id"]
            in {item["entity_id"] for item in list_lux_sensors(hass)},
            "Bitte einen Illuminanzsensor mit Einheit lx wählen.")
    for field in ("target_lux", "hysteresis_lux", "min_interval_seconds"):
        value = raw[field]
        require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
                "Lux-Werte und Mindestzeit müssen gültige, nicht negative Zahlen sein.")
    require(raw["target_lux"] > 0, "Die Zielhelligkeit muss größer als 0 lx sein.")
    require(1 <= raw["min_interval_seconds"] <= 86400,
            "Die Mindestzeit muss 1 bis 86400 Sekunden betragen.")
    result = deepcopy(raw)
    result["time_window"] = validate_time_window(raw["time_window"])
    persons = raw["person_entity_ids"]
    available = {item["entity_id"] for item in list_persons(hass)}
    require(isinstance(persons, list) and all(isinstance(p, str) and p in available for p in persons),
            "Eine ausgewählte Person wurde nicht gefunden.")
    result["person_entity_ids"] = list(dict.fromkeys(persons))
    require(isinstance(raw["stages"], list) and 1 <= len(raw["stages"]) <= 500,
            "Bitte mindestens eine Helligkeitsstufe anlegen.")
    seen = set()
    for stage in result["stages"]:
        require(isinstance(stage, dict) and set(stage) == {"entity_ids", "brightness"})
        targets = validate_selected_lights(hass, store, stage["entity_ids"])
        require(all(entity_area_id(hass, entity_id) == area_id for entity_id in targets),
                "Alle Lampen einer Stufe müssen zu diesem Raum gehören.")
        require(not seen.intersection(targets), "Jede Lampe darf nur in einer Stufe vorkommen.")
        seen.update(targets)
        stage["entity_ids"] = targets
        brightness = stage["brightness"]
        switch_only = all(entity_id.startswith("switch.") for entity_id in targets)
        require((brightness is None and switch_only) or
                (type(brightness) is int and 1 <= brightness <= 255),
                "Die Helligkeit muss 1 bis 255 betragen.")
    return result
