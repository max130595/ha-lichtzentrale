# Geändert für Lichtzentrale
"""Closed schedule schemas and runtime-only target/person discovery."""

import math
from copy import deepcopy
from uuid import uuid4

from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from .motion_config import list_lux_sensors, validate_boundary
from .rooms import room_targets
from .selected_lights import validate_selected_lights


def list_persons(hass):
    """Discover selectable persons without assuming installation-specific IDs."""
    registry = er.async_get(hass)
    return sorted([
        {"entity_id": state.entity_id, "name": state.name,
         "available": state.state not in {"unknown", "unavailable"}
         and not state.attributes.get("restored")}
        for state in hass.states.async_all("person")
        if not ((entry := registry.async_get(state.entity_id)) and entry.disabled_by)
    ], key=lambda item: (item["name"].casefold(), item["entity_id"]))


def _require(value, message="Ungültiger Zeitplan."):
    if not value:
        raise ServiceValidationError(message)


def validate_time_window(window):
    """Share closed optional wall-time/solar windows across room automations."""
    if window is None:
        return None
    _require(isinstance(window, dict) and set(window) == {"after", "before"},
             "Das Zeitfenster benötigt Beginn und Ende; leere Grenzen bleiben offen.")
    result = {key: validate_boundary(value) if value is not None else None
              for key, value in window.items()}
    return result if any(value is not None for value in result.values()) else None


def action_targets(hass, store, action):
    """Validate references/grants again and return the affected light targets."""
    kind = action["type"]
    if kind == "lights":
        return validate_selected_lights(hass, store, action["entity_ids"])
    if kind == "scene":
        from .bindings import _check_scene
        from .scenes import _scene, hue_scene_targets

        scene = _scene(store, action["scene_id"])
        scene = _check_scene(hass, store, scene["id"], scene["area_id"])
        if scene["kind"] == "snapshot":
            targets = list(scene["lights"])
        elif scene["kind"] == "hue":
            targets = hue_scene_targets(hass, scene["hue_scene"])
        else:
            targets = [e for e in room_targets(hass, store, scene["area_id"])
                       if e.startswith("light.")]
    else:
        area = action["area_id"]
        _require(isinstance(area, str) and ar.async_get(hass).async_get_area(area),
                 "Der Raum wurde nicht gefunden.")
        if kind == "adaptive":
            from .adaptive import _validated

            targets = _validated(hass, store, area,
                                 store.data["rooms"].get(area, {}).get("adaptive_switch"))
        else:
            if kind == "motion":
                from .motion_config import validate_motion

                validate_motion(hass, store, area,
                                store.data["rooms"].get(area, {}).get("motion"))
            targets = room_targets(hass, store, area)
    return validate_selected_lights(hass, store, list(targets))


