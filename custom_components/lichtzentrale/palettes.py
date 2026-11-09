# Geändert für Lichtzentrale
"""Original palettes and capability-aware application derived from presets.py."""

import math

from homeassistant.components.light import LightEntityFeature
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from .color_temperature import find_closest_ct_match
from .lights import (
    clamp_xy,
    color_modes,
    entity_area_id,
    is_individual_light,
    supports_payload,
    validate_lights,
)

# Backward-compatible imports for callers; custom palettes live in the same Store.
from .palette_catalogue import BUILTIN_PALETTES, builtin_palettes, get_palette, list_palettes  # noqa: F401
from .positions import ordered_targets, palette_indices, validate_distribution
from .rooms import async_dispatch, check_execution_guard, light_service_data, validate_transition
from .storage import LichtzentraleStore
from .zones import contains, validate_area


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
    layout_area_id: str | None = None,
    schedule_transition: bool = False,
    dispatch_guard=None,
    lamp_settings=None,
    wave_order=None,
    gentle=False,
    palette_override=None,
    dynamic_commands=False,
    tick_guard=None,
    moon_due=True,
    moon_breath=False,
    only_moon=False,
) -> dict[str, list[str]]:
    """Apply one original palette to explicitly allowed individual lamps only."""
    validate_distribution(verteilung)
    if type(welle) is not bool or type(color_offset) is not int:
        raise ServiceValidationError("Ungültige Wellen-Einstellungen.")
    if welle and verteilung == "zufall" and not wave_order:
        raise ServiceValidationError("Für eine Welle bitte eine räumliche Verteilung auswählen.")
    palette = palette_override if palette_override is not None else get_palette(store, palette_id)
    if palette is None:
        raise ServiceValidationError("Die Farbpalette wurde nicht gefunden.")
    if not entity_ids:
        raise ServiceValidationError("Bitte mindestens eine Lampe auswählen.")
    targets = validate_lights(hass, entity_ids)
    if layout_area_id is not None:
        validate_area(hass, store, layout_area_id)
        if any(not contains(hass, store, layout_area_id, entity) for entity in targets):
            raise ServiceValidationError("Die Lampen gehören nicht vollständig zum gewählten Ziel.")
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
        from .dynamic_scenes import async_stop_overlapping, stop_dynamic

        areas = sorted(
            {entity_area_id(hass, e) for e in targets if e.startswith("light.")} - {None}
        )
        locks = hass.data.setdefault(DOMAIN, {}).setdefault("scene_locks", {})
        async with AsyncExitStack() as stack:
            for area_id in areas:
                await stack.enter_async_context(locks.setdefault(area_id, Lock()))
            await async_stop_overlapping(hass, targets)
            for area_id in areas:
                await stop_dynamic(hass, area_id)
                await async_pause_adaptive(hass, store, area_id, context=context, dispatch_guard=dispatch_guard)
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
                layout_area_id=layout_area_id,
                schedule_transition=schedule_transition,
                dispatch_guard=dispatch_guard,
                lamp_settings=lamp_settings, wave_order=wave_order, gentle=gentle,
                palette_override=palette_override, dynamic_commands=dynamic_commands,
                tick_guard=tick_guard, moon_due=moon_due, moon_breath=moon_breath,
                only_moon=only_moon,
            )

    explicit_switches = [e for e in targets if e.startswith("switch.") and e in (lamp_settings or {})]
    skipped_switches = [e for e in targets if e.startswith("switch.") and e not in explicit_switches]
    targets = [e for e in targets if e.startswith("light.")]
    result: dict[str, list[str]] = {"applied": [], "skipped": skipped_switches}
    calls = []
    if tick_area_id is None:
        for entity_id in explicit_switches:
            state = hass.states.get(entity_id)
            if state and state.state in {"on", "off"}:
                calls.append(("switch", "turn_off" if lamp_settings[entity_id].get("mode") == "off" else "turn_on", {"entity_id": entity_id}))
            else:
                result["skipped"].append(entity_id)
    layout = layout_targets if layout_targets is not None else targets
    layout = [e for e in layout if e.startswith("light.")]
    positions = {}
    for entity_id in layout:
        area_id = layout_area_id or tick_area_id or entity_area_id(hass, entity_id)
        positions.update(
            {entity_id: store.data["rooms"].get(area_id, {}).get("positions", {}).get(entity_id)}
        )
    settings = lamp_settings or {}
    indices = palette_indices(layout, positions, palette["colors"], verteilung, color_offset, welle)
    order = ordered_targets(targets, positions, verteilung)
    if wave_order:
        # Keep absent/excluded lamps' slots. Manual edits must not compress a wave.
        ordered = [e for e in wave_order if e in layout]
        ordered.extend(e for e in layout if e not in ordered)
        indices = {e: (i + (-color_offset if welle else color_offset)) % len(palette["colors"])
                   for i, e in enumerate(ordered)}
        order = [e for e in ordered if e in targets]
    for entity_id in order:
        state = hass.states.get(entity_id)
        if state is None or state.state in {"unknown", "unavailable"}:
            result["skipped"].append(entity_id)
            continue
        attributes = state.attributes
        modes = color_modes(state)
        setting = settings.get(entity_id, {})
        mode = setting.get("mode", "cycle")
        if only_moon and mode != "moon":
            continue
        if tick_area_id is not None and (
            setting.get("effect") or mode in {"off", "fixed"} or not modes - {"onoff"}
            or (mode == "moon" and not moon_due and not (moon_breath and setting.get("moon", {}).get("breath")))
        ):
            continue
        if mode == "off":
            payload = light_service_data(state, on=False, transition=transition)
            calls.append(("light", *payload))
            continue
        if not modes & {"xy", "hs", "rgb", "rgbw", "rgbww", "color_temp", "brightness", "white", "onoff"}:
            result["skipped"].append(entity_id)
            continue
        index = indices[entity_id]
        if mode == "fixed" and setting.get("palette_index") is not None:
            index = setting["palette_index"] % len(palette["colors"])
        color = palette["colors"][index]
        xy = setting.get("xy") if mode == "fixed" else None
        xy = xy or (color["x"], color["y"])
        kelvin = setting.get("color_temp_kelvin") if mode == "fixed" else None
        base = setting.get("brightness")
        if base is None:
            base = brightness if brightness is not None else palette["bri"]
        if gentle and mode == "cycle" and color_offset:
            # A stable phase per lamp, relative to its own base, not scene average.
            base = max(1, min(255, round(base * (
                1 + 0.1 * math.sin(color_offset * math.pi / 4 + layout.index(entity_id))
            ))))
        if mode == "moon":
            from .moon import light_values

            moon_values = light_values(setting.get("moon"), breath=moon_breath)
            base = setting.get("brightness")
            if base is None:
                base = moon_values["brightness"]
            xy = moon_values["xy"]
        params = {"entity_id": entity_id}
        if modes.intersection({"xy", "hs", "rgb", "rgbw", "rgbww"}) and kelvin is None:
            params["xy_color"] = clamp_xy(state, xy)
        elif "color_temp" in modes:
            kelvin = kelvin or find_closest_ct_match(*xy)
            minimum = attributes.get("min_color_temp_kelvin") or 2000
            maximum = attributes.get("max_color_temp_kelvin") or 6500
            params["color_temp_kelvin"] = max(minimum, min(maximum, kelvin))
        elif kelvin is not None and modes.intersection({"xy", "hs", "rgb", "rgbw", "rgbww"}):
            from homeassistant.util.color import color_RGB_to_xy, color_temperature_to_rgb

            params["xy_color"] = clamp_xy(state, color_RGB_to_xy(*color_temperature_to_rgb(kelvin)))
        if modes - {"onoff"}:
            params["brightness"] = base
            if attributes.get("supported_features", 0) & LightEntityFeature.TRANSITION:
                params["transition"] = transition
        if setting.get("effect"):
            params["_effect"] = setting["effect"]
        calls.append(("light", "turn_on", params))
    if tick_area_id is not None:
        # Positional guard keeps the compatibility boundary straightforward.
        return await _async_dispatch_tick(
            hass, store, tick_area_id, calls, result["skipped"], context, tick_guard
        )

    prepared = {params["entity_id"]: params for _, _, params in calls}

    def still_allowed(entity_id):
        check_execution_guard(dispatch_guard)
        state = hass.states.get(entity_id)
        return bool(
            entity_id in store.data["settings"]["light_entity_ids"]
            and state and state.state in {"on", "off"} and is_individual_light(hass, state)
            and supports_payload(state, prepared[entity_id])
            and (layout_area_id is None or contains(hass, store, layout_area_id, entity_id))
        )

    if dynamic_commands:
        from .command_limiter import limiter

        for call in calls:
            key, entity = await limiter(hass).dispatch(hass, *call, context, still_allowed)
            result.setdefault(key, []).append(entity)
        return result
    return await async_dispatch(hass, calls, result["skipped"], context, guard=still_allowed, effect_guard=still_allowed)


async def _async_dispatch_tick(hass, store, area_id, calls, skipped, context, tick_guard=None):
    """Stagger calls globally and revalidate after the wait at each dispatch."""
    from .command_limiter import limiter

    result = {"applied": [], "skipped": list(skipped)}
    prepared = {params["entity_id"]: params for _, _, params in calls}

    def allowed(entity_id):
        state = hass.states.get(entity_id)
        return bool(
            state is not None and state.domain == "light" and state.state == "on"
            and entity_id in store.data["settings"]["light_entity_ids"]
            and contains(hass, store, area_id, entity_id)
            and is_individual_light(hass, state)
            and supports_payload(state, prepared[entity_id])
            and (tick_guard is None or tick_guard(entity_id))
        )

    for call in calls:
        key, entity_id = await limiter(hass).dispatch(hass, *call, context, allowed)
        result.setdefault(key, []).append(entity_id)
    return result
