# Geändert für Lichtzentrale
"""Synthetic effect ordering, validation, cancellation and rollback coverage."""

import asyncio
from unittest.mock import patch

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import ServiceValidationError

from custom_components.lichtzentrale.effects import invalidate
from custom_components.lichtzentrale.live_preview import LivePreviewManager
from custom_components.lichtzentrale.rooms import async_set_light
from custom_components.lichtzentrale.scenes import async_apply_scene, async_save_scene
from tests.test_scenes import room as _room

room = _room


def capable(hass, entity, effect=None):
    state = hass.states.get(entity)
    hass.states.async_set(entity, state.state, {**state.attributes, "effect_list": ["sparkle", "candle", "stop_hue_effect"], "effect": effect})


async def make(hass, store, room, index=0, effect="sparkle", kind="snapshot"):
    area, ids = room
    entity = ids[index]
    capable(hass, entity)
    scene = {"name": "Synthetic effects", "area_id": area, "kind": kind,
             "lights": {entity: {"on": True, "brightness": 140}},
             "lamp_settings": {entity: {"mode": "cycle", "effect": effect}}}
    if kind == "palette":
        from custom_components.lichtzentrale.palette_catalogue import list_palettes
        scene["palette_id"] = list_palettes(store)[0]["id"]
    return await async_save_scene(hass, store, scene)


@pytest.mark.parametrize("index", [0, 1, 2])
@pytest.mark.parametrize("kind", ["snapshot", "palette"])
async def test_color_then_separate_effect(hass, store, room, light_calls, index, kind):
    scene = await make(hass, store, room, index, kind=kind)
    with patch("custom_components.lichtzentrale.effects.EFFECT_DELAY", 0):
        result = await async_apply_scene(hass, store, scene["id"])
    calls = [c for c in light_calls if c.data["entity_id"] == room[1][index]]
    assert room[1][index] in result["applied"]
    assert "effect" not in calls[0].data
    assert calls[0].data["brightness"] == 140 if kind == "snapshot" else calls[0].data["brightness"] > 0
    assert calls[-1].data == {"entity_id": room[1][index], "effect": "sparkle"}


async def test_invalid_effect_rejected_and_pure_onoff(hass, store, room, light_calls):
    with pytest.raises(ServiceValidationError):
        await make(hass, store, room, effect="invented")
    entity = room[1][3]
    with pytest.raises(ServiceValidationError):
        await async_save_scene(hass, store, {"name": "Synthetic onoff", "area_id": room[0], "kind": "snapshot", "lights": {entity: {"on": True}}, "lamp_settings": {entity: {"effect": "candle"}}})
    scene = await async_save_scene(hass, store, {"name": "Synthetic onoff", "area_id": room[0], "kind": "snapshot", "lights": {entity: {"on": True}}})
    await async_apply_scene(hass, store, scene["id"])
    assert light_calls[-1].data == {"entity_id": entity}


@pytest.mark.parametrize("off", [True, False])
async def test_stop_before_scene_or_off(hass, store, room, light_calls, off):
    scene = await make(hass, store, room)
    with patch("custom_components.lichtzentrale.effects.EFFECT_DELAY", 0):
        await async_apply_scene(hass, store, scene["id"])
    light_calls.clear()
    hass.services.async_register("light", "turn_off", lambda call: None)
    if off:
        await async_set_light(hass, store, room[1][0], on=False)
    else:
        scene["lamp_settings"] = {}
        await async_save_scene(hass, store, scene)
        await async_apply_scene(hass, store, scene["id"])
    assert light_calls[0].data["effect"] == "stop_hue_effect"


