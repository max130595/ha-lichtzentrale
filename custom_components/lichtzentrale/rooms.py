# Geändert für Lichtzentrale
"""Area-backed rooms and explicit, capability-aware lighting controls."""

import asyncio
import math

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
                "on": any(item["on"] for item in members),
                "brightness": round(sum(brightness) / len(brightness)) if brightness else None,
                "available_count": sum(item["available"] for item in members),
                "last_scene_id": store.data["rooms"].get(area.id, {}).get("last_scene_id"),
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


def light_service_data(state: State, on=None, brightness=None, xy=None, color_temp_kelvin=None):
    """Build a safe native payload; switch and on/off lamps never get color values."""
    params = {"entity_id": state.entity_id}
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


async def async_dispatch(hass, calls, skipped=None, context=None):
    """Start all prepared calls together and isolate individual device failures."""
    result = {"applied": [], "skipped": list(skipped or [])}
    outcomes = await asyncio.gather(
        *(
            hass.services.async_call(domain, service, params, blocking=True, context=context)
            for domain, service, params in calls
        ),
        return_exceptions=True,
    )
    for (_, _, params), outcome in zip(calls, outcomes, strict=True):
        key = "failed" if isinstance(outcome, BaseException) else "applied"
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
    return await async_dispatch(hass, [(state.domain, *payload)], context=context)


async def async_toggle_room(hass, store, area_id, on=None, context=None):
    from asyncio import Lock

    locks = hass.data.setdefault(DOMAIN, {}).setdefault("scene_locks", {})
    async with locks.setdefault(area_id, Lock()):
        return await _toggle_room(hass, store, area_id, on, context)


async def _toggle_room(hass, store, area_id, on=None, context=None):
    """Toggle all available approved room lights in parallel."""
    validate_control_options(on=on)
    targets = room_targets(hass, store, area_id)
    from .dynamic_scenes import stop_dynamic

    await stop_dynamic(hass, area_id)
    # Cancelling a loop can yield; do not retain grants or registry membership.
    targets = room_targets(hass, store, area_id)
    states = [hass.states.get(entity_id) for entity_id in targets]
    if on is None:
        on = not any(state.state == "on" for state in states)
    calls, skipped = [], []
    for state in states:
        if state.state in {"unavailable", "unknown"}:
            skipped.append(state.entity_id)
        else:
            calls.append((state.domain, *light_service_data(state, on=on)))
    result = await async_dispatch(hass, calls, skipped, context)
    if on and store.data["rooms"].get(area_id, {}).get("default_on") == "adaptive":
        from .adaptive import async_resume_adaptive

        await async_resume_adaptive(hass, store, area_id, context=context)
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
