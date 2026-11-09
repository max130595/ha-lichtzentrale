# Geändert für Lichtzentrale
"""Thin, authenticated vacation commands and runtime notification discovery."""
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN


def get_vacation(hass):
    manager = hass.data.get(DOMAIN, {}).get("vacation")
    if manager is None or manager.closed:
        raise HomeAssistantError("Lichtzentrale ist nicht geladen.")
    return manager


def list_notify_services(hass):
    """Offer named services only; generic notify.send_message also needs a target."""
    return [{"service": f"notify.{name}", "name": name.replace("_", " ")}
            for name in sorted(hass.services.async_services().get("notify", {}))
            if name != "send_message"]


async def vacation_get(hass, store, msg, context):
    return get_vacation(hass).status()


async def vacation_save(hass, store, msg, context):
    options = {"until": msg["until"]} if "until" in msg else {}
    return await get_vacation(hass).async_save_config(msg["config"], **options)


async def vacation_set(hass, store, msg, context):
    options = {"until": msg["until"]} if "until" in msg else {}
    return await get_vacation(hass).async_set_enabled(msg["enabled"], context=context, **options)


async def vacation_test(hass, store, msg, context):
    return await get_vacation(hass).async_test(context=context)


async def vacation_notify_services(hass, store, msg, context):
    return list_notify_services(hass)