@pytest.mark.parametrize("change", ["grant", "newer", "external", "membership", "capability", "area", "device", "group", "homeassistant"])
async def test_delay_rechecks_ownership(hass, store, room, light_calls, change):
    scene = await make(hass, store, room)
    entity = room[1][0]
    entered, release = asyncio.Event(), asyncio.Event()
    original_sleep = asyncio.sleep
    async def delay(seconds):
        if seconds == 2.0:
            entered.set()
            await release.wait()
        else:
            await original_sleep(seconds)
    with patch("custom_components.lichtzentrale.effects.asyncio.sleep", side_effect=delay):
        task = asyncio.create_task(async_apply_scene(hass, store, scene["id"]))
        await entered.wait()
        if change == "grant":
            await store.async_set_lights([e for e in store.data["settings"]["light_entity_ids"] if e != entity])
        elif change == "newer":
            invalidate(hass, [entity])
        elif change == "external":
            await hass.services.async_call("light", "turn_on", {"entity_id": entity, "brightness": 50}, blocking=True, context=Context())
        elif change in {"area", "device", "group", "homeassistant"}:
            from homeassistant.const import EVENT_CALL_SERVICE
            data = {"area_id": room[0]} if change == "area" else {"device_id": "synthetic-device"} if change == "device" else {"entity_id": "group.synthetic_lights"} if change == "group" else {"entity_id": entity}
            hass.bus.async_fire(EVENT_CALL_SERVICE, {"domain": "homeassistant" if change == "homeassistant" else "light", "service": "turn_on", "service_data": data}, context=Context())
        elif change == "membership":
            from homeassistant.helpers import entity_registry as er
            er.async_get(hass).async_update_entity(entity, area_id=None)
        else:
            state = hass.states.get(entity)
            hass.states.async_set(entity, state.state, {**state.attributes, "effect_list": []})
        await original_sleep(0)
        release.set()
        result = await task
    assert entity in result.get("failed", [])
    assert not any(c.data.get("effect") == "sparkle" for c in light_calls)


async def test_live_preview_restores_previous_effect(hass, store, room, light_calls):
    scene = await make(hass, store, room)
    entity = room[1][0]
    capable(hass, entity, "candle")
    preview = LivePreviewManager(hass, store)
    owner = object()
    session = await preview.begin(room[0], owner)
    with patch("custom_components.lichtzentrale.effects.EFFECT_DELAY", 0):
        await preview.apply(session["preview_id"], owner, sequence=0, scene=scene)
        await preview.cancel(session["preview_id"], owner)
    assert [c.data.get("effect") for c in light_calls if "effect" in c.data] == ["stop_hue_effect", "sparkle", "stop_hue_effect", "candle"]


async def test_dynamic_effect_lamp_excluded(hass, store, room, light_calls):
    from custom_components.lichtzentrale.const import DOMAIN
    from custom_components.lichtzentrale.dynamic_scenes import DynamicSceneManager

    scene = await make(hass, store, room, kind="palette")
    scene["dynamic"]["enabled"] = True
    scene = await async_save_scene(hass, store, scene)
    manager = DynamicSceneManager(hass, store)
    hass.data.setdefault(DOMAIN, {})["dynamic"] = manager
    with patch("custom_components.lichtzentrale.effects.EFFECT_DELAY", 0):
        await async_apply_scene(hass, store, scene["id"])
    assert room[1][0] not in manager.active[room[0]]["targets"]
    assert room[1][1] in manager.active[room[0]]["targets"]
    await manager.stop(room[0])


async def test_stop_falls_back_to_none(hass, store, room, light_calls):
    entity = room[1][0]
    state = hass.states.get(entity)
    hass.states.async_set(entity, "on", {**state.attributes, "effect_list": ["candle"], "effect": "candle"})
    hass.services.async_register("light", "turn_off", lambda call: None)
    await async_set_light(hass, store, entity, on=False)
    assert light_calls[0].data == {"entity_id": entity, "effect": "none"}