def validate_schedule(hass, store, raw):
    """Normalize new plans; reject stale update IDs and unknown nested fields."""
    # Persisted extension fields belong to their writer. Preserve them verbatim,
    # but never accept new/changed unknown input or interpret it as an action.
    extensions = {}
    previous = next((p for p in store.data.get("schedules", [])
                     if isinstance(raw, dict) and p["id"] == raw.get("id")), None)
    if previous:
        raw = deepcopy(raw)
        schemas = {
            "": {"id", "name", "enabled", "trigger", "condition", "transition", "action", "actions"},
            "condition": {"weekdays", "person_entity_ids", "light_state", "time_window"},
            "trigger": {"type", "value", "event", "offset_min", "sensor_entity_id",
                        "comparison", "threshold", "duration_seconds"},
            "action": {"type", "scene_id", "area_id", "enabled", "entity_ids", "on", "brightness"},
        }
        for section, allowed in schemas.items():
            value = raw if not section else raw.get(section)
            old = previous if not section else previous.get(section)
            if not isinstance(value, dict) or not isinstance(old, dict):
                continue
            extra = {key: value[key] for key in set(value) - allowed}
            _require(all(key in old and old[key] == val for key, val in extra.items()))
            extensions[section] = deepcopy(extra)
            for key in extra:
                value.pop(key)
    keys = {"name", "enabled", "trigger", "condition", "transition"}
    _require(isinstance(raw, dict) and set(raw) in (
        keys | {"action"}, keys | {"action", "id"},
        keys | {"actions"}, keys | {"actions", "id"}))
    result = deepcopy(raw)
    if "id" in raw:
        _require(isinstance(raw["id"], str) and any(
            s["id"] == raw["id"] for s in store.data.get("schedules", [])
        ), "Der Zeitplan wurde nicht gefunden. Bitte neu laden.")
    else:
        result["id"] = str(uuid4())
    _require(isinstance(raw["name"], str) and 0 < len(raw["name"].strip()) <= 100,
             "Bitte einen Namen mit höchstens 100 Zeichen eingeben.")
    result["name"] = raw["name"].strip()
    _require(type(raw["enabled"]) is bool)
    transition = raw["transition"]
    _require(transition is None or (type(transition) in (int, float)
             and math.isfinite(transition) and 0 <= transition <= 1800),
             "Die Übergangszeit muss 0 bis 1800 Sekunden betragen.")
    trigger = raw["trigger"]
    _require(isinstance(trigger, dict))
    if trigger.get("type") == "lux":
        _require(set(trigger) == {"type", "sensor_entity_id", "comparison", "threshold",
                                  "duration_seconds"})
        _require(isinstance(trigger["sensor_entity_id"], str) and trigger["sensor_entity_id"]
                 in {s["entity_id"] for s in list_lux_sensors(hass)},
                 "Bitte einen Illuminanzsensor mit Einheit lx wählen.")
        _require(trigger["comparison"] in ("below", "above"))
        _require(type(trigger["threshold"]) in (int, float)
                 and math.isfinite(trigger["threshold"]) and trigger["threshold"] >= 0)
        _require(type(trigger["duration_seconds"]) is int
                 and 1 <= trigger["duration_seconds"] <= 86400)
    else:
        result["trigger"] = validate_boundary(trigger)
    condition = raw["condition"]
    _require(isinstance(condition, dict)
             and set(condition) in ({"weekdays", "person_entity_ids", "light_state"},
                                   {"weekdays", "person_entity_ids", "light_state", "time_window"}))
    result["condition"]["time_window"] = validate_time_window(condition.get("time_window"))
    days, persons = condition["weekdays"], condition["person_entity_ids"]
    _require(isinstance(days, list) and all(type(d) is int and 0 <= d <= 6 for d in days))
    _require(isinstance(persons, list) and all(isinstance(p, str) and p in {
        s["entity_id"] for s in list_persons(hass)} for p in persons),
        "Eine ausgewählte Person wurde nicht gefunden.")
    _require(condition["light_state"] in ("any", "on", "off"))
    result["condition"]["weekdays"] = sorted(set(days))
    result["condition"]["person_entity_ids"] = list(dict.fromkeys(persons))
    if "actions" in raw:
        from .target_actions import validate_action

        _require(isinstance(raw["actions"], list) and bool(raw["actions"]),
                 "Bitte mindestens eine Aktion auswählen.")
        result["actions"] = [validate_action(hass, store, action) for action in raw["actions"]]
    else:
        result["action"] = validate_legacy_action(hass, store, raw["action"])
    for section, extra in extensions.items():
        (result if not section else result[section]).update(extra)
    return result


def validate_legacy_action(hass, store, action):
    """Keep the original action schema and semantics for existing saved plans."""
    action = deepcopy(action)
    _require(isinstance(action, dict))
    kind = action.get("type")
    fields = {"scene": {"type", "scene_id"}, "adaptive": {"type", "area_id", "enabled"},
              "room_off": {"type", "area_id"}, "motion": {"type", "area_id", "enabled"},
              "lights": {"type", "entity_ids", "on", "brightness"}}
    _require(isinstance(kind, str) and kind in fields and set(action) == fields[kind])
    if kind in ("adaptive", "motion"):
        _require(type(action["enabled"]) is bool)
    if kind == "scene":
        _require(isinstance(action["scene_id"], str))
    if kind == "lights":
        _require(type(action["on"]) is bool)
        brightness = action["brightness"]
        _require(brightness is None or (type(brightness) is int and 1 <= brightness <= 255))
        _require(action["on"] or brightness is None,
                 "Beim Ausschalten bitte keine Helligkeit angeben.")
    targets = action_targets(hass, store, action)
    if kind == "lights":
        action["entity_ids"] = targets
    return action
