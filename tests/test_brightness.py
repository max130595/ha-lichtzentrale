# Geändert für Lichtzentrale
"""Synthetic, device-free regulator tests with real HA events and service dispatch."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.core import Context, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.lichtzentrale.brightness import BrightnessManager
from custom_components.lichtzentrale.const import DOMAIN
from custom_components.lichtzentrale.rooms import async_toggle_room


@pytest.fixture
async def brightness(hass, store, monkeypatch):
    area = ar.async_get(hass).async_create("Synthetic brightness room").id
    registry = er.async_get(hass)
    targets = []
    for index, domain in enumerate(("light", "light", "switch")):
        entry = registry.async_get_or_create(domain, "shelly", f"brightness-{index}",
                                             original_name=f"Synthetic stage light {index}")
        registry.async_update_entity(entry.entity_id, area_id=area)
        targets.append(entry.entity_id)
        hass.states.async_set(entry.entity_id, "off", {"supported_color_modes": ["color_temp"],
            "brightness": 120, "color_temp_kelvin": 3000} if domain == "light" else {})
    sensor = "sensor.synthetic_brightness_lux"
    hass.states.async_set(sensor, "10", {"device_class": "illuminance", "unit_of_measurement": "lx"})
    await store.async_set_lights(targets)
    config = {"enabled": True, "lux_sensor_entity_id": sensor, "target_lux": 100,
              "hysteresis_lux": 10, "min_interval_seconds": 180, "time_window": None,
              "person_entity_ids": [], "stages": [
                  {"entity_ids": [entity], "brightness": 120 if entity.startswith("light.") else None}
                  for entity in targets]}
    await store.async_set_brightness(area, config)
    calls, time = [], [1000.0]
    monkeypatch.setattr("custom_components.lichtzentrale.brightness.monotonic", lambda: time[0])

    @callback
    def capture(call):
        calls.append(call)
        entity = call.data["entity_id"]
        state = hass.states.get(entity)
        attrs = dict(state.attributes)
        attrs.update({key: call.data[key] for key in ("brightness", "color_temp_kelvin") if key in call.data})
        hass.states.async_set(entity, "on" if call.service == "turn_on" else "off", attrs, context=call.context)

    for domain in ("light", "switch"):
        for service in ("turn_on", "turn_off"):
            hass.services.async_register(domain, service, capture)
    manager = BrightnessManager(hass, store)
    hass.data.setdefault(DOMAIN, {})["brightness"] = manager
    await hass.async_block_till_done()
    manager.start()
    yield SimpleNamespace(manager=manager, area=area, targets=targets, sensor=sensor,
                          config=config, calls=calls, time=time)
    await manager.shutdown()


async def lux(hass, test, value, seconds=0):
    test.time[0] += seconds
    hass.states.async_set(test.sensor, str(value), {"device_class": "illuminance", "unit_of_measurement": "lx"})
    await hass.async_block_till_done()


async def test_cumulative_stages_learning_hysteresis_and_reverse_removal(hass, store, brightness):
    t = brightness
    await t.manager.async_evaluate(t.area)
    await hass.async_block_till_done()
    assert len(t.calls) == 1
    assert t.manager.status(t.area)["active_stage"] == 1
    assert not t.manager.status(t.area)["paused"]
    await lux(hass, t, 50, 10)
    assert t.manager.status(t.area)["learned_lux"] == [40, None, None]
    await lux(hass, t, 51, 169)
    assert len(t.calls) == 1
    await lux(hass, t, 50, 1)
    assert len(t.calls) == 2
    await lux(hass, t, 80, 10)
    assert t.manager.status(t.area)["learned_lux"] == [40, 30, None]
    await lux(hass, t, 79, 170)
    assert len(t.calls) == 3
    assert t.calls[-1].domain == "switch"
    assert t.calls[-1].data == {"entity_id": t.targets[2]}
    await lux(hass, t, 140, 10)
    await lux(hass, t, 141, 170)
    assert len(t.calls) == 3  # Bright because of our own light; removing it would be too dark.
    await lux(hass, t, 200)
    assert len(t.calls) == 4
    assert t.calls[-1].service == "turn_off"
    assert t.calls[-1].data == {"entity_id": t.targets[2]}
    await lux(hass, t, 180, 180)
    assert t.calls[-1].data == {"entity_id": t.targets[1]}
    assert t.manager.status(t.area)["active_stage"] == 1
    reloaded = type(store)(hass)
    await reloaded.async_load()
    assert reloaded.data["rooms"][t.area]["brightness_learned"] == [40, 30, 61]


async def test_manual_unchanged_command_pauses_and_room_off_resumes(hass, brightness):
    t = brightness
    await t.manager.async_evaluate(t.area)
    await hass.async_block_till_done()
    await hass.services.async_call("light", "turn_on", {"entity_id": t.targets[0], "brightness": 120}, blocking=True)
    await hass.async_block_till_done()
    assert t.manager.status(t.area)["paused"]
    before = len(t.calls)
    await lux(hass, t, 5, 300)
    assert len(t.calls) == before
    await async_toggle_room(hass, t.manager.store, t.area, False)
    await hass.async_block_till_done()
    assert not t.manager.status(t.area)["paused"]
    before = len(t.calls)
    await lux(hass, t, 4, 179)
    assert len(t.calls) == before
    await lux(hass, t, 3, 1)
    assert len(t.calls) == before + 1


async def test_manual_scene_state_change_and_metadata(hass, brightness):
    t = brightness
    state = hass.states.get(t.targets[0])
    hass.states.async_set(t.targets[0], "off", {**state.attributes, "friendly_name": "Synthetic new label"})
    await hass.async_block_till_done()
    assert not t.manager.status(t.area)["paused"]
    hass.states.async_set(t.targets[0], "on", {**state.attributes, "brightness": 77}, context=Context())
    await hass.async_block_till_done()
    assert t.manager.status(t.area)["paused"]
    await t.manager.async_evaluate(t.area)
    assert not t.calls


async def test_missing_sensor_and_person_fail_closed(hass, store, brightness):
    t = brightness
    hass.states.async_set("person.synthetic_resident", "unknown")
    config = {**t.config, "person_entity_ids": ["person.synthetic_resident"]}
    await store.async_set_brightness(t.area, config)
    await t.manager.async_evaluate(t.area)
    assert not t.calls
    hass.states.async_set("person.synthetic_resident", "home")
    await hass.async_block_till_done()
    assert len(t.calls) == 1
    await lux(hass, t, "unavailable", 200)
    assert len(t.calls) == 1
    await lux(hass, t, "nan")
    assert len(t.calls) == 1
    await lux(hass, t, -1)
    assert len(t.calls) == 1


async def test_known_departure_sheds_only_owned_stage(hass, store, brightness):
    t = brightness
    hass.states.async_set("person.synthetic_resident", "home")
    await store.async_set_brightness(t.area, {**t.config, "person_entity_ids": ["person.synthetic_resident"]})
    await t.manager.async_evaluate(t.area)
    await hass.async_block_till_done()
    await lux(hass, t, 50, 10)
    t.time[0] += 170
    hass.states.async_set("person.synthetic_resident", "unknown")
    await hass.async_block_till_done()
    assert len(t.calls) == 1
    hass.states.async_set("person.synthetic_resident", "not_home")
    await hass.async_block_till_done()
    assert len(t.calls) == 2
    assert t.calls[-1].data == {"entity_id": t.targets[0]}
    assert t.calls[-1].service == "turn_off"


async def test_next_daily_window_releases_pause_even_without_closed_tick(hass, store, brightness):
    t = brightness
    await store.async_set_brightness(t.area, {**t.config, "time_window": {
        "after": {"type": "time", "value": "06:00"}, "before": {"type": "time", "value": "06:00"}}})
    now = dt_util.now().replace(hour=12)
    with patch("custom_components.lichtzentrale.brightness.dt_util.now", return_value=now):
        await t.manager.async_evaluate(t.area)
        await hass.async_block_till_done()
        t.manager.pause(t.area)
        await t.manager.async_evaluate(t.area)
        assert t.manager.status(t.area)["paused"]
    with patch("custom_components.lichtzentrale.brightness.dt_util.now", return_value=now + timedelta(days=1)):
        t.time[0] += 86400
        await t.manager.async_evaluate(t.area)
        await hass.async_block_till_done()
        assert not t.manager.status(t.area)["paused"]
        assert len(t.calls) == 2


async def test_unknown_learning_never_switches_off_due_to_own_light(hass, brightness):
    t = brightness
    await t.manager.async_evaluate(t.area)
    await hass.async_block_till_done()
    await lux(hass, t, 500, 200)  # No timely sample; unknown contribution cannot justify removal.
    assert len(t.calls) == 1
    assert t.manager.status(t.area)["learned_lux"] == [None, None, None]
    assert t.manager.status(t.area)["last_error"]


async def test_revoke_and_room_move_while_waiting_for_lock(hass, store, brightness):
    t = brightness
    lock = asyncio.Lock()
    hass.data[DOMAIN].setdefault("scene_locks", {})[t.area] = lock
    await lock.acquire()
    task = hass.async_create_task(t.manager.async_evaluate(t.area))
    await asyncio.sleep(0)
    await store.async_set_lights(t.targets[1:])
    lock.release()
    with pytest.raises(Exception, match="freigegeben"):
        await task
    assert not t.calls


async def test_manual_pause_while_waiting_for_lock(hass, brightness):
    t = brightness
    lock = asyncio.Lock()
    hass.data[DOMAIN].setdefault("scene_locks", {})[t.area] = lock
    await lock.acquire()
    task = hass.async_create_task(t.manager.async_evaluate(t.area))
    await asyncio.sleep(0)
    t.manager.pause(t.area)
    lock.release()
    await task
    assert not t.calls


async def test_partial_failure_pauses_without_false_active_status(hass, store, brightness):
    t = brightness
    config = {**t.config, "stages": [{"entity_ids": t.targets, "brightness": 120}]}
    await store.async_set_brightness(t.area, config)

    async def fail(_call):
        raise RuntimeError("Synthetic device failure")

    hass.services.async_register("switch", "turn_on", fail)
    await t.manager.async_evaluate(t.area)
    await hass.async_block_till_done()
    assert t.manager.status(t.area)["paused"]
    assert t.manager.status(t.area)["last_error"]
    assert t.manager.status(t.area)["active_stage"] == 0
    before = len(t.calls)
    await lux(hass, t, 500, 200)
    assert len(t.calls) == before


async def test_restart_edit_disable_and_shutdown_do_not_reclaim_on_light(hass, store, brightness):
    t = brightness
    await t.manager.async_evaluate(t.area)
    await hass.async_block_till_done()
    t.manager.refresh_config(t.area)
    t.time[0] += 180
    await t.manager.async_evaluate(t.area)
    assert t.manager.status(t.area)["paused"]
    assert len(t.calls) == 1
    await store.async_set_brightness_enabled(t.area, False)
    await lux(hass, t, 1, 300)
    await t.manager.async_evaluate(t.area)
    assert len(t.calls) == 1
    await t.manager.shutdown()
    await lux(hass, t, 2, 300)
    assert len(t.calls) == 1


async def test_pause_before_first_window_resumes_at_next_beginning(hass, store, brightness):
    t = brightness
    await store.async_set_brightness(t.area, {**t.config, "time_window": {
        "after": {"type": "time", "value": "18:00"}, "before": {"type": "time", "value": "23:00"}}})
    now = dt_util.now().replace(hour=17, minute=0)
    with patch("custom_components.lichtzentrale.brightness.dt_util.now", return_value=now):
        t.manager.pause(t.area)
        await t.manager.async_evaluate(t.area)
        assert t.manager.status(t.area)["paused"]
        assert not t.calls
    with patch("custom_components.lichtzentrale.brightness.dt_util.now", return_value=now.replace(hour=18)):
        await t.manager.async_evaluate(t.area)
        await hass.async_block_till_done()
        assert not t.manager.status(t.area)["paused"]
        assert len(t.calls) == 1


async def test_threshold_rechecked_after_waiting_for_lock(hass, brightness):
    t = brightness
    lock = asyncio.Lock()
    hass.data[DOMAIN].setdefault("scene_locks", {})[t.area] = lock
    await lock.acquire()
    task = hass.async_create_task(t.manager.async_evaluate(t.area))
    await asyncio.sleep(0)
    hass.states.async_set(t.sensor, "500", dict(hass.states.get(t.sensor).attributes))
    lock.release()
    await task
    await hass.async_block_till_done()
    assert not t.calls


@pytest.mark.parametrize("selector", ["area", "all", "entity"])
async def test_targeted_manual_noop_commands_pause(hass, brightness, selector):
    t = brightness
    data = {"area_id": t.area} if selector == "area" else {"entity_id": "all" if selector == "all" else t.targets[0]}
    hass.bus.async_fire("call_service", {"domain": "light", "service": "turn_on", "service_data": data})
    await hass.async_block_till_done()
    assert t.manager.status(t.area)["paused"]


async def test_adaptive_color_only_service_is_not_manual_but_brightness_is(hass, brightness):
    t = brightness
    await t.manager.async_evaluate(t.area)
    await hass.async_block_till_done()
    await hass.services.async_call("light", "turn_on", {"entity_id": t.targets[0], "color_temp_kelvin": 4000},
                                  blocking=True, context=Context(id="adapt_lgt_synthetic_color"))
    await hass.async_block_till_done()
    assert not t.manager.status(t.area)["paused"]
    await hass.services.async_call("light", "turn_on", {"entity_id": t.targets[0], "brightness": 77},
                                  blocking=True, context=Context(id="adapt_lgt_synthetic_brightness"))
    await hass.async_block_till_done()
    assert t.manager.status(t.area)["paused"]


async def test_adaptive_white_does_not_apply_brightness_or_other_targets(hass, store, brightness):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    t = brightness
    config = MockConfigEntry(domain="adaptive_lighting")
    config.add_to_hass(hass)
    switch = er.async_get(hass).async_get_or_create("switch", "adaptive_lighting", "synthetic-brightness-main", config_entry=config)
    hass.states.async_set(switch.entity_id, "on", {"color_temp_kelvin": 4200})
    hass.data["adaptive_lighting"] = {config.entry_id: {"switch": SimpleNamespace(entity_id=switch.entity_id, lights=t.targets[:2])}}
    al_calls = []

    @callback
    def capture(call):
        al_calls.append(call)

    hass.services.async_register("adaptive_lighting", "apply", capture)
    hass.services.async_register("adaptive_lighting", "set_manual_control", capture)
    await store.async_update_room(t.area, {"adaptive_switch": switch.entity_id})
    await t.manager.async_evaluate(t.area)
    await hass.async_block_till_done()
    assert len(al_calls) == 1
    assert al_calls[0].service == "set_manual_control"
    assert al_calls[0].data == {"entity_id": switch.entity_id, "lights": [t.targets[0]], "manual_control": True}
    assert t.calls[0].data == {"entity_id": t.targets[0], "brightness": 120, "color_temp_kelvin": 4200}
    assert not t.manager.status(t.area)["paused"]


async def test_learning_invalidated_while_waiting_for_storage(hass, store, brightness):
    t = brightness
    await t.manager.async_evaluate(t.area)
    await hass.async_block_till_done()
    t.time[0] += 10
    await store._lock.acquire()
    hass.states.async_set(t.sensor, "50", dict(hass.states.get(t.sensor).attributes))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    t.manager.pause(t.area)
    store._lock.release()
    await hass.async_block_till_done()
    assert store.data["rooms"][t.area]["brightness_learned"] == [None, None, None]


async def test_sensor_gap_invalidates_learning(hass, brightness):
    t = brightness
    await t.manager.async_evaluate(t.area)
    await hass.async_block_till_done()
    await lux(hass, t, "unavailable", 5)
    await lux(hass, t, 90, 10)
    assert t.manager.status(t.area)["learned_lux"] == [None, None, None]


async def test_one_stage_completes_if_own_first_lamp_changes_lux(hass, store, brightness):
    t = brightness
    await store.async_set_brightness(t.area, {**t.config, "stages": [{"entity_ids": t.targets, "brightness": 100}]})

    @callback
    def capture(call):
        t.calls.append(call)
        entity = call.data["entity_id"]
        hass.states.async_set(entity, "on", dict(hass.states.get(entity).attributes), context=call.context)
        hass.states.async_set(t.sensor, "500", dict(hass.states.get(t.sensor).attributes))

    hass.services.async_register("light", "turn_on", capture)
    await t.manager.async_evaluate(t.area)
    await hass.async_block_till_done()
    assert len(t.calls) == 3
    assert not t.manager.status(t.area)["paused"]
    assert t.manager.status(t.area)["active_stage"] == 1


async def test_window_closing_sheds_without_waiting_for_learning(hass, store, brightness):
    t = brightness
    await store.async_set_brightness(t.area, {**t.config, "min_interval_seconds": 5, "time_window": {
        "after": {"type": "time", "value": "18:00"}, "before": {"type": "time", "value": "23:00"}}})
    now = dt_util.now().replace(hour=22, minute=59)
    with patch("custom_components.lichtzentrale.brightness.dt_util.now", return_value=now):
        await t.manager.async_evaluate(t.area)
        await hass.async_block_till_done()
        assert t.manager._runtime(t.area)["pending"]
    with patch("custom_components.lichtzentrale.brightness.dt_util.now", return_value=now.replace(hour=23)):
        t.time[0] += 60
        await t.manager.async_evaluate(t.area)
        await hass.async_block_till_done()
        assert len(t.calls) == 2
        assert t.calls[-1].service == "turn_off"
