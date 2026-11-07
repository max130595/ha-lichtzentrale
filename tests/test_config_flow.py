"""Empty local setup and single-instance enforcement."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lichtzentrale.const import DOMAIN


async def test_user_flow(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    with patch("custom_components.lichtzentrale.async_setup_entry", AsyncMock(return_value=True)):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {}
    assert result["title"] == "Lichtzentrale"
    assert result["result"].unique_id == DOMAIN


@pytest.mark.parametrize("unique_id", [DOMAIN, None])
async def test_single_instance(hass, unique_id):
    MockConfigEntry(domain=DOMAIN, unique_id=unique_id).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] in {"already_configured", "single_instance_allowed"}
