# Geändert für Lichtzentrale
"""Motion fixtures contain synthetic entities only and never contact devices."""

from datetime import datetime
from unittest.mock import patch

import pytest
from homeassistant.core import Context, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.lichtzentrale.motion import MotionManager, active_window


@pytest.fixture
async def motion(hass, store):
    area = ar.async_get(hass).async_create("Synthetic motion room").id
    registry = er.async_get(hass)
    targets = []
    for domain in ("light", "switch"):
        entry = registry.async_get_or_create(domain, "shelly", f"motion-{domain}",
                                             original_name=f"Synthetic light {domain}")
        registry.async_update_entity(entry.entity_id, area_id=area)
        targets.append(entry.entity_id)
        hass.states.async_set(entry.entity_id, "off", {
            "supported_color_modes": ["brightness"], "brightness": 150,
        } if domain == "light" else {})
    sensors = ["binary_sensor.synthetic_motion", "binary_sensor.synthetic_presence"]
    for entity in sensors:
        hass.states.async_set(entity, "off", {"device_class": "motion"})
    await store.async_set_lights(targets)
    config = {"enabled": True, "sensor_entity_ids": sensors, "timeout_seconds": 60,
              "dim_before_off": True, "lux_sensor_entity_id": None, "lux_below": None,
              "windows": [{"start": {"type": "time", "value": "00:00"},
                           "end": {"type": "time", "value": "00:00"},
                           "action": {"type": "lights", "entity_ids": targets, "brightness": 150}}]}
    store._data["rooms"][area] = {"motion": config}
    calls = []

    @callback
    def capture(call):
        calls.append(call)
        entity = call.data["entity_id"]
        state = hass.states.get(entity)
        attrs = dict(state.attributes)
        if "brightness" in call.data:
            attrs["brightness"] = call.data["brightness"]
        hass.states.async_set(entity, "on" if call.service == "turn_on" else "off", attrs,
                              context=call.context)

    for domain in ("light", "switch"):
        for service in ("turn_on", "turn_off"):
            hass.services.async_register(domain, service, capture)
    manager = MotionManager(hass, store)
    manager.start()
    yield manager, area, targets, sensors, calls
    await manager.shutdown()


async def change(hass, entity, state, context=None, **attrs):
    previous = hass.states.get(entity)
    hass.states.async_set(entity, state, {**previous.attributes, **attrs}, context=context)
    await hass.async_block_till_done()


async def test_multiple_sensors_last_off_and_dim_restore(hass, motion):
    manager, area, targets, sensors, calls = motion
    await change(hass, sensors[0], "on")
    assert manager.status(area)["active_targets"] == sorted(targets)
    assert not manager.status(area)["paused"]
    assert len(calls) == 2
    await change(hass, sensors[1], "on")
    await change(hass, sensors[0], "off")
    assert manager.status(area)["remaining_seconds"] is None
    assert len(calls) == 2
    await change(hass, sensors[1], "off")
    assert manager.status(area)["remaining_seconds"] == 60
    await manager._expire(area, dim=True)
    await hass.async_block_till_done()
    assert hass.states.get(targets[0]).attributes["brightness"] == 76
    assert calls[-1].domain == "light"
    assert manager.status(area)["dimmed"]
    await change(hass, sensors[0], "on")
    assert hass.states.get(targets[0]).attributes["brightness"] == 150
    assert not manager.status(area)["dimmed"]
    await change(hass, sensors[0], "off")
    await manager._expire(area)
    await hass.async_block_till_done()
    assert all(hass.states.get(e).state == "off" for e in targets)
    assert not manager.status(area)["active_targets"]


async def test_manual_change_pauses_until_confirmed_empty(hass, motion):
    manager, area, targets, sensors, calls = motion
    await change(hass, sensors[0], "on")
    await change(hass, targets[0], "on", brightness=110)
    assert manager.status(area)["paused"]
    before = len(calls)
    await change(hass, sensors[1], "on")
    await manager._expire(area)
    assert manager.status(area)["paused"]
    await change(hass, sensors[0], "off")
    await change(hass, sensors[1], "unavailable")
    await manager._expire(area)
    assert manager.status(area)["paused"]
    assert len(calls) == before
    await change(hass, sensors[1], "off")
    await manager._expire(area)
    assert not manager.status(area)["paused"]
    assert len(calls) == before
    await change(hass, sensors[0], "on")
    assert len(calls) == before + 2


