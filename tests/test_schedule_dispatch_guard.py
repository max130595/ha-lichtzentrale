# Geändert für Lichtzentrale
"""Launch guards survive awaited preparation; synthetic devices only."""

from unittest.mock import ANY, AsyncMock, Mock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from custom_components.lichtzentrale.adaptive import _set_enabled, async_set_adaptive
from custom_components.lichtzentrale.rooms import async_toggle_room
from custom_components.lichtzentrale.scenes import async_apply_scene, async_save_scene
from custom_components.lichtzentrale.selected_lights import async_control_lights


@pytest.fixture
async def dispatch_room(hass, store):
    area = ar.async_get(hass).async_create("Synthetic studio")
    entry = er.async_get(hass).async_get_or_create("light", "synthetic", "dispatch-lamp")
    er.async_get(hass).async_update_entity(entry.entity_id, area_id=area.id)
    hass.states.async_set(entry.entity_id, "on", {
        "supported_color_modes": ["xy"], "brightness": 100, "xy_color": [0.3, 0.4],
    })
    await store.async_set_lights([entry.entity_id])
    return area.id, entry.entity_id


@pytest.mark.parametrize("action", ["selected", "room", "snapshot", "palette", "hue", "adaptive"])
async def test_window_closes_during_stop(hass, store, dispatch_room, action):
    area, entity = dispatch_room
    allowed = True

    async def close_window(*args):
        nonlocal allowed
        allowed = False

    kwargs = {"guard": Mock(return_value=True), "dispatch_guard": lambda: allowed}
    if action in {"snapshot", "palette", "hue"}:
        hass.states.async_set("scene.synthetic_studio", "unknown", {"is_dynamic": True})
        data = {"name": "Synthetic launch", "area_id": area, "kind": action}
        data.update({"lights": {entity: {"on": False}}} if action == "snapshot" else
                    {"palette_id": "kupfernest"} if action == "palette" else
                    {"hue_scene": "scene.synthetic_studio"})
        with patch("custom_components.lichtzentrale.scenes.hue_scene_targets", return_value=[entity]):
            scene = await async_save_scene(hass, store, data)
    if action == "adaptive":
        await store.async_update_room(area, {"adaptive_switch": "switch.synthetic_adaptive"})
    with (
        patch("custom_components.lichtzentrale.dynamic_scenes.stop_dynamic", side_effect=close_window),
        patch("custom_components.lichtzentrale.dynamic_scenes.async_exclude_targets", side_effect=close_window),
        patch("custom_components.lichtzentrale.scenes.stop_dynamic", side_effect=close_window),
        patch("custom_components.lichtzentrale.scenes.hue_scene_targets", return_value=[entity]),
        patch("custom_components.lichtzentrale.adaptive._validated", return_value=[entity]),
        patch.object(type(hass.services), "async_call", AsyncMock()) as call,
    ):
        try:
            if action == "selected":
                result = await async_control_lights(hass, store, [entity], on=False, **kwargs)
            elif action == "room":
                result = await async_toggle_room(hass, store, area, on=False, **kwargs)
            elif action == "adaptive":
                result = await async_set_adaptive(hass, store, area, enabled=True, **kwargs)
            else:
                result = await async_apply_scene(hass, store, scene["id"], **kwargs)
        except ServiceValidationError:
            pass
        else:
            assert result["applied"] == []
            assert result["failed"] == [entity]
        call.assert_not_awaited()
    kwargs["guard"].assert_called_once_with()


@pytest.mark.parametrize("action", ["selected", "room", "snapshot"])
async def test_window_closes_during_persistence(hass, store, dispatch_room, action):
    area, entity = dispatch_room
    scene = await async_save_scene(hass, store, {
        "name": "Synthetic off", "area_id": area, "kind": "snapshot",
        "lights": {entity: {"on": False}},
    })
    allowed = True
    method = "async_update_room" if action == "room" else "async_remember_light_states"
    original = getattr(store, method)

    async def save_then_close(*args, **kwargs):
        nonlocal allowed
        value = await original(*args, **kwargs)
        allowed = False
        return value

    with (
        patch.object(store, method, side_effect=save_then_close),
        patch.object(type(hass.services), "async_call", AsyncMock()) as call,
    ):
        kwargs = {"guard": lambda: True, "dispatch_guard": lambda: allowed}
        if action == "selected":
            result = await async_control_lights(hass, store, [entity], on=False, **kwargs)
        elif action == "room":
            result = await async_toggle_room(hass, store, area, on=False, **kwargs)
        else:
            result = await async_apply_scene(hass, store, scene["id"], **kwargs)
        assert result["applied"] == []
        call.assert_not_awaited()


