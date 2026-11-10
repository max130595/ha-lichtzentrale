# Geändert für Lichtzentrale
"""Vacation ownership and timer lifecycle using synthetic HA devices only."""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import test_bindings as binding_tests
from homeassistant.core import Context, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from custom_components.lichtzentrale.vacation import VacationManager
from custom_components.lichtzentrale.vacation_config import default_vacation_config

rig = binding_tests.rig


@pytest.fixture
async def vacation(hass, store, rig):
    config = default_vacation_config()
    config["rooms"] = [{"area_id": rig["area"], "type": "living", "weight": 1,
                        "on_behavior": {"mode": "brightness", "brightness": 80}}]
    await store.async_update_vacation({"config": config})
    calls = []
    @callback
    def control(call):
        calls.append(call)
        entities = call.data["entity_id"]
        for entity in [entities] if isinstance(entities, str) else entities:
            state = hass.states.get(entity)
            hass.states.async_set(entity, "off" if call.service == "turn_off" else "on",
                {**state.attributes, **{k: v for k, v in call.data.items() if k != "entity_id"}}, context=call.context)
    for domain in ("light", "switch"):
        for service in ("turn_on", "turn_off"):
            hass.services.async_register(domain, service, control)
    for entity in rig["lights"]:
        state = hass.states.get(entity)
        hass.states.async_set(entity, "off", state.attributes)
    await hass.async_block_till_done()
    manager = VacationManager(hass, store)
    hass.data["lichtzentrale"]["vacation"] = manager
    manager.start()
    await hass.async_block_till_done()
    yield manager, calls
    await manager.shutdown()


async def test_test_runs_five_minutes_and_only_own_lamps_off(hass, store, rig, vacation):
    manager, calls = vacation
    preexisting = rig["lights"][0]
    hass.states.async_set(preexisting, "on", hass.states.get(preexisting).attributes)
    await manager.async_test()
    assert manager.paused and manager.status()["testing"]
    assert not store.data["vacation"]["enabled"]
    assert len(manager._owned) == len(rig["lights"]) - 1
    assert (_instant(manager._plan[-1]["end"]) - _instant(manager._plan[0]["start"])).total_seconds() == 300
    await manager.async_set_enabled(False)
    assert hass.states.get(preexisting).state == "on"
    assert all(hass.states.get(e).state == "off" for e in rig["lights"] if e != preexisting)
    assert all("brightness" not in c.data for c in calls if c.domain == "switch")


def _instant(value):
    return dt_util.parse_datetime(value)


async def test_manual_service_and_attribute_reports(hass, rig, vacation):
    manager, calls = vacation
    await manager.async_test()
    entity = rig["lights"][0]
    state = hass.states.get(entity)
    context = Context()
    manager._changed(SimpleNamespace(data={"entity_id": entity, "old_state": state,
        "new_state": SimpleNamespace(state="on", attributes={"brightness": 79}, context=context)}))
    assert entity in manager._owned  # contextless Zigbee report is not manual.
    await hass.services.async_call("light", "turn_on", {"entity_id": entity, "brightness": 170}, blocking=True, context=Context())
    await hass.async_block_till_done()
    assert entity not in manager._owned
    await manager.async_set_enabled(False)
    assert hass.states.get(entity).state == "on"


async def test_button_removes_room_for_section(hass, rig, vacation):
    manager, calls = vacation
    await manager.async_test()
    await manager.manual_targets(entity_ids=[rig["lights"][0]])
    assert rig["area"] in manager.status()["excluded"]
    assert not manager._owned
    await manager.async_set_enabled(False)
    assert all(hass.states.get(e).state == "on" for e in rig["lights"])


async def test_revoked_grant_cannot_be_switched_off(hass, store, rig, vacation):
    manager, calls = vacation
    await manager.async_test()
    revoked = rig["lights"][0]
    await store.async_set_lights([e for e in rig["lights"] if e != revoked])
    calls.clear()
    await manager.async_set_enabled(False)
    assert not any(c.data.get("entity_id") == revoked for c in calls)
    assert hass.states.get(revoked).state == "on"


