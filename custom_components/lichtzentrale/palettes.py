# Geändert für Lichtzentrale
"""Original palettes and capability-aware application derived from presets.py."""

import asyncio
from copy import deepcopy

from homeassistant.components.light import LightEntityFeature
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util.color import color_RGB_to_xy

from .color_temperature import find_closest_ct_match
from .lights import entity_area_id, is_individual_light, validate_lights
from .positions import ordered_targets, palette_indices, validate_distribution
from .rooms import async_dispatch, validate_transition
from .storage import LichtzentraleStore

# Original names and color choices; no upstream presets or image assets.
_PALETTES = [
    ("kupfernest", "Kupfernest", "Gemütlich", 145, ["#FFAA68", "#F36D47", "#FFD4A1"]),
    ("zimtfunken", "Zimtfunken", "Gemütlich", 115, ["#F47D50", "#D94B43", "#F8B86B"]),
    ("samtkiesel", "Samtkiesel", "Gemütlich", 95, ["#C993CF", "#E8B3BA", "#F6CDA0"]),
    ("minzpapier", "Minzpapier", "Frisch", 210, ["#94F1CF", "#C9F1E7", "#8ED0ED"]),
    ("taulinien", "Taulinien", "Frisch", 195, ["#A1DDEB", "#C7DFFA", "#CDF0C3"]),
    ("limettenfaden", "Limettenfaden", "Frisch", 225, ["#DAEC85", "#A6E7A9", "#F1E6B3"]),
    ("konfettitakt", "Konfettitakt", "Party", 220, ["#FD5BA8", "#765EF0", "#36D9CB"]),
    ("elektrobonbon", "Elektrobonbon", "Party", 235, ["#DA46EB", "#4589F3", "#FA9D43"]),
    ("diskokomet", "Diskokomet", "Party", 200, ["#EA4F68", "#46C7DD", "#D2D553"]),
    ("knospenpost", "Knospenpost", "Jahreszeiten", 190, ["#F1A8C8", "#B5DB84", "#F3D99B"]),
    ("laubgeflecht", "Laubgeflecht", "Jahreszeiten", 155, ["#DC673B", "#E7A044", "#A5AF68"]),
    ("frostsaum", "Frostsaum", "Jahreszeiten", 175, ["#ADCDF7", "#C9BBEB", "#B5E5ED"]),
]


def builtin_palettes() -> list[dict]:
    """Generate preview gradients and XY targets from the same authored colors."""
    palettes = []
    for palette_id, name, category, brightness, preview in _PALETTES:
        colors = []
        for value in preview:
            rgb = tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))
            x, y = color_RGB_to_xy(*rgb)
            colors.append({"x": x, "y": y})
        palettes.append(
            {
                "id": palette_id,
                "name": name,
                "category": category,
                "bri": brightness,
                "colors": colors,
                "preview": list(preview),
            }
        )
    return palettes


BUILTIN_PALETTES = builtin_palettes()


def list_palettes() -> list[dict]:
    """Return built-ins; editing custom palettes belongs to a later stage."""
    return deepcopy(BUILTIN_PALETTES)


