"""Nearest white point matches the complete bounded lookup."""

import pytest

from custom_components.lichtzentrale.color_temperature import (
    CT_XY_LOOKUP,
    find_closest_ct_match,
)


@pytest.mark.parametrize("kelvin", [2000, 2700, 4000, 6500])
def test_exact_white_points(kelvin):
    assert find_closest_ct_match(*CT_XY_LOOKUP[kelvin]) == kelvin


@pytest.mark.parametrize("xy", [(0.1, 0.2), (0.65, 0.3), (0.33, 0.33)])
def test_nearest_temperature_minimizes_distance(xy):
    match = find_closest_ct_match(*xy)
    assert 2000 <= match <= 6500
    expected = min(
        CT_XY_LOOKUP,
        key=lambda kelvin: sum(
            (left - right) ** 2 for left, right in zip(xy, CT_XY_LOOKUP[kelvin], strict=True)
        ),
    )
    assert match == expected
