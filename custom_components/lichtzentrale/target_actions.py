# Geändert für Lichtzentrale
"""Shared validated actions for room, zone and explicit lamp selections."""

import logging
import math
from copy import deepcopy

from homeassistant.exceptions import ServiceValidationError

from .automatic_state import async_record_action, recall_actions
from .rooms import (
    async_dispatch,
    check_execution_guard,
    light_service_data,
    room_targets,
    validate_control_options,
    validate_transition,
)
from .selected_lights import async_control_lights, validate_selected_lights

_LOGGER = logging.getLogger(__name__)
KINDS = {"scene", "off", "on", "toggle", "brightness", "full_brightness", "night", "return_auto", "night_auto", "adaptive", "motion"}


def areas_for(action):
    values = action.get("area_ids", [])
    if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
        raise ServiceValidationError("Ungültige Raum- oder Zonenauswahl.")
    if action.get("area_id") is not None:
        if not isinstance(action["area_id"], str) or not action["area_id"]:
            raise ServiceValidationError("Ungültiges Ziel.")
        values = [*values, action["area_id"]]
    return list(dict.fromkeys(values))


def night_scene(store, area_id):
    scene = next((s for s in store.data["scenes"] if s["area_id"] == area_id and s.get("night")), None)
    if scene is None:
        raise ServiceValidationError("Bitte zuerst eine Szene als Nachtlicht kennzeichnen.")
    return scene


def action_targets(hass, store, action, *, _entity_ids=None):
    areas = areas_for(action)
    entities = action.get("entity_ids", [])
    if not isinstance(entities, list) or any(not isinstance(e, str) for e in entities):
        raise ServiceValidationError("Ungültige Lampenauswahl.")
    if action.get("type") == "scene":
        from .scenes import _scene, _targets, hue_scene_targets

        scene = _scene(store, action.get("scene_id"))
        from .seasonal_scenes import resolve_scene

        scene, _ = resolve_scene(hass, store, scene)
        if entities or (areas and areas != [scene["area_id"]]):
            raise ServiceValidationError("Eine Szene gehört zu genau einem Raum oder einer Zone.")
        targets = (scene["lights"] if scene["kind"] == "snapshot" else
                   hue_scene_targets(hass, scene["hue_scene"]) if scene["kind"] == "hue" else
                   _area_targets(hass, store, scene["area_id"], _entity_ids))
        if _entity_ids is not None:
            targets = [e for e in targets if e in _entity_ids]
            if not targets:
                return []
        return _targets(hass, store, scene["area_id"], targets)
    if action.get("type") in {"adaptive", "motion"}:
        if len(areas) != 1 or entities:
            raise ServiceValidationError("Diese Aktion benötigt genau einen Raum und keine einzelnen Lampen.")
        if action["type"] == "adaptive":
            from .adaptive import _validated

            return _validated(hass, store, areas[0], store.data["rooms"].get(areas[0], {}).get("adaptive_switch"))
        from .motion_config import validate_motion

        validate_motion(hass, store, areas[0], store.data["rooms"].get(areas[0], {}).get("motion"))
    targets = list(entities)
    for area in areas:
        targets.extend(_area_targets(hass, store, area, _entity_ids))
    if _entity_ids is not None:
        targets = [e for e in targets if e in _entity_ids]
        if not targets:
            return []
    return validate_selected_lights(hass, store, list(dict.fromkeys(targets)))


def _area_targets(hass, store, area, subset):
    if subset is None:
        return room_targets(hass, store, area)
    from .zones import contains, validate_area

    validate_area(hass, store, area)
    return [e for e in store.data["settings"]["light_entity_ids"]
            if e in subset and contains(hass, store, area, e)]


def validate_action(hass, store, action, *, _entity_ids=None):
    if not isinstance(action, dict) or not isinstance(action.get("type"), str) or action["type"] not in KINDS:
        raise ServiceValidationError("Unbekannte Aktion.")
    allowed = {"type", "area_id", "area_ids", "entity_ids"}
    if action["type"] in {"adaptive", "motion"}:
        allowed.add("enabled")
        if type(action.get("enabled")) is not bool:
            raise ServiceValidationError("Ein/Aus muss ein Wahrheitswert sein.")
    if action["type"] == "scene":
        allowed.add("scene_id")
    if action["type"] == "brightness":
        allowed.add("brightness")
        validate_control_options(brightness=action.get("brightness"))
        if action.get("brightness") is None:
            raise ServiceValidationError("Bitte eine Helligkeit auswählen.")
    if set(action) - allowed:
        raise ServiceValidationError("Unbekannte Aktionseinstellung.")
    if action["type"] in {"night", "return_auto", "night_auto"}:
        if not areas_for(action) or action.get("entity_ids"):
            raise ServiceValidationError("Diese Aktion benötigt Räume oder Zonen.")
        if action["type"] != "return_auto":
            for area in areas_for(action):
                night_scene(store, area)
    action_targets(hass, store, action, _entity_ids=_entity_ids)
    return deepcopy(action)


def _night_active(hass, store, area, scene):
    # A remembered scene alone is insufficient after manual control or room-off.
    targets = room_targets(hass, store, area)
    if store.data["rooms"].get(area, {}).get("last_scene_id") != scene["id"]:
        return False
    from .seasonal_scenes import resolve_scene

    scene, _ = resolve_scene(hass, store, scene)
    if scene["kind"] == "snapshot":
        for entity, value in scene["lights"].items():
            state = hass.states.get(entity)
            if state is None or state.state != ("on" if value["on"] else "off"):
                return False
            if value["on"] and state.domain == "light":
                for key, attr in (("brightness", "brightness"), ("color_temp_kelvin", "color_temp_kelvin"), ("xy", "xy_color")):
                    if key in value:
                        actual = state.attributes.get(attr)
                        if key == "xy":
                            if (not isinstance(actual, (list, tuple)) or len(actual) != 2
                                    or any(not _within(a, b, 0.01) for a, b in zip(actual, value[key], strict=True))):
                                return False
                        elif not _within(actual, value[key], 3 if key == "brightness" else 50):
                            return False
        return True
    return any((state := hass.states.get(e)) is not None and state.state == "on" for e in targets)


