# Geändert für Lichtzentrale
"""Successful automation recalls, valid only for the current local calendar day."""

from copy import deepcopy
from zoneinfo import ZoneInfo

from homeassistant.util import dt as dt_util


def local_day(hass):
    return dt_util.utcnow().astimezone(ZoneInfo(hass.config.time_zone)).date().isoformat()


def current_action(hass, store, area_id):
    value = store.data.get("automatic_state", {}).get(area_id, {})
    return deepcopy(value.get("action")) if value.get("day") == local_day(hass) else None


async def async_record_action(hass, store, action, result):
    """Never record failure/partial execution or unrelated manual controls."""
    if not result.get("applied") or result.get("failed") or result.get("skipped"):
        return
    kind = action.get("type")
    areas = action.get("area_ids", []) or ([action["area_id"]] if action.get("area_id") else [])
    if kind == "scene":
        scene = next((s for s in store.data["scenes"] if s["id"] == action.get("scene_id")), None)
        if not scene:
            return
        areas = [scene["area_id"]]
    elif kind not in {"off", "room_off", "night"}:
        return
    for area_id in dict.fromkeys(areas):
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
