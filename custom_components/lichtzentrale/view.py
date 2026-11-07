# Geändert für Lichtzentrale
"""Register the local panel, adapted from hass-scene_presets/view.py."""

from pathlib import Path

from homeassistant.components.frontend import (
    async_register_built_in_panel,
    async_remove_panel,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN, NAME, PANEL_URL, VERSION


async def async_setup_view(hass: HomeAssistant) -> None:
    """Register the immutable bundle route once, including after entry reload."""
    runtime = hass.data[DOMAIN]
    if not runtime.get("static_registered"):
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    PANEL_URL,
                    str(Path(__file__).parent / "frontend" / "lichtzentrale_panel.js"),
                    True,
                )
            ]
        )
        runtime["static_registered"] = True
    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title=NAME,
        sidebar_icon="mdi:lightbulb-group",
        frontend_url_path=DOMAIN,
        require_admin=True,
        config={
            "_panel_custom": {
                "name": "lichtzentrale-panel",
                "module_url": f"{PANEL_URL}?v={VERSION}",
            }
        },
    )


async def async_remove_view(hass: HomeAssistant) -> None:
    """Remove the sidebar entry without duplicating HTTP routes on reload."""
    async_remove_panel(hass, DOMAIN)
