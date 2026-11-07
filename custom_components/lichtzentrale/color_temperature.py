# Geändert für Lichtzentrale
"""XY/temperature matching adapted from hass-scene_presets (Apache-2.0)."""

from homeassistant.util.color import color_RGB_to_xy, color_temperature_to_rgb

CT_XY_LOOKUP = {
    kelvin: color_RGB_to_xy(*color_temperature_to_rgb(kelvin)) for kelvin in range(2000, 6501, 50)
}


def find_closest_ct_match(x: float, y: float) -> int:
    """Find the nearest white point, without assuming monotonic XY distance."""
    return min(
        CT_XY_LOOKUP,
        key=lambda kelvin: (x - CT_XY_LOOKUP[kelvin][0]) ** 2 + (y - CT_XY_LOOKUP[kelvin][1]) ** 2,
    )
