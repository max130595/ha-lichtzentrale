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
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from zoneinfo import ZoneInfo

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
from homeassistant.core import Context, CoreState, HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry, device_registry, entity_registry
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

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
from custom_components.lichtzentrale.bindings import (  # noqa: E402
    BindingManager,
    list_buttons,
)
from custom_components.lichtzentrale.brightness import BrightnessManager  # noqa: E402
from custom_components.lichtzentrale.config_flow import LichtzentraleConfigFlow  # noqa: E402
from custom_components.lichtzentrale.const import DOMAIN, STORAGE_KEY  # noqa: E402
from custom_components.lichtzentrale.dynamic_scenes import (  # noqa: E402
    DynamicSceneManager,
    async_stop_room,
)
from custom_components.lichtzentrale.lights import list_lights, validate_lights  # noqa: E402
from custom_components.lichtzentrale.motion import MotionManager  # noqa: E402
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
from custom_components.lichtzentrale.schedule_windows import window_is_open  # noqa: E402
from custom_components.lichtzentrale.schedules import ScheduleManager, next_run  # noqa: E402
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
        assert len(palettes) >= 20
        assert {"Herbst", "Winter", "Weihnachten", "Frühling", "Sommer", "Party", "Entspannen", "Romantik"} <= {item["category"] for item in palettes}
        result = await async_apply_palette(hass, restored, palettes[0]["id"], targets, 123)
        assert result == {"applied": targets[:-1], "skipped": ["light.fixture_unavailable"]}
        assert len(calls) == 5
        assert "xy_color" in calls[0].data
        assert "xy_color" in calls[1].data
        assert 3999 <= calls[2].data["color_temp_kelvin"] <= 4000
        assert calls[3].data["brightness"] == 123
        assert "xy_color" not in calls[3].data
        assert "brightness" not in calls[4].data
        assert all(call.data["transition"] == 1 for call in calls[:-1])
        assert "transition" not in calls[-1].data

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
            hass.states.async_set(entity_id, "on" if call.service == "turn_on" else "off", attrs,
                                  context=call.context)

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

        @callback
        def simulate_adaptive(call):
            calls.append(call)
            if call.data.get("turn_on_lights"):
                for entity_id in call.data["lights"]:
                    state = hass.states.get(entity_id)
                    hass.states.async_set(entity_id, "on", dict(state.attributes),
                                          context=Context(id="adapt_lgt_fixture_apply"))

        hass.services.async_register("adaptive_lighting", "apply", simulate_adaptive)
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
        hass.states.async_set(switch.entity_id, "on")
        await async_toggle_room(hass, final, area.id, False)
        assert not active.list()
        assert hass.states.get(lamp.entity_id).state == "off"
        assert final.data["rooms"][area.id]["pre_off_lights"][switch.entity_id] == {"on": True}
        extra = entities.async_get_or_create("light", "synthetic", "fixture-outside-adaptive")
        entities.async_update_entity(extra.entity_id, area_id=area.id)
        hass.states.async_set(extra.entity_id, "off", lamp_attrs)
        await final.async_set_lights([*room_ids, extra.entity_id])
        await async_toggle_room(hass, final, area.id, True)
        assert hass.states.get(al.entity_id).state == "on"
        assert calls[-1].domain == "adaptive_lighting" and calls[-1].service == "apply"
        assert calls[-1].data["turn_on_lights"] is True
        assert calls[-1].data["lights"] == [lamp.entity_id]
        assert hass.states.get(lamp.entity_id).state == "on"
        assert hass.states.get(extra.entity_id).state == "off"
        assert hass.states.get(switch.entity_id).state == "off"
        restored_defaults = LichtzentraleStore(hass)
        await restored_defaults.async_load()
        assert restored_defaults.data["rooms"][area.id]["default_on"] == "adaptive"
        await final.async_update_room(area.id, {"default_on": "last"})
        hass.states.async_set(lamp.entity_id, "on", lamp_attrs)
        hass.states.async_set(switch.entity_id, "on")
        count = len(calls)
        await async_toggle_room(hass, final, area.id, False)
        await async_toggle_room(hass, final, area.id, False)
        restored_off = LichtzentraleStore(hass)
        await restored_off.async_load()
        assert restored_off.data["rooms"][area.id]["pre_off_lights"][lamp.entity_id]["on"]
        assert restored_off.data["rooms"][area.id]["pre_off_lights"][switch.entity_id] == {"on": True}
        assert hass.states.get(switch.entity_id).state == "off"
        result = await async_toggle_room(hass, final, area.id, True)
        assert result["applied"] == room_ids
        assert hass.states.get(lamp.entity_id).attributes["brightness"] == 87
        assert hass.states.get(extra.entity_id).state == "off"
        assert hass.states.get(switch.entity_id).state == "on"
        assert [call.service for call in calls[count:] if call.data.get("entity_id") == switch.entity_id] == ["turn_off", "turn_off", "turn_on"]
        # Switch-only rooms obey direct room commands, even without a prior snapshot.
        switch_area = area_registry.async_get(hass).async_create("Fixture switch room")
        entities.async_update_entity(switch.entity_id, area_id=switch_area.id)
        hass.states.async_set(switch.entity_id, "off")
        assert switch_area.id not in final.data["rooms"]
        assert hass.states.get(switch.entity_id).state == "off"
        assert not next(room for room in list_rooms(hass, final) if room["area_id"] == switch_area.id)["on"]
        await async_toggle_room(hass, final, switch_area.id, True)
        assert hass.states.get(switch.entity_id).state == "on"
        assert next(room for room in list_rooms(hass, final) if room["area_id"] == switch_area.id)["on"]
        await async_toggle_room(hass, final, switch_area.id)
        assert hass.states.get(switch.entity_id).state == "off"
        await async_toggle_room(hass, final, switch_area.id, True)
        await async_toggle_room(hass, final, switch_area.id, False)
        assert hass.states.get(switch.entity_id).state == "off"
        entities.async_update_entity(switch.entity_id, area_id=area.id)
        hass.states.async_set(switch.entity_id, "off")
        await final.async_set_lights(room_ids)
        # Stage 2b: persisted positions, spatial palette/wave, and native-color
        # freeze dispatch without waking off lamps or touching switch entities.
        position = {"cell": [2, 1], "height": "decke"}
        await final.async_set_position(area.id, lamp.entity_id, position)
        positioned = LichtzentraleStore(hass)
        await positioned.async_load()
        assert positioned.data["rooms"][area.id]["positions"][lamp.entity_id] == position
        assert list_rooms(hass, positioned)[0]["positions"][lamp.entity_id] == position
        wave = await async_save_scene(hass, final, {
            "name": "Fixture wave", "area_id": area.id, "kind": "palette",
            "palette_id": "kupfernest", "verteilung": "verlauf_links_rechts",
            "dynamic": {"enabled": True, "interval": 5, "transition": 2, "welle": True},
        })
        await async_apply_scene(hass, final, wave["id"])
        assert hass.states.get(switch.entity_id).state == "off"
        before_color = hass.states.get(lamp.entity_id).attributes["xy_color"]
        await asyncio.sleep(5.1)
        assert hass.states.get(lamp.entity_id).attributes["xy_color"] != before_color
        frozen = dict(hass.states.get(lamp.entity_id).attributes)
        count = len(calls)
        result = await async_stop_room(hass, final, area.id)
        assert result["stopped"] is True and result["applied"] == [lamp.entity_id]
        assert not active.list()
        assert len(calls) == count + 1
        assert calls[-1].domain == "light" and calls[-1].service == "turn_on"
        assert list(calls[-1].data["xy_color"]) == list(frozen["xy_color"])
        assert calls[-1].data["brightness"] == frozen["brightness"]
        # Native bridge dynamics need no local run for the same freeze action.
        result = await async_stop_room(hass, final, area.id)
        assert result["stopped"] is False and result["applied"] == [lamp.entity_id]
        hass.states.async_set(lamp.entity_id, "off", frozen)
        count = len(calls)
        assert (await async_stop_room(hass, final, area.id))["applied"] == []
        assert len(calls) == count
        # Stage 3: genuine HA state-change events, server-persisted bindings,
        # relative dim dispatch and delayed synthetic Hue double release.
        button = entities.async_get_or_create("event", "hue", "fixture-button")
        attributes = {"event_types": ["short_release", "clock_wise"], "event_type": "short_release"}
        hass.states.async_set(button.entity_id, "2026-01-01T00:00:00+00:00", attributes)
        assert "double_short_release" in list_buttons(hass)[0]["event_types"]
        single = await final.async_save_binding({
            "event_entity": button.entity_id, "event_type": "short_release",
            "action": "turn_on_room", "area_id": area.id, "params": {},
        })
        await final.async_save_binding({
            "event_entity": button.entity_id, "event_type": "clock_wise",
            "action": "dim_up", "area_id": area.id, "params": {},
        })
        await final.async_set_room_settings(area.id, {
            "cycle": [snapshot["id"], dynamic["id"]], "default_on": snapshot["id"],
        })
        button_store = LichtzentraleStore(hass)
        await button_store.async_load()
        assert button_store.data == final.data
        bindings = BindingManager(hass, final)
        hass.data[DOMAIN]["bindings"] = bindings
        bindings.start()
        hass.set_state(CoreState.running)
        hass.states.async_set(button.entity_id, "2026-01-01T00:00:01+00:00", attributes)
        await hass.async_block_till_done()
        assert hass.states.get(lamp.entity_id).state == "on"
        assert final.data["rooms"][area.id]["last_scene_id"] == snapshot["id"]
        assert (await bindings.async_next_scene(area.id))["scene_id"] == snapshot["id"]
        assert (await bindings.async_next_scene(area.id))["scene_id"] == dynamic["id"]
        await async_stop_room(hass, final, area.id)
        count = len(calls)
        hass.states.async_set(button.entity_id, "2026-01-01T00:00:02+00:00", {
            **attributes, "event_type": "clock_wise",
        })
        await hass.async_block_till_done()
        assert len(calls) == count + 1
        assert calls[-1].domain == "light"
        assert calls[-1].data == {"entity_id": lamp.entity_id, "brightness_step_pct": 10}
        await final.async_save_binding({
            "event_entity": button.entity_id, "event_type": "double_short_release",
            "action": "turn_off_room", "area_id": area.id, "params": {},
        })
        await final.async_set_double_click(200)
        count = len(calls)
        hass.states.async_set(button.entity_id, "2026-01-01T00:00:03+00:00", attributes)
        await hass.async_block_till_done()
        assert len(calls) == count
        hass.states.async_set(button.entity_id, "2026-01-01T00:00:04+00:00", attributes)
        await hass.async_block_till_done()
        assert hass.states.get(lamp.entity_id).state == "off"
        count = len(calls)
        await asyncio.sleep(0.25)
        await hass.async_block_till_done()
        assert len(calls) == count  # No extra single action after the double.
        hass.states.async_set(button.entity_id, "2026-01-01T00:00:05+00:00", attributes)
        await hass.async_block_till_done()
        await bindings.shutdown()
        await asyncio.sleep(0.25)
        await hass.async_block_till_done()
        assert len(calls) == count  # Unload cancels the pending single.
        await final.async_delete_binding(single["id"])
        assert len(final.data["bindings"]) == 2
        # Stage 3A: explicit cross-room light and switch selection, persisted
        # pre-off values and optional per-light dim through native button events.
        entities.async_update_entity(switch.entity_id, area_id=switch_area.id)
        hass.states.async_set(lamp.entity_id, "on", lamp_attrs)
        hass.states.async_set(switch.entity_id, "off")
        selected = await final.async_save_binding({
            "event_entity": button.entity_id, "event_type": "short_release",
            "action": "toggle_lights", "area_id": None,
            "params": {"entity_ids": [lamp.entity_id, switch.entity_id]},
        })
        assert selected["area_id"] is None
        selected_manager = BindingManager(hass, final)
        for binding in final.data["bindings"]:
            if binding["id"] != selected["id"]:
                await final.async_delete_binding(binding["id"])
        hass.data[DOMAIN]["bindings"] = selected_manager
        selected_manager.start()
        hass.states.async_set(button.entity_id, "2026-01-01T00:00:06+00:00", attributes)
        await hass.async_block_till_done()
        assert hass.states.get(lamp.entity_id).state == "off"
        assert hass.states.get(switch.entity_id).state == "off"
        off_store = LichtzentraleStore(hass)
        await off_store.async_load()
        assert off_store.data["settings"]["last_light_states"][lamp.entity_id]["brightness"] == 87
        hass.states.async_set(lamp.entity_id, "off", {"supported_color_modes": ["xy"]})
        hass.states.async_set(button.entity_id, "2026-01-01T00:00:07+00:00", attributes)
        await hass.async_block_till_done()
        assert hass.states.get(lamp.entity_id).state == "on"
        assert hass.states.get(lamp.entity_id).attributes["brightness"] == 87
        assert list(hass.states.get(lamp.entity_id).attributes["xy_color"]) == [0.4, 0.3]
        assert hass.states.get(switch.entity_id).state == "on"
        await final.async_save_binding({
            "event_entity": button.entity_id, "event_type": "clock_wise",
            "action": "dim_up", "area_id": None,
            "params": {"entity_ids": [lamp.entity_id, switch.entity_id]},
        })
        count = len(calls)
        hass.states.async_set(button.entity_id, "2026-01-01T00:00:08+00:00", {
            **attributes, "event_type": "clock_wise",
        })
        await hass.async_block_till_done()
        assert len(calls) == count + 1
        assert calls[-1].data == {"entity_id": lamp.entity_id, "brightness_step_pct": 10}
        await selected_manager.shutdown()
        # Native motion dispatch uses the same synthetic lamp/switch capture.
        motion_sensor = "binary_sensor.fixture_motion"
        hass.states.async_set(motion_sensor, "off", {"device_class": "motion"})
        await final.async_set_motion(area.id, {
            "enabled": True, "sensor_entity_ids": [motion_sensor], "timeout_seconds": 60,
            "dim_before_off": True, "lux_sensor_entity_id": None, "lux_below": None,
            "windows": [{"start": {"type": "time", "value": "00:00"},
                         "end": {"type": "time", "value": "00:00"},
                         "action": {"type": "lights", "entity_ids": [lamp.entity_id, switch.entity_id],
                                    "brightness": 140}}],
        })
        motion = MotionManager(hass, final)
        hass.data[DOMAIN]["motion"] = motion
        motion.start()
        hass.states.async_set(motion_sensor, "on", {"device_class": "motion"})
        await hass.async_block_till_done()
        assert set(motion.status(area.id)["active_targets"]) == {lamp.entity_id, switch.entity_id}
        assert hass.states.get(lamp.entity_id).attributes["brightness"] == 140
        hass.states.async_set(motion_sensor, "off", {"device_class": "motion"})
        await hass.async_block_till_done()
        count = len(calls)
        await motion._expire(area.id, dim=True)
        await hass.async_block_till_done()
        assert len(calls) == count + 1 and calls[-1].domain == "light"
        assert hass.states.get(lamp.entity_id).attributes["brightness"] == 76
        hass.states.async_set(motion_sensor, "on", {"device_class": "motion"})
        await hass.async_block_till_done()
        assert hass.states.get(lamp.entity_id).attributes["brightness"] == 140
        hass.states.async_set(lamp.entity_id, "on", {**lamp_attrs, "brightness": 100})
        await hass.async_block_till_done()
        assert motion.status(area.id)["paused"]
        hass.states.async_set(motion_sensor, "off", {"device_class": "motion"})
        await hass.async_block_till_done()
        count = len(calls)
        await motion._expire(area.id)
        assert len(calls) == count and not motion.status(area.id)["paused"]
        motion_store = LichtzentraleStore(hass)
        await motion_store.async_load()
        assert motion_store.data["rooms"][area.id]["motion"]["enabled"]
        # Review regressions: automatic updates must not cancel vacancy shutdown.
        motion_config = final.data["rooms"][area.id]["motion"]
        motion_config["dim_before_off"] = False
        motion_config["windows"][0]["action"] = {"type": "adaptive"}
        await final.async_set_motion(area.id, motion_config)
        hass.states.async_set(motion_sensor, "on", {"device_class": "motion"})
        await hass.async_block_till_done()
        assert motion.status(area.id)["active_targets"] == [lamp.entity_id]
        hass.states.async_set(lamp.entity_id, "on", {**lamp_attrs, "brightness": 170},
                              context=Context(id="adapt_lgt_fixture_periodic"))
        await hass.async_block_till_done()
        assert not motion.status(area.id)["paused"]
        hass.states.async_set(motion_sensor, "off", {"device_class": "motion"})
        await hass.async_block_till_done()
        motion._runtime(area.id)["timers"][-1]._callback()
        await hass.async_block_till_done()
        assert hass.states.get(lamp.entity_id).state == "off"
        motion_config["windows"][0]["action"] = {"type": "scene", "scene_id": dynamic["id"]}
        await final.async_set_motion(area.id, motion_config)
        hass.states.async_set(motion_sensor, "on", {"device_class": "motion"})
        await hass.async_block_till_done()
        assert active.list()
        state = hass.states.get(lamp.entity_id)
        hass.states.async_set(lamp.entity_id, "on", {
            **state.attributes, "brightness": 150, "xy_color": [0.3, 0.4],
        })
        await hass.async_block_till_done()
        assert not motion.status(area.id)["paused"]
        hass.states.async_set(motion_sensor, "off", {"device_class": "motion"})
        await hass.async_block_till_done()
        motion._runtime(area.id)["timers"][-1]._callback()
        await hass.async_block_till_done()
        assert hass.states.get(lamp.entity_id).state == "off"
        assert not active.list()
        await motion.shutdown()
        # Stage four: native scheduler dispatch and persistence, no real devices.
        schedules = ScheduleManager(hass, final)
        hass.data[DOMAIN]["schedules"] = schedules
        schedules.start()
        await hass.async_block_till_done()
        plan = await final.async_save_schedule({
            "name": "Synthetic scheduled fade", "enabled": False,
            "trigger": {"type": "time", "value": "20:30"},
            "condition": {"weekdays": list(range(7)), "person_entity_ids": [],
                          "light_state": "any"},
            "action": {"type": "lights", "entity_ids": [lamp.entity_id, switch.entity_id],
                       "on": True, "brightness": 111}, "transition": 1800,
        })
        assert plan["condition"]["time_window"] is None
        assert next_run(hass, plan) is not None
        count = len(calls)
        result = await schedules.async_test(plan["id"])
        assert result["condition_met"] and set(result["applied"]) == {lamp.entity_id, switch.entity_id}
        recent = calls[count:]
        assert any(call.domain == "light" and call.data.get("brightness") == 111 for call in recent)
        assert all(set(call.data) == {"entity_id"} for call in recent if call.domain == "switch")
        assert not schedules.list_schedules()[0]["enabled"]
        enabled = await final.async_set_schedule_enabled(plan["id"], True)
        assert enabled["enabled"] and schedules.list_schedules()[0]["next_run"]
        lux_id = "sensor.fixture_schedule_illuminance"
        hass.states.async_set(lux_id, "20", {"device_class": "illuminance", "unit_of_measurement": "lx"})
        lux_plan = await final.async_save_schedule({
            **plan, "trigger": {"type": "lux", "sensor_entity_id": lux_id,
                               "comparison": "below", "threshold": 30, "duration_seconds": 300},
            "enabled": True,
            "condition": {**plan["condition"], "time_window": {
                "after": {"type": "time", "value": "00:00"},
                "before": {"type": "time", "value": "00:00"}}},
        })
        assert schedules.list_schedules()[0]["next_run"]
        runtime = schedules._state(lux_plan["id"])
        schedules._fire(lux_plan["id"], runtime["generation"], runtime["timer_token"])
        await hass.async_block_till_done()
        assert final.data["settings"]["schedule_last_run_dates"][lux_plan["id"]] == dt_util.now().date().isoformat()
        count = len(calls)
        schedules._fire(lux_plan["id"], runtime["generation"], runtime["timer_token"])
        await hass.async_block_till_done()
        assert len(calls) == count
        overnight = {"after": {"type": "time", "value": "22:00"},
                     "before": {"type": "time", "value": "06:00"}}
        assert window_is_open(hass, overnight, datetime(2026, 11, 2, 23, tzinfo=ZoneInfo("UTC")))
        assert not window_is_open(hass, overnight, datetime(2026, 11, 2, 12, tzinfo=ZoneInfo("UTC")))
        await final.async_set_schedule_enabled(lux_plan["id"], False)
        assert schedules.list_schedules()[0]["next_run"] is None
        saved_schedules = LichtzentraleStore(hass)
        await saved_schedules.async_load()
        assert saved_schedules.data["schedules"][0]["trigger"]["duration_seconds"] == 300
        await final.async_delete_schedule(plan["id"])
        assert not schedules.list_schedules()
        await schedules.shutdown()
        await active.shutdown()
        assert not active.list()
        # Stage five: native service events, lux state and persistent stage settings.
        # Dedicated synthetic room: no inherited scenes, motion or adaptive mapping.
        brightness_area = area_registry.async_get(hass).async_create("Fixture brightness room")
        brightness_lamp = entities.async_get_or_create("light", "synthetic", "fixture-basic-lux-light")
        entities.async_update_entity(brightness_lamp.entity_id, area_id=brightness_area.id)
        brightness_lux = "sensor.fixture_basic_lux"
        lux_attrs = {"device_class": "illuminance", "unit_of_measurement": "lx"}
        hass.states.async_set(brightness_lamp.entity_id, "off", {"supported_color_modes": ["brightness"]})
        hass.states.async_set(brightness_lux, "10", lux_attrs)
        await final.async_set_lights([*final.data["settings"]["light_entity_ids"], brightness_lamp.entity_id])
        brightness_config = await final.async_set_brightness(brightness_area.id, {
            "enabled": True, "lux_sensor_entity_id": brightness_lux,
            "target_lux": 100, "hysteresis_lux": 10, "min_interval_seconds": 180,
            "time_window": None, "person_entity_ids": [],
            "stages": [{"entity_ids": [brightness_lamp.entity_id], "brightness": 135}],
        })
        await hass.async_block_till_done()
        brightness = BrightnessManager(hass, final)
        hass.data[DOMAIN]["brightness"] = brightness
        brightness.start()
        try:
            count = len(calls)
            await brightness.async_evaluate(brightness_area.id)
            await hass.async_block_till_done()
            assert len(calls) == count + 1
            assert calls[-1].domain == "light" and calls[-1].data["brightness"] == 135
            assert hass.states.get(brightness_lamp.entity_id).state == "on"
            assert brightness.status(brightness_area.id)["active_stage"] == 1
            assert brightness.status(brightness_area.id)["learned_lux"] == [None]
            assert not brightness.status(brightness_area.id)["paused"]
            # The minimum interval prevents immediate removal after sudden brightness.
            hass.states.async_set(brightness_lux, "500", lux_attrs)
            await hass.async_block_till_done()
            await brightness.async_evaluate(brightness_area.id)
            assert len(calls) == count + 1
            # Stufe 5a: target-only edits retain owned stages and learned light.
            brightness._runtime(brightness_area.id)["pending"]["time"] -= 10
            hass.states.async_set(brightness_lux, "50", lux_attrs)
            await hass.async_block_till_done()
            brightness_config = await final.async_set_brightness(
                brightness_area.id, {**brightness_config, "target_lux": 120})
            assert brightness.status(brightness_area.id)["active_stage"] == 1
            assert brightness.status(brightness_area.id)["learned_lux"] == [40]
            brightness._runtime(brightness_area.id)["last_change"] -= 180
            hass.states.async_set(brightness_lux, "500", lux_attrs)
            await hass.async_block_till_done()
            assert calls[-1].service == "turn_off"
            assert hass.states.get(brightness_lamp.entity_id).state == "off"
            assert brightness.status(brightness_area.id)["active_stage"] == 0
            brightness._runtime(brightness_area.id)["last_change"] -= 180
            hass.states.async_set(brightness_lux, "10", lux_attrs)
            await hass.async_block_till_done()
            assert brightness.status(brightness_area.id)["active_stage"] == 1
            await final.async_set_brightness_enabled(brightness_area.id, False)
            assert hass.states.get(brightness_lamp.entity_id).state == "off"
            await final.async_set_brightness_enabled(brightness_area.id, True)
            brightness._runtime(brightness_area.id)["last_change"] -= 180
            await brightness.async_evaluate(brightness_area.id)
            await hass.async_block_till_done()
            assert brightness.status(brightness_area.id)["active_stage"] == 1
            count = len(calls)
            await final.async_set_brightness_enabled(brightness_area.id, False, keep_lights=True)
            assert len(calls) == count
            assert hass.states.get(brightness_lamp.entity_id).state == "on"
            assert brightness.status(brightness_area.id)["active_stage"] == 0
            await final.async_set_brightness_enabled(brightness_area.id, True)
            # A real native service event, even without a changed on/off state, pauses.
            await hass.services.async_call("light", "turn_on", {
                "entity_id": brightness_lamp.entity_id, "brightness": 95,
            }, blocking=True, context=Context())
            await hass.async_block_till_done()
            assert brightness.status(brightness_area.id)["paused"]
            count = len(calls)
            hass.states.async_set(brightness_lux, "0", lux_attrs)
            await hass.async_block_till_done()
            await brightness.async_evaluate(brightness_area.id)
            assert len(calls) == count
            persisted_brightness = LichtzentraleStore(hass)
            await persisted_brightness.async_load()
            room = persisted_brightness.data["rooms"][brightness_area.id]
            assert room["brightness"] == brightness_config
            assert room["brightness_learned"] == [40]
            assert "paused" not in room["brightness"]
            await final.async_set_brightness_enabled(brightness_area.id, False)
        finally:
            await brightness.shutdown()
        # Stufe 5b: a cross-room zone and day state use the real native Store.
        from custom_components.lichtzentrale.automatic_state import current_action
        from custom_components.lichtzentrale.target_actions import async_execute_action

        zone = await final.async_save_zone({
            "name": "Synthetic shared evening", "entity_ids": [lamp.entity_id, brightness_lamp.entity_id],
        })
        zone_area = "zone:" + zone["id"]
        night = await async_save_scene(hass, final, {
            "name": "Synthetic low light", "area_id": zone_area, "kind": "snapshot", "night": True,
            "lights": {lamp.entity_id: {"on": True, "brightness": 30},
                       brightness_lamp.entity_id: {"on": True, "brightness": 30}},
        })
        await async_execute_action(hass, final, {"type": "night", "area_ids": [zone_area]}, automatic=True)
        assert current_action(hass, final, zone_area)["type"] == "night"
        await async_execute_action(hass, final, {"type": "full_brightness", "area_ids": [zone_area]})
        assert current_action(hass, final, zone_area)["type"] == "night"
        await async_execute_action(hass, final, {"type": "return_auto", "area_ids": [zone_area]})
        assert hass.states.get(brightness_lamp.entity_id).attributes["brightness"] == 30
        assert final.data["rooms"][zone_area]["last_scene_id"] == night["id"]
        await async_execute_action(hass, final, {"type": "off", "area_ids": [zone_area]}, automatic=True)
        after_restart = LichtzentraleStore(hass)
        await after_restart.async_load()
        assert after_restart.data["zones"] == final.data["zones"]
        assert current_action(hass, after_restart, zone_area)["type"] == "off"
        await async_execute_action(hass, after_restart, {"type": "full_brightness", "area_ids": [zone_area]})
        await async_execute_action(hass, after_restart, {"type": "return_auto", "area_ids": [zone_area]})
        assert all(hass.states.get(e).state == "off" for e in zone["entity_ids"])
        # Review fixes: a room inherits only its overlap with a zone, including
        # device brightness rounding. The unrelated zone lamp stays untouched.
        evening = await async_save_scene(hass, after_restart, {
            "name": "Synthetic inherited evening", "area_id": zone_area, "kind": "snapshot",
            "lights": {lamp.entity_id: {"on": True, "brightness": 130},
                       brightness_lamp.entity_id: {"on": True, "brightness": 85}},
        })
        await async_execute_action(hass, after_restart, {"type": "scene", "scene_id": evening["id"]}, automatic=True)
        await async_save_scene(hass, after_restart, {
            "name": "Synthetic corridor night", "area_id": brightness_area.id, "kind": "snapshot", "night": True,
            "lights": {brightness_lamp.entity_id: {"on": True, "brightness": 30}},
        })
        assert current_action(hass, after_restart, brightness_area.id) is None
        await hass.services.async_call("light", "turn_on", {"entity_id": lamp.entity_id, "brightness": 145}, blocking=True)
        await async_execute_action(hass, after_restart, {"type": "night_auto", "area_id": brightness_area.id})
        night_state = hass.states.get(brightness_lamp.entity_id)
        assert night_state.attributes["brightness"] == 30
        hass.states.async_set(brightness_lamp.entity_id, "on", {**night_state.attributes, "brightness": 33})
        count = len(calls)
        await async_execute_action(hass, after_restart, {"type": "night_auto", "area_id": brightness_area.id})
        assert hass.states.get(brightness_lamp.entity_id).attributes["brightness"] == 85
        assert hass.states.get(lamp.entity_id).attributes["brightness"] == 145
        assert {call.data["entity_id"] for call in calls[count:]} == {brightness_lamp.entity_id}
        # Persisted wildcard learning matches any speed, never the wrong direction.
        dial_attributes = {"event_types": ["dial_rotate"], "event_type": "dial_rotate", "direction": "right", "speed": 1}
        hass.states.async_set(button.entity_id, "2026-01-02T00:00:00+00:00", dial_attributes)
        await after_restart.async_save_binding({
            "event_entity": button.entity_id, "event_type": "dial_rotate",
            "event_attributes": {"direction": "right", "speed": 1}, "ignored_event_attributes": ["speed"],
            "action": "turn_off_room", "area_id": brightness_area.id, "params": {},
        })
        learned_store = LichtzentraleStore(hass)
        await learned_store.async_load()
        learned_manager = BindingManager(hass, learned_store)
        learned_manager.start()
        try:
            count = len(calls)
            hass.states.async_set(button.entity_id, "2026-01-02T00:00:01+00:00", {**dial_attributes, "direction": "left", "speed": 12})
            await hass.async_block_till_done()
            assert len(calls) == count
            hass.states.async_set(button.entity_id, "2026-01-02T00:00:02+00:00", {**dial_attributes, "speed": 12})
            await hass.async_block_till_done()
            assert hass.states.get(brightness_lamp.entity_id).state == "off"
            assert hass.states.get(lamp.entity_id).attributes["brightness"] == 145
            assert {call.data["entity_id"] for call in calls[count:]} == {brightness_lamp.entity_id}
        finally:
            await learned_manager.shutdown()
        # Stage 5c uses the real target-version Store and native service dispatch.
        custom = await after_restart.async_save_palette({
            "name": "Synthetic custom autumn", "category": "Herbst",
            "preview": ["#FF9A2E", "#FF6A13", "#FFC247"], "bri": 150, "tempo": "slow",
        })
        authored = await async_save_scene(hass, after_restart, {
            "name": "Synthetic authored scene", "area_id": brightness_area.id,
            "kind": "palette", "palette_id": custom["id"], "brightness": 160,
            "dynamic": {"enabled": True, "tempo": "slow"},
            "lamp_settings": {brightness_lamp.entity_id: {"mode": "cycle", "brightness": 31}},
            "wave_order": [brightness_lamp.entity_id],
        })
        reload_5c = LichtzentraleStore(hass)
        await reload_5c.async_load()
        assert reload_5c.data["palettes"][-1]["id"] == custom["id"]
        assert next(item for item in reload_5c.data["scenes"] if item["id"] == authored["id"])["lamp_settings"][brightness_lamp.entity_id]["brightness"] == 31
        try:
            await reload_5c.async_delete_palette(custom["id"])
        except ServiceValidationError as error:
            assert authored["name"] in str(error)
        else:
            raise AssertionError("Referenced custom palette deleted")
        native_dynamic = DynamicSceneManager(hass, reload_5c)
        hass.data[DOMAIN]["dynamic"] = native_dynamic
        await async_apply_scene(hass, reload_5c, authored["id"])
        assert hass.states.get(brightness_lamp.entity_id).attributes["brightness"] == 31
        assert brightness_area.id in reload_5c.data["active_dynamic"]
        await native_dynamic.shutdown()
        restart_5c = LichtzentraleStore(hass)
        await restart_5c.async_load()
        resumed = DynamicSceneManager(hass, restart_5c)
        hass.data[DOMAIN]["dynamic"] = resumed
        await resumed.restore(wait_for_start=False)
        assert brightness_area.id in resumed.active
        await resumed.stop(brightness_area.id)
        assert brightness_area.id not in restart_5c.data["active_dynamic"]
        await resumed.shutdown()
        from custom_components.lichtzentrale.bindings import validate_binding
        fixed = validate_binding(hass, restart_5c, {
            "event_entity": button.entity_id, "event_type": "dial_rotate", "action": "turn_on_lights",
            "area_id": None, "params": {"entity_ids": [brightness_lamp.entity_id],
                                        "on_behavior": {"mode": "brightness", "brightness": 255}},
        })
        await BindingManager(hass, restart_5c)._action(fixed, Context())
        assert hass.states.get(brightness_lamp.entity_id).attributes["brightness"] == 255
        time_on = validate_binding(hass, restart_5c, {
            "event_entity": button.entity_id, "event_type": "dial_rotate", "action": "turn_on_lights",
            "area_id": None, "params": {"entity_ids": [brightness_lamp.entity_id],
                "on_behavior": {"mode": "time", "windows": [{
                    "window": {"after": {"type": "time", "value": "00:00"},
                               "before": {"type": "time", "value": "00:00"}},
                    "mode": "brightness", "brightness": 76, "color_temp_kelvin": 2200,
                }]}},
        })
        await BindingManager(hass, restart_5c)._action(time_on, Context())
        assert hass.states.get(brightness_lamp.entity_id).attributes["brightness"] == 76
        seasonal = await async_save_scene(hass, restart_5c, {
            "name": "Synthetic seasonal scene", "area_id": brightness_area.id,
            "kind": "seasonal", "seasonal": {"scenes": {"autumn": authored["id"]}},
        })
        from custom_components.lichtzentrale.seasonal_scenes import resolve_scene
        resolved, info = resolve_scene(hass, restart_5c, seasonal,
                                      now=datetime(2026, 7, 2, 12, tzinfo=ZoneInfo("UTC")))
        assert resolved["id"] == authored["id"] and info["resolution_note"]
        seasonal_run = DynamicSceneManager(hass, restart_5c)
        hass.data[DOMAIN]["dynamic"] = seasonal_run
        result = await async_apply_scene(hass, restart_5c, seasonal["id"])
        assert result["resolved_scene_id"] == authored["id"]
        assert restart_5c.data["rooms"][brightness_area.id]["last_scene_id"] == seasonal["id"]
        assert restart_5c.data["active_dynamic"][brightness_area.id]["scene_id"] == authored["id"]
        await seasonal_run.stop(brightness_area.id)
        await seasonal_run.shutdown()
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
        "reload and removal; at least 20 palettes/8 requested categories; XY, RGBWW, CT clamp, brightness, "
        "on/off; unavailable skip; allowlist and unrelated-switch/lock/group rejection; "
        "area rooms; XY/brightness and Shelly on/off snapshot restore; last-scene "
        "persistence/reload/deletion; aiohue 4.9.0 scene/action models, color previews and "
        "synthetic Hue controller dispatch; revoked-target and grouped-target rejection; "
        "dynamic timer/color rotation/room-off stop; Adaptive Lighting absence, validated "
        "mapping, scene pause, off/on resume and persisted room defaults; persisted positions, "
        "spatial wave timer, palette switch exclusion, pre-off lamp/switch restore, switch-only "
        "room commands/status, adaptive subset-only on, "
        "current-color freeze with and without local run, no off-lamp wake; runtime event "
        "discovery, binding/cycle/default persistence, native timestamp event dispatch, "
        "room-on scene, scene cycling, relative dim service payload, double release and unload cancellation; "
        "selected cross-room lamp/switch toggles, persisted pre-off color restore and selected dim; motion sensor activation, selected lamp/switch "
        "ownership, dim/restore without switch dim, manual pause, empty-room release and motion persistence; parentless adapt_lgt updates and contextless "
        "motion-owned dynamic colors preserve vacancy shutdown; schedule time calculation, manual selected-light/switch "
        "dispatch, bounded transition selection, atomic save/enable/delete, Lux timer registration and cancellation, "
        "schedule persistence/reload/unload, overnight windows and persisted daily lux limits; "
        "brightness-stage native dispatch/payload, minimum interval, manual-service pause, "
        "configuration and learning persistence, target-edit ownership/bright-light removal, "
        "disable with/without keep_lights and unload; cross-room zones, night scene tagging, "
        "full neutral brightness, manual state preservation, day-state disk reload and return to off; room night/rounded recall from zone restricted to shared lamps; persisted dial direction matching with wildcard speed; Stufe5c custom palette disk reload/reference protection, per-lamp brightness, dynamic persisted shutdown/restart/stop, fixed 100-percent and time-window button-on; seasonal resolution/fallback with concrete dynamic persistence and wrapper last-scene identity."
    )
    print(
        "Not verified here: full config-entry/panel lifecycle, HTTP/WebSocket protocol, "
        "frontend rendering, live Adaptive Lighting integration or physical devices. These are separate test scopes."
    )


if __name__ == "__main__":
    main()