async def test_preview_cancel_fences_delayed_effect(hass, store, room, light_calls):
    scene = await make(hass, store, room)
    preview = LivePreviewManager(hass, store)
    owner = object()
    session = await preview.begin(room[0], owner)
    entered, release = asyncio.Event(), asyncio.Event()
    original_sleep = asyncio.sleep
    async def delay(seconds):
        if seconds == 2.0:
            entered.set()
            await release.wait()
        else:
            await original_sleep(seconds)
    with patch("custom_components.lichtzentrale.effects.asyncio.sleep", side_effect=delay):
        apply = asyncio.create_task(preview.apply(session["preview_id"], owner, sequence=0, scene=scene))
        await entered.wait()
        cancel = asyncio.create_task(preview.cancel(session["preview_id"], owner))
        await original_sleep(0)
        release.set()
        await apply
        await cancel
    assert not any(c.data.get("effect") == "sparkle" for c in light_calls)


async def test_snapshot_captures_effect(hass, store, room):
    from custom_components.lichtzentrale.scenes import async_snapshot

    entity = room[1][0]
    capable(hass, entity, "candle")
    saved = await async_snapshot(hass, store, room[0], "Synthetic effect snapshot")
    assert saved["scene"]["lamp_settings"][entity]["effect"] == "candle"


async def test_onoff_ignores_misreported_effect_list(hass, store, room):
    from custom_components.lichtzentrale.effects import effect_list

    entity = room[1][3]
    capable(hass, entity)
    assert effect_list(hass.states.get(entity)) == []
    with pytest.raises(ServiceValidationError):
        await async_save_scene(hass, store, {"name": "Synthetic invalid onoff", "area_id": room[0], "kind": "snapshot", "lights": {entity: {"on": True}}, "lamp_settings": {entity: {"effect": "candle"}}})


async def test_dynamic_start_effect_keeps_global_rate_limit(hass, store, room):
    from homeassistant.core import callback
    from homeassistant.helpers import entity_registry as er

    scene = await make(hass, store, room, kind="palette")
    scene["dynamic"]["enabled"] = True
    scene = await async_save_scene(hass, store, scene)
    extra = []
    for index in range(4):
        entry = er.async_get(hass).async_get_or_create("light", "synthetic", f"effect-limit-{index}", original_name=f"Synthetic limit {index}")
        er.async_get(hass).async_update_entity(entry.entity_id, area_id=room[0])
        hass.states.async_set(entry.entity_id, "on", {"supported_color_modes": ["brightness"], "brightness": 100})
        extra.append(entry.entity_id)
    await store.async_set_lights([*room[1], *extra])
    times = []
    @callback
    def capture(call):
        times.append(asyncio.get_running_loop().time())
    hass.services.async_register("light", "turn_on", capture)
    with patch("custom_components.lichtzentrale.effects.EFFECT_DELAY", 0):
        result = await async_apply_scene(hass, store, scene["id"])
    assert not result.get("failed")
    assert len(times) == 9
    assert all(b - a >= 0.19 for a, b in zip(times, times[1:]))


async def test_script_light_command_releases_dynamic_lamp(hass, store, room, light_calls):
    from custom_components.lichtzentrale.const import DOMAIN
    from custom_components.lichtzentrale.dynamic_scenes import DynamicSceneManager

    scene = await make(hass, store, room, kind="palette")
    scene["lamp_settings"] = {}
    scene["dynamic"]["enabled"] = True
    scene = await async_save_scene(hass, store, scene)
    manager = DynamicSceneManager(hass, store)
    hass.data.setdefault(DOMAIN, {})["dynamic"] = manager
    context = Context()
    await async_apply_scene(hass, store, scene["id"], context)
    entity = room[1][0]
    from custom_components.lichtzentrale.scene_scripts import async_run_start_script

    hass.states.async_set("script.synthetic_lights", "off")
    async def script(call):
        await hass.services.async_call("light", "turn_on", {"entity_id": entity, "brightness": 77}, blocking=True, context=call.context)
    hass.services.async_register("script", "turn_on", script)
    await async_run_start_script(hass, "script.synthetic_lights", context)
    await hass.async_block_till_done()
    assert entity in manager.active[room[0]]["excluded"]
    await manager.stop(room[0])
