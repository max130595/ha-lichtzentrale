# Geändert für Lichtzentrale
"""Cancellable room-local palette loops adapted from hass-scene_presets.

Unlike the upstream loop, targets are revalidated on every tick and tasks are
owned by the integration, never by an object's destructor.
"""

import asyncio
import logging
import math
from copy import deepcopy
from uuid import uuid4

from homeassistant.const import EVENT_CALL_SERVICE, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Context, CoreState, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


TEMPOS = {"very_slow": (180, 60), "slow": (90, 40), "medium": (30, 15), "fast": (8, 3)}
EXECUTION_FIELDS = (
    "kind", "area_id", "lights", "palette_id", "brightness", "dynamic", "hue_scene",
    "verteilung", "lamp_settings", "wave_order",
)


def validate_dynamic(value, kind):
    if not isinstance(value, dict) or set(value) - {
        "enabled", "interval", "transition", "welle", "tempo", "gentle"
    }:
        raise ServiceValidationError("Ungültige Dynamik-Einstellungen.")
    enabled, wave, gentle = value.get("enabled", False), value.get("welle", False), value.get("gentle", False)
    tempo = value.get("tempo")
    if tempo is not None and (not isinstance(tempo, str) or tempo not in TEMPOS):
        raise ServiceValidationError("Ungültiges Tempo.")
    if type(wave) is not bool or (wave and kind != "palette"):
        raise ServiceValidationError("Welle ist nur für Farbpaletten verfügbar.")
    defaults = TEMPOS.get(tempo, (60, 10))
    interval, transition = value.get("interval", defaults[0]), value.get("transition", defaults[1])
    if type(enabled) is not bool or type(gentle) is not bool or any(
        type(v) not in (int, float) or not math.isfinite(v) for v in (interval, transition)
    ):
        raise ServiceValidationError("Ungültige Dynamik-Einstellungen.")
    if not 5 <= interval <= 3600 or not 0 <= transition <= min(interval, 60):
        raise ServiceValidationError(
            "Intervall: 5–3600 Sekunden; Übergang: 0–60 Sekunden und höchstens das Intervall."
        )
    if enabled and kind != "palette":
        raise ServiceValidationError("Dynamik ist nur für Farbpaletten verfügbar.")
    result = {"enabled": enabled, "interval": interval, "transition": transition, "welle": wave}
    # Legacy seconds remain byte-for-byte meaningful; no implicit preset migration.
    if "tempo" in value:
        result["tempo"] = tempo
    if "gentle" in value:
        result["gentle"] = gentle
    return result


