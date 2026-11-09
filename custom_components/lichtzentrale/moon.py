# Geändert für Lichtzentrale
"""Local approximate synodic illumination; no astronomy service or network needed."""

import math
from datetime import datetime, timezone

from homeassistant.util import dt as dt_util

SYNODIC_DAYS = 29.530588853
# Known new moon, 6 January 2000 18:14 UTC. This is an illumination estimate,
# not an ephemeris: it deliberately does not model lunar latitude or distance.
NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
UPDATE_SECONDS = 1800
DEFAULTS = {
    "new_brightness": 26,
    "full_brightness": 204,
    "new_xy": [0.25, 0.27],
    "full_xy": [0.3127, 0.3290],
    "breath": False,
}


def illuminated_fraction(now=None):
    now = now or dt_util.utcnow()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    phase = ((now - NEW_MOON).total_seconds() / (SYNODIC_DAYS * 86400)) % 1
    return (1 - math.cos(2 * math.pi * phase)) / 2


def light_values(options=None, now=None, breath=False):
    """Interpolate each lamp's explicit new/full endpoints independently."""
    values = {**DEFAULTS, **(options or {})}
    now = now or dt_util.utcnow()
    fraction = illuminated_fraction(now)
    brightness = values["new_brightness"] + fraction * (
        values["full_brightness"] - values["new_brightness"]
    )
    if breath and values["breath"] and fraction >= 0.95:
        brightness *= 0.95 + 0.05 * math.sin(now.timestamp() * 2 * math.pi / 180)
    return {
        "brightness": max(1, min(255, round(brightness))),
        "xy": [a + fraction * (b - a) for a, b in zip(
            values["new_xy"], values["full_xy"], strict=True
        )],
    }
