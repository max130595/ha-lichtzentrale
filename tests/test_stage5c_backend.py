# Geändert für Lichtzentrale
"""Synthetic palette authoring and transactional live scene editor regressions."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.core import Context, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from custom_components.lichtzentrale.const import DOMAIN
from custom_components.lichtzentrale.dynamic_scenes import DynamicSceneManager
from custom_components.lichtzentrale.live_preview import LivePreviewManager
from custom_components.lichtzentrale.palette_catalogue import (
    _LEGACY,
    CATEGORIES,
    get_palette,
    list_palettes,
)
from custom_components.lichtzentrale.scene_settings import validate_lamp_settings
from custom_components.lichtzentrale.scenes import async_save_scene, list_scenes, validate_scene
from custom_components.lichtzentrale.storage import LichtzentraleStore


@pytest.fixture
async def editor(hass, store):
    area = ar.async_get(hass).async_create("Synthetic editor area")
    targets = []
    for index, mode in enumerate(("xy", "color_temp", "onoff")):
        entry = er.async_get(hass).async_get_or_create("light", "synthetic", f"editor-{index}", original_name=f"Editor lamp {index}")
        er.async_get(hass).async_update_entity(entry.entity_id, area_id=area.id)
        attrs = {"supported_color_modes": [mode], "color_mode": mode}
        if mode != "onoff":
            attrs["brightness"] = 100 + index
        if mode == "xy":
            attrs["xy_color"] = [0.4, 0.3]
        if mode == "color_temp":
            attrs.update(color_temp_kelvin=3000, min_color_temp_kelvin=2200, max_color_temp_kelvin=6500)
        hass.states.async_set(entry.entity_id, "on", attrs)
        targets.append(entry.entity_id)
    await store.async_set_lights(targets)
    calls = []

    @callback
    def control(call):
        entity_id = call.data["entity_id"]
        state = hass.states.get(entity_id)
        attrs = dict(state.attributes)
        for key in ("brightness", "xy_color", "color_temp_kelvin"):
            if key in call.data:
                attrs[key] = call.data[key]
        if "xy_color" in call.data:
            attrs["color_mode"] = "xy"
        elif "color_temp_kelvin" in call.data:
            attrs["color_mode"] = "color_temp"
        calls.append((call.service, dict(call.data)))
        hass.states.async_set(entity_id, "off" if call.service == "turn_off" else "on", attrs, context=call.context)

    hass.services.async_register("light", "turn_on", control)
    hass.services.async_register("light", "turn_off", control)
    dynamic = DynamicSceneManager(hass, store)
    preview = LivePreviewManager(hass, store)
    hass.data[DOMAIN] = {"store": store, "dynamic": dynamic, "live_preview": preview}
    owner = SimpleNamespace(subscriptions={})
    yield SimpleNamespace(area=area.id, ids=targets, calls=calls, preview=preview, owner=owner)
    await preview.shutdown()
    await dynamic.shutdown()


def palette(**changes):
    return {"name": "Testfarben", "category": "Eigene", "preview": ["#FF7000", "#FFC200", "#A52B20"], "bri": 145, "tempo": "slow", **changes}


def scene(editor, **changes):
    return {"name": "Testszene", "area_id": editor.area, "kind": "palette", "palette_id": "herbstglut", "brightness": 155, **changes}


def test_curated_and_legacy_catalogue():
    palettes = list_palettes()
    assert len(palettes) >= 32
    assert set(CATEGORIES) <= {p["category"] for p in palettes}
    assert len({p["id"] for p in palettes}) == len(palettes)
    for identifier, name, category, bri, preview in _LEGACY:
        p = next(p for p in palettes if p["id"] == identifier)
        assert (p["name"], p["category"], p["bri"], p["preview"]) == (name, category, bri, preview)
    assert next(p for p in palettes if p["id"] == "herbstglut")["preview"] == ["#FF9A2E", "#FF6A13", "#D9541E", "#FFC247", "#9E2A2B"]


async def test_palette_crud_preserves_fields_reload_and_reference_refusal(hass, store, editor):
    own = await store.async_save_palette(palette())
    original = store.data
    original["future_field"] = {"keep": True}
    original["palettes"][0]["future_palette"] = "kept"
    await store._store.async_save(original)
    await store.async_load()
    updated = await store.async_save_palette({**own, "name": "Andere Farben"})
    assert updated["future_palette"] == "kept"
    saved = await async_save_scene(hass, store, scene(editor, palette_id=own["id"]))
    assert list_scenes(store)[0]["preview"] == own["preview"]
    with pytest.raises(ServiceValidationError, match="Testszene"):
        await store.async_delete_palette(own["id"])
    copy = await store.async_duplicate_palette("herbstglut")
    assert not copy["builtin"] and copy["id"] != "herbstglut"
    assert copy["preview"] == get_palette(store, "herbstglut")["preview"]
    reloaded = LichtzentraleStore(hass)
    await reloaded.async_load()
    assert get_palette(reloaded, own["id"])["name"] == "Andere Farben"
    assert reloaded.data["future_field"] == {"keep": True}
    await store.async_delete_scene(saved["id"])
    await store.async_delete_palette(own["id"])
    assert own["id"] not in {p["id"] for p in list_palettes(store)}


@pytest.mark.parametrize("change", [{"preview": ["bad", "#123456"]}, {"preview": ["#123456"]}, {"preview": ["#123456"] * 7}, {"bri": True}, {"bri": 0}, {"tempo": "warp"}, {"name": " "}])
async def test_palette_invalid_input_atomic(store, change):
    before = store.data
    with pytest.raises(ServiceValidationError):
        await store.async_save_palette(palette(**change))
    assert store.data == before


async def test_builtin_protected_and_failed_write_not_published(store):
    original = get_palette(store, "herbstglut")
    with pytest.raises(ServiceValidationError):
        await store.async_save_palette(original)
    with pytest.raises(ServiceValidationError):
        await store.async_delete_palette("herbstglut")
    before = store.data
    with patch.object(store._store, "async_save", side_effect=RuntimeError("disk failure")):
        with pytest.raises(RuntimeError):
            await store.async_save_palette(palette())
    assert store.data == before


async def test_scene_settings_roundtrip_and_snapshot_brightness(hass, store, editor):
    saved = await async_save_scene(hass, store, scene(editor, lamp_settings={
        editor.ids[0]: {"mode": "fixed", "brightness": 25, "palette_index": 1},
        editor.ids[1]: {"mode": "moon"}, editor.ids[2]: {"mode": "off"},
    }, wave_order=list(reversed(editor.ids)), dynamic={"enabled": True, "tempo": "slow", "welle": True, "gentle": True}))
    assert saved["lamp_settings"][editor.ids[0]]["brightness"] == 25
    assert saved["dynamic"]["interval"] == 90
    assert saved["lamp_settings"][editor.ids[1]]["moon"]["full_brightness"] == 204
    reread = LichtzentraleStore(hass)
    await reread.async_load()
    assert reread.data["scenes"][0]["wave_order"] == list(reversed(editor.ids))
    snap = validate_scene(hass, store, scene(editor, kind="snapshot", lights={editor.ids[0]: {"on": True, "brightness": 70, "xy": [.4, .3]}}, brightness=80))
    assert snap["brightness"] == 80


@pytest.mark.parametrize("setting", [{"mode": "moon"}, {"brightness": 50}, {"mode": "fixed", "xy": [.3, .3]}])
async def test_onoff_never_dimmable_or_colored(hass, editor, setting):
    with pytest.raises(ServiceValidationError, match="An / Aus"):
        validate_lamp_settings(hass, {editor.ids[2]: setting}, editor.ids, get_palette(None, "herbstglut"))


async def test_settings_cannot_broaden_scene(hass, store, editor):
    with pytest.raises(ServiceValidationError):
        validate_scene(hass, store, scene(editor, lamp_settings={"light.synthetic_outsider": {"mode": "off"}}))
    with pytest.raises(ServiceValidationError):
        validate_scene(hass, store, scene(editor, wave_order=[editor.ids[0], editor.ids[0]]))


async def test_preview_uses_unsaved_draft_and_cancel_restores(hass, store, editor):
    before = store.data
    session = await editor.preview.begin(editor.area, editor.owner)
    draft = scene(editor, lamp_settings={editor.ids[0]: {"mode": "fixed", "brightness": 33, "xy": [.6, .3]}, editor.ids[2]: {"mode": "off"}})
    result = await editor.preview.apply(session["preview_id"], editor.owner, sequence=1, scene=draft)
    await hass.async_block_till_done()
    assert editor.ids[0] in result["applied"]
    assert hass.states.get(editor.ids[0]).attributes["brightness"] == 33
    assert hass.states.get(editor.ids[2]).state == "off"
    assert store.data == before
    await editor.preview.cancel(session["preview_id"], editor.owner)
    assert hass.states.get(editor.ids[0]).attributes["brightness"] == 100
    assert hass.states.get(editor.ids[0]).attributes["xy_color"] == [.4, .3]
    assert hass.states.get(editor.ids[2]).state == "on"
    assert not editor.owner.subscriptions
    assert not editor.preview.sessions


async def test_palette_preview_commit_custom_scene_and_owner_isolation(hass, store, editor):
    session = await editor.preview.begin(editor.area, editor.owner)
    foreign = SimpleNamespace(subscriptions={})
    with pytest.raises(ServiceValidationError):
        await editor.preview.apply(session["preview_id"], foreign, sequence=1, palette=palette())
    result = await editor.preview.commit(session["preview_id"], editor.owner, palette=palette())
    assert get_palette(store, result["palette"]["id"])["preview"] == palette()["preview"]
    session = await editor.preview.begin(editor.area, editor.owner)
    result = await editor.preview.commit(session["preview_id"], editor.owner, scene=scene(editor, brightness=210))
    assert len(store.data["scenes"]) == 1
    assert result["scene"]["brightness"] == 210
    assert hass.states.get(editor.ids[0]).attributes["brightness"] == 210


async def test_preview_does_not_undo_or_overwrite_manual_change(hass, store, editor):
    session = await editor.preview.begin(editor.area, editor.owner)
    await editor.preview.apply(session["preview_id"], editor.owner, sequence=1, scene=scene(editor))
    await hass.async_block_till_done()
    await hass.services.async_call("light", "turn_on", {"entity_id": editor.ids[0], "brightness": 23}, blocking=True, context=Context())
    await hass.async_block_till_done()
    await editor.preview.apply(session["preview_id"], editor.owner, sequence=2, scene=scene(editor, brightness=220))
    assert hass.states.get(editor.ids[0]).attributes["brightness"] == 23
    await editor.preview.cancel(session["preview_id"], editor.owner)
    assert hass.states.get(editor.ids[0]).attributes["brightness"] == 23
    assert hass.states.get(editor.ids[1]).attributes["brightness"] == 101


async def test_preview_cancel_respects_revocation_and_disconnect(hass, store, editor):
    session = await editor.preview.begin(editor.area, editor.owner)
    await editor.preview.apply(session["preview_id"], editor.owner, sequence=1, scene=scene(editor))
    await hass.async_block_till_done()
    await store.async_set_lights(editor.ids[1:])
    editor.calls.clear()
    for close in list(editor.owner.subscriptions.values()):
        close()
    await hass.async_block_till_done()
    assert editor.ids[0] not in {data["entity_id"] for _, data in editor.calls}
    assert not editor.preview.sessions


async def test_preview_cancel_fences_inflight_apply(hass, editor):
    session = await editor.preview.begin(editor.area, editor.owner)
    entered, finish = asyncio.Event(), asyncio.Event()
    real_call = hass.services.async_call

    async def slow_call(*args, **kwargs):
        entered.set()
        await finish.wait()
        return await real_call(*args, **kwargs)

    with patch.object(type(hass.services), "async_call", side_effect=slow_call):
        applying = asyncio.create_task(editor.preview.apply(session["preview_id"], editor.owner, sequence=1, scene=scene(editor)))
        await asyncio.wait_for(entered.wait(), 2)
        cancelling = asyncio.create_task(editor.preview.cancel(session["preview_id"], editor.owner))
        await asyncio.sleep(0)
        finish.set()
        await applying
        await cancelling
    assert hass.states.get(editor.ids[0]).attributes["brightness"] == 100
    assert not editor.preview.sessions


async def test_preview_stale_sequence_and_changed_target_rejected(hass, editor):
    session = await editor.preview.begin(editor.area, editor.owner)
    await editor.preview.apply(session["preview_id"], editor.owner, sequence=9, scene=scene(editor))
    count = len(editor.calls)
    stale = await editor.preview.apply(session["preview_id"], editor.owner, sequence=8, scene=scene(editor))
    assert stale["superseded"] and len(editor.calls) == count
    with pytest.raises(ServiceValidationError):
        await editor.preview.apply(session["preview_id"], editor.owner, sequence=10, scene=scene(editor, area_id="different"))


async def test_dynamic_intent_cas_and_unknown_store_preservation(store):
    first = {"token": "first", "scene_id": "fixture", "targets": []}
    assert await store.async_set_dynamic_run("synthetic", first)
    assert not await store.async_set_dynamic_run("synthetic", None, expected_token="older")
    assert store.data["active_dynamic"]["synthetic"] == first
    assert await store.async_set_dynamic_run("synthetic", None, expected_token="first")
    assert not store.data["active_dynamic"]
    before = deepcopy(store.data)
    with patch.object(store._store, "async_save", side_effect=RuntimeError("failure")):
        with pytest.raises(RuntimeError):
            await store.async_transform_entity_references(lambda data: ({**data, "future": 1}, {}))
    assert store.data == before


async def api_request(client, name, **payload):
    await client.send_json_auto_id({"type": f"lichtzentrale/{name}", **payload})
    return await client.receive_json()


@pytest.mark.parametrize("name,payload", [
    ("palette/save", {"palette": {}}),
    ("palette/duplicate", {"palette_id": "herbstglut"}),
    ("palette/delete", {"palette_id": "synthetic"}),
    ("preview/begin", {"area_id": "synthetic"}),
    ("preview/apply", {"preview_id": "synthetic", "sequence": 0, "scene": {}}),
    ("preview/commit", {"preview_id": "synthetic", "scene": {}}),
    ("preview/cancel", {"preview_id": "synthetic"}),
    ("preview/keepalive", {"preview_id": "synthetic"}),
    ("light/replace_options", {}),
    ("light/replace_preview", {"old_entity_id": "light.synthetic_a", "new_entity_id": "light.synthetic_b"}),
    ("light/replace", {"old_entity_id": "light.synthetic_a", "new_entity_id": "light.synthetic_b", "preview_token": "fixture"}),
])
async def test_stage5c_endpoints_require_admin(hass, store, hass_ws_client, hass_read_only_access_token, name, payload):
    from custom_components.lichtzentrale.websocket_api import async_setup_websocket_api

    hass.data[DOMAIN] = {"store": store}
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    async_setup_websocket_api(hass)
    result = await api_request(client, name, **payload)
    assert result["error"]["code"] == "unauthorized"
    assert not store.data["palettes"]


async def test_live_api_connection_cleanup_and_crud(hass, hass_ws_client, editor, store):
    from custom_components.lichtzentrale.websocket_api import async_setup_websocket_api

    client = await hass_ws_client(hass)
    async_setup_websocket_api(hass)
    saved = await api_request(client, "palette/save", palette=palette())
    assert saved["success"]
    listed = (await api_request(client, "palettes/list"))["result"]
    assert saved["result"]["id"] in {p["id"] for p in listed}
    session = (await api_request(client, "preview/begin", area_id=editor.area))["result"]
    assert 0 <= session["moon_fraction"] <= 1
    assert (await api_request(client, "preview/keepalive", preview_id=session["preview_id"]))["success"]
    applied = await api_request(client, "preview/apply", preview_id=session["preview_id"], sequence=1, scene=scene(editor))
    assert applied["success"]
    assert hass.states.get(editor.ids[0]).attributes["brightness"] == 155
    await client.close()
    await hass.async_block_till_done()
    assert hass.states.get(editor.ids[0]).attributes["brightness"] == 100
    assert not editor.preview.sessions


async def test_preview_timeout_restores_and_keepalive_rearms(hass, editor):
    timers, cancelled = [], []

    def timer(_hass, seconds, callback):
        assert seconds == 120
        timers.append(callback)
        return lambda: cancelled.append(True)

    with patch("custom_components.lichtzentrale.live_preview.async_call_later", side_effect=timer):
        session = await editor.preview.begin(editor.area, editor.owner)
        await editor.preview.apply(session["preview_id"], editor.owner, sequence=1, scene=scene(editor))
        editor.preview.keepalive(session["preview_id"], editor.owner)
        assert len(timers) == 3 and len(cancelled) == 2
        timers[-1](None)
        await hass.async_block_till_done()
    assert not editor.preview.sessions
    assert hass.states.get(editor.ids[0]).attributes["brightness"] == 100


async def test_unsaved_dynamic_ticks_and_cancel_never_persist(hass, store, editor):
    before = store.data
    session = await editor.preview.begin(editor.area, editor.owner)
    draft = scene(editor, dynamic={"enabled": True, "tempo": "medium"}, lamp_settings={editor.ids[1]: {"mode": "fixed", "color_temp_kelvin": 2800, "brightness": 22}})
    await editor.preview.apply(session["preview_id"], editor.owner, sequence=1, scene=draft)
    active = hass.data[DOMAIN]["dynamic"]
    run = active.active[editor.area]
    for offset in range(1, 4):
        assert await active.tick(run, offset)
    assert store.data == before
    assert hass.states.get(editor.ids[1]).attributes["brightness"] == 22
    await editor.preview.cancel(session["preview_id"], editor.owner)
    assert not active.active
    assert not store.data["active_dynamic"]
    assert hass.states.get(editor.ids[1]).attributes["brightness"] == 101


@pytest.mark.parametrize("setting", [{"mode": "fixed", "xy": None}, {"mode": "fixed", "color_temp_kelvin": None}, {"mode": "fixed", "color_temp_kelvin": "warm"}, {"mode": "fixed", "palette_index": {}}, {"mode": "moon", "moon": {"new_xy": None}}])
async def test_malformed_settings_fail_with_validation_error(hass, store, editor, setting):
    with pytest.raises(ServiceValidationError):
        validate_scene(hass, store, scene(editor, lamp_settings={editor.ids[0]: setting}))


async def test_cancel_failed_lamp_retry_is_limited_and_expired_cancel_idempotent(hass, editor):
    session = await editor.preview.begin(editor.area, editor.owner)
    await editor.preview.apply(session["preview_id"], editor.owner, sequence=1, scene=scene(editor))
    real_call = hass.services.async_call

    async def fail_one(domain, service, data, **kwargs):
        if data["entity_id"] == editor.ids[0]:
            raise ServiceValidationError("Synthetic unavailable lamp")
        return await real_call(domain, service, data, **kwargs)

    with patch.object(type(hass.services), "async_call", side_effect=fail_one):
        result = await editor.preview.cancel(session["preview_id"], editor.owner)
    assert result["failed"] == [editor.ids[0]]
    assert session["preview_id"] in editor.preview.sessions
    editor.calls.clear()
    await editor.preview.cancel(session["preview_id"], editor.owner)
    assert [data["entity_id"] for _, data in editor.calls] == [editor.ids[0]]
    assert (await editor.preview.cancel(session["preview_id"], editor.owner))["expired"]


async def test_preview_never_expands_open_target_cap(hass, store, editor):
    session = await editor.preview.begin(editor.area, editor.owner)
    extra = er.async_get(hass).async_get_or_create("light", "synthetic", "extra-preview-member")
    er.async_get(hass).async_update_entity(extra.entity_id, area_id=editor.area)
    hass.states.async_set(extra.entity_id, "on", {"supported_color_modes": ["xy"], "brightness": 75})
    await store.async_set_lights([*editor.ids, extra.entity_id])
    await editor.preview.apply(session["preview_id"], editor.owner, sequence=1, scene=scene(editor))
    assert extra.entity_id not in {data["entity_id"] for _, data in editor.calls}
    await editor.preview.cancel(session["preview_id"], editor.owner)
    assert extra.entity_id not in {data["entity_id"] for _, data in editor.calls}


async def test_legacy_palette_xy_pairs_display_without_mutating_store(store):
    legacy = {"id": "synthetic_legacy_palette", "colors": [[.3, .4], {"x": .4, "y": .3}], "future": True}
    store._data["palettes"].append(legacy)
    decorated = get_palette(store, legacy["id"])
    assert decorated["colors"] == [{"x": .3, "y": .4}, {"x": .4, "y": .3}]
    assert len(decorated["preview"]) == 2
    assert store.data["palettes"] == [legacy]


async def test_binding_preflight_rejects_malformed_settings_before_side_effects(hass, store, editor):
    from custom_components.lichtzentrale.bindings import _check_scene

    saved = await async_save_scene(hass, store, scene(editor))
    store._data["scenes"][0]["lamp_settings"] = {editor.ids[0]: {"mode": "fixed", "color_temp_kelvin": None}}
    with pytest.raises(ServiceValidationError):
        _check_scene(hass, store, saved["id"], editor.area)
    assert not editor.calls


async def test_committed_scene_reports_playback_warning_without_duplicate_retry(hass, store, editor):
    session = await editor.preview.begin(editor.area, editor.owner)
    with patch.object(store, "async_set_last_scene", side_effect=ServiceValidationError("Synthetic metadata failure")):
        result = await editor.preview.commit(session["preview_id"], editor.owner, scene=scene(editor))
    assert result["scene"]["id"] == store.data["scenes"][0]["id"]
    assert result["notes"] and len(store.data["scenes"]) == 1
    assert session["preview_id"] not in editor.preview.sessions
    with pytest.raises(ServiceValidationError):
        await editor.preview.commit(session["preview_id"], editor.owner, scene=scene(editor))
    assert len(store.data["scenes"]) == 1
