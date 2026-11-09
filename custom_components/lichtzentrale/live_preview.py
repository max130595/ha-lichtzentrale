# Geändert für Lichtzentrale
"""Bounded, connection-owned scene trials with conservative transactional rollback."""

import asyncio
import logging
from copy import deepcopy
from uuid import uuid4

from homeassistant.const import EVENT_CALL_SERVICE, EVENT_STATE_CHANGED
from homeassistant.core import Context, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.event import async_call_later

from .const import DOMAIN
from .dynamic_scenes import manager, stop_dynamic
from .lights import validate_lights
from .palette_catalogue import validate_palette
from .rooms import _remember_light, async_dispatch, light_service_data, locked_room, room_targets
from .scenes import async_apply_scene_draft, async_save_scene, validate_scene
from .zones import contains

TIMEOUT_SECONDS = 120
_LOGGER = logging.getLogger(__name__)


class LivePreviewManager:
    """Never grant targets, persist draft rows, or roll back newer manual work."""

    def __init__(self, hass, store):
        self.hass, self.store = hass, store
        self.sessions = {}
        self.closed = False

    def _get(self, preview_id, owner):
        session = self.sessions.get(preview_id)
        if session is None or session["owner"] is not owner or session["closing"]:
            raise ServiceValidationError("Die Live-Probe ist abgelaufen. Bitte erneut öffnen.")
        return session

    def _refresh(self, session):
        if cancel := session.pop("timer", None):
            cancel()

        @callback
        def expired(_now):
            self._queue_cancel(session)

        session["timer"] = async_call_later(self.hass, TIMEOUT_SECONDS, expired)

    @callback
    def _queue_cancel(self, session):
        if session["closing"]:
            return
        session["closing"] = True
        self.hass.async_create_task(self._finish(session, restore=True), "Lichtzentrale Live-Probe beenden")

    def _allowed(self, session, entity_id):
        if entity_id not in session["original"] or entity_id in session["released"]:
            return False
        if entity_id not in self.store.data["settings"]["light_entity_ids"]:
            return False
        if not contains(self.hass, self.store, session["area_id"], entity_id):
            return False
        try:
            validate_lights(self.hass, [entity_id])
        except ServiceValidationError:
            return False
        return True

    async def begin(self, area_id, owner, context=None):
        if self.closed:
            raise ServiceValidationError("Lichtzentrale ist nicht geladen.")
        for previous in list(self.sessions.values()):
            if previous["owner"] is owner:
                previous["closing"] = True
                await self._finish(previous, restore=True)
        async with locked_room(self.hass, self.store, area_id):
            targets = room_targets(self.hass, self.store, area_id)
            if not targets:
                raise ServiceValidationError("Das Ziel enthält keine freigegebenen Lampen.")
            if any(set(targets) & set(s["original"]) for s in self.sessions.values()):
                raise ServiceValidationError("Für diese Lampen ist bereits eine Live-Probe geöffnet.")
            # Snapshot immediately before editor ownership. Existing loops must not
            # keep changing the captured lamps while the user edits their first value.
            await stop_dynamic(self.hass, area_id)
            original = {e: _remember_light(state) for e in targets
                        if (state := self.hass.states.get(e)) and state.state in {"on", "off"}}
            identifier = str(uuid4())
            session = {"id": identifier, "area_id": area_id, "owner": owner,
                       "original": original, "released": set(), "touched": set(),
                       "context": Context(user_id=getattr(context, "user_id", None)),
                       "lock": asyncio.Lock(), "sequence": -1, "generation": 0, "closing": False}
            self.sessions[identifier] = session

            @callback
            def changed(event):
                entity_id = event.data.get("entity_id")
                if entity_id not in original:
                    return
                old, new = event.data.get("old_state"), event.data.get("new_state")
                own = new is not None and (new.context.id == session["context"].id or new.context.parent_id == session["context"].id)
                if own:
                    session["touched"].add(entity_id)
                elif old is not None and new is not None and (
                    (old.state in {"on", "off"} and new.state in {"on", "off"}
                     and old.state != new.state)
                    or (new.context.user_id is not None and old.attributes != new.attributes)
                ):
                    # Delayed attribute-only device reports carry no command
                    # context. Keep rollback ownership unless a user changed them.
                    session["released"].add(entity_id)
                    session["generation"] += 1

            @callback
            def called(event):
                if event.data.get("domain") not in {"light", "switch"}:
                    return
                raw = event.data.get("service_data", {}).get("entity_id", [])
                targets_called = [raw] if isinstance(raw, str) else raw
                if not isinstance(targets_called, (list, tuple, set)):
                    return
                affected = set(targets_called) & set(original)
                if event.context.id == session["context"].id or event.context.parent_id == session["context"].id:
                    session["touched"].update(affected)
                elif affected:
                    session["released"].update(affected)
                    session["generation"] += 1

            session["unsubscribe"] = [self.hass.bus.async_listen(EVENT_STATE_CHANGED, changed),
                                      self.hass.bus.async_listen(EVENT_CALL_SERVICE, called)]
            if hasattr(owner, "subscriptions"):
                key = f"lichtzentrale_preview_{identifier}"
                owner.subscriptions[key] = lambda: self._queue_cancel(session)
                session["subscription_key"] = key
            self._refresh(session)
            from .moon import illuminated_fraction

            return {"preview_id": identifier, "area_id": area_id, "expires_in": TIMEOUT_SECONDS,
                    "moon_fraction": illuminated_fraction(), "lights": deepcopy(original)}

    def keepalive(self, preview_id, owner):
        session = self._get(preview_id, owner)
        self._refresh(session)
        return {"expires_in": TIMEOUT_SECONDS}

    def _draft(self, session, scene=None, palette=None):
        if (scene is None) == (palette is None):
            raise ServiceValidationError("Bitte genau eine Szene oder Palette für die Live-Probe angeben.")
        override = None
        if palette is not None:
            override = validate_palette(palette)
            scene = {"name": override["name"], "area_id": session["area_id"], "kind": "palette",
                     "palette_id": override["id"], "brightness": override["bri"],
                     "dynamic": {"enabled": False, "tempo": override["tempo"]}}
        if scene.get("area_id") != session["area_id"] or scene.get("kind") not in {"palette", "snapshot"}:
            raise ServiceValidationError("Die Live-Probe bleibt auf dem geöffneten Raum oder der Zone.")
        validate_scene(self.hass, self.store, scene, palette_override=override)
        return scene, override

    async def _apply(self, session, scene=None, palette=None):
        draft, override = self._draft(session, scene, palette)
        generation = session["generation"]
        targets = [e for e in session["original"] if self._allowed(session, e)]
        if not targets:
            return {"applied": [], "skipped": list(session["original"])}

        def current():
            return (not self.closed and not session["closing"]
                    and session["generation"] == generation
                    and all(self._allowed(session, e) for e in targets))

        result = await async_apply_scene_draft(self.hass, self.store, draft, session["context"],
            palette_override=override, targets=targets, dispatch_guard=current)
        session["touched"].update(result.get("applied", []))
        result["skipped"] = list(dict.fromkeys([*result.get("skipped", []), *session["released"]]))
        return result

    async def apply(self, preview_id, owner, *, sequence, scene=None, palette=None):
        session = self._get(preview_id, owner)
        if type(sequence) is not int or sequence < 0:
            raise ServiceValidationError("Ungültige Reihenfolge der Live-Probe.")
        session["sequence"] = max(session["sequence"], sequence)
        async with session["lock"]:
            self._get(preview_id, owner)
            if sequence < session["sequence"]:
                return {"applied": [], "skipped": [], "sequence": sequence, "superseded": True}
            self._refresh(session)
            return {**await self._apply(session, scene, palette), "sequence": sequence}

    async def commit(self, preview_id, owner, *, scene=None, palette=None):
        session = self._get(preview_id, owner)
        async with session["lock"]:
            self._get(preview_id, owner)
            result = await self._apply(session, scene, palette)
            if result.get("failed"):
                raise ServiceValidationError("Einzelne Lampen antworten nicht. Die Live-Probe bleibt zum Wiederholen geöffnet.")
            if scene is not None:
                saved = await async_save_scene(self.hass, self.store, scene)
                result["scene"] = saved
            else:
                saved = await self.store.async_save_palette(palette)
                result["palette"] = saved
            # The document is now durably saved. A playback/status failure must
            # not invite a retry that creates a second copy of a new document.
            try:
                await self._stop_own(session)
                if scene is not None:
                    if active := manager(self.hass):
                        if saved.get("dynamic", {}).get("enabled") or any(v.get("mode") == "moon" for v in saved.get("lamp_settings", {}).values()):
                            eligible = [e for e in result.get("applied", []) if self._allowed(session, e)]
                            await active.start(saved, session["context"], eligible)
                    if result.get("applied"):
                        await self.store.async_set_last_scene(session["area_id"], saved["id"])
            except Exception:
                _LOGGER.exception("Gespeicherte Live-Probe konnte nicht vollständig als laufende Szene übernommen werden")
                result.setdefault("notes", []).append("Gespeichert. Die Wiedergabe konnte nicht vollständig übernommen werden; bitte die gespeicherte Szene erneut starten.")
            session["closing"] = True
            self._dispose(session)
            return result

    async def _stop_own(self, session):
        if active := manager(self.hass):
            run = active.active.get(session["area_id"])
            context = run.get("context") if run else None
            if context is not None and context.id == session["context"].id:
                await active.stop(session["area_id"])

    def _dispose(self, session):
        if cancel := session.pop("timer", None):
            cancel()
        for unsubscribe in session.pop("unsubscribe", []):
            unsubscribe()
        if key := session.pop("subscription_key", None):
            session["owner"].subscriptions.pop(key, None)
        self.sessions.pop(session["id"], None)

    async def _finish(self, session, *, restore, retain_failed=False):
        async with session["lock"]:
            if session["id"] not in self.sessions:
                return {"applied": [], "skipped": []}
            await self._stop_own(session)
            result = {"applied": [], "skipped": []}
            try:
                if restore:
                    # Do not rely on a stale precomputed target set after a lock or
                    # service yield. Every restore checks the current grant again.
                    calls = []
                    prepared = {}
                    for entity_id in session["touched"]:
                        state = self.hass.states.get(entity_id)
                        if (not self._allowed(session, entity_id) or state is None
                                or state.state not in {"on", "off"}):
                            result["skipped"].append(entity_id)
                            continue
                        payload = light_service_data(state, transition=0, **session["original"][entity_id])
                        if payload:
                            calls.append((state.domain, *payload))
                            prepared[entity_id] = state
                    def safe(entity_id):
                        return self._allowed(session, entity_id) and self.hass.states.get(entity_id) is prepared[entity_id]
                    result = await async_dispatch(self.hass, calls, result["skipped"], session["context"], guard=safe)
                return result
            finally:
                if result.get("failed") and retain_failed and not self.closed:
                    # A retry must touch only lamps that actually failed, never
                    # replay successful rollback over a newer manual change.
                    session["touched"] = set(result["failed"])
                    session["closing"] = False
                    self._refresh(session)
                else:
                    if result.get("failed"):
                        _LOGGER.warning("Einzelne Lampen der beendeten Live-Probe konnten nicht wiederhergestellt werden")
                    self._dispose(session)

    async def cancel(self, preview_id, owner):
        if preview_id not in self.sessions:
            return {"applied": [], "skipped": [], "expired": True}
        session = self._get(preview_id, owner)
        session["closing"] = True  # Fence an in-flight apply before waiting for its lock.
        return await self._finish(session, restore=True, retain_failed=True)

    async def async_invalidate(self, entity_ids=None):
        for session in list(self.sessions.values()):
            if entity_ids is None or set(entity_ids) & set(session["original"]):
                session["closing"] = True
                await self._finish(session, restore=True)

    async def shutdown(self):
        self.closed = True
        await self.async_invalidate()


def preview_manager(hass):
    result = hass.data.get(DOMAIN, {}).get("live_preview")
    if result is None:
        raise ServiceValidationError("Lichtzentrale ist nicht geladen.")
    return result
