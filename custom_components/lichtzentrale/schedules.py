# Geändert für Lichtzentrale
"""Cancellable wall-clock, solar and continuous-lux schedules; no catch-up."""

import asyncio
import logging
import math
from copy import deepcopy
from datetime import datetime, timedelta

from homeassistant.core import Context, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.util import dt as dt_util

from .schedule_config import action_targets, list_persons, validate_schedule
from .schedule_windows import next_window_run, window_is_open

_LOGGER = logging.getLogger(__name__)


def next_run(hass, schedule, now=None):
    """Next future instant in HA time zone; weekdays refer to execution date.

    Clock gaps are skipped, folds use the first occurrence only. Solar offsets
    are elapsed minutes, even across DST; polar absence produces no event.
    """
    now = dt_util.as_local(now) if now is not None else dt_util.now()
    trigger = schedule["trigger"]
    if trigger["type"] == "lux" or not schedule["condition"]["weekdays"]:
        return None
    candidates = []
    for offset in range(-2, 370):
        day = now.date() + timedelta(days=offset)
        if trigger["type"] == "time":
            hour, minute = map(int, trigger["value"].split(":"))
            candidate = datetime.combine(day, datetime.min.time(), now.tzinfo).replace(
                hour=hour, minute=minute, fold=0)
            utc = dt_util.as_utc(candidate)
            if utc.astimezone(now.tzinfo).replace(tzinfo=None) != candidate.replace(tzinfo=None):
                continue
        else:
            event = get_astral_event_date(hass, trigger["event"], day)
            if event is None:
                continue
            utc = dt_util.as_utc(event) + timedelta(minutes=trigger["offset_min"])
            candidate = utc.astimezone(now.tzinfo)
        if (utc > dt_util.as_utc(now)
            and candidate.weekday() in schedule["condition"]["weekdays"]
            and window_is_open(hass, schedule["condition"].get("time_window"), candidate)):
            candidates.append(candidate)
        if candidates and offset > 10:
            break
    return min(candidates, key=dt_util.as_utc) if candidates else None


