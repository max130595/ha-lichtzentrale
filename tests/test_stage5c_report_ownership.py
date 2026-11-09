# Geändert für Lichtzentrale
"""Delayed synthetic Zigbee reports must not surrender playback ownership."""

from datetime import timedelta

import pytest
from homeassistant.core import Context
from test_stage5c_backend import editor as editor_fixture
from test_stage5c_backend import scene

from custom_components.lichtzentrale.const import DOMAIN
from custom_components.lichtzentrale.scenes import async_save_scene

editor = editor_fixture


@pytest.fixture(autouse=True)
def no_command_spacing(monkeypatch):
    """A frozen clock cannot advance the unrelated command-spacing wait."""
    monkeypatch.setattr("custom_components.lichtzentrale.command_limiter.COMMAND_SPACING", 0)


@pytest.mark.parametrize("tempo", ["slow", "very_slow"])
@pytest.mark.parametrize("report", [{"brightness": 91}, {"xy_color": [.32, .28]}])
async def test_dynamic_delayed_report_keeps_lamp_and_next_tick(
    hass, store, editor, freezer, tempo, report
):
    dynamic = hass.data[DOMAIN]["dynamic"]
    saved = await async_save_scene(hass, store, scene(
        editor, dynamic={"enabled": True, "tempo": tempo}
    ))
    await dynamic.start(saved, Context())
    run = dynamic.active[editor.area]
    assert await dynamic.tick(run, 1)
    await hass.async_block_till_done()
    entity = editor.ids[0]
    commanded = hass.states.get(entity)
    freezer.tick(timedelta(seconds=10))
    hass.states.async_set(entity, "on", {**commanded.attributes, **report})
    await hass.async_block_till_done()
    reported = hass.states.get(entity)
    assert (reported.last_updated - commanded.last_updated).total_seconds() >= 10
    assert reported.context.user_id is None
    assert reported.context.id != run["context"].id
    assert not run["excluded"]
    assert dynamic.active[editor.area] is run
    editor.calls.clear()
    assert await dynamic.tick(run, 2)
    assert entity in {data["entity_id"] for _, data in editor.calls}


@pytest.mark.parametrize("action", ["service", "off", "frontend", "frontend_color_mode", "own", "own_child"])
async def test_dynamic_distinguishes_manual_and_owned_changes(hass, store, editor, action):
    dynamic = hass.data[DOMAIN]["dynamic"]
    saved = await async_save_scene(hass, store, scene(
        editor, dynamic={"enabled": True, "tempo": "slow"}
    ))
    await dynamic.start(saved, Context(user_id="synthetic-user"))
    run = dynamic.active[editor.area]
    entity = editor.ids[0]
    await change(hass, entity, action, run["context"])
    assert (entity in run["excluded"]) == (action in {"service", "off", "frontend", "frontend_color_mode"})
    assert dynamic.active[editor.area] is run


@pytest.mark.parametrize("tempo", ["slow", "very_slow"])
@pytest.mark.parametrize("report", [{"brightness": 91}, {"xy_color": [.32, .28]}])
async def test_preview_delayed_report_keeps_original_for_cancel(
    hass, editor, freezer, tempo, report
):
    opened = await editor.preview.begin(editor.area, editor.owner)
    preview_id = opened["preview_id"]
    session = editor.preview.sessions[preview_id]
    await editor.preview.apply(preview_id, editor.owner, sequence=1, scene=scene(
        editor, dynamic={"enabled": True, "tempo": tempo}
    ))
    await hass.async_block_till_done()
    entity = editor.ids[0]
    commanded = hass.states.get(entity)
    generation = session["generation"]
    freezer.tick(timedelta(seconds=10))
    hass.states.async_set(entity, "on", {**commanded.attributes, **report})
    await hass.async_block_till_done()
    reported = hass.states.get(entity)
    assert (reported.last_updated - commanded.last_updated).total_seconds() >= 10
    assert reported.context.user_id is None
    assert reported.context.id != session["context"].id
    assert entity not in session["released"]
    assert entity in session["touched"]
    assert session["generation"] == generation
    result = await editor.preview.cancel(preview_id, editor.owner)
    assert entity in result["applied"]
    restored = hass.states.get(entity)
    assert restored.state == "on"
    assert restored.attributes["brightness"] == 100
    assert restored.attributes["xy_color"] == [.4, .3]


@pytest.mark.parametrize("action", ["service", "off", "frontend", "frontend_color_mode", "own", "own_child"])
async def test_preview_distinguishes_manual_and_owned_changes(hass, editor, action):
    opened = await editor.preview.begin(editor.area, editor.owner, Context(user_id="synthetic-user"))
    preview_id = opened["preview_id"]
    session = editor.preview.sessions[preview_id]
    await editor.preview.apply(preview_id, editor.owner, sequence=1, scene=scene(editor))
    await hass.async_block_till_done()
    entity = editor.ids[0]
    generation = session["generation"]
    await change(hass, entity, action, session["context"])
    manual = action in {"service", "off", "frontend", "frontend_color_mode"}
    assert (entity in session["released"]) == manual
    assert (session["generation"] > generation) == manual
    before_cancel = hass.states.get(entity)
    result = await editor.preview.cancel(preview_id, editor.owner)
    if manual:
        assert entity not in result["applied"]
        assert hass.states.get(entity) is before_cancel
    else:
        assert entity in result["applied"]
        assert hass.states.get(entity).attributes["brightness"] == 100


async def change(hass, entity, action, own_context):
    """Exercise actual HA service/state events with synthetic user identifiers."""
    if action == "service":
        await hass.services.async_call("light", "turn_on", {
            "entity_id": entity, "brightness": 23,
        }, blocking=True, context=Context())
    else:
        contexts = {
            "off": None,
            "frontend": Context(user_id="synthetic-other-user"),
            "frontend_color_mode": Context(user_id="synthetic-other-user"),
            "own": own_context,
            "own_child": Context(parent_id=own_context.id, user_id="synthetic-user"),
        }
        attributes = dict(hass.states.get(entity).attributes)
        attributes.update({"color_mode": "hs"} if action == "frontend_color_mode"
                          else {"brightness": 23})
        hass.states.async_set(entity, "off" if action == "off" else "on", attributes,
                              context=contexts[action])
    await hass.async_block_till_done()
