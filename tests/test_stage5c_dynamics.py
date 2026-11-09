# Geändert für Lichtzentrale
"""Synthetic multi-tick acceptance, persistence and command-boundary safety."""

import asyncio
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.core import Context, State
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from custom_components.lichtzentrale.command_limiter import DynamicCommandLimiter
from custom_components.lichtzentrale.dynamic_scenes import DynamicSceneManager, validate_dynamic
from custom_components.lichtzentrale.lights import clamp_xy
from custom_components.lichtzentrale.moon import (
    NEW_MOON,
    SYNODIC_DAYS,
    illuminated_fraction,
    light_values,
)
from custom_components.lichtzentrale.palettes import async_apply_palette, list_palettes
from custom_components.lichtzentrale.rooms import async_set_light, light_service_data
from custom_components.lichtzentrale.scenes import async_apply_scene, async_save_scene
from custom_components.lichtzentrale.storage import LichtzentraleStore


@pytest.fixture
async def setup(hass, store, monkeypatch):
    monkeypatch.setattr("custom_components.lichtzentrale.command_limiter.COMMAND_SPACING", 0)
    areas = [ar.async_get(hass).async_create(f"Synthetic accent room {i}") for i in range(2)]
    ids = []
    for i in range(7):
        entry = er.async_get(hass).async_get_or_create("light", "synthetic", f"accent-{i}")
        er.async_get(hass).async_update_entity(entry.entity_id, area_id=areas[i % 2].id)
        hass.states.async_set(entry.entity_id, "on", {
            "supported_color_modes": ["onoff" if i == 6 else "xy"],
            "color_mode": "unknown", "brightness": None,
        })
        ids.append(entry.entity_id)
    await store.async_set_lights(ids)
    zone = await store.async_save_zone({"name": "Synthetic accent zone", "entity_ids": ids})
    await async_save_scene(hass, store, {
        "name": "Synthetic accents", "area_id": "zone:" + zone["id"], "kind": "palette",
        "palette_id": "kupfernest", "brightness": 150,
        "dynamic": {"enabled": True, "tempo": "fast", "welle": True},
        "wave_order": list(reversed(ids)),
        "lamp_settings": {
            ids[0]: {"mode": "cycle", "brightness": 31},
            ids[1]: {"mode": "cycle", "brightness": 64},
            ids[2]: {"mode": "fixed", "brightness": 90, "xy": [0.6, 0.3]},
            ids[3]: {"mode": "moon"},
            ids[5]: {"mode": "off"},
        },
    })
    manager = DynamicSceneManager(hass, store)
    hass.data["lichtzentrale"] = {"store": store, "dynamic": manager}
    hass.services.async_register("light", "turn_off", lambda _: None)
    yield manager, store.data["scenes"][0], ids
    await manager.shutdown()
    if (other := hass.data["lichtzentrale"].get("dynamic")) is not manager:
        await other.shutdown()


@pytest.mark.parametrize("tempo,seconds", [("very_slow", (180, 60)), ("slow", (90, 40)), ("medium", (30, 15)), ("fast", (8, 3))])
def test_tempos_and_legacy_seconds(tempo, seconds):
    actual = validate_dynamic({"tempo": tempo}, "palette")
    assert (actual["interval"], actual["transition"]) == seconds
    assert validate_dynamic({"interval": 37, "transition": 11}, "palette") == {
        "enabled": False, "interval": 37, "transition": 11, "welle": False,
    }


