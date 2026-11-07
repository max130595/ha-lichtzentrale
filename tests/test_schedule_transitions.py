# Geändert für Lichtzentrale
"""Schedule fades and lock-time conditions use only synthetic room devices."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.components.light import LightEntityFeature
from homeassistant.core import State, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from custom_components.lichtzentrale.adaptive import _set_enabled, async_set_adaptive
from custom_components.lichtzentrale.dynamic_scenes import DynamicSceneManager
from custom_components.lichtzentrale.palettes import async_apply_palette
from custom_components.lichtzentrale.rooms import (
    async_toggle_room,
    light_service_data,
    validate_transition,
)
from custom_components.lichtzentrale.scenes import async_apply_scene, async_save_scene
from custom_components.lichtzentrale.selected_lights import async_control_lights


@pytest.fixture
def fade_calls(hass):
    calls = []

    @callback
    def capture(call):
        calls.append(call)

    for domain in ("light", "switch"):
        for service in ("turn_on", "turn_off"):
            hass.services.async_register(domain, service, capture)
    return calls


@pytest.fixture
async def fade_room(hass, store):
    area = ar.async_get(hass).async_create("Studio")
    ids = []
    for index, (domain, mode, feature) in enumerate([
        ("light", "xy", LightEntityFeature.TRANSITION),
        ("light", "brightness", 0),
        ("switch", None, LightEntityFeature.TRANSITION),
    ]):
        entry = er.async_get(hass).async_get_or_create(
            domain, "shelly" if domain == "switch" else "synthetic", f"fade-{index}",
            original_name=f"Studio light {index}",
        )
        er.async_get(hass).async_update_entity(entry.entity_id, area_id=area.id)
        hass.states.async_set(entry.entity_id, "on", {
            "supported_color_modes": [mode] if mode else [], "brightness": 123,
            "supported_features": feature, "color_mode": mode,
            **({"xy_color": [0.3, 0.4]} if mode == "xy" else {}),
        })
        ids.append(entry.entity_id)
    await store.async_set_lights(ids)
    return area.id, ids


@pytest.mark.parametrize("value", [True, -1, 1801, "30", float("nan"), float("inf")])
def test_invalid_transition(value):
    with pytest.raises(ServiceValidationError):
        validate_transition(value)


@pytest.mark.parametrize("value", [None, 0, 0.5, 1800])
def test_valid_transition(value):
    validate_transition(value)


def test_switch_never_gets_transition_or_brightness():
    state = State("switch.studio_light", "on", {"supported_features": 32})
    assert light_service_data(state, on=True, brightness=50, transition=1800) == (
        "turn_on", {"entity_id": state.entity_id}
    )
    assert light_service_data(state, on=False, transition=1800) == (
        "turn_off", {"entity_id": state.entity_id}
    )


async def test_selected_override_on_and_off_snapshot(hass, store, fade_room, fade_calls):
    _, ids = fade_room
    await async_control_lights(hass, store, ids, on=True, brightness=42, transition=1800)
    data = {call.data["entity_id"]: call.data for call in fade_calls}
    assert data[ids[0]]["brightness"] == 42
    assert data[ids[0]]["transition"] == 1800
    assert data[ids[1]]["brightness"] == 42
    assert "transition" not in data[ids[1]]
    assert dict(data[ids[2]]) == {"entity_id": ids[2]}
    fade_calls.clear()
    await async_control_lights(hass, store, ids, on=False, transition=1200)
    assert store.data["settings"]["last_light_states"][ids[0]]["brightness"] == 123
    assert fade_calls[0].data["transition"] == 1200
    assert "brightness" not in fade_calls[0].data


async def test_room_off_fade_keeps_pre_off_snapshot(hass, store, fade_room, fade_calls):
    area, ids = fade_room
    await async_toggle_room(hass, store, area, on=False, transition=1800)
    assert store.data["rooms"][area]["pre_off_lights"][ids[0]]["brightness"] == 123
    data = {call.data["entity_id"]: call.data for call in fade_calls}
    assert data[ids[0]]["transition"] == 1800
    assert dict(data[ids[2]]) == {"entity_id": ids[2]}


async def test_snapshot_and_palette_overrides(hass, store, fade_room, fade_calls):
    area, ids = fade_room
    scene = await async_save_scene(hass, store, {
        "name": "Studio evening", "area_id": area, "kind": "snapshot",
        "lights": {ids[0]: {"on": True, "brightness": 50}, ids[2]: {"on": False}},
    })
    await async_apply_scene(hass, store, scene["id"], transition=1800)
    assert fade_calls[0].data["transition"] == 1800
    assert dict(fade_calls[1].data) == {"entity_id": ids[2]}
    scene = await async_save_scene(hass, store, {
        "name": "Studio colors", "area_id": area, "kind": "palette",
        "palette_id": "kupfernest",
    })
    fade_calls.clear()
    await async_apply_scene(hass, store, scene["id"], transition=1800)
    assert fade_calls[0].data["transition"] == 1800
    with pytest.raises(ServiceValidationError):
        await async_apply_palette(hass, store, "kupfernest", ids, transition=1800)


async def test_dynamic_first_tick_waits_for_fade_only_once(hass, store):
    manager = DynamicSceneManager(hass, store)
    run = {"scene": {"area_id": "studio", "dynamic": {"interval": 5}},
           "initial_transition": 1800}
    with (
        patch("custom_components.lichtzentrale.dynamic_scenes.asyncio.sleep", AsyncMock()) as sleep,
        patch.object(manager, "tick", AsyncMock(side_effect=[True, False])),
    ):
        await manager._loop(run)
    assert [call.args[0] for call in sleep.await_args_list] == [1800, 5]


async def test_adaptive_final_apply_owns_transition(hass, store):
    with (
        patch("custom_components.lichtzentrale.adaptive._validated", return_value=["light.studio"]),
        patch.object(type(hass.services), "async_call", AsyncMock()) as call,
    ):
        await _set_enabled(hass, store, "studio", "switch.adaptive_studio", True, None,
                           transition=1800, turn_on_lights=True)
    assert call.await_args_list[-1].args[:2] == ("adaptive_lighting", "apply")
    assert call.await_args_list[-1].args[2]["transition"] == 1800
    assert call.await_args_list[-1].args[2]["turn_on_lights"] is True
    assert "transition" not in call.await_args_list[0].args[2]


async def test_invalid_override_has_no_device_effect(hass, store, fade_room, fade_calls):
    area, ids = fade_room
    for operation in (
        async_toggle_room(hass, store, area, on=False, transition=1801),
        async_control_lights(hass, store, ids, on=True, transition=float("nan")),
    ):
        with pytest.raises(ServiceValidationError):
            await operation
    assert fade_calls == []


async def test_hue_override_preserves_dynamic(hass, store, fade_room):
    area, ids = fade_room
    hass.states.async_set("scene.studio", "unknown", {"is_dynamic": True})
    with patch("custom_components.lichtzentrale.scenes.hue_scene_targets", return_value=ids[:1]):
        scene = await async_save_scene(hass, store, {
            "name": "Studio Hue", "area_id": area, "kind": "hue", "hue_scene": "scene.studio",
        })
        with patch.object(type(hass.services), "async_call", AsyncMock()) as call:
            await async_apply_scene(hass, store, scene["id"], transition=1800)
        assert call.await_args.args == (
            "hue", "activate_scene",
            {"entity_id": "scene.studio", "dynamic": True, "transition": 1800},
        )


@pytest.mark.parametrize("action", ["room", "scene", "lights", "adaptive"])
async def test_guard_rechecks_after_lock_before_side_effects(hass, store, fade_room, fade_calls, action):
    area, ids = fade_room
    scene = await async_save_scene(hass, store, {
        "name": "Studio locked", "area_id": area, "kind": "palette", "palette_id": "kupfernest",
    })
    lock = asyncio.Lock()
    hass.data.setdefault("lichtzentrale", {}).setdefault("scene_locks", {})[area] = lock
    valid = True
    guard = Mock(side_effect=lambda: valid)
    await lock.acquire()
    if action == "room":
        coro = async_toggle_room(hass, store, area, on=False, guard=guard)
    elif action == "scene":
        coro = async_apply_scene(hass, store, scene["id"], guard=guard)
    elif action == "lights":
        coro = async_control_lights(hass, store, ids, on=False, guard=guard)
    else:
        coro = async_set_adaptive(hass, store, area, enabled=True, guard=guard)
    with patch("custom_components.lichtzentrale.dynamic_scenes.stop_dynamic", AsyncMock()) as stop:
        task = asyncio.create_task(coro)
        await asyncio.sleep(0)
        assert not task.done()
        guard.assert_not_called()
        valid = False
        lock.release()
        with pytest.raises(ServiceValidationError, match="Bedingungen"):
            await task
    stop.assert_not_awaited()
    assert fade_calls == []


async def test_full_condition_guard_only_once_per_batch(hass, store, fade_room, fade_calls):
    _, ids = fade_room
    guard = Mock(side_effect=[True, False])
    result = await async_control_lights(hass, store, ids, on=True, brightness=50, guard=guard)
    assert set(result["applied"]) == set(ids)
    guard.assert_called_once_with()
