# Geändert für Lichtzentrale
"""Local Lichtzentrale foundation, adapted from hass-scene_presets."""

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service

from .const import DOMAIN, SERVICE_APPLY_PALETTE
from .palettes import async_apply_palette
from .rooms import async_toggle_room
from .scenes import async_apply_scene
from .storage import LichtzentraleStore
from .view import async_remove_view, async_setup_view
from .websocket_api import APPLY_FIELDS, async_setup_websocket_api, get_store

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load storage and set up the local panel and explicit palette action."""
    runtime = hass.data.setdefault(DOMAIN, {})
    store = LichtzentraleStore(hass)
    await store.async_load()
    runtime["store"] = store
    try:
        await async_setup_view(hass)
    except Exception:
        runtime.pop("store", None)
        raise
    if not runtime.get("websocket_registered"):
        async_setup_websocket_api(hass)
        runtime["websocket_registered"] = True

    async def apply_palette_service(call: ServiceCall):
        return await async_apply_palette(
            hass,
            get_store(hass),
            call.data["palette_id"],
            call.data["entity_ids"],
            call.data.get("brightness"),
            call.data["transition"],
            call.context,
        )

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_APPLY_PALETTE,
        apply_palette_service,
        schema=vol.Schema(APPLY_FIELDS),
        supports_response=SupportsResponse.OPTIONAL,
    )

    async def apply_scene_service(call: ServiceCall):
        return await async_apply_scene(hass, get_store(hass), call.data["scene_id"], call.context)

    async def toggle_room_service(call: ServiceCall):
        return await async_toggle_room(
            hass, get_store(hass), call.data["area_id"], call.data.get("on"), context=call.context
        )

    async_register_admin_service(
        hass,
        DOMAIN,
        "apply_scene",
        apply_scene_service,
        schema=vol.Schema({vol.Required("scene_id"): cv.string}),
        supports_response=SupportsResponse.OPTIONAL,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        "toggle_room",
        toggle_room_service,
        schema=vol.Schema({vol.Required("area_id"): cv.string, vol.Optional("on"): cv.boolean}),
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload without removing persisted user settings."""
    await async_remove_view(hass)
    hass.services.async_remove(DOMAIN, SERVICE_APPLY_PALETTE)
    hass.services.async_remove(DOMAIN, "apply_scene")
    hass.services.async_remove(DOMAIN, "toggle_room")
    hass.data[DOMAIN].pop("store", None)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete private stored data only when the integration is removed."""
    await LichtzentraleStore(hass).async_remove()
