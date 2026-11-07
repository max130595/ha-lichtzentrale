# Geändert für Lichtzentrale
"""Position validation and deterministic spatial palette mapping."""

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.lichtzentrale.positions import (
    ordered_targets,
    palette_indices,
    strongest_color,
    validate_distribution,
    validate_position,
    validate_positions,
)

COLORS = [{"x": 0.31, "y": 0.33}, {"x": 0.65, "y": 0.32}, {"x": 0.2, "y": 0.3}]


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {},
        {"cell": [1, 2]},
        {"cell": [True, 1], "height": "boden"},
        {"cell": [0.0, 1], "height": "boden"},
        {"cell": [-1, 1], "height": "boden"},
        {"cell": [3, 1], "height": "boden"},
        {"cell": [1], "height": "boden"},
        {"cell": [1, 1], "height": []},
        {"cell": [1, 1], "height": "Boden"},
        {"cell": [1, 1], "height": "boden", "extra": 1},
    ],
)
def test_invalid_position(value):
    with pytest.raises(ServiceValidationError):
        validate_position(value)


@pytest.mark.parametrize("value", [None, [], True, "wrong", 1])
def test_invalid_distribution(value):
    with pytest.raises(ServiceValidationError):
        validate_distribution(value)


def test_positions_copy_and_keys():
    value = {"light.fixture": {"cell": [1, 2], "height": "moebel"}}
    copied = validate_positions(value)
    copied["light.fixture"]["cell"][0] = 0
    assert value["light.fixture"]["cell"] == [1, 2]
    for invalid in ([], {1: {}}, {"lock.fixture": {}}, {"light.fixture": None}):
        with pytest.raises(ServiceValidationError):
            validate_positions(invalid)


def test_axes_height_sorting_and_legacy_order():
    positions = {
        "a": {"cell": [0, 2], "height": "boden"},
        "b": {"cell": [2, 0], "height": "decke"},
        "c": {"cell": [1, 1], "height": "moebel"},
        "d": {"cell": [0, 0], "height": "hintergrund"},
    }
    ids = ["missing", "b", "c", "a", "d"]
    assert ordered_targets(ids, positions) == ["b", "c", "a", "d", "missing"]
    assert ordered_targets(ids, {}) == ids
    assert ordered_targets(ids, positions, "verlauf_links_rechts") == [
        "d",
        "a",
        "c",
        "b",
        "missing",
    ]
    assert ordered_targets(ids, positions, "verlauf_vorne_hinten") == [
        "d",
        "b",
        "c",
        "a",
        "missing",
    ]
    assert ordered_targets(ids, positions, "hoehe") == ["a", "c", "d", "b", "missing"]
    indices = palette_indices(ids, positions, COLORS, "hoehe")
    assert [indices[e] for e in ("a", "c", "b")] == [0, 1, 2]
    assert indices["d"] == strongest_color(COLORS) == 1
    assert palette_indices(ids, positions, COLORS, offset=1) == {
        e: (i + 1) % 3 for i, e in enumerate(ordered_targets(ids, positions))
    }


def test_wave_same_axis_and_fixed_coordinates():
    positions = {
        e: {"cell": cell, "height": "boden"}
        for e, cell in [("a", [0, 0]), ("b", [0, 2]), ("c", [2, 1])]
    }
    initial = palette_indices(list(positions), positions, COLORS, "verlauf_links_rechts", wave=True)
    shifted = palette_indices(list(positions), positions, COLORS, "verlauf_links_rechts", 1, True)
    assert initial == {"a": 0, "b": 0, "c": 2}
    assert shifted == {"a": 2, "b": 2, "c": 1}
    assert (
        palette_indices(["c"], positions, COLORS, "verlauf_links_rechts", 1, True)["c"]
        == shifted["c"]
    )
