"""Versioned server-side persistence, never browser storage."""

from asyncio import Lock
from copy import deepcopy
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION


def empty_data() -> dict[str, Any]:
    """Return independent containers for the planned data model."""
    return {
        "scenes": [],
        "palettes": [],
        "rooms": {},
        "bindings": [],
        "schedules": [],
        "settings": {"light_entity_ids": []},
    }


class LichtzentraleStore:
    """Own the complete data model while preserving future-stage fields."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data = empty_data()
        self._lock = Lock()

    @property
    def data(self) -> dict[str, Any]:
        """Return a snapshot that callers cannot mutate accidentally."""
        return deepcopy(self._data)

    async def async_load(self) -> None:
        """Load data, filling missing keys without discarding saved fields."""
        saved = await self._store.async_load()
        if saved is not None:
            self._data.update(saved)
            self._data["settings"] = {
                "light_entity_ids": [],
                **saved.get("settings", {}),
            }
        else:
            await self._store.async_save(self._data)

    async def async_set_lights(self, entity_ids: list[str]) -> None:
        """Commit an explicit allowlist, keeping memory unchanged on failure."""
        async with self._lock:
            updated = deepcopy(self._data)
            updated["settings"]["light_entity_ids"] = list(dict.fromkeys(entity_ids))
            await self._store.async_save(updated)
            self._data = updated

    async def async_remove(self) -> None:
        """Remove integration data when its config entry is deleted."""
        await self._store.async_remove()