async def test_test_expires_and_until_is_preserved(hass, store, rig, vacation):
    manager, calls = vacation
    await manager.async_test()
    end = manager._test_until
    with patch("custom_components.lichtzentrale.vacation.dt_util.utcnow", return_value=end + timedelta(seconds=1)):
        await manager._tick()
    assert not manager.paused
    future = (dt_util.now().date() + timedelta(days=3)).isoformat()
    await store.async_update_vacation({"until": future})
    with patch("custom_components.lichtzentrale.vacation_planner.build_plan", return_value=[]):
        await manager.async_set_enabled(True)
    assert store.data["vacation"]["until"] == future
    with pytest.raises(ServiceValidationError):
        await manager.async_test()
    await manager.async_set_enabled(False, until=None)
    assert store.data["vacation"]["until"] is None


async def test_enddate_disables_and_restart_never_replays_test(hass, store, rig, vacation):
    manager, calls = vacation
    yesterday = (dt_util.now().date() - timedelta(days=1)).isoformat()
    await store.async_update_vacation({"enabled": True, "until": yesterday})
    await manager._tick()
    assert not store.data["vacation"]["enabled"]
    await manager.async_test()
    await manager.shutdown()
    restarted = VacationManager(hass, store)
    hass.data["lichtzentrale"]["vacation"] = restarted
    restarted.start()
    await hass.async_block_till_done()
    assert not restarted.paused
    assert restarted.status()["plan"] == []
    await restarted.shutdown()


async def test_user_attribute_change_releases_ownership(hass, rig, vacation):
    manager, calls = vacation
    await manager.async_test()
    entity = rig["lights"][0]
    state = hass.states.get(entity)
    hass.states.async_set(entity, "on", {**state.attributes, "brightness": 33}, context=Context(user_id="synthetic-user"))
    await hass.async_block_till_done()
    assert entity not in manager._owned
    await manager.async_set_enabled(False)
    assert hass.states.get(entity).state == "on"


async def test_empty_positive_weight_test_is_rejected(hass, store, rig, vacation):
    manager, calls = vacation
    config = manager.config
    config["rooms"][0]["weight"] = 0
    await manager.async_save_config(config)
    with pytest.raises(ServiceValidationError):
        await manager.async_test()
    assert not calls


async def test_save_end_date_does_not_enable_mode(hass, store, rig, vacation):
    manager, calls = vacation
    future = (dt_util.now().date() + timedelta(days=2)).isoformat()
    status = await manager.async_save_config(manager.config, until=future)
    assert status["until"] == future
    assert not status["enabled"] and not status["paused"]
    assert not calls


async def test_restart_replans_without_replaying_old_on(hass, store, rig, vacation):
    manager, calls = vacation
    now = dt_util.utcnow()
    with patch("custom_components.lichtzentrale.vacation_planner.build_plan", return_value=[]):
        await manager.async_set_enabled(True)
    await manager.shutdown()
    # Old no-longer-owned state must never be acquired just because it is ON.
    for entity in rig["lights"]:
        state = hass.states.get(entity)
        hass.states.async_set(entity, "on", state.attributes, context=Context())
    restarted = VacationManager(hass, store)
    hass.data["lichtzentrale"]["vacation"] = restarted
    plan = [{"area_id": rig["area"], "section": "evening", "section_id": "synthetic-evening",
             "start": (now - timedelta(minutes=2)).isoformat(), "end": (now - timedelta(minutes=1)).isoformat(),
             "on_behavior": {"mode": "last"}}]
    calls.clear()
    with patch("custom_components.lichtzentrale.vacation_planner.build_plan", return_value=plan) as build:
        restarted.start()
        await hass.async_block_till_done()
        assert build.call_count == 1
    assert restarted.paused and not calls and not restarted._owned
    await restarted.async_set_enabled(False)
    assert not calls
    await restarted.shutdown()


