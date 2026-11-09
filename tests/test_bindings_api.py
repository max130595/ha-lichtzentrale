# Geändert für Lichtzentrale
"""Authenticated button API, atomic storage and native room-on scene recalls."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from custom_components.lichtzentrale.const import DOMAIN
from custom_components.lichtzentrale.rooms import async_toggle_room, list_rooms
from custom_components.lichtzentrale.scenes import async_save_scene
from custom_components.lichtzentrale.storage import LichtzentraleStore
from custom_components.lichtzentrale.websocket_api import async_setup_websocket_api


@pytest.fixture
async def setup(hass, store):
    area = ar.async_get(hass).async_create("Synthetic controls")
    lamp = er.async_get(hass).async_get_or_create("light", "synthetic", "synthetic-controls-lamp")
    er.async_get(hass).async_update_entity(lamp.entity_id, area_id=area.id)
    hass.states.async_set(lamp.entity_id, "off", {"supported_color_modes": ["xy"], "brightness": 90})
    await store.async_set_lights([lamp.entity_id])
    button = er.async_get(hass).async_get_or_create("event", "hue", "synthetic-controls-button")
    hass.states.async_set(button.entity_id, "2026-01-01T00:00:00+00:00", {
        "event_types": ["initial_press", "short_release", "repeat", "clock_wise"],
        "event_type": "short_release",
    })
    scene = await async_save_scene(hass, store, {
        "name": "Synthetic colors", "area_id": area.id, "kind": "palette", "palette_id": "kupfernest",
    })
    binding = {"event_entity": button.entity_id, "event_type": "short_release",
               "action": "toggle_room", "area_id": area.id, "params": {}}
    return area.id, lamp.entity_id, scene, binding


@pytest.fixture
async def client(hass, hass_ws_client, store):
    hass.data[DOMAIN] = {"store": store}
    client = await hass_ws_client(hass)
    async_setup_websocket_api(hass)
    return client


async def request(client, name, **kwargs):
    await client.send_json_auto_id({"type": f"lichtzentrale/{name}", **kwargs})
    return await client.receive_json()


async def test_button_api_roundtrip_and_room_configuration(hass, client, setup, store):
    area, _, scene, binding = setup
    buttons = (await request(client, "buttons/list"))["result"]
    assert buttons[0]["entity_id"] == binding["event_entity"]
    assert "double_short_release" in buttons[0]["event_types"]
    result = await request(client, "binding/save", binding=binding)
    assert result["success"]
    saved = result["result"]
    assert saved["id"]
    listed = (await request(client, "bindings/list"))["result"]
    assert listed == {"bindings": [saved], "double_click_ms": 500}
    saved["action"] = "scene"
    saved["params"] = {"scene_id": scene["id"]}
    assert (await request(client, "binding/save", binding=saved))["success"]
    assert (await request(client, "binding/settings", double_click_ms=650))["result"] == {"double_click_ms": 650}
    configured = await request(client, "room/settings", area_id=area, cycle=[scene["id"]], default_on=scene["id"])
    assert configured["result"] == {"cycle": [scene["id"]], "default_on": scene["id"]}
    restored = LichtzentraleStore(hass)
    await restored.async_load()
    assert restored.data == store.data
    assert list_rooms(hass, restored)[0]["cycle"] == [scene["id"]]
    assert list_rooms(hass, restored)[0]["default_on"] == scene["id"]
    assert (await request(client, "binding/delete", binding_id=saved["id"]))["success"]
    assert (await request(client, "bindings/list"))["result"]["bindings"] == []


@pytest.mark.parametrize("name,payload", [
    ("buttons/learn/start", {"entity_id": "event.synthetic"}),
    ("buttons/learn/status", {"token": "synthetic"}),
    ("buttons/learn/cancel", {"token": "synthetic"}),
    ("buttons/list", {}), ("bindings/list", {}), ("binding/save", {"binding": {}}),
    ("binding/delete", {"binding_id": "synthetic"}),
    ("binding/settings", {"double_click_ms": 600}),
    ("room/settings", {"area_id": "synthetic", "cycle": []}),
])
async def test_all_stage_three_commands_require_admin(
    hass, hass_ws_client, hass_read_only_access_token, store, name, payload,
):
    hass.data[DOMAIN] = {"store": store}
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    async_setup_websocket_api(hass)
    result = await request(client, name, **payload)
    assert result["error"]["code"] == "unauthorized"
    assert not store.data["bindings"]


async def test_duplicate_and_stale_bindings_do_not_overwrite(hass, setup, store):
    _, _, _, binding = setup
    outcomes = await asyncio.gather(
        store.async_save_binding(binding), store.async_save_binding(binding), return_exceptions=True,
    )
    assert sum(isinstance(value, ServiceValidationError) for value in outcomes) == 1
    assert len(store.data["bindings"]) == 1
    saved = store.data["bindings"][0]
    await store.async_delete_binding(saved["id"])
    with pytest.raises(ServiceValidationError):
        await store.async_save_binding(saved, is_update=True)
    assert store.data["bindings"] == []


async def test_storage_errors_leave_all_stage_three_data_unchanged(client, setup, store):
    area, _, scene, binding = setup
    saved = (await request(client, "binding/save", binding=binding))["result"]
    before = store.data
    with patch.object(store._store, "async_save", AsyncMock(side_effect=HomeAssistantError("synthetic disk error"))):
        for command, payload in [
            ("binding/delete", {"binding_id": saved["id"]}),
            ("binding/save", {"binding": {**saved, "action": "turn_on_room"}}),
            ("binding/settings", {"double_click_ms": 700}),
            ("room/settings", {"area_id": area, "cycle": [scene["id"]]}),
        ]:
            assert not (await request(client, command, **payload))["success"]
            assert store.data == before


@pytest.mark.parametrize("value", [0, 199, 1001, True, "500"])
async def test_invalid_double_click_window_rejected(client, value, store):
    before = store.data
    assert not (await request(client, "binding/settings", double_click_ms=value))["success"]
    assert store.data == before


async def test_room_settings_reject_foreign_scene_duplicate_and_unknown(client, setup, store):
    area, _, scene, _ = setup
    before = store.data
    for changes in [{"cycle": [scene["id"], scene["id"]]}, {"cycle": ["missing"]},
                    {"default_on": "missing"}, {"default_on": "adaptive"}, {}, {"other": "bad"}]:
        assert not (await request(client, "room/settings", area_id=area, **changes))["success"]
        assert store.data == before


async def test_scene_default_on_dispatches_under_room_lock(hass, setup, store, light_calls):
    area, lamp, scene, _ = setup
    await store.async_set_room_settings(area, {"default_on": scene["id"]})
    context = Context()
    result = await asyncio.wait_for(async_toggle_room(hass, store, area, True, context), 2)
    assert result["applied"] == [lamp]
    assert light_calls[0].context == context
    assert store.data["rooms"][area]["last_scene_id"] == scene["id"]
    await store.async_delete_scene(scene["id"])
    assert store.data["rooms"][area]["default_on"] == "last"


async def test_room_settings_revalidate_after_waiting_for_store_lock(hass, setup, store):
    area, _, scene, _ = setup
    await store._lock.acquire()
    task = asyncio.create_task(store.async_set_room_settings(area, {"cycle": [scene["id"]]}))
    await asyncio.sleep(0)
    store._data["scenes"] = []
    store._lock.release()
    with pytest.raises(ServiceValidationError):
        await task
    assert "cycle" not in store.data["rooms"].get(area, {})


async def test_next_scene_service_authorization_and_result(
    hass, setup, store, hass_admin_user, hass_read_only_user, light_calls,
):
    from homeassistant.exceptions import Unauthorized
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    area, lamp, scene, _ = setup
    await store.async_set_room_settings(area, {"cycle": [scene["id"]]})
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN, "next_scene", {"area_id": area}, blocking=True, return_response=True,
            context=Context(user_id=hass_read_only_user.id),
        )
    assert not light_calls
    result = await hass.services.async_call(
        DOMAIN, "next_scene", {"area_id": area}, blocking=True, return_response=True,
        context=Context(user_id=hass_admin_user.id),
    )
    assert result["scene_id"] == scene["id"]
    assert result["applied"] == [lamp]
    assert light_calls[0].context.user_id == hass_admin_user.id
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("action", ["toggle_lights", "turn_on_lights", "turn_off_lights", "dim_up", "dim_down"])
async def test_selected_binding_api_roundtrip(client, setup, store, action):
    _, lamp, _, original = setup
    binding = {**original, "action": action, "area_id": None, "params": {"entity_ids": [lamp]}}
    result = await request(client, "binding/save", binding=binding)
    assert result["success"]
    assert result["result"]["params"] == {"entity_ids": [lamp]}
    assert result["result"]["area_id"] is None
    assert (await request(client, "bindings/list"))["result"]["bindings"] == [result["result"]]
    assert store.data["bindings"] == [result["result"]]


async def test_learning_commands_are_ephemeral_and_cancelable(hass, client, setup, store):
    from custom_components.lichtzentrale.bindings import BindingManager

    manager = BindingManager(hass, store)
    hass.data[DOMAIN]["bindings"] = manager
    before = store.data
    try:
        result = await request(client, "buttons/learn/start", entity_id=setup[3]["event_entity"])
        assert result["success"]
        token = result["result"]["token"]
        assert (await request(client, "buttons/learn/status", token=token))["result"] == {"status": "waiting", "observation": None}
        assert (await request(client, "buttons/learn/cancel", token=token))["result"] == {"cancelled": True}
        assert not (await request(client, "buttons/learn/status", token=token))["success"]
        assert store.data == before
    finally:
        await manager.shutdown()
