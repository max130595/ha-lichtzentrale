# Geändert für Lichtzentrale
"""Area-backed rooms and explicit, capability-aware lighting controls."""

import asyncio
import math

from homeassistant.components.light import LightEntityFeature
from homeassistant.core import Context, HomeAssistant, State, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar

from .color_temperature import find_closest_ct_match
from .const import DOMAIN
from .lights import entity_area_id, list_lights, validate_lights
from .storage import LichtzentraleStore

COLOR_MODES = {"xy", "hs", "rgb", "rgbw", "rgbww"}


@callback
def list_rooms(hass: HomeAssistant, store: LichtzentraleStore) -> list[dict]:
    """Only HA areas containing explicitly approved lighting are rooms."""
    allowed = store.data["settings"]["light_entity_ids"]
    lights = list_lights(hass, allowed)
    result = []
    for area in ar.async_get(hass).async_list_areas():
        members = [item for item in lights if item["allowed"] and item["area_id"] == area.id]
        if not members:
            continue
        status_members = [item for item in members if item["domain"] == "light"] or members
        brightness = [
            item["brightness"]
            for item in members
            if item["on"] and item["available"] and item["brightness"] is not None
        ]
        result.append(
            {
                "area_id": area.id,
                "name": area.name,
                "lights": members,
                "on": any(item["on"] for item in status_members),
                "brightness": round(sum(brightness) / len(brightness)) if brightness else None,
                "available_count": sum(item["available"] for item in members),
                "last_scene_id": store.data["rooms"].get(area.id, {}).get("last_scene_id"),
                "cycle": store.data["rooms"].get(area.id, {}).get("cycle", []),
                "default_on": store.data["rooms"].get(area.id, {}).get("default_on", "last"),
                "positions": {
                    item["entity_id"]: position
                    for item in members
                    if (
                        position := store.data["rooms"]
                        .get(area.id, {})
                        .get("positions", {})
                        .get(item["entity_id"])
                    )
                    is not None
                },
            }
        )
    return sorted(result, key=lambda room: room["name"])


@callback
def room_targets(hass: HomeAssistant, store: LichtzentraleStore, area_id: str) -> list[str]:
    """Return approved area members, validating all before performing work."""
    if not ar.async_get(hass).async_get_area(area_id):
        raise ServiceValidationError("Der Raum wurde nicht gefunden.")
    targets = [
        entity_id
        for entity_id in store.data["settings"]["light_entity_ids"]
        if entity_area_id(hass, entity_id) == area_id
    ]
    return validate_lights(hass, targets)


def validate_control_options(on=None, brightness=None, xy=None, color_temp_kelvin=None):
    """Validate service values in full before dispatching any target."""
    if on is not None and not isinstance(on, bool):
        raise ServiceValidationError("Ein/Aus muss ein Wahrheitswert sein.")
    if brightness is not None and (type(brightness) is not int or not 1 <= brightness <= 255):
        raise ServiceValidationError("Die Helligkeit muss zwischen 1 und 255 liegen.")
    if xy is not None and (
        not isinstance(xy, (list, tuple))
        or len(xy) != 2
        or any(
            type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1
            for value in xy
        )
    ):
        raise ServiceValidationError("Die XY-Farbe muss zwei Werte zwischen 0 und 1 enthalten.")
    if color_temp_kelvin is not None and (
        type(color_temp_kelvin) is not int or color_temp_kelvin <= 0
    ):
        raise ServiceValidationError("Die Farbtemperatur muss positiv sein.")
    if xy is not None and color_temp_kelvin is not None:
        raise ServiceValidationError("Bitte nur Farbe oder Farbtemperatur auswählen.")
    if on is False and any(value is not None for value in (brightness, xy, color_temp_kelvin)):
        raise ServiceValidationError("Ausschalten kann nicht mit Farbwerten kombiniert werden.")


def check_execution_guard(guard):
    """Fail closed when a supplied execution or dispatch condition no longer holds."""
    if guard is not None and not guard():
        raise ServiceValidationError("Die Bedingungen des Zeitplans sind nicht mehr erfüllt.")


def validate_transition(transition):
    """Schedule overrides are finite seconds; None retains the existing default."""
    if transition is not None and (
        type(transition) not in (int, float)
        or not math.isfinite(transition)
        or not 0 <= transition <= 1800
    ):
        raise ServiceValidationError("Der Übergang muss zwischen 0 und 1800 Sekunden liegen.")


def light_service_data(
    state: State, on=None, brightness=None, xy=None, color_temp_kelvin=None, *, transition=None
):
    """Build a safe native payload; switch and on/off lamps never get color values."""
    params = {"entity_id": state.entity_id}
    if (
        transition is not None
        and state.domain == "light"
        and state.attributes.get("supported_features", 0) & LightEntityFeature.TRANSITION
    ):
        params["transition"] = transition
    if on is False:
        return "turn_off", params
    if state.domain == "switch":
        return ("turn_on", params) if on is True else None
    modes = set(state.attributes.get("supported_color_modes") or [])
    if brightness is not None and modes - {"onoff", "unknown"}:
        params["brightness"] = brightness
    if xy is not None:
        if modes & COLOR_MODES:
            params["xy_color"] = list(xy)
        elif "color_temp" in modes:
            color_temp_kelvin = find_closest_ct_match(*xy)
    if color_temp_kelvin is not None and "color_temp" in modes:
        minimum = state.attributes.get("min_color_temp_kelvin") or 2000
        maximum = state.attributes.get("max_color_temp_kelvin") or 6500
        params["color_temp_kelvin"] = max(minimum, min(maximum, color_temp_kelvin))
    return ("turn_on", params) if on is True or len(params) > 1 else None


