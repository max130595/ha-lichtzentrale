# Geändert für Lichtzentrale
"""Versioned server-side persistence, never browser storage."""

from asyncio import Lock
from copy import deepcopy
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
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

    async def async_save_scene(self, scene: dict, *, is_update: bool = False) -> None:
        """Upsert a validated scene without overwriting concurrent Store changes."""
        async with self._lock:
            updated = deepcopy(self._data)
            index = next(
                (i for i, s in enumerate(updated["scenes"]) if s["id"] == scene["id"]), None
            )
            if is_update and index is None:
                raise ServiceValidationError(
                    "Die Szene wurde inzwischen gelöscht. Bitte neu laden."
                )
            if index is None:
                updated["scenes"].append(deepcopy(scene))
            else:
                updated["scenes"][index] = deepcopy(scene)
            await self._store.async_save(updated)
            self._data = updated

    async def async_delete_scene(self, scene_id: str) -> None:
        """Remove a scene and every room reference in the same transaction."""
        async with self._lock:
            updated = deepcopy(self._data)
            updated["scenes"] = [s for s in updated["scenes"] if s["id"] != scene_id]
            for room in updated["rooms"].values():
                if room.get("last_scene_id") == scene_id:
                    room.pop("last_scene_id", None)
                if room.get("default_on") == scene_id:
                    room["default_on"] = "last"
                if "cycle" in room:
                    room["cycle"] = [s for s in room["cycle"] if s != scene_id]
            await self._store.async_save(updated)
            self._data = updated

    async def async_reorder_scenes(self, area_id: str, scene_ids: list[str]) -> None:
        """Require an exact permutation, so stale tabs cannot lose scene order."""
        async with self._lock:
            updated = deepcopy(self._data)
            expected = {s["id"] for s in updated["scenes"] if s["area_id"] == area_id}
            if len(scene_ids) != len(expected) or set(scene_ids) != expected:
                raise ServiceValidationError("Die Szenenliste hat sich geändert. Bitte neu laden.")
            positions = {scene_id: index for index, scene_id in enumerate(scene_ids)}
            for scene in updated["scenes"]:
                if scene["area_id"] == area_id:
                    scene["order"] = positions[scene["id"]]
            await self._store.async_save(updated)
            self._data = updated

    async def async_set_last_scene(self, area_id: str, scene_id: str) -> None:
        """Remember a successful recall; do not resurrect concurrently deleted scenes."""
        async with self._lock:
            if not any(
                s["id"] == scene_id and s["area_id"] == area_id for s in self._data["scenes"]
            ):
                return
            updated = deepcopy(self._data)
            updated["rooms"].setdefault(area_id, {})["last_scene_id"] = scene_id
            await self._store.async_save(updated)
            self._data = updated

    async def async_remove(self) -> None:
        """Remove integration data when its config entry is deleted."""
        await self._store.async_remove()
