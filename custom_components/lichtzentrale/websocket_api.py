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
from .positions import DISTRIBUTIONS
from .rooms import async_room_brightness, async_set_light, async_toggle_room, list_rooms
from .scenes import (
    async_apply_scene,
    async_delete_scene,
    async_reorder_scenes,
    async_save_scene,
    async_snapshot,
    list_hue_scenes,
    list_scenes,
)
from .storage import LichtzentraleStore

LIGHT_IDS = vol.All(cv.ensure_list, [cv.entity_id], vol.Length(max=500))
APPLY_FIELDS = {
    vol.Required("palette_id"): cv.string,
    vol.Required("entity_ids"): vol.All(LIGHT_IDS, vol.Length(min=1)),
    vol.Optional("brightness"): vol.All(vol.Coerce(int), vol.Range(min=1, max=255)),
    vol.Optional("transition", default=1): vol.All(vol.Coerce(float), vol.Range(min=0, max=60)),
    vol.Optional("verteilung", default="zufall"): vol.In(DISTRIBUTIONS),
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


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/lights/list",
        vol.Optional("include_hidden", default=False): bool,
    }
)
@websocket_api.require_admin
@callback
def ws_lights(hass, connection, msg):
    """Return runtime-discovered lights with server-side allowlist flags."""
    try:
        allowed = get_store(hass).data["settings"]["light_entity_ids"]
        connection.send_result(msg["id"], list_lights(hass, allowed, msg["include_hidden"]))
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
            verteilung=msg["verteilung"],
        )
        connection.send_result(msg["id"], result)
    except HomeAssistantError as error:
        connection.send_error(msg["id"], "apply_failed", str(error))


@callback
def async_setup_websocket_api(hass: HomeAssistant) -> None:
    """Register once; handlers look up the current store after every reload."""
    for handler in (
        ws_palettes,
        ws_lights,
        ws_settings,
        ws_apply,
        *STAGE_ONE_HANDLERS,
        *STAGE_TWO_HANDLERS,
        *STAGE_THREE_HANDLERS,
        *MOTION_HANDLERS,
        *SCHEDULE_HANDLERS,
    ):
        websocket_api.async_register_command(hass, handler)


# Keep command schemas explicit: unknown fields and non-admin calls never reach a service.
AREA_FIELDS = {vol.Required("area_id"): cv.string}
BRIGHTNESS = vol.All(int, vol.Range(min=1, max=255))
CONTROL_FIELDS = {
    vol.Optional("on"): bool,
    vol.Optional("brightness"): BRIGHTNESS,
    vol.Optional("xy"): vol.All(
        [vol.All(vol.Coerce(float), vol.Range(min=0, max=1))], vol.Length(min=2, max=2)
    ),
    vol.Optional("color_temp_kelvin"): vol.All(int, vol.Range(min=1000, max=40000)),
}


def command(name, fields, handler):
    """Register a uniformly authenticated, guarded async command."""

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/{name}", **fields})
    @websocket_api.require_admin
    @websocket_api.async_response
    async def wrapped(hass, connection, msg):
        try:
            result = await handler(hass, get_store(hass), msg, connection.context(msg))
            connection.send_result(msg["id"], result)
        except HomeAssistantError as error:
            connection.send_error(msg["id"], "invalid_request", str(error))

    return wrapped


async def rooms_list(hass, store, msg, context):
    return list_rooms(hass, store)


async def room_toggle(hass, store, msg, context):
    return await async_toggle_room(hass, store, msg["area_id"], msg.get("on"), context=context)


async def room_brightness(hass, store, msg, context):
    return await async_room_brightness(
        hass, store, msg["area_id"], msg["brightness"], context=context
    )


async def room_position(hass, store, msg, context):
    return await store.async_set_position(msg["area_id"], msg["entity_id"], msg["position"])


async def light_set(hass, store, msg, context):
    return await async_set_light(
        hass,
        store,
        msg["entity_id"],
        context=context,
        **{key: msg[key] for key in ("on", "brightness", "xy", "color_temp_kelvin") if key in msg},
    )