async def async_dispatch(hass, calls, skipped=None, context=None, guard=None):
    """Start all prepared calls together and isolate individual device failures."""
    result = {"applied": [], "skipped": list(skipped or [])}
    not_allowed = object()

    async def dispatch(domain, service, params):
        # gather schedules children later: revalidate at that final boundary.
        if guard is not None and not guard(params["entity_id"]):
            return not_allowed
        return await hass.services.async_call(
            domain, service, params, blocking=True, context=context
        )

    outcomes = await asyncio.gather(
        *(dispatch(domain, service, params) for domain, service, params in calls),
        return_exceptions=True,
    )
    for (_, _, params), outcome in zip(calls, outcomes, strict=True):
        key = (
            "skipped"
            if outcome is not_allowed
            else "failed"
            if isinstance(outcome, BaseException)
            else "applied"
        )
        result.setdefault(key, []).append(params["entity_id"])
    return result


async def async_set_light(
    hass: HomeAssistant,
    store: LichtzentraleStore,
    entity_id: str,
    on: bool | None = None,
    brightness: int | None = None,
    xy=None,
    color_temp_kelvin: int | None = None,
    context: Context | None = None,
) -> dict:
    """Set one explicitly approved lighting entity."""
    validate_control_options(on, brightness, xy, color_temp_kelvin)
    validate_lights(hass, [entity_id])
    if entity_id not in store.data["settings"]["light_entity_ids"]:
        raise ServiceValidationError("Bitte die Lampe zuerst freigeben.")
    state = hass.states.get(entity_id)
    payload = light_service_data(state, on, brightness, xy, color_temp_kelvin)
    if state.state in {"unknown", "unavailable"} or payload is None:
        return {"applied": [], "skipped": [entity_id]}
    if on is False:
        captured = await store.async_remember_light_states([entity_id])
        # Do not switch off using a snapshot invalidated while storage yielded.
        if hass.states.get(entity_id) is not captured[entity_id]:
            return {"applied": [], "skipped": [entity_id]}

    def still_allowed(target):
        if target not in store.data["settings"]["light_entity_ids"]:
            return False
        try:
            validate_lights(hass, [target])
        except ServiceValidationError:
            return False
        return hass.states.get(target) is state

    return await async_dispatch(
        hass, [(state.domain, *payload)], context=context, guard=still_allowed
    )


async def async_toggle_room(
    hass, store, area_id, on=None, context=None, *, transition=None, guard=None, dispatch_guard=None
):
    from asyncio import Lock

    locks = hass.data.setdefault(DOMAIN, {}).setdefault("scene_locks", {})
    async with locks.setdefault(area_id, Lock()):
        return await _toggle_room(
            hass, store, area_id, on, context, transition=transition, guard=guard, dispatch_guard=dispatch_guard
        )


def _remember_light(state):
    """Capture native light values and only the on/off state for switches."""
    from homeassistant.util.color import color_hs_to_xy, color_RGB_to_xy

    value = {"on": state.state == "on"}
    if state.domain == "switch" or not value["on"]:
        return value
    attrs = state.attributes
    brightness = attrs.get("brightness")
    if type(brightness) is int and 1 <= brightness <= 255:
        value["brightness"] = brightness
    mode = attrs.get("color_mode")
    kelvin = attrs.get("color_temp_kelvin")
    if mode == "color_temp" and type(kelvin) is int and kelvin > 0:
        value["color_temp_kelvin"] = kelvin
    elif mode in COLOR_MODES:
        xy = attrs.get("xy_color")
        if xy is None and attrs.get("rgb_color"):
            xy = color_RGB_to_xy(*attrs["rgb_color"])
        if xy is None and attrs.get("hs_color"):
            xy = color_hs_to_xy(*attrs["hs_color"])
        if xy is not None:
            try:
                validate_control_options(xy=xy)
            except ServiceValidationError:
                pass
            else:
                value["xy"] = list(xy)
    return value


