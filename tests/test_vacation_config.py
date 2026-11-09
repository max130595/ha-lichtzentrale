# Geändert für Lichtzentrale
"""Closed vacation settings with synthetic registry and approved lights only."""

from copy import deepcopy

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from custom_components.lichtzentrale.vacation_config import (
    default_vacation_config,
    validate_until,
    validate_vacation_config,
)


@pytest.fixture
async def vacation_config(hass, store):
    area = ar.async_get(hass).async_create("Synthetic vacation room")
    entry = er.async_get(hass).async_get_or_create("light", "synthetic", "vacation-config")
    er.async_get(hass).async_update_entity(entry.entity_id, area_id=area.id)
    hass.states.async_set(entry.entity_id, "off")
    await store.async_set_lights([entry.entity_id])
    config = default_vacation_config()
    config["rooms"] = [{"area_id": area.id, "type": "living", "weight": 1,
                        "on_behavior": {"mode": "last"}}]
    return config


async def test_valid_independent_config(hass, store, vacation_config):
    assert validate_vacation_config(hass, store, vacation_config) == vacation_config
    result = validate_vacation_config(hass, store, vacation_config)
    result["rooms"][0]["weight"] = 7
    assert vacation_config["rooms"][0]["weight"] == 1
    assert default_vacation_config()["rooms"] == []
    vacation_config["rooms"][0]["on_behavior"] = {"mode": "brightness", "brightness": 123}
    assert validate_vacation_config(hass, store, vacation_config) == vacation_config


@pytest.mark.parametrize("key,value", [
    ("max_rooms", True), ("max_rooms", 0), ("max_rooms", 21),
    ("learn_history", 1), ("rooms", {}), ("evening", {}), ("morning", {}),
    ("notify_service", "light.turn_on"), ("notify_service", "notify.missing"),
    ("unexpected", 1),
])
async def test_invalid_config(hass, store, vacation_config, key, value):
    with pytest.raises(ServiceValidationError):
        validate_vacation_config(hass, store, {**vacation_config, key: value})


@pytest.mark.parametrize("key,value", [
    ("weight", True), ("weight", -1), ("weight", float("nan")), ("weight", float("inf")),
    ("type", []), ("type", "other"), ("area_id", "missing"), ("area_id", []),
    ("on_behavior", {"mode": "time", "windows": []}),
    ("on_behavior", {"mode": "brightness", "brightness": 0}),
    ("on_behavior", {"mode": "scene", "scene_id": "missing"}),
])
async def test_invalid_room(hass, store, vacation_config, key, value):
    vacation_config["rooms"][0][key] = value
    with pytest.raises(ServiceValidationError):
        validate_vacation_config(hass, store, vacation_config)


async def test_duplicate_and_revoked_room(hass, store, vacation_config):
    duplicate = deepcopy(vacation_config)
    duplicate["rooms"] *= 2
    with pytest.raises(ServiceValidationError):
        validate_vacation_config(hass, store, duplicate)
    await store.async_set_lights([])
    with pytest.raises(ServiceValidationError):
        validate_vacation_config(hass, store, vacation_config)


@pytest.mark.parametrize("boundary", [
    {"type": "time", "value": "24:00"}, {"type": "time", "value": "6:00"},
    {"type": "sun", "event": "sunset", "offset_min": True},
    {"type": "sun", "event": "sunset", "offset_min": 1441},
    {"type": "sun", "event": "sunset", "offset_min": 0, "extra": 0},
])
async def test_boundaries(hass, store, vacation_config, boundary):
    vacation_config["evening"]["start"] = boundary
    with pytest.raises(ServiceValidationError):
        validate_vacation_config(hass, store, vacation_config)


async def test_notify_named_only(hass, store, vacation_config):
    async def notify(call):
        pass

    hass.services.async_register("notify", "synthetic_phone", notify)
    hass.services.async_register("notify", "send_message", notify)
    vacation_config["notify_service"] = "notify.synthetic_phone"
    assert validate_vacation_config(hass, store, vacation_config) == vacation_config
    vacation_config["notify_service"] = "notify.send_message"
    with pytest.raises(ServiceValidationError):
        validate_vacation_config(hass, store, vacation_config)


@pytest.mark.parametrize("value", [True, "2026-02-30", "2026-1-01", "9999-12-31", "2026-11-09T12:00:00Z"])
def test_invalid_until(value):
    with pytest.raises(ServiceValidationError):
        validate_until(value)


def test_valid_until():
    assert validate_until(None) is None
    assert validate_until("") is None
    assert validate_until("2026-11-09") == "2026-11-09"