async def test_manual_before_activation_and_own_descendants(hass, motion):
    manager, area, targets, sensors, calls = motion
    await change(hass, targets[0], "on", brightness=100)
    assert manager.status(area)["paused"]
    await change(hass, sensors[0], "on")
    assert not calls
    manager.refresh_config(area)
    context = manager._context()
    await change(hass, targets[0], "on", Context(parent_id=context.id), brightness=110)
    assert not manager.status(area)["paused"]


async def test_unknown_blocks_countdown_and_recovery_restarts(hass, motion):
    manager, area, targets, sensors, calls = motion
    await change(hass, sensors[0], "on")
    await change(hass, sensors[0], "off")
    await change(hass, sensors[1], "unavailable")
    assert manager.status(area)["remaining_seconds"] is None
    await manager._expire(area)
    assert len(calls) == 2
    await change(hass, sensors[1], "off")
    assert manager.status(area)["remaining_seconds"] == 60


async def test_revoked_target_never_switched_off(hass, store, motion):
    manager, area, targets, sensors, calls = motion
    await change(hass, sensors[0], "on")
    await store.async_set_lights([targets[1]])
    await change(hass, sensors[0], "off")
    await manager._expire(area)
    assert calls[-1].data["entity_id"] == targets[1]
    assert hass.states.get(targets[0]).state == "on"


async def test_lux_gate_fails_closed_and_does_not_prevent_off(hass, store, motion):
    manager, area, targets, sensors, calls = motion
    config = store._data["rooms"][area]["motion"]
    config.update(lux_sensor_entity_id="sensor.synthetic_lux", lux_below=20)
    hass.states.async_set("sensor.synthetic_lux", "unavailable",
                          {"device_class": "illuminance", "unit_of_measurement": "lx"})
    await change(hass, sensors[0], "on")
    assert not calls
    await change(hass, sensors[0], "off")
    await change(hass, "sensor.synthetic_lux", "10")
    await change(hass, sensors[0], "on")
    assert len(calls) == 2
    await change(hass, "sensor.synthetic_lux", "100")
    await change(hass, sensors[0], "off")
    await manager._expire(area)
    assert all(hass.states.get(e).state == "off" for e in targets)


async def test_refresh_and_shutdown_cancel_timers(hass, motion):
    manager, area, targets, sensors, calls = motion
    await change(hass, sensors[0], "on")
    await change(hass, sensors[0], "off")
    handles = manager._runtime(area)["timers"][:]
    manager.refresh_config(area)
    assert all(handle.cancelled() for handle in handles)
    assert not manager.status(area)["active_targets"]
    await manager.shutdown()
    await change(hass, sensors[0], "on")
    assert len(calls) == 2


async def test_only_successful_targets_owned(hass, motion):
    manager, area, targets, sensors, calls = motion

    async def failing(call):
        raise RuntimeError("Synthetic failure")

    hass.services.async_register("switch", "turn_on", failing)
    await change(hass, sensors[0], "on")
    assert manager.status(area)["active_targets"] == [targets[0]]
    assert manager.status(area)["last_error"]


def test_clock_windows_midnight_and_solar_missing(hass):
    window = {"start": {"type": "time", "value": "22:00"},
              "end": {"type": "time", "value": "06:00"}, "action": {}}
    assert active_window(hass, [window], datetime(2026, 1, 2, 1, tzinfo=dt_util.DEFAULT_TIME_ZONE)) is window
    assert active_window(hass, [window], datetime(2026, 1, 2, 12, tzinfo=dt_util.DEFAULT_TIME_ZONE)) is None
    window["start"] = {"type": "sun", "event": "sunset", "offset_min": -30}
    with patch("custom_components.lichtzentrale.motion.get_astral_event_date", return_value=None):
        assert active_window(hass, [window]) is None


