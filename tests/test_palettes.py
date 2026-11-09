"""Capability-aware palettes and atomic target validation."""

from unittest.mock import patch

import pytest
from homeassistant.components.light import LightEntityFeature
from homeassistant.core import Context
from homeassistant.exceptions import ServiceValidationError

from custom_components.lichtzentrale.palettes import async_apply_palette, list_palettes

PALETTE = "kupfernest"


def test_original_catalogue_and_copy_isolation():
    palettes = list_palettes()
    assert len(palettes) >= 20
    assert {"Herbst", "Winter", "Weihnachten", "Frühling", "Sommer", "Party", "Entspannen", "Romantik"} <= {item["category"] for item in palettes}
    assert len({item["id"] for item in palettes}) == len(palettes)
    for item in palettes:
        assert 1 <= item["bri"] <= 255
        assert 3 <= len(item["colors"]) == len(item["preview"]) <= 5
        assert all(0 <= color["x"] <= 1 and 0 <= color["y"] <= 1 for color in item["colors"])
        assert all(value.startswith("#") and len(value) == 7 for value in item["preview"])
    palettes[0]["colors"].clear()
    assert list_palettes()[0]["colors"]


@pytest.mark.parametrize("mode", ["xy", "hs", "rgb", "rgbw", "rgbww", "brightness", "onoff"])
async def test_capability_service_payload(hass, store, light_calls, mode):
    entity_id = "light.fixture_a"
    hass.states.async_set(entity_id, "off", {"supported_color_modes": [mode]})
    await store.async_set_lights([entity_id])
    context = Context()
    result = await async_apply_palette(hass, store, PALETTE, [entity_id], 123, context=context)
    assert result == {"applied": [entity_id], "skipped": []}
    assert len(light_calls) == 1
    call = light_calls[0]
    assert call.context == context
    assert call.data["entity_id"] == entity_id
    assert ("xy_color" in call.data) == (mode not in {"brightness", "onoff"})
    assert ("brightness" in call.data) == (mode != "onoff")
    if mode != "onoff":
        assert call.data["brightness"] == 123
    assert "transition" not in call.data


@pytest.mark.parametrize("match,expected", [(2000, 2700), (6500, 4000), (3500, 3500)])
async def test_temperature_clamped_to_device_range(hass, store, light_calls, match, expected):
    hass.states.async_set(
        "light.fixture_a",
        "on",
        {
            "supported_color_modes": ["color_temp"],
            "min_color_temp_kelvin": 2700,
            "max_color_temp_kelvin": 4000,
            "supported_features": LightEntityFeature.TRANSITION,
        },
    )
    await store.async_set_lights(["light.fixture_a"])
    with patch(
        "custom_components.lichtzentrale.palettes.find_closest_ct_match", return_value=match
    ):
        await async_apply_palette(hass, store, PALETTE, ["light.fixture_a"], transition=2.5)
    assert light_calls[0].data == {
        "entity_id": "light.fixture_a",
        "color_temp_kelvin": expected,
        "brightness": list_palettes()[0]["bri"],
        "transition": 2.5,
    }


@pytest.mark.parametrize("state,modes", [("unavailable", ["xy"]), ("unknown", ["xy"]), ("on", [])])
async def test_unavailable_and_unsupported_skipped(hass, store, light_calls, state, modes):
    hass.states.async_set("light.fixture_a", state, {"supported_color_modes": modes})
    await store.async_set_lights(["light.fixture_a"])
    assert await async_apply_palette(hass, store, PALETTE, ["light.fixture_a"]) == {
        "applied": [],
        "skipped": ["light.fixture_a"],
    }
    assert not light_calls


@pytest.mark.parametrize(
    "invalid", ["switch.fixture_a", "lock.fixture_a", "group.fixture_a", "light.missing"]
)
async def test_mixed_targets_rejected_before_any_call(hass, store, light_calls, invalid):
    hass.states.async_set("light.fixture_a", "on", {"supported_color_modes": ["xy"]})
    if invalid != "light.missing":
        hass.states.async_set(invalid, "on")
    await store.async_set_lights(["light.fixture_a", invalid])
    with pytest.raises(ServiceValidationError):
        await async_apply_palette(hass, store, PALETTE, ["light.fixture_a", invalid])
    assert not light_calls


