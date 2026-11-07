# Geändert für Lichtzentrale
"""Scene recalls use synthetic registry-backed devices and fail closed."""

import asyncio
from enum import Enum
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lichtzentrale.rooms import list_rooms
from custom_components.lichtzentrale.scenes import (
    async_apply_scene,
    async_delete_scene,
    async_reorder_scenes,
    async_save_scene,
    async_snapshot,
    hue_scene_targets,
    list_hue_scenes,
    list_scenes,
)
from custom_components.lichtzentrale.storage import LichtzentraleStore


@pytest.fixture
async def room(hass, store):
    area = ar.async_get(hass).async_create("Synthetic scene room")
    ids = []
    for domain, platform, mode in [
        ("light", "synthetic", "xy"),
        ("light", "synthetic", "color_temp"),
        ("light", "synthetic", "brightness"),
        ("light", "synthetic", "onoff"),
        ("switch", "shelly", None),
    ]:
        entry = er.async_get(hass).async_get_or_create(
            domain, platform, f"fixture-{len(ids)}", original_name=f"Fixture light {len(ids)}"
        )
        er.async_get(hass).async_update_entity(entry.entity_id, area_id=area.id)
        attrs = {"supported_color_modes": [mode], "color_mode": mode}
        if mode in {"xy", "color_temp", "brightness"}:
            attrs["brightness"] = 110
        if mode == "xy":
            attrs["xy_color"] = [0.4, 0.3]
        if mode == "color_temp":
            attrs.update(
                color_temp_kelvin=3000, min_color_temp_kelvin=2700, max_color_temp_kelvin=6000
            )
        hass.states.async_set(entry.entity_id, "off" if mode == "onoff" else "on", attrs)
        ids.append(entry.entity_id)
    await store.async_set_lights(ids)
    return area.id, ids


async def snapshot(hass, store, room):
    return (await async_snapshot(hass, store, room[0], "Fixture scene"))["scene"]


async def test_snapshot_roundtrip_parallel_and_last_scene(hass, store, room):
    area, ids = room
    scene = await snapshot(hass, store, room)
    assert scene["lights"] == {
        ids[0]: {"on": True, "brightness": 110, "xy": [0.4, 0.3]},
        ids[1]: {"on": True, "brightness": 110, "color_temp_kelvin": 3000},
        ids[2]: {"on": True, "brightness": 110},
        ids[3]: {"on": False},
        ids[4]: {"on": True},
    }
    entered = []
    ready = asyncio.Event()
    context = Context()

    async def call(domain, service, data, blocking, context):
        entered.append((domain, service, data, context))
        if len(entered) == len(ids):
            ready.set()
        await asyncio.wait_for(ready.wait(), 1)

    with patch.object(type(hass.services), "async_call", side_effect=call):
        result = await async_apply_scene(hass, store, scene["id"], context)
    assert result == {"applied": ids, "skipped": []}
    assert entered[0][2]["xy_color"] == [0.4, 0.3]
    assert entered[1][2]["color_temp_kelvin"] == 3000
    assert entered[2][2]["brightness"] == 110
    assert entered[3][:2] == ("light", "turn_off")
    assert entered[4][:3] == ("switch", "turn_on", {"entity_id": ids[4]})
    assert all(item[3] == context for item in entered)
    assert list_rooms(hass, store)[0]["last_scene_id"] == scene["id"]
    reloaded = LichtzentraleStore(hass)
    await reloaded.async_load()
    assert reloaded.data["rooms"][area]["last_scene_id"] == scene["id"]


async def test_crud_favorite_preview_reorder_reload(hass, store, room):
    first = await snapshot(hass, store, room)
    second = await snapshot(hass, store, room)
    first.update(name="Renamed fixture", favorite=True)
    updated = await async_save_scene(hass, store, first)
    assert updated["preview"] and updated["favorite"]
    await async_reorder_scenes(store, room[0], [second["id"], first["id"]])
    reloaded = LichtzentraleStore(hass)
    await reloaded.async_load()
    assert [s["id"] for s in list_scenes(reloaded, room[0])] == [second["id"], first["id"]]
    assert list_scenes(reloaded)[1]["name"] == "Renamed fixture"
    await reloaded.async_set_last_scene(room[0], first["id"])
    await async_delete_scene(reloaded, first["id"])
    assert "last_scene_id" not in reloaded.data["rooms"][room[0]]
    with pytest.raises(ServiceValidationError):
        await async_apply_scene(hass, reloaded, first["id"])


