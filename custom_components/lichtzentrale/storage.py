# Geändert für Lichtzentrale
"""Versioned server-side persistence, never browser storage."""

import math
from asyncio import Lock
from copy import deepcopy
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION


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
        async with self._lock:
            saved = await self._store.async_load()
            updated = empty_data()
            migrated = False
            if saved is not None:
                updated.update(deepcopy(saved))
                updated["settings"] = {
                    "light_entity_ids": [],
                    **deepcopy(saved.get("settings", {})),
                }
                # Do not revalidate runtime references while loading: stale plans
                # must remain visible and removable. Preserve every other field.
                for schedule in updated["schedules"]:
                    if not isinstance(schedule, dict):
                        continue
                    condition = schedule.get("condition")
                    if isinstance(condition, dict) and "time_window" not in condition:
                        condition["time_window"] = None
                        migrated = True
            if saved is None or migrated:
                await self._store.async_save(updated)
            # Publish only after a necessary migration has reached disk.
            self._data = updated

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
            if "pre_off_lights" in changes:
                from .lights import entity_area_id, is_individual_light
                from .rooms import _remember_light

                # Share the newest room-off values with explicit-target recalls.
                # Pending/off peers retain their own previous useful last state.
                values = {
                    entity_id: _remember_light(state)
                    for entity_id in changes["pre_off_lights"]
                    if entity_id in self._data["settings"]["light_entity_ids"]
                    and entity_area_id(self._hass, entity_id) == area_id
                    and (state := self._hass.states.get(entity_id)) is not None
                    and state.domain == "light"
                    and state.state == "on"
                    and is_individual_light(self._hass, state)
                }
                if values:
                    updated["settings"].setdefault("last_light_states", {}).update(values)
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

    async def async_remember_light_states(self, entity_ids):
        """Capture approved, currently-on lights under the persistence lock."""
        from .rooms import _remember_light
        from .selected_lights import validate_selected_lights

        async with self._lock:
            targets = validate_selected_lights(self._hass, self, entity_ids)
            captured = {entity_id: self._hass.states.get(entity_id) for entity_id in targets}
            values = {
                entity_id: _remember_light(state)
                for entity_id, state in captured.items()
                if state.domain == "light" and state.state == "on"
            }
            # Already-off or unavailable lights never erase a useful last state.
            if values:
                updated = deepcopy(self._data)
                updated["settings"].setdefault("last_light_states", {}).update(values)
                await self._store.async_save(updated)
                self._data = updated
            return captured

    async def async_save_binding(self, binding: dict, *, is_update: bool = False) -> dict:
        """Validate and persist one unique button/event action atomically."""
        from .bindings import validate_binding

        async with self._lock:
            binding = validate_binding(self._hass, self, binding)
            updated = deepcopy(self._data)
            index = next(
                (i for i, item in enumerate(updated["bindings"]) if item["id"] == binding["id"]),
                None,
            )
            if is_update and index is None:
                raise ServiceValidationError("Die Belegung wurde inzwischen gelöscht. Bitte neu laden.")
            if any(
                item["id"] != binding["id"]
                and item["event_entity"] == binding["event_entity"]
                and item["event_type"] == binding["event_type"]
                for item in updated["bindings"]
            ):
                raise ServiceValidationError("Für dieses Ereignis gibt es bereits eine Belegung.")
            if index is None:
                updated["bindings"].append(deepcopy(binding))
            else:
                updated["bindings"][index] = deepcopy(binding)
            await self._store.async_save(updated)
            self._data = updated
            self._refresh_bindings()
            return deepcopy(binding)

    def _refresh_bindings(self) -> None:
        """Invalidate delayed work immediately after the changed binding commits."""
        if manager := self._hass.data.get(DOMAIN, {}).get("bindings"):
            manager.refresh_bindings()

    async def async_delete_binding(self, binding_id: str) -> None:
        """Remove one binding without losing concurrent room or scene writes."""
        async with self._lock:
            updated = deepcopy(self._data)
            updated["bindings"] = [item for item in updated["bindings"] if item["id"] != binding_id]
            await self._store.async_save(updated)
            self._data = updated
            self._refresh_bindings()

    async def async_set_double_click(self, milliseconds: int) -> dict:
        """Persist a bounded global recognition window; never browser-local."""
        if type(milliseconds) is not int or not 200 <= milliseconds <= 1000:
            raise ServiceValidationError("Das Doppelklick-Fenster muss 200–1000 ms betragen.")
        async with self._lock:
            updated = deepcopy(self._data)
            updated["settings"]["double_click_ms"] = milliseconds
            await self._store.async_save(updated)
            self._data = updated
            return {"double_click_ms": milliseconds}

    async def async_set_room_settings(self, area_id: str, changes: dict) -> dict:
        """Configure only same-room cycle/default references under the Store lock."""
        from .adaptive import _validated
        from .rooms import room_targets

        if not changes or set(changes) - {"cycle", "default_on"}:
            raise ServiceValidationError("Bitte Szenenzyklus oder Einschaltregel angeben.")
        async with self._lock:
            if not room_targets(self._hass, self, area_id):
                raise ServiceValidationError("Bitte zuerst Lampen für diesen Raum freigeben.")
            scene_ids = {scene["id"] for scene in self._data["scenes"] if scene["area_id"] == area_id}
            if "cycle" in changes:
                cycle = changes["cycle"]
                if (
                    not isinstance(cycle, list)
                    or len(cycle) > 500
                    or any(not isinstance(item, str) or item not in scene_ids for item in cycle)
                    or len(set(cycle)) != len(cycle)
                ):
                    raise ServiceValidationError("Der Szenenzyklus darf nur Szenen dieses Raums enthalten.")
            if "default_on" in changes:
                default = changes["default_on"]
                if not isinstance(default, str) or default not in {"last", "adaptive", *scene_ids}:
                    raise ServiceValidationError("Bitte eine Einschaltregel für diesen Raum auswählen.")
                if default == "adaptive":
                    switch = self._data["rooms"].get(area_id, {}).get("adaptive_switch")
                    _validated(self._hass, self, area_id, switch)
            updated = deepcopy(self._data)
            room = updated["rooms"].setdefault(area_id, {})
            room.update(deepcopy(changes))
            await self._store.async_save(updated)
            self._data = updated
            return {"cycle": list(room.get("cycle", [])), "default_on": room.get("default_on", "last")}

    async def async_set_motion(self, area_id: str, config: dict) -> dict:
        """Commit complete room automation without losing concurrent room edits."""
        from .motion_config import validate_motion

        async with self._lock:
            config = validate_motion(self._hass, self, area_id, config)
            updated = deepcopy(self._data)
            updated["rooms"].setdefault(area_id, {})["motion"] = config
            await self._store.async_save(updated)
            self._data = updated
            self._refresh_motion(area_id)
            return deepcopy(config)

    async def async_set_motion_enabled(self, area_id: str, enabled: bool, *, guard=None) -> dict:
        """Disable even stale setups; enabling revalidates every selected resource."""
        from .motion_config import validate_motion

        if type(enabled) is not bool:
            raise ServiceValidationError("Bitte einen Ein/Aus-Wert angeben.")
        async with self._lock:
            config = deepcopy(self._data["rooms"].get(area_id, {}).get("motion"))
            if not isinstance(config, dict):
                raise ServiceValidationError("Bitte zuerst die Bewegungsautomatik einrichten.")
            config["enabled"] = enabled
            if enabled:
                config = validate_motion(self._hass, self, area_id, config)
            updated = deepcopy(self._data)
            updated["rooms"][area_id]["motion"] = config
            if guard is not None and not guard():
                raise ServiceValidationError("Die Bedingungen des Zeitplans sind nicht mehr erfüllt.")
            await self._store.async_save(updated)
            self._data = updated
            self._refresh_motion(area_id)
            return deepcopy(config)

    def _refresh_motion(self, area_id: str) -> None:
        if manager := self._hass.data.get(DOMAIN, {}).get("motion"):
            manager.refresh_config(area_id)

    async def async_set_brightness(self, area_id: str, config: dict) -> dict:
        """Commit settings atomically, retaining learning only for unchanged stages/sensor."""
        from .brightness_config import validate_brightness

        async with self._lock:
            config = validate_brightness(self._hass, self, area_id, config)
            updated = deepcopy(self._data)
            room = updated["rooms"].setdefault(area_id, {})
            previous = room.get("brightness", {})
            if any(previous.get(key) != config[key] for key in ("lux_sensor_entity_id", "stages")):
                room["brightness_learned"] = [None] * len(config["stages"])
            room["brightness"] = config
            await self._store.async_save(updated)
            self._data = updated
            self._refresh_brightness(area_id)
            return deepcopy(config)

    async def async_set_brightness_enabled(self, area_id: str, enabled: bool) -> dict:
        """Always permit disabling stale setups; validate all references on enabling."""
        from .brightness_config import validate_brightness

        if type(enabled) is not bool:
            raise ServiceValidationError("Bitte einen Ein/Aus-Wert angeben.")
        async with self._lock:
            config = deepcopy(self._data["rooms"].get(area_id, {}).get("brightness"))
            if not isinstance(config, dict):
                raise ServiceValidationError("Bitte zuerst die Grundhelligkeit einrichten.")
            config["enabled"] = enabled
            if enabled:
                config = validate_brightness(self._hass, self, area_id, config)
            updated = deepcopy(self._data)
            updated["rooms"][area_id]["brightness"] = config
            await self._store.async_save(updated)
            self._data = updated
            self._refresh_brightness(area_id)
            return deepcopy(config)

    async def async_learn_brightness(self, area_id, expected_config, index, rise, *, guard=None):
        """Persist an EMA sample without refreshing runtime or resurrecting stale work."""
        if (type(index) is not int or index < 0 or type(rise) not in (int, float)
                or not math.isfinite(rise) or rise < 0):
            raise ServiceValidationError("Ungültiger gelernter Lichtanteil.")
        async with self._lock:
            room = self._data["rooms"].get(area_id, {})
            config = room.get("brightness")
            if (not isinstance(config, dict) or config != expected_config
                    or index >= len(config["stages"]) or (guard is not None and not guard())):
                return False
            updated = deepcopy(self._data)
            room = updated["rooms"][area_id]
            learned = room.setdefault("brightness_learned", [None] * len(config["stages"]))
            previous = learned[index]
            learned[index] = rise if previous is None else previous * 0.75 + rise * 0.25
            await self._store.async_save(updated)
            self._data = updated
            return True

    def _refresh_brightness(self, area_id):
        if manager := self._hass.data.get(DOMAIN, {}).get("brightness"):
            manager.refresh_config(area_id)

    async def async_save_schedule(self, raw: dict) -> dict:
        """Validate and commit one plan atomically, rejecting stale editor IDs."""
        from .schedule_config import validate_schedule

        async with self._lock:
            schedule = validate_schedule(self._hass, self, raw)
            updated = deepcopy(self._data)
            index = next((i for i, item in enumerate(updated["schedules"])
                          if item["id"] == schedule["id"]), None)
            if index is None:
                updated["schedules"].append(schedule)
            else:
                updated["schedules"][index] = schedule
            await self._store.async_save(updated)
            self._data = updated
            self._refresh_schedules(schedule["id"])
            return deepcopy(schedule)

    async def async_set_schedule_enabled(self, schedule_id: str, enabled: bool) -> dict:
        """Always allow stale plans to be disabled; revalidate before enabling."""
        from .schedule_config import validate_schedule

        if type(enabled) is not bool:
            raise ServiceValidationError("Bitte einen Ein/Aus-Wert angeben.")
        async with self._lock:
            updated = deepcopy(self._data)
            schedule = next((item for item in updated["schedules"]
                             if item["id"] == schedule_id), None)
            if schedule is None:
                raise ServiceValidationError("Der Zeitplan wurde nicht gefunden. Bitte neu laden.")
            schedule["enabled"] = enabled
            if enabled:
                validate_schedule(self._hass, self, schedule)
            await self._store.async_save(updated)
            self._data = updated
            self._refresh_schedules(schedule_id)
            return deepcopy(schedule)

    async def async_claim_schedule_day(self, schedule_id: str, day: str) -> bool:
        """Persist a daily execution claim before dispatch, including across restarts."""
        async with self._lock:
            schedule = next((item for item in self._data["schedules"]
                             if item["id"] == schedule_id), None)
            if schedule is None or not schedule["enabled"]:
                return False
            claims = self._data["settings"].get("schedule_last_run_dates", {})
            if claims.get(schedule_id) == day:
                return False
            updated = deepcopy(self._data)
            updated["settings"].setdefault("schedule_last_run_dates", {})[schedule_id] = day
            await self._store.async_save(updated)
            self._data = updated
            return True

    async def async_delete_schedule(self, schedule_id: str) -> None:
        """Remove exactly one saved plan and retire outstanding work after commit."""
        async with self._lock:
            if not any(item["id"] == schedule_id for item in self._data["schedules"]):
                raise ServiceValidationError("Der Zeitplan wurde nicht gefunden. Bitte neu laden.")
            updated = deepcopy(self._data)
            updated["schedules"] = [item for item in updated["schedules"]
                                    if item["id"] != schedule_id]
            updated["settings"].get("schedule_last_run_dates", {}).pop(schedule_id, None)
            await self._store.async_save(updated)
            self._data = updated
            self._refresh_schedules(schedule_id)

    def _refresh_schedules(self, schedule_id: str) -> None:
        if manager := self._hass.data.get(DOMAIN, {}).get("schedules"):
            manager.refresh_config(schedule_id)

    async def async_remove(self) -> None:
        """Remove integration data when its config entry is deleted."""
        await self._store.async_remove()