async def test_allowlist_required_and_duplicates_only_called_once(hass, store, light_calls):
    hass.states.async_set("light.fixture_a", "on", {"supported_color_modes": ["xy"]})
    with pytest.raises(ServiceValidationError):
        await async_apply_palette(hass, store, PALETTE, ["light.fixture_a"])
    assert not light_calls
    await store.async_set_lights(["light.fixture_a"])
    await async_apply_palette(hass, store, PALETTE, ["light.fixture_a"] * 2)
    assert len(light_calls) == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"brightness": 0},
        {"brightness": 256},
        {"brightness": True},
        {"brightness": 2.5},
        {"transition": -1},
        {"transition": 61},
        {"transition": float("nan")},
    ],
)
async def test_invalid_options_have_no_side_effects(hass, store, light_calls, kwargs):
    hass.states.async_set("light.fixture_a", "on", {"supported_color_modes": ["xy"]})
    await store.async_set_lights(["light.fixture_a"])
    with pytest.raises(ServiceValidationError):
        await async_apply_palette(hass, store, PALETTE, ["light.fixture_a"], **kwargs)
    assert not light_calls


@pytest.mark.parametrize("palette,targets", [("missing", ["light.fixture_a"]), (PALETTE, [])])
async def test_unknown_palette_or_empty_targets(hass, store, light_calls, palette, targets):
    with pytest.raises(ServiceValidationError):
        await async_apply_palette(hass, store, palette, targets)
    assert not light_calls


async def test_palette_skips_switch_and_reports_light_failure(hass, store):

    from homeassistant.helpers import entity_registry as er

    entry = er.async_get(hass).async_get_or_create(
        "switch",
        "shelly",
        "fixture-ceiling",
        original_name="Fixture Deckenlicht",
    )
    ids = ["light.fixture_a", entry.entity_id]
    hass.states.async_set(ids[0], "on", {"supported_color_modes": ["xy"]})
    hass.states.async_set(ids[1], "off")
    await store.async_set_lights(ids)
    calls = []

    async def call(domain, service, data, **kwargs):
        calls.append((domain, service, data))
        if domain == "light":
            raise RuntimeError("Synthetic device failure")

    with patch.object(type(hass.services), "async_call", side_effect=call):
        result = await async_apply_palette(hass, store, PALETTE, ids)
    assert len(calls) == 1
    assert calls[0][0] == "light"
    assert result == {"applied": [], "skipped": [ids[1]], "failed": [ids[0]]}


@pytest.mark.parametrize(
    "kwargs", [{"verteilung": []}, {"verteilung": "diagonal"}, {"welle": 1}, {"welle": True}]
)
async def test_invalid_spatial_options_no_calls(hass, store, light_calls, kwargs):
    hass.states.async_set("light.fixture_a", "on", {"supported_color_modes": ["xy"]})
    await store.async_set_lights(["light.fixture_a"])
    with pytest.raises(ServiceValidationError):
        await async_apply_palette(hass, store, PALETTE, ["light.fixture_a"], **kwargs)
    assert not light_calls


@pytest.mark.parametrize("wave", [False, True])
async def test_switch_never_consumes_palette_slot(hass, store, light_calls, wave):
    from homeassistant.helpers import entity_registry as er

    switch = er.async_get(hass).async_get_or_create(
        "switch", "shelly", "fixture-palette-switch", original_name="Fixture Licht"
    )
    ids = ["light.fixture_a", switch.entity_id, "light.fixture_b"]
    for entity_id in ids:
        hass.states.async_set(entity_id, "off", {"supported_color_modes": ["xy"]})
    await store.async_set_lights(ids)
    result = await async_apply_palette(
        hass,
        store,
        PALETTE,
        ids,
        welle=wave,
        verteilung="verlauf_links_rechts" if wave else "zufall",
        layout_targets=ids,
    )
    assert result == {"applied": [ids[0], ids[2]], "skipped": [ids[1]]}
    colors = list_palettes()[0]["colors"]
    assert [c.data["xy_color"] for c in light_calls] == [(c["x"], c["y"]) for c in colors[:2]]
