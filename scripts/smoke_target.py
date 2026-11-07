# Geändert für Lichtzentrale
"""Native HA compatibility smoke test, not a replacement for the pytest suite.

Run with the target Home Assistant installed:
    python scripts/smoke_target.py

No pytest fixtures, HA private-symbol shims, network listeners, or external devices.
Real Store files live only inside a temporary directory deleted after this run.
"""

from __future__ import annotations

import asyncio
import json
import sys
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

# Import HA before anything that may import httpx: HA 2026.11 installs its
# supported httpx2 alias during package initialization.
import homeassistant  # noqa: F401
from aiohue.v2.models.feature import ColorFeatureBase, ColorPoint, OnFeature
from aiohue.v2.models.resource import ResourceIdentifier, ResourceTypes
from aiohue.v2.models.scene import Action, ActionAction, Scene, SceneMetadata
from homeassistant.components.light import LightEntityFeature
from homeassistant.config_entries import (
    STORAGE_KEY as CONFIG_STORAGE_KEY,
)
from homeassistant.config_entries import (
    STORAGE_VERSION as CONFIG_STORAGE_VERSION,
)
from homeassistant.config_entries import (
    STORAGE_VERSION_MINOR as CONFIG_STORAGE_VERSION_MINOR,
)
from homeassistant.config_entries import (
    ConfigEntries,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry, device_registry, entity_registry
from homeassistant.helpers.storage import Store

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.lichtzentrale import (  # noqa: E402
    async_remove_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.lichtzentrale.adaptive import (  # noqa: E402
    async_set_adaptive,
)
from custom_components.lichtzentrale.adaptive import (
    status as adaptive_status,
)
from custom_components.lichtzentrale.config_flow import LichtzentraleConfigFlow  # noqa: E402
from custom_components.lichtzentrale.const import DOMAIN, STORAGE_KEY  # noqa: E402
from custom_components.lichtzentrale.dynamic_scenes import DynamicSceneManager  # noqa: E402
from custom_components.lichtzentrale.lights import list_lights, validate_lights  # noqa: E402
from custom_components.lichtzentrale.palettes import async_apply_palette, list_palettes  # noqa: E402
from custom_components.lichtzentrale.rooms import async_toggle_room, list_rooms  # noqa: E402
from custom_components.lichtzentrale.scenes import (  # noqa: E402
    async_apply_scene,
    async_delete_scene,
    async_save_scene,
    async_snapshot,
    hue_scene_preview,
    hue_scene_targets,
)
from custom_components.lichtzentrale.storage import LichtzentraleStore  # noqa: E402
from custom_components.lichtzentrale.websocket_api import APPLY_FIELDS  # noqa: E402


async def run(config_dir: str) -> None:
    """Exercise real native objects without bootstrapping network integrations."""
    hass = HomeAssistant(config_dir)
    # Load a synthetic config entry via the actual storage/initialization path.
    # Never set up Hue itself: that would start network discovery.
    config_store = Store(
        hass, CONFIG_STORAGE_VERSION, CONFIG_STORAGE_KEY, minor_version=CONFIG_STORAGE_VERSION_MINOR
    )
    await config_store.async_save(
        {
            "entries": [
                {
                    "entry_id": f"fixture-{domain}-config",
                    "domain": domain,
                    "title": "Fixture bridge",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "modified_at": "2026-01-01T00:00:00+00:00",
                    "data": {},
                    "options": {},
                    "disabled_by": None,
                    "discovery_keys": {},
                    "minor_version": 1,
                    "pref_disable_new_entities": False,
                    "pref_disable_polling": False,
                    "source": "user",
                    "subentries": [],
                    "unique_id": f"fixture-{domain}",
                    "version": 1,
                }
                for domain in ("hue", "adaptive_lighting")
            ]
        }
    )
    hass.config_entries = ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    try:
        await area_registry.async_load(hass)
        device_registry.async_setup(hass)
        await device_registry.async_load(hass)
        await entity_registry.async_load(hass)
        assert callable(async_setup_entry)
        assert callable(async_unload_entry)
        assert callable(async_remove_entry)
        assert LichtzentraleConfigFlow.VERSION == 1
        assert APPLY_FIELDS

        store = LichtzentraleStore(hass)
        await store.async_load()
        assert store.data["settings"]["light_entity_ids"] == []
        path = Path(config_dir) / ".storage" / STORAGE_KEY
        assert path.is_file()
        assert json.loads(path.read_text())["version"] == 1

        calls = []

        @callback
        def capture(call):
            calls.append(call)

        hass.services.async_register("light", "turn_on", capture)
        modes = ["xy", "rgbww", "color_temp", "brightness", "onoff"]
        targets = []
        for index, mode in enumerate(modes):
            entity_id = f"light.fixture_{index}"
            targets.append(entity_id)
            hass.states.async_set(
                entity_id,
                "off",
                {
                    "supported_color_modes": [mode],
                    "supported_features": LightEntityFeature.TRANSITION,
                    # A deliberately narrow CT range verifies clamping.
                    "min_color_temp_kelvin": 3999,
                    "max_color_temp_kelvin": 4000,
                },
            )
        hass.states.async_set(
            "light.fixture_unavailable", "unavailable", {"supported_color_modes": ["xy"]}
        )
        targets.append("light.fixture_unavailable")
        await store.async_set_lights(targets)
        restored = LichtzentraleStore(hass)
        await restored.async_load()
        assert restored.data == store.data
        assert len(list_lights(hass, targets)) == 6

        palettes = list_palettes()
        assert len(palettes) == 12
        assert len({item["category"] for item in palettes}) == 4
        result = await async_apply_palette(hass, restored, palettes[0]["id"], targets, 123)
        assert result == {"applied": targets[:-1], "skipped": ["light.fixture_unavailable"]}
        assert len(calls) == 5
        assert "xy_color" in calls[0].data
        assert "xy_color" in calls[1].data
        assert 3999 <= calls[2].data["color_temp_kelvin"] <= 4000
        assert calls[3].data["brightness"] == 123
        assert "xy_color" not in calls[3].data
        assert "brightness" not in calls[4].data
        assert all(call.data["transition"] == 1 for call in calls)

        for forbidden in ("switch.fixture_a", "lock.fixture_a", "light.fixture_group"):
            hass.states.async_set(forbidden, "on", {"is_hue_group": True})
            try:
                validate_lights(hass, [targets[0], forbidden])
            except ServiceValidationError:
                pass
            else:
                raise AssertionError(f"Unsafe target accepted: {forbidden}")
        hass.states.async_set("light.fixture_unapproved", "on", {"supported_color_modes": ["xy"]})
        try:
            await async_apply_palette(
                hass, restored, palettes[0]["id"], ["light.fixture_unapproved"]
            )
        except ServiceValidationError:
            pass
        else:
            raise AssertionError("Unapproved lamp accepted")
        assert len(calls) == 5
        # Stage 1: real area/entity registries, synthetic state updates, native
        # service dispatch and persisted snapshots (including a Shelly switch).
        area = area_registry.async_get(hass).async_create("Fixture room")
        entities = entity_registry.async_get(hass)
        lamp = entities.async_get_or_create(
            "light",
            "hue",
            "fixture-hue-light",
            config_entry=hass.config_entries.async_get_entry("fixture-hue-config"),
            suggested_object_id="fixture_snapshot_lamp",
        )
        switch = entities.async_get_or_create(
            "switch",
            "shelly",
            "fixture-shelly-light",
            original_name="Fixture Deckenlicht",
        )
        for entry in (lamp, switch):
            entities.async_update_entity(entry.entity_id, area_id=area.id)
        lamp_attrs = {
            "supported_color_modes": ["xy"],
            "color_mode": "xy",
            "xy_color": [0.4, 0.3],
            "brightness": 87,
        }
        hass.states.async_set(lamp.entity_id, "on", lamp_attrs)
        hass.states.async_set(switch.entity_id, "off")
        room_ids = [lamp.entity_id, switch.entity_id]
        await restored.async_set_lights(room_ids)
        assert len(list_rooms(hass, restored)) == 1
        snapshot = (await async_snapshot(hass, restored, area.id, "Fixture evening"))["scene"]
        assert snapshot["lights"][switch.entity_id] == {"on": False}
        assert snapshot["lights"][lamp.entity_id] == {
            "on": True,
            "brightness": 87,
            "xy": [0.4, 0.3],
        }
        hass.states.async_set(lamp.entity_id, "off", lamp_attrs)
        hass.states.async_set(switch.entity_id, "on")

        @callback
        def simulate_device(call):
            calls.append(call)
            entity_id = call.data["entity_id"]
            state = hass.states.get(entity_id)
            attrs = dict(state.attributes)
            attrs.update({key: value for key, value in call.data.items() if key != "entity_id"})
            hass.states.async_set(entity_id, "on" if call.service == "turn_on" else "off", attrs)

        for domain in ("light", "switch"):
            for service in ("turn_on", "turn_off"):
                hass.services.async_register(domain, service, simulate_device)
        result = await async_apply_scene(hass, restored, snapshot["id"])
        assert result == {"applied": room_ids, "skipped": []}
        assert hass.states.get(lamp.entity_id).state == "on"
        assert hass.states.get(lamp.entity_id).attributes["brightness"] == 87
        assert list(hass.states.get(lamp.entity_id).attributes["xy_color"]) == [0.4, 0.3]
        assert hass.states.get(switch.entity_id).state == "off"
        assert calls[-1].domain == "switch"
        assert calls[-1].data == {"entity_id": switch.entity_id}
        reloaded = LichtzentraleStore(hass)
        await reloaded.async_load()
        assert reloaded.data == restored.data
        assert list_rooms(hass, reloaded)[0]["last_scene_id"] == snapshot["id"]

        # Native HA config entry and aiohue 4.9.0 resource/action models.
        # The controller is synthetic: no bridge or external network is contacted.
        hue = entities.async_get_or_create(
            "scene",
            "hue",
            "fixture-hue-scene",
            config_entry=hass.config_entries.async_get_entry("fixture-hue-config"),
        )
        hass.states.async_set(hue.entity_id, "2026-01-01T00:00:00+00:00")
        resource = Scene(
            id=hue.unique_id,
            metadata=SceneMetadata(name="Fixture colors"),
            group=ResourceIdentifier(rid="fixture-group", rtype=ResourceTypes.ROOM),
            actions=[Action(
                target=ResourceIdentifier(rtype=ResourceTypes.LIGHT, rid=lamp.unique_id),
                action=ActionAction(on=OnFeature(on=True), color=ColorFeatureBase(
                    xy=ColorPoint(x=0.55, y=0.35)
                )),
            )],
            speed=0.5,
        )
        config = hass.config_entries.async_get_entry("fixture-hue-config")
        config.runtime_data = SimpleNamespace(
            api=SimpleNamespace(
                scenes={hue.unique_id: resource},
            )
        )
        assert hue_scene_targets(hass, hue.entity_id) == [lamp.entity_id]
        assert hue_scene_preview(hass, hue.entity_id)[0].startswith("#")
        imported = await async_save_scene(
            hass,
            reloaded,
            {
                "kind": "hue",
                "area_id": area.id,
                "name": "Fixture bridge scene",
                "hue_scene": hue.entity_id,
            },
        )
        hass.services.async_register("hue", "activate_scene", capture)
        assert (await async_apply_scene(hass, reloaded, imported["id"]))["applied"] == [
            lamp.entity_id
        ]
        assert calls[-1].domain == "hue"
        assert calls[-1].data == {"entity_id": hue.entity_id, "dynamic": False}
        count = len(calls)
        await reloaded.async_set_lights([switch.entity_id])
        try:
            await async_apply_scene(hass, reloaded, imported["id"])
        except ServiceValidationError:
            pass
        else:
            raise AssertionError("Hue scene ignored revoked light approval")
        resource.actions[0].target.rtype = "grouped_light"
        try:
            hue_scene_targets(hass, hue.entity_id)
        except ServiceValidationError:
            pass
        else:
            raise AssertionError("Hue grouped target accepted")
        assert len(calls) == count
        await async_delete_scene(reloaded, imported["id"])
        final = LichtzentraleStore(hass)
        await final.async_load()
        assert final.data["rooms"][area.id].get("last_scene_id") is None
        # Stage 2: optional bridge, room defaults and local palette runtime.
        await final.async_set_lights(room_ids)
        assert adaptive_status(hass, final)["available"] is False
        al_entry = hass.config_entries.async_get_entry("fixture-adaptive_lighting-config")
        al = entities.async_get_or_create(
            "switch", "adaptive_lighting", "fixture-adaptive-primary", config_entry=al_entry,
        )
        hass.states.async_set(al.entity_id, "on")
        hass.data["adaptive_lighting"] = {
            al_entry.entry_id: {"switch": SimpleNamespace(entity_id=al.entity_id, lights=[lamp.entity_id])}
        }
        for service in ("apply", "set_manual_control"):
            hass.services.async_register("adaptive_lighting", service, capture)
        await async_set_adaptive(
            hass, final, area.id, adaptive_switch=al.entity_id, default_on="adaptive"
        )
        active = DynamicSceneManager(hass, final)
        hass.data.setdefault(DOMAIN, {}).update(store=final, dynamic=active)
        dynamic = await async_save_scene(hass, final, {
            "name": "Fixture dynamic", "area_id": area.id, "kind": "palette",
            "palette_id": "kupfernest", "dynamic": {"enabled": True, "interval": 5, "transition": 2},
        })
        await async_apply_scene(hass, final, dynamic["id"])
        assert hass.states.get(al.entity_id).state == "off"
        assert active.list()[0]["scene_id"] == dynamic["id"]
        before_color = hass.states.get(lamp.entity_id).attributes["xy_color"]
        await asyncio.sleep(5.1)
        assert hass.states.get(lamp.entity_id).attributes["xy_color"] != before_color
        await async_toggle_room(hass, final, area.id, False)
        assert not active.list()
        assert hass.states.get(lamp.entity_id).state == "off"
        await async_toggle_room(hass, final, area.id, True)
        assert hass.states.get(al.entity_id).state == "on"
        assert calls[-1].domain == "adaptive_lighting" and calls[-1].service == "apply"
        assert calls[-1].data["turn_on_lights"] is False
        assert calls[-1].data["lights"] == [lamp.entity_id]
        restored_defaults = LichtzentraleStore(hass)
        await restored_defaults.async_load()
        assert restored_defaults.data["rooms"][area.id]["default_on"] == "adaptive"
        await active.shutdown()
        assert not active.list()
        await final.async_remove()
        assert not path.exists()
    finally:
        await hass.async_stop(force=True)


def main() -> None:
    """Report exact runtime and explicitly bounded verification scope."""
    with TemporaryDirectory(prefix="lichtzentrale-smoke-") as config_dir:
        asyncio.run(run(config_dir))
    print(f"PASS native smoke: Home Assistant {version('homeassistant')}")
    print(
        "Verified: integration imports; native registries/discovery; real Store create, "
        "reload and removal; 12 palettes/4 categories; XY, RGBWW, CT clamp, brightness, "
        "on/off; unavailable skip; allowlist and unrelated-switch/lock/group rejection; "
        "area rooms; XY/brightness and Shelly on/off snapshot restore; last-scene "
        "persistence/reload/deletion; aiohue 4.9.0 scene/action models, color previews and "
        "synthetic Hue controller dispatch; revoked-target and grouped-target rejection; "
        "dynamic timer/color rotation/room-off stop; Adaptive Lighting absence, validated "
        "mapping, scene pause, off/on resume and persisted room defaults."
    )
    print(
        "Not verified here: full config-entry/panel lifecycle, HTTP/WebSocket protocol, "
        "frontend rendering, live Adaptive Lighting integration or physical devices. These are separate test scopes."
    )


if __name__ == "__main__":
    main()