async def test_timer_callbacks_and_stale_deadline(hass, motion):
    manager, area, targets, sensors, calls = motion
    await change(hass, sensors[0], "on")
    await change(hass, sensors[0], "off")
    handles = manager._runtime(area)["timers"][:]
    # Execute the actual loop callback, not just the expiry implementation.
    expired_callback = handles[-1]._callback
    handles[0]._callback()
    await hass.async_block_till_done()
    assert manager.status(area)["dimmed"]
    await change(hass, sensors[0], "on")
    expired_callback()
    await hass.async_block_till_done()
    assert all(hass.states.get(e).state == "on" for e in targets)
    await change(hass, sensors[0], "off")
    manager._runtime(area)["timers"][-1]._callback()
    await hass.async_block_till_done()
    assert all(hass.states.get(e).state == "off" for e in targets)


async def test_cross_room_selection_and_nightlight_not_brightened(hass, store, motion):
    manager, area, targets, sensors, calls = motion
    other = ar.async_get(hass).async_create("Synthetic second motion room").id
    er.async_get(hass).async_update_entity(targets[0], area_id=other)
    store._data["rooms"][area]["motion"]["windows"][0]["action"]["brightness"] = 20
    # Even artificial brightness metadata must never make a switch dimmable.
    await change(hass, targets[1], "off", manager._context(), brightness=200)
    await change(hass, sensors[0], "on")
    await change(hass, sensors[0], "off")
    before = len(calls)
    await manager._expire(area, dim=True)
    assert len(calls) == before + 1
    assert calls[-1].domain == "light"
    assert calls[-1].data["brightness"] == 20


async def test_scene_dispatch_scoped_and_deleted_scene_reported(hass, store, motion):
    manager, area, targets, sensors, calls = motion
    scene = {"id": "synthetic-scene", "area_id": area, "kind": "snapshot",
             "lights": {targets[0]: {"on": True, "brightness": 90}}, "dynamic": {}}
    store._data["scenes"].append(scene)
    store._data["rooms"][area]["motion"]["windows"][0]["action"] = {
        "type": "scene", "scene_id": scene["id"]}
    await change(hass, sensors[0], "on")
    assert manager.status(area)["active_targets"] == [targets[0]]
    assert len(calls) == 1
    await change(hass, sensors[0], "off")
    await manager._expire(area)
    manager.refresh_config(area)
    store._data["scenes"].clear()
    await change(hass, sensors[0], "on")
    assert manager.status(area)["last_error"]


async def test_adaptive_optional_absence_and_exact_result(hass, store, motion):
    from unittest.mock import AsyncMock

    manager, area, targets, sensors, calls = motion
    store._data["rooms"][area]["motion"]["windows"][0]["action"] = {"type": "adaptive"}
    await change(hass, sensors[0], "on")
    assert not calls
    assert manager.status(area)["last_error"]
    await change(hass, sensors[0], "off")
    with patch("custom_components.lichtzentrale.adaptive.async_turn_on_adaptive",
               AsyncMock(return_value=[targets[0]])):
        await change(hass, sensors[0], "on")
    assert manager.status(area)["active_targets"] == [targets[0]]


async def test_lock_wait_rechecks_occupancy_for_scene(hass, store, motion):
    import asyncio

    from custom_components.lichtzentrale.const import DOMAIN

    manager, area, targets, sensors, calls = motion
    scene = {"id": "synthetic-wait", "area_id": area, "kind": "snapshot",
             "lights": {targets[0]: {"on": True}}, "dynamic": {}}
    store._data["scenes"].append(scene)
    store._data["rooms"][area]["motion"]["windows"][0]["action"] = {
        "type": "scene", "scene_id": scene["id"]}
    lock = asyncio.Lock()
    hass.data.setdefault(DOMAIN, {}).setdefault("scene_locks", {})[area] = lock
    await lock.acquire()
    hass.states.async_set(sensors[0], "on", {"device_class": "motion"})
    for _ in range(4):
        await asyncio.sleep(0)
    hass.states.async_set(sensors[0], "off", {"device_class": "motion"})
    lock.release()
    await hass.async_block_till_done()
    assert not calls


