# Geändert für Lichtzentrale
"""Room scenes with validated targets, parallel recall and private persistence."""

import math
from asyncio import Lock
from copy import deepcopy
from uuid import uuid4

from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.util.color import (
    color_hs_to_xy,
    color_RGB_to_xy,
    color_temperature_to_rgb,
    color_xy_to_RGB,
)

from .const import DOMAIN
from .dynamic_scenes import manager, stop_dynamic, validate_dynamic
from .lights import entity_area_id, validate_lights
from .palette_catalogue import get_palette, list_palettes
from .palettes import async_apply_palette
from .positions import validate_distribution
from .rooms import (
    async_dispatch,
    check_execution_guard,
    light_service_data,
    locked_room,
    room_targets,
    validate_control_options,
    validate_transition,
)
from .scene_settings import snapshot_values, validate_lamp_settings, validate_wave_order
from .storage import LichtzentraleStore


def _error(message):
    raise ServiceValidationError(message)


def _name(value):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 100:
        _error("Bitte einen Szenennamen mit 1 bis 100 Zeichen angeben.")
    return value.strip()


def _area(hass, area_id, store=None):
    if store is not None:
        from .zones import validate_area

        return validate_area(hass, store, area_id)
    if not isinstance(area_id, str) or ar.async_get(hass).async_get_area(area_id) is None:
        _error("Der Raum wurde nicht gefunden.")


def _targets(hass, store, area_id, targets):
    _area(hass, area_id, store)
    if any(not isinstance(entity_id, str) for entity_id in targets):
        _error("Ungültige Lampenkennung.")
    ids = validate_lights(hass, list(targets))
    allowed = store.data["settings"]["light_entity_ids"]
    if not ids or any(e not in allowed for e in ids):
        _error("Alle Lampen der Szene müssen ausdrücklich freigegeben sein.")
    from .zones import contains

    if any(not contains(hass, store, area_id, e) for e in ids):
        _error("Alle Lampen der Szene müssen zum gewählten Raum gehören.")
    return ids


@callback
def hue_scene_targets(hass: HomeAssistant, entity_id: str) -> list[str]:
    """Resolve actual Hue V2 resource actions, never trust an arbitrary scene.* ID.

    HA does not publish a Hue scene's targets as state attributes. The loaded
    Hue config entry exposes its native aiohue resource controller; fail closed
    when this data is unavailable or a smart/group target cannot be verified.
    """
    registry = er.async_get(hass)
    entry = registry.async_get(entity_id)
    state = hass.states.get(entity_id)
    if (
        entry is None
        or entry.domain != "scene"
        or entry.platform != "hue"
        or entry.disabled_by is not None
        or state is None
    ):
        _error("Bitte eine vorhandene Szene der Hue Bridge auswählen.")
    config = hass.config_entries.async_get_entry(entry.config_entry_id)
    bridge = getattr(config, "runtime_data", None)
    api = getattr(bridge, "api", None)
    controller = getattr(api, "scenes", None)
    try:
        resource = controller.get(entry.unique_id) if controller is not None else None
    except KeyError, AttributeError:
        resource = None
    actions = getattr(resource, "actions", None)
    if not actions:
        _error(
            "Die Ziele dieser Hue-Szene lassen sich nicht sicher prüfen. Smart-Szenen werden noch nicht unterstützt."
        )
    targets = []
    for action in actions:
        target = action.target
        if getattr(target.rtype, "value", target.rtype) != "light":
            _error("Die Hue-Szene enthält nicht unterstützte Gruppenziele.")
        target_id = registry.async_get_entity_id("light", "hue", target.rid)
        lamp = registry.async_get(target_id) if target_id else None
        if lamp is None or lamp.config_entry_id != entry.config_entry_id:
            _error("Eine Lampe der Hue-Szene wurde nicht gefunden.")
        targets.append(target_id)
    return list(dict.fromkeys(targets))