def _within(actual, expected, tolerance):
    return (type(actual) in (int, float) and math.isfinite(actual)
            and abs(actual - expected) <= tolerance + 1e-9)


async def async_execute_action(hass, store, action, context=None, *, transition=None, guard=None, dispatch_guard=None, automatic=False, _entity_ids=None):
    action = validate_action(hass, store, action, _entity_ids=_entity_ids)
    validate_transition(transition)
    check_execution_guard(guard)
    kind = action["type"]
    targets = action_targets(hass, store, action, _entity_ids=_entity_ids)
    original_targets = tuple(targets)
    if _entity_ids is not None and not targets:
        return {"applied": [], "skipped": []}
    previous_dispatch_guard = dispatch_guard

    def stable_selection():
        check_execution_guard(previous_dispatch_guard)
        if tuple(action_targets(hass, store, action, _entity_ids=_entity_ids)) != original_targets:
            raise ServiceValidationError("Die Zielauswahl hat sich geändert. Bitte erneut versuchen.")
        return True

    dispatch_guard = stable_selection
    if kind == "adaptive":
        from .adaptive import async_set_adaptive

        return await async_set_adaptive(hass, store, areas_for(action)[0], enabled=action["enabled"], context=context, transition=transition, guard=guard, dispatch_guard=dispatch_guard)
    if kind == "motion":
        check_execution_guard(dispatch_guard)
        return await store.async_set_motion_enabled(areas_for(action)[0], action["enabled"], guard=dispatch_guard)
    if kind == "scene":
        from .scenes import async_apply_scene, async_apply_scene_subset

        if _entity_ids is not None:
            result = await async_apply_scene_subset(hass, store, action["scene_id"], targets, context, transition=transition, guard=guard, dispatch_guard=dispatch_guard)
        else:
            result = await async_apply_scene(hass, store, action["scene_id"], context, transition=transition, guard=guard, dispatch_guard=dispatch_guard)
    elif kind in {"night", "return_auto", "night_auto"}:
        result = {"applied": [], "skipped": []}
        for area in areas_for(action):
            check_execution_guard(guard)
            scene = night_scene(store, area) if kind != "return_auto" else None
            returning = kind == "return_auto" or (kind == "night_auto" and _night_active(hass, store, area, scene))
            recalls = recall_actions(hass, store, area) if returning else [({"type": "scene", "scene_id": scene["id"]}, _entity_ids)]
            if not recalls:
                _LOGGER.info("Kein Automatikstand für dieses Ziel am heutigen Tag.")
                result.setdefault("notes", []).append("Für dieses Ziel gibt es heute noch keinen Automatikstand.")
                continue
            for nested, subset in recalls:
                part = await async_execute_action(hass, store, nested, context, transition=transition, guard=guard, dispatch_guard=dispatch_guard, automatic=False, _entity_ids=subset)
                for key in ("applied", "skipped", "failed", "notes"):
                    if key in part:
                        result.setdefault(key, []).extend(e for e in part[key] if e not in result.get(key, []))
                if returning and subset is not None and part.get("applied"):
                    # A partial foreign scene is not the recipient's old night scene.
                    await store.async_update_room(area, {"last_scene_id": None})
                if automatic and not returning:
                    await async_record_action(hass, store, {"type": "night", "area_id": area}, part)
        return result
    elif kind in {"off", "on", "toggle"}:
        result = await async_control_lights(hass, store, targets, on={"off": False, "on": True, "toggle": None}[kind], context=context, transition=transition, guard=guard, dispatch_guard=dispatch_guard)
    else:
        from .selected_lights import _locked_targets, _stop_dynamics

        async with _locked_targets(hass, store, targets) as (locked, areas):
            await _stop_dynamics(hass, store, locked, areas)
            check_execution_guard(guard)
            check_execution_guard(dispatch_guard)
            targets = action_targets(hass, store, action, _entity_ids=_entity_ids)
            calls, skipped, prepared = [], [], {}
            for entity in targets:
                state = hass.states.get(entity)
                if state.state not in {"on", "off"} or (kind == "brightness" and (state.domain == "switch" or light_service_data(state, brightness=action["brightness"]) is None)):
                    skipped.append(entity)
                    continue
                options = {"on": True, "brightness": 255} if kind == "full_brightness" else {"on": True, "brightness": action["brightness"]}
                if kind == "full_brightness" and state.domain == "light":
                    modes = set(state.attributes.get("supported_color_modes") or [])
                    options.update({"color_temp_kelvin": 4000} if "color_temp" in modes else {"xy": [0.38, 0.38]})
                payload = light_service_data(state, transition=transition, **options)
                if payload is None:
                    skipped.append(entity)
                    continue
                calls.append((state.domain, *payload))
                prepared[entity] = state

            def allowed(entity):
                check_execution_guard(dispatch_guard)
                try:
                    return entity in action_targets(hass, store, action, _entity_ids=_entity_ids) and hass.states.get(entity) is prepared[entity]
                except ServiceValidationError:
                    return False

            result = await async_dispatch(hass, calls, skipped, context, guard=allowed)
    if automatic:
        await async_record_action(hass, store, action, result)
    return result
