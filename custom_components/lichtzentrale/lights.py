"""Discover individual lamps from registries, without private identifiers."""

from homeassistant.core import HomeAssistant, State, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er


@callback
def is_individual_light(hass: HomeAssistant, state: State) -> bool:
    """Reject all non-light domains and known group lights (including Hue)."""
    if state.domain != "light":
        return False
    attributes = state.attributes
    if attributes.get("is_hue_group") or "entity_id" in attributes:
        return False
    entry = er.async_get(hass).async_get(state.entity_id)
    if entry and (
        entry.platform == "group"
        or entry.translation_key == "hue_grouped_light"
        or entry.disabled_by is not None
    ):
        return False
    return True


@callback
def validate_lights(hass: HomeAssistant, entity_ids: list[str]) -> list[str]:
    """Validate all targets before any mutation or light service call."""
    result = list(dict.fromkeys(entity_ids))
    for entity_id in result:
        state = hass.states.get(entity_id)
        if state is None or not is_individual_light(hass, state):
            raise ServiceValidationError(
                "Nur vorhandene Einzellampen der Domain light sind erlaubt."
            )
    return result


@callback
def list_lights(hass: HomeAssistant, allowed: list[str]) -> list[dict]:
    """Resolve an entity's area first, falling back to its device's area."""
    entities = er.async_get(hass)
    devices = dr.async_get(hass)
    areas = ar.async_get(hass)
    result = []
    for state in hass.states.async_all("light"):
        if not is_individual_light(hass, state):
            continue
        area_id = None
        if entry := entities.async_get(state.entity_id):
            area_id = entry.area_id
            if area_id is None and entry.device_id:
                if device := devices.async_get(entry.device_id):
                    area_id = device.area_id
        area = areas.async_get_area(area_id) if area_id else None
        result.append(
            {
                "entity_id": state.entity_id,
                "name": state.name,
                "area_id": area_id,
                "area_name": area.name if area else None,
                "available": state.state not in {"unavailable", "unknown"},
                "allowed": state.entity_id in allowed,
            }
        )
    return sorted(result, key=lambda item: (item["area_name"] or "", item["name"]))
