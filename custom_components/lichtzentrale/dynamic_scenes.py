# Geändert für Lichtzentrale
"""Cancellable room-local palette loops adapted from hass-scene_presets.

Unlike the upstream loop, targets are revalidated on every tick and tasks are
owned by the integration, never by an object's destructor.
"""

import asyncio
import logging
import math
from copy import deepcopy

from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN
from .rooms import room_targets

_LOGGER = logging.getLogger(__name__)


def validate_dynamic(value, kind):
    if not isinstance(value, dict) or set(value) - {"enabled", "interval", "transition", "welle"}:
        raise ServiceValidationError("Ungültige Dynamik-Einstellungen.")
    enabled = value.get("enabled", False)
    wave = value.get("welle", False)
    if type(wave) is not bool or (wave and kind != "palette"):
        raise ServiceValidationError("Welle ist nur für Farbpaletten verfügbar.")
    interval = value.get("interval", 60)
    transition = value.get("transition", 10)
    if type(enabled) is not bool or any(
        type(v) not in (int, float) or not math.isfinite(v) for v in (interval, transition)
    ):
        raise ServiceValidationError("Ungültige Dynamik-Einstellungen.")
    if not 5 <= interval <= 3600 or not 0 <= transition <= min(interval, 60):
        raise ServiceValidationError(
            "Intervall: 5–3600 Sekunden; Übergang: 0–60 Sekunden und höchstens das Intervall."
        )
    if enabled and kind != "palette":
        raise ServiceValidationError("Dynamik ist nur für Farbpaletten verfügbar.")
    return {"enabled": enabled, "interval": interval, "transition": transition, "welle": wave}


class DynamicSceneManager:
    def __init__(self, hass, store):
        self.hass, self.store = hass, store
        self.active = {}
        self.closed = False

    def list(self):
        return [
            {
                "scene_id": r["scene"]["id"],
                "area_id": area,
                "name": r["scene"]["name"],
                "interval": r["scene"]["dynamic"]["interval"],
                "transition": r["scene"]["dynamic"]["transition"],
                "welle": r["scene"]["dynamic"].get("welle", False),
                "verteilung": r["scene"].get("verteilung", "zufall"),
            }
            for area, r in self.active.items()
        ]

    @staticmethod
    def _unsubscribe(run):
        if unsubscribe := run.pop("unsubscribe", None):
            unsubscribe()

    async def stop(self, area_id):
        run = self.active.pop(area_id, None)
        if run:
            self._unsubscribe(run)
            run["task"].cancel()
            await asyncio.gather(run["task"], return_exceptions=True)
        return {"stopped": run is not None}

    async def shutdown(self):
        self.closed = True
        for area in list(self.active):
            await self.stop(area)

    async def start(self, scene, context, applied_targets=None, *, initial_transition=None):
        await self.stop(scene["area_id"])
        if self.closed:
            raise ServiceValidationError("Lichtzentrale ist nicht geladen.")
        targets = [
            e
            for e in room_targets(self.hass, self.store, scene["area_id"])
            if e.startswith("light.")
        ]
        layout_targets = list(targets)
        if applied_targets is not None:
            targets = [e for e in targets if e in applied_targets]
        if not targets:
            return
        run = {
            "scene": deepcopy(scene),
            "targets": targets,
            "context": context,
            "layout_targets": layout_targets,
            "initial_transition": initial_transition or 0,
        }

        @callback
        def changed(event):
            if not any((s := self.hass.states.get(e)) and s.state == "on" for e in targets):
                if self.active.get(scene["area_id"]) is run:
                    self.active.pop(scene["area_id"], None)
                self._unsubscribe(run)
                run["task"].cancel()

        run["unsubscribe"] = async_track_state_change_event(self.hass, targets, changed)
        self.active[scene["area_id"]] = run
        run["task"] = self.hass.async_create_background_task(
            self._loop(run), "Lichtzentrale Dynamik"
        )

    async def tick(self, run, offset):
        from .palettes import async_apply_palette

        scene = run["scene"]
        current = next((s for s in self.store.data["scenes"] if s["id"] == scene["id"]), None)
        execution_fields = (
            "kind",
            "area_id",
            "lights",
            "palette_id",
            "brightness",
            "dynamic",
            "hue_scene",
            "verteilung",
        )
        if current is None or any(current.get(key) != scene.get(key) for key in execution_fields):
            return False
        # Cosmetic edits should neither stop playback nor leave a stale title.
        scene["name"] = current["name"]
        # Never grow the original target set after starting. Registry changes,
        # permission removal and unavailable/off entities take effect each tick.
        allowed = set(_current_targets(self.hass, self.store, scene["area_id"]))
        targets = [
            e
            for e in run["targets"]
            if e.startswith("light.")
            and e in allowed
            and (s := self.hass.states.get(e))
            and s.state == "on"
        ]
        if not targets:
            return False
        result = await async_apply_palette(
            self.hass,
            self.store,
            scene["palette_id"],
            targets,
            scene.get("brightness"),
            scene["dynamic"]["transition"],
            run["context"],
            color_offset=offset,
            manage=False,
            verteilung=scene.get("verteilung", "zufall"),
            welle=scene["dynamic"].get("welle", False),
            layout_targets=run.get("layout_targets", run["targets"]),
            tick_area_id=scene["area_id"],
        )
        if result.get("failed"):
            _LOGGER.warning("Dynamische Szene wurde nach einem Gerätefehler gestoppt")
            return False
        return bool(result.get("applied"))

    async def _loop(self, run):
        scene = run["scene"]
        try:
            offset = 1
            while True:
                await asyncio.sleep(max(
                    scene["dynamic"]["interval"],
                    run.get("initial_transition", 0) if offset == 1 else 0,
                ))
                if not await self.tick(run, offset):
                    return
                offset += 1
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Dynamische Szene wurde nach einem Fehler gestoppt")
        finally:
            self._unsubscribe(run)
            if self.active.get(scene["area_id"]) is run:
                self.active.pop(scene["area_id"], None)


