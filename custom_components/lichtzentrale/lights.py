# Geändert für Lichtzentrale
"""Discover individual lighting entities using runtime registry metadata."""

import re

from homeassistant.core import HomeAssistant, State, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er


@callback
def is_individual_light(hass: HomeAssistant, state: State) -> bool:
    """Accept individual lights and registered Shelly lighting switches only."""
    if state.domain not in {"light", "switch"}:
        return False
    if state.attributes.get("is_hue_group") or "entity_id" in state.attributes:
        return False
    entry = er.async_get(hass).async_get(state.entity_id)
    if entry and (
        entry.platform == "group"
        or entry.translation_key == "hue_grouped_light"
        or entry.disabled_by is not None
    ):
        return False
    if state.domain == "light":
        return True
    if not entry or entry.platform != "shelly":
        return False
    device = dr.async_get(hass).async_get(entry.device_id) if entry.device_id else None
    names = [state.name, entry.original_name, entry.name]
    if device:
        names.extend([device.name, device.name_by_user])
    # Names are installation metadata, not private entity identifiers. Require a
    # lighting-specific label rather than admitting arbitrary Shelly appliances.
    return any(
        re.search(r"licht|lampe|leuchte|\blights?\b|\blamps?\b", name, re.IGNORECASE)
        for name in names
        if name
    )


@callback
def hidden_by_default(hass: HomeAssistant, entity_id: str) -> bool:
    """Printer chamber lights are opt-in, identified without private IDs."""
    entry = er.async_get(hass).async_get(entity_id)
    if not entry:
        return False
    device = dr.async_get(hass).async_get(entry.device_id) if entry.device_id else None
    metadata = [entry.platform, device.manufacturer if device else None]
    return any("bambu" in value.casefold() for value in metadata if value)


@callback
def entity_area_id(hass: HomeAssistant, entity_id: str) -> str | None:
    """Resolve entity assignment before the device's area."""
    entry = er.async_get(hass).async_get(entity_id)
    if entry:
        if entry.area_id:
            return entry.area_id
        if entry.device_id and (device := dr.async_get(hass).async_get(entry.device_id)):
            return device.area_id
    return None


@callback
def validate_lights(hass: HomeAssistant, entity_ids: list[str]) -> list[str]:
    """Validate the entire selection before any mutation or service call."""
    result = list(dict.fromkeys(entity_ids))
    for entity_id in result:
        state = hass.states.get(entity_id)
        if state is None or not is_individual_light(hass, state):
            raise ServiceValidationError(
                "Nur Einzellampen und Shelly-Schalter für Beleuchtung sind erlaubt."
            )
    return result


@callback
def list_lights(
    hass: HomeAssistant, allowed: list[str], include_hidden: bool = False
) -> list[dict]:
    """List eligible lights, retaining hidden approved entries for revocation."""
    areas = ar.async_get(hass)
    result = []
    for state in hass.states.async_all():
        if not is_individual_light(hass, state):
            continue
        hidden = hidden_by_default(hass, state.entity_id)
        if hidden and not include_hidden and state.entity_id not in allowed:
            continue
        area_id = entity_area_id(hass, state.entity_id)
        area = areas.async_get_area(area_id) if area_id else None
        attributes = state.attributes if state.domain == "light" else {}
        result.append(
            {
                "entity_id": state.entity_id,
                "name": state.name,
                "area_id": area_id,
                "area_name": area.name if area else None,
                "available": state.state not in {"unavailable", "unknown"},
                "allowed": state.entity_id in allowed,
                "domain": state.domain,
                "on": state.state == "on",
                "supported_color_modes": list(attributes.get("supported_color_modes") or []),
                "hidden_by_default": hidden,
                **{
                    key: attributes.get(key)
                    for key in (
                        "brightness",
                        "color_mode",
                        "xy_color",
                        "rgb_color",
                        "color_temp_kelvin",
                        "min_color_temp_kelvin",
                        "max_color_temp_kelvin",
                    )
                },
            }
        )
    return sorted(result, key=lambda item: (item["area_name"] or "", item["name"]))


def color_modes(state):
    """Capabilities, never the uninitialized current Z2M color_mode."""
    if state.domain != "light":
        return set()
    return set(state.attributes.get("supported_color_modes") or []) - {"unknown"}


def clamp_xy(state, xy):
    """Project outside colors onto the actual reported triangle, if available."""
    import math

    point = tuple(xy)
    gamut = state.attributes.get("color_gamut")
    if not isinstance(gamut, (list, tuple)) or len(gamut) != 3:
        return point
    if any(not isinstance(p, (list, tuple)) or len(p) != 2 or any(
        type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1
        for v in p
    ) for p in gamut):
        return point
    a, b, c = gamut
    def cross(u, v, w):
        return (v[0] - u[0]) * (w[1] - u[1]) - (v[1] - u[1]) * (w[0] - u[0])

    if abs(cross(a, b, c)) < 1e-10:
        return point
    signs = [cross(a, b, point), cross(b, c, point), cross(c, a, point)]
    if min(signs) >= -1e-10 or max(signs) <= 1e-10:
        return point
    candidates = []
    for start, end in ((a, b), (b, c), (c, a)):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = dx * dx + dy * dy
        t = max(0, min(1, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length))
        candidates.append((start[0] + t * dx, start[1] + t * dy))
    return min(candidates, key=lambda p: (p[0] - point[0]) ** 2 + (p[1] - point[1]) ** 2)


def supports_payload(state, params):
    """Drop prepared commands when capabilities changed while they were waiting."""
    from homeassistant.components.light import LightEntityFeature

    modes = color_modes(state)
    if state.domain == "switch":
        return set(params) == {"entity_id"}
    if "brightness" in params and not modes - {"onoff"}:
        return False
    if "xy_color" in params and not modes & {"xy", "hs", "rgb", "rgbw", "rgbww"}:
        return False
    if "color_temp_kelvin" in params and "color_temp" not in modes:
        return False
    if "transition" in params and not (
        modes - {"onoff"}
        and state.attributes.get("supported_features", 0) & LightEntityFeature.TRANSITION
    ):
        return False
    return True
