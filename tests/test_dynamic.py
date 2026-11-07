# Geändert für Lichtzentrale
"""Dynamic palettes remain scoped, cancellable and observable."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from custom_components.lichtzentrale.dynamic_scenes import DynamicSceneManager, validate_dynamic
from custom_components.lichtzentrale.rooms import async_toggle_room
from custom_components.lichtzentrale.scenes import async_apply_scene, async_save_scene


@pytest.fixture
async def running(hass, store):
    area = ar.async_get(hass).async_create("Synthetic dynamic room")
    ids = []
    for i in range(3):
        entry = er.async_get(hass).async_get_or_create("light", "fixture", f"dynamic-{i}")
        er.async_get(hass).async_update_entity(entry.entity_id, area_id=area.id)
        hass.states.async_set(entry.entity_id, "on", {"supported_color_modes": ["xy"]})
        ids.append(entry.entity_id)
    await store.async_set_lights(ids)
    scene = await async_save_scene(
        hass,
        store,
        {
            "name": "Synthetic loop",
            "area_id": area.id,
            "kind": "palette",
            "palette_id": "kupfernest",
            "dynamic": {"enabled": True, "interval": 5, "transition": 2},
        },
    )
    manager = DynamicSceneManager(hass, store)
    hass.data["lichtzentrale"] = {"store": store, "dynamic": manager}
    yield manager, scene, ids
    await manager.shutdown()


@pytest.mark.parametrize(
    "value,kind",
    [
        ({"enabled": 1}, "palette"),
        ({"interval": float("nan")}, "palette"),
        ({"interval": 4}, "palette"),
        ({"transition": 61}, "palette"),
        ({"interval": 5, "transition": 6}, "palette"),
        ({"enabled": True}, "snapshot"),
        ({"enabled": True}, "hue"),
        ({"unknown": 1}, "palette"),
    ],
)
def test_invalid(value, kind):
    with pytest.raises(ServiceValidationError):
        validate_dynamic(value, kind)


async def test_ticks_rotate_and_never_rekindle_or_expand(hass, store, running, light_calls):
    manager, scene, ids = running
    context = Context()
    await manager.start(store.data["scenes"][0], context)
    run = manager.active[scene["area_id"]]
    assert await manager.tick(run, 1)
    first_color = light_calls[0].data["xy_color"]
    light_calls.clear()
    hass.states.async_set(ids[1], "off", {"supported_color_modes": ["xy"]})
    await store.async_set_lights(ids[:2])
    assert await manager.tick(run, 2)
    assert [c.data["entity_id"] for c in light_calls] == [ids[0]]
    assert light_calls[0].data["xy_color"] != first_color
    assert light_calls[0].context == context


async def test_replace_stop_external_off_and_shutdown(hass, store, running):
    manager, scene, ids = running
    raw = store.data["scenes"][0]
    await manager.start(raw, None)
    old = manager.active[scene["area_id"]]["task"]
    await manager.start(raw, None)
    assert old.done()
    for entity in ids:
        hass.states.async_set(entity, "off")
    await hass.async_block_till_done()
    assert manager.list() == []
    await manager.start(raw, None)
    await manager.shutdown()
    assert manager.list() == []
    with pytest.raises(ServiceValidationError):
        await manager.start(raw, None)


async def test_deleted_or_changed_scene_stops(hass, store, running):
    manager, scene, _ = running
    await manager.start(store.data["scenes"][0], None)
    run = manager.active[scene["area_id"]]
    await store.async_delete_scene(scene["id"])
    assert not await manager.tick(run, 1)


async def test_recall_starts_and_room_off_cancels(hass, store, running, light_calls):
    manager, scene, ids = running
    hass.services.async_register("light", "turn_off", lambda call: None)
    await async_apply_scene(hass, store, scene["id"])
    assert manager.list()[0]["scene_id"] == scene["id"]
    await async_toggle_room(hass, store, scene["area_id"], False)
    assert manager.list() == []


async def test_failed_tick_stops(hass, store, running):
    manager, scene, _ = running
    await manager.start(store.data["scenes"][0], None)
    with patch(
        "custom_components.lichtzentrale.palettes.async_dispatch",
        AsyncMock(return_value={"failed": ["fixture"]}),
    ):
        assert not await manager.tick(manager.active[scene["area_id"]], 1)


async def test_partial_initial_targets_never_expand(hass, store, running, light_calls):
    manager, scene, ids = running
    await manager.start(store.data["scenes"][0], None, [ids[0]])
    assert await manager.tick(manager.active[scene["area_id"]], 1)
    assert [call.data["entity_id"] for call in light_calls] == [ids[0]]


async def test_malformed_restored_snapshot_has_no_side_effects(hass, store, running):
    manager, scene, ids = running
    invalid = {
        **store.data["scenes"][0],
        "kind": "snapshot",
        "dynamic": {"enabled": False},
        "lights": {ids[0]: {"on": True, "xy": [float("nan"), 0.2]}},
    }
    await store.async_save_scene(invalid, is_update=True)
    with patch(
        "custom_components.lichtzentrale.adaptive.async_pause_adaptive", AsyncMock()
    ) as pause:
        with pytest.raises(ServiceValidationError):
            await async_apply_scene(hass, store, scene["id"])
    pause.assert_not_awaited()


async def test_palette_rechecks_allowlist_after_pause(hass, store, running, light_calls):
    from custom_components.lichtzentrale.palettes import async_apply_palette

    _, _, ids = running

    async def revoke(*args, **kwargs):
        await store.async_set_lights([])

    with patch("custom_components.lichtzentrale.adaptive.async_pause_adaptive", side_effect=revoke):
        with pytest.raises(ServiceValidationError):
            await async_apply_palette(hass, store, "kupfernest", ids)
    assert not light_calls


async def test_palette_and_room_off_serialize(hass, store, running, light_calls):
    import asyncio

    from custom_components.lichtzentrale.palettes import async_apply_palette

    _, scene, ids = running
    started, proceed = asyncio.Event(), asyncio.Event()
    order = []

    async def pause(*args, **kwargs):
        started.set()
        await proceed.wait()

    async def dispatch(domain, service, params, **kwargs):
        order.append(service)

    with (
        patch("custom_components.lichtzentrale.adaptive.async_pause_adaptive", side_effect=pause),
        patch.object(type(hass.services), "async_call", side_effect=dispatch),
    ):
        palette = asyncio.create_task(async_apply_palette(hass, store, "kupfernest", ids))
        await started.wait()
        off = asyncio.create_task(async_toggle_room(hass, store, scene["area_id"], False))
        await asyncio.sleep(0)
        assert not order
        proceed.set()
        await asyncio.gather(palette, off)
    assert order == ["turn_on"] * len(ids) + ["turn_off"] * len(ids)


async def test_room_toggle_revalidates_after_stop(hass, store, running, light_calls):
    _, scene, ids = running

    async def revoke(*args):
        await store.async_set_lights(ids[1:])

    with patch("custom_components.lichtzentrale.dynamic_scenes.stop_dynamic", side_effect=revoke):
        await async_toggle_room(hass, store, scene["area_id"], True)
    assert [call.data["entity_id"] for call in light_calls] == ids[1:]


async def test_cosmetic_edits_keep_playback(hass, store, running, light_calls):
    manager, scene, _ = running
    await manager.start(store.data["scenes"][0], None)
    changed = {**store.data["scenes"][0], "favorite": True, "order": 17, "name": "New title"}
    await store.async_save_scene(changed, is_update=True)
    assert await manager.tick(manager.active[scene["area_id"]], 1)
    assert manager.list()[0]["name"] == "New title"
    assert light_calls


async def test_delete_immediately_stops_only_matching_run(hass, store, running):
    from custom_components.lichtzentrale.scenes import async_delete_scene

    manager, scene, _ = running
    original = store.data["scenes"][0]
    other = {**original, "id": "synthetic-other"}
    await store.async_save_scene(other)
    await manager.start(original, None)
    await async_delete_scene(store, other["id"], hass)
    assert manager.list()[0]["scene_id"] == original["id"]
    await async_delete_scene(store, original["id"], hass)
    assert manager.list() == []
