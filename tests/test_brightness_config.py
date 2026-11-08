# Geändert für Lichtzentrale
"""Synthetic room validation, with no installation-specific identifiers."""
from copy import deepcopy

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from custom_components.lichtzentrale.brightness_config import validate_brightness


@pytest.fixture
async def brightness_setup(hass, store):
    area = ar.async_get(hass).async_create("Synthetic brightness room")
    registry = er.async_get(hass)
    lamp = registry.async_get_or_create("light", "synthetic", "brightness-lamp")
    switch = registry.async_get_or_create("switch", "shelly", "brightness-switch",
                                         original_name="Synthetic ceiling light")
    for entry in (lamp, switch):
        registry.async_update_entity(entry.entity_id, area_id=area.id)
        hass.states.async_set(entry.entity_id, "off", {"friendly_name": entry.original_name or "Lamp"})
    hass.states.async_set("sensor.synthetic_brightness", "40",
                         {"device_class": "illuminance", "unit_of_measurement": "lx"})
    hass.states.async_set("person.synthetic_brightness", "home")
    await store.async_set_lights([lamp.entity_id, switch.entity_id])
    config = {
        "enabled": False, "lux_sensor_entity_id": "sensor.synthetic_brightness",
        "target_lux": 100, "hysteresis_lux": 10, "min_interval_seconds": 180,
        "time_window": None, "person_entity_ids": ["person.synthetic_brightness"],
        "stages": [{"entity_ids": [lamp.entity_id], "brightness": 100},
                   {"entity_ids": [switch.entity_id], "brightness": None}],
    }
    return area.id, lamp.entity_id, config


async def test_valid_config_and_window(hass, store, brightness_setup):
    area, _, config = brightness_setup
    assert validate_brightness(hass, store, area, config) == config
    config["time_window"] = {"after": {"type": "sun", "event": "sunset", "offset_min": -10},
                             "before": None}
    result = validate_brightness(hass, store, area, config)
    assert result == config and result is not config
    config["time_window"] = {"after": None, "before": None}
    assert validate_brightness(hass, store, area, config)["time_window"] is None


@pytest.mark.parametrize("field,value", [
    ("enabled", 1), ("target_lux", 0), ("target_lux", -1), ("target_lux", float("nan")),
    ("hysteresis_lux", float("inf")), ("hysteresis_lux", True),
    ("min_interval_seconds", 0), ("min_interval_seconds", 86401),
    ("lux_sensor_entity_id", None), ("lux_sensor_entity_id", "sensor.missing"),
    ("person_entity_ids", ["person.missing"]), ("person_entity_ids", [None]),
    ("stages", []), ("stages", [{}]), ("time_window", {}),
    ("time_window", {"after": {"type": "time", "value": "24:00"}, "before": None}),
])
async def test_invalid_fields(hass, store, brightness_setup, field, value):
    area, _, config = brightness_setup
    with pytest.raises(ServiceValidationError):
        validate_brightness(hass, store, area, {**config, field: value})


async def test_closed_schemas_and_target_safety(hass, store, brightness_setup):
    area, lamp, config = brightness_setup
    cases = [{**config, "extra": True}, {k: v for k, v in config.items() if k != "enabled"}]
    for stage in ({"entity_ids": [lamp], "brightness": None},
                  {"entity_ids": [lamp], "brightness": True},
                  {"entity_ids": [lamp], "brightness": 256},
                  {"entity_ids": [lamp], "brightness": 10, "extra": True},
                  {"entity_ids": ["lock.synthetic"], "brightness": None}):
        cases.append({**config, "stages": [stage]})
    cases.append({**config, "stages": [config["stages"][0], config["stages"][0]]})
    for raw in cases:
        with pytest.raises(ServiceValidationError):
            validate_brightness(hass, store, area, raw)
    other = ar.async_get(hass).async_create("Synthetic other room")
    er.async_get(hass).async_update_entity(lamp, area_id=other.id)
    with pytest.raises(ServiceValidationError):
        validate_brightness(hass, store, area, config)
    er.async_get(hass).async_update_entity(lamp, area_id=area)
    await store.async_set_lights([])
    with pytest.raises(ServiceValidationError):
        validate_brightness(hass, store, area, config)


@pytest.mark.parametrize("attributes", [
    {"device_class": "temperature", "unit_of_measurement": "lx"},
    {"device_class": "illuminance", "unit_of_measurement": "lm"},
])
async def test_lux_sensor_contract(hass, store, brightness_setup, attributes):
    area, _, config = brightness_setup
    hass.states.async_set(config["lux_sensor_entity_id"], "30", attributes)
    with pytest.raises(ServiceValidationError):
        validate_brightness(hass, store, area, deepcopy(config))