async def test_scene_script_and_nonpersistent_dynamic(hass, store, rig, vacation):
    from custom_components.lichtzentrale.dynamic_scenes import DynamicSceneManager
    from custom_components.lichtzentrale.scenes import async_save_scene

    manager, calls = vacation
    hass.states.async_set("script.synthetic_vacation_music", "off")
    scripts = []
    @callback
    def script(call):
        scripts.append(call)
    hass.services.async_register("script", "turn_on", script)
    scene = await async_save_scene(hass, store, {
        "name": "Synthetic vacation scene", "area_id": rig["area"], "kind": "palette",
        "palette_id": "kupfernest", "brightness": 80,
        "start_script": "script.synthetic_vacation_music",
        "dynamic": {"enabled": True, "interval": 30, "transition": 10, "welle": False},
    })
    config = manager.config
    config["rooms"][0]["on_behavior"] = {"mode": "scene", "scene_id": scene["id"]}
    await manager.async_save_config(config)
    dynamic = DynamicSceneManager(hass, store)
    hass.data["lichtzentrale"]["dynamic"] = dynamic
    try:
        await manager.async_test()
        await hass.async_block_till_done()
        assert len(scripts) == 1
        assert rig["area"] in dynamic.active
        assert not dynamic.active[rig["area"]]["persist"]
        assert not store.data.get("active_dynamic")
        run = dynamic.active[rig["area"]]
        assert rig["lights"][-1].startswith("switch.")
        assert rig["lights"][-1] not in manager._owned
        before = len(calls)
        for offset in range(1, 4):
            assert await dynamic.tick(run, offset)
        assert len(calls) > before
        # A released individual lamp leaves the run, not the whole room.
        manual = rig["lights"][0]
        await hass.services.async_call("light", "turn_on", {"entity_id": manual, "brightness": 99}, blocking=True, context=Context())
        await hass.async_block_till_done()
        assert manual in run["excluded"] and manual not in manager._owned
        assert await dynamic.tick(run, 4)
        await manager.async_set_enabled(False)
        assert not dynamic.active
    finally:
        await dynamic.shutdown()


async def test_group_manual_service_releases_members(hass, rig, vacation):
    manager, calls = vacation
    await manager.async_test()
    entity = rig["lights"][0]
    hass.states.async_set("light.synthetic_group", "on", {"entity_id": [entity]})
    manager._called(SimpleNamespace(context=Context(), data={"domain": "light", "service": "turn_on",
        "service_data": {"entity_id": "light.synthetic_group", "brightness": 170}}))
    assert entity not in manager._owned
    await manager.async_set_enabled(False)
    assert hass.states.get(entity).state == "on"


async def test_failed_off_keeps_ownership_for_retry(hass, rig, vacation):
    from homeassistant.exceptions import HomeAssistantError
    manager, calls = vacation
    await manager.async_test()
    @callback
    def fail(call):
        raise HomeAssistantError("synthetic unavailable")
    hass.services.async_register("light", "turn_off", fail)
    await manager.async_set_enabled(False)
    assert manager._owned
    assert manager.status()["last_error"]
    @callback
    def recover(call):
        entity = call.data["entity_id"]
        hass.states.async_set(entity, "off", hass.states.get(entity).attributes, context=call.context)
    hass.services.async_register("light", "turn_off", recover)
    await manager.async_set_enabled(False)
    assert not manager._owned


async def test_manual_exclusion_before_first_visit(hass, rig, vacation):
    manager, calls = vacation
    await manager.async_test()
    now = dt_util.utcnow()
    manager._plan[0].update(start=(now + timedelta(minutes=1)).isoformat(),
        section_start=(now - timedelta(minutes=1)).isoformat(), section_end=(now + timedelta(minutes=5)).isoformat())
    manager._active.clear()
    await manager.manual_targets(rig["area"])
    assert rig["area"] in manager.status()["excluded"]


