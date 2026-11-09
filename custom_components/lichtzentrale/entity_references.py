# Geändert für Lichtzentrale
"""Exact, previewable lighting-reference migrations with atomic collision checks.

Only declared reference fields are traversed. User names, event signatures, IDs of
rooms/scenes, and unknown future payloads are never rewritten as text. Distinct
settings at the destination block the complete transaction; identical references
may merge, and that fact is always included in the preview.
"""

import hashlib
import json
import logging
import re
from copy import deepcopy
from uuid import uuid4

from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .lights import entity_area_id, list_lights, validate_lights

_LOGGER = logging.getLogger(__name__)
_LIGHT_ID = re.compile(r"^(light|switch)\.[a-z0-9_]+$")
_KIND_NAMES = {
    "settings": "Freigaben und letzte Lampenwerte", "zones": "Zone",
    "scenes": "Szene", "rooms": "Raumeinstellungen", "bindings": "Tasterbelegung",
    "schedules": "Zeitplan", "automatic_state": "Automatik-Stand",
    "active_dynamic": "Laufende Dynamik",
}


class _References:
    """A schema-aware walker, shared by discovery and replacement."""

    def __init__(self, old=None, new=None):
        self.old, self.new = old, new
        self.found = set()
        self.count = 0
        self.merges = 0
        self.conflicts = []

    def scalar(self, value):
        if isinstance(value, str) and _LIGHT_ID.fullmatch(value):
            self.found.add(value)
            if self.old is not None and value == self.old:
                self.count += 1
                return self.new
        return value

    def ids(self, obj, key):
        values = obj.get(key)
        if not isinstance(values, list):
            return
        updated = [self.scalar(value) for value in values]
        # Leave unrelated/legacy duplicates untouched; collapse only the pair
        # explicitly being merged, keeping the first position in ordered lists.
        if self.old is not None and self.old in values:
            seen_new = False
            result = []
            for value in updated:
                if value == self.new:
                    if seen_new:
                        self.merges += 1
                        continue
                    seen_new = True
                result.append(value)
            updated = result
        obj[key] = updated

    def mapping(self, obj, key):
        values = obj.get(key)
        if not isinstance(values, dict):
            return
        for entity_id in values:
            self.scalar(entity_id)
        if self.old is None or self.old not in values:
            return
        if self.new in values:
            if values[self.old] != values[self.new]:
                self.conflicts.append("Unterschiedliche gespeicherte Lampenwerte am Ziel")
                return
            self.merges += 1
        else:
            values[self.new] = values[self.old]
        del values[self.old]

    def action(self, obj):
        if not isinstance(obj, dict):
            return
        self.ids(obj, "entity_ids")
        if "entity_id" in obj:
            obj["entity_id"] = self.scalar(obj["entity_id"])
        for key in ("action", "params"):
            self.action(obj.get(key))
        for value in obj.get("actions", []) if isinstance(obj.get("actions"), list) else []:
            self.action(value)

    def scene(self, obj):
        if not isinstance(obj, dict):
            return
        for key in ("lights", "lamp_settings", "light_settings"):
            self.mapping(obj, key)
        self.ids(obj, "wave_order")
        if isinstance(obj.get("dynamic"), dict):
            self.ids(obj["dynamic"], "wave_order")

    def room(self, obj):
        if not isinstance(obj, dict):
            return
        self.mapping(obj, "positions")
        self.mapping(obj, "pre_off_lights")
        self.ids(obj, "pre_off_pending")
        motion = obj.get("motion")
        if isinstance(motion, dict):
            for window in motion.get("windows", []):
                if isinstance(window, dict):
                    self.action(window.get("action"))
        brightness = obj.get("brightness")
        if isinstance(brightness, dict):
            stages = brightness.get("stages", [])
            if self.old is not None:
                old_stages = {i for i, stage in enumerate(stages)
                              if self.old in stage.get("entity_ids", [])}
                new_stages = {i for i, stage in enumerate(stages)
                              if self.new in stage.get("entity_ids", [])}
                if any(a != b for a in old_stages for b in new_stages):
                    self.conflicts.append("Beide Lampen stehen in verschiedenen Helligkeitsstufen")
            for stage in stages:
                if isinstance(stage, dict):
                    self.ids(stage, "entity_ids")

    def item(self, kind, obj):
        if not isinstance(obj, dict):
            return
        if kind == "settings":
            self.ids(obj, "light_entity_ids")
            self.mapping(obj, "last_light_states")
        elif kind == "zones":
            self.ids(obj, "entity_ids")
            self.mapping(obj, "positions")
        elif kind == "scenes":
            self.scene(obj)
        elif kind == "rooms":
            self.room(obj)
        elif kind in {"bindings", "schedules", "automatic_state"}:
            self.action(obj)
        elif kind == "active_dynamic":
            self.scene(obj.get("scene"))
            for key in ("targets", "excluded", "entity_ids", "excluded_entity_ids", "wave_order"):
                self.ids(obj, key)


