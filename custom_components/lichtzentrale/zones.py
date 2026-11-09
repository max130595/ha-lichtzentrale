# Geändert für Lichtzentrale
"""Additive, overlapping groups of explicitly approved lighting entities."""

from copy import deepcopy
from uuid import uuid4

from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar


def zone_id(area_id):
    return area_id[5:] if isinstance(area_id, str) and area_id.startswith("zone:") else None


def get_zone(store, area_id):
    identifier = zone_id(area_id)
    return next((z for z in store.data.get("zones", []) if z["id"] == identifier), None)


def validate_area(hass, store, area_id):
    if not isinstance(area_id, str) or not (
        get_zone(store, area_id) if zone_id(area_id) is not None
        else ar.async_get(hass).async_get_area(area_id)
    ):
        raise ServiceValidationError("Der Raum oder die Zone wurde nicht gefunden.")


def contains(hass, store, area_id, entity_id):
    from .lights import entity_area_id

    if zone_id(area_id) is not None:
        zone = get_zone(store, area_id)
        return bool(zone and entity_id in zone["entity_ids"])
    return entity_area_id(hass, entity_id) == area_id


def validate_zone(hass, store, raw):
    from .selected_lights import validate_selected_lights

    if not isinstance(raw, dict):
        raise ServiceValidationError("Ungültige Zone.")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        raise ServiceValidationError("Bitte einen Zonennamen mit 1 bis 100 Zeichen angeben.")
    identifier = raw.get("id")
    old = None
    if identifier is not None:
        if not isinstance(identifier, str):
            raise ServiceValidationError("Ungültige Zonenkennung.")
        old = get_zone(store, "zone:" + identifier)
        if old is None:
            raise ServiceValidationError("Die Zone wurde inzwischen gelöscht.")
    members = validate_selected_lights(hass, store, raw.get("entity_ids"))
    return {**deepcopy(old or {}), "id": identifier or str(uuid4()), "name": name.strip(), "entity_ids": members}
