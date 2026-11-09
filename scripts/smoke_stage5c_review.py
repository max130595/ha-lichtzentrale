# Geändert für Lichtzentrale
"""Isolated K1/K2 regression smoke against native Home Assistant 2026.11.0.

Run: .venv-target/bin/python scripts/smoke_stage5c_review.py
Uses real HA state events, service calls and temporary Store files. No pytest,
bootstrap, device connection, fabricated timestamps, or timing monkeypatches.
The two ownership cases share one real ten-second wait.
"""

from __future__ import annotations

import asyncio
import sys
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import homeassistant  # noqa: F401 -- initialize HA's supported dependency aliases first
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.helpers import area_registry, device_registry, entity_registry

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.lichtzentrale.const import DOMAIN, STORAGE_KEY  # noqa: E402
from custom_components.lichtzentrale.dynamic_scenes import DynamicSceneManager  # noqa: E402
from custom_components.lichtzentrale.live_preview import LivePreviewManager  # noqa: E402
from custom_components.lichtzentrale.palettes import list_palettes  # noqa: E402
from custom_components.lichtzentrale.rooms import async_set_light  # noqa: E402
from custom_components.lichtzentrale.storage import LichtzentraleStore  # noqa: E402


async def run(config_dir):
    hass = HomeAssistant(config_dir)
    hass.config_entries = ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    dynamic = preview = None
    try:
        await area_registry.async_load(hass)
        device_registry.async_setup(hass)
        await device_registry.async_load(hass)
        await entity_registry.async_load(hass)
        store = LichtzentraleStore(hass)
        await store.async_load()
        calls = []

        @callback
        def capture(call):
            """Synthetic device responds through the real HA state machine."""
            calls.append(call)
            entity = call.data["entity_id"]
            old = hass.states.get(entity)
            attrs = dict(old.attributes)
            for field in ("brightness", "xy_color", "color_temp_kelvin"):
                if field in call.data:
                    attrs[field] = call.data[field]
            if "xy_color" in call.data:
                attrs["color_mode"] = "xy"
            elif "color_temp_kelvin" in call.data:
                attrs["color_mode"] = "color_temp"
            hass.states.async_set(entity, "off" if call.service == "turn_off" else "on",
                                  attrs, context=call.context)

        hass.services.async_register("light", "turn_on", capture)
        hass.services.async_register("light", "turn_off", capture)

        # Each missing-value combination gets an actual brightness-only call.
        k1 = []
        for mode in ("xy", "color_temp"):
            for missing in ("mode", "brightness", "both", "unknown"):
                entity = f"light.fixture_review_{mode}_{missing}"
                hass.states.async_set(entity, "off", {
                    "supported_color_modes": [mode],
                    "color_mode": "unknown" if missing == "unknown" else (
                        None if missing in {"mode", "both"} else mode),
                    "brightness": None if missing in {"brightness", "both", "unknown"} else 70,
                })
                k1.append((entity, mode, missing))
        cases = ("brightness", "xy", "service", "off", "on", "user", "own", "child")
        groups = {
            kind: {case: f"light.fixture_review_{kind}_{case}" for case in cases}
            for kind in ("dynamic", "preview")
        }
        original_attrs = {"supported_color_modes": ["xy"], "color_mode": "xy",
                          "brightness": 71, "xy_color": (0.31, 0.33)}
        for group in groups.values():
            for case, entity in group.items():
                hass.states.async_set(entity, "off" if case == "on" else "on", original_attrs)
        await store.async_set_lights([e for e, _, _ in k1] + [e for g in groups.values() for e in g.values()])
        for entity, mode, missing in k1:
            result = await async_set_light(hass, store, entity, brightness=133)
            assert result["applied"] == [entity], result
            payload = calls[-1].data
            assert payload["brightness"] == 133
            if missing == "unknown":
                assert ("xy_color" if mode == "xy" else "color_temp_kelvin") in payload, payload
            else:
                assert "xy_color" not in payload and "color_temp_kelvin" not in payload, payload
        print("PASS K1: off lamps with None mode/brightness preserve brightness-only payload; explicit unknown initializes XY/CT")

        zones = {}
        for kind, group in groups.items():
            zone = await store.async_save_zone({"name": f"Fixture review {kind}", "entity_ids": list(group.values())})
            zones[kind] = "zone:" + zone["id"]
        assert (Path(config_dir) / ".storage" / STORAGE_KEY).is_file()
        reloaded = LichtzentraleStore(hass)
        await reloaded.async_load()
        assert reloaded.data == store.data

        dynamic = DynamicSceneManager(hass, store)
        preview = LivePreviewManager(hass, store)
        hass.data.setdefault(DOMAIN, {}).update(dynamic=dynamic, live_preview=preview)
        scene = {"id": "fixture-review-dynamic", "name": "Fixture review", "kind": "palette",
                 "area_id": zones["dynamic"], "palette_id": list_palettes()[0]["id"],
                 "brightness": 180, "dynamic": {"enabled": True, "interval": 60, "transition": 15}}
        await dynamic.start(scene, Context(), persist=False)
        active = dynamic.active[zones["dynamic"]]
        assert await dynamic.tick(active, 1)
        owner = SimpleNamespace(subscriptions={})
        begun = await preview.begin(zones["preview"], owner)
        identifier = begun["preview_id"]
        session = preview.sessions[identifier]
        draft = {"name": "Fixture trial", "kind": "snapshot", "area_id": zones["preview"],
                 "lights": {entity: {"on": case != "on", **({"brightness": 180, "xy": [0.45, 0.4]} if case != "on" else {})}
                            for case, entity in groups["preview"].items()}}
        applied = await preview.apply(identifier, owner, sequence=1, scene=draft)
        assert set(applied["applied"]) == set(groups["preview"].values()), applied
        await hass.async_block_till_done()
        assert not active["excluded"] and not session["released"]
        started = asyncio.get_running_loop().time()
        await asyncio.sleep(10.05)
        elapsed = asyncio.get_running_loop().time() - started
        assert elapsed >= 10

        async def report(entity, *, state=None, context=None, **attributes):
            old = hass.states.get(entity)
            hass.states.async_set(entity, state or old.state, {**old.attributes, **attributes}, context=context)
            await hass.async_block_till_done()

        for kind, record, excluded_key in (("dynamic", active, "excluded"), ("preview", session, "released")):
            group = groups[kind]
            for case, attrs in (("brightness", {"brightness": 95}), ("xy", {"xy_color": (0.38, 0.36)})):
                await report(group[case], **attrs)
                assert group[case] not in record[excluded_key], (kind, case)
            for case, context in (("own", record["context"]), ("child", Context(parent_id=record["context"].id, user_id="fixture-user"))):
                await hass.services.async_call("light", "turn_on", {"entity_id": group[case], "brightness": 99}, blocking=True, context=context)
                await report(group[case], brightness=100, context=context)
                await report(group[case], state="off", context=context)
                await report(group[case], state="on", context=context)
                assert group[case] not in record[excluded_key], (kind, case)
            await hass.services.async_call("light", "turn_on", {"entity_id": group["service"], "brightness": 77}, blocking=True, context=Context())
            await hass.async_block_till_done()
            await report(group["off"], state="off")
            await report(group["on"], state="on")
            await report(group["user"], brightness=89, context=Context(user_id="fixture-user"))
            assert record[excluded_key] == {group[c] for c in ("service", "off", "on", "user")}, (kind, record[excluded_key])
            print(f"PASS K2 {kind}: delayed contextless brightness/XY retained after {elapsed:.3f}s real time; foreign service, on/off, user attributes released; own/child contexts retained")

        before_cancel = len(calls)
        cancelled = await preview.cancel(identifier, owner)
        retained = {groups["preview"][c] for c in ("brightness", "xy", "own", "child")}
        assert set(cancelled["applied"]) == retained, cancelled
        assert {call.data["entity_id"] for call in calls[before_cancel:]} == retained
        for entity in retained:
            state = hass.states.get(entity)
            assert state.state == "on" and state.attributes["brightness"] == 71
            assert tuple(state.attributes["xy_color"]) == (0.31, 0.33)
        assert identifier not in preview.sessions and not owner.subscriptions
        print("PASS live cancel: restores captured brightness/XY only for retained lamps, including delayed reports")
    finally:
        if preview:
            await preview.shutdown()
        if dynamic:
            await dynamic.shutdown()
        await hass.async_stop(force=True)


def main():
    actual = version("homeassistant")
    assert actual == "2026.11.0", f"Expected native Home Assistant 2026.11.0, got {actual}"
    with TemporaryDirectory(prefix="lichtzentrale-review-") as directory:
        asyncio.run(run(directory))
    print(f"PASS native HA {actual}; isolated temporary storage removed. No physical-device or frontend coverage.")


if __name__ == "__main__":
    main()
