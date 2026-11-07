# Geändert für Lichtzentrale
"""Schedule validation uses synthetic runtime entities only."""

from copy import deepcopy

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.lichtzentrale.schedule_config import list_persons, validate_schedule


@pytest.fixture
async def schedule(hass, store):
    er.async_get(hass).async_get_or_create(
        "light", "synthetic", "schedule-fixture", suggested_object_id="synthetic_schedule")
    hass.states.async_set("light.synthetic_schedule", "off", {"supported_color_modes": ["brightness"]})
    hass.states.async_set("sensor.synthetic_lux", "10", {
        "device_class": "illuminance", "unit_of_measurement": "lx"})
    hass.states.async_set("person.synthetic_occupant", "home")
    await store.async_set_lights(["light.synthetic_schedule"])
    return {"name": "Synthetic plan", "enabled": False,
            "trigger": {"type": "time", "value": "20:00"},
            "condition": {"weekdays": list(range(7)), "person_entity_ids": [], "light_state": "any"},
            "action": {"type": "lights", "entity_ids": ["light.synthetic_schedule"],
                       "on": True, "brightness": None}, "transition": None}


async def test_normalize_and_stale_id(hass, store, schedule):
    normalized = validate_schedule(hass, store, schedule)
    assert normalized["id"] and "id" not in schedule
    with pytest.raises(ServiceValidationError):
        validate_schedule(hass, store, normalized)
    store._data["schedules"] = [normalized]
    assert validate_schedule(hass, store, normalized) == normalized
    assert list_persons(hass)[0]["entity_id"] == "person.synthetic_occupant"


@pytest.mark.parametrize("field,value", [
    ("transition", True), ("transition", float("nan")), ("transition", 1801),
    ("enabled", 1), ("name", " "),
    ("trigger", {"type": "time", "value": "24:00"}),
    ("trigger", {"type": "sun", "event": "sunset", "offset_min": True}),
    ("condition", {"weekdays": [True], "person_entity_ids": [], "light_state": "any"}),
    ("condition", {"weekdays": [0], "person_entity_ids": ["person.missing"], "light_state": "any"}),
    ("action", {"type": []}),
    ("condition", {"weekdays": [0], "person_entity_ids": [], "light_state": []}),
])
async def test_reject_invalid_fields(hass, store, schedule, field, value):
    schedule[field] = value
    with pytest.raises(ServiceValidationError):
        validate_schedule(hass, store, schedule)


@pytest.mark.parametrize("section", [None, "trigger", "condition", "action"])
async def test_closed_schemas(hass, store, schedule, section):
    (schedule if section is None else schedule[section])["extra"] = 1
    with pytest.raises(ServiceValidationError):
        validate_schedule(hass, store, schedule)


async def test_lux_validation_and_revocation(hass, store, schedule):
    schedule["trigger"] = {"type": "lux", "sensor_entity_id": "sensor.synthetic_lux",
                           "comparison": "below", "threshold": 50, "duration_seconds": 300}
    assert validate_schedule(hass, store, schedule)["trigger"] == schedule["trigger"]
    for field, value in [("threshold", float("inf")), ("threshold", -1),
                         ("duration_seconds", 0), ("comparison", "equal"), ("comparison", [])]:
        invalid = deepcopy(schedule)
        invalid["trigger"][field] = value
        with pytest.raises(ServiceValidationError):
            validate_schedule(hass, store, invalid)
    await store.async_set_lights([])
    with pytest.raises(ServiceValidationError):
        validate_schedule(hass, store, schedule)