async def test_seven_lamp_scene_preserves_accents_over_three_ticks(hass, store, setup, light_calls):
    manager, scene, ids = setup
    await async_apply_scene(hass, store, scene["id"])
    first = {c.data["entity_id"]: c.data for c in light_calls}
    assert first[ids[0]]["brightness"] == 31
    assert first[ids[1]]["brightness"] == 64
    assert first[ids[2]]["xy_color"] == (0.6, 0.3)
    assert first[ids[6]] == {"entity_id": ids[6]}
    assert ids[5] not in first
    colors = []
    run = manager.active[scene["area_id"]]
    for offset in (1, 2, 3):
        light_calls.clear()
        assert await manager.tick(run, offset)
        values = {c.data["entity_id"]: c.data for c in light_calls}
        assert set(values) == {ids[0], ids[1], ids[4]}
        assert values[ids[0]]["brightness"] == 31
        assert values[ids[1]]["brightness"] == 64
        assert values[ids[4]]["brightness"] == 150
        colors.append(values[ids[4]]["xy_color"])
    assert len(set(colors)) == 3
    run["last_moon"] -= 1801
    light_calls.clear()
    assert await manager.tick(run, 4)
    assert ids[3] in {c.data["entity_id"] for c in light_calls}


async def test_gentle_is_relative_to_each_cycling_lamp(hass, store, setup, light_calls):
    _, scene, ids = setup
    for offset in range(1, 12):
        light_calls.clear()
        await async_apply_palette(hass, store, scene["palette_id"], ids, brightness=150,
                                  manage=False, lamp_settings=scene["lamp_settings"],
                                  gentle=True, color_offset=offset)
        values = {c.data["entity_id"]: c.data for c in light_calls}
        assert 28 <= values[ids[0]]["brightness"] <= 34
        assert 58 <= values[ids[1]]["brightness"] <= 70
        assert values[ids[2]]["brightness"] == 90
        assert values[ids[6]] == {"entity_id": ids[6]}


async def test_ordered_wave_keeps_slots_after_manual_exclusion(hass, store, setup, light_calls):
    manager, scene, ids = setup
    await manager.start(scene, Context())
    run = manager.active[scene["area_id"]]
    await manager.tick(run, 1)
    first = {c.data["entity_id"]: c.data["xy_color"] for c in light_calls}
    await async_set_light(hass, store, ids[1], brightness=42)
    light_calls.clear()
    await manager.tick(run, 1)
    assert {c.data["entity_id"]: c.data["xy_color"] for c in light_calls} == {
        e: color for e, color in first.items() if e != ids[1]
    }
    assert ids[1] in store.data["active_dynamic"][scene["area_id"]]["excluded"]
    await manager.start(scene, Context())
    assert not manager.active[scene["area_id"]]["excluded"]


async def test_restart_keeps_intent_and_exclusions_but_never_turns_off_lamp_on(hass, store, setup, light_calls):
    manager, scene, ids = setup
    await manager.start(scene, Context())
    await manager.exclude_targets([ids[0]])
    await manager.shutdown()
    restored_store = LichtzentraleStore(hass)
    await restored_store.async_load()
    hass.states.async_set(ids[1], "off", {"supported_color_modes": ["xy"]})
    fresh = DynamicSceneManager(hass, restored_store)
    hass.data["lichtzentrale"].update(dynamic=fresh, store=restored_store)
    await fresh.restore(wait_for_start=False)
    assert not light_calls  # Restore never recalls on, only schedules future ticks.
    assert await fresh.tick(fresh.active[scene["area_id"]], 1)
    assert [c.data["entity_id"] for c in light_calls] == [ids[4]]
    await fresh.stop(scene["area_id"])
    assert restored_store.data["active_dynamic"] == {}
    await fresh.shutdown()
    newer = DynamicSceneManager(hass, restored_store)
    hass.data["lichtzentrale"]["dynamic"] = newer
    await newer.restore(wait_for_start=False)
    assert newer.active == {}


async def test_external_one_lamp_change_and_own_context(hass, store, setup):
    manager, scene, ids = setup
    context = Context()
    await manager.start(scene, context)
    run = manager.active[scene["area_id"]]
    attrs = {**hass.states.get(ids[0]).attributes, "brightness": 70}
    hass.states.async_set(ids[0], "on", attrs, context=context)
    await hass.async_block_till_done()
    assert ids[0] not in run["excluded"]
    hass.states.async_set(ids[0], "on", {**attrs, "brightness": 80}, context=Context(user_id="synthetic-user"))
    await hass.async_block_till_done()
    assert run["excluded"] == {ids[0]}
    assert manager.active[scene["area_id"]] is run