@callback
def hue_scene_preview(hass: HomeAssistant, entity_id: str) -> list[str]:
    """Generate swatches from native Hue action colors, never from Hue images."""
    entry = er.async_get(hass).async_get(entity_id)
    if entry is None or entry.platform != "hue":
        return []
    config = hass.config_entries.async_get_entry(entry.config_entry_id)
    controller = getattr(
        getattr(getattr(config, "runtime_data", None), "api", None), "scenes", None
    )
    try:
        resource = controller.get(entry.unique_id) if controller is not None else None
    except KeyError, AttributeError:
        return []
    colors = []
    for item in getattr(resource, "actions", []) or []:
        action = getattr(item, "action", None)
        xy = getattr(getattr(action, "color", None), "xy", None)
        mirek = getattr(getattr(action, "color_temperature", None), "mirek", None)
        if getattr(getattr(action, "on", None), "on", None) is False:
            rgb = (41, 50, 56)
        elif xy is not None and all(
            type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1
            for v in (getattr(xy, "x", None), getattr(xy, "y", None))
        ):
            rgb = color_xy_to_RGB(xy.x, xy.y)
        elif type(mirek) in (int, float) and math.isfinite(mirek) and mirek > 0:
            rgb = color_temperature_to_rgb(max(1000, min(40000, 1_000_000 / mirek)))
        else:
            continue
        colors.append("#%02x%02x%02x" % tuple(round(v) for v in rgb))
    return colors[:8]


@callback
def list_hue_scenes(hass: HomeAssistant, store: LichtzentraleStore, area_id=None) -> list[dict]:
    """Offer only native Hue scenes; expose why a candidate cannot be imported."""
    result = []
    for state in hass.states.async_all("scene"):
        entry = er.async_get(hass).async_get(state.entity_id)
        if entry is None or entry.platform != "hue" or entry.disabled_by is not None:
            continue
        scene_area = entity_area_id(hass, state.entity_id)
        error = None
        try:
            targets = hue_scene_targets(hass, state.entity_id)
            target_areas = {entity_area_id(hass, target) for target in targets}
            if scene_area is None and len(target_areas) == 1:
                scene_area = next(iter(target_areas))
            _targets(hass, store, area_id or scene_area, targets)
        except ServiceValidationError as exc:
            error = str(exc)
        if area_id is not None and scene_area not in {None, area_id}:
            continue
        result.append(
            {
                "entity_id": state.entity_id,
                "name": state.name,
                "area_id": scene_area,
                "available": error is None and state.state != "unavailable",
                "reason": error,
                "preview": hue_scene_preview(hass, state.entity_id) if error is None else [],
            }
        )
    return sorted(result, key=lambda item: item["name"].casefold())


def _decorate(scene, hass=None, store=None):
    result = deepcopy(scene)
    if scene["kind"] == "seasonal" and store is not None:
        from .seasonal_scenes import resolve_scene

        try:
            concrete, info = resolve_scene(hass or store._hass, store, scene)
            result.update(info)
            result["preview"] = _decorate(concrete, hass, store)["preview"]
        except ServiceValidationError as error:
            result.update(resolved_scene_id=None, resolved_name=None, resolved_season=None,
                          resolution_note=str(error), preview=["#b6c9ce", "#8396a1"])
        return result
    colors = []
    if scene["kind"] == "palette":
        palette = next((p for p in list_palettes(store) if p["id"] == scene.get("palette_id")), None)
        colors = palette["preview"] if palette else []
    elif scene["kind"] == "hue":
        colors = (hue_scene_preview(hass, scene["hue_scene"]) if hass else []) or scene.get(
            "hue_preview", []
        )
    else:
        for value in scene.get("lights", {}).values():
            if not value.get("on"):
                colors.append("#293238")
            elif "xy" in value:
                rgb = color_xy_to_RGB(*value["xy"])
                colors.append("#%02x%02x%02x" % rgb)
            elif "color_temp_kelvin" in value:
                colors.append("#ffce8a" if value["color_temp_kelvin"] < 4000 else "#e4f0ff")
            else:
                colors.append("#f5e8c8")
    result["preview"] = colors[:8] or ["#b6c9ce", "#8396a1"]
    return result