async def test_manual_change_cancels_pending_activation(hass, motion):
    import asyncio

    from custom_components.lichtzentrale.const import DOMAIN

    manager, area, targets, sensors, calls = motion
    lock = asyncio.Lock()
    hass.data.setdefault(DOMAIN, {}).setdefault("selected_light_locks", {})[targets[0]] = lock
    await lock.acquire()
    hass.states.async_set(sensors[0], "on", {"device_class": "motion"})
    for _ in range(4):
        await asyncio.sleep(0)
    hass.states.async_set(targets[0], "on", {"brightness": 100})
    for _ in range(4):
        await asyncio.sleep(0)
    lock.release()
    await hass.async_block_till_done()
    assert manager.status(area)["paused"]
    assert not calls


async def test_restored_sensor_and_lux_block(hass, store, motion):
    manager, area, targets, sensors, calls = motion
    await change(hass, sensors[0], "on", restored=True)
    assert not calls
    assert manager.status(area)["occupied"] is None
    config = store._data["rooms"][area]["motion"]
    config.update(lux_sensor_entity_id="sensor.synthetic_lux", lux_below=20)
    hass.states.async_set("sensor.synthetic_lux", "10", {
        "device_class": "illuminance", "unit_of_measurement": "lx", "restored": True})
    await change(hass, sensors[0], "on", restored=False)
    assert not calls


def test_solar_offset_and_first_window(hass):
    now = datetime(2026, 1, 2, 17, 40, tzinfo=dt_util.DEFAULT_TIME_ZONE)
    window = {"start": {"type": "sun", "event": "sunset", "offset_min": -30},
              "end": {"type": "time", "value": "22:00"}, "action": {}}
    other = {"start": {"type": "time", "value": "00:00"},
             "end": {"type": "time", "value": "00:00"}, "action": {}}

    def solar(hass, event, day):
        return datetime.combine(day, now.time(), now.tzinfo).replace(hour=18, minute=0)

    with patch("custom_components.lichtzentrale.motion.get_astral_event_date", side_effect=solar):
        assert active_window(hass, [window, other], now) is window
        assert active_window(hass, [other, window], now) is other


@pytest.mark.parametrize("change_kind", ["move", "revoke"])
async def test_target_changes_during_lock_wait(hass, store, motion, change_kind):
    import asyncio

    from custom_components.lichtzentrale.const import DOMAIN

    manager, area, targets, sensors, calls = motion
    lock = asyncio.Lock()
    hass.data.setdefault(DOMAIN, {}).setdefault("selected_light_locks", {})[targets[0]] = lock
    await lock.acquire()
    hass.states.async_set(sensors[0], "on", {"device_class": "motion"})
    for _ in range(4):
        await asyncio.sleep(0)
    if change_kind == "move":
        other = ar.async_get(hass).async_create("Synthetic moved room").id
        er.async_get(hass).async_update_entity(targets[0], area_id=other)
    else:
        store._data["settings"]["light_entity_ids"] = []
    lock.release()
    await hass.async_block_till_done()
    # Cross-room selections intentionally permit a move before locks establish
    # their area snapshot. Revocation must never dispatch any target.
    if change_kind == "revoke":
        assert not calls
    else:
        assert manager._runtime(area)["owned"][targets[0]] == other


async def test_restore_final_boundary_rechecks_state_identity(hass, motion):
    manager, area, targets, sensors, calls = motion
    await change(hass, sensors[0], "on")
    await change(hass, sensors[0], "off")
    await manager._expire(area, dim=True)
    await hass.async_block_till_done()
    from custom_components.lichtzentrale.rooms import async_dispatch as real_dispatch

    async def race(hass, commands, **kwargs):
        # Mutation happens after preparation but before state_changed is handled.
        hass.states.async_set(targets[0], "off", dict(hass.states.get(targets[0]).attributes))
        return await real_dispatch(hass, commands, **kwargs)

    before = len(calls)
    with patch("custom_components.lichtzentrale.motion.async_dispatch", side_effect=race):
        await change(hass, sensors[0], "on")
    assert len(calls) == before
    assert hass.states.get(targets[0]).state == "off"