async def test_manual_command_waits_for_inflight_and_fences_later_tick(hass, store, setup):
    manager, scene, ids = setup
    await manager.start(scene, Context())
    run = manager.active[scene["area_id"]]
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def service(domain, action, data, **kwargs):
        calls.append(dict(data))
        if data["entity_id"] == ids[0] and data.get("brightness") == 31:
            started.set()
            await release.wait()

    with patch.object(type(hass.services), "async_call", side_effect=service):
        tick = asyncio.create_task(manager.tick(run, 1))
        await started.wait()
        manual = asyncio.create_task(async_set_light(hass, store, ids[0], brightness=44))
        await asyncio.sleep(0)
        assert not manual.done()
        release.set()
        await asyncio.gather(tick, manual)
        await manager.tick(run, 2)
    selected = [c for c in calls if c["entity_id"] == ids[0]]
    assert [c["brightness"] for c in selected] == [31, 44]


async def test_overlap_stops_old_run_and_clears_persistence(hass, store, setup, light_calls):
    from custom_components.lichtzentrale.dynamic_scenes import async_stop_overlapping

    manager, scene, ids = setup
    await manager.start(scene, Context())
    run = manager.active[scene["area_id"]]
    await async_stop_overlapping(hass, [ids[1]])
    assert run["task"].done()
    assert not manager.active and not store.data["active_dynamic"]
    assert not await manager.tick(run, 2)
    assert not light_calls


async def test_global_limiter_staggers_across_two_sequences(hass, light_calls, monkeypatch):
    monkeypatch.setattr("custom_components.lichtzentrale.command_limiter.COMMAND_SPACING", 0.21)
    gate = DynamicCommandLimiter()
    stamps = []
    clock = asyncio.get_running_loop().time

    async def service(*args, **kwargs):
        stamps.append(clock())

    async def run(prefix):
        for index in range(3):
            await gate.dispatch(hass, "light", "turn_on", {"entity_id": f"light.synthetic_{prefix}_{index}"}, None, lambda _: True)

    with patch.object(type(hass.services), "async_call", side_effect=service):
        await asyncio.gather(run("a"), run("b"))
    assert len(stamps) == 6
    assert all(b - a >= 0.20 for a, b in zip(stamps, stamps[1:]))


def test_moon_endpoints_and_synodic_repeat():
    full = NEW_MOON + timedelta(days=SYNODIC_DAYS / 2)
    assert illuminated_fraction(NEW_MOON) == pytest.approx(0)
    assert illuminated_fraction(full) == pytest.approx(1)
    assert light_values(now=NEW_MOON)["brightness"] == 26
    assert light_values(now=full)["brightness"] == 204
    assert illuminated_fraction(full + timedelta(days=SYNODIC_DAYS)) == pytest.approx(1)
    assert light_values(now=full)["xy"] == pytest.approx([0.3127, 0.329])


@pytest.mark.parametrize("modes", [["xy"], ["color_temp"], ["onoff"]])
def test_uninitialized_z2m_first_on_has_native_color_except_onoff(modes):
    state = State("light.synthetic_unknown", "on", {"supported_color_modes": modes, "color_mode": "unknown", "brightness": None})
    action, payload = light_service_data(state, on=True, brightness=100)
    assert action == "turn_on"
    if modes == ["xy"]:
        assert payload["xy_color"]
    elif modes == ["color_temp"]:
        assert payload["color_temp_kelvin"]
    else:
        assert payload == {"entity_id": state.entity_id}


def test_saturated_xy_is_projected_to_reported_gamut():
    state = State("light.synthetic_gamut", "on", {"color_gamut": [[0.6, 0.3], [0.3, 0.6], [0.15, 0.06]]})
    assert clamp_xy(state, (0.9, 0.2)) == pytest.approx((0.6, 0.3))
    assert clamp_xy(state, (0.3, 0.3)) == (0.3, 0.3)