@callback
def list_scenes(store: LichtzentraleStore, area_id=None, hass=None) -> list[dict]:
    return [
        _decorate(s, hass, store)
        for s in sorted(store.data["scenes"], key=lambda s: s.get("order", 0))
        if area_id is None or s["area_id"] == area_id
    ]


def _scene(store, scene_id):
    scene = next((s for s in store.data["scenes"] if s["id"] == scene_id), None)
    if scene is None:
        _error("Die Szene wurde nicht gefunden.")
    return scene


def validate_scene(hass, store, scene, *, palette_override=None):
    """Validate a complete saved or unsaved scene without changing any state."""
    if not isinstance(scene, dict):
        _error("Ungültige Szene.")
    area_id = scene.get("area_id")
    _area(hass, area_id, store)
    existing = _scene(store, scene["id"]) if scene.get("id") else None
    if existing and existing["area_id"] != area_id:
        _error("Eine Szene kann nicht in einen anderen Raum verschoben werden.")
    kind = scene.get("kind")
    if not isinstance(kind, str) or kind not in {"snapshot", "palette", "hue", "seasonal"}:
        _error("Dieser Szenentyp wird noch nicht unterstützt.")
    favorite = scene.get("favorite", False)
    order = scene.get(
        "order", existing.get("order", 0) if existing else len(list_scenes(store, area_id))
    )
    if not isinstance(favorite, bool) or type(order) is not int or order < 0:
        _error("Ungültige Favoriten- oder Sortierangabe.")
    dynamic = scene.get("dynamic", {"enabled": False, "interval": 60, "transition": 10})
    dynamic = validate_dynamic(dynamic, kind)
    verteilung = validate_distribution(scene.get("verteilung", "zufall"))
    if dynamic["welle"] and verteilung == "zufall" and not scene.get("wave_order"):
        _error("Für eine Welle bitte eine räumliche Verteilung auswählen.")
    night = scene.get("night", existing.get("night", False) if existing else False)
    if type(night) is not bool:
        _error("Die Nachtlicht-Kennzeichnung muss ein Wahrheitswert sein.")
    result = {
        **deepcopy(existing or {}),
        "night": night,
        "id": existing["id"] if existing else str(uuid4()),
        "name": _name(scene.get("name")),
        "area_id": area_id,
        "kind": kind,
        "lights": {},
        "palette_id": None,
        "brightness": None,
        "hue_scene": None,
        "favorite": favorite,
        "order": order,
        "dynamic": dynamic,
        "verteilung": verteilung,
    }
    if kind == "seasonal":
        from .seasonal_scenes import validate_seasonal

        if scene.get("lamp_settings") or scene.get("wave_order"):
            _error("Lampenwerte und Welle werden in den zugeordneten Szenen eingestellt.")
        result["seasonal"] = validate_seasonal(store, {**result, "seasonal": scene.get("seasonal")}, existing=existing)
        result.update(lamp_settings={}, wave_order=[])
        return result
    result.pop("seasonal", None)
    palette = None
    if kind == "snapshot":
        lights = scene.get("lights")
        if not isinstance(lights, dict) or len(lights) > 500:
            _error("Ungültige Lampen der Szene.")
        _targets(hass, store, area_id, lights)
        validate_control_options(brightness=scene.get("brightness"))
        result["brightness"] = scene.get("brightness")
        for entity_id, value in lights.items():
            if not isinstance(value, dict) or type(value.get("on")) is not bool:
                _error("Jede Lampe benötigt einen Ein/Aus-Zustand.")
            if set(value) - {"on", "brightness", "xy", "color_temp_kelvin"}:
                _error("Unbekannte Lampeneinstellung.")
            validate_control_options(**value)
            if entity_id.startswith("switch.") and set(value) != {"on"}:
                _error("Lichtschalter erlauben ausschließlich Ein/Aus.")
            result["lights"][entity_id] = deepcopy(value)
    elif kind == "palette":
        if not isinstance(scene.get("palette_id"), str):
            _error("Die Farbpalette wurde nicht gefunden.")
        palette = palette_override or get_palette(store, scene["palette_id"])
        brightness = scene.get("brightness")
        validate_control_options(brightness=brightness)
        _targets(hass, store, area_id, room_targets(hass, store, area_id))
        result.update(palette_id=scene["palette_id"], brightness=brightness)
    else:
        hue_id = scene.get("hue_scene")
        if not isinstance(hue_id, str):
            _error("Bitte eine Hue-Szene auswählen.")
        _targets(hass, store, area_id, hue_scene_targets(hass, hue_id))
        result["hue_scene"] = hue_id
        result["hue_preview"] = hue_scene_preview(hass, hue_id)
    targets = (result["lights"] if kind == "snapshot" else hue_scene_targets(hass, result["hue_scene"])
               if kind == "hue" else room_targets(hass, store, area_id))
    settings = scene.get("lamp_settings", existing.get("lamp_settings", {}) if existing else {})
    if kind == "hue" and settings:
        _error("Lampenwerte bitte als Palette oder Momentaufnahme bearbeiten.")
    result["lamp_settings"] = validate_lamp_settings(hass, settings, targets, palette)
    result["wave_order"] = validate_wave_order(scene.get("wave_order", existing.get("wave_order", []) if existing else []), targets)
    return result


