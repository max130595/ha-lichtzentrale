# Geändert für Lichtzentrale
"""Runtime event buttons and narrowly scoped, cancellable room actions."""

import asyncio
import json
import logging
from copy import deepcopy
from time import monotonic
from uuid import uuid4

from homeassistant.const import EVENT_STATE_CHANGED, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Context, CoreState, HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util.dt import parse_datetime

from .adaptive import async_set_adaptive
from .const import DOMAIN
from .dimming import dim_min_pct, dim_payload
from .dynamic_scenes import async_stop_room, validate_dynamic
from .lights import entity_area_id, is_individual_light
from .palettes import list_palettes
from .positions import validate_distribution
from .rooms import (
    async_dispatch,
    async_toggle_room,
    room_targets,
    validate_control_options,
)
from .scenes import _targets, async_apply_scene, async_apply_scene_subset, hue_scene_targets
from .selected_lights import (
    async_control_lights,
    async_dim_lights,
    validate_selected_lights,
)
from .storage import LichtzentraleStore

_LOGGER = logging.getLogger(__name__)
DOUBLE_RELEASE = "double_short_release"
ACTIONS = frozenset(
    {
        "toggle_lights",
        "turn_on_lights",
        "turn_off_lights",
        "toggle_room",
        "turn_on_room",
        "turn_off_room",
        "next_scene",
        "scene",
        "dim_up",
        "dim_down",
        "adaptive_on",
        "adaptive_off",
        "stop_dynamic",
        "full_brightness", "night", "return_auto", "night_auto",
    }
)
CYCLE_RESET_SECONDS = 600
ON_ACTIONS = frozenset({"toggle_lights", "turn_on_lights", "toggle_room", "turn_on_room"})


@callback
def list_buttons(hass: HomeAssistant) -> list[dict]:
    """Discover loaded event entities without installation-specific identifiers."""
    entities, devices = er.async_get(hass), dr.async_get(hass)
    result = []
    for state in hass.states.async_all("event"):
        entry = entities.async_get(state.entity_id)
        if entry and entry.disabled_by is not None:
            continue
        advertised = state.attributes.get("event_types")
        if not isinstance(advertised, (list, tuple)):
            continue
        event_types = list(
            dict.fromkeys(
                value
                for value in advertised
                if isinstance(value, str) and value and value != DOUBLE_RELEASE
            )
        )
        if "short_release" in event_types:
            event_types.append(DOUBLE_RELEASE)
        if not event_types:
            continue
        device = devices.async_get(entry.device_id) if entry and entry.device_id else None
        result.append(
            {
                "entity_id": state.entity_id,
                "name": state.name,
                "device_id": entry.device_id if entry else None,
                "device_name": (device.name_by_user or device.name or state.name)
                if device
                else state.name,
                "area_id": entity_area_id(hass, state.entity_id),
                "event_types": event_types,
                "manufacturer": device.manufacturer if device else None,
                "model": device.model if device else None,
                # An event entity is unknown until its first press, not necessarily offline.
                "available": state.state != STATE_UNAVAILABLE
                and not state.attributes.get("restored"),
            }
        )
    return sorted(
        result,
        key=lambda item: (
            (item["device_name"] or "").casefold(),
            item["name"].casefold(),
            item["entity_id"],
        ),
    )


# HA metadata describes the entity rather than the physical gesture. All other
# attribute names/values come from the observed event; no device-specific keys.
_EVENT_METADATA = frozenset({"event_type", "event_types", "friendly_name", "icon", "device_class", "restored"})


def validate_event_attributes(value):
    if not isinstance(value, dict) or len(value) > 64 or any(
        not isinstance(key, str) or not key or key in _EVENT_METADATA for key in value
    ):
        raise ServiceValidationError("Ungültige gelernte Ereignisattribute.")
    try:
        encoded = json.dumps(value, allow_nan=False)
        if len(encoded) > 8192:
            raise ValueError
        return json.loads(encoded)
    except (ValueError, TypeError, OverflowError) as error:
        raise ServiceValidationError("Ungültige gelernte Ereignisattribute.") from error


def event_attributes(state):
    return validate_event_attributes({key: value for key, value in state.attributes.items() if key not in _EVENT_METADATA})


