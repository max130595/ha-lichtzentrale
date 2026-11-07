# Geändert für Lichtzentrale
"""Pure validation and deterministic room-local palette placement."""

from colorsys import rgb_to_hsv

from homeassistant.exceptions import ServiceValidationError
from homeassistant.util.color import color_xy_to_RGB

HEIGHTS = ("boden", "moebel", "hintergrund", "decke")
DISTRIBUTIONS = ("zufall", "verlauf_links_rechts", "verlauf_vorne_hinten", "hoehe")


def validate_distribution(value):
    if not isinstance(value, str) or value not in DISTRIBUTIONS:
        raise ServiceValidationError("Ungültige Farbverteilung.")
    return value


def validate_position(value):
    if not isinstance(value, dict) or set(value) != {"cell", "height"}:
        raise ServiceValidationError("Eine Position benötigt Rasterfeld und Höhe.")
    cell = value["cell"]
    if (
        not isinstance(cell, list)
        or len(cell) != 2
        or any(type(v) is not int or not 0 <= v <= 2 for v in cell)
        or not isinstance(value["height"], str)
        or value["height"] not in HEIGHTS
    ):
        raise ServiceValidationError("Ungültiges Rasterfeld oder ungültige Höhe.")
    return {"cell": list(cell), "height": value["height"]}


def validate_positions(value):
    if not isinstance(value, dict) or len(value) > 500:
        raise ServiceValidationError("Ungültige Lampenpositionen.")
    if any(not isinstance(e, str) or not e.startswith(("light.", "switch.")) for e in value):
        raise ServiceValidationError("Ungültige Lampe für eine Position.")
    return {e: validate_position(p) for e, p in value.items()}


def _position(positions, entity_id):
    """Ignore corrupt legacy layout entries without preventing light control."""
    try:
        return validate_position(positions.get(entity_id))
    except ServiceValidationError:
        return None


def ordered_targets(ids, positions, verteilung="zufall"):
    validate_distribution(verteilung)
    if verteilung == "zufall":
        return sorted(ids, key=lambda e: _position(positions, e) is None)

    def key(entity_id):
        position = _position(positions, entity_id)
        if position is None:
            return (1, 0, 0)
        x, y = position["cell"]
        if verteilung == "hoehe":
            return (0, HEIGHTS.index(position["height"]), 0)
        return (0, x, y) if verteilung == "verlauf_links_rechts" else (0, y, x)

    return sorted(ids, key=key)


def strongest_color(colors):
    """Highest HSV saturation after HA's XY→RGB conversion; first wins ties."""
    return max(
        range(len(colors)),
        key=lambda i: rgb_to_hsv(
            *(v / 255 for v in color_xy_to_RGB(colors[i]["x"], colors[i]["y"]))
        )[1],
    )


def palette_indices(ids, positions, colors, verteilung="zufall", offset=0, wave=False):
    """Use fixed axis coordinates, never compress occupied cells after lamps go off.

    Without a wave, spatial dynamic playback cycles the assigned colors forward.
    A wave moves toward increasing coordinates by shifting the palette backwards.
    Background stays the most saturated color for height distributions.
    """
    ordered = ordered_targets(ids, positions, verteilung)
    count = len(colors)
    result = {}
    for index, entity_id in enumerate(ordered):
        position = _position(positions, entity_id)
        base = index
        if position and verteilung != "zufall":
            if verteilung == "hoehe" and position["height"] == "hintergrund":
                result[entity_id] = strongest_color(colors)
                continue
            coordinate = (
                {"boden": 0, "moebel": 1, "decke": 2}[position["height"]]
                if verteilung == "hoehe"
                else position["cell"][0 if verteilung == "verlauf_links_rechts" else 1]
            )
            base = (coordinate * (count - 1) + 1) // 2
        result[entity_id] = (base + (-offset if wave else offset)) % count
    return result