async def test_vacation_commands_use_shared_five_per_second_limiter(hass, rig, vacation):
    import asyncio

    from custom_components.lichtzentrale.rooms import async_dispatch
    manager, calls = vacation
    context = Context()
    manager._contexts.add(context.id)
    times = []
    @callback
    def timed(call):
        times.append(asyncio.get_running_loop().time())
    hass.services.async_register("light", "turn_on", timed)
    commands = [("light", "turn_on", {"entity_id": rig["lights"][0]}) for _ in range(6)]
    result = await async_dispatch(hass, commands, context=context)
    assert len(result["applied"]) == 6
    assert all(b - a >= .2 for a, b in zip(times, times[1:]))


@pytest.mark.parametrize("previous_effect", [None, "candle"])
async def test_snapshot_effect_survives_own_state_updates(hass, store, rig, vacation, previous_effect):
    """Real HA state updates after stop/color must not invalidate delayed effect."""
    from custom_components.lichtzentrale.scenes import async_save_scene
    manager, calls = vacation
    entity = rig["lights"][0]
    state = hass.states.get(entity)
    hass.states.async_set(entity, "off", {**state.attributes,
        "effect_list": ["sparkle", "candle", "stop_hue_effect"], "effect": previous_effect})
    scene = await async_save_scene(hass, store, {
        "name": "Synthetic vacation effect", "area_id": rig["area"], "kind": "snapshot",
        "lights": {entity: {"on": True, "brightness": 140}},
        "lamp_settings": {entity: {"mode": "cycle", "effect": "sparkle"}},
    })
    config = manager.config
    config["rooms"][0]["on_behavior"] = {"mode": "scene", "scene_id": scene["id"]}
    await manager.async_save_config(config)
    with patch("custom_components.lichtzentrale.effects.EFFECT_DELAY", 0.01):
        await manager.async_test()
    commands = [c for c in calls if c.data["entity_id"] == entity]
    assert commands[-1].data["effect"] == "sparkle"
    assert commands[-2].data["brightness"] == 140
    if previous_effect:
        assert commands[0].data["effect"] == "stop_hue_effect"
    assert hass.states.get(entity).attributes["effect"] == "sparkle"
    await manager.async_set_enabled(False)
    assert hass.states.get(entity).state == "off"
    assert calls[-2].data["effect"] == "stop_hue_effect"
    assert calls[-1].service == "turn_off"


@pytest.mark.parametrize("change", ["grant", "membership"])
async def test_cleanup_rechecks_after_effect_stop(hass, store, rig, vacation, change):
    """A revocation between stop-effect and OFF must suppress the final command."""
    manager, calls = vacation
    first, second = rig["lights"][:2]
    zone = await store.async_save_zone({"name": "Synthetic vacation zone", "entity_ids": [first, second]})
    config = manager.config
    config["rooms"][0]["area_id"] = "zone:" + zone["id"]
    await manager.async_save_config(config)
    await manager.async_test()
    state = hass.states.get(first)
    hass.states.async_set(first, "on", {**state.attributes,
        "effect_list": ["candle", "stop_hue_effect"], "effect": "candle"}, context=state.context)
    stopped = []
    async def stop_and_revoke(call):
        entity = call.data["entity_id"]
        stopped.append(call)
        state = hass.states.get(entity)
        hass.states.async_set(entity, "on", {**state.attributes, "effect": call.data["effect"]}, context=call.context)
        if change == "grant":
            await store.async_set_lights([e for e in rig["lights"] if e != first])
        else:
            await store.async_save_zone({**zone, "entity_ids": [second]})
    hass.services.async_register("light", "turn_on", stop_and_revoke)
    calls.clear()
    await manager.async_set_enabled(False)
    assert stopped and stopped[0].data["effect"] == "stop_hue_effect"
    assert not any(c.service == "turn_off" and c.data["entity_id"] == first for c in calls)
    assert hass.states.get(first).state == "on"
    assert hass.states.get(second).state == "off"