def test_dst_overnight_window(hass):
    from zoneinfo import ZoneInfo

    zone = ZoneInfo("Europe/Berlin")
    window = {"start": {"type": "time", "value": "22:00"},
              "end": {"type": "time", "value": "06:00"}, "action": {}}
    with patch.object(dt_util, "DEFAULT_TIME_ZONE", zone):
        # Both occurrences of the repeated clock hour belong to the same window.
        for fold in (0, 1):
            now = datetime(2026, 10, 25, 2, 30, tzinfo=zone, fold=fold)
            assert active_window(hass, [window], now) is window
        assert active_window(hass, [window], datetime(2026, 3, 29, 4, tzinfo=zone)) is window


@pytest.fixture
async def motion_adaptive(hass, store, motion):
    from types import SimpleNamespace

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    manager, area, targets, sensors, calls = motion
    config = MockConfigEntry(domain="adaptive_lighting")
    config.add_to_hass(hass)
    registry = er.async_get(hass)
    peer = registry.async_get_or_create("light", "synthetic", "unselected-adaptive-peer")
    registry.async_update_entity(peer.entity_id, area_id=area)
    hass.states.async_set(peer.entity_id, "on", {"brightness": 200})
    await store.async_set_lights(targets + [peer.entity_id])
    switch = registry.async_get_or_create("switch", "adaptive_lighting", "motion-primary",
                                          config_entry=config)
    hass.states.async_set(switch.entity_id, "on")
    hass.data["adaptive_lighting"] = {config.entry_id: {"switch": SimpleNamespace(
        entity_id=switch.entity_id, lights=[targets[0], peer.entity_id])}}
    adaptive_calls = []

    @callback
    def capture(call):
        adaptive_calls.append(call)

    hass.services.async_register("adaptive_lighting", "set_manual_control", capture)
    return switch.entity_id, peer.entity_id, adaptive_calls


async def test_nightlight_and_warning_pause_only_selected_adaptive_lamps(hass, motion, motion_adaptive):
    manager, area, targets, sensors, calls = motion
    switch, peer, adaptive_calls = motion_adaptive
    await change(hass, sensors[0], "on")
    assert len(adaptive_calls) == 1
    assert adaptive_calls[0].data == {
        "entity_id": switch, "lights": [targets[0]], "manual_control": True}
    assert hass.states.get(switch).state == "on"
    assert hass.states.get(peer).attributes["brightness"] == 200
    await change(hass, sensors[0], "off")
    await manager._expire(area, dim=True)
    await hass.async_block_till_done()
    assert len(adaptive_calls) == 2
    assert adaptive_calls[-1].data["lights"] == [targets[0]]
    assert calls[-1].data["brightness"] == 76
    await change(hass, sensors[0], "on")
    assert len(adaptive_calls) == 2  # Restore does not accidentally clear manual flags.
    assert calls[-1].data["brightness"] == 150
    assert not manager.status(area)["paused"]


async def test_failed_adaptive_pause_prevents_nightlight_dispatch(hass, motion, motion_adaptive):
    manager, area, targets, sensors, calls = motion

    async def fail(call):
        raise RuntimeError("Synthetic AL failure")

    hass.services.async_register("adaptive_lighting", "set_manual_control", fail)
    await change(hass, sensors[0], "on")
    assert not calls
    assert manager.status(area)["last_error"]


async def test_disabled_adaptive_switch_does_not_receive_manual_flags(hass, motion, motion_adaptive):
    manager, area, targets, sensors, calls = motion
    switch, peer, adaptive_calls = motion_adaptive
    await change(hass, switch, "off")
    await change(hass, sensors[0], "on")
    assert not adaptive_calls
    assert len(calls) == 2


