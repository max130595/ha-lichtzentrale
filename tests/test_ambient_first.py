# Geändert für Lichtzentrale
"""Synthetic ambient button ownership, safety and window regressions."""
from datetime import datetime
from unittest.mock import patch

import pytest
import test_bindings as binding_tests
from homeassistant.core import Context, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from test_bindings import raw, scene

from custom_components.lichtzentrale.ambient_first import AmbientFirstTracker
from custom_components.lichtzentrale.bindings import validate_binding
from custom_components.lichtzentrale.scenes import async_apply_scene, async_save_scene
from custom_components.lichtzentrale.schedule_windows import window_is_open

rig = binding_tests.rig

WINDOW = {"after": {"type": "time", "value": "20:00"}, "before": {"type": "time", "value": "02:00"}}


@pytest.fixture
async def ambient(hass, store, rig):
    saved = await scene(hass, store, rig)
    calls = []

    @callback
    def control(call):
        calls.append(call)
        entities = call.data["entity_id"]
        if isinstance(entities, str):
            entities = [entities]
        for entity in entities:
            state = hass.states.get(entity)
            attrs = {**state.attributes, **{k: v for k, v in call.data.items() if k != "entity_id"}}
            hass.states.async_set(entity, "off" if call.service == "turn_off" else "on", attrs, context=call.context)

    for domain in ("light", "switch"):
        for service in ("turn_on", "turn_off"):
            hass.services.async_register(domain, service, control)
    for entity in rig["lights"]:
        state = hass.states.get(entity)
        hass.states.async_set(entity, "off", state.attributes)
    await hass.async_block_till_done()
    binding = validate_binding(hass, store, raw(rig, "toggle_lights", params={
        "entity_ids": [rig["lights"][1]],
        "ambient_first": {"scene_id": saved["id"], "window": WINDOW},
        "on_behavior": {"mode": "brightness", "brightness": 255},
    }))
    return saved, binding, calls


async def press(hass, rig, binding, inside=True):
    with patch("custom_components.lichtzentrale.ambient_first.window_is_open", return_value=inside):
        result = await rig["manager"]._action(binding, Context())
        await hass.async_block_till_done()
        return result


async def test_three_steps_running_wins_when_button_targets_stay_off(hass, store, rig, ambient):
    saved, binding, calls = ambient
    await press(hass, rig, binding)
    assert hass.states.get(rig["lights"][0]).state == "on"
    assert hass.states.get(rig["lights"][1]).state == "off"
    assert rig["manager"].ambient_first.running(rig["area"], saved["id"])
    await press(hass, rig, binding)
    assert hass.states.get(rig["lights"][0]).state == "off"
    assert hass.states.get(rig["lights"][1]).attributes["brightness"] == 255
    await press(hass, rig, binding)
    assert all(hass.states.get(e).state == "off" for e in rig["lights"])


async def test_outside_window_uses_normal_toggle(hass, store, rig, ambient):
    saved, binding, calls = ambient
    await press(hass, rig, binding, False)
    assert hass.states.get(rig["lights"][1]).state == "on"
    assert hass.states.get(rig["lights"][0]).state == "off"
    await press(hass, rig, binding, False)
    assert hass.states.get(rig["lights"][1]).state == "off"


async def test_other_scene_entry_path_owns_ambient(hass, store, rig, ambient):
    saved, binding, calls = ambient
    await async_apply_scene(hass, store, saved["id"])
    await hass.async_block_till_done()
    await press(hass, rig, binding)
    assert hass.states.get(rig["lights"][0]).state == "off"
    assert hass.states.get(rig["lights"][1]).state == "on"


async def test_deleted_scene_falls_back_with_warning(hass, store, rig, ambient, caplog):
    saved, binding, calls = ambient
    await store.async_delete_scene(saved["id"])
    await press(hass, rig, binding)
    assert hass.states.get(rig["lights"][1]).state == "on"
    assert "gelöscht" in caplog.text
    # Runtime accepts a stale reference, while a newly saved one is rejected.
    value = {key: val for key, val in binding.items() if key != "id"}
    validate_binding(hass, store, value, _runtime=True)
    with pytest.raises(ServiceValidationError):
        validate_binding(hass, store, value)


async def test_revoked_grant_fails_closed(hass, store, rig, ambient):
    saved, binding, calls = ambient
    await store.async_set_lights(rig["lights"][1:])
    with pytest.raises(ServiceValidationError):
        await press(hass, rig, binding)
    assert calls == []


