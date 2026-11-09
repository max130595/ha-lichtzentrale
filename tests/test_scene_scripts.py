# Geändert für Lichtzentrale
"""Synthetic scripts: strict selection, runtime failures, authenticated discovery."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.lichtzentrale.const import DOMAIN
from custom_components.lichtzentrale.scene_scripts import (
    async_run_start_script,
    list_scripts,
    validate_start_script,
)
from custom_components.lichtzentrale.websocket_api import async_setup_websocket_api


@pytest.mark.parametrize("value", ["", "script.missing", "light.synthetic", "script.", "script.a,b", [], 1, True])
async def test_reject_nonexistent_or_invalid_script(hass, value):
    hass.states.async_set("light.synthetic", "on")
    with pytest.raises(ServiceValidationError):
        validate_start_script(hass, value)


async def test_optional_and_existing_unavailable_script(hass):
    assert validate_start_script(hass, None) is None
    hass.states.async_set("script.synthetic", "unavailable")
    assert validate_start_script(hass, "script.synthetic") == "script.synthetic"


async def test_script_discovery_has_no_script_contents(hass):
    hass.states.async_set("script.synthetic_b", "off", {"friendly_name": "Beta", "sequence": ["private"]})
    hass.states.async_set("script.synthetic_a", "unavailable", {"friendly_name": "Alpha"})
    hass.states.async_set("light.synthetic", "on")
    assert list_scripts(hass) == [
        {"entity_id": "script.synthetic_a", "name": "Alpha", "available": False},
        {"entity_id": "script.synthetic_b", "name": "Beta", "available": True},
    ]


async def test_single_script_dispatch_uses_independent_context(hass):
    hass.states.async_set("script.synthetic", "off")
    context = Context()
    with patch.object(type(hass.services), "async_call", new_callable=AsyncMock) as call:
        assert await async_run_start_script(hass, "script.synthetic", context)
        call.assert_awaited_once()
        assert call.call_args.args == ("script", "turn_on", {"entity_id": "script.synthetic"})
        child = call.call_args.kwargs["context"]
        assert child.id != context.id
        assert child.parent_id is None
        assert child.user_id == context.user_id
        assert call.call_args.kwargs["blocking"] is True


@pytest.mark.parametrize("state", [None, "unavailable", "unknown"])
async def test_missing_or_unavailable_runtime_script_only_logs(hass, state, caplog):
    if state is not None:
        hass.states.async_set("script.synthetic", state)
    with patch.object(type(hass.services), "async_call", new_callable=AsyncMock) as call:
        assert not await async_run_start_script(hass, "script.synthetic")
        call.assert_not_awaited()
    assert "die Lichtszene läuft weiter" in caplog.text


@pytest.mark.parametrize("error", [HomeAssistantError("synthetic failure"), RuntimeError("synthetic failure")])
async def test_script_failure_does_not_escape(hass, caplog, error):
    hass.states.async_set("script.synthetic", "off")
    with patch.object(type(hass.services), "async_call", AsyncMock(side_effect=error)):
        assert not await async_run_start_script(hass, "script.synthetic")
    assert "die Lichtszene läuft weiter" in caplog.text


async def test_script_cancellation_is_not_swallowed(hass):
    hass.states.async_set("script.synthetic", "off")
    with patch.object(type(hass.services), "async_call", AsyncMock(side_effect=asyncio.CancelledError)):
        with pytest.raises(asyncio.CancelledError):
            await async_run_start_script(hass, "script.synthetic")


async def test_unset_script_does_not_dispatch(hass):
    with patch.object(type(hass.services), "async_call", new_callable=AsyncMock) as call:
        assert not await async_run_start_script(hass, None)
        call.assert_not_awaited()


async def test_scripts_websocket_list(hass, hass_ws_client, store):
    hass.data[DOMAIN] = {"store": store}
    hass.states.async_set("script.synthetic", "off", {"friendly_name": "Synthetic script"})
    client = await hass_ws_client(hass)
    async_setup_websocket_api(hass)
    await client.send_json_auto_id({"type": "lichtzentrale/scripts/list"})
    result = await client.receive_json()
    assert result["success"]
    assert result["result"] == [{"entity_id": "script.synthetic", "name": "Synthetic script", "available": True}]


async def test_scripts_websocket_requires_admin(hass, hass_ws_client, hass_read_only_access_token, store):
    hass.data[DOMAIN] = {"store": store}
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    async_setup_websocket_api(hass)
    await client.send_json_auto_id({"type": "lichtzentrale/scripts/list"})
    result = await client.receive_json()
    assert not result["success"]
    assert result["error"]["code"] == "unauthorized"
