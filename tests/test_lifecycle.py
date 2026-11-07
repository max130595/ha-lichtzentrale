# Geändert für Lichtzentrale
"""Real HA setup, local panel registration, reload and removal."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components import websocket_api
from homeassistant.components.frontend import DATA_PANELS
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError, Unauthorized
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lichtzentrale import async_remove_entry, async_setup_entry
from custom_components.lichtzentrale.const import DOMAIN, STORAGE_KEY


async def test_setup_unload_reload_remove(hass, hass_storage):
    assert await async_setup_component(hass, "frontend", {})
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    with (
        patch.object(
            hass.http, "async_register_static_paths", wraps=hass.http.async_register_static_paths
        ) as register,
        patch.object(
            websocket_api, "async_register_command", wraps=websocket_api.async_register_command
        ) as register_command,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert register.call_count == 1
        assert hass.data[DATA_PANELS][DOMAIN].require_admin is True
        assert hass.services.has_service(DOMAIN, "apply_palette")
        assert hass.services.has_service(DOMAIN, "apply_scene")
        assert hass.services.has_service(DOMAIN, "toggle_room")
        assert hass.services.has_service(DOMAIN, "next_scene")
        assert "bindings" in hass.data[DOMAIN]
        await hass.data[DOMAIN]["store"].async_set_lights(["light.fixture_a"])
        original_store = hass.data[DOMAIN]["store"]
        command_calls = register_command.call_count
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert register.call_count == 1
        assert register_command.call_count == command_calls
        assert hass.data[DOMAIN]["store"] is not original_store
        assert hass.data[DOMAIN]["store"].data["settings"]["light_entity_ids"] == [
            "light.fixture_a"
        ]
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert DOMAIN not in hass.data[DATA_PANELS]
        assert not hass.services.has_service(DOMAIN, "apply_palette")
        assert not hass.services.has_service(DOMAIN, "apply_scene")
        assert not hass.services.has_service(DOMAIN, "toggle_room")
        assert not hass.services.has_service(DOMAIN, "next_scene")
        assert "bindings" not in hass.data[DOMAIN]
        assert "store" not in hass.data[DOMAIN]
        assert STORAGE_KEY in hass_storage
        await async_remove_entry(hass, entry)
        assert STORAGE_KEY not in hass_storage


async def test_admin_service_authorization_and_response(
    hass, hass_admin_user, hass_read_only_user, light_calls
):
    """Automation service uses HA admin guard and forwards verified lamp targets."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    hass.states.async_set("light.fixture_a", "on", {"supported_color_modes": ["xy"]})
    await hass.data[DOMAIN]["store"].async_set_lights(["light.fixture_a"])
    params = {"palette_id": "kupfernest", "entity_ids": ["light.fixture_a"]}
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            "apply_palette",
            params,
            blocking=True,
            context=Context(user_id=hass_read_only_user.id),
            return_response=True,
        )
    assert not light_calls
    result = await hass.services.async_call(
        DOMAIN,
        "apply_palette",
        params,
        blocking=True,
        context=Context(user_id=hass_admin_user.id),
        return_response=True,
    )
    assert result == {"applied": ["light.fixture_a"], "skipped": []}
    assert len(light_calls) == 1


async def test_panel_setup_failure_does_not_expose_partial_runtime(hass, hass_storage):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN)
    with patch(
        "custom_components.lichtzentrale.async_setup_view",
        AsyncMock(side_effect=HomeAssistantError("synthetic panel failure")),
    ):
        with pytest.raises(HomeAssistantError):
            await async_setup_entry(hass, entry)
    assert "store" not in hass.data[DOMAIN]
    assert not hass.services.has_service(DOMAIN, "apply_palette")
    assert STORAGE_KEY in hass_storage


async def test_storage_load_failure_does_not_register_panel_or_service(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN)
    with (
        patch(
            "custom_components.lichtzentrale.LichtzentraleStore.async_load",
            AsyncMock(side_effect=HomeAssistantError("synthetic storage failure")),
        ),
        patch("custom_components.lichtzentrale.async_setup_view", AsyncMock()) as panel,
    ):
        with pytest.raises(HomeAssistantError):
            await async_setup_entry(hass, entry)
    panel.assert_not_awaited()
    assert "store" not in hass.data[DOMAIN]
    assert not hass.services.has_service(DOMAIN, "apply_palette")
