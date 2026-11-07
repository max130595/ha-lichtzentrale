"""Registry-backed runtime discovery, room precedence, and group rejection."""

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lichtzentrale.lights import list_lights, validate_lights


@pytest.mark.parametrize(
    "attributes", [{"is_hue_group": True}, {"entity_id": ["light.fixture_member"]}]
)
async def test_group_attributes_rejected(hass, attributes):
    hass.states.async_set("light.fixture_group", "on", attributes)
    assert list_lights(hass, []) == []
    with pytest.raises(ServiceValidationError):
        validate_lights(hass, ["light.fixture_group"])


@pytest.mark.parametrize(
    "platform,translation_key,disabled",
    [
        ("group", None, None),
        ("hue", "hue_grouped_light", None),
        ("synthetic", None, er.RegistryEntryDisabler.USER),
    ],
)
async def test_registry_groups_and_disabled_entities_rejected(
    hass, platform, translation_key, disabled
):
    entry = er.async_get(hass).async_get_or_create(
        "light",
        platform,
        "synthetic-id",
        suggested_object_id="fixture_group",
        translation_key=translation_key,
        disabled_by=disabled,
    )
    hass.states.async_set(entry.entity_id, "on")
    assert list_lights(hass, []) == []
    with pytest.raises(ServiceValidationError):
        validate_lights(hass, [entry.entity_id])


async def test_entity_area_overrides_device_then_falls_back(hass):
    config_entry = MockConfigEntry(domain="synthetic")
    config_entry.add_to_hass(hass)
    areas = ar.async_get(hass)
    direct_area = areas.async_create("Fixture direct area")
    device_area = areas.async_create("Fixture device area")
    devices = dr.async_get(hass)
    device = devices.async_get_or_create(
        config_entry_id=config_entry.entry_id, identifiers={("synthetic", "fixture-device")}
    )
    devices.async_update_device(device.id, area_id=device_area.id)
    entities = er.async_get(hass)
    entity = entities.async_get_or_create(
        "light",
        "synthetic",
        "fixture-lamp",
        device_id=device.id,
        suggested_object_id="fixture_a",
        original_name="Fixture lamp",
    )
    hass.states.async_set(entity.entity_id, "unavailable", {"friendly_name": "Fixture lamp"})
    item = list_lights(hass, [entity.entity_id])[0]
    assert item["area_id"] == device_area.id
    assert item["area_name"] == device_area.name
    assert item["allowed"] is True
    assert item["available"] is False
    entities.async_update_entity(entity.entity_id, area_id=direct_area.id)
    assert list_lights(hass, [])[0]["area_id"] == direct_area.id
    assert list_lights(hass, [])[0]["allowed"] is False


async def test_unregistered_light_has_no_area(hass):
    hass.states.async_set("light.fixture_a", "on")
    assert list_lights(hass, [])[0]["area_id"] is None
