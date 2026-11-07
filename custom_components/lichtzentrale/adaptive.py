# Geändert für Lichtzentrale
"""Optional, fail-closed bridge to Adaptive Lighting's public services.

The runtime primary switch and its resolved lights are inspected because HA's
state attributes omit the light configuration by default. No dependency/import
of the optional custom integration is required. See basnijholt/adaptive-lighting
switch.py: _switches_from_service_call, handle_apply_service.
"""

from asyncio import Lock
from collections.abc import Mapping

from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .lights import entity_area_id, validate_lights
from .rooms import check_execution_guard, validate_transition

ADAPTIVE_DOMAIN = "adaptive_lighting"
UNSET = object()


def _primary(hass, entity_id):
    entry = er.async_get(hass).async_get(entity_id) if isinstance(entity_id, str) else None
    if (
        not entry
        or entry.domain != "switch"
        or entry.platform != ADAPTIVE_DOMAIN
        or entry.disabled_by
    ):
        raise ServiceValidationError("Bitte einen Hauptschalter von Adaptive Lighting auswählen.")
    runtime = hass.data.get(ADAPTIVE_DOMAIN, {}).get(entry.config_entry_id, {})
    switch = runtime.get("switch") if isinstance(runtime, Mapping) else None
    if switch is None or getattr(switch, "entity_id", None) != entity_id:
        raise ServiceValidationError("Der Hauptschalter von Adaptive Lighting ist nicht geladen.")
    return switch


def _validated(hass, store, area_id, entity_id):
    switch = _primary(hass, entity_id)
    state = hass.states.get(entity_id)
    if state is None or state.state not in {"on", "off"}:
        raise ServiceValidationError("Adaptive Lighting ist für diesen Raum nicht erreichbar.")
    lights = getattr(switch, "lights", None)
    if (
        not isinstance(lights, (list, tuple, set))
        or not lights
        or any(not isinstance(e, str) for e in lights)
    ):
        raise ServiceValidationError(
            "Die Lampen von Adaptive Lighting lassen sich nicht sicher prüfen."
        )
    lights = validate_lights(hass, list(lights))
    allowed = store.data["settings"]["light_entity_ids"]
    if any(
        not e.startswith("light.") or e not in allowed or entity_area_id(hass, e) != area_id
        for e in lights
    ):
        raise ServiceValidationError(
            "Adaptive Lighting darf nur freigegebene Einzellampen dieses Raums steuern."
        )
    if not all(
        hass.services.has_service(ADAPTIVE_DOMAIN, service)
        for service in ("apply", "set_manual_control")
    ):
        raise ServiceValidationError("Die Dienste von Adaptive Lighting sind nicht verfügbar.")
    return lights


def status(hass, store):
    """Expose genuine primary switches, never infer switch identity from its name."""
    switches = []
    for state in hass.states.async_all("switch"):
        try:
            _primary(hass, state.entity_id)
        except ServiceValidationError:
            continue
        switches.append(
            {
                "entity_id": state.entity_id,
                "name": state.name,
                "available": state.state in {"on", "off"},
            }
        )
    rooms = []
    for area in ar.async_get(hass).async_list_areas():
        settings = store.data["rooms"].get(area.id, {})
        entity_id = settings.get("adaptive_switch")
        available, reason = False, None
        if entity_id:
            try:
                _validated(hass, store, area.id, entity_id)
                available = True
            except ServiceValidationError as error:
                reason = str(error)
        state = hass.states.get(entity_id) if entity_id else None
        rooms.append(
            {
                "area_id": area.id,
                "switch_entity_id": entity_id,
                "enabled": bool(available and state and state.state == "on"),
                "available": available,
                "reason": reason,
                "default_on": settings.get("default_on", "last"),
            }
        )
    return {
        "available": bool(switches),
        "rooms": rooms,
        "switches": sorted(switches, key=lambda item: item["name"].casefold()),
    }


async def _set_enabled(hass, store, area_id, entity_id, enabled, context, *, turn_on_lights=False, transition=None, dispatch_guard=None):
    validate_transition(transition)
    lights = _validated(hass, store, area_id, entity_id)
    check_execution_guard(dispatch_guard)
    await hass.services.async_call(
        "switch",
        "turn_on" if enabled else "turn_off",
        {"entity_id": entity_id},
        blocking=True,
        context=context,
    )
    if enabled:
        # Recheck after each await: the allowlist or area assignment may change.
        lights = _validated(hass, store, area_id, entity_id)
        check_execution_guard(dispatch_guard)
        await hass.services.async_call(
            ADAPTIVE_DOMAIN,
            "set_manual_control",
            {"entity_id": entity_id, "lights": lights, "manual_control": False},
            blocking=True,
            context=context,
        )
        lights = _validated(hass, store, area_id, entity_id)
        # Keep the explicit fade on the final apply, after enabling/resetting AL.
        # AL may start its configured initial fade on already-on lights during
        # those earlier calls; its own transition timer protects this final fade
        # from interval adaptation. Off lights are first lit by this apply.
        check_execution_guard(dispatch_guard)
        await hass.services.async_call(
            ADAPTIVE_DOMAIN,
            "apply",
            {
                "entity_id": entity_id, "lights": lights, "turn_on_lights": turn_on_lights,
                **({"transition": transition} if transition is not None else {}),
            },
            blocking=True,
            context=context,
        )

    return lights


