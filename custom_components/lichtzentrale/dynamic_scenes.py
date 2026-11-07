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
    if not isinstance(value, dict) or set(value) - {"enabled", "interval", "transition"}:
        raise ServiceValidationError("Ungültige Dynamik-Einstellungen.")
    enabled = value.get("enabled", False)
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
    return {"enabled": enabled, "interval": interval, "transition": transition}


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

    async def start(self, scene, context, applied_targets=None):
        await self.stop(scene["area_id"])
        if self.closed:
            raise ServiceValidationError("Lichtzentrale ist nicht geladen.")
        targets = room_targets(self.hass, self.store, scene["area_id"])
        if applied_targets is not None:
            targets = [e for e in targets if e in applied_targets]
        run = {"scene": deepcopy(scene), "targets": targets, "context": context}

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
        )
        if current is None or any(current.get(key) != scene.get(key) for key in execution_fields):
            return False
        # Cosmetic edits should neither stop playback nor leave a stale title.
        scene["name"] = current["name"]
        # Never grow the original target set after starting. Registry changes,
        # permission removal and unavailable/off entities take effect each tick.
        allowed = set(room_targets(self.hass, self.store, scene["area_id"]))
        targets = [
            e
            for e in run["targets"]
            if e in allowed and (s := self.hass.states.get(e)) and s.state == "on"
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
        )
        if result.get("failed"):
            _LOGGER.warning("Dynamische Szene wurde nach einem Gerätefehler gestoppt")
            return False
        return True

    async def _loop(self, run):
        scene = run["scene"]
        try:
            offset = 1
            while True:
                await asyncio.sleep(scene["dynamic"]["interval"])
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


async def async_stop_room(hass, store, area_id):
    """Serialize the public stop action with recalls and room controls."""
    from asyncio import Lock

    room_targets(hass, store, area_id)
    locks = hass.data.setdefault(DOMAIN, {}).setdefault("scene_locks", {})
    async with locks.setdefault(area_id, Lock()):
        return await stop_dynamic(hass, area_id)