async def async_save_scene(hass, store, scene):
    result = validate_scene(hass, store, scene)
    await store.async_save_scene(result, is_update=bool(scene.get("id")))
    return _decorate(result, hass, store)


async def async_apply_scene_draft(hass, store, scene, context=None, *, palette_override=None, targets=None, dispatch_guard=None):
    """Run a validated draft through the same scene executor, never a temporary Store row."""
    result = validate_scene(hass, store, scene, palette_override=palette_override)
    async with locked_room(hass, store, result["area_id"]):
        return await async_apply_scene_locked(hass, store, result["id"], context,
            scene_override=result, palette_override=palette_override, preview_targets=targets,
            dispatch_guard=dispatch_guard, persist=False)



async def async_snapshot(hass, store, area_id, name):
    lights = {}
    skipped = []
    for entity_id in room_targets(hass, store, area_id):
        state = hass.states.get(entity_id)
        if state.state not in {"on", "off"}:
            skipped.append(entity_id)
            continue
        value = {"on": state.state == "on"}
        attrs = state.attributes
        if state.domain == "light" and value["on"]:
            if isinstance(attrs.get("brightness"), int) and 1 <= attrs["brightness"] <= 255:
                value["brightness"] = attrs["brightness"]
            mode = attrs.get("color_mode")
            if mode == "color_temp" and attrs.get("color_temp_kelvin"):
                value["color_temp_kelvin"] = attrs["color_temp_kelvin"]
            elif mode in {"xy", "hs", "rgb", "rgbw", "rgbww"}:
                xy = attrs.get("xy_color")
                if xy is None and attrs.get("rgb_color"):
                    xy = color_RGB_to_xy(*attrs["rgb_color"])
                if xy is None and attrs.get("hs_color"):
                    xy = color_hs_to_xy(*attrs["hs_color"])
                if xy is not None:
                    value["xy"] = list(xy)
        lights[entity_id] = value
    scene = await async_save_scene(
        hass, store, {"name": name, "area_id": area_id, "kind": "snapshot", "lights": lights}
    )
    return {"scene": scene, "skipped": skipped}


