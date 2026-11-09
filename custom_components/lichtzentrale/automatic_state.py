# Geändert für Lichtzentrale
"""Successful automation recalls, valid only for the current local calendar day."""

import logging
from copy import deepcopy
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


def local_day(hass):
    return dt_util.utcnow().astimezone(ZoneInfo(hass.config.time_zone)).date().isoformat()


def current_action(hass, store, area_id):
    value = store.data.get("automatic_state", {}).get(area_id, {})
    return deepcopy(value.get("action")) if value.get("day") == local_day(hass) else None


def recall_actions(hass, store, area_id):
    """Prefer this target's own day state, otherwise the newest source per lamp.

    Old entries without a timestamp remain usable, behind dated entries. A
    persisted sequence breaks equal timestamps; source IDs break legacy ties
    deterministically. Scene membership and current grants restrict inheritance,
    so an unrelated lamp never acquires a scene's state.
    """
    if own := current_action(hass, store, area_id):
        return [(own, None)]
    from .rooms import room_targets
    from .target_actions import action_targets, night_scene
    from .zones import contains, validate_area

    targets = set(room_targets(hass, store, area_id))
    day = local_day(hass)

    def newest(item):
        key, value = item
        raw_timestamp = value.get("updated_at")
        timestamp = dt_util.parse_datetime(raw_timestamp) if isinstance(raw_timestamp, str) else None
        if timestamp is None or timestamp.tzinfo is None:
            timestamp = datetime.min.replace(tzinfo=UTC)
        sequence = value.get("sequence", 0)
        return timestamp, sequence if type(sequence) is int else 0, key

    candidates = sorted(
        ((key, value) for key, value in store.data.get("automatic_state", {}).items()
         if value.get("day") == day and key != area_id),
        key=newest, reverse=True,
    )
    result = []
    for source, value in candidates:
        action = deepcopy(value.get("action"))
        if not isinstance(action, dict) or action.get("type") not in {"scene", "off", "night"}:
            continue
        try:
            validate_area(hass, store, source)
            shared = {e for e in targets if contains(hass, store, source, e)}
            if not shared:
                continue
            resolved = action
            if action["type"] == "night":
                resolved = {"type": "scene", "scene_id": night_scene(store, source)["id"]}
            shared.intersection_update(action_targets(hass, store, resolved, _entity_ids=shared))
            if resolved["type"] == "scene":
                scene = next(s for s in store.data["scenes"] if s["id"] == resolved["scene_id"])
                from .seasonal_scenes import resolve_scene

                scene, _ = resolve_scene(hass, store, scene)
                if scene["kind"] == "palette":
                    shared = {e for e in shared if e.startswith("light.")}
        except ServiceValidationError:
            # Deleted source rooms/scenes must not prevent another valid match.
            continue
        if shared:
            result.append((resolved, sorted(shared)))
            targets.difference_update(shared)
    return result


async def async_record_action(hass, store, action, result):
    """Remember successful automatic targets, including partial execution."""
    if not result.get("applied"):
        return
    from .zones import contains, validate_area

    kind = action.get("type")
    areas = action.get("area_ids", []) or ([action["area_id"]] if action.get("area_id") else [])
    if kind == "scene":
        scene = next((s for s in store.data["scenes"] if s["id"] == action.get("scene_id")), None)
        if not scene:
            return
        areas = [scene["area_id"]]
    elif kind not in {"off", "room_off", "night"}:
        return
    if result.get("failed") or result.get("skipped"):
        _LOGGER.warning(
            "Automatikstand als Teilergebnis gespeichert: %s angewendet, %s übersprungen, %s fehlgeschlagen.",
            len(result["applied"]), len(result.get("skipped", [])), len(result.get("failed", [])),
        )
    for area_id in dict.fromkeys(areas):
        try:
            validate_area(hass, store, area_id)
        except ServiceValidationError:
            continue
        applied = [entity for entity in result["applied"]
                   if entity in store.data["settings"]["light_entity_ids"]
                   and contains(hass, store, area_id, entity)]
        if not applied:
            continue
        saved = {"type": "off" if kind == "room_off" else kind, "area_id": area_id}
        if kind == "scene":
            saved["scene_id"] = action["scene_id"]
        await store.async_set_automatic_state(area_id, saved, local_day(hass))


class AutomaticStateManager:
    """Expire persisted day state at local midnight, including DST transitions."""

    def __init__(self, hass, store):
        self.hass, self.store = hass, store
        self._unsubscribe = None

    async def start(self):
        from homeassistant.helpers.event import async_track_time_change

        await self.store.async_expire_automatic_state(local_day(self.hass))
        self._unsubscribe = async_track_time_change(self.hass, self._midnight, hour=0, minute=0, second=0)

    async def _midnight(self, now):
        await self.store.async_expire_automatic_state(local_day(self.hass))

    async def shutdown(self):
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None
