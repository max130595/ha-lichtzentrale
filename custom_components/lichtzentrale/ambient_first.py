# Geändert für Lichtzentrale
"""Runtime-only scene ownership and the optional ambient-first button cycle."""

import logging

from homeassistant.const import EVENT_CALL_SERVICE, EVENT_STATE_CHANGED
from homeassistant.core import Context, callback
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN
from .rooms import room_targets
from .schedule_config import validate_time_window
from .schedule_windows import window_is_open

_LOGGER = logging.getLogger(__name__)


def validate_ambient_first(hass, store, value, area_id, selected=None, *, runtime=False):
    if (not isinstance(value, dict) or set(value) != {"scene_id", "window"}
            or not isinstance(value["scene_id"], str) or not value["scene_id"]):
        raise ServiceValidationError("Bitte Ambiente-Szene und Zeitfenster auswählen.")
    targets = room_targets(hass, store, area_id)
    if not targets or (selected is not None and not set(selected) <= set(targets)):
        raise ServiceValidationError("Die Ambiente-Taste darf nur Lampen ihres Raums oder ihrer Zone steuern.")
    scene = next((s for s in store.data["scenes"] if s["id"] == value["scene_id"]), None)
    if (scene is None and not runtime) or (scene is not None and scene["area_id"] != area_id):
        raise ServiceValidationError("Bitte eine Ambiente-Szene dieses Raums auswählen.")
    window = validate_time_window(value["window"])
    if window is None:
        raise ServiceValidationError("Bitte mindestens eine Grenze des Ambiente-Zeitfensters wählen.")
    return {"scene_id": value["scene_id"], "window": window}


class AmbientFirstTracker:
    """Do not infer ownership from persisted last_scene_id after a restart."""

    def __init__(self, hass, store):
        self.hass, self.store = hass, store
        self.records = {}
        self._unsub = []

    @callback
    def start(self):
        if not self._unsub:
            self._unsub = [self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._changed),
                           self.hass.bus.async_listen(EVENT_CALL_SERVICE, self._called)]

    @callback
    def shutdown(self):
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()
        self.records.clear()

    @callback
    def scene_started(self, scene, context, result):
        """Called for successful persisted recalls from every public scene path."""
        area = scene["area_id"]
        self.records.pop(area, None)
        if (not result.get("applied") or result.get("failed")
                or any(not e.startswith("switch.") or scene["kind"] == "snapshot" for e in result.get("skipped", []))):
            return
        self.records[area] = {"scene_id": scene["id"], "context": context,
                              "targets": set(room_targets(self.hass, self.store, area)),
                              "scene_targets": set(result["applied"])}

    def running(self, area, scene_id):
        record = self.records.get(area)
        if not record or record["scene_id"] != scene_id:
            return False
        if self.store.data["rooms"].get(area, {}).get("last_scene_id") != scene_id:
            return False
        if record["targets"] != set(room_targets(self.hass, self.store, area)):
            self.records.pop(area, None)
            return False
        dynamic = self.hass.data.get(DOMAIN, {}).get("dynamic")
        run = dynamic.active.get(area) if dynamic else None
        return bool((run and run.get("context") == record["context"])
                    or any((s := self.hass.states.get(e)) and s.state == "on"
                           for e in record["scene_targets"]))

    @callback
    def _changed(self, event):
        old, new = event.data.get("old_state"), event.data.get("new_state")
        if old is None or new is None:
            return
        for area, record in list(self.records.items()):
            if event.data.get("entity_id") not in record["targets"]:
                continue
            context = record["context"]
            if context and (new.context.id == context.id or new.context.parent_id == context.id):
                continue
            # Attribute-only Zigbee reports without user context are not manual.
            if ((old.state in {"on", "off"} and new.state in {"on", "off"} and old.state != new.state)
                    or (new.context.user_id is not None and old.attributes != new.attributes)):
                self.records.pop(area, None)

    @callback
    def _called(self, event):
        data = event.data
        if data.get("domain") not in {"light", "switch", "homeassistant"} or data.get("service") not in {"turn_on", "turn_off", "toggle"}:
            return
        payload = data.get("service_data", {})
        entities = payload.get("entity_id", [])
        entities = [entities] if isinstance(entities, str) else entities
        if not isinstance(entities, (list, tuple, set)):
            entities = []
        for area, record in list(self.records.items()):
            if record["context"] and event.context.id == record["context"].id:
                continue
            # Entity targets are normal. Area/device/group commands can affect
            # the room without an immediate state change: invalidate conservatively.
            if ("all" in entities or record["targets"].intersection(entities)
                    or payload.get("area_id") or payload.get("device_id") or payload.get("floor_id") or payload.get("label_id")):
                self.records.pop(area, None)


