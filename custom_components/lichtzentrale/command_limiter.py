# Geändert für Lichtzentrale
"""One shared, cancellation-safe dynamic dispatcher; never enqueue future ticks."""

import asyncio

from .const import DOMAIN

COMMAND_SPACING = 0.21  # Fewer than five command starts per sliding second.


class DynamicCommandLimiter:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.entities = {}
        self.last_command = None

    def entity_lock(self, entity_id):
        return self.entities.setdefault(entity_id, asyncio.Lock())

    async def dispatch(self, hass, domain, service, params, context, guard):
        # Only one outstanding command per running scene. The loop awaits the
        # whole tick before sleeping again, so slow devices cannot build a queue.
        async with self.lock:
            loop = asyncio.get_running_loop()
            if self.last_command is not None:
                await asyncio.sleep(max(0, self.last_command + COMMAND_SPACING - loop.time()))
            else:
                await asyncio.sleep(0)  # Let pending registry/state events run first.
            entity = params["entity_id"]
            async with self.entity_lock(entity):
                if not guard(entity):
                    return "skipped", entity
                async def send(call_domain, call_service, payload, call_context, effect_guard):
                    if self.last_command is not None:
                        await asyncio.sleep(max(0, self.last_command + COMMAND_SPACING - loop.time()))
                    if not guard(entity) or (effect_guard is not None and not effect_guard()):
                        from homeassistant.exceptions import ServiceValidationError

                        raise ServiceValidationError("Der Lampenauftrag wurde inzwischen ersetzt.")
                    self.last_command = loop.time()
                    return await hass.services.async_call(call_domain, call_service, payload, blocking=True, context=call_context)

                try:
                    from .effects import async_call

                    await async_call(hass, domain, service, params, context, guard=guard, command_call=send)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    return "failed", entity
                return "applied", entity


def limiter(hass):
    return hass.data.setdefault(DOMAIN, {}).setdefault(
        "dynamic_command_limiter", DynamicCommandLimiter()
    )
