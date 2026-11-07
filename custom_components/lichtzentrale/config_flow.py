# Geändert für Lichtzentrale
"""Single-instance configuration, adapted from hass-scene_presets."""

from homeassistant import config_entries

from .const import DOMAIN, NAME


class LichtzentraleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create a local integration without credentials or external services."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Show an empty confirmation dialog and enforce a single instance."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is None:
            return self.async_show_form(step_id="user")
        return self.async_create_entry(title=NAME, data={})