class ScheduleManager:
    """Own per-plan locks, timer generations, in-flight work and runtime errors."""

    def __init__(self, hass, store):
        self.hass, self.store = hass, store
        self.closed = False
        self._started = False
        self._unsub = None
        self._unsub_start = None
        self._runtime = {}

    def _state(self, plan_id):
        return self._runtime.setdefault(plan_id, {
            "generation": 0, "timer_token": 0, "cancel": None, "next_run": None,
            "tasks": set(), "lock": asyncio.Lock(), "latched": False, "last_error": None,
            "lux_ready": False, "lux_epoch": 0, "last_attempt_date": None,
        })

    def _plan(self, plan_id):
        return next((p for p in self.store.data.get("schedules", []) if p["id"] == plan_id), None)

    @callback
    def start(self):
        if self.closed or self._unsub_start is not None or self._started:
            return
        self._unsub_start = async_at_started(self.hass, self._start)

    @callback
    def _start(self, hass):
        if self.closed or self._started:
            return
        self._started = True
        self._unsub = self.hass.bus.async_listen("state_changed", self._changed)
        self.refresh_config()

    @callback
    def refresh_config(self, schedule_id=None):
        ids = {schedule_id} if schedule_id else set(self._runtime) | {
            p["id"] for p in self.store.data.get("schedules", [])}
        for plan_id in ids:
            runtime = self._state(plan_id)
            runtime["generation"] += 1
            self._cancel_timer(runtime)
            for task in tuple(runtime["tasks"]):
                task.cancel()
            runtime["latched"] = False
            runtime["lux_ready"] = False
            runtime["last_attempt_date"] = None
            runtime["last_error"] = None
            if self._started and not self.closed:
                self._arm(plan_id)

    def _cancel_timer(self, runtime):
        runtime["timer_token"] += 1
        if runtime["cancel"]:
            runtime["cancel"]()
        runtime["cancel"] = None
        runtime["next_run"] = None

    def _lux(self, plan):
        trigger = plan["trigger"]
        state = self.hass.states.get(trigger["sensor_entity_id"])
        if (state is None or state.attributes.get("restored")
            or state.attributes.get("device_class") != "illuminance"
            or state.attributes.get("unit_of_measurement") != "lx"):
            return False
        entry = er.async_get(self.hass).async_get(state.entity_id)
        if entry and entry.disabled_by:
            return False
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return False
        if not math.isfinite(value) or value < 0:
            return False
        return (value < trigger["threshold"] if trigger["comparison"] == "below"
                else value > trigger["threshold"])

    def _arm(self, plan_id):
        plan = self._plan(plan_id)
        if not plan or not plan.get("enabled") or self.closed:
            return
        runtime = self._state(plan_id)
        generation, token = runtime["generation"], runtime["timer_token"]
        if plan["trigger"]["type"] == "lux":
            if not self._lux(plan):
                self._cancel_timer(runtime)
                runtime["latched"] = False
                runtime["lux_ready"] = False
                runtime["lux_epoch"] += 1
                runtime["last_attempt_date"] = None
                return
            window = plan["condition"].get("time_window")
            if window and runtime["lux_ready"]:
                if runtime["cancel"]:
                    return
                now = dt_util.now()
                day = now.date().isoformat()
                last_run = self.store.data["settings"].get("schedule_last_run_dates", {}).get(plan_id)
                if day in (last_run, runtime["last_attempt_date"]):
                    now = datetime.combine(now.date() + timedelta(days=1),
                                           datetime.min.time(), now.tzinfo)
                when = next_window_run(self.hass, window, now, plan["condition"]["weekdays"])
                runtime["next_run"] = when
                if when:
                    @callback
                    def fire_window(now):
                        self._fire(plan_id, generation, token)

                    runtime["cancel"] = async_track_point_in_utc_time(
                        self.hass, fire_window, dt_util.as_utc(when))
                return
            if runtime["latched"] or runtime["cancel"]:
                return
            seconds = plan["trigger"]["duration_seconds"]
            runtime["next_run"] = dt_util.as_local(dt_util.utcnow() + timedelta(seconds=seconds))
            runtime["cancel"] = self.hass.loop.call_later(
                seconds, self._fire, plan_id, generation, token).cancel
        else:
            when = next_run(self.hass, plan)
            runtime["next_run"] = when
            if when:
                @callback
                def fire(now):
                    self._fire(plan_id, generation, token)

                runtime["cancel"] = async_track_point_in_utc_time(
                    self.hass, fire, dt_util.as_utc(when))

    @callback
    def _changed(self, event):
        if self.closed:
            return
        for plan in self.store.data.get("schedules", []):
            trigger = plan["trigger"]
            if (plan["enabled"] and trigger["type"] == "lux"
                and event.data.get("entity_id") == trigger["sensor_entity_id"]):
                self._arm(plan["id"])

    @callback
    def _fire(self, plan_id, generation, token=None):
        runtime = self._state(plan_id)
        plan = self._plan(plan_id)
        if (self.closed or generation != runtime["generation"] or not plan or not plan["enabled"]
            or (token is not None and token != runtime["timer_token"])):
            return
        self._cancel_timer(runtime)
        if plan["trigger"]["type"] == "lux":
            if not self._lux(plan):
                runtime["latched"] = False
                runtime["lux_ready"] = False
                runtime["lux_epoch"] += 1
                runtime["last_attempt_date"] = None
                return
            window = plan["condition"].get("time_window")
            if window:
                runtime["lux_ready"] = True
                now = dt_util.now()
                day = now.date().isoformat()
                last_run = self.store.data["settings"].get("schedule_last_run_dates", {}).get(plan_id)
                if (not window_is_open(self.hass, window, now)
                    or now.weekday() not in plan["condition"]["weekdays"]
                    or day in (last_run, runtime["last_attempt_date"])):
                    self._arm(plan_id)
                    return
                runtime["last_attempt_date"] = day
                self._arm(plan_id)
            else:
                runtime["latched"] = True
        else:
            self._arm(plan_id)
        task = self.hass.async_create_task(
            self._execute(plan_id, generation, lux_epoch=runtime["lux_epoch"]),
            "Lichtzentrale Zeitplan")
        runtime["tasks"].add(task)

        def done(completed):
            runtime["tasks"].discard(completed)
            if not completed.cancelled() and (error := completed.exception()):
                if generation == runtime["generation"]:
                    runtime["last_error"] = str(error)
                _LOGGER.warning("Zeitplan konnte nicht ausgeführt werden: %s", error)

        task.add_done_callback(done)

    def list_schedules(self):
        result = []
        for plan in self.store.data.get("schedules", []):
            runtime = self._state(plan["id"])
            when = runtime["next_run"] if plan["enabled"] else None
            result.append({**deepcopy(plan), "next_run": when.isoformat() if when else None,
                           "last_error": runtime["last_error"]})
        return result

    def _conditions(self, plan, targets):
        condition = plan["condition"]
        now = dt_util.now()
        if (now.weekday() not in condition["weekdays"]
            or not window_is_open(self.hass, condition.get("time_window"), now)):
            return False
        persons = condition["person_entity_ids"]
        eligible = {p["entity_id"] for p in list_persons(self.hass) if p["available"]}
        if persons and (any(p not in eligible for p in persons)
                        or not any(self.hass.states.get(p).state == "home" for p in persons)):
            return False
        states = [self.hass.states.get(e) for e in targets]
        if not states or any(s is None or s.state not in {"on", "off"}
                             or s.attributes.get("restored") for s in states):
            return False
        if condition["light_state"] == "on":
            return any(s.state == "on" for s in states)
        if condition["light_state"] == "off":
            return all(s.state == "off" for s in states)
        return True

    async def async_test(self, schedule_id, context=None):
        """Perform the real action once, bypassing trigger/enabled, never conditions."""
        runtime = self._state(schedule_id)
        generation = runtime["generation"]
        task = asyncio.current_task()
        runtime["tasks"].add(task)
        try:
            return await self._execute(schedule_id, generation, context, test=True)
        except Exception as error:
            if generation == runtime["generation"]:
                runtime["last_error"] = str(error)
            raise
        finally:
            runtime["tasks"].discard(task)

    async def _execute(self, plan_id, generation, context=None, *, test=False, lux_epoch=None):
        runtime = self._state(plan_id)
        async with runtime["lock"]:
            plan = self._plan(plan_id)
            if self.closed or generation != runtime["generation"]:
                raise ServiceValidationError("Der Zeitplan wurde zwischenzeitlich geändert.")
            if plan is None:
                raise ServiceValidationError("Der Zeitplan wurde nicht gefunden.")
            if not test and not plan["enabled"]:
                return {"condition_met": False, "applied": [], "skipped": [], "reason": "disabled"}
            plan = validate_schedule(self.hass, self.store, plan)
            targets = action_targets(self.hass, self.store, plan["action"])
            if not self._conditions(plan, targets):
                return {"condition_met": False, "applied": [], "skipped": [], "reason": "conditions"}
            if (not test and plan["trigger"]["type"] == "lux"
                and plan["condition"].get("time_window")):
                if (not self._lux(plan) or not runtime["lux_ready"]
                    or lux_epoch != runtime["lux_epoch"]):
                    return {"condition_met": False, "applied": [], "skipped": [], "reason": "lux"}
                execution_day = dt_util.now().date().isoformat()
                claimed = await self.store.async_claim_schedule_day(plan_id, execution_day)
                if not claimed:
                    return {"condition_met": False, "applied": [], "skipped": [], "reason": "daily_limit"}
            context = context or Context()
            action, transition = plan["action"], plan["transition"]
            kind = action["type"]

            def dispatch_guard():
                # Unlike the full condition, time/lux eligibility must survive
                # asynchronous preparation without rechecking a batch's own on/off changes.
                if self.closed or generation != runtime["generation"]:
                    raise ServiceValidationError("Der Zeitplan wurde zwischenzeitlich geändert.")
                if self._plan(plan_id) != plan:
                    raise ServiceValidationError("Der Zeitplan wurde zwischenzeitlich geändert.")
                return (window_is_open(self.hass, plan["condition"].get("time_window"))
                        and (test or plan["trigger"]["type"] != "lux"
                             or not plan["condition"].get("time_window")
                             or (self._lux(plan) and runtime["lux_ready"]
                                 and lux_epoch == runtime["lux_epoch"]
                                 and dt_util.now().date().isoformat() == execution_day)))

            def guard():
                return (dispatch_guard()
                        and self._conditions(plan, action_targets(self.hass, self.store, action)))

            launch_guard = dispatch_guard if plan["condition"].get("time_window") else None

            if kind == "scene":
                from .scenes import async_apply_scene

                result = await async_apply_scene(self.hass, self.store, action["scene_id"],
                    context=context, transition=transition, guard=guard, dispatch_guard=launch_guard)
            elif kind == "adaptive":
                from .adaptive import async_set_adaptive

                result = await async_set_adaptive(self.hass, self.store, action["area_id"],
                    enabled=action["enabled"], context=context, transition=transition,
                    guard=guard, dispatch_guard=launch_guard)
            elif kind == "room_off":
                from .rooms import async_toggle_room

                result = await async_toggle_room(self.hass, self.store, action["area_id"],
                    on=False, context=context, transition=transition,
                    guard=guard, dispatch_guard=launch_guard)
            elif kind == "lights":
                from .selected_lights import async_control_lights

                result = await async_control_lights(self.hass, self.store, action["entity_ids"],
                    on=action["on"], brightness=action["brightness"], transition=transition,
                    context=context, guard=guard, dispatch_guard=launch_guard)
            else:
                result = await self.store.async_set_motion_enabled(
                    action["area_id"], action["enabled"], guard=guard)
            response = {"condition_met": True, "applied": [], "skipped": []}
            if isinstance(result, dict):
                response.update({key: result[key] for key in ("applied", "skipped", "failed")
                                 if key in result})
            runtime["last_error"] = (
                "Nicht alle Ziele konnten geschaltet werden."
                if response.get("skipped") or response.get("failed") else None)
            return response

    async def shutdown(self):
        if self.closed:
            return
        self.closed = True
        if self._unsub_start:
            self._unsub_start()
        if self._unsub:
            self._unsub()
        tasks = set()
        for runtime in self._runtime.values():
            runtime["generation"] += 1
            self._cancel_timer(runtime)
            tasks.update(runtime["tasks"])
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