def _items(data):
    for kind in _KIND_NAMES:
        values = data.get(kind, {})
        if kind == "settings":
            yield kind, values
        elif isinstance(values, dict):
            yield from ((kind, item) for item in values.values())
        elif isinstance(values, list):
            yield from ((kind, item) for item in values)


def referenced_lights(data):
    """Return only actual lighting references, including currently missing lamps."""
    walker = _References()
    for kind, item in _items(deepcopy(data)):
        walker.item(kind, item)
    return walker.found


def build_reference_replacement(data, old_entity_id, new_entity_id):
    """Prepare a complete copy and report; never mutate input or partially commit."""
    if (not isinstance(old_entity_id, str) or not isinstance(new_entity_id, str)
            or not _LIGHT_ID.fullmatch(old_entity_id) or not _LIGHT_ID.fullmatch(new_entity_id)
            or old_entity_id == new_entity_id):
        raise ServiceValidationError("Bitte zwei verschiedene Lampen auswählen.")
    updated = deepcopy(data)
    walker = _References(old_entity_id, new_entity_id)
    entries = []
    for kind, item in _items(updated):
        before = walker.count
        conflict_start = len(walker.conflicts)
        walker.item(kind, item)
        if walker.count != before:
            if kind == "active_dynamic":
                # Fence persistence/cleanup already queued by the old runtime.
                # Its compare-and-swap token must not resurrect old references.
                item["token"] = uuid4().hex
            name = item.get("name") or item.get("control_label") or _KIND_NAMES[kind]
            entries.append({"kind": kind, "name": name, "count": walker.count - before})
        for i in range(conflict_start, len(walker.conflicts)):
            name = item.get("name") or _KIND_NAMES[kind]
            walker.conflicts[i] = f"{name}: {walker.conflicts[i]}."
    warnings = []
    if walker.merges:
        warnings.append(f"{walker.merges} gleiche Verweise werden zusammengeführt; "
                        "die erste Position in Listen bleibt erhalten.")
    report = {"entries": entries, "conflicts": walker.conflicts, "warnings": warnings,
              "can_replace": bool(entries) and not walker.conflicts}
    # An unusable preview must not accidentally expose a partially migrated tree.
    return (updated if report["can_replace"] else deepcopy(data)), report


def _physical_reference_areas(data, entity_id):
    """Find only room-constrained references; explicit motion targets may cross rooms."""
    result = set()
    for area_id, config in data.get("rooms", {}).items():
        constrained = {key: config[key] for key in (
            "positions", "pre_off_lights", "pre_off_pending", "brightness"
        ) if key in config}
        if entity_id in referenced_lights({"rooms": {area_id: constrained}}):
            result.add(area_id)
    for scene in data.get("scenes", []):
        if entity_id in referenced_lights({"scenes": [scene]}):
            result.add(scene.get("area_id"))
    for binding in data.get("bindings", []):
        params = binding.get("params") or {}
        # Plain selected-light buttons may cross rooms. Ambient buttons have an
        # explicit container whose physical scope must survive replacement.
        if params.get("ambient_first") and entity_id in params.get("entity_ids", []):
            result.add(binding.get("area_id"))
    for kind in ("automatic_state", "active_dynamic"):
        for area_id, value in data.get(kind, {}).items():
            if entity_id in referenced_lights({kind: {area_id: value}}):
                result.add(area_id)
    return result


def _identity(entry):
    if entry is None:
        return None
    return (entry.id, entry.unique_id, entry.platform, entry.domain, entry.device_id)