async def async_delete_scene(store, scene_id, hass=None):
    scene = _scene(store, scene_id)
    if hass is None:
        await store.async_delete_scene(scene_id)
        return
    area_id = scene["area_id"]
    locks = hass.data.setdefault(DOMAIN, {}).setdefault("scene_locks", {})
    async with locks.setdefault(area_id, Lock()):
        await store.async_delete_scene(scene_id)
        if active := manager(hass):
            run = active.active.get(area_id)
            if run and run["scene"]["id"] == scene_id:
                await active.stop(area_id)


async def async_reorder_scenes(store, area_id, scene_ids):
    await store.async_reorder_scenes(area_id, scene_ids)
    return list_scenes(store, area_id)


async def async_apply_scene(
    hass: HomeAssistant, store: LichtzentraleStore, scene_id: str, context: Context | None = None,
    *, transition=None, guard=None, dispatch_guard=None
):
    """Serialize recalls per room; dispatch each recall's individual lamps in parallel."""
    initial = _scene(store, scene_id)
    async with locked_room(hass, store, initial["area_id"]):
        return await async_apply_scene_locked(
            hass, store, scene_id, context, transition=transition, guard=guard, dispatch_guard=dispatch_guard
        )


def _hue_subset_values(hass, entity_id, targets):
    """Project verifiable native Hue actions without activating the whole scene."""
    hue_scene_targets(hass, entity_id)
    registry = er.async_get(hass)
    entry = registry.async_get(entity_id)
    resource = hass.config_entries.async_get_entry(entry.config_entry_id).runtime_data.api.scenes.get(entry.unique_id)
    values = {}
    for item in resource.actions:
        target = registry.async_get_entity_id("light", "hue", item.target.rid)
        if target not in targets:
            continue
        action = getattr(item, "action", None)
        on = getattr(getattr(action, "on", None), "on", None)
        if type(on) is not bool:
            continue
        value = {"on": on}
        if on:
            # Gradients/effects cannot be faithfully expressed as a single color.
            if any(getattr(action, key, None) is not None for key in ("gradient", "effects", "effects_v2")):
                continue
            brightness = getattr(getattr(action, "dimming", None), "brightness", None)
            if brightness is not None:
                if type(brightness) not in (int, float) or not math.isfinite(brightness) or not 0 <= brightness <= 100:
                    continue
                value["brightness"] = max(1, round(brightness * 255 / 100))
            xy = getattr(getattr(action, "color", None), "xy", None)
            mirek = getattr(getattr(action, "color_temperature", None), "mirek", None)
            if mirek is not None:
                if type(mirek) not in (int, float) or not math.isfinite(mirek) or mirek <= 0:
                    continue
                value["color_temp_kelvin"] = round(1_000_000 / mirek)
            elif xy is not None:
                value["xy"] = [getattr(xy, "x", None), getattr(xy, "y", None)]
        try:
            validate_control_options(**value)
        except ServiceValidationError:
            continue
        values[target] = value
    return values


async def _async_pause_subset_adaptive(hass, store, targets, context, dispatch_guard):
    """Pause only selected lamps; never switch off an entire AL group."""
    from .adaptive import ADAPTIVE_DOMAIN, _primary

    if not hass.data.get(ADAPTIVE_DOMAIN):
        return
    for state in hass.states.async_all("switch"):
        try:
            primary = _primary(hass, state.entity_id)
        except ServiceValidationError:
            continue
        lights = getattr(primary, "lights", None)
        if not isinstance(lights, (list, tuple, set)):
            continue
        selected = [e for e in targets if e.startswith("light.") and e in lights]
        if not selected or state.state == "off":
            continue
        if state.state != "on":
            _error("Adaptive Lighting ist nicht erreichbar.")
        check_execution_guard(dispatch_guard)
        await hass.services.async_call(
            ADAPTIVE_DOMAIN, "set_manual_control",
            {"entity_id": state.entity_id, "lights": selected, "manual_control": True},
            blocking=True, context=context,
        )