@pytest.mark.parametrize("manual", ["service", "physical", "user_attribute", "script"])
async def test_manual_control_ends_ownership(hass, store, rig, ambient, manual):
    saved, binding, calls = ambient
    await press(hass, rig, binding)
    tracker = rig["manager"].ambient_first
    entity = rig["lights"][0]
    if manual in {"service", "script"}:
        context = Context(parent_id=tracker.records[rig["area"]]["context"].id) if manual == "script" else Context()
        await hass.services.async_call("light", "turn_on", {"entity_id": entity, "brightness": 42}, blocking=True, context=context)
    else:
        state = hass.states.get(entity)
        hass.states.async_set(entity, "off" if manual == "physical" else "on",
                              {**state.attributes, "brightness": 42}, context=Context(user_id="synthetic") if manual == "user_attribute" else Context())
    await hass.async_block_till_done()
    assert not tracker.running(rig["area"], saved["id"])


async def test_contextless_attribute_reports_preserve_ownership(hass, store, rig, ambient):
    saved, binding, calls = ambient
    await press(hass, rig, binding)
    entity = rig["lights"][0]
    state = hass.states.get(entity)
    hass.states.async_set(entity, "on", {**state.attributes, "brightness": 110})
    await hass.async_block_till_done()
    assert rig["manager"].ambient_first.running(rig["area"], saved["id"])


async def test_restart_never_infers_ownership_from_last_scene(hass, store, rig, ambient):
    saved, binding, calls = ambient
    await press(hass, rig, binding)
    tracker = AmbientFirstTracker(hass, store)
    tracker.start()
    assert not tracker.running(rig["area"], saved["id"])
    tracker.shutdown()
    assert tracker._unsub == []


async def test_selection_must_belong_to_explicit_room(hass, store, rig, ambient):
    saved, binding, calls = ambient
    value = {key: val for key, val in binding.items() if key != "id"}
    assert validate_binding(hass, store, value)["area_id"] == rig["area"]
    with pytest.raises(ServiceValidationError):
        validate_binding(hass, store, {**value, "area_id": rig["other"]})
    with pytest.raises(ServiceValidationError):
        validate_binding(hass, store, {**value, "area_id": None})


@pytest.mark.parametrize("hour, expected", [(21, True), (1, True), (2, False), (12, False)])
async def test_midnight_window(hass, hour, expected):
    assert window_is_open(hass, WINDOW, datetime(2026, 11, 5, hour, tzinfo=dt_util.DEFAULT_TIME_ZONE)) is expected


async def test_seasonal_scene_is_tracked_by_wrapper(hass, store, rig, ambient):
    saved, binding, calls = ambient
    wrapper = await async_save_scene(hass, store, {
        "name": "Synthetic seasonal ambient", "kind": "seasonal", "area_id": rig["area"],
        "seasonal": {"scenes": {key: saved["id"] for key in ("spring", "summer", "autumn", "winter")}},
    })
    binding["params"]["ambient_first"]["scene_id"] = wrapper["id"]
    await press(hass, rig, binding)
    assert rig["manager"].ambient_first.running(rig["area"], wrapper["id"])
    await press(hass, rig, binding)
    assert hass.states.get(rig["lights"][0]).state == "off"
    assert hass.states.get(rig["lights"][1]).state == "on"


async def test_own_dynamic_commands_do_not_end_ownership(hass, store, rig, ambient):
    saved, binding, calls = ambient
    await press(hass, rig, binding)
    tracker = rig["manager"].ambient_first
    context = tracker.records[rig["area"]]["context"]
    await hass.services.async_call("light", "turn_on", {"entity_id": rig["lights"][0], "brightness": 130}, blocking=True, context=context)
    await hass.async_block_till_done()
    assert tracker.running(rig["area"], saved["id"])


async def test_room_toggle_supports_ambient_option(hass, store, rig, ambient):
    saved, binding, calls = ambient
    binding["action"] = "toggle_room"
    binding["params"].pop("entity_ids")
    await press(hass, rig, binding)
    await press(hass, rig, binding)
    assert all(hass.states.get(e).state == "on" for e in rig["lights"])
    assert hass.states.get(rig["lights"][0]).attributes["brightness"] == 255
    await press(hass, rig, binding)
    assert all(hass.states.get(e).state == "off" for e in rig["lights"])


