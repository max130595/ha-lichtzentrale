# Geändert für Lichtzentrale
"""Fail-closed, cancellable occupancy automation with explicit target ownership."""

import asyncio
import logging
import math
from collections import deque
from datetime import datetime, timedelta
from time import monotonic

from homeassistant.core import Context, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .lights import entity_area_id
from .rooms import async_dispatch, light_service_data, room_targets
from .selected_lights import _locked_targets, _still_allowed, _stop_dynamics

_LOGGER = logging.getLogger(__name__)
_SENSOR_CLASSES = {"motion", "occupancy", "presence"}


def _boundary(hass, boundary, day):
    if boundary["type"] == "time":
        hour, minute = map(int, boundary["value"].split(":"))
        return datetime.combine(day, datetime.min.time(), dt_util.DEFAULT_TIME_ZONE).replace(
            hour=hour, minute=minute
        )
    event = get_astral_event_date(hass, boundary["event"], day)
    return dt_util.as_local(event) + timedelta(minutes=boundary["offset_min"]) if event else None


def active_window(hass, windows, now=None):
    """First matching window wins; equal clock boundaries mean a full day.

    Resolve each date separately, including overnight solar events and DST.
    No solar result (polar day/night) means no matching solar window.
    """
    now = dt_util.as_local(now) if now is not None else dt_util.now()
    for window in windows:
        for offset in (-3, -2, -1, 0, 1):
            day = now.date() + timedelta(days=offset)
            start = _boundary(hass, window["start"], day)
            end = _boundary(hass, window["end"], day)
            if start is None or end is None:
                continue
            for next_day in (1, 2, 3):
                if end is None or end > start:
                    break
                end = _boundary(hass, window["end"], day + timedelta(days=next_day))
            if end is not None and start <= now < end:
                return window
    return None


