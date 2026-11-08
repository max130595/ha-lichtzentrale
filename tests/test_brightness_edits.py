# Geändert für Lichtzentrale
"""Regression coverage for edits while synthetic brightness stages are owned."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
import test_brightness as regulator_tests
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from test_brightness_api import request

from custom_components.lichtzentrale.const import DOMAIN
from custom_components.lichtzentrale.websocket_api import async_setup_websocket_api

brightness = regulator_tests.brightness
lux = regulator_tests.lux


async def activate(hass, t, count=3):
    await t.manager.async_evaluate(t.area)
    await hass.async_block_till_done()
    await lux(hass, t, 50, 10)
    if count > 1:
        await lux(hass, t, 51, 170)
        await lux(hass, t, 80, 10)
    if count > 2:
        await lux(hass, t, 79, 170)
        await lux(hass, t, 140, 10)
    assert t.manager.status(t.area)["active_stage"] == count


async def test_api_save_target_keeps_owned_stages_then_sheds_in_reverse(
    hass, store, brightness, hass_ws_client,
):
    t = brightness
    hass.data[DOMAIN]["store"] = store
    client = await hass_ws_client(hass)
    async_setup_websocket_api(hass)
    await activate(hass, t)
    response = await request(client, "save", area_id=t.area, config={**t.config, "target_lux": 120})
    assert response["success"]
    assert response["result"]["status"]["active_stage"] == 3
    assert response["result"]["status"]["learned_lux"] == [40, 29, 61]
    assert not response["result"]["status"]["paused"]
    assert len(t.calls) == 3
    await lux(hass, t, 500, 169)
    assert len(t.calls) == 3  # Saving does not erase the minimum interval.
    for index, seconds in ((2, 1), (1, 180), (0, 180)):
        await lux(hass, t, 500 + index, seconds)
        assert t.calls[-1].service == "turn_off"
        assert t.calls[-1].data == {"entity_id": t.targets[index]}
        assert t.manager.status(t.area)["active_stage"] == index
    assert not t.manager.status(t.area)["paused"]


@pytest.mark.parametrize("change", ["reorder", "remove", "replace", "regroup", "member_order"])
async def test_changed_stages_turn_off_old_targets_before_commit(hass, store, brightness, change):
    t = brightness
    if change == "member_order":
        await store.async_set_brightness(t.area, {**t.config, "stages": [
            {"entity_ids": t.targets, "brightness": 120}]})
        await t.manager.async_evaluate(t.area)
        await hass.async_block_till_done()
    else:
        await activate(hass, t)
    changed = deepcopy(store.data["rooms"][t.area]["brightness"])
    if change in {"reorder", "replace"}:
        changed["stages"] = changed["stages"][::-1]
        if change == "replace":
            changed["stages"] = changed["stages"][:1]
    elif change == "remove":
        changed["stages"] = changed["stages"][:2]
    elif change == "regroup":
        changed["stages"] = [{"entity_ids": t.targets, "brightness": 120}]
    else:
        changed["stages"][0]["entity_ids"].reverse()
    old = store.data["rooms"][t.area]["brightness"]
    old_active = t.manager.status(t.area)["active_stage"]
    seen = []

    @callback
    def capture(call):
        assert store.data["rooms"][t.area]["brightness"] == old
        seen.append(call)
        assert t.manager.status(t.area)["active_stage"] > 0
        entity = call.data["entity_id"]
        hass.states.async_set(entity, "off", dict(hass.states.get(entity).attributes), context=call.context)

    for domain in ("light", "switch"):
        hass.services.async_register(domain, "turn_off", capture)
    await store.async_set_brightness(t.area, changed)
    await hass.async_block_till_done()
    assert len(seen) == 3
    assert {call.data["entity_id"] for call in seen} == set(t.targets)
    if old_active == 3:
        assert [call.data["entity_id"] for call in seen] == t.targets[::-1]
    assert all(call.data == {"entity_id": call.data["entity_id"]} for call in seen)
    assert t.manager.status(t.area)["active_stage"] == 0
    assert store.data["rooms"][t.area]["brightness"] == changed
    assert t.manager.status(t.area)["learned_lux"] == [None] * len(changed["stages"])


@pytest.mark.parametrize("field", ["brightness", "sensor"])
async def test_non_target_edits_keep_ownership_but_reset_invalid_learning(hass, store, brightness, field):
    t = brightness
    await activate(hass, t, 1)
    config = deepcopy(t.config)
    if field == "brightness":
        config["stages"][0]["brightness"] = 77
    else:
        config["lux_sensor_entity_id"] = "sensor.synthetic_other_lux"
        hass.states.async_set(config["lux_sensor_entity_id"], "50",
                              {"device_class": "illuminance", "unit_of_measurement": "lx"})
    await store.async_set_brightness(t.area, config)
    assert t.manager.status(t.area)["active_stage"] == 1
    assert store.data["rooms"][t.area]["brightness_learned"] == [None, None, None]
    assert t.manager.status(t.area)["learned_lux"] == ([40, None, None] if field == "brightness" else [None, None, None])
    assert len(t.calls) == 1
    if field == "brightness":
        await lux(hass, t, 500, 180)
        assert t.calls[-1].service == "turn_off"
        assert t.manager.status(t.area)["active_stage"] == 0
        assert t.manager.status(t.area)["learned_lux"] == [None, None, None]


@pytest.mark.parametrize("keep_lights", [None, False, True])
async def test_api_disable_owns_only_active_targets(hass, store, brightness, hass_ws_client, keep_lights):
    t = brightness
    hass.data[DOMAIN]["store"] = store
    client = await hass_ws_client(hass)
    async_setup_websocket_api(hass)
    await activate(hass, t, 1)
    options = {} if keep_lights is None else {"keep_lights": keep_lights}
    response = await request(client, "set_enabled", area_id=t.area, enabled=False, **options)
    assert response["success"]
    assert not response["result"]["config"]["enabled"]
    assert response["result"]["status"]["active_stage"] == 0
    assert len(t.calls) == (1 if keep_lights else 2)
    if not keep_lights:
        assert t.calls[-1].data == {"entity_id": t.targets[0]}
        assert t.calls[-1].service == "turn_off"
    await lux(hass, t, 500, 300)
    await t.manager.async_evaluate(t.area)
    assert len(t.calls) == (1 if keep_lights else 2)
    # Repeated disable cannot claim unrelated lights or issue duplicate commands.
    await request(client, "set_enabled", area_id=t.area, enabled=False)
    assert len(t.calls) == (1 if keep_lights else 2)


async def test_disable_via_save_and_repeated_enable(hass, store, brightness):
    t = brightness
    await activate(hass, t)
    await store.async_set_brightness_enabled(t.area, True)
    assert t.manager.status(t.area)["active_stage"] == 3
    assert len(t.calls) == 3
    await store.async_set_brightness(t.area, {**t.config, "enabled": False})
    assert [call.data["entity_id"] for call in t.calls[3:]] == t.targets[::-1]
    assert t.manager.status(t.area)["active_stage"] == 0


async def test_keep_lights_reenable_does_not_reclaim(hass, store, brightness):
    t = brightness
    await activate(hass, t, 1)
    await store.async_set_brightness_enabled(t.area, False, keep_lights=True)
    await store.async_set_brightness_enabled(t.area, True)
    await lux(hass, t, 5, 180)
    assert t.manager.status(t.area)["paused"]
    assert t.manager.status(t.area)["active_stage"] == 0
    assert len(t.calls) == 1


async def test_manual_pause_survives_target_save_and_never_turns_manual_lights_off(hass, store, brightness):
    t = brightness
    await activate(hass, t, 1)
    await hass.services.async_call("light", "turn_on", {"entity_id": t.targets[0]}, blocking=True)
    await hass.async_block_till_done()
    await store.async_set_brightness(t.area, {**t.config, "target_lux": 120})
    assert t.manager.status(t.area)["paused"]
    await store.async_set_brightness_enabled(t.area, False)
    assert len(t.calls) == 2
    assert hass.states.get(t.targets[0]).state == "on"


async def test_disable_stale_sensor_still_turns_owned_lights_off(hass, store, brightness):
    t = brightness
    await activate(hass, t, 1)
    hass.states.async_remove(t.sensor)
    await store.async_set_brightness_enabled(t.area, False)
    assert t.calls[-1].service == "turn_off"
    assert t.manager.status(t.area)["active_stage"] == 0


@pytest.mark.parametrize("change", ["revoked", "moved", "unavailable"])
async def test_cleanup_revalidates_target_safety(hass, store, brightness, change):
    t = brightness
    await activate(hass, t, 1)
    if change == "revoked":
        await store.async_set_lights(t.targets[1:])
    elif change == "moved":
        other = ar.async_get(hass).async_create("Synthetic alternate room")
        er.async_get(hass).async_update_entity(t.targets[0], area_id=other.id)
    else:
        state = hass.states.get(t.targets[0])
        hass.states.async_set(t.targets[0], "unavailable", dict(state.attributes), context=t.manager._context())
    with pytest.raises(ServiceValidationError):
        await store.async_set_brightness_enabled(t.area, False)
    assert len(t.calls) == 1
    assert t.manager.status(t.area)["paused"]
    assert t.manager.status(t.area)["active_stage"] == 1


async def test_failed_cleanup_keeps_remaining_ownership_for_retry(hass, store, brightness):
    t = brightness
    config = {**t.config, "stages": [{"entity_ids": t.targets, "brightness": 120}]}
    await store.async_set_brightness(t.area, config)
    await t.manager.async_evaluate(t.area)
    await hass.async_block_till_done()

    async def fail(_call):
        raise HomeAssistantError("Synthetic failure")

    hass.services.async_register("switch", "turn_off", fail)
    with pytest.raises(ServiceValidationError):
        await store.async_set_brightness_enabled(t.area, False)
    assert t.manager._runtime(t.area)["active"] == [{t.targets[2]}]
    assert store.data["rooms"][t.area]["brightness"] == config
    assert t.manager.status(t.area)["paused"]
    assert t.manager.status(t.area)["last_error"]
    assert len(t.calls) == 5

    @callback
    def capture(call):
        t.calls.append(call)
        hass.states.async_set(t.targets[2], "off", context=call.context)

    hass.services.async_register("switch", "turn_off", capture)
    await store.async_set_brightness_enabled(t.area, False)
    assert len(t.calls) == 6
    assert t.manager.status(t.area)["active_stage"] == 0
    assert not t.manager.status(t.area)["enabled"]


async def test_inflight_activation_finishes_before_disable_cleanup(hass, store, brightness):
    t = brightness
    started, finish = asyncio.Event(), asyncio.Event()

    async def delayed(call):
        started.set()
        await finish.wait()
        t.calls.append(call)
        hass.states.async_set(t.targets[0], "on", dict(hass.states.get(t.targets[0]).attributes), context=call.context)

    hass.services.async_register("light", "turn_on", delayed)
    activation = asyncio.create_task(t.manager.async_evaluate(t.area))
    await started.wait()
    disabling = asyncio.create_task(store.async_set_brightness_enabled(t.area, False))
    await asyncio.sleep(0)
    assert not disabling.done()
    finish.set()
    await asyncio.wait_for(asyncio.gather(activation, disabling), 2)
    await hass.async_block_till_done()
    assert [call.service for call in t.calls] == ["turn_on", "turn_off"]
    assert t.manager.status(t.area)["active_stage"] == 0
    assert not t.manager.status(t.area)["enabled"]


async def test_failed_target_write_preserves_owned_runtime(hass, store, brightness):
    t = brightness
    await activate(hass, t, 1)
    runtime = deepcopy({key: value for key, value in t.manager._runtime(t.area).items() if key != "lock"})
    with patch.object(store._store, "async_save", AsyncMock(side_effect=HomeAssistantError("disk"))):
        with pytest.raises(HomeAssistantError):
            await store.async_set_brightness(t.area, {**t.config, "target_lux": 150})
    assert {key: value for key, value in t.manager._runtime(t.area).items() if key != "lock"} == runtime
    assert store.data["rooms"][t.area]["brightness"] == t.config


@pytest.mark.parametrize("value", [None, 1, "true"])
async def test_keep_lights_requires_boolean(hass, store, brightness, hass_ws_client, value):
    t = brightness
    hass.data[DOMAIN]["store"] = store
    client = await hass_ws_client(hass)
    async_setup_websocket_api(hass)
    response = await request(client, "set_enabled", area_id=t.area, enabled=False, keep_lights=value)
    assert not response["success"]
    assert store.data["rooms"][t.area]["brightness"]["enabled"]


async def test_target_edit_keeps_in_progress_first_learning(hass, store, brightness):
    t = brightness
    await t.manager.async_evaluate(t.area)
    await hass.async_block_till_done()
    pending = t.manager._runtime(t.area)["pending"]
    assert pending is not None
    await store.async_set_brightness(t.area, {**t.config, "target_lux": 120})
    assert t.manager._runtime(t.area)["pending"] is pending
    await lux(hass, t, 50, 10)
    assert t.manager.status(t.area)["learned_lux"] == [40, None, None]
    await lux(hass, t, 500, 170)
    assert t.calls[-1].service == "turn_off"
    assert t.manager.status(t.area)["active_stage"] == 0


async def test_disk_failure_after_cleanup_does_not_restore_false_ownership(hass, store, brightness):
    t = brightness
    await activate(hass, t)
    with patch.object(store._store, "async_save", AsyncMock(side_effect=HomeAssistantError("disk"))):
        with pytest.raises(HomeAssistantError):
            await store.async_set_brightness_enabled(t.area, False)
    assert store.data["rooms"][t.area]["brightness"] == t.config
    assert t.manager.status(t.area)["active_stage"] == 0
    assert [call.service for call in t.calls] == ["turn_on"] * 3 + ["turn_off"] * 3
    await store.async_set_brightness_enabled(t.area, False)
    assert len(t.calls) == 6


@pytest.mark.parametrize("change", ["manual", "revoked"])
async def test_cleanup_rechecks_after_waiting_for_room_lock(hass, store, brightness, change):
    t = brightness
    await activate(hass, t, 1)
    lock = hass.data[DOMAIN]["scene_locks"][t.area]
    await lock.acquire()
    pending = asyncio.create_task(store.async_set_brightness_enabled(t.area, False))
    await asyncio.sleep(0)
    if change == "manual":
        hass.bus.async_fire("call_service", {"domain": "light", "service": "turn_on",
                                            "service_data": {"entity_id": t.targets[0]}})
        await asyncio.sleep(0)
    else:
        await store.async_set_lights(t.targets[1:])
    lock.release()
    with pytest.raises(ServiceValidationError):
        await asyncio.wait_for(pending, 2)
    assert len(t.calls) == 1
    assert t.manager.status(t.area)["paused"]
    assert store.data["rooms"][t.area]["brightness"] == t.config


async def test_concurrent_target_saves_keep_owned_stages(hass, store, brightness):
    t = brightness
    await activate(hass, t, 1)
    await asyncio.gather(
        store.async_set_brightness(t.area, {**t.config, "target_lux": 110}),
        store.async_set_brightness(t.area, {**t.config, "target_lux": 120}),
    )
    assert store.data["rooms"][t.area]["brightness"]["target_lux"] == 120
    assert t.manager.status(t.area)["active_stage"] == 1
    assert t.manager.status(t.area)["learned_lux"] == [40, None, None]
    await lux(hass, t, 500, 180)
    assert t.calls[-1].service == "turn_off"
    assert t.manager.status(t.area)["active_stage"] == 0


async def test_pending_sample_after_stage_brightness_edit_is_activation_local(hass, store, brightness):
    t = brightness
    await t.manager.async_evaluate(t.area)
    await hass.async_block_till_done()
    changed = deepcopy(t.config)
    changed["stages"][0]["brightness"] = 240
    await store.async_set_brightness(t.area, changed)
    await lux(hass, t, 50, 10)
    assert t.manager.status(t.area)["learned_lux"] == [40, None, None]
    assert store.data["rooms"][t.area]["brightness_learned"] == [None, None, None]
    await lux(hass, t, 500, 170)
    assert t.calls[-1].service == "turn_off"
    assert t.manager.status(t.area)["learned_lux"] == [None, None, None]
    await lux(hass, t, 10, 180)
    assert t.calls[-1].data["brightness"] == 240
    await lux(hass, t, 90, 10)
    assert store.data["rooms"][t.area]["brightness_learned"] == [80, None, None]