class DynamicSceneManager:
    def __init__(self, hass, store):
        self.hass, self.store = hass, store
        self.active = {}
        self.closed = False
        self._startup_unsubscribe = None

    def list(self):
        from .moon import illuminated_fraction

        return [
            {
                "scene_id": r["scene"]["id"], "area_id": area,
                "name": r["scene"]["name"],
                "interval": r["scene"]["dynamic"].get("interval", 60),
                "transition": r["scene"]["dynamic"].get("transition", 10),
                "welle": r["scene"]["dynamic"].get("welle", False),
                "verteilung": r["scene"].get("verteilung", "zufall"),
                "tempo": r["scene"]["dynamic"].get("tempo"),
                "gentle": r["scene"]["dynamic"].get("gentle", False),
                "excluded": sorted(r["excluded"]),
                "moon_illumination": round(100 * illuminated_fraction()),
            }
            for area, r in self.active.items()
        ]

    @staticmethod
    def _unsubscribe(run):
        for key in ("unsubscribe", "service_unsubscribe"):
            if unsubscribe := run.pop(key, None):
                unsubscribe()

    async def _persist(self, run):
        if not run["persist"]:
            return
        await self.store.async_set_dynamic_run(run["scene"]["area_id"], {
            "token": run["token"], "scene_id": run["scene"]["id"],
            "scene": run["scene"], "targets": run["targets"],
            "excluded": sorted(run["excluded"]),
        }, expected_token=run["token"])

    async def stop(self, area_id, *, preserve=False):
        run = self.active.pop(area_id, None)
        if run:
            run["preserve"] = preserve
            self._unsubscribe(run)
            run["task"].cancel()
            await asyncio.gather(run["task"], return_exceptions=True)
        if not preserve and (run is None or run["persist"]):
            await self.store.async_set_dynamic_run(
                area_id, None, expected_token=run["token"] if run else None
            )
        return {"stopped": run is not None}

    async def shutdown(self):
        self.closed = True
        if self._startup_unsubscribe:
            self._startup_unsubscribe()
            self._startup_unsubscribe = None
        for area in list(self.active):
            await self.stop(area, preserve=True)

    async def restore(self, *, wait_for_start=True):
        """Resume only the persisted scope and currently-on lamps, never recall on."""
        if self.closed:
            return
        if wait_for_start and self.hass.state != CoreState.running:
            if not self._startup_unsubscribe:
                async def started(_event):
                    self._startup_unsubscribe = None
                    await self.restore(wait_for_start=False)
                self._startup_unsubscribe = self.hass.bus.async_listen_once(
                    EVENT_HOMEASSISTANT_STARTED, started
                )
            return
        for area, saved in self.store.data.get("active_dynamic", {}).items():
            if self.closed or area in self.active:
                continue
            try:
                scene = next((s for s in self.store.data["scenes"] if s["id"] == saved.get("scene_id")), None)
                if scene is None or any(scene.get(k) != saved.get("scene", {}).get(k) for k in EXECUTION_FIELDS):
                    await self.store.async_set_dynamic_run(area, None, expected_token=saved.get("token"))
                    continue
                await self.start(
                    scene, None, saved.get("targets", []), excluded=saved.get("excluded", []),
                    resume_token=saved.get("token"),
                )
            except Exception:
                _LOGGER.exception("Gespeicherte Dynamik konnte nicht fortgesetzt werden")
                await self.store.async_set_dynamic_run(area, None, expected_token=saved.get("token"))

    async def entity_references_changed(self, old_entity_id, new_entity_id):
        for area, run in list(self.active.items()):
            if old_entity_id in run["targets"] or old_entity_id in run["layout_targets"]:
                await self.stop(area, preserve=True)
        await self.restore(wait_for_start=False)

    async def exclude_targets(self, targets):
        from .command_limiter import limiter

        affected = []
        for run in list(self.active.values()):
            selected = set(targets).intersection(run["targets"])
            if selected:
                run["excluded"].update(selected)  # Fence pending ticks before any await.
                affected.append(run)
        for entity in targets:
            async with limiter(self.hass).entity_lock(entity):
                pass  # Join the already-dispatched command before the manual command.
        for run in affected:
            if self.active.get(run["scene"]["area_id"]) is run:
                if set(run["targets"]) <= run["excluded"]:
                    await self.stop(run["scene"]["area_id"])
                else:
                    await self._persist(run)

    async def start(self, scene, context, applied_targets=None, *, initial_transition=None,
                    persist=True, palette_override=None, dispatch_guard=None,
                    excluded=None, resume_token=None):
        if resume_token is not None:
            # A newer recall/explicit off wins a concurrent startup restoration.
            if scene["area_id"] in self.active:
                return
        else:
            await self.stop(scene["area_id"])
        if self.closed:
            raise ServiceValidationError("Lichtzentrale ist nicht geladen.")
        targets = [e for e in _current_targets(self.hass, self.store, scene["area_id"])
                   if e.startswith("light.")]
        layout_targets = list(targets)
        if applied_targets is not None:
            targets = [e for e in targets if e in applied_targets]
        if resume_token is not None:
            targets = [e for e in targets if (state := self.hass.states.get(e)) and state.state == "on"]
        if not targets:
            if persist:
                await self.store.async_set_dynamic_run(scene["area_id"], None, expected_token=resume_token)
            return
        run = {
            "scene": deepcopy(scene), "targets": targets, "context": context or Context(),
            "layout_targets": layout_targets, "initial_transition": initial_transition or 0,
            "excluded": set(excluded or []), "token": resume_token or uuid4().hex,
            "persist": persist, "preserve": False, "palette_override": palette_override,
            "dispatch_guard": dispatch_guard if not persist else None, "last_moon": asyncio.get_running_loop().time(),
        }
        if persist:
            saved = await self.store.async_set_dynamic_run(scene["area_id"], {
                "token": run["token"], "scene_id": scene["id"], "scene": scene,
                "targets": targets, "excluded": sorted(run["excluded"]),
            }, expected_token=resume_token)
            if not saved or self.closed:
                return

        @callback
        def changed(event):
            if self.active.get(scene["area_id"]) is not run or self.closed:
                return
            old, new = event.data.get("old_state"), event.data.get("new_state")
            own = new and (new.context.id == run["context"].id or new.context.parent_id == run["context"].id)
            # Long Zigbee transitions outlive HA's command context. Attribute
            # reports alone are not manual controls; service calls are handled below.
            if old and new and not own and new.state in {"on", "off"} and (
                (old.state in {"on", "off"} and old.state != new.state)
                or (new.context.user_id is not None and old.attributes != new.attributes)
            ):
                run["excluded"].add(event.data["entity_id"])
                self.hass.async_create_task(self._persist(run))
            if not any((s := self.hass.states.get(e)) and s.state == "on"
                       for e in targets if e not in run["excluded"]):
                self._unsubscribe(run)
                if self.active.get(scene["area_id"]) is run:
                    self.active.pop(scene["area_id"], None)
                run["task"].cancel()
                if run["persist"] and not self.closed:
                    self.hass.async_create_task(self.store.async_set_dynamic_run(
                        scene["area_id"], None, expected_token=run["token"]
                    ))

        @callback
        def called(event):
            # A real service invocation disambiguates a contextless physical
            # control/automation from unsolicited device color reports.
            if self.active.get(scene["area_id"]) is not run or self.closed:
                return
            data = event.data
            if data.get("domain") != "light" or data.get("service") not in {"turn_on", "turn_off", "toggle"}:
                return
            if event.context.id == run["context"].id or event.context.parent_id == run["context"].id:
                return
            selected = data.get("service_data", {}).get("entity_id", [])
            if isinstance(selected, str):
                selected = targets if selected == "all" else [selected]
            if not isinstance(selected, (list, tuple, set)):
                return
            affected = set(targets).intersection(selected)
            if affected:
                run["excluded"].update(affected)

                async def finish_manual():
                    if self.active.get(scene["area_id"]) is run:
                        await self.exclude_targets(sorted(affected))

                self.hass.async_create_task(finish_manual())

        run["unsubscribe"] = async_track_state_change_event(self.hass, targets, changed)
        run["service_unsubscribe"] = self.hass.bus.async_listen(EVENT_CALL_SERVICE, called)
        self.active[scene["area_id"]] = run
        run["task"] = self.hass.async_create_background_task(self._loop(run), "Lichtzentrale Dynamik")

    async def tick(self, run, offset, *, moon_only=False):
        from .moon import UPDATE_SECONDS, illuminated_fraction
        from .palettes import async_apply_palette

        scene = run["scene"]
        if self.active.get(scene["area_id"]) is not run or self.closed:
            return False
        if run["persist"]:
            current = next((s for s in self.store.data["scenes"] if s["id"] == scene["id"]), None)
            if current is None or any(current.get(key) != scene.get(key) for key in EXECUTION_FIELDS):
                return False
            scene["name"] = current["name"]
        allowed = set(_current_targets(self.hass, self.store, scene["area_id"]))
        targets = [e for e in run["targets"] if e not in run["excluded"] and e in allowed
                   and (s := self.hass.states.get(e)) and s.state == "on"]
        if not targets:
            return False
        now = asyncio.get_running_loop().time()
        moon_due = now - run["last_moon"] >= UPDATE_SECONDS
        breath = illuminated_fraction() >= 0.95 and any(
            s.get("mode") == "moon" and s.get("moon", {}).get("breath")
            for s in scene.get("lamp_settings", {}).values()
        )

        def valid(entity):
            return bool(self.active.get(scene["area_id"]) is run and not self.closed
                        and entity not in run["excluded"]
                        and (run["dispatch_guard"] is None or run["dispatch_guard"]()))

        result = await async_apply_palette(
            self.hass, self.store, scene.get("palette_id") or "kupfernest", targets,
            scene.get("brightness"), scene["dynamic"].get("transition", 10), run["context"],
            color_offset=offset, manage=False, verteilung=scene.get("verteilung", "zufall"),
            welle=scene["dynamic"].get("welle", False), layout_targets=run["layout_targets"],
            tick_area_id=scene["area_id"], lamp_settings=scene.get("lamp_settings"),
            wave_order=scene.get("wave_order"), gentle=scene["dynamic"].get("gentle", False),
            palette_override=run["palette_override"], tick_guard=valid,
            moon_due=moon_due, moon_breath=breath,
            only_moon=moon_only or scene["kind"] != "palette" or not scene["dynamic"].get("enabled", False),
        )
        if moon_due:
            run["last_moon"] = now
        if result.get("failed"):
            _LOGGER.warning("Dynamische Szene wurde nach einem Gerätefehler gestoppt")
            return False
        return True  # Fixed lamps and a not-yet-due moon intentionally emit no command.

    async def _loop(self, run):
        from .moon import UPDATE_SECONDS, illuminated_fraction

        scene = run["scene"]
        try:
            offset = 1
            clock = asyncio.get_running_loop().time
            dynamic = scene.get("dynamic", {})
            interval = dynamic.get("interval", 60)
            cycling = dynamic.get("enabled", False)
            has_moon = any(v.get("mode") == "moon" for v in scene.get("lamp_settings", {}).values())
            ready_at = clock() + run["initial_transition"]
            next_cycle = clock() + max(interval, run["initial_transition"]) if cycling else math.inf
            next_moon = clock() + UPDATE_SECONDS if has_moon else math.inf
            while True:
                breathing = illuminated_fraction() >= 0.95 and any(
                    v.get("mode") == "moon" and v.get("moon", {}).get("breath")
                    for v in scene.get("lamp_settings", {}).values()
                )
                due = max(ready_at, min(next_cycle, next_moon, clock() + 30 if breathing else math.inf))
                if math.isinf(due):
                    return
                await asyncio.sleep(max(0, due - clock()))
                started = clock()
                cycle_due = started >= next_cycle
                if not await self.tick(run, offset, moon_only=not cycle_due):
                    return
                elapsed = clock() - started
                if cycle_due:
                    # Delay the next tick from completion: no catch-up backlog.
                    next_cycle = clock() + interval
                    offset += 1
                    if elapsed >= interval:
                        _LOGGER.warning(
                            "Dynamik-Takt wegen Geräte-/Zigbee-Auslastung verlängert (%.1f s statt %.1f s); keine Warteschlange",
                            elapsed + interval, interval,
                        )
                if started >= next_moon:
                    next_moon = clock() + UPDATE_SECONDS
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Dynamische Szene wurde nach einem Fehler gestoppt")
        finally:
            self._unsubscribe(run)
            if self.active.get(scene["area_id"]) is run:
                self.active.pop(scene["area_id"], None)
                if run["persist"] and not self.closed and not run["preserve"]:
                    await self.store.async_set_dynamic_run(scene["area_id"], None, expected_token=run["token"])


async def async_exclude_targets(hass, targets):
    """Manual lamp controls leave peers running until the next explicit scene start."""
    if active := manager(hass):
        await active.exclude_targets(targets)


def manager(hass):
    return hass.data.get(DOMAIN, {}).get("dynamic")


async def async_stop_overlapping(hass, targets):
    """Join every local loop touching selected lights before a new action starts."""
    active = manager(hass)
    stopped = False
    if active:
        for area, run in list(active.active.items()):
            if set(targets).intersection(run["targets"]):
                stopped = (await active.stop(area))["stopped"] or stopped
    return {"stopped": stopped}


async def stop_dynamic(hass, area_id):
    active = manager(hass)
    if not active:
        return {"stopped": False}
    try:
        targets = _current_targets(hass, active.store, area_id)
    except ServiceValidationError:
        targets = []
    stopped = (await async_stop_overlapping(hass, targets))["stopped"]
    return {"stopped": (await active.stop(area_id))["stopped"] or stopped}


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
    from .lights import is_individual_light
    from .zones import contains, validate_area

    validate_area(hass, store, area_id)
    return [
        e
        for e in store.data["settings"]["light_entity_ids"]
        if contains(hass, store, area_id, e)
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
