# Geändert für Lichtzentrale
"""Room scenes with validated targets, parallel recall and private persistence."""

from asyncio import Lock
from copy import deepcopy
from uuid import uuid4

from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.util.color import color_hs_to_xy, color_RGB_to_xy, color_xy_to_RGB

from .const import DOMAIN
from .lights import entity_area_id, validate_lights
from .palettes import async_apply_palette, list_palettes
from .rooms import async_dispatch, light_service_data, room_targets, validate_control_options
from .storage import LichtzentraleStore


def _error(message):
    raise ServiceValidationError(message)


def _name(value):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 100:
        _error("Bitte einen Szenennamen mit 1 bis 100 Zeichen angeben.")
    return value.strip()


def _area(hass, area_id):
    if not isinstance(area_id, str) or ar.async_get(hass).async_get_area(area_id) is None:
        _error("Der Raum wurde nicht gefunden.")


def _targets(hass, store, area_id, targets):
    _area(hass, area_id)
    if any(not isinstance(entity_id, str) for entity_id in targets):
        _error("Ungültige Lampenkennung.")
    ids = validate_lights(hass, list(targets))
    allowed = store.data["settings"]["light_entity_ids"]
    if not ids or any(e not in allowed for e in ids):
        _error("Alle Lampen der Szene müssen ausdrücklich freigegeben sein.")
    if any(entity_area_id(hass, e) != area_id for e in ids):
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
            }
        )
    return sorted(result, key=lambda item: item["name"].casefold())


def _decorate(scene):
    result = deepcopy(scene)
    colors = []
    if scene["kind"] == "palette":
        palette = next((p for p in list_palettes() if p["id"] == scene.get("palette_id")), None)
        colors = palette["preview"] if palette else []
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
def list_scenes(store: LichtzentraleStore, area_id=None) -> list[dict]:
    return [
        _decorate(s)
        for s in sorted(store.data["scenes"], key=lambda s: s.get("order", 0))
        if area_id is None or s["area_id"] == area_id
    ]


def _scene(store, scene_id):
    scene = next((s for s in store.data["scenes"] if s["id"] == scene_id), None)
    if scene is None:
        _error("Die Szene wurde nicht gefunden.")
    return scene


async def async_save_scene(hass, store, scene):
    """Validate the entire model before the single atomic Store write."""
    if not isinstance(scene, dict):
        _error("Ungültige Szene.")
    area_id = scene.get("area_id")
    _area(hass, area_id)
    existing = _scene(store, scene["id"]) if scene.get("id") else None
    if existing and existing["area_id"] != area_id:
        _error("Eine Szene kann nicht in einen anderen Raum verschoben werden.")
    kind = scene.get("kind")
    if not isinstance(kind, str) or kind not in {"snapshot", "palette", "hue"}:
        _error("Dieser Szenentyp wird noch nicht unterstützt.")
    favorite = scene.get("favorite", False)
    order = scene.get(
        "order", existing.get("order", 0) if existing else len(list_scenes(store, area_id))
    )
    if not isinstance(favorite, bool) or type(order) is not int or order < 0:
        _error("Ungültige Favoriten- oder Sortierangabe.")
    dynamic = scene.get("dynamic", {"enabled": False, "interval": 60, "transition": 10})
    if not isinstance(dynamic, dict) or dynamic.get("enabled", False) is not False:
        _error("Dynamische Szenen folgen in Stufe 2.")
    result = {
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
        "dynamic": {"enabled": False, "interval": 60, "transition": 10},
    }
    if kind == "snapshot":
        lights = scene.get("lights")
        if not isinstance(lights, dict) or len(lights) > 500:
            _error("Ungültige Lampen der Szene.")
        _targets(hass, store, area_id, lights)
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
        if not isinstance(scene.get("palette_id"), str) or scene["palette_id"] not in {
            p["id"] for p in list_palettes()
        }:
            _error("Die Farbpalette wurde nicht gefunden.")
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
    await store.async_save_scene(result, is_update=existing is not None)
    return _decorate(result)


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


async def async_delete_scene(store, scene_id):
    _scene(store, scene_id)
    await store.async_delete_scene(scene_id)


async def async_reorder_scenes(store, area_id, scene_ids):
    await store.async_reorder_scenes(area_id, scene_ids)
    return list_scenes(store, area_id)


async def async_apply_scene(
    hass: HomeAssistant, store: LichtzentraleStore, scene_id: str, context: Context | None = None
):
    """Serialize recalls per room; dispatch each recall's individual lamps in parallel."""
    initial = _scene(store, scene_id)
    locks = hass.data.setdefault(DOMAIN, {}).setdefault("scene_locks", {})
    async with locks.setdefault(initial["area_id"], Lock()):
        scene = _scene(store, scene_id)
        area_id = scene["area_id"]
        _area(hass, area_id)
        if scene.get("dynamic", {}).get("enabled"):
            _error("Dynamische Szenen folgen in Stufe 2.")
        if scene["kind"] == "palette":
            result = await async_apply_palette(
                hass,
                store,
                scene["palette_id"],
                room_targets(hass, store, area_id),
                brightness=scene.get("brightness"),
                context=context,
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
            await hass.services.async_call(
                "hue",
                "activate_scene",
                {"entity_id": entity_id, "dynamic": False},
                blocking=True,
                context=context,
            )
            result = {"applied": targets, "skipped": []}
        else:
            targets = _targets(hass, store, area_id, scene["lights"])
            commands = []
            skipped = []
            for entity_id in targets:
                state = hass.states.get(entity_id)
                if state.state in {"unknown", "unavailable"}:
                    skipped.append(entity_id)
                    continue
                value = scene["lights"][entity_id]
                validate_control_options(**value)
                payload = light_service_data(state, **value)
                if payload is None:
                    skipped.append(entity_id)
                else:
                    commands.append((state.domain, *payload))
            result = await async_dispatch(hass, commands, skipped, context)
        if not result.get("skipped") and not result.get("failed") and result["applied"]:
            await store.async_set_last_scene(area_id, scene_id)
        return result