async def test_solar_offset_and_missing_solar_event(hass):
    window = {"after": {"type": "sun", "event": "sunset", "offset_min": -15}, "before": {"type": "time", "value": "22:30"}}
    zone = dt_util.DEFAULT_TIME_ZONE
    def sunset(hass, event, day):
        return datetime(day.year, day.month, day.day, 18, tzinfo=zone)
    with patch("custom_components.lichtzentrale.schedule_windows.get_astral_event_date", side_effect=sunset):
        assert window_is_open(hass, window, datetime(2026, 11, 5, 17, 50, tzinfo=zone))
        assert not window_is_open(hass, window, datetime(2026, 11, 5, 17, 40, tzinfo=zone))
    with patch("custom_components.lichtzentrale.schedule_windows.get_astral_event_date", return_value=None):
        assert not window_is_open(hass, window, datetime(2026, 11, 5, 18, tzinfo=zone))


async def test_membership_change_invalidates_ownership(hass, store, rig, ambient):
    saved, binding, calls = ambient
    await press(hass, rig, binding)
    await store.async_set_lights(rig["lights"][:-1])
    assert not rig["manager"].ambient_first.running(rig["area"], saved["id"])


@pytest.mark.parametrize("mode", ["last", "time_match", "time_fallback", "scene"])
async def test_second_press_respects_on_behavior(hass, store, rig, ambient, mode):
    saved, binding, calls = ambient
    if mode == "last":
        behavior = {"mode": "last"}
    elif mode.startswith("time"):
        behavior = {"mode": "time", "windows": [{"window": WINDOW, "mode": "brightness", "brightness": 51}]}
    else:
        normal = await async_save_scene(hass, store, {"name": "Synthetic task scene", "kind": "snapshot", "area_id": rig["area"],
                                                   "lights": {rig["lights"][1]: {"on": True, "brightness": 75}}})
        behavior = {"mode": "scene", "scene_id": normal["id"]}
    binding["params"]["on_behavior"] = behavior
    await press(hass, rig, binding)
    with patch("custom_components.lichtzentrale.schedule_windows.window_is_open", return_value=mode != "time_fallback"):
        await press(hass, rig, binding)
    assert hass.states.get(rig["lights"][0]).state == "off"
    assert hass.states.get(rig["lights"][1]).state == "on"
    if mode in {"time_match", "scene"}:
        assert hass.states.get(rig["lights"][1]).attributes["brightness"] == (51 if mode == "time_match" else 75)


async def test_foreign_command_between_off_and_on_wins(hass, store, rig, ambient):
    from custom_components.lichtzentrale.selected_lights import async_control_lights

    saved, binding, calls = ambient
    await press(hass, rig, binding)
    async def interleave(*args, **kwargs):
        result = await async_control_lights(*args, **kwargs)
        if kwargs.get("on") is False:
            await hass.services.async_call("light", "turn_on", {"entity_id": rig["lights"][0], "brightness": 42}, blocking=True, context=Context())
            await hass.async_block_till_done()
        return result
    with patch("custom_components.lichtzentrale.selected_lights.async_control_lights", side_effect=interleave):
        with pytest.raises(ServiceValidationError, match="Vorrang"):
            await press(hass, rig, binding)
    assert hass.states.get(rig["lights"][1]).state == "off"
    assert hass.states.get(rig["lights"][0]).attributes["brightness"] == 42


async def test_shutdown_clears_runtime_tracker(hass, store, rig, ambient):
    saved, binding, calls = ambient
    await press(hass, rig, binding)
    tracker = rig["manager"].ambient_first
    await rig["manager"].shutdown()
    assert tracker.records == {}
    assert tracker._unsub == []
    assert "ambient_first" not in hass.data["lichtzentrale"]


async def test_malformed_service_targets_do_not_crash_tracker(hass, store, rig, ambient):
    from homeassistant.const import EVENT_CALL_SERVICE
    from homeassistant.core import Event

    saved, binding, calls = ambient
    await press(hass, rig, binding)
    tracker = rig["manager"].ambient_first
    tracker._called(Event(EVENT_CALL_SERVICE, {"domain": "light", "service": "turn_on", "service_data": {"entity_id": None}}))
    assert tracker.running(rig["area"], saved["id"])
