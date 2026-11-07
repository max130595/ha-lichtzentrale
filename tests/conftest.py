"""Isolated Home Assistant fixtures with synthetic devices only."""

import pytest
from homeassistant.core import callback

from custom_components.lichtzentrale.storage import LichtzentraleStore


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    """Enable the actual custom integration in Home Assistant's test loader."""


@pytest.fixture
async def store(hass):
    """Create an empty native HA Store backed by the plugin's isolated storage."""
    result = LichtzentraleStore(hass)
    await result.async_load()
    return result


@pytest.fixture
def light_calls(hass):
    """Capture actual HA service dispatch without contacting any devices."""
    calls = []

    @callback
    def capture(call):
        calls.append(call)

    hass.services.async_register("light", "turn_on", capture)
    return calls
