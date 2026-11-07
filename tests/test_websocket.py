"""Real authenticated WebSocket protocol and admin authorization."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.lichtzentrale.const import DOMAIN
from custom_components.lichtzentrale.websocket_api import async_setup_websocket_api


@pytest.fixture
async def client(hass, hass_ws_client, store):
    hass.data[DOMAIN] = {"store": store}
    client = await hass_ws_client(hass)
    async_setup_websocket_api(hass)
    return client


async def request(client, command, **kwargs):
    await client.send_json_auto_id({"type": f"lichtzentrale/{command}", **kwargs})
    return await client.receive_json()


async def test_catalogue_discovery_save_and_apply(hass, client, store, light_calls):
    hass.states.async_set("light.fixture_a", "off", {"supported_color_modes": ["xy"]})
    result = await request(client, "palettes/list")
    assert result["success"] is True
    assert len(result["result"]) == 12
    result = await request(client, "lights/list")
    assert result["result"][0]["allowed"] is False
    result = await request(client, "settings/save", light_entity_ids=["light.fixture_a"])
    assert result["success"] is True
    assert store.data["settings"]["light_entity_ids"] == ["light.fixture_a"]
    result = await request(
        client, "palette/apply", palette_id="kupfernest", entity_ids=["light.fixture_a"]
    )
    assert result["result"] == {"applied": ["light.fixture_a"], "skipped": []}
    assert len(light_calls) == 1


@pytest.mark.parametrize(
    "command,kwargs",
    [
        ("palettes/list", {}),
        ("lights/list", {}),
        ("settings/save", {"light_entity_ids": []}),
        ("palette/apply", {"palette_id": "kupfernest", "entity_ids": ["light.fixture_a"]}),
    ],
)
async def test_non_admin_cannot_read_or_write(
    hass, hass_ws_client, hass_read_only_access_token, store, light_calls, command, kwargs
):
    hass.data[DOMAIN] = {"store": store}
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    async_setup_websocket_api(hass)
    result = await request(client, command, **kwargs)
    assert result["success"] is False
    assert result["error"]["code"] == "unauthorized"
    assert store.data["settings"]["light_entity_ids"] == []
    assert not light_calls


@pytest.mark.parametrize("target", ["switch.fixture_a", "lock.fixture_a", "light.fixture_group"])
async def test_rejected_allowlist_does_not_mutate(hass, client, store, target):
    hass.states.async_set(
        target, "on", {"is_hue_group": True} if target.startswith("light.") else {}
    )
    result = await request(client, "settings/save", light_entity_ids=[target])
    assert result["success"] is False
    assert result["error"]["code"] == "invalid_request"
    assert store.data["settings"]["light_entity_ids"] == []


async def test_storage_failure_returns_protocol_error(hass, client, store):
    hass.states.async_set("light.fixture_a", "on")
    with patch.object(
        store._store, "async_save", AsyncMock(side_effect=HomeAssistantError("storage unavailable"))
    ):
        result = await request(client, "settings/save", light_entity_ids=["light.fixture_a"])
    assert result["success"] is False
    assert result["error"]["code"] == "invalid_request"
    assert store.data["settings"]["light_entity_ids"] == []


async def test_unloaded_integration_returns_not_ready(hass, client):
    hass.data[DOMAIN].pop("store")
    result = await request(client, "palettes/list")
    assert result["error"]["code"] == "not_ready"


@pytest.mark.parametrize(
    "field,value", [("brightness", 0), ("brightness", 256), ("transition", -1), ("transition", 61)]
)
async def test_protocol_schema_rejects_invalid_options(client, light_calls, field, value):
    result = await request(
        client,
        "palette/apply",
        palette_id="kupfernest",
        entity_ids=["light.fixture_a"],
        **{field: value},
    )
    assert result["success"] is False
    assert result["error"]["code"] == "invalid_format"
    assert not light_calls


async def test_unloaded_discovery_returns_not_ready(hass, client):
    hass.data[DOMAIN].pop("store")
    result = await request(client, "lights/list")
    assert result["success"] is False
    assert result["error"]["code"] == "not_ready"


async def test_unapproved_apply_returns_error_without_service_calls(hass, client, light_calls):
    hass.states.async_set("light.fixture_a", "on", {"supported_color_modes": ["xy"]})
    result = await request(
        client, "palette/apply", palette_id="kupfernest", entity_ids=["light.fixture_a"]
    )
    assert result["success"] is False
    assert result["error"]["code"] == "apply_failed"
    assert not light_calls
