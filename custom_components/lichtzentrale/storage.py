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
        self._hass = hass
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

    async def async_update_room(self, area_id: str, changes: dict) -> None:
        """Merge validated room settings atomically with concurrent scene writes."""
        async with self._lock:
            updated = deepcopy(self._data)
            updated["rooms"].setdefault(area_id, {}).update(deepcopy(changes))
            await self._store.async_save(updated)
            self._data = updated

    async def async_set_position(self, area_id: str, entity_id: str, position: dict | None):
        """Write one position without losing concurrent edits or trusting stale grants."""
        from homeassistant.helpers import area_registry as ar

        from .lights import entity_area_id, validate_lights
        from .positions import validate_position

        position = validate_position(position) if position is not None else None
        async with self._lock:
            # Validate after waiting for the Store lock: settings or area membership
            # may have changed while another write was being persisted.
            if (
                ar.async_get(self._hass).async_get_area(area_id) is None
                or entity_id not in self._data["settings"]["light_entity_ids"]
                or entity_area_id(self._hass, entity_id) != area_id
            ):
                raise ServiceValidationError("Die Lampe muss für diesen Raum freigegeben sein.")
            validate_lights(self._hass, [entity_id])
            updated = deepcopy(self._data)
            positions = updated["rooms"].setdefault(area_id, {}).setdefault("positions", {})
            if position is None:
                positions.pop(entity_id, None)
            else:
                positions[entity_id] = deepcopy(position)
            await self._store.async_save(updated)
            self._data = updated
            return deepcopy(position)

    async def async_remove(self) -> None:
        """Remove integration data when its config entry is deleted."""
        await self._store.async_remove()