@pytest.mark.parametrize("change", ["revoked", "moved", "group", "lock", "removed", "disabled"])
async def test_recall_revalidates_every_target_before_dispatch(hass, store, room, change):
    scene = await snapshot(hass, store, room)
    target = room[1][-1]
    if change == "revoked":
        await store.async_set_lights(room[1][:-1])
    elif change == "moved":
        other = ar.async_get(hass).async_create("Other synthetic area")
        er.async_get(hass).async_update_entity(target, area_id=other.id)
    elif change == "group":
        hass.states.async_set(target, "on", {"entity_id": [room[1][0]]})
    elif change == "lock":
        scene["lights"]["lock.fixture"] = {"on": True}
        hass.states.async_set("lock.fixture", "locked")
        await store.async_save_scene(scene)
    elif change == "disabled":
        er.async_get(hass).async_update_entity(target, disabled_by=er.RegistryEntryDisabler.USER)
    else:
        hass.states.async_remove(target)
    with patch.object(type(hass.services), "async_call") as call:
        with pytest.raises(ServiceValidationError):
            await async_apply_scene(hass, store, scene["id"])
    call.assert_not_called()
    assert not store.data["rooms"]


@pytest.mark.parametrize("failure", ["unavailable", "unknown", "service"])
async def test_partial_recall_does_not_replace_last_scene(hass, store, room, failure):
    previous = await snapshot(hass, store, room)
    scene = await snapshot(hass, store, room)
    await store.async_set_last_scene(room[0], previous["id"])
    target = room[1][-1]
    if failure != "service":
        hass.states.async_set(target, failure)

    async def call(domain, service, data, **kwargs):
        if data["entity_id"] == target:
            raise HomeAssistantError("Synthetic failure")

    with patch.object(type(hass.services), "async_call", side_effect=call):
        result = await async_apply_scene(hass, store, scene["id"])
    assert result["failed" if failure == "service" else "skipped"] == [target]
    assert store.data["rooms"][room[0]]["last_scene_id"] == previous["id"]


async def test_snapshot_reports_unavailable_and_empty_fails(hass, store, room):
    hass.states.async_set(room[1][0], "unavailable")
    result = await async_snapshot(hass, store, room[0], "Partial fixture")
    assert result["skipped"] == room[1][:1]
    assert room[1][0] not in result["scene"]["lights"]
    for entity_id in room[1]:
        hass.states.async_set(entity_id, "unavailable")
    with pytest.raises(ServiceValidationError):
        await async_snapshot(hass, store, room[0], "Empty fixture")


@pytest.mark.parametrize("value", [{"on": True, "brightness": 120}, {"on": True, "xy": [0.3, 0.4]}])
async def test_switch_snapshot_rejects_color_and_brightness(hass, store, room, value):
    scene = await snapshot(hass, store, room)
    scene["lights"][room[1][-1]] = value
    before = store.data
    with pytest.raises(ServiceValidationError):
        await async_save_scene(hass, store, scene)
    assert store.data == before


class ResourceType(Enum):
    LIGHT = "light"
    GROUPED_LIGHT = "grouped_light"


@pytest.fixture
async def hue(hass, store):
    area = ar.async_get(hass).async_create("Synthetic Hue area")
    config = MockConfigEntry(domain="hue", data={})
    config.add_to_hass(hass)
    registry = er.async_get(hass)
    light = registry.async_get_or_create(
        "light", "hue", "synthetic-resource-light", config_entry=config
    )
    scene = registry.async_get_or_create(
        "scene", "hue", "synthetic-resource-scene", config_entry=config
    )
    for entry in (light, scene):
        registry.async_update_entity(entry.entity_id, area_id=area.id)
        hass.states.async_set(entry.entity_id, "on" if entry.domain == "light" else "unknown")
    hass.states.async_set(scene.entity_id, "2026-01-01T00:00:00+00:00")
    target = SimpleNamespace(rtype=ResourceType.LIGHT, rid=light.unique_id)
    resource = SimpleNamespace(actions=[SimpleNamespace(target=target)])
    config.runtime_data = SimpleNamespace(api=SimpleNamespace(scenes={scene.unique_id: resource}))
    await store.async_set_lights([light.entity_id])
    return area.id, light, scene, config, resource


async def save_hue(hass, store, hue):
    return await async_save_scene(
        hass,
        store,
        {
            "name": "Fixture bridge scene",
            "area_id": hue[0],
            "kind": "hue",
            "hue_scene": hue[2].entity_id,
        },
    )