async def test_activation_final_boundary_keeps_manual_change(hass, motion):
    manager, area, targets, sensors, calls = motion
    from custom_components.lichtzentrale.rooms import async_dispatch as real_dispatch

    async def race(hass, commands, **kwargs):
        hass.states.async_set(targets[0], "on", {
            **hass.states.get(targets[0]).attributes, "brightness": 33,
        })
        return await real_dispatch(hass, commands, **kwargs)

    with patch("custom_components.lichtzentrale.motion.async_dispatch", side_effect=race):
        await change(hass, sensors[0], "on")
    assert hass.states.get(targets[0]).attributes["brightness"] == 33
    assert not any(call.data["entity_id"] == targets[0] for call in calls)


@pytest.mark.parametrize("dim", [False, True])
async def test_expiry_waiting_for_target_lock_does_not_consume_new_deadline(hass, motion, dim):
    import asyncio

    from custom_components.lichtzentrale.const import DOMAIN

    manager, area, targets, sensors, calls = motion
    await change(hass, sensors[0], "on")
    await change(hass, sensors[0], "off")
    previous = manager._runtime(area)["deadline"]
    lock = hass.data[DOMAIN]["selected_light_locks"][targets[0]]
    await lock.acquire()
    task = asyncio.create_task(manager._expire(area, dim=dim, deadline=previous))
    await asyncio.sleep(0)
    # Let state listeners run without waiting for the deliberately blocked task.
    hass.states.async_set(sensors[0], "on", {"device_class": "motion"})
    await asyncio.sleep(0)
    hass.states.async_set(sensors[0], "off", {"device_class": "motion"})
    await asyncio.sleep(0)
    current = manager._runtime(area)["deadline"]
    assert current is not None and current != previous
    before = len(calls)
    lock.release()
    await task
    await hass.async_block_till_done()
    assert len(calls) == before
    assert manager._runtime(area)["deadline"] == current
    assert manager.status(area)["active_targets"] == sorted(targets)


