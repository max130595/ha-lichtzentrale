# Geändert für Lichtzentrale
"""Authenticated panel API adapted from hass-scene_presets websocket setup."""

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .lights import list_lights, validate_lights
from .palettes import async_apply_palette, list_palettes
from .storage import LichtzentraleStore

LIGHT_IDS = vol.All(cv.ensure_list, [cv.entity_id], vol.Length(max=500))
APPLY_FIELDS = {
    vol.Required("palette_id"): cv.string,
    vol.Required("entity_ids"): vol.All(LIGHT_IDS, vol.Length(min=1)),
    vol.Optional("brightness"): vol.All(vol.Coerce(int), vol.Range(min=1, max=255)),
    vol.Optional("transition", default=1): vol.All(vol.Coerce(float), vol.Range(min=0, max=60)),
}


@callback
def get_store(hass: HomeAssistant) -> LichtzentraleStore:
    """Fail cleanly for old panel tabs after entry unload."""
    if (store := hass.data.get(DOMAIN, {}).get("store")) is None:
        raise HomeAssistantError("Lichtzentrale ist nicht geladen.")
    return store


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/palettes/list"})
@websocket_api.require_admin
@callback
def ws_palettes(hass, connection, msg):
    """Return the catalogue only when the integration is loaded."""
    try:
        get_store(hass)
        connection.send_result(msg["id"], list_palettes())
    except HomeAssistantError as error:
        connection.send_error(msg["id"], "not_ready", str(error))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/lights/list"})
@websocket_api.require_admin
@callback
def ws_lights(hass, connection, msg):
    """Return runtime-discovered lights with server-side allowlist flags."""
    try:
        allowed = get_store(hass).data["settings"]["light_entity_ids"]
        connection.send_result(msg["id"], list_lights(hass, allowed))
    except HomeAssistantError as error:
        connection.send_error(msg["id"], "not_ready", str(error))


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/settings/save",
        vol.Required("light_entity_ids"): LIGHT_IDS,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_settings(hass, connection, msg):
    """Persist only explicitly granted individual lamps."""
    try:
        store = get_store(hass)
        entity_ids = validate_lights(hass, msg["light_entity_ids"])
        await store.async_set_lights(entity_ids)
        connection.send_result(msg["id"], {"light_entity_ids": entity_ids})
    except HomeAssistantError as error:
        connection.send_error(msg["id"], "invalid_request", str(error))


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/palette/apply",
        **APPLY_FIELDS,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_apply(hass, connection, msg):
    """Apply a palette and report unavailable/unsupported lamps separately."""
    try:
        result = await async_apply_palette(
            hass,
            get_store(hass),
            msg["palette_id"],
            msg["entity_ids"],
            msg.get("brightness"),
            msg["transition"],
            connection.context(msg),
        )
        connection.send_result(msg["id"], result)
    except HomeAssistantError as error:
        connection.send_error(msg["id"], "apply_failed", str(error))


@callback
def async_setup_websocket_api(hass: HomeAssistant) -> None:
    """Register once; handlers look up the current store after every reload."""
    for handler in (ws_palettes, ws_lights, ws_settings, ws_apply):
        websocket_api.async_register_command(hass, handler)