async def test_hue_v2_resource_targets_recall_and_last_scene(hass, store, hue):
    assert hue_scene_targets(hass, hue[2].entity_id) == [hue[1].entity_id]
    assert list_hue_scenes(hass, store, hue[0])[0]["available"]
    scene = await save_hue(hass, store, hue)
    with patch.object(type(hass.services), "async_call") as call:
        result = await async_apply_scene(hass, store, scene["id"])
        remembered = store.data["rooms"][hue[0]]["last_scene_id"]
        await async_apply_scene(hass, store, remembered)
    assert result == {"applied": [hue[1].entity_id], "skipped": []}
    assert call.await_count == 2
    assert call.call_args.args == (
        "hue",
        "activate_scene",
        {"entity_id": hue[2].entity_id, "dynamic": False},
    )


@pytest.mark.parametrize(
    "change", ["revoked", "moved", "group", "missing", "empty", "bridge", "unloaded"]
)
async def test_hue_fails_closed_when_resource_targets_change(hass, store, hue, change):
    scene = await save_hue(hass, store, hue)
    if change == "revoked":
        await store.async_set_lights([])
    elif change == "moved":
        other = ar.async_get(hass).async_create("Different fixture area")
        er.async_get(hass).async_update_entity(hue[1].entity_id, area_id=other.id)
    elif change == "group":
        hue[4].actions[0].target.rtype = ResourceType.GROUPED_LIGHT
    elif change == "missing":
        hue[4].actions[0].target.rid = "missing-resource"
    elif change == "empty":
        hue[4].actions.clear()
    elif change == "bridge":
        other = MockConfigEntry(domain="hue", data={})
        other.add_to_hass(hass)
        er.async_get(hass).async_update_entity(hue[1].entity_id, config_entry_id=other.entry_id)
    else:
        hue[3].runtime_data = None
    with patch.object(type(hass.services), "async_call") as call:
        with pytest.raises(ServiceValidationError):
            await async_apply_scene(hass, store, scene["id"])
    call.assert_not_called()
    assert not store.data["rooms"]


async def test_arbitrary_scene_not_hue_is_never_executed(hass, store, room):
    entry = er.async_get(hass).async_get_or_create("scene", "synthetic", "fixture-non-hue")
    hass.states.async_set(entry.entity_id, "on", {"entity_id": room[1]})
    with pytest.raises(ServiceValidationError):
        await async_save_scene(
            hass,
            store,
            {"name": "Invalid", "area_id": room[0], "kind": "hue", "hue_scene": entry.entity_id},
        )
    assert list_hue_scenes(hass, store) == []


async def test_invalid_late_target_settings_prevent_partial_dispatch(hass, store, room):
    scene = await snapshot(hass, store, room)
    scene["lights"][room[1][-2]] = {"on": True, "brightness": 999}
    # A restored older Store may contain data that did not pass today's save schema.
    await store.async_save_scene(scene)
    with patch.object(type(hass.services), "async_call") as call:
        with pytest.raises(ServiceValidationError):
            await async_apply_scene(hass, store, scene["id"])
    call.assert_not_called()


async def test_recall_adapts_to_changed_device_capabilities(hass, store, room):
    scene = await snapshot(hass, store, room)
    ids = room[1]
    hass.states.async_set(ids[0], "on", {"supported_color_modes": ["onoff"]})
    hass.states.async_set(
        ids[1],
        "on",
        {
            "supported_color_modes": ["color_temp"],
            "min_color_temp_kelvin": 3500,
            "max_color_temp_kelvin": 4500,
        },
    )
    with patch.object(type(hass.services), "async_call") as call:
        await async_apply_scene(hass, store, scene["id"])
    payloads = {c.args[2]["entity_id"]: c.args[2] for c in call.call_args_list}
    assert payloads[ids[0]] == {"entity_id": ids[0]}
    assert payloads[ids[1]]["color_temp_kelvin"] == 3500


@pytest.mark.parametrize("target", ["scene", "light"])
async def test_unavailable_hue_does_not_call_bridge_or_remember(hass, store, hue, target):
    scene = await save_hue(hass, store, hue)
    hass.states.async_set(hue[2 if target == "scene" else 1].entity_id, "unavailable")
    with patch.object(type(hass.services), "async_call") as call:
        result = await async_apply_scene(hass, store, scene["id"])
    call.assert_not_called()
    assert result == {"applied": [], "skipped": [hue[1].entity_id]}
    assert not store.data["rooms"]


async def test_failed_hue_service_does_not_remember(hass, store, hue):
    scene = await save_hue(hass, store, hue)
    with patch.object(type(hass.services), "async_call", side_effect=HomeAssistantError("bridge")):
        with pytest.raises(HomeAssistantError):
            await async_apply_scene(hass, store, scene["id"])
    assert not store.data["rooms"]