async def scenes_list(hass, store, msg, context):
    return list_scenes(store, msg.get("area_id"), hass)


async def scene_save(hass, store, msg, context):
    return await async_save_scene(hass, store, msg["scene"])


async def scene_delete(hass, store, msg, context):
    await async_delete_scene(store, msg["scene_id"], hass)
    return {}


async def scene_snapshot(hass, store, msg, context):
    return await async_snapshot(hass, store, msg["area_id"], msg["name"])


async def scene_apply(hass, store, msg, context):
    return await async_apply_scene(hass, store, msg["scene_id"], context)


async def scenes_reorder(hass, store, msg, context):
    return await async_reorder_scenes(store, msg["area_id"], msg["scene_ids"])


async def hue_scenes_list(hass, store, msg, context):
    return list_hue_scenes(hass, store, msg.get("area_id"))


STAGE_ONE_HANDLERS = (
    command("rooms/list", {}, rooms_list),
    command("room/toggle", {**AREA_FIELDS, vol.Optional("on"): bool}, room_toggle),
    command(
        "room/position",
        {**AREA_FIELDS, vol.Required("entity_id"): cv.entity_id, vol.Required("position"): vol.Any(None, dict)},
        room_position,
    ),
    command(
        "room/brightness", {**AREA_FIELDS, vol.Required("brightness"): BRIGHTNESS}, room_brightness
    ),
    command("light/set", {vol.Required("entity_id"): cv.entity_id, **CONTROL_FIELDS}, light_set),
    command("scenes/list", {vol.Optional("area_id"): cv.string}, scenes_list),
    command("scene/save", {vol.Required("scene"): dict}, scene_save),
    command("scene/delete", {vol.Required("scene_id"): cv.string}, scene_delete),
    command("scene/snapshot", {**AREA_FIELDS, vol.Required("name"): cv.string}, scene_snapshot),
    command("scene/apply", {vol.Required("scene_id"): cv.string}, scene_apply),
    command(
        "scenes/reorder",
        {**AREA_FIELDS, vol.Required("scene_ids"): vol.All([cv.string], vol.Length(max=500))},
        scenes_reorder,
    ),
    command("hue_scenes/list", {vol.Optional("area_id"): cv.string}, hue_scenes_list),
)


async def dynamic_list(hass, store, msg, context):
    from .dynamic_scenes import manager

    active = manager(hass)
    return active.list() if active else []


async def dynamic_stop(hass, store, msg, context):
    from .dynamic_scenes import async_stop_room

    return await async_stop_room(hass, store, msg["area_id"], context=context)


async def adaptive_status(hass, store, msg, context):
    from .adaptive import status

    return status(hass, store)


async def adaptive_set(hass, store, msg, context):
    from .adaptive import async_set_adaptive

    return await async_set_adaptive(
        hass,
        store,
        msg["area_id"],
        context=context,
        **{k: msg[k] for k in ("enabled", "adaptive_switch", "default_on") if k in msg},
    )


ADAPTIVE_FIELDS = {
    **AREA_FIELDS,
    vol.Optional("enabled"): bool,
    vol.Optional("adaptive_switch"): vol.Any(None, cv.entity_id),
    vol.Optional("default_on"): vol.In(["adaptive", "last"]),
}
STAGE_TWO_HANDLERS = (
    command("dynamic/list", {}, dynamic_list),
    command("dynamic/stop", AREA_FIELDS, dynamic_stop),
    command("adaptive/status", {}, adaptive_status),
    command("adaptive/set", ADAPTIVE_FIELDS, adaptive_set),
)


async def buttons_list(hass, store, msg, context):
    from .bindings import list_buttons

    return list_buttons(hass)


async def bindings_list(hass, store, msg, context):
    data = store.data
    return {"bindings": data["bindings"], "double_click_ms": data["settings"].get("double_click_ms", 500)}


async def binding_save(hass, store, msg, context):
    from .bindings import async_save_binding

    return await async_save_binding(hass, store, msg["binding"])


async def binding_delete(hass, store, msg, context):
    await store.async_delete_binding(msg["binding_id"])
    return {}