class EntityReferenceManager:
    """Admin replacement previews and identity-checked registry rename handling."""

    def __init__(self, hass, store):
        self.hass, self.store = hass, store
        self._unsubscribe = None
        self._known = {}

    @callback
    def start(self):
        registry = er.async_get(self.hass)
        self._known = {entry.entity_id: _identity(entry) for entry in registry.entities.values()}
        self._unsubscribe = self.hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED,
                                                     self._registry_updated)

    async def shutdown(self):
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None
        self._known.clear()

    def options(self):
        data = self.store.data
        allowed = data.get("settings", {}).get("light_entity_ids", [])
        lights = list_lights(self.hass, allowed, include_hidden=True)
        by_id = {light["entity_id"]: light for light in lights}
        sources = []
        for index, entity_id in enumerate(sorted(referenced_lights(data)), 1):
            state = self.hass.states.get(entity_id)
            light = by_id.get(entity_id)
            sources.append({"entity_id": entity_id,
                            "name": state.name if state else f"Gespeicherte Lampe {index}",
                            "available": bool(light and light["available"])})
        return {"sources": sources, "targets": [light for light in lights if light["allowed"]]}

    def _target_signature(self, entity_id):
        state = self.hass.states.get(entity_id)
        entry = er.async_get(self.hass).async_get(entity_id)
        return {"identity": _identity(entry), "area_id": entity_area_id(self.hass, entity_id),
                "disabled": str(entry.disabled_by) if entry else None,
                "available": bool(state and state.state not in {"unknown", "unavailable"}),
                "capabilities": {key: state.attributes.get(key) for key in (
                    "supported_color_modes", "supported_features", "min_color_temp_kelvin",
                    "max_color_temp_kelvin") } if state else None}

    def _preview(self, data, old, new):
        if new not in data.get("settings", {}).get("light_entity_ids", []):
            raise ServiceValidationError("Die neue Lampe muss zuerst unter Freigaben erlaubt werden.")
        validate_lights(self.hass, [new])
        updated, report = build_reference_replacement(data, old, new)
        if not report["entries"]:
            raise ServiceValidationError("Für die bisherige Lampe wurden keine Verweise gefunden.")
        areas = ar.async_get(self.hass)
        target_area = entity_area_id(self.hass, new)
        for area_id in sorted(_physical_reference_areas(data, old), key=str):
            # Zone membership is explicitly migrated. Stale/deleted areas remain
            # visible for repair, but never become new physical-room constraints.
            if (not isinstance(area_id, str) or area_id.startswith("zone:")
                    or not (area := areas.async_get_area(area_id)) or target_area == area_id):
                continue
            report["conflicts"].append(
                f"{area.name}: Die neue Lampe gehört nicht zu diesem Raum. "
                "Bitte die neue Lampe zuerst in Home Assistant demselben Raum zuordnen. "
                "Die bisherigen Einstellungen bleiben unverändert."
            )
        if report["conflicts"]:
            report["can_replace"] = False
            updated = deepcopy(data)
        source, target = self.hass.states.get(old), self.hass.states.get(new)
        if target.state not in {"on", "off"}:
            raise ServiceValidationError("Die neue Lampe ist derzeit nicht verfügbar.")
        modes = set(target.attributes.get("supported_color_modes") or [])
        if target.domain == "switch" or not modes or modes <= {"onoff", "unknown"}:
            report["warnings"].append(
                "Das Ziel unterstützt nur An/Aus oder meldet noch keine Dimmfähigkeit. "
                "Gespeicherte Helligkeit und Farben bleiben erhalten, werden aber nur bei "
                "passenden Fähigkeiten angewendet. Farbwechsel ist für reine Schalter nicht möglich."
            )
        elif not modes.intersection({"xy", "hs", "rgb", "rgbw", "rgbww"}):
            report["warnings"].append(
                "Das Ziel unterstützt keine Farben. Gespeicherte Farben bleiben erhalten; "
                "Weißtonlampen verwenden einen passenden Weißton."
            )
        digest = hashlib.sha256(json.dumps(
            {"data": data, "old": old, "new": new, "source": self._target_signature(old),
             "target": self._target_signature(new)},
            sort_keys=True, separators=(",", ":"), default=str,
        ).encode()).hexdigest()
        report.update({"old_entity_id": old, "new_entity_id": new,
                       "source_name": source.name if source else "Gespeicherte Lampe",
                       "target_name": target.name, "preview_token": digest})
        return updated, report

    def preview(self, old_entity_id, new_entity_id):
        return self._preview(self.store.data, old_entity_id, new_entity_id)[1]

    async def async_replace(self, old_entity_id, new_entity_id, preview_token):
        """Require the exact current read-only preview before one atomic save."""
        def transform(data):
            updated, report = self._preview(data, old_entity_id, new_entity_id)
            if not isinstance(preview_token, str) or preview_token != report["preview_token"]:
                raise ServiceValidationError("Die Vorschau ist nicht mehr aktuell. Bitte neu prüfen.")
            if not report["can_replace"]:
                raise ServiceValidationError("Widersprüchliche Lampenwerte: Bitte zuerst bereinigen.")
            return updated, {**report, "replaced": True}

        # Validate before touching runtime sessions. The lock repeats this check,
        # including after any preview rollback or a concurrent configuration save.
        transform(self.store.data)
        await self._invalidate_preview(old_entity_id, new_entity_id)
        result = await self.store.async_transform_entity_references(transform)
        warnings = await self._refresh(old_entity_id, new_entity_id)
        result["runtime_warnings"] = warnings
        result["warnings"].extend(warnings)
        return result

    async def _invalidate_preview(self, old, new):
        if preview := self.hass.data.get(DOMAIN, {}).get("live_preview"):
            await preview.async_invalidate([old, new])

    async def _refresh(self, old, new):
        runtime = self.hass.data.get(DOMAIN, {})
        warnings = []

        def refresh(label, method, *args):
            try:
                method(*args)
            except Exception:
                _LOGGER.exception("Lampenverweise gespeichert, Laufzeit konnte nicht erneuert werden")
                warnings.append(f"Gespeichert, aber {label} konnte nicht aktualisiert werden. "
                                "Bitte Lichtzentrale neu laden und das Protokoll prüfen.")

        if bindings := runtime.get("bindings"):
            refresh("die Tastersteuerung", bindings.refresh_bindings)
        if schedules := runtime.get("schedules"):
            refresh("die Zeitplansteuerung", schedules.refresh_config)
        for area, config in self.store.data.get("rooms", {}).items():
            if not {old, new}.intersection(referenced_lights({"rooms": {area: config}})):
                continue
            for key in ("motion", "brightness"):
                if manager := runtime.get(key):
                    refresh("die Raumautomatik", manager.refresh_config, area)
        if dynamic := runtime.get("dynamic"):
            try:
                await dynamic.entity_references_changed(old, new)
            except Exception:
                _LOGGER.exception("Lampenverweise gespeichert, Dynamik konnte nicht erneuert werden")
                warnings.append("Gespeichert, aber die Dynamik konnte nicht fortgesetzt werden. "
                                "Bitte die Szene neu starten und das Protokoll prüfen.")
        return warnings

    async def _registry_updated(self, event):
        data = event.data
        old = data.get("changes", {}).get("entity_id") or data.get("old_entity_id")
        new = data.get("entity_id")
        registry = er.async_get(self.hass)
        expected = self._known.get(old)
        entry = registry.async_get(new) if isinstance(new, str) else None
        if entry is None and expected is not None and data.get("action") == "update":
            # Registry events may queue while one Store save is awaiting disk.
            # Follow the stable entry to its newest ID, never a reused name.
            entry = next((candidate for candidate in registry.entities.values()
                          if _identity(candidate) == expected), None)
            if entry is not None:
                new = entry.entity_id
        if isinstance(new, str):
            if entry:
                self._known[new] = _identity(entry)
            else:
                self._known.pop(new, None)
        if old and old != new:
            self._known.pop(old, None)
        if (data.get("action") != "update" or not isinstance(old, str)
                or not isinstance(new, str) or not _LIGHT_ID.fullmatch(old)
                or not _LIGHT_ID.fullmatch(new) or old == new or expected is None
                or _identity(entry) != expected or registry.async_get(old) is not None
                or entry.disabled_by is not None):
            return

        def transform(saved):
            current = registry.async_get(new)
            if _identity(current) != expected:
                current = next((candidate for candidate in registry.entities.values()
                                if _identity(candidate) == expected), None)
            if current is None or current.disabled_by is not None or registry.async_get(old) is not None:
                raise ServiceValidationError("Die Lampenzuordnung hat sich inzwischen geändert.")
            updated, report = build_reference_replacement(saved, old, current.entity_id)
            report["new_entity_id"] = current.entity_id
            if report["conflicts"]:
                raise ServiceValidationError(" ".join(report["conflicts"]))
            return updated, report

        if old not in referenced_lights(self.store.data):
            return
        try:
            transform(self.store.data)
            await self._invalidate_preview(old, new)
            result = await self.store.async_transform_entity_references(transform)
            await self._refresh(old, result["new_entity_id"])
        except Exception:
            # Leave every stored reference intact on collision/storage failure;
            # a visible log points the administrator to the replacement preview.
            _LOGGER.exception("Lampen-Umbenennung nicht vollständig übernommen; "
                              "bitte unter Mehr → Lampe ersetzen prüfen.")