def manager(hass):
    return hass.data.get(DOMAIN, {}).get("dynamic")


async def stop_dynamic(hass, area_id):
    active = manager(hass)
    return await active.stop(area_id) if active else {"stopped": False}


async def async_stop_room(hass, store, area_id, context=None):
    """Serialize the public stop action with recalls and room controls."""
    from asyncio import Lock

    _current_targets(hass, store, area_id)
    locks = hass.data.setdefault(DOMAIN, {}).setdefault("scene_locks", {})
    async with locks.setdefault(area_id, Lock()):
        stopped = await stop_dynamic(hass, area_id)
        result = {**stopped, "applied": [], "skipped": []}

        async def freeze(entity_id):
            # Each task checks immediately before its own call, not before gather yields.
            if entity_id not in _current_targets(hass, store, area_id):
                return "skipped", entity_id
            params = freeze_payload(hass.states.get(entity_id))
            if params is None:
                return "skipped", entity_id
            try:
                await hass.services.async_call(
                    "light", "turn_on", params, blocking=True, context=context
                )
            except Exception:
                _LOGGER.warning("Eine Lampe konnte nicht festgesetzt werden")
                return "failed", entity_id
            return "applied", entity_id

        outcomes = await asyncio.gather(
            *(freeze(e) for e in _current_targets(hass, store, area_id))
        )
        for key, entity_id in outcomes:
            result.setdefault(key, []).append(entity_id)
        return result


def _current_targets(hass, store, area_id):
    """Resolve approved, existing individual members; missing entities cannot block peers."""
    from homeassistant.helpers import area_registry as ar

    from .lights import entity_area_id, is_individual_light

    if not ar.async_get(hass).async_get_area(area_id):
        raise ServiceValidationError("Der Raum wurde nicht gefunden.")
    return [
        e
        for e in store.data["settings"]["light_entity_ids"]
        if entity_area_id(hass, e) == area_id
        and (state := hass.states.get(e))
        and is_individual_light(hass, state)
    ]


def freeze_payload(state):
    """Replay only the supported, currently active native mode, never stale derived colors."""
    if state is None or state.domain != "light" or state.state != "on":
        return None
    attrs = state.attributes
    mode = attrs.get("color_mode")
    if not isinstance(mode, str) or mode not in (attrs.get("supported_color_modes") or []):
        return None
    params = {"entity_id": state.entity_id}
    if mode == "onoff":
        return params
    brightness = attrs.get("brightness")
    if type(brightness) is not int or not 1 <= brightness <= 255:
        return None
    params["brightness"] = brightness
    if mode in {"brightness", "white"}:
        if mode == "white":
            params["white"] = params.pop("brightness")
        return params
    if mode == "color_temp":
        kelvin = attrs.get("color_temp_kelvin")
        if type(kelvin) is not int or kelvin <= 0:
            return None
        minimum = attrs.get("min_color_temp_kelvin") or 1
        maximum = attrs.get("max_color_temp_kelvin") or 40000
        if (
            any(type(v) not in (int, float) or not math.isfinite(v) for v in (minimum, maximum))
            or not minimum <= kelvin <= maximum
        ):
            return None
        params["color_temp_kelvin"] = kelvin
        return params
    specs = {
        "xy": (2, (1, 1)),
        "hs": (2, (360, 100)),
        "rgb": (3, (255,) * 3),
        "rgbw": (4, (255,) * 4),
        "rgbww": (5, (255,) * 5),
    }
    if mode not in specs:
        return None
    value = attrs.get(f"{mode}_color")
    size, limits = specs[mode]
    if not isinstance(value, (list, tuple)) or len(value) != size:
        return None
    if any(
        type(v) not in (int, float)
        or not math.isfinite(v)
        or not 0 <= v <= limit
        or (mode.startswith("rgb") and type(v) is not int)
        for v, limit in zip(value, limits, strict=True)
    ):
        return None
    params[f"{mode}_color"] = tuple(value)
    return params