async def test_custom_palette_uses_same_execution_path(hass, store, light_calls):
    custom = await store.async_save_palette({
        "name": "Synthetic own", "category": "Eigene", "preview": ["#FF8000", "#FFCC00"], "bri": 128,
    })
    hass.states.async_set("light.synthetic_custom", "on", {"supported_color_modes": ["xy"]})
    await store.async_set_lights(["light.synthetic_custom"])
    await async_apply_palette(hass, store, custom["id"], ["light.synthetic_custom"], manage=False)
    assert light_calls[0].data["brightness"] == 128
    assert custom["id"] in {p["id"] for p in list_palettes(store)}


async def test_scoped_revocation_during_stagger_prevents_later_command(hass, store, setup):
    manager, scene, ids = setup
    await manager.start(scene, Context())
    calls = []

    async def service(domain, action, data, **kwargs):
        calls.append(data["entity_id"])
        if data["entity_id"] == ids[4]:
            await store.async_set_lights([e for e in ids if e != ids[0]])

    with patch.object(type(hass.services), "async_call", side_effect=service):
        assert await manager.tick(manager.active[scene["area_id"]], 1)
    assert calls == [ids[4], ids[1]]


async def test_stop_cancels_inflight_owned_tick_and_no_later_commands(hass, store, setup):
    manager, scene, ids = setup
    await manager.start(scene, Context())
    run = manager.active[scene["area_id"]]
    # Replace the long initial sleep with an immediately-running owned tick.
    # Ownership/cancellation is identical to the manager's real loop task.
    run["preserve"] = True
    original = run["task"]
    original.cancel()
    await asyncio.gather(original, return_exceptions=True)
    manager.active[scene["area_id"]] = run
    started = asyncio.Event()
    calls = []

    async def service(domain, action, data, **kwargs):
        calls.append(data["entity_id"])
        started.set()
        await asyncio.Event().wait()

    with patch.object(type(hass.services), "async_call", side_effect=service):
        run["task"] = asyncio.create_task(manager.tick(run, 1))
        await started.wait()
        await manager.stop(scene["area_id"])
    assert len(calls) == 1
    assert run["task"].done()
    assert not store.data["active_dynamic"]


async def test_stale_run_cleanup_cannot_erase_replacement(hass, store, setup):
    manager, scene, _ = setup
    await manager.start(scene, Context())
    old = manager.active[scene["area_id"]]
    await manager.start(scene, Context())
    fresh = manager.active[scene["area_id"]]
    old["excluded"].add(old["targets"][0])
    await manager._persist(old)
    await store.async_set_dynamic_run(scene["area_id"], None, expected_token=old["token"])
    assert store.data["active_dynamic"][scene["area_id"]]["token"] == fresh["token"]
    assert not store.data["active_dynamic"][scene["area_id"]]["excluded"]


async def test_explicit_off_before_startup_restore_cannot_resurrect(hass, store, setup):
    manager, scene, _ = setup
    await manager.start(scene, Context())
    await manager.shutdown()
    fresh = DynamicSceneManager(hass, store)
    hass.data["lichtzentrale"]["dynamic"] = fresh
    await fresh.stop(scene["area_id"])
    await fresh.restore(wait_for_start=False)
    assert fresh.active == {}


async def test_static_moon_scene_updates_without_animating_peers(hass, store, setup, light_calls):
    manager, scene, ids = setup
    scene["dynamic"]["enabled"] = False
    await store.async_save_scene(scene, is_update=True)
    await manager.start(scene, Context())
    run = manager.active[scene["area_id"]]
    assert await manager.tick(run, 1)
    assert light_calls == []
    run["last_moon"] -= 1801
    assert await manager.tick(run, 1)
    assert [c.data["entity_id"] for c in light_calls] == [ids[3]]


async def test_explicit_off_racing_restore_store_write_wins(hass, store, setup):
    manager, scene, _ = setup
    await manager.start(scene, Context())
    await manager.shutdown()
    fresh = DynamicSceneManager(hass, store)
    hass.data["lichtzentrale"]["dynamic"] = fresh
    original = store.async_set_dynamic_run
    entered, release = asyncio.Event(), asyncio.Event()

    async def racing(area_id, record=None, **kwargs):
        if record is not None:
            entered.set()
            await release.wait()
        return await original(area_id, record, **kwargs)

    with patch.object(store, "async_set_dynamic_run", side_effect=racing):
        restore = asyncio.create_task(fresh.restore(wait_for_start=False))
        await entered.wait()
        await fresh.stop(scene["area_id"])
        release.set()
        await restore
    assert not fresh.active and not store.data["active_dynamic"]


