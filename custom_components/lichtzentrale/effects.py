# Geändert für Lichtzentrale
"""Separate, guarded Hue effect commands; no device-specific entity identifiers."""

import asyncio

from homeassistant.const import EVENT_CALL_SERVICE, EVENT_STATE_CHANGED
from homeassistant.core import Context, callback
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN

EFFECT_DELAY = 2.0
STOP_EFFECTS = {"none", "stop_hue_effect"}


def effect_list(state):
    if not state or state.domain != "light" or not (set(state.attributes.get("supported_color_modes") or []) - {"onoff", "unknown"}):
        return []
    raw = state.attributes.get("effect_list", [])
    return [v for v in raw if isinstance(v, str) and v] if isinstance(raw, (list, tuple)) else []


def validate_effect(state, effect):
    if effect is None:
        return None
    if not isinstance(effect, str) or effect not in effect_list(state):
        raise ServiceValidationError("Der Effekt wird von dieser Lampe nicht angeboten.")
    return effect


def invalidate(hass, targets):
    versions = hass.data.setdefault(DOMAIN, {}).setdefault("effect_versions", {})
    for entity in targets:
        versions[entity] = versions.get(entity, 0) + 1


async def async_call(hass, domain, service, params, context=None, *, guard=None, command_call=None):
    """Execute color first and effect later, abandoning ownership on newer work."""
    send_guard = None

    async def send(domain, service, payload):
        if command_call is not None:
            return await command_call(domain, service, payload, context, send_guard)
        return await hass.services.async_call(domain, service, payload, blocking=True, context=context)

    params = dict(params)
    effect = params.pop("_effect", None)
    entity = params["entity_id"]
    state = hass.states.get(entity)
    known = effect_list(state)
    data = hass.data.setdefault(DOMAIN, {})
    active = data.setdefault("active_effects", {})
    old = active.get(entity) or (state.attributes.get("effect") if state else None)
    stop = domain == "light" and known and old and old not in STOP_EFFECTS
    if stop and service == "turn_off" and state.state == "off":
        # Switched off elsewhere: a stop is light.turn_on and would flash the lamp.
        active.pop(entity, None)
        stop = False
    invalidate(hass, [entity])
    if not effect and not stop:
        return await send(domain, service, params)
    from .lights import entity_area_id

    original_area = entity_area_id(hass, entity)
    if effect:
        validate_effect(state, effect)
    context = context or Context()
    versions = data.setdefault("effect_versions", {})
    token = versions[entity]
    lost = False

    def own(ctx):
        return ctx.id == context.id or ctx.parent_id == context.id

    @callback
    def called(event):
        nonlocal lost
        if event.data.get("domain") not in {"light", "switch", "homeassistant"} or own(event.context):
            return
        service_data = event.data.get("service_data", {})
        raw = service_data.get("entity_id", [])
        targets = [raw] if isinstance(raw, str) else raw or []
        broad = any(service_data.get(key) for key in ("area_id", "device_id", "floor_id", "label_id"))
        groups = any(str(target).startswith("group.") or (
            (target_state := hass.states.get(target)) and "entity_id" in target_state.attributes
        ) for target in targets)
        if entity in targets or "all" in targets or broad or groups:
            lost = True

    @callback
    def changed(event):
        nonlocal lost
        if event.data.get("entity_id") != entity:
            return
        old_state, new = event.data.get("old_state"), event.data.get("new_state")
        if new and own(new.context):
            return
        if new is None or (old_state and new and (old_state.state != new.state or
                (new.context.user_id and old_state.attributes != new.attributes))):
            lost = True

    def current():
        now = hass.states.get(entity)
        store = data.get("store")
        granted = store is None or entity in store.data["settings"]["light_entity_ids"]
        return (granted and entity_area_id(hass, entity) == original_area and not lost and versions.get(entity) == token and now is not None
                and now.state in {"on", "off"} and (guard is None or guard(entity)))

    send_guard = current
    unsub = [hass.bus.async_listen(EVENT_CALL_SERVICE, called), hass.bus.async_listen(EVENT_STATE_CHANGED, changed)]
    try:
        if not current():
            raise ServiceValidationError("Der Lampenauftrag ist nicht mehr freigegeben.")
        if stop:
            stop_value = "stop_hue_effect" if "stop_hue_effect" in known else "none"
            await send("light", "turn_on", {"entity_id": entity, "effect": stop_value})
            active.pop(entity, None)
            if not current():
                raise ServiceValidationError("Der Lampenauftrag wurde inzwischen ersetzt.")
        await send(domain, service, params)
        if effect and service == "turn_on":
            await asyncio.sleep(EFFECT_DELAY)
            if not current() or effect not in effect_list(hass.states.get(entity)):
                raise ServiceValidationError("Der verzögerte Effekt wurde verworfen.")
            await send("light", "turn_on", {"entity_id": entity, "effect": effect})
            active[entity] = effect
    finally:
        for remove in unsub:
            remove()
