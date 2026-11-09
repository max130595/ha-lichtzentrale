# Geändert für Lichtzentrale
"""Explicit cross-room button targets with persisted, pre-off light values."""

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager

from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN
from .lights import entity_area_id, is_individual_light, validate_lights
from .rooms import (
    async_dispatch,
    check_execution_guard,
    light_service_data,
    validate_control_options,
    validate_transition,
)


def validate_selected_lights(hass, store, entity_ids):
    """Validate the whole explicit selection before changing anything."""
    if (
        not isinstance(entity_ids, list)
        or not 1 <= len(entity_ids) <= 500
        or any(not isinstance(entity_id, str) or not entity_id for entity_id in entity_ids)
    ):
        raise ServiceValidationError("Bitte mindestens eine freigegebene Lampe auswählen.")
    targets = list(dict.fromkeys(entity_ids))
    allowed = store.data["settings"]["light_entity_ids"]
    if any(entity_id not in allowed for entity_id in targets):
        raise ServiceValidationError("Alle ausgewählten Lampen müssen freigegeben sein.")
    return validate_lights(hass, targets)


@asynccontextmanager
async def _locked_targets(hass, store, entity_ids):
    """Serialize overlapping selections and room recalls without lock inversion."""
    targets = validate_selected_lights(hass, store, entity_ids)
    runtime = hass.data.setdefault(DOMAIN, {})
    entity_locks = runtime.setdefault("selected_light_locks", {})
    room_locks = runtime.setdefault("scene_locks", {})
    async with AsyncExitStack() as stack:
        for entity_id in sorted(targets):
            await stack.enter_async_context(entity_locks.setdefault(entity_id, asyncio.Lock()))
        areas = {entity_id: entity_area_id(hass, entity_id) for entity_id in targets}
        for area in sorted({area for area in areas.values() if area is not None}):
            await stack.enter_async_context(room_locks.setdefault(area, asyncio.Lock()))
        validate_selected_lights(hass, store, targets)
        if any(entity_area_id(hass, entity_id) != areas[entity_id] for entity_id in targets):
            raise ServiceValidationError("Die Raumzuordnung hat sich geändert. Bitte erneut versuchen.")
        yield targets, areas


def _still_allowed(hass, store, entity_id, areas):
    state = hass.states.get(entity_id)
    return bool(
        entity_id in store.data["settings"]["light_entity_ids"]
        and entity_area_id(hass, entity_id) == areas[entity_id]
        and state is not None
        and state.state in {"on", "off"}
        and is_individual_light(hass, state)
    )


async def _stop_dynamics(hass, store, targets, areas):
    from .dynamic_scenes import async_exclude_targets

    # A manual selection owns only its lamps. Fence in-flight commands before
    # reading a snapshot, without cancelling the other lamps' running scene.
    await async_exclude_targets(hass, targets)
    validate_selected_lights(hass, store, targets)
    if any(entity_area_id(hass, entity_id) != areas[entity_id] for entity_id in targets):
        raise ServiceValidationError("Die Raumzuordnung hat sich geändert. Bitte erneut versuchen.")


async def async_control_lights(
    hass, store, entity_ids, on=None, context=None, *, brightness=None, color_temp_kelvin=None, transition=None, guard=None, dispatch_guard=None
):
    """Any selected on means all off; otherwise restore all selected lights."""
    validate_control_options(on=on, brightness=brightness, color_temp_kelvin=color_temp_kelvin)
    validate_transition(transition)
    async with _locked_targets(hass, store, entity_ids) as (targets, areas):
        check_execution_guard(guard)
        await _stop_dynamics(hass, store, targets, areas)
        if on is None:
            on = not any(hass.states.get(entity_id).state == "on" for entity_id in targets)
        captured = None
        if not on:
            # Persist before dispatch. Storage failure means no lamp is switched off.
            # This captures again *inside* the Store lock, never after turn_off.
            captured = await store.async_remember_light_states(targets)
        settings = store.data
        remembered = settings["settings"].get("last_light_states", {})
        calls, skipped, prepared = [], [], {}
        for entity_id in targets:
            state = hass.states.get(entity_id)
            if not _still_allowed(hass, store, entity_id, areas) or (
                captured is not None and state is not captured.get(entity_id)
            ):
                skipped.append(entity_id)
                continue
            options = {}
            if on and state.domain == "light" and state.state == "off":
                # Existing room snapshots also provide a last state for lamps
                # previously turned off through the room controls.
                value = remembered.get(entity_id)
                if value is None:
                    value = settings["rooms"].get(areas[entity_id], {}).get(
                        "pre_off_lights", {}
                    ).get(entity_id, {})
                if not isinstance(value, dict):
                    skipped.append(entity_id)
                    continue
                options = {key: value[key] for key in (
                    "brightness", "xy", "color_temp_kelvin"
                ) if key in value}
            if on and state.domain == "light" and brightness is not None:
                options["brightness"] = brightness
            if on and state.domain == "light" and color_temp_kelvin is not None:
                options.pop("xy", None)
                options["color_temp_kelvin"] = color_temp_kelvin
            try:
                validate_control_options(on=on, **options)
            except ServiceValidationError:
                skipped.append(entity_id)
                continue
            calls.append((state.domain, *light_service_data(state, on=on, transition=transition, **options)))
            prepared[entity_id] = state

        def still_allowed(entity_id):
            # Recheck launch constraints after awaits, not mutable light-state conditions.
            check_execution_guard(dispatch_guard)
            return (
                _still_allowed(hass, store, entity_id, areas)
                and hass.states.get(entity_id) is prepared[entity_id]
            )

        return await async_dispatch(hass, calls, skipped, context=context, guard=still_allowed)


async def async_dim_lights(hass, store, entity_ids, direction, context=None):
    """Apply relative steps only to selected, currently-on dimmable lamps."""
    async with _locked_targets(hass, store, entity_ids) as (targets, areas):
        await _stop_dynamics(hass, store, targets, areas)

        def guard(entity_id):
            state = hass.states.get(entity_id)
            return bool(
                _still_allowed(hass, store, entity_id, areas)
                and state.domain == "light"
                and state.state == "on"
                and type(state.attributes.get("brightness")) is int
                and 1 <= state.attributes["brightness"] <= 255
                and light_service_data(state, brightness=1) is not None
            )

        calls, skipped = [], []
        for entity_id in targets:
            if not guard(entity_id):
                skipped.append(entity_id)
                continue
            calls.append(("light", "turn_on", {
                "entity_id": entity_id, "brightness_step_pct": direction * 10,
            }))
        return await async_dispatch(hass, calls, skipped, context=context, guard=guard)