async def test_moon_timer_is_not_delayed_by_an_hour_long_color_interval(hass, store):
    manager = DynamicSceneManager(hass, store)
    run = {"scene": {"area_id": "synthetic_timer", "dynamic": {"enabled": True, "interval": 3600},
                     "lamp_settings": {"light.synthetic_moon": {"mode": "moon"}}},
           "initial_transition": 0}
    now = [0]

    async def advance(seconds):
        now[0] += seconds

    with (
        patch.object(asyncio.get_running_loop(), "time", side_effect=lambda: now[0]),
        patch("custom_components.lichtzentrale.dynamic_scenes.asyncio.sleep", side_effect=advance) as sleep,
        patch.object(manager, "tick", side_effect=[True, False]) as tick,
    ):
        await manager._loop(run)
    assert [c.args[0] for c in sleep.await_args_list] == [1800, 1800]
    assert tick.await_args_list[0].kwargs["moon_only"] is True
    assert tick.await_args_list[1].kwargs["moon_only"] is False


async def test_overloaded_tick_extends_interval_without_catchup_queue(hass, store, caplog):
    manager = DynamicSceneManager(hass, store)
    run = {"scene": {"area_id": "synthetic_load", "dynamic": {"enabled": True, "interval": 8}},
           "initial_transition": 0}
    now, calls = [0], []

    async def advance(seconds):
        now[0] += seconds

    async def slow_tick(*args, **kwargs):
        calls.append(now[0])
        now[0] += 9
        return len(calls) < 2

    with (
        patch.object(asyncio.get_running_loop(), "time", side_effect=lambda: now[0]),
        patch("custom_components.lichtzentrale.dynamic_scenes.asyncio.sleep", side_effect=advance) as sleep,
        patch.object(manager, "tick", side_effect=slow_tick),
    ):
        await manager._loop(run)
    assert [c.args[0] for c in sleep.await_args_list] == [8, 8]
    assert calls == [8, 25]
    assert "verlängert" in caplog.text and "keine Warteschlange" in caplog.text


async def test_capability_change_to_onoff_while_staggered_never_gets_color(hass, store, setup):
    manager, scene, ids = setup
    await manager.start(scene, Context())
    calls = []

    async def service(domain, action, data, **kwargs):
        calls.append(data["entity_id"])
        if data["entity_id"] == ids[4]:
            # Simulate a migrated/replaced light exposing only on/off capability.
            hass.states.async_set(ids[0], "on", {"supported_color_modes": ["onoff"]},
                                  context=manager.active[scene["area_id"]]["context"])

    with patch.object(type(hass.services), "async_call", side_effect=service):
        assert await manager.tick(manager.active[scene["area_id"]], 1)
    assert calls == [ids[4], ids[1]]


async def test_explicit_moon_brightness_stays_fixed(hass, store, setup, light_calls):
    _, scene, ids = setup
    settings = {ids[3]: {"mode": "moon", "brightness": 31, "moon": {"breath": True}}}
    await async_apply_palette(hass, store, scene["palette_id"], [ids[3]], manage=False,
                              lamp_settings=settings, moon_breath=True)
    assert light_calls[0].data["brightness"] == 31


async def test_initial_recall_context_matches_later_ticks(hass, store, setup, light_calls):
    manager, scene, ids = setup
    await async_apply_scene(hass, store, scene["id"])
    run = manager.active[scene["area_id"]]
    assert all(call.context.id == run["context"].id for call in light_calls)
    attrs = {**hass.states.get(ids[0]).attributes, "brightness": 31}
    hass.states.async_set(ids[0], "on", attrs, context=light_calls[0].context)
    await hass.async_block_till_done()
    assert ids[0] not in run["excluded"]
