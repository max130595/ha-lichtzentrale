# Geändert für Lichtzentrale
"""K1: an off lamp's null attributes must not replace its remembered color."""

import pytest
from homeassistant.core import State

from custom_components.lichtzentrale.rooms import light_service_data


@pytest.mark.parametrize("modes", [["xy"], ["color_temp"], ["xy", "color_temp"]])
@pytest.mark.parametrize("attributes", [
    {"color_mode": None, "brightness": 77},
    {"color_mode": None, "brightness": None},
    {"brightness": None},
])
@pytest.mark.parametrize("on", [True, None])
def test_off_lamp_brightness_does_not_initialize_a_null_color_mode(modes, attributes, on):
    state = State("light.synthetic_off_color", "off", {
        "supported_color_modes": modes, **attributes,
    })
    service, payload = light_service_data(state, on=on, brightness=100)
    assert service == "turn_on"
    assert payload == {"entity_id": state.entity_id, "brightness": 100}
    assert "xy_color" not in payload
    assert "color_temp_kelvin" not in payload


@pytest.mark.parametrize("modes", [["xy"], ["color_temp"], ["xy", "color_temp"]])
def test_off_lamp_plain_on_keeps_its_remembered_color(modes):
    state = State("light.synthetic_off_color", "off", {
        "supported_color_modes": modes, "color_mode": None, "brightness": None,
    })
    assert light_service_data(state, on=True) == (
        "turn_on", {"entity_id": state.entity_id},
    )
