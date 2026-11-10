# Geändert für Lichtzentrale
"""Native isolated HA 2026.11 smoke for vacation planning and lamp ownership.

Temporary Store, registries, real services/state events, and actual runtime timers.
Synthetic entities and a public city location only; no physical devices or mocks.
The five-minute trial is started, its deadline checked, and explicitly stopped;
this smoke does NOT wait five minutes or claim timeout completion coverage.
Run: .venv-target/bin/python scripts/smoke_stage6.py
"""

import asyncio
import sys
from copy import deepcopy
from datetime import datetime, timedelta
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntries
from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.helpers import area_registry, device_registry, entity_registry
from homeassistant.util import dt as dt_util

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from custom_components.lichtzentrale.const import DOMAIN
from custom_components.lichtzentrale.storage import LichtzentraleStore
from custom_components.lichtzentrale.vacation import VacationManager
from custom_components.lichtzentrale.vacation_config import default_vacation_config
from custom_components.lichtzentrale.vacation_history import async_learn_history
from custom_components.lichtzentrale.vacation_planner import build_plan

ZONE = ZoneInfo("Europe/Berlin")


async def run(directory):
    hass = HomeAssistant(directory)
    hass.config_entries = ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    manager = None
    try:
        # Public Berlin city coordinates, unrelated to any user's installation.
        hass.config.latitude, hass.config.longitude = 52.52, 13.405
        hass.config.elevation, hass.config.time_zone = 34, "Europe/Berlin"
        dt_util.set_default_time_zone(ZONE)
        await area_registry.async_load(hass)
        device_registry.async_setup(hass)
        await device_registry.async_load(hass)
        await entity_registry.async_load(hass)
        store = LichtzentraleStore(hass)
        await store.async_load()
        assert store.data["vacation"]["enabled"] is False
        assert store.data["vacation"]["until"] is None
        assert store.data["vacation"]["config"] == default_vacation_config()
        calls, notifications = [], []

        @callback
        def capture(call):
            calls.append(call)
            entity = call.data["entity_id"]
            state = hass.states.get(entity)
            attributes = {**state.attributes, **{key: value for key, value in call.data.items()
                                                if key != "entity_id"}}
            hass.states.async_set(entity, "off" if call.service == "turn_off" else "on",
                                  attributes, context=call.context)

        @callback
        def notify(call):
            notifications.append(call.data["message"])

        for service in ("turn_on", "turn_off"):
            hass.services.async_register("light", service, capture)
        hass.services.async_register("notify", "synthetic_stage6", notify)
        lamp, preexisting = "light.fixture_6_simulated", "light.fixture_6_preexisting"
        attributes = {"supported_color_modes": ["brightness"], "color_mode": "brightness",
                      "brightness": 80}
        for entity, state in ((lamp, "off"), (preexisting, "on")):
            hass.states.async_set(entity, state, attributes, context=Context())
        await store.async_set_lights([lamp, preexisting])
        zone = await store.async_save_zone({"name": "Synthetic stage 6", "entity_ids": [lamp, preexisting]})
        area = "zone:" + zone["id"]
        config = default_vacation_config()
        config["rooms"] = [{"area_id": area, "type": "living", "weight": 1,
                            "on_behavior": {"mode": "brightness", "brightness": 100}}]
        await store.async_update_vacation({"config": config})
        restored = LichtzentraleStore(hass)
        await restored.async_load()
        assert restored.data["vacation"]["config"] == config
        assert restored.data["vacation"]["enabled"] is False
        store = restored
        print("PASS native Store: defaults disabled; selected config survives disk reload")

        winter = datetime(2026, 12, 1, 5, tzinfo=ZONE)
        plan = build_plan(hass, config, winter, seed=42)
        assert plan and plan == build_plan(hass, config, winter, seed=42)
        assert plan != build_plan(hass, config, winter, seed=43)
        assert all(datetime.fromisoformat(item["start"]) >= winter for item in plan)
        morning_config = deepcopy(config)
        morning_config["morning"]["enabled"] = True
        dark = build_plan(hass, morning_config, winter, seed=42)
        bright = build_plan(hass, morning_config, datetime(2026, 6, 1, 5, tzinfo=ZONE), seed=42)
        assert any(item["section"] == "morning" for item in dark)
        assert not any(item["section"] == "morning" for item in bright)
        morning_config["learn_history"] = True
        assert await async_learn_history(hass, store, morning_config, winter) == {}
        print("PASS native planner: fixed seed, real Astral winter dark/summer bright morning, no-Recorder fallback")

        manager = VacationManager(hass, store)
        hass.data.setdefault(DOMAIN, {}).update(store=store, vacation=manager)
        manager.start()
        await hass.async_block_till_done()
        before = dt_util.utcnow()
        status = await manager.async_test()
        await hass.async_block_till_done()
        deadline = datetime.fromisoformat(status["test_until"])
        assert before + timedelta(minutes=5) <= deadline <= dt_util.utcnow() + timedelta(minutes=5)
        assert status["testing"] and status["paused"] and not status["enabled"]
        assert manager._timer is not None and not manager._timer.cancelled()
        assert len(status["plan"]) == 1
        entry = status["plan"][0]
        assert datetime.fromisoformat(entry["end"]) - datetime.fromisoformat(entry["start"]) == timedelta(minutes=5)
        assert [(call.service, call.data["entity_id"]) for call in calls] == [("turn_on", lamp)]
        assert hass.states.get(lamp).state == "on"
        assert hass.states.get(preexisting).attributes["brightness"] == 80
        # Real state events with fresh contexts model a short Zigbee reconnect.
        # The same ON state must retain ownership until the interval is stopped.
        owned_attributes = dict(hass.states.get(lamp).attributes)
        for transient in ("unavailable", "unknown"):
            hass.states.async_set(lamp, transient, {}, context=Context())
            await hass.async_block_till_done()
            assert lamp in manager._owned
        hass.states.async_set(lamp, "on", owned_attributes, context=Context())
        await hass.async_block_till_done()
        assert lamp in manager._owned
        await manager.async_set_enabled(False)
        await hass.async_block_till_done()
        assert [(call.service, call.data["entity_id"]) for call in calls] == [("turn_on", lamp), ("turn_off", lamp)]
        assert hass.states.get(lamp).state == "off" and hass.states.get(preexisting).state == "on"
        assert not manager.paused and manager._timer is None
        print("PASS native trial: real five-minute deadline/timer, explicit stop, only newly-on owned lamp off")
        print("PASS native K1: ON/unavailable/unknown/ON with new contexts retains ownership and switches off")

        calls.clear()
        await manager.async_test()
        await hass.async_block_till_done()
        calls.clear()
        await manager.manual_targets(area_id=area)
        assert not calls and area in manager.status()["excluded_rooms"]
        await manager.async_set_enabled(False)
        await hass.async_block_till_done()
        assert not calls and hass.states.get(lamp).state == "on"
        print("PASS native button release: no commands; explicit stop leaves manually released room untouched")

        hass.states.async_set(lamp, "off", attributes, context=Context())
        await hass.async_block_till_done()
        calls.clear()
        await manager.async_test()
        await hass.async_block_till_done()
        assert hass.states.get(lamp).state == "on"
        calls.clear()
        await store.async_set_lights([preexisting])
        await manager.async_set_enabled(False)
        await hass.async_block_till_done()
        assert not calls and hass.states.get(lamp).state == "on"
        assert hass.states.get(preexisting).state == "on"
        print("PASS native revoked grant: no shutdown commands to removed lamp or preexisting-on lamp")

        # K2 uses actual native service dispatch with synthetic due section
        # records. Ten-minute scheduling and restart timing are unit-tested;
        # this smoke does not wait ten real minutes or patch HA's clock.
        outside = "light.fixture_6_outside"
        for entity in (lamp, preexisting, outside):
            hass.states.async_set(entity, "on", attributes, context=Context())
        await store.async_set_lights([lamp, preexisting, outside])
        await manager.async_save_config(config)
        await manager.async_set_enabled(True)
        await hass.async_block_till_done()
        assert not manager._owned
        now = dt_util.utcnow()
        section_id = f"{dt_util.as_local(now).date().isoformat()}:evening"
        manager._sections = {section_id: {
            "section": "evening", "start": (now - timedelta(hours=1)).isoformat(),
            "end": (now - timedelta(seconds=1)).isoformat(),
            "end_done": False, "retry_done": False,
        }}
        calls.clear()
        async with manager._lock:
            await manager._safety_tick(now)
        await hass.async_block_till_done()
        assert {call.data["entity_id"] for call in calls} == {lamp, preexisting}
        assert all(call.service == "turn_off" for call in calls)
        assert hass.states.get(outside).state == "on"
        assert manager._sections[section_id]["end_done"]
        assert not manager._sections[section_id]["retry_done"]
        hass.states.async_set(preexisting, "on", attributes, context=Context())
        await hass.async_block_till_done()
        now = dt_util.utcnow()
        manager._sections[section_id]["end"] = (now - timedelta(minutes=10, seconds=1)).isoformat()
        calls.clear()
        async with manager._lock:
            await manager._safety_tick(now)
        assert [(call.service, call.data["entity_id"]) for call in calls] == [("turn_off", preexisting)]
        assert manager._sections[section_id]["retry_done"]
        hass.states.async_set(preexisting, "on", attributes, context=Context())
        await hass.async_block_till_done()
        calls.clear()
        async with manager._lock:
            await manager._safety_tick(dt_util.utcnow())
        assert not calls and hass.states.get(preexisting).state == "on"
        await manager.async_set_enabled(False)
        print("PASS native K2: unknown-ownership selected lamps off, outside untouched, due retry once only")

        # Empty configured selection permits an enabled state without real light
        # actions; the synthetic named notification service is still exercised.
        notification_config = default_vacation_config()
        notification_config["notify_service"] = "notify.synthetic_stage6"
        await manager.async_save_config(notification_config)
        calls.clear()
        await manager.async_set_enabled(True)
        restored = LichtzentraleStore(hass)
        await restored.async_load()
        assert restored.data["vacation"]["enabled"] is True
        await manager.async_set_enabled(False)
        assert notifications == ["Urlaubsmodus eingeschaltet.", "Urlaubsmodus ausgeschaltet."]
        assert not calls and not manager.paused
        print("PASS native notifications: named synthetic service receives start/stop; enabled state persists")
    finally:
        if manager:
            await manager.shutdown()
        await hass.async_stop(force=True)


if __name__ == "__main__":
    assert version("homeassistant") == "2026.11.0"
    with TemporaryDirectory(prefix="lichtzentrale-stage6-") as directory:
        asyncio.run(run(directory))
    print("PASS Home Assistant 2026.11.0 isolated native smoke; no physical devices or timing patches")
    print("Timing scope: trial timeout and ten-minute safety schedule are unit-tested; native safety uses due records")