async def test_disabled_registry_at_expiry_does_not_keep_stale_deadline(hass, motion):
    manager, area, _, sensors, _ = motion
    registry = er.async_get(hass)
    entry = registry.async_get_or_create("binary_sensor", "synthetic", "disabled-expiry",
                                         suggested_object_id="disabled_expiry")
    hass.states.async_set(entry.entity_id, "off", {"device_class": "motion"})
    manager.store._data["rooms"][area]["motion"]["sensor_entity_ids"].append(entry.entity_id)
    await change(hass, sensors[0], "on")
    await change(hass, sensors[0], "off")
    registry.async_update_entity(entry.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
    await manager._expire(area)
    assert manager.status(area)["remaining_seconds"] is None
    registry.async_update_entity(entry.entity_id, disabled_by=None)
    await change(hass, entry.entity_id, "off", friendly_name="Recovered synthetic sensor")
    assert manager.status(area)["remaining_seconds"] == 60


async def test_adaptive_context_without_parent_keeps_automatic_off(hass, store, motion, motion_adaptive):
    manager, area, targets, sensors, calls = motion
    switch, peer, _ = motion_adaptive
    store._data["rooms"][area]["adaptive_switch"] = switch
    store._data["rooms"][area]["motion"]["windows"][0]["action"] = {"type": "adaptive"}

    @callback
    def apply(call):
        for entity in call.data["lights"]:
            state = hass.states.get(entity)
            hass.states.async_set(entity, "on", {**state.attributes, "brightness": 130},
                                  context=call.context)

    hass.services.async_register("adaptive_lighting", "apply", apply)
    await change(hass, sensors[0], "on")
    assert set(manager.status(area)["active_targets"]) == {targets[0], peer}
    context = Context(id="adapt_lgt_synthetic_periodic")
    assert context.parent_id is None
    await change(hass, targets[0], "on", context, brightness=180, color_temp_kelvin=3500)
    assert not manager.status(area)["paused"]
    await change(hass, sensors[0], "off")
    manager._runtime(area)["timers"][-1]._callback()
    await hass.async_block_till_done()
    assert hass.states.get(targets[0]).state == "off"
    assert hass.states.get(peer).state == "off"
    assert not manager.status(area)["active"]


@pytest.mark.parametrize("prefix", ["adapt_lgt", "adapt_lgt_synthetic"])
async def test_adaptive_context_and_descendant_are_recognized(hass, motion, prefix):
    manager, area, targets, sensors, _ = motion
    await change(hass, sensors[0], "on")
    context = Context(id=prefix)
    await change(hass, targets[0], "on", context, brightness=120)
    await change(hass, targets[0], "on", Context(parent_id=context.id), brightness=110)
    assert not manager.status(area)["paused"]
    await change(hass, targets[0], "off", Context(id="synthetic_manual"))
    assert manager.status(area)["paused"]


@pytest.fixture
async def dynamic_motion(hass, store, motion, request):
    from types import SimpleNamespace

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.lichtzentrale.const import DOMAIN
    from custom_components.lichtzentrale.dynamic_scenes import DynamicSceneManager
    from custom_components.lichtzentrale.scenes import async_save_scene

    manager, area, targets, sensors, calls = motion
    active = DynamicSceneManager(hass, store)
    hass.data.setdefault(DOMAIN, {}).update(store=store, motion=manager, dynamic=active)
    if request.param == "hue":
        entry = MockConfigEntry(domain="hue")
        entry.add_to_hass(hass)
        registry = er.async_get(hass)
        lamp = registry.async_get_or_create("light", "hue", "synthetic-motion-hue-lamp", config_entry=entry)
        hue_scene = registry.async_get_or_create("scene", "hue", "synthetic-motion-hue-scene", config_entry=entry)
        for item in (lamp, hue_scene):
            registry.async_update_entity(item.entity_id, area_id=area)
        hass.states.async_set(lamp.entity_id, "off", {"supported_color_modes": ["xy"], "brightness": 150})
        hass.states.async_set(hue_scene.entity_id, "2026-01-01T00:00:00+00:00", {"is_dynamic": True})
        entry.runtime_data = SimpleNamespace(api=SimpleNamespace(scenes={
            hue_scene.unique_id: SimpleNamespace(actions=[SimpleNamespace(target=SimpleNamespace(
                rtype="light", rid=lamp.unique_id))])}))
        await store.async_set_lights(targets + [lamp.entity_id])
        scene = await async_save_scene(hass, store, {"name": "Synthetic motion bridge scene",
            "area_id": area, "kind": "hue", "hue_scene": hue_scene.entity_id})

        @callback
        def apply_hue(call):
            assert call.data["dynamic"] is True
            hass.states.async_set(lamp.entity_id, "on", {"supported_color_modes": ["xy"],
                "brightness": 150, "dynamics": "dynamic_palette"}, context=call.context)

        hass.services.async_register("hue", "activate_scene", apply_hue)
        target = lamp.entity_id
    else:
        target = targets[0]
        await change(hass, target, "off", manager._context(), supported_color_modes=["xy"])
        scene = await async_save_scene(hass, store, {"name": "Synthetic motion palette",
            "area_id": area, "kind": "palette", "palette_id": "kupfernest",
            "dynamic": {"enabled": True, "interval": 60, "transition": 1}})
    config = store._data["rooms"][area]["motion"]
    config["windows"][0]["action"] = {"type": "scene", "scene_id": scene["id"]}
    # A separate configured target must not inherit the scene-lamp exception.
    config["windows"].append({"start": {"type": "time", "value": "00:00"},
        "end": {"type": "time", "value": "00:00"},
        "action": {"type": "lights", "entity_ids": [targets[1]], "brightness": 100}})
    try:
        yield manager, area, target, sensors, calls, active, scene
    finally:
        await active.shutdown()


@pytest.mark.parametrize("dynamic_motion", ["palette", "hue"], indirect=True)
async def test_motion_dynamic_colors_keep_automatic_off(hass, dynamic_motion):
    manager, area, target, sensors, _, active, _ = dynamic_motion
    await change(hass, sensors[0], "on")
    assert manager.status(area)["active_targets"] == [target]
    if active.active:
        # Exercise an actual local palette tick as well as a contextless device update.
        assert await active.tick(active.active[area], 1)
        await hass.async_block_till_done()
    await change(hass, target, "on", brightness=101, xy_color=[0.3, 0.4], color_mode="xy")
    assert not manager.status(area)["paused"]
    await change(hass, sensors[0], "off")
    await change(hass, target, "on", brightness=102, xy_color=[0.4, 0.3])
    assert not manager.status(area)["paused"]
    manager._runtime(area)["timers"][-1]._callback()
    await hass.async_block_till_done()
    assert hass.states.get(target).state == "off"
    assert not manager.status(area)["active"]
    assert manager._runtime(area)["dynamic_scene"] is None


@pytest.mark.parametrize("dynamic_motion", ["palette", "hue"], indirect=True)
@pytest.mark.parametrize("state", ["off", "unavailable"])
async def test_dynamic_scene_external_power_and_unavailable_still_pause(hass, dynamic_motion, state):
    manager, area, target, sensors, _, _, _ = dynamic_motion
    await change(hass, sensors[0], "on")
    await change(hass, target, state, Context(id="synthetic_external"))
    assert manager.status(area)["paused"]
    assert manager._runtime(area)["dynamic_scene"] is None


@pytest.mark.parametrize("dynamic_motion", ["palette", "hue"], indirect=True)
async def test_stopped_dynamic_scene_no_longer_exempts_manual_color(hass, dynamic_motion):
    manager, area, target, sensors, _, active, _ = dynamic_motion
    await change(hass, sensors[0], "on")
    if active.active:
        await active.stop(area)
        await change(hass, target, "on", brightness=100)
    else:
        await change(hass, target, "on", brightness=100, dynamics="none")
    assert manager.status(area)["paused"]


@pytest.mark.parametrize("dynamic_motion", ["palette", "hue"], indirect=True)
async def test_dynamic_exception_does_not_cover_other_configured_targets(hass, motion, dynamic_motion):
    manager, area, _, sensors, _, _, _ = dynamic_motion
    unrelated_switch = motion[2][1]
    await change(hass, sensors[0], "on")
    await change(hass, unrelated_switch, "on")
    assert manager.status(area)["paused"]


async def test_static_scene_color_changes_still_pause(hass, store, motion):
    from custom_components.lichtzentrale.scenes import async_save_scene

    manager, area, target_ids, sensors, _ = motion
    scene = await async_save_scene(hass, store, {"name": "Synthetic static motion scene",
        "area_id": area, "kind": "snapshot", "lights": {target_ids[0]: {"on": True, "brightness": 90}}})
    store._data["rooms"][area]["motion"]["windows"][0]["action"] = {"type": "scene", "scene_id": scene["id"]}
    await change(hass, sensors[0], "on")
    await change(hass, target_ids[0], "on", brightness=100)
    assert manager.status(area)["paused"]


@pytest.mark.parametrize("dynamic_motion", ["palette"], indirect=True)
async def test_replaced_local_dynamic_run_is_not_motion_owned(hass, dynamic_motion):
    manager, area, target, sensors, _, active, scene = dynamic_motion
    await change(hass, sensors[0], "on")
    await active.start(scene, Context(id="synthetic_external_scene"), [target])
    await change(hass, target, "on", brightness=110)
    assert manager.status(area)["paused"]


@pytest.mark.parametrize("dynamic_motion", ["palette", "hue"], indirect=True)
async def test_config_refresh_clears_dynamic_exception(hass, dynamic_motion):
    manager, area, target, sensors, _, _, _ = dynamic_motion
    await change(hass, sensors[0], "on")
    manager.refresh_config(area)
    assert manager._runtime(area)["dynamic_scene"] is None
    await change(hass, target, "on", brightness=110)
    assert manager.status(area)["paused"]