class MotionManager:
    """One serialized state machine per configured room, no hardware assumptions."""

    def __init__(self, hass, store):
        self.hass, self.store = hass, store
        self.closed = False
        self._unsubscribe = None
        self._rooms = {}
        self._tasks = {}
        self._contexts = deque(maxlen=4096)

    def _config(self, area):
        return self.store.data["rooms"].get(area, {}).get("motion", {})

    def _runtime(self, area):
        return self._rooms.setdefault(area, {
            "paused": False, "owned": {}, "restore": {}, "deadline": None,
            "timers": [], "lock": asyncio.Lock(), "last_error": None,
        })

    @callback
    def start(self):
        if self._unsubscribe is None and not self.closed:
            self._unsubscribe = self.hass.bus.async_listen("state_changed", self._changed)

    def _occupancy(self, area):
        ids = self._config(area).get("sensor_entity_ids", [])
        states = [self.hass.states.get(e) for e in ids]
        registry = er.async_get(self.hass)
        valid = bool(states) and all(
            s is not None and s.domain == "binary_sensor"
            and s.attributes.get("device_class") in _SENSOR_CLASSES
            and not s.attributes.get("restored")
            and not ((entry := registry.async_get(s.entity_id)) and entry.disabled_by)
            and s.state in {"on", "off"} for s in states
        )
        if not valid:
            return None
        return any(s.state == "on" for s in states)

    def status(self, area):
        runtime = self._runtime(area)
        deadline = runtime["deadline"]
        return {
            "enabled": bool(self._config(area).get("enabled")),
            "paused": runtime["paused"], "occupied": self._occupancy(area),
            "active": bool(runtime["owned"]),
            "active_targets": sorted(runtime["owned"]), "dimmed": bool(runtime["restore"]),
            "remaining_seconds": max(0, math.ceil(deadline - monotonic())) if deadline else None,
            "last_error": runtime["last_error"],
        }

    def _context(self):
        context = Context()
        self._contexts.append(context.id)
        return context

    def _own(self, context):
        if context and (context.id in self._contexts or context.parent_id in self._contexts):
            if context.id not in self._contexts:
                self._contexts.append(context.id)
            return True
        return False

    def _targets(self, area):
        """Observe configured targets even before the first automatic activation."""
        from .adaptive import _validated
        from .scenes import _scene, hue_scene_targets

        targets = set(self._runtime(area)["owned"])
        for window in self._config(area).get("windows", []):
            action = window["action"]
            try:
                if action["type"] == "lights":
                    targets.update(action.get("entity_ids") or room_targets(self.hass, self.store, area))
                elif action["type"] == "adaptive":
                    targets.update(_validated(self.hass, self.store, area,
                        self.store.data["rooms"].get(area, {}).get("adaptive_switch")))
                else:
                    scene = _scene(self.store, action["scene_id"])
                    if scene["area_id"] != area:
                        continue
                    targets.update(scene["lights"] if scene["kind"] == "snapshot" else
                        hue_scene_targets(self.hass, scene["hue_scene"]) if scene["kind"] == "hue"
                        else room_targets(self.hass, self.store, area))
            except (HomeAssistantError, KeyError, TypeError):
                continue
        return targets

    @callback
    def _changed(self, event):
        if self.closed:
            return
        entity = event.data["entity_id"]
        old, new = event.data.get("old_state"), event.data.get("new_state")
        own = self._own(event.context) or (new is not None and self._own(new.context))
        for area in self.store.data["rooms"]:
            config = self._config(area)
            if not config.get("enabled"):
                continue
            runtime = self._runtime(area)
            if entity in config.get("sensor_entity_ids", []):
                occupied = self._occupancy(area)
                if occupied is False:
                    self._schedule(area)
                else:
                    self._cancel_timers(area)
                    if occupied and not runtime["paused"]:
                        self._spawn(area, self._activate(area))
            elif not own and entity in self._targets(area):
                # Ignore metadata-only updates, but unknown/removal revokes ownership.
                keys = ("brightness", "xy_color", "hs_color", "rgb_color", "color_temp_kelvin")
                if old and new and old.state == new.state and all(
                    old.attributes.get(k) == new.attributes.get(k) for k in keys
                ):
                    continue
                runtime["paused"] = True
                runtime["owned"].clear()
                runtime["restore"].clear()
                self._cancel_work(area)
                self._cancel_timers(area)
                if self._occupancy(area) is False:
                    self._schedule(area)

    def _spawn(self, area, coro):
        task = self.hass.async_create_task(coro, "Lichtzentrale Bewegung")
        self._tasks.setdefault(area, set()).add(task)

        def done(task):
            self._tasks.get(area, set()).discard(task)
            if not task.cancelled() and (error := task.exception()):
                self._runtime(area)["last_error"] = str(error)
                _LOGGER.warning("Bewegungsautomatik: %s", error)
        task.add_done_callback(done)

    def _cancel_work(self, area):
        for task in self._tasks.get(area, set()):
            task.cancel()

    def _cancel_timers(self, area):
        runtime = self._runtime(area)
        for handle in runtime["timers"]:
            handle.cancel()
        runtime["timers"].clear()
        runtime["deadline"] = None

    def _schedule(self, area):
        runtime = self._runtime(area)
        if runtime["deadline"] is not None:
            return
        config = self._config(area)
        timeout = config["timeout_seconds"]
        runtime["deadline"] = monotonic() + timeout
        deadline = runtime["deadline"]
        if config.get("dim_before_off") and timeout > 20 and not runtime["paused"]:
            runtime["timers"].append(self.hass.loop.call_later(
                timeout - 20, lambda: self._spawn(area, self._expire(area, dim=True, deadline=deadline))))
        runtime["timers"].append(self.hass.loop.call_later(
            timeout, lambda: self._spawn(area, self._expire(area, deadline=deadline))))

    @callback
    def refresh_config(self, area):
        """Drop ownership without device commands on save/revoke/disable."""
        self._cancel_timers(area)
        self._cancel_work(area)
        runtime = self._runtime(area)
        runtime.update(paused=False, owned={}, restore={}, last_error=None)

    def _lux_ok(self, config):
        entity = config.get("lux_sensor_entity_id")
        if not entity:
            return True
        state = self.hass.states.get(entity)
        if (state is None or state.domain != "sensor"
                or state.attributes.get("device_class") != "illuminance"
                or state.attributes.get("unit_of_measurement") != "lx"
                or state.attributes.get("restored")
                or ((entry := er.async_get(self.hass).async_get(entity)) and entry.disabled_by)):
            return False
        try:
            value = float(state.state) if state else math.nan
            return math.isfinite(value) and value >= 0 and value < config["lux_below"]
        except (ValueError, TypeError):
            return False

    async def _pause_selected_adaptive(self, targets, areas, context):
        """Stop AL adapting only these lamps, never disable its room switch.

        Discover loaded primary switches rather than relying on a room mapping:
        an explicit selection can cross rooms or intersect an unmapped AL group.
        Retain manual control until the next explicit adaptive activation. Clearing
        it on expiry could undo a user's subsequent manual intervention.
        """
        from .adaptive import ADAPTIVE_DOMAIN, _primary

        if not self.hass.data.get(ADAPTIVE_DOMAIN):
            return
        for state in self.hass.states.async_all("switch"):
            entry = er.async_get(self.hass).async_get(state.entity_id)
            if not entry or entry.platform != ADAPTIVE_DOMAIN:
                continue
            try:
                primary = _primary(self.hass, state.entity_id)
            except HomeAssistantError:
                continue
            lights = getattr(primary, "lights", None)
            if not isinstance(lights, (list, tuple, set)):
                continue
            selected = [e for e in targets if e.startswith("light.") and e in lights
                        and _still_allowed(self.hass, self.store, e, areas)]
            if not selected or state.state == "off":
                continue
            if state.state != "on":
                raise HomeAssistantError("Adaptive Lighting ist nicht erreichbar.")
            await self.hass.services.async_call(
                ADAPTIVE_DOMAIN, "set_manual_control",
                {"entity_id": state.entity_id, "lights": selected, "manual_control": True},
                blocking=True, context=context,
            )

    async def _activate(self, area):
        runtime = self._runtime(area)
        async with runtime["lock"]:
            config = self._config(area)
            if self.closed or not config.get("enabled") or runtime["paused"] or self._occupancy(area) is not True:
                return
            if runtime["restore"]:
                await self._dispatch_owned(area, "restore")
                return
            if runtime["owned"] or not self._lux_ok(config):
                return
            window = active_window(self.hass, config["windows"])
            if window is None:
                return
            action, context = window["action"], self._context()
            if action["type"] == "scene":
                from .scenes import _scene, async_apply_scene_locked
                scene = _scene(self.store, action["scene_id"])
                if scene["area_id"] != area:
                    return
                locks = self.hass.data.setdefault(DOMAIN, {}).setdefault("scene_locks", {})
                async with locks.setdefault(area, asyncio.Lock()):
                    if runtime["paused"] or self._occupancy(area) is not True:
                        return
                    result = await async_apply_scene_locked(self.hass, self.store, scene["id"], context)
            elif action["type"] == "adaptive":
                from .adaptive import async_turn_on_adaptive
                from .dynamic_scenes import stop_dynamic
                locks = self.hass.data.setdefault(DOMAIN, {}).setdefault("scene_locks", {})
                async with locks.setdefault(area, asyncio.Lock()):
                    if runtime["paused"] or self._occupancy(area) is not True:
                        return
                    await stop_dynamic(self.hass, area)
                    if runtime["paused"] or self._occupancy(area) is not True:
                        return
                    result = {"applied": await async_turn_on_adaptive(self.hass, self.store, area, context)}
            else:
                targets = action.get("entity_ids") or room_targets(self.hass, self.store, area)
                if not targets:
                    return
                async with _locked_targets(self.hass, self.store, targets) as (targets, areas):
                    await _stop_dynamics(self.hass, self.store, targets, areas)
                    if runtime["paused"] or self._occupancy(area) is not True:
                        return
                    await self._pause_selected_adaptive(targets, areas, context)
                    calls, prepared = [], {}
                    for entity in targets:
                        state = self.hass.states.get(entity)
                        if _still_allowed(self.hass, self.store, entity, areas):
                            prepared[entity] = state
                            calls.append((state.domain, *light_service_data(
                                state, on=True, brightness=action["brightness"])))
                    result = await async_dispatch(self.hass, calls, context=context,
                        guard=lambda e: not runtime["paused"] and self._occupancy(area) is True
                        and self.hass.states.get(e) is prepared[e]
                        and _still_allowed(self.hass, self.store, e, areas))
            if runtime["paused"]:
                return
            runtime["owned"] = {e: entity_area_id(self.hass, e) for e in result.get("applied", [])}
            runtime["last_error"] = "Einige Ziele konnten nicht geschaltet werden." if result.get("failed") else None

    async def _dispatch_owned(self, area, operation, deadline=None):
        runtime = self._runtime(area)
        targets = [e for e in runtime["owned"] if _still_allowed(
            self.hass, self.store, e, runtime["owned"])]
        if not targets:
            runtime["restore"].clear()
            return
        async with _locked_targets(self.hass, self.store, targets):
            if deadline is not None and runtime["deadline"] != deadline:
                return
            await _stop_dynamics(self.hass, self.store, targets, runtime["owned"])
            if operation == "dim":
                candidates = [e for e in targets if (state := self.hass.states.get(e))
                              and state.state == "on" and state.domain == "light"
                              and light_service_data(state, brightness=76) is not None]
                if (runtime["paused"] or self._occupancy(area) is not False
                        or (deadline is not None and runtime["deadline"] != deadline)):
                    return
                await self._pause_selected_adaptive(candidates, runtime["owned"], self._context())
            calls, captured, prepared = [], {}, {}
            for entity in targets:
                state = self.hass.states.get(entity)
                if state.state != "on":
                    continue
                if operation == "off":
                    payload = light_service_data(state, on=False)
                elif operation == "restore":
                    if entity not in runtime["restore"]:
                        continue
                    payload = light_service_data(state, brightness=runtime["restore"][entity])
                else:
                    brightness = state.attributes.get("brightness")
                    if state.domain != "light" or type(brightness) is not int:
                        continue
                    # Never brighten a dim nightlight during the warning period.
                    payload = light_service_data(state, brightness=min(brightness, 76))
                    captured[entity] = brightness
                if payload:
                    calls.append((state.domain, *payload))
                    prepared[entity] = state
            result = await async_dispatch(self.hass, calls, context=self._context(),
                guard=lambda e: not self.closed and not runtime["paused"]
                and self._config(area).get("enabled")
                and (deadline is None or runtime["deadline"] == deadline)
                and self.hass.states.get(e) is prepared[e]
                and self._occupancy(area) is (operation == "restore")
                and e in runtime["owned"]
                and _still_allowed(self.hass, self.store, e, runtime["owned"]))
            if operation == "dim":
                runtime["restore"].update({e: captured[e] for e in result["applied"]})
            elif operation == "restore":
                for entity in result["applied"]:
                    runtime["restore"].pop(entity, None)
            if result.get("failed"):
                runtime["last_error"] = "Einige Ziele konnten nicht geschaltet werden."

    async def _expire(self, area, dim=False, deadline=None):
        runtime = self._runtime(area)
        async with runtime["lock"]:
            deadline = runtime["deadline"] if deadline is None else deadline
            if runtime["deadline"] != deadline:
                return
            if self.closed or not self._config(area).get("enabled") or self._occupancy(area) is not False:
                self._cancel_timers(area)
                return
            if dim:
                if not runtime["paused"]:
                    await self._dispatch_owned(area, "dim", deadline)
                return
            if not runtime["paused"]:
                await self._dispatch_owned(area, "off", deadline)
            # New movement can replace the timer while target locks/services yield.
            if runtime["deadline"] == deadline:
                runtime.update(paused=False, owned={}, restore={})
                self._cancel_timers(area)

    async def shutdown(self):
        self.closed = True
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None
        for area in self._rooms:
            self._cancel_timers(area)
            self._cancel_work(area)
        tasks = [task for tasks in self._tasks.values() for task in tasks]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._rooms.clear()
