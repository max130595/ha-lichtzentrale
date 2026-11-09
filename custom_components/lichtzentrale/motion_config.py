# Geändert für Lichtzentrale
"""Closed motion configuration and runtime-only sensor discovery."""

import math
import re
from copy import deepcopy

from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from .lights import entity_area_id
from .rooms import room_targets
from .selected_lights import validate_selected_lights

MOTION_CLASSES = frozenset({"motion", "occupancy", "presence"})


def _sensors(hass, *, lux=False):
    entities, areas = er.async_get(hass), ar.async_get(hass)
    result = []
    for state in hass.states.async_all("sensor" if lux else "binary_sensor"):
        entry = entities.async_get(state.entity_id)
        if entry and entry.disabled_by is not None:
            continue
        device_class = state.attributes.get("device_class")
        if lux:
            if device_class != "illuminance" or state.attributes.get("unit_of_measurement") != "lx":
                continue
        elif device_class not in MOTION_CLASSES:
            continue
        area_id = entity_area_id(hass, state.entity_id)
        area = areas.async_get_area(area_id) if area_id else None
        result.append({
            "entity_id": state.entity_id, "name": state.name,
            "device_class": device_class, "area_id": area_id,
            "area_name": area.name if area else None,
            "available": state.state not in {"unknown", "unavailable"}
            and not state.attributes.get("restored"),
        })
    return sorted(result, key=lambda item: (item["name"].casefold(), item["entity_id"]))


def list_motion_sensors(hass):
    """Discover every eligible trigger, independent of room or manufacturer."""
    return _sensors(hass)


def list_lux_sensors(hass):
    """Expose only illuminance values with the requested lux unit."""
    return _sensors(hass, lux=True)


def validate_boundary(raw):
    """Validate local wall time or a solar event with a minute offset."""
    if not isinstance(raw, dict):
        raise ServiceValidationError("Bitte eine Uhrzeit oder ein Sonnenereignis wählen.")
    if raw.get("type") == "time" and set(raw) == {"type", "value"}:
        if isinstance(raw["value"], str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", raw["value"]):
            return deepcopy(raw)
    elif raw.get("type") == "sun" and set(raw) == {"type", "event", "offset_min"}:
        if (
            raw["event"] in ("sunrise", "sunset")
            and type(raw["offset_min"]) is int
            and -1440 <= raw["offset_min"] <= 1440
        ):
            return deepcopy(raw)
    raise ServiceValidationError("Ungültige Zeitgrenze; Sonnenversatz muss −1440 bis 1440 Minuten sein.")


def validate_motion(hass, store, area_id, raw):
    """Validate all references before persistence and again before runtime actions."""
    from .zones import validate_area

    validate_area(hass, store, area_id)
    keys = {
        "enabled", "sensor_entity_ids", "timeout_seconds", "dim_before_off",
        "lux_sensor_entity_id", "lux_below", "windows",
    }
    if not isinstance(raw, dict) or set(raw) != keys:
        raise ServiceValidationError("Ungültige Bewegungsautomatik.")
    if type(raw["enabled"]) is not bool or type(raw["dim_before_off"]) is not bool:
        raise ServiceValidationError("Automatik und Abdunkeln müssen Ein/Aus-Werte sein.")
    timeout = raw["timeout_seconds"]
    if type(timeout) is not int or not 1 <= timeout <= 86400:
        raise ServiceValidationError("Die Ausschaltzeit muss 1 bis 86400 Sekunden betragen.")
    if raw["dim_before_off"] and timeout <= 20:
        raise ServiceValidationError("Zum Vorabdunkeln muss die Ausschaltzeit über 20 Sekunden liegen.")
    sensors = raw["sensor_entity_ids"]
    available = {sensor["entity_id"] for sensor in list_motion_sensors(hass)}
    if not isinstance(sensors, list) or not sensors or any(
        not isinstance(entity_id, str) or entity_id not in available for entity_id in sensors
    ):
        raise ServiceValidationError("Bitte Bewegungs-, Belegungs- oder Präsenzsensoren auswählen.")
    config = deepcopy(raw)
    config["sensor_entity_ids"] = list(dict.fromkeys(sensors))
    lux_sensor, threshold = raw["lux_sensor_entity_id"], raw["lux_below"]
    if lux_sensor is None:
        if threshold is not None:
            raise ServiceValidationError("Eine Lux-Schwelle benötigt einen Sensor.")
    elif (
        not isinstance(lux_sensor, str)
        or lux_sensor not in {sensor["entity_id"] for sensor in list_lux_sensors(hass)}
        or type(threshold) not in (int, float)
        or not math.isfinite(threshold)
        or threshold < 0
    ):
        raise ServiceValidationError("Bitte einen Lux-Sensor und eine gültige Schwelle in lx wählen.")
    windows = config["windows"]
    if not isinstance(windows, list) or not windows:
        raise ServiceValidationError("Bitte mindestens ein Zeitfenster anlegen.")
    for window in windows:
        if not isinstance(window, dict) or set(window) != {"start", "end", "action"}:
            raise ServiceValidationError("Ungültiges Zeitfenster.")
        window["start"] = validate_boundary(window["start"])
        window["end"] = validate_boundary(window["end"])
        action = window["action"]
        if not isinstance(action, dict):
            raise ServiceValidationError("Ungültige Aktion im Zeitfenster.")
        if action.get("type") == "scene" and set(action) == {"type", "scene_id"}:
            from .bindings import _check_scene

            _check_scene(hass, store, action["scene_id"], area_id)
        elif action.get("type") == "adaptive" and set(action) == {"type"}:
            from .adaptive import _validated

            switch = store.data["rooms"].get(area_id, {}).get("adaptive_switch")
            _validated(hass, store, area_id, switch)
        elif action.get("type") == "lights" and set(action) in (
            {"type", "entity_ids"}, {"type", "entity_ids", "brightness"},
        ):
            targets = action["entity_ids"]
            checked = validate_selected_lights(
                hass, store, room_targets(hass, store, area_id) if targets is None else targets
            )
            if targets is not None:
                action["entity_ids"] = checked
            brightness = action.get("brightness")
            switch_only = all(entity_id.startswith("switch.") for entity_id in checked)
            if not (brightness is None and switch_only) and (
                type(brightness) is not int or not 1 <= brightness <= 255
            ):
                raise ServiceValidationError("Die Helligkeit muss 1 bis 255 betragen.")
            action["brightness"] = brightness
        else:
            raise ServiceValidationError("Bitte Szene, Natürliches Licht oder Lampenauswahl wählen.")
    return config