async def async_apply_scene_subset(hass, store, scene_id, entity_ids, context=None, *, transition=None, guard=None, dispatch_guard=None):
    """Recall an inherited scene only on shared lamps, without a broader loop.

    Keep palette placement relative to the complete source. Hue is projected to
    individual light actions, never hue.activate_scene. Unsupported native Hue
    actions fail closed. A partial recall must not mark the source as recalled.
    """
    from .selected_lights import _locked_targets
    from .zones import contains

    initial = _scene(store, scene_id)
    if initial["kind"] == "seasonal":
        from .seasonal_scenes import decorate_result, guard_resolution, resolve_scene

        concrete, info = resolve_scene(hass, store, initial)
        def stable_season():
            return guard_resolution(hass, store, initial, concrete["id"], dispatch_guard)
        result = await async_apply_scene_subset(hass, store, concrete["id"], entity_ids, context,
            transition=transition, guard=guard, dispatch_guard=stable_season)
        return decorate_result(result, initial, info)
    area_id = initial["area_id"]
    async with _locked_targets(hass, store, entity_ids):
        check_execution_guard(guard)
        validate_transition(transition)
        scene = _scene(store, scene_id)
        targets = _targets(hass, store, area_id, entity_ids)

        def stable():
            check_execution_guard(guard)
            check_execution_guard(dispatch_guard)
            if _scene(store, scene_id) != scene:
                _error("Die Szene hat sich geändert. Bitte erneut versuchen.")
            _targets(hass, store, area_id, targets)
            return True

        stable()
        # A subset recall must not depend on unrelated missing/revoked source lamps.
        settings = scene.get("lamp_settings", {})
        wave_order = scene.get("wave_order", [])
        if not isinstance(settings, dict) or not isinstance(wave_order, list):
            _error("Ungültige Lampen- oder Wellen-Einstellungen.")
        palette = get_palette(store, scene["palette_id"]) if scene["kind"] == "palette" else None
        validate_lamp_settings(hass, {e: value for e, value in settings.items() if e in targets}, targets, palette, capabilities=False)
        validate_wave_order([e for e in wave_order if e in targets], targets)
        if scene["kind"] == "hue":
            hue_state = hass.states.get(scene["hue_scene"])
            if hue_state is None or hue_state.state == "unavailable":
                return {"applied": [], "skipped": targets}
            values = _hue_subset_values(hass, scene["hue_scene"], targets)
        elif scene["kind"] == "snapshot":
            values = {e: snapshot_values(scene, e) for e in targets if e in scene["lights"]}
            for value in values.values():
                validate_control_options(**value)
        else:
            values = {}
        from .dynamic_scenes import async_exclude_targets

        await async_exclude_targets(hass, targets)
        stable()
        await _async_pause_subset_adaptive(hass, store, targets, context, stable)
        if scene["kind"] == "palette":
            result = await async_apply_palette(
                hass, store, scene["palette_id"], targets, brightness=scene.get("brightness"),
                context=context, manage=False, layout_area_id=area_id,
                layout_targets=[e for e in store.data["settings"]["light_entity_ids"]
                                if contains(hass, store, area_id, e)],
                verteilung=scene.get("verteilung", "zufall"),
                welle=scene.get("dynamic", {}).get("welle", False),
                transition=scene["dynamic"]["transition"] if transition is None else transition,
                schedule_transition=transition is not None, dispatch_guard=stable,
                lamp_settings=scene.get("lamp_settings"), wave_order=scene.get("wave_order"),
            )
        else:
            off_targets = [e for e, value in values.items() if not value["on"]]
            captured = await store.async_remember_light_states(off_targets) if off_targets else {}
            stable()
            calls, skipped, prepared = [], [], {}
            for entity in targets:
                state = hass.states.get(entity)
                if (entity not in values or state is None or state.state not in {"on", "off"}
                        or (entity in captured and state is not captured[entity])):
                    skipped.append(entity)
                    continue
                payload = light_service_data(state, transition=transition, **values[entity])
                if payload is None:
                    skipped.append(entity)
                    continue
                calls.append((state.domain, *payload))
                prepared[entity] = state

            def allowed(entity):
                stable()
                return hass.states.get(entity) is prepared[entity]

            result = await async_dispatch(hass, calls, skipped, context, guard=allowed)
            if scene["kind"] == "hue" and any(e not in values for e in targets):
                result.setdefault("notes", []).append("Einzelne Hue-Szenenwerte lassen sich nicht sicher auf gemeinsame Lampen übertragen.")
        if result.get("applied") and (scene.get("dynamic", {}).get("enabled") or (
                scene["kind"] == "hue" and hue_state.attributes.get("is_dynamic"))):
            result.setdefault("notes", []).append("Die geerbte Szene wurde nur auf den gemeinsamen Lampen statisch wiederhergestellt.")
        return result