async def async_apply_palette(
    hass: HomeAssistant,
    store: LichtzentraleStore,
    palette_id: str,
    entity_ids: list[str],
    brightness: int | None = None,
    transition: float = 1,
    context: Context | None = None,
    *,
    color_offset: int = 0,
    manage: bool = True,
    verteilung: str = "zufall",
    welle: bool = False,
    layout_targets: list[str] | None = None,
    tick_area_id: str | None = None,
    schedule_transition: bool = False,
) -> dict[str, list[str]]:
    """Apply one original palette to explicitly allowed individual lamps only."""
    validate_distribution(verteilung)
    if type(welle) is not bool or type(color_offset) is not int:
        raise ServiceValidationError("Ungültige Wellen-Einstellungen.")
    if welle and verteilung == "zufall":
        raise ServiceValidationError("Für eine Welle bitte eine räumliche Verteilung auswählen.")
    palette = next((item for item in BUILTIN_PALETTES if item["id"] == palette_id), None)
    if palette is None:
        raise ServiceValidationError("Die Farbpalette wurde nicht gefunden.")
    if not entity_ids:
        raise ServiceValidationError("Bitte mindestens eine Lampe auswählen.")
    targets = validate_lights(hass, entity_ids)
    allowed = store.data["settings"]["light_entity_ids"]
    if any(entity_id not in allowed for entity_id in targets):
        raise ServiceValidationError("Bitte die ausgewählten Lampen zuerst freigeben.")
    if brightness is not None and (
        not isinstance(brightness, int)
        or isinstance(brightness, bool)
        or not 1 <= brightness <= 255
    ):
        raise ServiceValidationError("Die Helligkeit muss zwischen 1 und 255 liegen.")
    validate_transition(transition)
    if transition is None or (not schedule_transition and transition > 60):
        raise ServiceValidationError("Der Übergang muss zwischen 0 und 60 Sekunden liegen.")

    if manage:
        from asyncio import Lock
        from contextlib import AsyncExitStack

        from .adaptive import async_pause_adaptive
        from .const import DOMAIN
        from .dynamic_scenes import stop_dynamic

        areas = sorted(
            {entity_area_id(hass, e) for e in targets if e.startswith("light.")} - {None}
        )
        locks = hass.data.setdefault(DOMAIN, {}).setdefault("scene_locks", {})
        async with AsyncExitStack() as stack:
            for area_id in areas:
                await stack.enter_async_context(locks.setdefault(area_id, Lock()))
            for area_id in areas:
                await stop_dynamic(hass, area_id)
                await async_pause_adaptive(hass, store, area_id, context=context)
            return await async_apply_palette(
                hass,
                store,
                palette_id,
                targets,
                brightness,
                transition,
                context,
                color_offset=color_offset,
                manage=False,
                verteilung=verteilung,
                welle=welle,
                layout_targets=layout_targets,
                tick_area_id=tick_area_id,
                schedule_transition=schedule_transition,
            )

    skipped_switches = [e for e in targets if e.startswith("switch.")]
    targets = [e for e in targets if e.startswith("light.")]
    result: dict[str, list[str]] = {"applied": [], "skipped": skipped_switches}
    calls = []
    layout = layout_targets if welle and layout_targets is not None else targets
    layout = [e for e in layout if e.startswith("light.")]
    positions = {}
    for entity_id in layout:
        area_id = entity_area_id(hass, entity_id)
        positions.update(
            {entity_id: store.data["rooms"].get(area_id, {}).get("positions", {}).get(entity_id)}
        )
    indices = palette_indices(layout, positions, palette["colors"], verteilung, color_offset, welle)
    for entity_id in ordered_targets(targets, positions, verteilung):
        state = hass.states.get(entity_id)
        if state is None or state.state in {"unknown", "unavailable"}:
            result["skipped"].append(entity_id)
            continue
        attributes = state.attributes
        modes = set(attributes.get("supported_color_modes") or [])
        color = palette["colors"][indices[entity_id]]
        xy = (color["x"], color["y"])
        params = {"entity_id": entity_id}
        if modes.intersection({"xy", "hs", "rgb", "rgbw", "rgbww"}):
            params["xy_color"] = xy
        elif "color_temp" in modes:
            kelvin = find_closest_ct_match(*xy)
            minimum = attributes.get("min_color_temp_kelvin", 2000)
            maximum = attributes.get("max_color_temp_kelvin", 6500)
            params["color_temp_kelvin"] = max(minimum, min(maximum, kelvin))
        elif not modes.intersection({"brightness", "onoff"}):
            result["skipped"].append(entity_id)
            continue
        if modes - {"onoff"}:
            params["brightness"] = brightness if brightness is not None else palette["bri"]
        if attributes.get("supported_features", 0) & LightEntityFeature.TRANSITION:
            params["transition"] = transition
        calls.append(("light", "turn_on", params))
    if tick_area_id is not None:
        return await _async_dispatch_tick(
            hass, store, tick_area_id, calls, result["skipped"], context
        )
    return await async_dispatch(hass, calls, result["skipped"], context)


async def _async_dispatch_tick(hass, store, area_id, calls, skipped, context):
    """Recheck each tick target after scheduling, directly before sending its command."""
    result = {"applied": [], "skipped": list(skipped)}

    async def dispatch(domain, service, params):
        entity_id = params["entity_id"]
        state = hass.states.get(entity_id)
        if (
            state is None
            or state.domain != "light"
            or state.state != "on"
            or entity_id not in store.data["settings"]["light_entity_ids"]
            or entity_area_id(hass, entity_id) != area_id
            or not is_individual_light(hass, state)
        ):
            return "skipped", entity_id
        try:
            await hass.services.async_call(domain, service, params, blocking=True, context=context)
        except Exception:
            return "failed", entity_id
        return "applied", entity_id

    for key, entity_id in await asyncio.gather(*(dispatch(*call) for call in calls)):
        result.setdefault(key, []).append(entity_id)
    return result
