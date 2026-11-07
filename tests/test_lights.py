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


@pytest.mark.parametrize(
    "platform,name,expected",
    [
        ("shelly", "Deckenlicht", True),
        ("shelly", "Flurlicht", True),
        ("shelly", "Heating relay", False),
        ("synthetic", "Ceiling light", False),
    ],
)
async def test_only_registered_shelly_lighting_switches(hass, platform, name, expected):
    entry = er.async_get(hass).async_get_or_create(
        "switch",
        platform,
        "fixture-relay",
        original_name=name,
    )
    hass.states.async_set(entry.entity_id, "on")
    assert bool(list_lights(hass, [])) is expected
    if expected:
        assert validate_lights(hass, [entry.entity_id]) == [entry.entity_id]
        item = list_lights(hass, [])[0]
        assert item["domain"] == "switch"
        assert item["brightness"] is None
        assert item["supported_color_modes"] == []
    else:
        with pytest.raises(ServiceValidationError):
            validate_lights(hass, [entry.entity_id])


@pytest.mark.parametrize("platform,manufacturer", [("bambu_lab", None), ("synthetic", "Bambu Lab")])
async def test_printer_hidden_unless_requested_or_already_approved(hass, platform, manufacturer):
    config = MockConfigEntry(domain=platform)
    config.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config.entry_id,
        identifiers={(platform, "fixture-printer")},
        manufacturer=manufacturer,
    )
    entity = er.async_get(hass).async_get_or_create(
        "light",
        platform,
        "fixture-chamber",
        device_id=device.id,
    )
    hass.states.async_set(entity.entity_id, "off")
    assert list_lights(hass, []) == []
    assert list_lights(hass, [], include_hidden=True)[0]["hidden_by_default"]
    assert list_lights(hass, [entity.entity_id])[0]["allowed"]


async def test_shelly_lighting_device_metadata_is_used(hass):
    config = MockConfigEntry(domain="shelly")
    config.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config.entry_id,
        identifiers={("shelly", "fixture-relay-device")},
        name="Fixture Flurlicht",
    )
    entry = er.async_get(hass).async_get_or_create(
        "switch",
        "shelly",
        "fixture-relay",
        device_id=device.id,
        original_name="Relay 0",
    )
    hass.states.async_set(entry.entity_id, "off")
    assert list_lights(hass, [])[0]["entity_id"] == entry.entity_id