@pytest.mark.parametrize("close_after", [1, 2])
async def test_adaptive_rechecks_between_service_calls(hass, store, close_after):
    dispatched = []

    async def record(*args, **kwargs):
        dispatched.append(args[:2])

    with (
        patch("custom_components.lichtzentrale.adaptive._validated", return_value=["light.synthetic"]),
        patch.object(type(hass.services), "async_call", side_effect=record),
        pytest.raises(ServiceValidationError, match="Bedingungen"),
    ):
        await _set_enabled(hass, store, "synthetic", "switch.synthetic", True, None,
                           dispatch_guard=lambda: len(dispatched) < close_after)
    assert len(dispatched) == close_after
    assert ("adaptive_lighting", "apply") not in dispatched


async def test_dynamic_launch_does_not_retain_window_guard(hass, store, dispatch_room):
    area, entity = dispatch_room
    scene = await async_save_scene(hass, store, {
        "name": "Synthetic dynamic", "area_id": area, "kind": "palette",
        "palette_id": "kupfernest", "dynamic": {"enabled": True, "interval": 5, "transition": 1},
    })
    manager = Mock(start=AsyncMock())
    guard = Mock(return_value=True)
    with (
        patch("custom_components.lichtzentrale.scenes.manager", return_value=manager),
        patch.object(type(hass.services), "async_call", AsyncMock()),
    ):
        result = await async_apply_scene(hass, store, scene["id"], dispatch_guard=guard)
    assert result["applied"] == [entity]
    # Rechecked before the limited dispatch and immediately before its native
    # service call; neither launch check remains attached to the running scene.
    assert guard.call_count == 2
    guard.assert_called_with()
    manager.start.assert_awaited_once_with(
        {key: value for key, value in scene.items() if key != "preview"},
        ANY, [entity], initial_transition=None, persist=True,
        palette_override=None, dispatch_guard=guard,
    )
    # The real runtime intentionally discards launch-only conditions. Closing a
    # schedule window later must not stop an already-launched persistent scene.
    from custom_components.lichtzentrale.dynamic_scenes import DynamicSceneManager

    runtime = DynamicSceneManager(hass, store)
    try:
        await runtime.start(store.data["scenes"][0], None, [entity], dispatch_guard=guard)
        guard.return_value = False
        assert runtime.active[area]["dispatch_guard"] is None
    finally:
        await runtime.shutdown()


@pytest.mark.parametrize("kind", ["palette", "hue"])
async def test_window_closes_during_adaptive_pause(hass, store, dispatch_room, kind):
    area, entity = dispatch_room
    hass.states.async_set("scene.synthetic_studio", "unknown", {"is_dynamic": True})
    data = {"name": "Synthetic color", "area_id": area, "kind": kind}
    data.update({"palette_id": "kupfernest"} if kind == "palette" else
                {"hue_scene": "scene.synthetic_studio"})
    allowed = True

    async def pause(*args, **kwargs):
        nonlocal allowed
        allowed = False

    with patch("custom_components.lichtzentrale.scenes.hue_scene_targets", return_value=[entity]):
        scene = await async_save_scene(hass, store, data)
        with (
            patch("custom_components.lichtzentrale.adaptive.async_pause_adaptive", side_effect=pause),
            patch.object(type(hass.services), "async_call", AsyncMock()) as call,
        ):
            try:
                result = await async_apply_scene(hass, store, scene["id"], dispatch_guard=lambda: allowed)
            except ServiceValidationError:
                pass
            else:
                assert result["applied"] == []
            call.assert_not_awaited()