def validate_ignored_attributes(value, attributes):
    """Only explicitly observed fields may become wildcards."""
    if (
        not isinstance(attributes, dict)
        or not isinstance(value, list)
        or len(value) > 64
        or any(not isinstance(key, str) or key not in attributes for key in value)
    ):
        raise ServiceValidationError("Ungültige als egal markierte Ereignisattribute.")
    return sorted(set(value))


def _attribute_pattern(binding):
    attributes = validate_event_attributes(binding["event_attributes"])
    ignored = validate_ignored_attributes(binding.get("ignored_event_attributes", []), attributes)
    return {key: value for key, value in attributes.items() if key not in ignored}, ignored


def _same_attributes(left, right):
    # JSON comparison keeps booleans distinct from numeric selector values.
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(
        right, sort_keys=True, allow_nan=False
    )


def _matches_payload(binding, attributes):
    # Old type-only bindings and exact learned bindings retain their semantics.
    # Only fields explicitly marked as ignored may change or disappear.
    if "event_attributes" not in binding:
        return True
    try:
        required, ignored = _attribute_pattern(binding)
        return _same_attributes(
            required, {key: value for key, value in attributes.items() if key not in ignored}
        )
    except (ServiceValidationError, TypeError, ValueError):
        return False


def matches_attributes(binding, state):
    try:
        return _matches_payload(binding, event_attributes(state))
    except ServiceValidationError:
        return False


def _specificity(binding):
    if "event_attributes" not in binding:
        return (-1, 0)
    required, ignored = _attribute_pattern(binding)
    return (len(required), -len(ignored))


def binding_patterns_conflict(left, right):
    """Reject equally specific overlapping patterns, regardless of ignored values."""
    if _specificity(left) != _specificity(right):
        return False
    if "event_attributes" not in left:
        return True
    left_values, left_ignored = _attribute_pattern(left)
    right_values, right_ignored = _attribute_pattern(right)
    left_keys, right_keys = set(left_values), set(right_values)
    return (
        left_keys <= right_keys | set(right_ignored)
        and right_keys <= left_keys | set(left_ignored)
        and all(_same_attributes(left_values[key], right_values[key]) for key in left_keys & right_keys)
    )


def _scene_for_room(store, scene_id, area_id):
    if not isinstance(scene_id, str):
        raise ServiceValidationError("Bitte eine Szene dieses Raums auswählen.")
    scene = next((s for s in store.data["scenes"] if s.get("id") == scene_id), None)
    if scene is None or scene.get("area_id") != area_id:
        raise ServiceValidationError("Bitte eine vorhandene Szene dieses Raums auswählen.")
    return scene


