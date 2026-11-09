# Geändert für Lichtzentrale
"""Minimal relative dim commands with a per-lamp lower brightness bound."""

from homeassistant.exceptions import ServiceValidationError

from .lights import color_modes

DEFAULT_DIM_MIN_PCT = 1
DIMMABLE_MODES = {"brightness", "color_temp", "hs", "xy", "rgb", "rgbw", "rgbww", "white"}


def validate_dim_min_pct(value):
    """Reject coercion (including booleans) at every persistence boundary."""
    if type(value) is not int or not 1 <= value <= 20:
        raise ServiceValidationError("Die Dimm-Untergrenze muss eine ganze Zahl von 1 bis 20 % sein.")
    return value


def dim_min_pct(store):
    """Use the default safely for missing or damaged old stored values."""
    value = store.data["settings"].get("dim_min_pct", DEFAULT_DIM_MIN_PCT)
    return value if type(value) is int and 1 <= value <= 20 else DEFAULT_DIM_MIN_PCT


def dim_payload(state, direction, minimum_pct):
    """Never initialize colors or send dim commands to on/off-only entities.

    HA rounds the current brightness to percent *before* applying a percent
    step. Mirror that algorithm, rather than subtracting 25 or 26 raw units.
    Call again at dispatch, since states/settings can change while awaiting.
    """
    if (state is None or state.domain != "light" or state.state != "on"
            or not color_modes(state) & DIMMABLE_MODES):
        return None
    brightness = state.attributes.get("brightness")
    if type(brightness) is not int or not 1 <= brightness <= 255:
        return None
    params = {"entity_id": state.entity_id}
    if direction < 0:
        floor = round(minimum_pct * 255 / 100)
        if brightness <= floor:
            return None
        predicted = round((round(brightness / 255 * 100) - 10) / 100 * 255)
        if predicted <= floor:
            return {**params, "brightness": floor}
    return {**params, "brightness_step_pct": direction * 10}
