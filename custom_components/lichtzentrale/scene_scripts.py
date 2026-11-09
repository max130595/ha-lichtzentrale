# Geändert für Lichtzentrale
"""Optional existing Home Assistant scripts, isolated from scene light success."""

import logging

from homeassistant.core import Context, HomeAssistant, callback, valid_entity_id
from homeassistant.exceptions import ServiceValidationError

_LOGGER = logging.getLogger(__name__)


@callback
def validate_start_script(hass: HomeAssistant, value) -> str | None:
    """Accept only an existing script entity; no implicit creation or domain fallback."""
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not valid_entity_id(value)
        or not value.startswith("script.")
        or hass.states.get(value) is None
    ):
        raise ServiceValidationError("Bitte ein vorhandenes Home-Assistant-Skript auswählen.")
    return value


@callback
def list_scripts(hass: HomeAssistant) -> list[dict]:
    """Expose runtime names and availability, never script contents or credentials."""
    return sorted(
        [
            {
                "entity_id": state.entity_id,
                "name": state.name,
                "available": state.state not in {"unknown", "unavailable"},
            }
            for state in hass.states.async_all("script")
        ],
        key=lambda item: (item["name"].casefold(), item["entity_id"]),
    )


async def async_run_start_script(
    hass: HomeAssistant, entity_id: str | None, context: Context | None = None
) -> bool:
    """Dispatch once after the lights, retaining scene success on script failures.

    The scene executor owns start-versus-preview/resume and seasonal resolution.
    script.turn_on starts the user's script without awaiting its full sequence.
    Runtime sequence errors are therefore also reported by Home Assistant itself.
    Cancellation is deliberately not swallowed.
    """
    if entity_id is None:
        return False
    try:
        validate_start_script(hass, entity_id)
        if hass.states.get(entity_id).state in {"unknown", "unavailable"}:
            raise ServiceValidationError("Das Szenen-Skript ist nicht verfügbar.")
        # Script-controlled lamps are later manual work, not children owned
        # by this scene or its dynamic loop. Keep the actor, isolate ownership.
        await hass.services.async_call(
            "script", "turn_on", {"entity_id": entity_id}, blocking=True,
            context=Context(
                user_id=context.user_id if context else None,
            )
        )
    except Exception:
        _LOGGER.warning(
            "Das Szenen-Skript %s konnte nicht gestartet werden; die Lichtszene läuft weiter.",
            entity_id,
            exc_info=True,
        )
        return False
    return True