def validate_binding(hass, store, raw, *, _runtime=False) -> dict:
    """Normalize a closed schema without writing or calling any HA service."""
    if not isinstance(raw, dict) or set(raw) - {
        "id",
        "event_entity",
        "event_type",
        "action",
        "area_id",
        "params",
        "event_attributes",
        "ignored_event_attributes",
        "control_label",
    }:
        raise ServiceValidationError("Ungültige Tasterbelegung.")
    binding_id = raw.get("id")
    if binding_id is not None and (
        not isinstance(binding_id, str) or not binding_id or len(binding_id) > 256
    ):
        raise ServiceValidationError("Ungültige Kennung der Tasterbelegung.")
    if binding_id is not None and not any(
        item.get("id") == binding_id for item in store.data["bindings"]
    ):
        raise ServiceValidationError("Die Tasterbelegung wurde nicht gefunden. Bitte neu laden.")
    button = next(
        (b for b in list_buttons(hass) if b["entity_id"] == raw.get("event_entity")), None
    )
    event_type, action, area_id = raw.get("event_type"), raw.get("action"), raw.get("area_id")
    if button is None or not isinstance(event_type, str) or event_type not in button["event_types"]:
        raise ServiceValidationError("Bitte ein verfügbares Taster-Ereignis auswählen.")
    if not isinstance(action, str) or action not in ACTIONS:
        raise ServiceValidationError("Diese Tasteraktion ist nicht erlaubt.")
    attributes = raw.get("event_attributes")
    if attributes is not None:
        attributes = validate_event_attributes(attributes)
    ignored = None
    if "ignored_event_attributes" in raw:
        ignored = validate_ignored_attributes(raw["ignored_event_attributes"], attributes)
    label = raw.get("control_label")
    if label is not None and (not isinstance(label, str) or not label.strip() or len(label) > 80):
        raise ServiceValidationError("Ungültige Tastenbezeichnung.")
    params = raw.get("params", {})
    selected_action = action in {"toggle_lights", "turn_on_lights", "turn_off_lights"} or (action == "full_brightness" and isinstance(params, dict) and "entity_ids" in params)
    dim_action = action in {"dim_up", "dim_down"}
    if not isinstance(params, dict):
        raise ServiceValidationError("Ungültige Parameter der Tasteraktion.")
    expected = {"scene_id"} if action == "scene" else (
        {"entity_ids"} if selected_action or (dim_action and "entity_ids" in params) else set()
    )
    optional = {"on_behavior"} if action in ON_ACTIONS else set()
    if not expected <= set(params) or set(params) - expected - optional:
        raise ServiceValidationError("Ungültige Parameter der Tasteraktion.")
    params = deepcopy(params)
    if "entity_ids" in params:
        params["entity_ids"] = validate_selected_lights(hass, store, params["entity_ids"])
        # Explicit targets are independent of the button's or an editor's room.
        if area_id is not None and not isinstance(area_id, str):
            raise ServiceValidationError("Ungültiger Raum.")
        area_id = None
    elif not isinstance(area_id, str) or not room_targets(hass, store, area_id):
        raise ServiceValidationError("Bitte einen Raum mit freigegebenen Lampen auswählen.")
    if action in {"full_brightness", "night", "return_auto", "night_auto"}:
        from .target_actions import validate_action
        validate_action(hass, store, {"type": action, **({"entity_ids": params["entity_ids"]} if "entity_ids" in params else {"area_id": area_id})})
    if action == "scene":
        _scene_for_room(store, params["scene_id"], area_id)
    if "on_behavior" in params:
        params["on_behavior"] = validate_on_behavior(hass, store, params["on_behavior"], area_id, params.get("entity_ids"), _validate_refs=not _runtime)
    return {
        "id": binding_id or str(uuid4()),
        "event_entity": button["entity_id"],
        "event_type": event_type,
        "action": action,
        "area_id": area_id,
        "params": deepcopy(params),
        **({"event_attributes": attributes} if attributes is not None else {}),
        **({"ignored_event_attributes": ignored} if ignored is not None else {}),
        **({"control_label": label.strip()} if label is not None else {}),
    }


def validate_on_behavior(hass, store, value, area_id, entity_ids=None, *, _window=False, _validate_refs=True):
    """An optional on-only override never expands the binding's selected targets."""
    if not isinstance(value, dict) or not isinstance(value.get("mode"), str) or value["mode"] not in ({"brightness", "scene"} if _window else {"last", "brightness", "scene", "time"}):
        raise ServiceValidationError("Ungültiges Verhalten beim Einschalten.")
    if value["mode"] == "time":
        from .schedule_config import validate_time_window

        windows = value.get("windows")
        if set(value) != {"mode", "windows"} or not isinstance(windows, list) or not 1 <= len(windows) <= 24:
            raise ServiceValidationError("Bitte 1 bis 24 Zeitfenster anlegen.")
        cleaned = []
        for item in windows:
            if not isinstance(item, dict) or "window" not in item:
                raise ServiceValidationError("Das Einschaltverhalten benötigt ein Zeitfenster.")
            window = validate_time_window(item["window"])
            if window is None:
                raise ServiceValidationError("Bitte mindestens eine Grenze des Zeitfensters wählen.")
            action = validate_on_behavior(hass, store, {key: val for key, val in item.items() if key != "window"},
                                          area_id, entity_ids, _window=True, _validate_refs=_validate_refs)
            cleaned.append({"window": window, **action})
        return {"mode": "time", "windows": cleaned}
    expected = {"mode"} | ({"brightness"} if value["mode"] == "brightness" else {"scene_id"} if value["mode"] == "scene" else set())
    if _window and value["mode"] == "brightness" and "color_temp_kelvin" in value:
        expected.add("color_temp_kelvin")
        kelvin = value["color_temp_kelvin"]
        if type(kelvin) is not int or not 1000 <= kelvin <= 40000:
            raise ServiceValidationError("Der Weißton muss zwischen 1000 und 40000 Kelvin liegen.")
    if set(value) != expected:
        raise ServiceValidationError("Ungültiges Verhalten beim Einschalten.")
    if value["mode"] == "brightness":
        validate_control_options(brightness=value["brightness"])
        if value["brightness"] is None:
            raise ServiceValidationError("Bitte eine feste Helligkeit wählen.")
    elif value["mode"] == "scene":
        if not isinstance(value["scene_id"], str) or not value["scene_id"]:
            raise ServiceValidationError("Bitte eine Einschalt-Szene auswählen.")
        if not _validate_refs:
            return deepcopy(value)
        scene = next((s for s in store.data["scenes"] if s.get("id") == value["scene_id"]), None)
        if scene is None:
            raise ServiceValidationError("Die Einschalt-Szene wurde nicht gefunden.")
        from .seasonal_scenes import resolve_scene

        scene, _ = resolve_scene(hass, store, scene)
        if entity_ids is None:
            _scene_for_room(store, value["scene_id"], area_id)
        else:
            if scene.get("kind") == "palette" and any(entity.startswith("switch.") for entity in entity_ids):
                raise ServiceValidationError("Für ausgewählte Lichtschalter bitte eine Momentaufnahme wählen.")
            members = (scene.get("lights", {}) if scene.get("kind") == "snapshot" else
                       hue_scene_targets(hass, scene["hue_scene"]) if scene.get("kind") == "hue" else
                       room_targets(hass, store, scene["area_id"]))
            if not set(entity_ids) <= set(members):
                raise ServiceValidationError("Die Einschalt-Szene muss alle ausgewählten Lampen enthalten.")
            _targets(hass, store, scene["area_id"], entity_ids)
    return deepcopy(value)


