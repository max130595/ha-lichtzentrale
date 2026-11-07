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


@pytest.mark.parametrize("window", [
    None, {"after": None, "before": None},
    {"after": {"type": "time", "value": "23:00"}, "before": None},
    {"after": None, "before": {"type": "sun", "event": "sunrise", "offset_min": -1440}},
    {"after": {"type": "sun", "event": "sunset", "offset_min": 1440},
     "before": {"type": "time", "value": "05:30"}},
])
async def test_time_window_normalizes_without_mutating_input(hass, store, schedule, window):
    schedule["condition"]["time_window"] = deepcopy(window)
    original = deepcopy(schedule)
    normalized = validate_schedule(hass, store, schedule)
    expected = None if window == {"after": None, "before": None} else window
    assert normalized["condition"]["time_window"] == expected
    assert schedule == original
    if expected:
        key = next(key for key, value in expected.items() if value is not None)
        normalized["condition"]["time_window"][key]["type"] = "changed"
        assert schedule == original


async def test_legacy_condition_normalizes_to_unrestricted(hass, store, schedule):
    assert "time_window" not in schedule["condition"]
    assert validate_schedule(hass, store, schedule)["condition"]["time_window"] is None
    assert "time_window" not in schedule["condition"]


@pytest.mark.parametrize("window", [
    False, 0, "", [], {},
    {"after": None}, {"before": None},
    {"after": None, "before": None, "extra": True},
    {"after": [], "before": None},
    {"after": {"type": "time", "value": "24:00"}, "before": None},
    {"after": None, "before": {"type": "time", "value": "7:00"}},
    {"after": {"type": "time", "value": "07:00", "extra": 1}, "before": None},
    {"after": {"type": "sun", "event": "noon", "offset_min": 0}, "before": None},
    {"after": {"type": "sun", "event": "sunset", "offset_min": True}, "before": None},
    {"after": None, "before": {"type": "sun", "event": "sunrise", "offset_min": 1441}},
    {"after": None, "before": {"type": "sun", "event": "sunrise", "offset_min": -1441}},
    {"after": {"type": "sun", "event": "sunset", "offset_min": 1.5}, "before": None},
    {"after": {"type": "lux", "threshold": 50}, "before": None},
])
async def test_time_window_rejects_malformed_values(hass, store, schedule, window):
    schedule["condition"]["time_window"] = window
    with pytest.raises(ServiceValidationError):
        validate_schedule(hass, store, schedule)