async def async_apply_scene_locked(hass, store, scene_id, context=None, *, transition=None, guard=None, dispatch_guard=None, scene_override=None, palette_override=None, preview_targets=None, persist=True):
    """Recall while the caller holds this room's scene lock (including room-on)."""
    context = context or Context()
    check_execution_guard(guard)
    validate_transition(transition)
    scene = deepcopy(scene_override) if scene_override is not None else _scene(store, scene_id)
    if scene["kind"] == "seasonal":
        from .seasonal_scenes import decorate_result, guard_resolution, resolve_scene

        concrete, info = resolve_scene(hass, store, scene)
        def stable_season():
            return guard_resolution(hass, store, scene, concrete["id"], dispatch_guard)
        result = await async_apply_scene_locked(hass, store, concrete["id"], context,
            transition=transition, guard=guard, dispatch_guard=stable_season, persist=persist,
            preview_targets=preview_targets, palette_override=palette_override)
        incomplete = [e for e in result.get("skipped", [])
                      if concrete["kind"] != "palette" or not e.startswith("switch.")]
        if persist and result.get("applied") and not result.get("failed") and not incomplete:
            # Keep the selectable wrapper on the tile, while dynamics owns the concrete snapshot.
            stable_season()
            await store.async_set_last_scene(scene["area_id"], scene_id)
        return decorate_result(result, scene, info)
    area_id = scene["area_id"]
    _area(hass, area_id, store)
    from .adaptive import async_pause_adaptive

    validate_dynamic(scene.get("dynamic", {}), scene["kind"])
    validate_distribution(scene.get("verteilung", "zufall"))
    if scene.get("dynamic", {}).get("welle") and scene.get("verteilung", "zufall") == "zufall" and not scene.get("wave_order"):
        _error("Für eine Welle bitte eine räumliche Verteilung auswählen.")
    # Validate all targets before pausing another integration or replacing a loop.
    checked = (
        hue_scene_targets(hass, scene["hue_scene"])
        if scene["kind"] == "hue"
        else scene["lights"]
        if scene["kind"] == "snapshot"
        else room_targets(hass, store, area_id)
    )
    _targets(hass, store, area_id, checked)
    palette = palette_override or (get_palette(store, scene["palette_id"]) if scene["kind"] == "palette" else None)
    validate_lamp_settings(hass, scene.get("lamp_settings", {}), checked, palette, capabilities=False)
    validate_wave_order(scene.get("wave_order", []), checked)
    execution_targets = list(checked) if preview_targets is None else [e for e in checked if e in preview_targets]
    if not execution_targets:
        return {"applied": [], "skipped": list(checked)}
    if scene["kind"] == "snapshot":
        for value in scene["lights"].values():
            validate_control_options(**value)
    await stop_dynamic(hass, area_id)
    if scene["kind"] in {"palette", "hue"} or any("xy" in v for v in scene["lights"].values()):
        if persist:
            await async_pause_adaptive(hass, store, area_id, context=context, dispatch_guard=dispatch_guard)
        else:
            await _async_pause_subset_adaptive(hass, store, execution_targets, context, dispatch_guard)
    if scene["kind"] == "palette":
        result = await async_apply_palette(
            hass,
            store,
            scene["palette_id"],
            execution_targets,
            brightness=scene.get("brightness"),
            context=context,
            manage=False,
            layout_area_id=area_id,
            verteilung=scene.get("verteilung", "zufall"),
            welle=scene.get("dynamic", {}).get("welle", False),
            transition=scene["dynamic"]["transition"] if transition is None else transition,
            schedule_transition=transition is not None,
            dispatch_guard=dispatch_guard,
            lamp_settings=scene.get("lamp_settings"), wave_order=scene.get("wave_order"),
            gentle=scene.get("dynamic", {}).get("gentle", False), palette_override=palette_override,
            dynamic_commands=scene.get("dynamic", {}).get("enabled", False),
        )
    elif scene["kind"] == "hue":
        entity_id = scene["hue_scene"]
        targets = _targets(hass, store, area_id, hue_scene_targets(hass, entity_id))
        unavailable = [
            e for e in targets if hass.states.get(e).state in {"unknown", "unavailable"}
        ]
        state = hass.states.get(entity_id)
        if unavailable or state.state == "unavailable":
            return {"applied": [], "skipped": targets}
        check_execution_guard(dispatch_guard)
        await hass.services.async_call(
            "hue",
            "activate_scene",
            # Dynamische Hue-Szenen auch dynamisch starten (Farben wandern weiter).
            {
                "entity_id": entity_id,
                "dynamic": bool(state.attributes.get("is_dynamic")),
                **({"transition": transition} if transition is not None else {}),
            },
            blocking=True,
            context=context,
        )
        result = {"applied": targets, "skipped": []}
    else:
        targets = _targets(hass, store, area_id, execution_targets)
        off_targets = [entity_id for entity_id in targets if snapshot_values(scene, entity_id)["on"] is False]
        captured = await store.async_remember_light_states(off_targets) if off_targets and persist else {}
        targets = _targets(hass, store, area_id, execution_targets)
        commands = []
        skipped = []
        prepared = {}
        for entity_id in targets:
            state = hass.states.get(entity_id)
            if state.state in {"unknown", "unavailable"} or (
                entity_id in captured and state is not captured[entity_id]
            ):
                skipped.append(entity_id)
                continue
            value = snapshot_values(scene, entity_id)
            validate_control_options(**value)
            payload = light_service_data(state, transition=transition, **value)
            if payload is None:
                skipped.append(entity_id)
            else:
                commands.append((state.domain, *payload))
                prepared[entity_id] = state

        def still_allowed(entity_id):
            check_execution_guard(dispatch_guard)
            try:
                _targets(hass, store, area_id, [entity_id])
            except ServiceValidationError:
                return False
            return hass.states.get(entity_id) is prepared[entity_id]

        result = await async_dispatch(hass, commands, skipped, context, guard=still_allowed)
    # Palette switches are intentionally excluded, not incomplete light recalls.
    incomplete = [
        e
        for e in result.get("skipped", [])
        if scene["kind"] != "palette" or not e.startswith("switch.")
    ]
    if persist and not incomplete and not result.get("failed") and result["applied"]:
        await store.async_set_last_scene(area_id, scene_id)
    if (
        (scene.get("dynamic", {}).get("enabled") or any(v.get("mode") == "moon" for v in scene.get("lamp_settings", {}).values()))
        and result["applied"]
        and not result.get("failed")
    ):
        if active := manager(hass):
            await active.start(
                scene, context, result["applied"], initial_transition=transition,
                persist=persist, palette_override=palette_override, dispatch_guard=dispatch_guard
            )
    return result
