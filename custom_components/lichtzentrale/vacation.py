# Geändert für Lichtzentrale
"""Manual vacation runtime: cancellable plans and conservative lamp ownership."""

import asyncio
import logging
import secrets
from copy import deepcopy
from datetime import datetime, timedelta

from homeassistant.const import EVENT_CALL_SERVICE, EVENT_STATE_CHANGED
from homeassistant.core import Context, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .rooms import room_targets
from .vacation_planner import SAFETY_LATE_GRACE, SAFETY_RETRY_DELAY

_LOGGER = logging.getLogger(__name__)
_UNSET = object()


def vacation_paused(hass):
    manager = hass.data.get(DOMAIN, {}).get("vacation")
    return bool(manager and manager.paused)


def _instant(value):
    return dt_util.as_utc(datetime.fromisoformat(value))


class VacationManager:
    """One serialized timer; each dispatch rechecks live grants and ownership."""

    def __init__(self, hass, store):
        self.hass, self.store = hass, store
        self.closed = False
        self._lock = asyncio.Lock()
        self._timer = None
        self._unsubs = []
        self._tasks = set()
        self._generation = 0
        self._plan = []
        self._done = set()
        self._active = {}
        self._owned = {}
        self._contexts = set()
        self._excluded = set()
        self._sections = {}
        self._day = None
        self._test_until = None
        self._last_error = None
        self._transitioning = False
        self._stop_requested = False
        self._pending_stops = 0
        self._stop_failed = False

    @property
    def paused(self):
        return bool(self._transitioning or self.store.data.get("vacation", {}).get("enabled") or self._test_until)

    @property
    def config(self):
        return self.store.data["vacation"]["config"]

    def _spawn(self, coro):
        task = self.hass.async_create_task(coro, "Lichtzentrale Urlaubsmodus")
        self._tasks.add(task)
        def done(completed):
            self._tasks.discard(completed)
            if not completed.cancelled() and (error := completed.exception()):
                self._last_error = str(error)
                _LOGGER.warning("Urlaubsmodus: %s", error)
                self._arm(30)
        task.add_done_callback(done)

    @callback
    def start(self):
        if self._unsubs or self.closed:
            return
        self._unsubs = [self.hass.bus.async_listen(EVENT_CALL_SERVICE, self._called),
                        self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._changed)]
        if self.paused:
            self._pause_changed(True)
        self._spawn(self._startup())

    async def _startup(self):
        # HA can restore stale on states. Only an identical live command context
        # proves ownership, never an equal brightness/color snapshot alone.
        from .lights import entity_area_id
        async with self._lock:
            saved = self.store.data.get("vacation", {}).get("runtime", {})
            # Section clocks and button exclusions survive a restart, unlike
            # unknown lamp ownership. Never replay a trial after restarting.
            if self.store.data["vacation"].get("enabled"):
                self._sections = deepcopy(saved.get("sections", {}))
                self._excluded = {tuple(pair) for pair in saved.get("excluded", [])}
            for entity, record in saved.get("owned", {}).items():
                state = self.hass.states.get(entity)
                if (state and state.state == "on" and not state.attributes.get("restored")
                        and state.context.id == record.get("context_id")
                        and entity_area_id(self.hass, entity) == record.get("physical_area")):
                    self._owned[entity] = record
                    self._contexts.add(record["context_id"])
            await self._cleanup()
        await self._tick()

    def _pause_changed(self, paused):
        for key in ("motion", "brightness", "schedules"):
            manager = self.hass.data.get(DOMAIN, {}).get(key)
            if manager and hasattr(manager, "vacation_changed"):
                manager.vacation_changed(paused)
        bindings = self.hass.data.get(DOMAIN, {}).get("bindings")
        if bindings and hasattr(bindings, "ambient_first"):
            bindings.ambient_first.records.clear()
        self._publish()

    def _publish(self):
        from homeassistant.helpers.dispatcher import async_dispatcher_send
        async_dispatcher_send(self.hass, "lichtzentrale_vacation_updated")
        self.hass.bus.async_fire("lichtzentrale_vacation_updated")

    async def _stop_automatic_dynamics(self):
        data = self.hass.data.get(DOMAIN, {})
        contexts = set()
        for key in ("motion", "schedules"):
            contexts.update(getattr(data.get(key), "_contexts", ()))
        dynamic = data.get("dynamic")
        if dynamic:
            for area, run in list(dynamic.active.items()):
                if run.get("context") and run["context"].id in contexts:
                    await dynamic.stop(area)

    async def _persist(self):
        await self.store.async_update_vacation({"runtime": {
            "owned": deepcopy(self._owned), "sections": deepcopy(self._sections),
            "excluded": [list(pair) for pair in sorted(self._excluded)],
        }})
        self._publish()

    def _arm(self, seconds):
        if self._timer:
            self._timer.cancel()
        self._timer = None
        if not self.closed and self.paused:
            self._timer = self.hass.loop.call_later(max(.05, seconds), lambda: self._spawn(self._tick()))

    async def async_set_enabled(self, enabled, until=_UNSET, context=None):
        if type(enabled) is not bool:
            raise ServiceValidationError("Bitte den Urlaubsmodus ein- oder ausschalten.")
        if not enabled:
            # Fence a batch immediately, before waiting for its runtime lock.
            self._pending_stops += 1
            self._stop_requested = True
            self._generation += 1
        try:
            async with self._lock:
                previous = self.paused
                keep_sections = enabled and self.store.data["vacation"].get("enabled")
                self._transitioning = True
                try:
                    await self.store.async_update_vacation({"enabled": enabled, **({"until": until} if until is not _UNSET else {})})
                    self._generation += 1
                    self._test_until = None
                    self._pause_changed(True)
                    await self._stop_automatic_dynamics()
                    await self._cleanup()
                    self._reset_plan(clear_sections=not keep_sections)
                    await self._persist()
                finally:
                    self._transitioning = False
                    self._pause_changed(self.paused)
                if previous != enabled:
                    await self._notify(enabled)
            self._stop_failed = False
            if self._last_error == "Ausschalten wurde unterbrochen. Bitte erneut ausschalten.":
                self._last_error = None
        except BaseException:
            if not enabled:
                # A failed stop must not silently restart simulation commands.
                # Expose the fence through the existing error display and allow
                # a successful explicit retry to clear it.
                self._stop_failed = True
                self._last_error = "Ausschalten wurde unterbrochen. Bitte erneut ausschalten."
                self._publish()
            raise
        finally:
            # Include cancelled waiters that never acquired the runtime lock.
            if not enabled:
                self._pending_stops -= 1
            self._stop_requested = self._stop_failed or self._pending_stops > 0
        await self._tick()
        return self.status()

    async def async_save_config(self, config, until=_UNSET):
        async with self._lock:
            previous = self.config
            await self.store.async_update_vacation({"config": config, **({"until": until} if until is not _UNSET else {})})
            # An edited future window must take effect. Started/completed
            # sections retain their original endpoint and button exceptions.
            changed = {name for name in ("morning", "evening") if previous[name] != self.config[name]}
            now = dt_util.utcnow()
            self._sections = {key: section for key, section in self._sections.items()
                              if section["section"] not in changed or _instant(section["start"]) <= now}
            self._generation += 1
            await self._cleanup()
            self._reset_plan(clear_sections=False)
            await self._persist()
        await self._tick()
        return self.status()

    def _reset_plan(self, *, clear_sections=True):
        self._plan, self._done, self._active = [], set(), {}
        if clear_sections:
            self._excluded.clear()
            self._sections.clear()
        self._day = None

    async def async_test(self, context=None):
        if self.paused:
            raise ServiceValidationError("Bitte zuerst den laufenden Urlaubsmodus oder Probelauf ausschalten.")
        if not any(r["weight"] > 0 for r in self.config["rooms"]):
            raise ServiceValidationError("Bitte zuerst Räume für den Probelauf auswählen.")
        async with self._lock:
            if self.paused:
                raise ServiceValidationError("Bitte zuerst den laufenden Urlaubsmodus oder Probelauf ausschalten.")
            self._generation += 1
            await self._cleanup()
            self._reset_plan()
            now = dt_util.utcnow()
            self._test_until = now + timedelta(minutes=5)
            self._pause_changed(True)
            await self._stop_automatic_dynamics()
            rooms = [room for room in self.config["rooms"] if room["weight"] > 0]
            # Sequential compressed intervals genuinely span five minutes and
            # honor even max_rooms=1. No unselected room can enter the test.
            duration = 300 / len(rooms)
            self._plan = [{"area_id": room["area_id"], "section": "test", "section_id": "test:" + now.isoformat(),
                           "start": (now + timedelta(seconds=i * duration)).isoformat(),
                           "end": (now + timedelta(seconds=(i + 1) * duration)).isoformat(),
                           "on_behavior": room["on_behavior"]} for i, room in enumerate(rooms)]
            self._day = dt_util.now().date()
        await self._tick()
        return self.status()

    async def _build(self, now):
        from .vacation_planner import build_plan, build_sections
        learned = None
        if self.config.get("learn_history"):
            from .vacation_history import async_learn_history
            try:
                learned = await async_learn_history(self.hass, self.store, self.config, now)
            except Exception:
                _LOGGER.warning("Urlaubsmodus: Verlauf nicht verfügbar; Zufallsplan wird verwendet.")
        ongoing = [e for e in self._active.values() if _instant(e["end"]) > now]
        seed = secrets.randbits(64)
        until = self.store.data["vacation"].get("until")
        self._sections = build_sections(self.hass, self.config, now, seed=seed,
                                        until=until, existing=self._sections)
        self._excluded = {pair for pair in self._excluded if pair[0] in self._sections}
        self._plan = build_plan(self.hass, self.config, now, seed=seed,
                                until=until, learned=learned, sections=self._sections)
        self._plan = ongoing + self._plan
        self._day = dt_util.as_local(now).date()
        self._done = set(self._active)
        await self._persist()

    async def _tick(self):
        async with self._lock:
            if self.closed or self._stop_requested:
                return
            now = dt_util.utcnow()
            until = self.store.data["vacation"].get("until")
            expired = (self.store.data["vacation"].get("enabled") and until
                       and dt_util.as_local(now).date().isoformat() > until)
            test_expired = self._test_until and now >= self._test_until
            if expired or test_expired:
                if expired:
                    # A section clipped to the end-date midnight still gets its
                    # due safety pass while enabled; never retry after disabling.
                    await self._safety_tick(now)
                self._generation += 1
                await self._cleanup()
                self._test_until = None
                self._reset_plan()
                await self._persist()
                if expired:
                    await self.store.async_update_vacation({"enabled": False, "until": None})
                    await self._notify(False)
                self._pause_changed(self.paused)
            if not self.paused:
                if self._timer:
                    self._timer.cancel()
                    self._timer = None
                return
            if not self._test_until and self._day != dt_util.as_local(now).date():
                # Keep ongoing overnight intervals until their own end, but do
                # not replay past starts when generating today's fresh plan.
                await self._build(now)
            # Retain temporarily unavailable owned lamps after their visit and
            # retry cleanup when they return, rather than silently forgetting.
            orphaned = {tuple(record["key"]) for record in self._owned.values()
                        if tuple(record["key"]) not in self._active}
            for key in orphaned:
                await self._cleanup(key)
            for key, entry in list(self._active.items()):
                if _instant(entry["end"]) <= now:
                    await self._cleanup(key)
                    self._active.pop(key, None)
            for index, entry in enumerate(self._plan):
                if self._stop_requested:
                    break
                key = (entry["section_id"], entry["area_id"], entry["start"])
                if key in self._done or _instant(entry["start"]) > now:
                    continue
                self._done.add(key)
                if (_instant(entry["end"]) <= now or (entry["section_id"], entry["area_id"]) in self._excluded
                        or len(self._active) >= self.config["max_rooms"]
                        or any(active["area_id"] == entry["area_id"] for active in self._active.values())):
                    continue
                self._active[key] = entry
                try:
                    await self._activate(key, entry)
                except Exception as error:
                    if not self._stop_requested:
                        self._last_error = str(error)
                        _LOGGER.warning("Urlaubsmodus: Raum konnte nicht gestartet werden: %s", error)
            # The section boundary wins over a visit that starts on this tick,
            # including overlapping configured morning/evening windows.
            await self._safety_tick(now)
            times = [_instant(e[k]) for e in self._plan for k in ("start", "end") if _instant(e[k]) > now]
            times.extend(_instant(e["end"]) for e in self._active.values() if _instant(e["end"]) > now)
            if self._test_until:
                times.append(self._test_until)
            elif self._safety_enabled():
                for section in self._sections.values():
                    end = _instant(section["end"])
                    for field, at in (("end_done", end), ("retry_done", end + SAFETY_RETRY_DELAY)):
                        if not section[field] and at > now:
                            times.append(at)
            self._arm(min(30, max(.05, (min(times) - dt_util.utcnow()).total_seconds())) if times else 30)
            self._publish()

    def _safety_enabled(self):
        return bool(not self.closed and not self._stop_requested and not self._test_until
                    and self.store.data["vacation"].get("enabled")
                    and self.config.get("safety_off", True))

    def _room_members(self, area):
        """Resolve each current granted member without one stale sibling masking it."""
        from .zones import contains, validate_area

        try:
            validate_area(self.hass, self.store, area)
        except ServiceValidationError:
            return set()
        return {entity for entity in self.store.data["settings"]["light_entity_ids"]
                if contains(self.hass, self.store, area, entity)}

    def _safety_targets(self, section_id):
        """Current approved selection minus every overlapping excluded room."""
        from .lights import is_individual_light

        selected, excluded = set(), set()
        for room in self.config["rooms"]:
            selected.update(self._room_members(room["area_id"]))
        for section, area in self._excluded:
            if section == section_id:
                excluded.update(self._room_members(area))
        return {entity for entity in selected - excluded
                if (state := self.hass.states.get(entity)) and is_individual_light(self.hass, state)}

    async def _safety_tick(self, now):
        if not self._safety_enabled():
            return
        for section_id, section in self._sections.items():
            if not self._safety_enabled():
                return
            if section["section"] == "morning" and not self.config["morning"]["enabled"]:
                continue
            end = _instant(section["end"])
            retry = end + SAFETY_RETRY_DELAY
            if now < end or section["retry_done"]:
                continue
            # A late tick/restart within the retry window catches the first
            # boundary once. At +10 it performs only the retry, never two passes.
            if now >= retry:
                section["end_done"] = section["retry_done"] = True
            elif not section["end_done"]:
                section["end_done"] = True
            else:
                continue
            # Persist the attempt before dispatch: a restart cannot repeat it.
            await self._persist()
            if now <= retry + SAFETY_LATE_GRACE:
                await self._safety_off(section_id)

    async def _safety_off(self, section_id):
        from .lights import entity_area_id
        from .selected_lights import _still_allowed, async_control_lights

        generation = self._generation
        for entity in sorted(self._safety_targets(section_id)):
            if not self._safety_enabled() or generation != self._generation:
                break
            context = Context()
            self._contexts.add(context.id)
            physical_area = entity_area_id(self.hass, entity)
            nonowned = entity not in self._owned

            def guard():
                state = self.hass.states.get(entity)
                return bool(self._safety_enabled() and generation == self._generation
                    and entity in self._safety_targets(section_id)
                    and state and state.state == "on"
                    and _still_allowed(self.hass, self.store, entity, {entity: physical_area}))

            try:
                if not guard():
                    continue
                result = await async_control_lights(self.hass, self.store, [entity], on=False,
                                                   context=context, guard=guard, dispatch_guard=guard)
                if entity in result.get("applied", []):
                    self._owned.pop(entity, None)
                    if nonowned:
                        _LOGGER.info("Urlaubsmodus: Sicherheitsabschaltung hat eine nicht von der "
                                     "Simulation eingeschaltete Lampe ausgeschaltet: %s", entity)
                elif not self._stop_requested:
                    self._last_error = "Eine Lampe konnte bei der Sicherheitsabschaltung nicht ausgeschaltet werden."
            except Exception as error:
                if not self._stop_requested:
                    self._last_error = str(error)
                    _LOGGER.warning("Urlaubsmodus: Sicherheitsabschaltung fehlgeschlagen: %s", error)
        await self._persist()

    async def _activate(self, key, entry):
        from .lights import entity_area_id
        from .selected_lights import async_control_lights
        area = entry["area_id"]
        targets = room_targets(self.hass, self.store, area)
        # Never take over lamps already on, including another selected zone.
        targets = [e for e in targets if (s := self.hass.states.get(e)) and s.state == "off"]
        if not targets:
            return
        context, generation = Context(), self._generation
        self._contexts.add(context.id)
        records = {e: {"area_id": area, "physical_area": entity_area_id(self.hass, e),
                        "context_id": context.id, "key": list(key)} for e in targets}
        # Reserve before dispatch, so an intervening external service can release
        # ownership and prevent subsequent commands in this same batch.
        self._owned.update(records)
        def guard(scope=None):
            scope = targets if scope is None else scope
            valid = (not self.closed and not self._stop_requested and self.paused and generation == self._generation
                     and (entry["section_id"], area) not in self._excluded
                     and _instant(entry["end"]) > dt_util.utcnow()
                     and set(scope) <= set(room_targets(self.hass, self.store, area)))
            if not valid or any(self._owned.get(e) is not records[e] for e in scope):
                raise ServiceValidationError("Die Simulation wurde durch Bedienung oder eine Änderung unterbrochen.")
            return True
        behavior = entry["on_behavior"]
        result = {}
        try:
            if behavior["mode"] == "scene":
                from .scenes import async_apply_scene_subset
                result = await async_apply_scene_subset(self.hass, self.store, behavior["scene_id"], targets,
                    context=context, guard=guard, dispatch_guard=guard)
                scene_id = result.get("resolved_scene_id", behavior["scene_id"])
                scene = next((s for s in self.store.data["scenes"] if s["id"] == scene_id), None)
                dynamic = self.hass.data.get(DOMAIN, {}).get("dynamic")
                if scene and dynamic and scene["kind"] == "palette" and scene.get("dynamic", {}).get("enabled"):
                    applied = [e for e in result.get("applied", [])
                               if e.startswith("light.") and self._owned.get(e) is records.get(e)]

                    def dynamic_guard():
                        run = dynamic.active.get(area)
                        if not run or run.get("context") is not context:
                            return False
                        # Unapplied switches are not part of a palette run. A
                        # manually excluded lamp must not stop its neighbours.
                        scope = [e for e in applied if e in run["targets"] and e not in run["excluded"]]
                        return guard(scope)

                    await dynamic.start(scene, context, applied, persist=False, dispatch_guard=dynamic_guard)
            else:
                result = await async_control_lights(self.hass, self.store, targets, on=True, context=context,
                    brightness=behavior.get("brightness"), guard=guard, dispatch_guard=guard)
        finally:
            # A dispatched command may fail after the lamp already changed. Keep
            # live own-context ON states; never infer ownership from arbitrary ON.
            for entity, record in records.items():
                state = self.hass.states.get(entity)
                own_on = state and state.state == "on" and (state.context.id == context.id or state.context.parent_id == context.id)
                if self._owned.get(entity) is record and not own_on and entity not in result.get("applied", []):
                    self._owned.pop(entity, None)
            await self._persist()

    async def _cleanup(self, key=None):
        from .dynamic_scenes import async_exclude_targets
        from .lights import entity_area_id
        from .selected_lights import _still_allowed, async_control_lights
        selected = [e for e, record in self._owned.items() if key is None or record["key"] == list(key)]
        if not selected:
            return
        await async_exclude_targets(self.hass, selected)
        for entity in selected:
            record = self._owned.get(entity)
            if record is None:
                continue
            context = Context()
            self._contexts.add(context.id)
            def guard():
                state = self.hass.states.get(entity)
                return bool(self._owned.get(entity) is record and state and state.state == "on"
                    and entity in room_targets(self.hass, self.store, record["area_id"])
                    and _still_allowed(self.hass, self.store, entity, {entity: record["physical_area"]}))
            try:
                if not guard():
                    state = self.hass.states.get(entity)
                    if (state and state.state in {"unavailable", "unknown"}
                            and entity in room_targets(self.hass, self.store, record["area_id"])
                            and entity_area_id(self.hass, entity) == record["physical_area"]):
                        continue
                    self._owned.pop(entity, None)
                    continue
                result = await async_control_lights(self.hass, self.store, [entity], on=False, context=context,
                                                   guard=guard, dispatch_guard=guard)
                if entity in result.get("applied", []):
                    self._owned.pop(entity, None)
                else:
                    self._last_error = "Eine eigene Lampe konnte nicht ausgeschaltet werden. Erneut ausschalten versucht es nochmals."
            except Exception as error:
                self._last_error = str(error)
                _LOGGER.warning("Urlaubsmodus: Eigene Lampe konnte nicht ausgeschaltet werden: %s", error)
        await self._persist()

    async def manual_targets(self, area_id=None, entity_ids=None):
        if not self.paused:
            return
        targets = set(entity_ids or self._room_members(area_id))
        now = dt_util.utcnow()
        sections = {e["section_id"] for e in self._plan
                    if _instant(e.get("section_start", e["start"])) <= now
                    < _instant(e.get("section_end", e["end"]))}
        sections.update(e["section_id"] for e in self._active.values())
        sections.update(key for key, section in self._sections.items()
                        if _instant(section["start"]) <= now < _instant(section["end"]))
        affected = set()
        for room in self.config["rooms"]:
            area = room["area_id"]
            members = self._room_members(area)
            members.update(e for e, record in self._owned.items() if record["area_id"] == area)
            if area == area_id or targets & members:
                affected.update(members)
                self._excluded.update((section, area) for section in sections)
        for entity in affected:
            self._owned.pop(entity, None)
        from .dynamic_scenes import async_exclude_targets
        await async_exclude_targets(self.hass, affected)
        await self._persist()

    def _own(self, context):
        return context and (context.id in self._contexts or context.parent_id in self._contexts)

    @callback
    def _changed(self, event):
        entity = event.data.get("entity_id")
        if entity not in self._owned:
            return
        old, new = event.data.get("old_state"), event.data.get("new_state")
        if new and self._own(new.context):
            return
        if new and new.state in {"unavailable", "unknown"}:
            return
        # Ownership is only acquired for ON lamps. Losing connectivity and
        # returning ON is not a manual action, even with a fresh context.
        reconnect = old and old.state in {"unavailable", "unknown"}
        if (old is None or new is None or (reconnect and new.state != "on")
                or (not reconnect and old.state != new.state)
                or (not reconnect and new.context.user_id is not None and old.attributes != new.attributes)):
            self._owned.pop(entity, None)

    @callback
    def _called(self, event):
        if self._own(event.context):
            return
        data = event.data
        if data.get("domain") not in {"light", "switch", "homeassistant"} or data.get("service") not in {"turn_on", "turn_off", "toggle"}:
            return
        payload = data.get("service_data", {})
        targets = payload.get("entity_id", [])
        targets = [targets] if isinstance(targets, str) else targets
        if not isinstance(targets, (list, tuple, set)):
            targets = []
        # Both legacy groups and modern light groups expose their members.
        expanded, pending = set(targets), list(targets)
        while pending:
            state = self.hass.states.get(pending.pop())
            members = state.attributes.get("entity_id", []) if state else []
            if isinstance(members, str):
                members = [members]
            if isinstance(members, (list, tuple)):
                for member in members:
                    if isinstance(member, str) and member not in expanded:
                        expanded.add(member)
                        pending.append(member)
        targets = expanded
        broad = any(payload.get(k) for k in ("area_id", "device_id", "floor_id", "label_id")) or "all" in targets
        for entity in list(self._owned):
            if broad or entity in targets:
                self._owned.pop(entity, None)

    async def _notify(self, enabled):
        service = self.config.get("notify_service")
        if not service:
            return
        try:
            domain, name = service.split(".", 1)
            if domain == "notify" and self.hass.services.has_service(domain, name):
                await self.hass.services.async_call(domain, name, {"message": "Urlaubsmodus eingeschaltet." if enabled else "Urlaubsmodus ausgeschaltet."}, blocking=True)
        except Exception:
            _LOGGER.warning("Urlaubsmodus: Push-Hinweis konnte nicht gesendet werden.")

    def status(self):
        now = dt_util.utcnow()
        switches = [{"at": e[k], "area_id": e["area_id"], "on": k == "start"}
                    for e in self._plan for k in ("start", "end") if _instant(e[k]) > now
                    and (e["section_id"], e["area_id"]) not in self._excluded]
        return {**deepcopy(self.store.data.get("vacation", {})), "paused": self.paused, "time_zone": self.hass.config.time_zone,
                "testing": self._test_until is not None, "test_until": self._test_until.isoformat() if self._test_until else None,
                "plan": deepcopy(self._plan), "next_switch": min(switches, key=lambda e: e["at"]) if switches else None,
                "active_rooms": sorted({e["area_id"] for e in self._active.values()}),
                "excluded_rooms": sorted({area for _, area in self._excluded}),
                "excluded": sorted({area for _, area in self._excluded}),
                "section": next((e["section"] for e in self._active.values()), None),
                "notes": [self._last_error] if self._last_error else [], "last_error": self._last_error}

    async def shutdown(self):
        self.closed = True
        self._generation += 1
        if self._timer:
            self._timer.cancel()
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        # Never persist simulation dynamics: no resurrection after unload/restart.
        dynamic = self.hass.data.get(DOMAIN, {}).get("dynamic")
        if dynamic:
            for area, run in list(dynamic.active.items()):
                if self._own(run.get("context")):
                    await dynamic.stop(area)
        await self._persist()