async def async_save_binding(hass, store, raw):
    """The Store validates inside its write lock to reject stale editor updates."""
    if not isinstance(raw, dict):
        raise ServiceValidationError("Ungültige Tasterbelegung.")
    return await store.async_save_binding(raw, is_update=bool(raw.get("id")))


def _check_scene(hass, store, scene_id, area_id):
    """Skip obsolete cycle entries before a recall can pause or stop anything."""
    scene = _scene_for_room(store, scene_id, area_id)
    from .seasonal_scenes import resolve_scene

    scene, _ = resolve_scene(hass, store, scene)
    kind = scene.get("kind")
    if kind not in {"snapshot", "palette", "hue"}:
        raise ServiceValidationError("Ungültiger Szenentyp.")
    dynamic = validate_dynamic(scene.get("dynamic", {}), kind)
    distribution = validate_distribution(scene.get("verteilung", "zufall"))
    if dynamic["welle"] and distribution == "zufall" and not scene.get("wave_order"):
        raise ServiceValidationError("Für eine Welle bitte eine räumliche Verteilung auswählen.")
    if kind == "snapshot":
        values = scene.get("lights")
        if not isinstance(values, dict):
            raise ServiceValidationError("Ungültige Lampen der Szene.")
        _targets(hass, store, area_id, values)
        for entity_id, value in values.items():
            if (
                not isinstance(value, dict)
                or set(value) - {"on", "brightness", "xy", "color_temp_kelvin"}
                or type(value.get("on")) is not bool
                or (entity_id.startswith("switch.") and set(value) != {"on"})
            ):
                raise ServiceValidationError("Ungültige Lampeneinstellung.")
            validate_control_options(**value)
    elif kind == "hue":
        hue_id = scene.get("hue_scene")
        if not isinstance(hue_id, str):
            raise ServiceValidationError("Bitte eine Hue-Szene auswählen.")
        _targets(hass, store, area_id, hue_scene_targets(hass, hue_id))
    else:
        if scene.get("palette_id") not in {p["id"] for p in list_palettes(store)}:
            raise ServiceValidationError("Die Farbpalette wurde nicht gefunden.")
        validate_control_options(brightness=scene.get("brightness"))
        _targets(hass, store, area_id, room_targets(hass, store, area_id))
    from .palette_catalogue import get_palette
    from .scene_settings import validate_lamp_settings, validate_wave_order

    targets = (scene["lights"] if kind == "snapshot" else hue_scene_targets(hass, scene["hue_scene"])
               if kind == "hue" else room_targets(hass, store, area_id))
    palette = get_palette(store, scene["palette_id"]) if kind == "palette" else None
    validate_lamp_settings(hass, scene.get("lamp_settings", {}), targets, palette, capabilities=False)
    validate_wave_order(scene.get("wave_order", []), targets)
    validate_control_options(brightness=scene.get("brightness"))
    return scene