async def _toggle_room(
    hass, store, area_id, on=None, context=None, *, transition=None, guard=None, dispatch_guard=None
):
    """Restore pre-off members or AL targets; switch-only rooms toggle directly."""
    check_execution_guard(guard)
    validate_control_options(on=on)
    validate_transition(transition)
    room_targets(hass, store, area_id)
    from .dynamic_scenes import stop_dynamic

    await stop_dynamic(hass, area_id)
    # Cancelling a loop can yield; do not retain grants or registry membership.
    targets = room_targets(hass, store, area_id)
    states = [hass.states.get(entity_id) for entity_id in targets]
    light_states = [state for state in states if state.domain == "light"]
    switch_only = not light_states
    if on is None:
        on = not any(state.state == "on" for state in (light_states or states))
    brightness_manager = hass.data.get(DOMAIN, {}).get("brightness")
    if not on and brightness_manager:
        context = context or Context()
        brightness_manager.begin_room_off(area_id, context)
    settings = store.data["rooms"].get(area_id, {})
    default = settings.get("default_on", "last")
    if on and default not in {"adaptive", "last"}:
        from .scenes import async_apply_scene_locked

        if not any(s["id"] == default and s["area_id"] == area_id for s in store.data["scenes"]):
            raise ServiceValidationError("Die Einschalt-Szene dieses Raums wurde nicht gefunden.")
        result = await async_apply_scene_locked(hass, store, default, context, transition=transition, dispatch_guard=dispatch_guard)
        if result["applied"] and not result.get("failed") and settings.get("pre_off_pending"):
            await store.async_update_room(area_id, {"pre_off_pending": []})
        return result
    if on and default == "adaptive":
        from .adaptive import async_turn_on_adaptive

        applied = await async_turn_on_adaptive(hass, store, area_id, context=context, transition=transition, dispatch_guard=dispatch_guard)
        if applied and settings.get("pre_off_pending"):
            await store.async_update_room(area_id, {"pre_off_pending": []})
        return {"applied": applied, "skipped": [e for e in targets if e not in applied]}
    captured = {state.entity_id: state for state in states}
    if not on:
        snapshot = {
            state.entity_id: _remember_light(state)
            for state in states
            if state.state in {"on", "off"}
        }
        # A partial failure keeps the same off cycle across retries/reloads.
        # Only merge currently-on values: already switched-off lamps retain their
        # original on state. A successful off or explicit room-on ends the cycle.
        pending = settings.get("pre_off_pending", [])
        if pending:
            snapshot = {
                **settings.get("pre_off_lights", {}),
                **{entity: value for entity, value in snapshot.items() if value["on"]},
            }
        # Repeated all-off calls preserve the last useful snapshot.
        if any(value["on"] for value in snapshot.values()):
            await store.async_update_room(
                area_id,
                {
                    "pre_off_lights": snapshot,
                    "pre_off_pending": [
                        entity for entity, value in snapshot.items() if value["on"]
                    ],
                },
            )
        # Persistence yields too. Recheck approval, area and device eligibility.
        targets = room_targets(hass, store, area_id)
        states = [hass.states.get(entity_id) for entity_id in targets]
    saved = settings.get("pre_off_lights", {})
    calls, skipped, prepared = [], [], {}
    for state in states:
        value = saved.get(state.entity_id, {}) if isinstance(saved, dict) else {}
        if state.state not in {"on", "off"} or (
            not on and state is not captured.get(state.entity_id)
        ) or (
            on and not switch_only and value.get("on") is not True
        ):
            skipped.append(state.entity_id)
            continue
        options = (
            {key: value[key] for key in ("brightness", "xy", "color_temp_kelvin") if key in value}
            if on and state.domain == "light"
            else {}
        )
        try:
            validate_control_options(on=on, **options)
        except ServiceValidationError:
            skipped.append(state.entity_id)
            continue
        calls.append((state.domain, *light_service_data(state, on=on, transition=transition, **options)))
        prepared[state.entity_id] = state

    def still_allowed(entity_id):
        check_execution_guard(dispatch_guard)
        if (
            entity_id not in store.data["settings"]["light_entity_ids"]
            or entity_area_id(hass, entity_id) != area_id
        ):
            return False
        try:
            validate_lights(hass, [entity_id])
        except ServiceValidationError:
            return False
        return hass.states.get(entity_id) is prepared[entity_id]

    result = await async_dispatch(hass, calls, skipped, context, guard=still_allowed)
    if on and result["applied"] and settings.get("pre_off_pending"):
        await store.async_update_room(area_id, {"pre_off_pending": []})
    if not on and store.data["rooms"].get(area_id, {}).get("pre_off_pending"):
        await store.async_update_room(
            area_id,
            {
                "pre_off_pending": [
                    entity
                    for entity in store.data["rooms"][area_id]["pre_off_pending"]
                    if entity in result.get("failed", []) or entity in result["skipped"]
                ]
            },
        )
    if not on and brightness_manager and not result.get("failed") and not result["skipped"]:
        brightness_manager.room_off(area_id)
    return result


async def async_room_brightness(hass, store, area_id, brightness, context=None):
    """Adjust currently-on dimmable lamps, preserving switches and off lamps."""
    validate_control_options(brightness=brightness)
    targets = room_targets(hass, store, area_id)
    calls, skipped = [], []
    for entity_id in targets:
        state = hass.states.get(entity_id)
        payload = light_service_data(state, brightness=brightness)
        if state.state != "on" or payload is None:
            skipped.append(entity_id)
        else:
            calls.append((state.domain, *payload))
    return await async_dispatch(hass, calls, skipped, context)
