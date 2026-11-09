# Geändert für Lichtzentrale
"""Room-local lux regulation with measured self-light and explicit ownership."""

import asyncio
import logging
import math
from collections import deque
from datetime import timedelta
from time import monotonic

from homeassistant.components.group import expand_entity_ids
from homeassistant.core import Context, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .lights import entity_area_id
from .rooms import async_dispatch, light_service_data
from .schedule_windows import _interval, window_is_open
from .selected_lights import _locked_targets, _still_allowed
from .vacation import vacation_paused

_LOGGER = logging.getLogger(__name__)
LEARN_SETTLE_SECONDS = 10
LEARN_TIMEOUT_SECONDS = 120


class BrightnessManager:
    """One cumulative stage per interval, never dim switches or reclaim manual light."""

    def __init__(self, hass, store):
        self.hass, self.store = hass, store
        self.closed = False
        self._unsubscribers = []
        self._rooms = {}
        self._tasks = {}
        self._contexts = deque(maxlen=4096)

    def _config(self, area):
        return self.store.data["rooms"].get(area, {}).get("brightness", {})

    def _runtime(self, area):
        return self._rooms.setdefault(area, {
            "paused": False, "active": [], "pending": None, "last_change": None,
            "last_error": None, "window": None, "generation": 0,
            "lock": asyncio.Lock(), "reclaim": False, "active_learned": {},
        })

    @callback
    def start(self):
        if self.closed or self._unsubscribers:
            return
        self._unsubscribers = [
            self.hass.bus.async_listen("state_changed", self._changed),
            self.hass.bus.async_listen("call_service", self._service),
            async_track_time_interval(self.hass, self._tick, timedelta(seconds=10)),
        ]

    @callback
    def _tick(self, _now):
        for area in self.store.data["rooms"]:
            if self._config(area).get("enabled"):
                self._spawn(area)

    @callback
    def vacation_changed(self, paused):
        """Discard pending regulation and learning without touching existing lights."""
        for area in set(self._rooms) | set(self.store.data["rooms"]):
            runtime = self._runtime(area)
            runtime.update(active=[], active_learned={}, pending=None, reclaim=False,
                           generation=runtime["generation"] + 1, last_change=monotonic())
            task = self._tasks.get(area)
            if task and task is not asyncio.current_task():
                task.cancel()

    def _spawn(self, area):
        if (self.closed or vacation_paused(self.hass)
                or (task := self._tasks.get(area)) and not task.done()):
            return
        task = self.hass.async_create_task(self.async_evaluate(area), "Lichtzentrale Grundhelligkeit")
        self._tasks[area] = task

        def done(task):
            if not task.cancelled() and (error := task.exception()):
                self._runtime(area)["last_error"] = str(error)
                _LOGGER.warning("Grundhelligkeit: %s", error)
        task.add_done_callback(done)

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
        return {entity for stage in self._config(area).get("stages", [])
                for entity in stage["entity_ids"]}

    @callback
    def _service(self, event):
        """Even a repeated manual command with no state change pauses regulation."""
        if self.closed or vacation_paused(self.hass) or self._own(event.context):
            return
        if event.data.get("domain") not in {"light", "switch"} or event.data.get("service") not in {
            "turn_on", "turn_off", "toggle",
        }:
            return
        data = event.data.get("service_data", {})
        ids = data.get("entity_id", [])
        ids = [ids] if isinstance(ids, str) else ids
        if not isinstance(ids, (list, tuple, set)):
            return
        all_entities = "all" in ids
        ids = set(expand_entity_ids(self.hass, ids))
        areas, devices = data.get("area_id", []), data.get("device_id", [])
        areas = [areas] if isinstance(areas, str) else areas
        devices = [devices] if isinstance(devices, str) else devices
        registry = er.async_get(self.hass)
        for area in self.store.data["rooms"]:
            if not self._config(area).get("enabled"):
                continue
            matched = {entity for entity in self._targets(area)
                       if entity.split(".", 1)[0] == event.data["domain"] and (
                           entity in ids or all_entities or entity_area_id(self.hass, entity) in areas
                           or ((entry := registry.async_get(entity)) and entry.device_id in devices))}
            # AL white-only maintenance of already-on lamps is not manual input.
            color_only = (event.context.id.startswith("adapt_lgt")
                          and event.data["service"] == "turn_on"
                          and set(data) - {"entity_id", "area_id", "device_id", "transition"}
                          <= {"color_temp_kelvin", "color_temp", "xy_color", "hs_color", "rgb_color"}
                          and bool(set(data) & {"color_temp_kelvin", "color_temp", "xy_color", "hs_color", "rgb_color"})
                          and all(self.hass.states.get(entity) is not None
                                  and self.hass.states.get(entity).state == "on" for entity in matched))
            if matched and not color_only:
                self.pause(area)

    @callback
    def _changed(self, event):
        if self.closed or vacation_paused(self.hass):
            return
        entity = event.data["entity_id"]
        old, new = event.data.get("old_state"), event.data.get("new_state")
        own = self._own(event.context) or (new is not None and self._own(new.context))
        for area in self.store.data["rooms"]:
            config = self._config(area)
            if not config.get("enabled"):
                continue
            if entity == config.get("lux_sensor_entity_id") or entity in config.get("person_entity_ids", []):
                if self._lux(config) is None or self._presence(config) is None:
                    self._runtime(area)["pending"] = None
                self._spawn(area)
            elif not own and entity in self._targets(area):
                keys = ("brightness", "xy_color", "hs_color", "rgb_color", "color_temp_kelvin")
                if old and new and old.state == new.state and all(
                    old.attributes.get(key) == new.attributes.get(key) for key in keys
                ):
                    continue
                # AL white-tone updates are automatic; on/off and brightness are not.
                context = new.context if new is not None else event.context
                if (context and context.id.startswith("adapt_lgt") and old and new
                        and old.state == new.state
                        and old.attributes.get("brightness") == new.attributes.get("brightness")):
                    continue
                self.pause(area)

    @callback
    def pause(self, area):
        runtime = self._runtime(area)
        runtime["window"] = self._window(self._config(area), dt_util.now()) or runtime["window"] or "closed"
        runtime.update(paused=True, active=[], active_learned={}, pending=None, reclaim=False,
                       generation=runtime["generation"] + 1)

    @callback
    def begin_room_off(self, area, context):
        """Suspend before room-off dispatch and recognize its unchanged/repeated states."""
        self.pause(area)
        if context:
            self._contexts.append(context.id)

    @callback
    def room_off(self, area):
        """An explicit, successful room-off releases manual pause after a full interval."""
        runtime = self._runtime(area)
        runtime.update(paused=False, active=[], active_learned={}, pending=None, last_change=monotonic(),
                       reclaim=False, last_error=None, generation=runtime["generation"] + 1)

    def config_lock(self, area):
        """Serialize edits with complete stage transitions, including in-flight calls."""
        return self._runtime(area)["lock"]

    async def async_prepare_config(self, area, previous, config, *, keep_lights=False):
        """Release old owned lights before replacing their stage mapping or disabling."""
        same_targets = ([stage["entity_ids"] for stage in previous.get("stages", [])]
                        == [stage["entity_ids"] for stage in config.get("stages", [])])
        preserve_active = same_targets and config.get("enabled", False)
        if not preserve_active and not keep_lights:
            await self._async_turn_off_owned(area)
        return preserve_active

    async def _async_turn_off_owned(self, area):
        """Explicit edits bypass lux/interval conditions, but never target unowned lights."""
        runtime = self._runtime(area)
        generation = runtime["generation"]
        runtime["pending"] = None
        try:
            while runtime["active"]:
                stage = runtime["active"][-1]
                async with _locked_targets(self.hass, self.store, sorted(stage)) as (targets, areas):
                    def guard(entity):
                        return (not self.closed and not vacation_paused(self.hass)
                                and runtime["generation"] == generation
                                and bool(runtime["active"]) and runtime["active"][-1] is stage
                                and entity in stage and areas[entity] == area
                                and _still_allowed(self.hass, self.store, entity, areas))

                    calls = [(entity.split(".", 1)[0], "turn_off", {"entity_id": entity})
                             for entity in targets]
                    result = await async_dispatch(self.hass, calls, context=self._context(), guard=guard)
                    if runtime["generation"] != generation:
                        raise ServiceValidationError("Die Lampen wurden zwischenzeitlich manuell bedient.")
                    stage.difference_update(result["applied"])
                    if result["applied"]:
                        runtime["last_change"] = monotonic()
                    if stage:
                        raise ServiceValidationError("Eigene Stufen konnten nicht vollständig ausgeschaltet werden.")
                    runtime["active_learned"].pop(len(runtime["active"]) - 1, None)
                    runtime["active"].pop()
        except (HomeAssistantError, ValueError, TypeError) as error:
            # Retain failed targets for an explicit retry; do not resume regulation.
            runtime.update(paused=True, last_error=str(error), reclaim=False)
            raise

    @callback
    def refresh_config(self, area, *, preserve_active=False, previous=None, learned=()):
        """Invalidate old learning/tasks without forgetting unchanged owned stages."""
        runtime = self._runtime(area)
        same_sensor = preserve_active and previous is not None and (
            previous.get("lux_sensor_entity_id") == self._config(area).get("lux_sensor_entity_id"))
        if same_sensor:
            # Configuration does not change the brightness of already-owned lamps.
            # Keep their measured contribution until this activation ends, even when
            # new stage brightness invalidates the persisted estimate for future starts.
            for index in range(len(runtime["active"])):
                runtime["active_learned"].setdefault(index, learned[index] if index < len(learned) else None)
        else:
            runtime.update(pending=None, active_learned={})
        runtime.update(reclaim=False, last_error=None, generation=runtime["generation"] + 1)
        if not preserve_active:
            runtime.update(paused=False, active=[], window=None)
        task = self._tasks.get(area)
        if task and task is not asyncio.current_task():
            task.cancel()

    def _lux(self, config):
        entity = config.get("lux_sensor_entity_id")
        state = self.hass.states.get(entity) if entity else None
        if (state is None or state.domain != "sensor" or state.attributes.get("restored")
                or state.attributes.get("device_class") != "illuminance"
                or state.attributes.get("unit_of_measurement") != "lx"
                or ((entry := er.async_get(self.hass).async_get(entity)) and entry.disabled_by)):
            return None
        try:
            value = float(state.state)
            return value if math.isfinite(value) and value >= 0 else None
        except (ValueError, TypeError):
            return None

    def _presence(self, config):
        ids = config.get("person_entity_ids", [])
        if not ids:
            return True
        states = [self.hass.states.get(entity) for entity in ids]
        if any(state is None or state.domain != "person" or state.attributes.get("restored")
               or state.state in {"unknown", "unavailable", ""}
               or ((entry := er.async_get(self.hass).async_get(state.entity_id)) and entry.disabled_by)
               for state in states):
            return None
        return any(state.state == "home" for state in states)

    def status(self, area):
        config, runtime = self._config(area), self._runtime(area)
        learned = self.store.data["rooms"].get(area, {}).get("brightness_learned", [])
        return {"enabled": bool(config.get("enabled")), "paused": runtime["paused"] or vacation_paused(self.hass),
                "current_lux": self._lux(config), "active_stage": len(runtime["active"]),
                "learned_lux": [runtime["active_learned"].get(i, learned[i] if i < len(learned) else None)
                                for i in range(len(config.get("stages", [])))],
                "last_error": runtime["last_error"]}

    def _window(self, config, now):
        window = config.get("time_window")
        if not window:
            return "continuous"
        instant = dt_util.as_utc(now)
        matches = [_interval(self.hass, window, now.date() + timedelta(days=offset), now.tzinfo)
                   for offset in range(-3, 3)]
        starts = [start for interval in matches if interval is not None
                  for start, end in [interval] if start <= instant < end]
        return max(starts).isoformat() if starts else None

    def _valid(self, area, config, generation):
        runtime = self._runtime(area)
        return (not self.closed and not vacation_paused(self.hass)
                and config.get("enabled") and self._config(area) == config
                and generation == runtime["generation"] and not runtime["paused"])

    async def _learn(self, area, config):
        runtime = self._runtime(area)
        pending = runtime["pending"]
        if pending is None:
            return
        elapsed = monotonic() - pending["time"]
        if elapsed > LEARN_TIMEOUT_SECONDS:
            runtime["pending"] = None
            runtime["last_error"] = "Kein frischer Lux-Wert zum Lernen; Abschalten bleibt vorsichtig."
            return
        state = self.hass.states.get(config["lux_sensor_entity_id"])
        value = self._lux(config)
        if (elapsed < LEARN_SETTLE_SECONDS or value is None or state is None
                or state.last_updated <= pending["sensor_updated"]):
            return
        generation = runtime["generation"]
        rise = max(0.0, value - pending["before"])
        if pending["stage"] != config["stages"][pending["index"]]:
            # This sample belongs to the still-on, pre-edit brightness only.
            # Never seed the persisted estimate for a different future activation.
            previous = runtime["active_learned"].get(pending["index"])
            runtime["active_learned"][pending["index"]] = (
                rise if previous is None else previous * 0.75 + rise * 0.25)
            runtime["pending"] = None
            return
        await self.store.async_learn_brightness(area, config, pending["index"], rise,
            guard=lambda: self._valid(area, config, generation) and runtime["pending"] is pending)
        if self._valid(area, config, generation) and runtime["pending"] is pending:
            # A completed sample replaces any pre-edit estimate for this activation.
            runtime["active_learned"].pop(pending["index"], None)
            runtime["pending"] = None

    async def async_evaluate(self, area):
        """Evaluate fresh state under a per-room lock and recheck before every dispatch."""
        runtime = self._runtime(area)
        async with runtime["lock"]:
            config = self._config(area)
            if self.closed or vacation_paused(self.hass) or not config.get("enabled"):
                return
            from .brightness_config import validate_brightness

            try:
                validate_brightness(self.hass, self.store, area, config)
            except (HomeAssistantError, ValueError, TypeError) as error:
                runtime["last_error"] = str(error)
                runtime["pending"] = None
                return
            now = dt_util.now()
            token = self._window(config, now)
            previous = runtime["window"]
            # Keep the last open start while closed, including overnight windows.
            if token is not None and token != previous:
                runtime["window"] = token
                if previous is not None:
                    runtime.update(paused=False, reclaim=True, pending=None)
            if runtime["paused"]:
                return
            generation = runtime["generation"]
            presence = self._presence(config)
            if token is None or not presence or self._lux(config) is None:
                runtime["pending"] = None
            await self._learn(area, config)
            if not self._valid(area, config, generation):
                return
            elapsed = monotonic() - runtime["last_change"] if runtime["last_change"] is not None else math.inf
            if elapsed < config["min_interval_seconds"] or runtime["pending"] is not None:
                return
            presence = self._presence(config)
            if presence is None:
                runtime["pending"] = None
                return
            active = len(runtime["active"])
            if token is None or not presence:
                if active:
                    await self._change(area, config, active - 1, False, generation, constrained=False)
                return
            lux = self._lux(config)
            if lux is None:
                return
            if lux < config["target_lux"] - config["hysteresis_lux"] and active < len(config["stages"]):
                await self._change(area, config, active, True, generation)
            elif active:
                learned = self.status(area)["learned_lux"][active - 1]
                # Predict the lux AFTER removal: self-light must never provoke oscillation.
                if learned is not None and lux - learned > config["target_lux"] + config["hysteresis_lux"]:
                    await self._change(area, config, active - 1, False, generation)

    async def _change(self, area, config, index, on, generation, *, constrained=True):
        runtime = self._runtime(area)
        stage = config["stages"][index]
        targets = stage["entity_ids"] if on else list(runtime["active"][-1])
        async with _locked_targets(self.hass, self.store, targets) as (targets, areas):
            dispatching = False

            def guard(entity=None):
                if not self._valid(area, config, generation) or self._presence(config) is None:
                    return False
                opened = window_is_open(self.hass, config["time_window"])
                present = self._presence(config)
                if constrained:
                    lux = self._lux(config)
                    if not present or not opened or lux is None:
                        return False
                    if not dispatching and on and lux >= config["target_lux"] - config["hysteresis_lux"]:
                        return False
                    if not dispatching and not on:
                        learned = self.status(area)["learned_lux"][index]
                        if learned is None or lux - learned <= config["target_lux"] + config["hysteresis_lux"]:
                            return False
                elif opened and present:
                    return False
                return entity is None or (areas[entity] == area
                                          and _still_allowed(self.hass, self.store, entity, areas))

            if not guard() or not all(guard(entity) for entity in targets):
                return
            states = {entity: self.hass.states.get(entity) for entity in targets}
            if on and any(state.state == "on" for state in states.values()) and not runtime["reclaim"]:
                self.pause(area)
                return
            context = self._context()
            white = None
            if on:
                white = await self._adaptive_white(area, targets, context, guard)
            if not guard():
                return
            before = self._lux(config)
            sensor = self.hass.states.get(config["lux_sensor_entity_id"])
            calls = [(state.domain, *light_service_data(
                state, on=on, brightness=stage["brightness"] if on else None,
                color_temp_kelvin=white if on else None)) for state in states.values()]
            def dispatch_guard(entity):
                nonlocal dispatching
                valid = guard(entity) and self.hass.states.get(entity) is states[entity]
                if valid:
                    # A stage is one decision. Its first lamp can change the lux
                    # reading before peers dispatch; that is our own light, not a
                    # reason to cancel half the same stage.
                    dispatching = True
                return valid

            result = await async_dispatch(self.hass, calls, context=context, guard=dispatch_guard)
            if not self._valid(area, config, generation):
                return
            if result["applied"]:
                runtime["last_change"] = monotonic()
            if result.get("failed") or result["skipped"] or len(result["applied"]) != len(targets):
                self.pause(area)
                runtime["last_error"] = "Stufe nur teilweise geschaltet. Bitte Geräte prüfen; Regelung pausiert."
                return
            runtime["last_error"] = None
            if on:
                runtime["active_learned"].pop(index, None)
                runtime["active"].append(set(targets))
                if before is not None and sensor is not None and all(s.state == "off" for s in states.values()):
                    runtime["pending"] = {"index": index, "before": before, "stage": stage,
                        "sensor_updated": sensor.last_updated, "time": monotonic()}
            else:
                runtime["active_learned"].pop(index, None)
                runtime["active"].pop()

    async def _adaptive_white(self, area, targets, context, guard):
        """Borrow only AL's white tone, and prevent AL overriding stage brightness."""
        from .adaptive import ADAPTIVE_DOMAIN, _validated

        switch = self.store.data["rooms"].get(area, {}).get("adaptive_switch")
        if not switch or not self.hass.data.get(ADAPTIVE_DOMAIN):
            return None
        eligible = _validated(self.hass, self.store, area, switch)
        selected = [entity for entity in targets if entity in eligible]
        state = self.hass.states.get(switch)
        kelvin = state.attributes.get("color_temp_kelvin")
        if selected:
            if not guard() or not all(guard(entity) for entity in selected):
                raise ServiceValidationError("Die Grundhelligkeitsbedingungen haben sich geändert.")
            await self.hass.services.async_call(ADAPTIVE_DOMAIN, "set_manual_control",
                {"entity_id": switch, "lights": selected, "manual_control": True},
                blocking=True, context=context)
        return round(kelvin) if type(kelvin) in (int, float) and math.isfinite(kelvin) and kelvin > 0 else None

    async def shutdown(self):
        self.closed = True
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._rooms.clear()