class BindingManager:
    """Own the state listener, click windows, queued actions and cycle cursors."""

    def __init__(self, hass: HomeAssistant, store: LichtzentraleStore):
        self.hass, self.store = hass, store
        self.closed = False
        self._unsubscribe = None
        self._pending = {}
        self._tasks = set()
        self._task_bindings = {}
        self._locks = {}
        self._cycles = {}
        self._learning = {}

    @callback
    def start(self):
        """Register once; adding or editing a binding needs no listener rebuild."""
        if self.closed:
            raise ServiceValidationError("Lichtzentrale ist nicht geladen.")
        if self._unsubscribe is None:
            self._unsubscribe = self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._changed)

    def _prune_learning(self):
        self._learning = {token: session for token, session in self._learning.items() if session["expires"] > monotonic()}

    @callback
    def learn_start(self, entity_id):
        self._prune_learning()
        if self.closed or not any(b["entity_id"] == entity_id and b["available"] for b in list_buttons(self.hass)):
            raise ServiceValidationError("Dieser Taster ist nicht verfügbar.")
        if len(self._learning) >= 20:
            raise ServiceValidationError("Bitte eine laufende Anlernung beenden.")
        token = str(uuid4())
        self._learning[token] = {"entity_id": entity_id, "expires": monotonic() + 120, "observation": None}
        return {"token": token}

    @callback
    def learn_status(self, token):
        self._prune_learning()
        session = self._learning.get(token)
        if self.closed or session is None:
            raise ServiceValidationError("Anlernen abgelaufen. Bitte erneut starten.")
        if not any(b["entity_id"] == session["entity_id"] and b["available"] for b in list_buttons(self.hass)):
            self._learning.pop(token, None)
            raise ServiceValidationError("Dieser Taster ist nicht mehr verfügbar.")
        return {"status": "captured" if session["observation"] else "waiting", "observation": deepcopy(session["observation"])}

    @callback
    def learn_cancel(self, token):
        self._learning.pop(token, None)
        return {"cancelled": True}

    def _lock(self, area_id):
        return self._locks.setdefault(area_id, asyncio.Lock())

    @callback
    def _cancel_pending(self, entity_id):
        if pending := self._pending.pop(entity_id, None):
            pending["cancel"]()
        return pending

    @callback
    def refresh_bindings(self):
        """Cancel obsolete work immediately after a successful Store commit."""
        current = self.store.data["bindings"]
        for task, binding in list(self._task_bindings.items()):
            if binding not in current:
                task.cancel()
        for entity_id, pending in list(self._pending.items()):
            if pending["bindings"] != self._matching_bindings(entity_id, "short_release", pending["attributes"]) or pending[
                "doubles"
            ] != self._matching_bindings(entity_id, DOUBLE_RELEASE, pending["attributes"]):
                self._cancel_pending(entity_id)

    @callback
    def _task_done(self, task):
        self._tasks.discard(task)
        self._task_bindings.pop(task, None)

    def _bindings(self, entity_id, event_type):
        return [
            b
            for b in self.store.data["bindings"]
            if b.get("event_entity") == entity_id and b.get("event_type") == event_type
        ]

    def _matching_bindings(self, entity_id, event_type, attributes):
        matches = [
            binding for binding in self._bindings(entity_id, event_type)
            if _matches_payload(binding, attributes)
        ]
        # A precise learned gesture overrides a wildcard or legacy fallback.
        # Store validation prevents ties; old/corrupt duplicates still run only once.
        return [max(matches, key=_specificity)] if matches else []

    @callback
    def _queue(self, bindings, context):
        for binding in bindings:
            task = self.hass.async_create_task(
                self._execute(binding, context), "Lichtzentrale Tasteraktion"
            )
            self._tasks.add(task)
            self._task_bindings[task] = binding
            task.add_done_callback(self._task_done)

    @callback
    def _changed(self, event):
        entity_id = event.data.get("entity_id", "")
        if self.closed or not entity_id.startswith("event."):
            return
        old, new = event.data.get("old_state"), event.data.get("new_state")
        if (
            self.hass.state is not CoreState.running
            or new is None
            or old is None
            or new.state in {STATE_UNAVAILABLE, STATE_UNKNOWN}
            or old.state == STATE_UNAVAILABLE
            or new.attributes.get("restored")
            or old.attributes.get("restored")
        ):
            self._cancel_pending(entity_id)
            return
        if old.state == new.state:
            return  # Attribute-only updates (including event_type) are not a press.
        stamp = parse_datetime(new.state)
        previous = parse_datetime(old.state)
        if (
            stamp is None
            or stamp.tzinfo is None
            or (previous is not None and (previous.tzinfo is None or stamp <= previous))
        ):
            return
        button = next((b for b in list_buttons(self.hass) if b["entity_id"] == entity_id), None)
        event_type = new.attributes.get("event_type")
        if (
            not button
            or not button["available"]
            or not isinstance(event_type, str)
            or event_type not in button["event_types"]
            or event_type == DOUBLE_RELEASE
        ):
            return
        try:
            attributes = event_attributes(new)
        except ServiceValidationError:
            return
        self._prune_learning()
        learning = [session for session in self._learning.values() if session["entity_id"] == entity_id and session["observation"] is None]
        if learning:
            observed = {"event_entity": entity_id, "event_type": event_type, "event_attributes": attributes}
            for session in learning:
                session["observation"] = deepcopy(observed)
            self._cancel_pending(entity_id)
            return  # Learning does not run a previously saved action for this gesture.
        bindings = self._matching_bindings(entity_id, event_type, attributes)
        doubles = self._matching_bindings(entity_id, DOUBLE_RELEASE, attributes)
        if event_type != "short_release" or not doubles:
            # A removed double binding must not leave a stale delayed single behind.
            if event_type == "short_release":
                if pending := self._cancel_pending(entity_id):
                    self._queue(pending["bindings"], pending["context"])
            self._queue(bindings, event.context)
            return
        now = monotonic()
        pending = self._pending.get(entity_id)
        ignored = doubles[0].get("ignored_event_attributes", [])
        if (pending and now <= pending["deadline"] and pending["doubles"] == doubles
                and _same_attributes(
                    {key: value for key, value in pending["attributes"].items() if key not in ignored},
                    {key: value for key, value in attributes.items() if key not in ignored},
                )):
            self._cancel_pending(entity_id)
            self._queue(doubles, event.context)
            return
        if pending := self._cancel_pending(entity_id):
            self._queue(pending["bindings"], pending["context"])
        milliseconds = self.store.data["settings"].get("double_click_ms", 500)
        if type(milliseconds) is not int or not 200 <= milliseconds <= 1000:
            milliseconds = 500
        pending = {
            "bindings": bindings,
            "attributes": attributes,
            "doubles": doubles,
            "context": event.context,
            "deadline": now + milliseconds / 1000,
        }

        @callback
        def release_single():
            if self._pending.get(entity_id) is pending:
                self._pending.pop(entity_id)
                if not self.closed:
                    self._queue(pending["bindings"], pending["context"])

        pending["cancel"] = self.hass.loop.call_later(milliseconds / 1000, release_single).cancel
        self._pending[entity_id] = pending

    async def _execute(self, binding, context):
        """Recheck queued binding identity, grants and runtime state after locking."""
        try:
            async with self._lock(binding["area_id"]):
                if self.closed or binding not in self.store.data["bindings"]:
                    return
                state = self.hass.states.get(binding["event_entity"])
                if state is None or state.state in {STATE_UNAVAILABLE, STATE_UNKNOWN}:
                    return
                checked = validate_binding(self.hass, self.store, binding, _runtime=True)
                result = await self._action(checked, context)
                if isinstance(result, dict):
                    failed, skipped = len(result.get("failed", [])), len(result.get("skipped", []))
                    if failed:
                        _LOGGER.warning(
                            "Tasteraktion teilweise fehlgeschlagen: %s Fehler, %s übersprungen",
                            failed,
                            skipped,
                        )
                    elif skipped:
                        # Off lamps and binary switches are expected skips while dimming.
                        _LOGGER.debug("Tasteraktion: %s Ziele übersprungen", skipped)
                return result
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.warning("Eine Tasteraktion konnte nicht ausgeführt werden", exc_info=True)

    async def _action(self, binding, context):
        area_id, action = binding["area_id"], binding["action"]
        if action in {"full_brightness", "night", "return_auto", "night_auto"}:
            from .target_actions import async_execute_action
            return await async_execute_action(self.hass, self.store, {"type": action, **({"entity_ids": binding["params"]["entity_ids"]} if "entity_ids" in binding["params"] else {"area_id": area_id})}, context=context)
        if action in ON_ACTIONS and binding["params"].get("on_behavior", {}).get("mode", "last") != "last":
            return await self._with_on_behavior(binding, context)
        if action in {"toggle_room", "turn_on_room", "turn_off_room"}:
            return await async_toggle_room(
                self.hass,
                self.store,
                area_id,
                on={"toggle_room": None, "turn_on_room": True, "turn_off_room": False}[action],
                context=context,
            )
        if action in {"toggle_lights", "turn_on_lights", "turn_off_lights"}:
            return await async_control_lights(
                self.hass, self.store, binding["params"]["entity_ids"],
                on={"toggle_lights": None, "turn_on_lights": True, "turn_off_lights": False}[action],
                context=context,
            )
        if action == "next_scene":
            return await self._next_scene(area_id, context)
        if action == "scene":
            scene_id = binding["params"]["scene_id"]
            _check_scene(self.hass, self.store, scene_id, area_id)
            return await async_apply_scene(self.hass, self.store, scene_id, context=context)
        if action in {"dim_up", "dim_down"}:
            if "entity_ids" in binding["params"]:
                return await async_dim_lights(
                    self.hass, self.store, binding["params"]["entity_ids"],
                    1 if action == "dim_up" else -1, context=context,
                )
            return await self._dim(area_id, 1 if action == "dim_up" else -1, context)
        if action in {"adaptive_on", "adaptive_off"}:
            return await async_set_adaptive(
                self.hass, self.store, area_id, enabled=action == "adaptive_on", context=context
            )
        if action == "stop_dynamic":
            return await async_stop_room(self.hass, self.store, area_id, context=context)
        raise ServiceValidationError("Diese Tasteraktion ist nicht erlaubt.")

    async def _with_on_behavior(self, binding, context):
        """Resolve toggle once, then fail closed if a queued on/off decision became stale."""
        params, area_id, action = binding["params"], binding["area_id"], binding["action"]
        selected = "entity_ids" in params
        targets = (validate_selected_lights(self.hass, self.store, params["entity_ids"]) if selected
                   else room_targets(self.hass, self.store, area_id))
        behavior = validate_on_behavior(self.hass, self.store, params["on_behavior"], area_id, targets if selected else None, _validate_refs=False)
        initial = {entity: self.hass.states.get(entity) for entity in targets}
        states = list(initial.values())
        toggle_states = states if selected else [state for state in states if state.domain == "light"] or states
        on = action.startswith("turn_on") or not any(state.state == "on" for state in toggle_states)
        pending = True

        def guard():
            nonlocal pending
            current = (validate_selected_lights(self.hass, self.store, targets) if selected
                       else room_targets(self.hass, self.store, area_id))
            if current != targets:
                raise ServiceValidationError("Die Zielauswahl hat sich geändert. Bitte erneut drücken.")
            if pending:
                pending = False
                if any(self.hass.states.get(entity) is not state for entity, state in initial.items()):
                    raise ServiceValidationError("Der Lampenzustand hat sich geändert. Bitte erneut drücken.")
            return True

        if not on:
            if selected:
                return await async_control_lights(self.hass, self.store, targets, on=False, context=context, guard=guard)
            return await async_toggle_room(self.hass, self.store, area_id, on=False, context=context, guard=guard)
        if behavior["mode"] == "time":
            from .schedule_windows import window_is_open

            behavior = next(({key: value for key, value in item.items() if key != "window"}
                             for item in behavior["windows"] if window_is_open(self.hass, item["window"])), {"mode": "last"})
            if behavior["mode"] == "last":
                return await self._action({**binding, "params": {key: value for key, value in params.items()
                                                                if key != "on_behavior"}}, context)
        behavior = validate_on_behavior(self.hass, self.store, behavior, area_id, targets if selected else None,
                                        _window=params["on_behavior"]["mode"] == "time")
        if behavior["mode"] == "brightness":
            # Explicit on overrides remembered brightness without dimming binary lights.
            # Selection and capability checks remain at dispatch time.
            return await async_control_lights(self.hass, self.store, targets, on=True,
                                             brightness=behavior["brightness"], color_temp_kelvin=behavior.get("color_temp_kelvin"),
                                             context=context, guard=guard)
        scene_id = behavior["scene_id"]
        if selected:
            return await async_apply_scene_subset(self.hass, self.store, scene_id, targets, context=context, guard=guard)
        _check_scene(self.hass, self.store, scene_id, area_id)
        return await async_apply_scene(self.hass, self.store, scene_id, context=context, guard=guard)

    async def _dim(self, area_id, direction, context):
        # Serialize with manual scenes and room controls as well as other button actions.
        locks = self.hass.data.setdefault(DOMAIN, {}).setdefault("scene_locks", {})
        async with locks.setdefault(area_id, asyncio.Lock()):
            calls, skipped, payloads = [], [], {}
            for entity_id in room_targets(self.hass, self.store, area_id):
                params = dim_payload(self.hass.states.get(entity_id), direction, dim_min_pct(self.store))
                if params is None:
                    skipped.append(entity_id)
                    continue
                payloads[entity_id] = params
                calls.append(("light", "turn_on", params))

            def still_allowed(entity_id):
                state = self.hass.states.get(entity_id)
                if (entity_id not in self.store.data["settings"]["light_entity_ids"]
                        or entity_id not in room_targets(self.hass, self.store, area_id)
                        or state is None or not is_individual_light(self.hass, state)):
                    return False
                params = dim_payload(state, direction, dim_min_pct(self.store))
                if params is None:
                    return False
                # async_dispatch calls this without yielding before async_call.
                # Refresh the same dict so a newly low lamp gets an absolute floor.
                payloads[entity_id].clear()
                payloads[entity_id].update(params)
                return True

            return await async_dispatch(
                self.hass, calls, skipped, context=context, guard=still_allowed
            )

    async def async_next_scene(self, area_id, context: Context | None = None):
        """Cycle through persisted room order with a ten-minute runtime reset."""
        if not isinstance(area_id, str):
            raise ServiceValidationError("Ungültiger Raum.")
        if self.closed:
            raise ServiceValidationError("Lichtzentrale ist nicht geladen.")

        async def cycle():
            async with self._lock(area_id):
                if self.closed:
                    raise ServiceValidationError("Lichtzentrale ist nicht geladen.")
                return await self._next_scene(area_id, context)

        task = self.hass.async_create_task(cycle(), "Lichtzentrale Szenenzyklus")
        self._tasks.add(task)
        task.add_done_callback(self._task_done)
        return await task

    async def _next_scene(self, area_id, context):
        room_targets(self.hass, self.store, area_id)
        cycle = self.store.data["rooms"].get(area_id, {}).get("cycle", [])
        if not isinstance(cycle, list) or any(not isinstance(s, str) for s in cycle):
            raise ServiceValidationError("Ungültiger Szenenzyklus.")
        cycle = list(dict.fromkeys(cycle))
        cursor = self._cycles.get(area_id)
        start = 0
        if cursor and monotonic() - cursor[1] < CYCLE_RESET_SECONDS and cursor[0] in cycle:
            start = (cycle.index(cursor[0]) + 1) % len(cycle)
        for scene_id in cycle[start:] + cycle[:start]:
            try:
                scene = _check_scene(self.hass, self.store, scene_id, area_id)
            except ServiceValidationError:
                continue
            result = await async_apply_scene(self.hass, self.store, scene_id, context=context)
            incomplete = [
                e
                for e in result.get("skipped", [])
                if scene["kind"] != "palette" or not e.startswith("switch.")
            ]
            if result.get("applied") and not result.get("failed") and not incomplete:
                self._cycles[area_id] = (scene_id, monotonic())
            return {**result, "scene_id": scene_id}
        raise ServiceValidationError("Für diesen Raum ist keine gültige Zyklus-Szene vorhanden.")

    async def shutdown(self):
        """Unsubscribe first, then cancel timers and queued/in-flight button work."""
        self.closed = True
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        for entity_id in list(self._pending):
            self._cancel_pending(entity_id)
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._task_bindings.clear()
        self._learning.clear()
        self._cycles.clear()
        self._locks.clear()
