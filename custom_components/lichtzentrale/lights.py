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