async def test_disabled_saved_past_end_date_does_not_expire_or_notify(hass, store, rig, vacation):
    manager, calls = vacation
    yesterday = (dt_util.now().date() - timedelta(days=1)).isoformat()
    with patch.object(manager, "_notify") as notify:
        status = await manager.async_save_config(manager.config, until=yesterday)
        assert status["until"] == yesterday
        assert not status["enabled"]
        notify.assert_not_called()
        await manager.async_test()
        assert manager.status()["testing"]
        assert manager.paused
        assert store.data["vacation"]["until"] == yesterday
        notify.assert_not_called()


async def test_trial_crosses_saved_enddate_midnight_for_full_five_minutes(hass, store, rig, vacation):
    manager, calls = vacation
    local = dt_util.as_local(dt_util.utcnow())
    midnight = local.replace(hour=23, minute=59, second=0, microsecond=0)
    begin = dt_util.as_utc(midnight)
    await store.async_update_vacation({"until": midnight.date().isoformat()})
    with patch("custom_components.lichtzentrale.vacation.dt_util.utcnow", return_value=begin):
        await manager.async_test()
    with patch("custom_components.lichtzentrale.vacation.dt_util.utcnow", return_value=begin + timedelta(minutes=2)):
        await manager._tick()
        assert manager.status()["testing"]
        assert manager.paused
    with patch("custom_components.lichtzentrale.vacation.dt_util.utcnow", return_value=begin + timedelta(minutes=5)):
        await manager._tick()
        assert not manager.paused


async def test_disable_fences_inflight_activation_before_waiting_for_lock(hass, rig, vacation):
    import asyncio
    manager, calls = vacation
    started, resume = asyncio.Event(), asyncio.Event()
    observed = {}
    async def blocked_control(*args, **kwargs):
        if kwargs.get("on"):
            observed["guard"] = kwargs["dispatch_guard"]
            started.set()
            await resume.wait()
            kwargs["dispatch_guard"]()
        return {"applied": [], "skipped": []}
    with patch("custom_components.lichtzentrale.selected_lights.async_control_lights", side_effect=blocked_control):
        activation = asyncio.create_task(manager.async_test())
        await started.wait()
        previous_generation = manager._generation
        disable = asyncio.create_task(manager.async_set_enabled(False))
        await asyncio.sleep(0)
        assert not disable.done()  # The activation still holds the runtime lock.
        assert manager._generation > previous_generation
        with pytest.raises(ServiceValidationError):
            observed["guard"]()
        resume.set()
        await activation
        await disable
    assert not calls and not manager.paused


async def test_cancelled_stop_waiter_surfaces_fence_and_retry_clears_it(hass, vacation):
    import asyncio
    manager, calls = vacation
    previous_generation = manager._generation
    async with manager._lock:
        first = asyncio.create_task(manager.async_set_enabled(False))
        second = asyncio.create_task(manager.async_set_enabled(False))
        await asyncio.sleep(0)
        assert manager._stop_requested and manager._pending_stops == 2
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert manager._stop_requested and manager._pending_stops == 1
        second.cancel()
        with pytest.raises(asyncio.CancelledError):
            await second
        assert manager._stop_requested and manager._pending_stops == 0
        assert manager.status()["notes"]
        assert manager._generation == previous_generation + 2
    await manager.async_set_enabled(False)
    assert not manager._stop_requested and not manager.status()["notes"]
    await manager.async_test()
    assert manager.paused and manager._owned
    await manager.async_set_enabled(False)
    assert not manager.paused


async def test_failed_stop_persistence_is_visible_and_retryable(hass, store, vacation):
    manager, calls = vacation
    await manager.async_test()
    with patch.object(store, "async_update_vacation", side_effect=OSError("synthetic disk error")):
        with pytest.raises(OSError):
            await manager.async_set_enabled(False)
    assert manager._stop_requested and manager._pending_stops == 0
    assert manager.status()["notes"]
    before = len(calls)
    await manager._tick()
    assert len(calls) == before
    await manager.async_set_enabled(False)
    assert not manager._stop_requested and not manager.paused
    assert not manager.status()["notes"]