async def async_ambient_action(manager, binding, context):
    """Return None for ordinary behavior; otherwise execute one ambient step."""
    from .bindings import _check_scene
    from .dynamic_scenes import async_stop_room
    from .scenes import async_apply_scene
    from .selected_lights import async_control_lights, validate_selected_lights
    from .vacation import vacation_paused
    if vacation_paused(manager.hass):
        return None
    context = context or Context()
    hass, store = manager.hass, manager.store
    area, params = binding["area_id"], binding["params"]
    option = params["ambient_first"]
    if not window_is_open(hass, option["window"]):
        return None
    scene = next((s for s in store.data["scenes"] if s["id"] == option["scene_id"]), None)
    if scene is None:
        _LOGGER.warning("Ambiente-Szene der Tasterbelegung wurde gelöscht; normales Einschaltverhalten wird verwendet.")
        return None
    _check_scene(hass, store, scene["id"], area)
    room = room_targets(hass, store, area)
    targets = validate_selected_lights(hass, store, params["entity_ids"]) if "entity_ids" in params else room

    interrupted = False

    def guard():
        if interrupted:
            raise ServiceValidationError("Eine andere Bedienung hat Vorrang. Bitte erneut drücken.")
        if room_targets(hass, store, area) != room or not set(targets) <= set(room):
            raise ServiceValidationError("Die Raumzuordnung oder Freigabe hat sich geändert. Bitte erneut drücken.")
        validate_selected_lights(hass, store, targets)
        return True

    # Running wins even when the snapshot intentionally leaves button targets off.
    if manager.ambient_first.running(area, scene["id"]):
        previous_context = manager.ambient_first.records[area]["context"]
        own_ids = {context.id, previous_context.id}

        @callback
        def foreign_control(event):
            nonlocal interrupted
            if event.context.id in own_ids:
                return
            data = event.data
            if event.event_type == EVENT_CALL_SERVICE:
                if data.get("domain") not in {"light", "switch", "homeassistant"} or data.get("service") not in {"turn_on", "turn_off", "toggle"}:
                    return
                payload = data.get("service_data", {})
                entities = payload.get("entity_id", [])
                entities = [entities] if isinstance(entities, str) else entities
                if not isinstance(entities, (list, tuple, set)):
                    entities = []
                if ("all" in entities or set(room).intersection(entities)
                        or any(payload.get(key) for key in ("area_id", "device_id", "floor_id", "label_id"))):
                    interrupted = True
            elif data.get("entity_id") in room:
                old, new = data.get("old_state"), data.get("new_state")
                if old and new and new.context.parent_id not in own_ids and (
                    old.state != new.state or (new.context.user_id is not None and old.attributes != new.attributes)
                ):
                    interrupted = True

        # The component primitives own their existing locks. Fence across the
        # awaited stop/off/on phases without holding an inverted selection lock.
        unsubs = [hass.bus.async_listen(EVENT_CALL_SERVICE, foreign_control),
                  hass.bus.async_listen(EVENT_STATE_CHANGED, foreign_control)]
        try:
            manager.ambient_first.records.pop(area, None)
            guard()
            result = await async_stop_room(hass, store, area, context=context)
            guard()
            if result.get("failed"):
                return result
            others = [entity for entity in room if entity not in targets]
            if others:
                result = await async_control_lights(hass, store, others, on=False, context=context, guard=guard, dispatch_guard=guard)
                if result.get("failed") or result.get("skipped"):
                    return result
            forced = {**binding, "action": "turn_on_lights" if "entity_ids" in params else "turn_on_room",
                      "params": {key: value for key, value in params.items() if key != "ambient_first"}}
            guard()
            if params.get("on_behavior", {}).get("mode", "last") != "last":
                return await manager._with_on_behavior(forced, context, outer_guard=guard)
            # Selected targets retain their exact scope, including switch-only rooms.
            if "entity_ids" in params:
                return await async_control_lights(hass, store, targets, on=True, context=context, guard=guard, dispatch_guard=guard)
            from .rooms import async_toggle_room
            return await async_toggle_room(hass, store, area, on=True, context=context, guard=guard, dispatch_guard=guard)
        finally:
            for unsub in unsubs:
                unsub()
    if all(hass.states.get(entity).state == "off" for entity in targets):
        return await async_apply_scene(hass, store, scene["id"], context=context, guard=guard, dispatch_guard=guard)
    return None
