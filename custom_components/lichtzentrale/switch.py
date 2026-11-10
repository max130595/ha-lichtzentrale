# Geändert für Lichtzentrale
"""Explicit dashboard switch for the manually activated vacation simulation."""
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, NAME, VERSION
from .vacation_api import get_vacation


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([VacationSwitch(hass)])


class VacationSwitch(SwitchEntity):
    _attr_name = "Urlaubsmodus"
    _attr_has_entity_name = True
    _attr_unique_id = "lichtzentrale_urlaubsmodus"
    _attr_icon = "mdi:palm-tree"
    _attr_should_poll = False

    def __init__(self, hass):
        self.hass = hass
        self.entity_id = "switch.lichtzentrale_urlaubsmodus"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, DOMAIN)}, name=NAME,
                                            manufacturer=NAME, model="Lokale Lichtsteuerung", sw_version=VERSION)

    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(
            self.hass, f"{DOMAIN}_vacation_updated", self.async_write_ha_state))

    @property
    def available(self):
        manager = self.hass.data.get(DOMAIN, {}).get("vacation")
        return manager is not None and not manager.closed

    @property
    def is_on(self):
        return bool(get_vacation(self.hass).status()["enabled"])

    @property
    def extra_state_attributes(self):
        status = get_vacation(self.hass).status()
        return {key: status.get(key) for key in ("until", "testing", "next_switch")}

    async def async_turn_on(self, **kwargs):
        await get_vacation(self.hass).async_set_enabled(True, context=self._context)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        await get_vacation(self.hass).async_set_enabled(False, context=self._context)
        self.async_write_ha_state()