async def async_turn_on_adaptive(hass, store, area_id, context=None, *, transition=None, guard=None, dispatch_guard=None):
    """Room-on targets only the strictly validated AL assignment; caller holds lock."""
    check_execution_guard(guard)
    entity_id = store.data["rooms"].get(area_id, {}).get("adaptive_switch")
    if not entity_id:
        raise ServiceValidationError("Bitte zuerst Adaptive Lighting für diesen Raum zuordnen.")
    return await _set_enabled(hass, store, area_id, entity_id, True, context, turn_on_lights=True, transition=transition, dispatch_guard=dispatch_guard)


async def async_set_adaptive(
    hass, store, area_id, enabled=None, adaptive_switch=UNSET, default_on=None, context=None,
    *, transition=None, guard=None, dispatch_guard=None
):
    """Serialize settings and adaptive operations with scenes and room toggles."""
    if not isinstance(area_id, str):
        raise ServiceValidationError("Ungültiger Raum.")
    locks = hass.data.setdefault(DOMAIN, {}).setdefault("scene_locks", {})
    async with locks.setdefault(area_id, Lock()):
        return await _async_set_adaptive(
            hass, store, area_id, enabled, adaptive_switch, default_on, context, transition=transition, guard=guard, dispatch_guard=dispatch_guard
        )


async def _async_set_adaptive(
    hass, store, area_id, enabled=None, adaptive_switch=UNSET, default_on=None, context=None,
    *, transition=None, guard=None, dispatch_guard=None
):
    """Validate optional mapping/settings before persistence or device actions."""
    check_execution_guard(guard)
    validate_transition(transition)
    if not isinstance(area_id, str) or ar.async_get(hass).async_get_area(area_id) is None:
        raise ServiceValidationError("Der Raum wurde nicht gefunden.")
    if enabled is not None and type(enabled) is not bool:
        raise ServiceValidationError("Ein/Aus muss ein Wahrheitswert sein.")
    if default_on is not None and default_on not in ("adaptive", "last"):
        raise ServiceValidationError(
            "Als Einschaltverhalten bitte Natürliches Licht oder Letzter Zustand wählen."
        )
    settings = store.data["rooms"].get(area_id, {})
    entity_id = settings.get("adaptive_switch") if adaptive_switch is UNSET else adaptive_switch
    changes = {}
    if adaptive_switch is not UNSET:
        if adaptive_switch is not None and not isinstance(adaptive_switch, str):
            raise ServiceValidationError("Ungültiger Adaptive-Lighting-Schalter.")
        changes["adaptive_switch"] = adaptive_switch
        if (
            adaptive_switch is None
            and settings.get("default_on") == "adaptive"
            and default_on is None
        ):
            changes["default_on"] = "last"
    if default_on is not None:
        changes["default_on"] = default_on
    if entity_id:
        _validated(hass, store, area_id, entity_id)
        if any(
            other != area_id and room.get("adaptive_switch") == entity_id
            for other, room in store.data["rooms"].items()
        ):
            raise ServiceValidationError(
                "Dieser Adaptive-Lighting-Schalter ist bereits einem anderen Raum zugeordnet."
            )
    elif enabled is not None or default_on == "adaptive":
        raise ServiceValidationError("Bitte zuerst Adaptive Lighting für diesen Raum zuordnen.")
    if enabled is True:
        from .dynamic_scenes import stop_dynamic

        await stop_dynamic(hass, area_id)
    if enabled is not None:
        await _set_enabled(hass, store, area_id, entity_id, enabled, context, transition=transition, dispatch_guard=dispatch_guard)
    if changes:
        await store.async_update_room(area_id, changes)
    return status(hass, store)


async def async_pause_adaptive(hass, store, area_id, context=None, *, dispatch_guard=None):
    """Pause a configured room before a color scene; absent integration is optional."""
    entity_id = store.data["rooms"].get(area_id, {}).get("adaptive_switch")
    if entity_id and hass.data.get(ADAPTIVE_DOMAIN):
        await _set_enabled(hass, store, area_id, entity_id, False, context, dispatch_guard=dispatch_guard)


async def async_resume_adaptive(hass, store, area_id, context=None):
    """Restore natural light without turning on off lamps through AL's apply API."""
    entity_id = store.data["rooms"].get(area_id, {}).get("adaptive_switch")
    if entity_id and hass.data.get(ADAPTIVE_DOMAIN):
        await _set_enabled(hass, store, area_id, entity_id, True, context)