async def binding_settings(hass, store, msg, context):
    return await store.async_set_double_click(msg["double_click_ms"])


async def room_settings(hass, store, msg, context):
    return await store.async_set_room_settings(
        msg["area_id"], {key: msg[key] for key in ("cycle", "default_on") if key in msg}
    )


STAGE_THREE_HANDLERS = (
    command("buttons/list", {}, buttons_list),
    command("bindings/list", {}, bindings_list),
    command("binding/save", {vol.Required("binding"): dict}, binding_save),
    command("binding/delete", {vol.Required("binding_id"): cv.string}, binding_delete),
    command(
        "binding/settings",
        {vol.Required("double_click_ms"): vol.All(int, vol.Range(min=200, max=1000))},
        binding_settings,
    ),
    command(
        "room/settings",
        {
            **AREA_FIELDS,
            vol.Optional("cycle"): vol.All([cv.string], vol.Length(max=500)),
            vol.Optional("default_on"): cv.string,
        },
        room_settings,
    ),
)


async def motion_get(hass, store, msg, context):
    from .motion_config import list_lux_sensors, list_motion_sensors

    area_id = msg["area_id"]
    config = store.data["rooms"].get(area_id, {}).get("motion")
    manager = hass.data.get(DOMAIN, {}).get("motion")
    return {
        "config": config,
        "status": manager.status(area_id) if manager else {
            "enabled": bool(config and config.get("enabled")), "paused": False, "active": False,
        },
        "sensors": list_motion_sensors(hass), "lux_sensors": list_lux_sensors(hass),
    }


async def motion_save(hass, store, msg, context):
    await store.async_set_motion(msg["area_id"], msg["config"])
    return await motion_get(hass, store, msg, context)


async def motion_set_enabled(hass, store, msg, context):
    await store.async_set_motion_enabled(msg["area_id"], msg["enabled"])
    return await motion_get(hass, store, msg, context)


MOTION_HANDLERS = (
    command("motion/get", AREA_FIELDS, motion_get),
    command("motion/save", {**AREA_FIELDS, vol.Required("config"): dict}, motion_save),
    command("motion/set_enabled", {**AREA_FIELDS, vol.Required("enabled"): bool}, motion_set_enabled),
)


async def schedules_list(hass, store, msg, context):
    from .motion_config import list_lux_sensors
    from .schedule_config import list_persons

    manager = hass.data.get(DOMAIN, {}).get("schedules")
    return {
        "schedules": manager.list_schedules() if manager else [
            {**item, "next_run": None, "last_error": None} for item in store.data["schedules"]
        ],
        "lux_sensors": list_lux_sensors(hass), "persons": list_persons(hass),
        "time_zone": hass.config.time_zone,
    }


async def schedule_save(hass, store, msg, context):
    await store.async_save_schedule(msg["schedule"])
    return await schedules_list(hass, store, msg, context)


async def schedule_delete(hass, store, msg, context):
    await store.async_delete_schedule(msg["schedule_id"])
    return await schedules_list(hass, store, msg, context)


async def schedule_set_enabled(hass, store, msg, context):
    await store.async_set_schedule_enabled(msg["schedule_id"], msg["enabled"])
    return await schedules_list(hass, store, msg, context)


async def schedule_test(hass, store, msg, context):
    manager = hass.data.get(DOMAIN, {}).get("schedules")
    if manager is None:
        raise HomeAssistantError("Zeitpläne sind nicht geladen.")
    return await manager.async_test(msg["schedule_id"], context)


SCHEDULE_HANDLERS = (
    command("schedules/list", {}, schedules_list),
    command("schedule/save", {vol.Required("schedule"): dict}, schedule_save),
    command("schedule/delete", {vol.Required("schedule_id"): cv.string}, schedule_delete),
    command("schedule/set_enabled", {
        vol.Required("schedule_id"): cv.string, vol.Required("enabled"): bool,
    }, schedule_set_enabled),
    command("schedule/test", {vol.Required("schedule_id"): cv.string}, schedule_test),
)