async def test_recalls_in_same_room_are_serialized(hass, store, room):
    first = await snapshot(hass, store, room)
    second = await snapshot(hass, store, room)
    first_context, second_context = Context(), Context()
    entered = []
    first_ready, release = asyncio.Event(), asyncio.Event()

    async def call(domain, service, data, blocking, context):
        entered.append(context)
        if context == first_context:
            if len(entered) == len(room[1]):
                first_ready.set()
            await release.wait()

    with patch.object(type(hass.services), "async_call", side_effect=call):
        task = asyncio.create_task(async_apply_scene(hass, store, first["id"], first_context))
        await asyncio.wait_for(first_ready.wait(), 1)
        other = asyncio.create_task(async_apply_scene(hass, store, second["id"], second_context))
        await asyncio.sleep(0)
        assert entered == [first_context] * len(room[1])
        release.set()
        await asyncio.gather(task, other)
    assert entered == [first_context] * len(room[1]) + [second_context] * len(room[1])
    assert store.data["rooms"][room[0]]["last_scene_id"] == second["id"]


async def test_cancelled_device_call_is_failed_not_last_scene(hass, store, room):
    previous = await snapshot(hass, store, room)
    scene = await snapshot(hass, store, room)
    await store.async_set_last_scene(room[0], previous["id"])
    target = room[1][-1]

    async def call(domain, service, data, **kwargs):
        if data["entity_id"] == target:
            raise asyncio.CancelledError()

    with patch.object(type(hass.services), "async_call", side_effect=call):
        result = await async_apply_scene(hass, store, scene["id"])
    assert result["failed"] == [target]
    assert target not in result["applied"]
    assert store.data["rooms"][room[0]]["last_scene_id"] == previous["id"]


@pytest.mark.parametrize("palette_id", [[], {}, ["fixture"], {"id": "fixture"}])
async def test_invalid_palette_id_fails_cleanly(hass, store, room, palette_id):
    before = store.data
    with pytest.raises(ServiceValidationError):
        await async_save_scene(
            hass,
            store,
            {
                "name": "Fixture palette",
                "area_id": room[0],
                "kind": "palette",
                "palette_id": palette_id,
            },
        )
    assert store.data == before


async def test_pending_edit_does_not_resurrect_deleted_scene(hass, store, room):
    scene = await snapshot(hass, store, room)
    scene["name"] = "Pending edit"
    # Queue delete then edit behind another storage transaction. The edit sees
    # the scene during validation, but must recheck existence under the lock.
    await store._lock.acquire()
    delete = asyncio.create_task(async_delete_scene(store, scene["id"]))
    await asyncio.sleep(0)
    edit = asyncio.create_task(async_save_scene(hass, store, scene))
    await asyncio.sleep(0)
    store._lock.release()
    await delete
    with pytest.raises(ServiceValidationError):
        await edit
    assert not store.data["scenes"]


async def test_never_activated_hue_scene_is_available_and_recallable(hass, store, hue):
    # Scene.state is None/unknown until the first HA activation timestamp exists.
    hass.states.async_set(hue[2].entity_id, "unknown")
    assert list_hue_scenes(hass, store, hue[0])[0]["available"]
    scene = await save_hue(hass, store, hue)
    with patch.object(type(hass.services), "async_call") as call:
        result = await async_apply_scene(hass, store, scene["id"])
    assert result == {"applied": [hue[1].entity_id], "skipped": []}
    call.assert_awaited_once()
    assert store.data["rooms"][hue[0]]["last_scene_id"] == scene["id"]


async def test_hue_preview_uses_resource_colors_and_refreshes_existing_import(hass, store, hue):
    from homeassistant.util.color import color_xy_to_RGB

    hue[4].actions[0].action = SimpleNamespace(
        color=SimpleNamespace(xy=SimpleNamespace(x=0.55, y=0.35)),
        on=SimpleNamespace(on=True),
    )
    expected = "#%02x%02x%02x" % color_xy_to_RGB(0.55, 0.35)
    saved = await save_hue(hass, store, hue)
    assert saved["preview"] == [expected]
    assert list_hue_scenes(hass, store)[0]["preview"] == [expected]
    hue[4].actions[0].action.color.xy.x = 0.25
    assert list_scenes(store, hass=hass)[0]["preview"] != [expected]
    assert list_scenes(store)[0]["preview"] == [expected]


async def test_hue_preview_handles_missing_or_invalid_colors(hass, store, hue):
    hue[4].actions[0].action = SimpleNamespace(
        color=SimpleNamespace(xy=SimpleNamespace(x=float("nan"), y=0.35))
    )
    saved = await save_hue(hass, store, hue)
    assert saved["preview"] == ["#b6c9ce", "#8396a1"]
