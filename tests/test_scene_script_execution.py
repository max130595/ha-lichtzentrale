# Geändert für Lichtzentrale
"""Actual scene execution integrates optional scripts without preview/restart playback."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.lichtzentrale.bindings import BindingManager
from custom_components.lichtzentrale.const import DOMAIN
from custom_components.lichtzentrale.dynamic_scenes import DynamicSceneManager
from custom_components.lichtzentrale.live_preview import LivePreviewManager
from custom_components.lichtzentrale.scenes import async_apply_scene, async_save_scene
from custom_components.lichtzentrale.storage import LichtzentraleStore
from custom_components.lichtzentrale.target_actions import async_execute_action
from tests import test_scenes

room = test_scenes.room


async def scripted_scene(hass, store, room, **overrides):
    hass.states.async_set("script.synthetic_scene", "off")
    return await async_save_scene(hass, store, {
        "name": "Synthetic scripted scene", "area_id": room[0], "kind": "snapshot",
        "lights": {room[1][0]: {"on": True, "brightness": 140, "xy": [.55, .25]}},
        "start_script": "script.synthetic_scene", **overrides,
    })


@pytest.mark.parametrize("value", ["script.missing", "light.fixture", "", 3, []])
async def test_scene_save_rejects_script_without_mutation(hass, store, room, value):
    before = list(store.data["scenes"])
    with pytest.raises(ServiceValidationError):
        await scripted_scene(hass, store, room, start_script=value)
    assert store.data["scenes"] == before


async def test_script_scene_save_reload_preserve_and_clear(hass, store, room):
    scene = await scripted_scene(hass, store, room)
    reloaded = LichtzentraleStore(hass)
    await reloaded.async_load()
    assert reloaded.data["scenes"][0]["start_script"] == "script.synthetic_scene"
    without_field = {k: v for k, v in scene.items() if k != "start_script"}
    updated = await async_save_scene(hass, store, without_field)
    assert updated["start_script"] == "script.synthetic_scene"
    cleared = await async_save_scene(hass, store, {**updated, "start_script": None})
    assert cleared["start_script"] is None


@pytest.mark.parametrize("entrypoint", ["tile", "button", "schedule", "selected_button"])
async def test_each_scene_start_runs_script_once_after_lights(hass, store, room, entrypoint):
    scene = await scripted_scene(hass, store, room)
    context = Context()
    with patch.object(type(hass.services), "async_call", new_callable=AsyncMock) as calls:
        for _ in range(2):
            calls.reset_mock()
            if entrypoint == "tile":
                result = await async_apply_scene(hass, store, scene["id"], context)
            elif entrypoint in {"button", "selected_button"}:
                params = {"scene_id": scene["id"]}
                action = "scene"
                if entrypoint == "selected_button":
                    action = "turn_on_lights"
                    params = {"entity_ids": [room[1][0]], "on_behavior": {"mode": "scene", "scene_id": scene["id"]}}
                result = await BindingManager(hass, store)._action(
                    {"action": action, "area_id": room[0], "params": params}, context
                )
            else:
                result = await async_execute_action(
                    hass, store, {"type": "scene", "scene_id": scene["id"]},
                    context=context, automatic=True,
                )
            assert result["applied"] == [room[1][0]]
            assert [(c.args[0], c.args[1]) for c in calls.call_args_list] == [
                ("light", "turn_on"), ("script", "turn_on")
            ]
            assert calls.call_args_list[-1].args[2] == {"entity_id": "script.synthetic_scene"}


@pytest.mark.parametrize("wrapper_script", [None, "script.synthetic_wrapper"])
@pytest.mark.parametrize("selected", [False, True])
async def test_seasonal_runs_wrapper_or_child_once(hass, store, room, wrapper_script, selected):
    child = await scripted_scene(hass, store, room)
    hass.states.async_set("script.synthetic_wrapper", "off")
    wrapper = await async_save_scene(hass, store, {
        "name": "Synthetic scripted seasons", "area_id": room[0], "kind": "seasonal",
        "seasonal": {"scenes": {"autumn": child["id"]}}, "start_script": wrapper_script,
    })
    with patch.object(type(hass.services), "async_call", new_callable=AsyncMock) as calls:
        if selected:
            result = await BindingManager(hass, store)._action({
                "action": "turn_on_lights", "area_id": room[0], "params": {
                    "entity_ids": [room[1][0]],
                    "on_behavior": {"mode": "scene", "scene_id": wrapper["id"]},
                },
            }, Context())
        else:
            result = await async_apply_scene(hass, store, wrapper["id"])
    assert result["applied"] == [room[1][0]]
    script_calls = [c for c in calls.call_args_list if c.args[0] == "script"]
    assert len(script_calls) == 1
    assert script_calls[0].args[2] == {"entity_id": wrapper_script or child["start_script"]}
    assert calls.call_args_list[-1] == script_calls[0]
    if not selected:
        assert store.data["rooms"][room[0]]["last_scene_id"] == wrapper["id"]


@pytest.mark.parametrize("failure", ["service", "deleted"])
async def test_script_failure_preserves_successful_light_scene(hass, store, room, caplog, failure):
    scene = await scripted_scene(hass, store, room)
    if failure == "deleted":
        hass.states.async_remove(scene["start_script"])

    async def dispatch(domain, *args, **kwargs):
        if domain == "script":
            raise HomeAssistantError("Synthetic script failed")

    with patch.object(type(hass.services), "async_call", side_effect=dispatch) as calls:
        result = await async_apply_scene(hass, store, scene["id"])
    assert result["applied"] == [room[1][0]]
    assert not result.get("failed")
    assert result.get("notes")
    assert store.data["rooms"][room[0]]["last_scene_id"] == scene["id"]
    assert calls.call_args_list[0].args[0] == "light"
    assert "die Lichtszene läuft weiter" in caplog.text


async def test_live_preview_and_cancel_never_run_script(hass, store, room):
    scene = await scripted_scene(hass, store, room)
    manager = LivePreviewManager(hass, store)
    owner = object()
    try:
        with patch.object(type(hass.services), "async_call", new_callable=AsyncMock) as calls:
            session = await manager.begin(room[0], owner)
            result = await manager.apply(session["preview_id"], owner, sequence=1, scene=scene)
            await manager.cancel(session["preview_id"], owner)
        assert result["applied"] == [room[1][0]]
        assert calls.call_args_list
        assert all(c.args[0] != "script" for c in calls.call_args_list)
    finally:
        await manager.shutdown()


async def test_dynamic_restart_and_tick_never_run_script(hass, store, room, monkeypatch):
    monkeypatch.setattr("custom_components.lichtzentrale.command_limiter.COMMAND_SPACING", 0)
    scene = await scripted_scene(hass, store, room, kind="palette", lights={},
        palette_id="kupfernest", dynamic={"enabled": True, "interval": 60, "transition": 0})
    manager = DynamicSceneManager(hass, store)
    hass.data.setdefault(DOMAIN, {}).update(dynamic=manager, store=store)
    fresh = None
    try:
        with patch.object(type(hass.services), "async_call", new_callable=AsyncMock) as calls:
            await async_apply_scene(hass, store, scene["id"])
            assert len([c for c in calls.call_args_list if c.args[0] == "script"]) == 1
            await manager.shutdown()
            reloaded = LichtzentraleStore(hass)
            await reloaded.async_load()
            fresh = DynamicSceneManager(hass, reloaded)
            hass.data[DOMAIN].update(dynamic=fresh, store=reloaded)
            calls.reset_mock()
            await fresh.restore(wait_for_start=False)
            assert room[0] in fresh.active
            await fresh.tick(fresh.active[room[0]], 1)
            assert calls.call_args_list
            assert all(c.args[0] != "script" for c in calls.call_args_list)
    finally:
        await manager.shutdown()
        if fresh:
            await fresh.shutdown()


async def test_failed_light_start_does_not_run_script(hass, store, room):
    scene = await scripted_scene(hass, store, room)
    with patch.object(type(hass.services), "async_call", AsyncMock(side_effect=HomeAssistantError("Synthetic lamp failure"))) as calls:
        result = await async_apply_scene(hass, store, scene["id"])
    assert not result["applied"]
    assert result["failed"] == [room[1][0]]
    assert all(c.args[0] != "script" for c in calls.call_args_list)
