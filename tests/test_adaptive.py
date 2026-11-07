# Geändert für Lichtzentrale
"""Optional Adaptive Lighting integration with synthetic runtime entities."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import Context, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lichtzentrale.adaptive import (
    async_pause_adaptive,
    async_resume_adaptive,
    async_set_adaptive,
    status,
)
from custom_components.lichtzentrale.storage import LichtzentraleStore


@pytest.fixture
async def adaptive(hass, store):
    area = ar.async_get(hass).async_create("Synthetic adaptive room")
    config = MockConfigEntry(domain="adaptive_lighting")
    config.add_to_hass(hass)
    registry = er.async_get(hass)
    light = registry.async_get_or_create("light", "synthetic", "adaptive-test-lamp")
    registry.async_update_entity(light.entity_id, area_id=area.id)
    hass.states.async_set(light.entity_id, "on", {"supported_color_modes": ["color_temp"]})
    await store.async_set_lights([light.entity_id])
    switch = registry.async_get_or_create(
        "switch", "adaptive_lighting", "test-main", config_entry=config
    )
    hass.states.async_set(switch.entity_id, "on")
    runtime = SimpleNamespace(entity_id=switch.entity_id, lights=[light.entity_id])
    hass.data["adaptive_lighting"] = {config.entry_id: {"switch": runtime}}
    calls = []

    @callback
    def capture(call):
        calls.append(call)
        if call.domain == "switch":
            hass.states.async_set(switch.entity_id, "on" if call.service == "turn_on" else "off")

    for domain, services in {
        "adaptive_lighting": ["apply", "set_manual_control"],
        "switch": ["turn_on", "turn_off"],
    }.items():
        for service in services:
            hass.services.async_register(domain, service, capture)
    return area.id, light.entity_id, switch.entity_id, runtime, calls


async def test_absent_is_optional(hass, store):
    assert status(hass, store) == {"available": False, "rooms": [], "switches": []}
    await async_pause_adaptive(hass, store, "synthetic-area")
    await async_resume_adaptive(hass, store, "synthetic-area")


async def test_mapping_persists_and_color_resume_context(hass, store, adaptive):
    area, light, switch, _, calls = adaptive
    context = Context()
    result = await async_set_adaptive(
        hass, store, area, adaptive_switch=switch, default_on="adaptive"
    )
    assert result["rooms"][0]["enabled"]
    reloaded = LichtzentraleStore(hass)
    await reloaded.async_load()
    assert reloaded.data["rooms"][area] == {"adaptive_switch": switch, "default_on": "adaptive"}
    await async_pause_adaptive(hass, store, area, context)
    assert not status(hass, store)["rooms"][0]["enabled"]
    await async_resume_adaptive(hass, store, area, context)
    assert [(call.domain, call.service) for call in calls] == [
        ("switch", "turn_off"),
        ("switch", "turn_on"),
        ("adaptive_lighting", "set_manual_control"),
        ("adaptive_lighting", "apply"),
    ]
    assert calls[-1].data == {"entity_id": switch, "lights": [light], "turn_on_lights": False}
    assert calls[-2].data["manual_control"] is False
    assert all(call.context == context for call in calls)
    await async_set_adaptive(hass, store, area, adaptive_switch=None)
    assert store.data["rooms"][area]["default_on"] == "last"


@pytest.mark.parametrize(
    "mutation", ["unapproved", "moved", "group", "auxiliary", "unavailable", "missing_service"]
)
async def test_unsafe_mapping_has_no_side_effects(hass, store, adaptive, mutation):
    area, light, switch, runtime, calls = adaptive
    if mutation == "unapproved":
        await store.async_set_lights([])
    elif mutation == "moved":
        other = ar.async_get(hass).async_create("Other synthetic room")
        er.async_get(hass).async_update_entity(light, area_id=other.id)
    elif mutation == "group":
        hass.states.async_set(light, "on", {"entity_id": ["light.synthetic_member"]})
    elif mutation == "auxiliary":
        runtime.entity_id = "switch.synthetic_auxiliary"
    elif mutation == "unavailable":
        hass.states.async_set(switch, "unavailable")
    else:
        hass.services.async_remove("adaptive_lighting", "apply")
    with pytest.raises(ServiceValidationError):
        await async_set_adaptive(hass, store, area, enabled=True, adaptive_switch=switch)
    assert not calls
    assert not store.data["rooms"]


async def test_revalidate_existing_mapping_after_allowlist_change(hass, store, adaptive):
    area, _, switch, _, calls = adaptive
    await async_set_adaptive(hass, store, area, adaptive_switch=switch)
    await store.async_set_lights([])
    with pytest.raises(ServiceValidationError):
        await async_resume_adaptive(hass, store, area)
    assert not calls
    result = status(hass, store)["rooms"][0]
    assert not result["available"] and result["reason"]


async def test_revalidate_between_awaits(hass, store, adaptive):
    area, _, switch, _, _ = adaptive
    await async_set_adaptive(hass, store, area, adaptive_switch=switch)

    async def revoke(*args, **kwargs):
        await store.async_set_lights([])

    with patch.object(type(hass.services), "async_call", side_effect=revoke) as call:
        with pytest.raises(ServiceValidationError):
            await async_resume_adaptive(hass, store, area)
    assert call.call_count == 1


async def test_settings_failure_does_not_update_memory(hass, store, adaptive):
    area, _, switch, _, _ = adaptive
    with patch.object(store._store, "async_save", new=AsyncMock(side_effect=OSError("fixture"))):
        with pytest.raises(OSError):
            await async_set_adaptive(hass, store, area, adaptive_switch=switch)
    assert not store.data["rooms"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"enabled": 1},
        {"default_on": []},
        {"adaptive_switch": []},
        {"enabled": True},
        {"default_on": "adaptive"},
    ],
)
async def test_invalid_parameters(hass, store, adaptive, kwargs):
    with pytest.raises(ServiceValidationError):
        await async_set_adaptive(hass, store, adaptive[0], **kwargs)
    assert not adaptive[-1]


async def test_failed_service_does_not_persist_mapping(hass, store, adaptive):
    from homeassistant.exceptions import HomeAssistantError

    area, _, switch, _, _ = adaptive
    with patch.object(type(hass.services), "async_call", side_effect=HomeAssistantError("fixture")):
        with pytest.raises(HomeAssistantError):
            await async_set_adaptive(hass, store, area, enabled=True, adaptive_switch=switch)
    assert not store.data["rooms"]


async def test_set_waits_for_scene_lock(hass, store, adaptive):
    import asyncio

    from custom_components.lichtzentrale.const import DOMAIN

    area, _, switch, _, calls = adaptive
    lock = asyncio.Lock()
    hass.data.setdefault(DOMAIN, {}).setdefault("scene_locks", {})[area] = lock
    async with lock:
        task = asyncio.create_task(
            async_set_adaptive(hass, store, area, enabled=False, adaptive_switch=switch)
        )
        await asyncio.sleep(0)
        assert not calls and not task.done()
    await task
    assert calls[0].service == "turn_off"


async def test_enabling_stops_dynamics_before_switch(hass, store, adaptive):
    area, _, switch, _, calls = adaptive
    stopped = []

    async def stop(hass, area_id):
        assert not calls
        stopped.append(area_id)

    with patch("custom_components.lichtzentrale.dynamic_scenes.stop_dynamic", side_effect=stop):
        await async_set_adaptive(hass, store, area, enabled=True, adaptive_switch=switch)
    assert stopped == [area]


async def test_room_on_only_enables_actual_adaptive_subset(hass, store, adaptive):
    from custom_components.lichtzentrale.rooms import async_toggle_room

    area, light, switch, _, calls = adaptive
    registry = er.async_get(hass)
    extras = []
    for domain, platform, name in [
        ("light", "synthetic", "Other adaptive lamp"),
        ("switch", "shelly", "Synthetic Deckenlicht"),
    ]:
        entry = registry.async_get_or_create(domain, platform, name, original_name=name)
        registry.async_update_entity(entry.entity_id, area_id=area)
        hass.states.async_set(entry.entity_id, "off")
        extras.append(entry.entity_id)
    await store.async_set_lights([light, *extras])
    await async_set_adaptive(hass, store, area, adaptive_switch=switch, default_on="adaptive")
    result = await async_toggle_room(hass, store, area, on=True)
    assert result == {"applied": [light], "skipped": extras}
    assert calls[-1].data == {"entity_id": switch, "lights": [light], "turn_on_lights": True}
    assert all(call.data["entity_id"] == switch for call in calls)


@pytest.mark.parametrize("mutation", ["missing", "revoked", "moved", "switch"])
async def test_room_on_invalid_adaptive_never_falls_back(hass, store, adaptive, mutation):
    from custom_components.lichtzentrale.rooms import async_toggle_room

    area, light, switch, runtime, calls = adaptive
    await async_set_adaptive(hass, store, area, adaptive_switch=switch, default_on="adaptive")
    if mutation == "missing":
        hass.data.pop("adaptive_lighting")
    elif mutation == "revoked":
        await store.async_set_lights([])
    elif mutation == "moved":
        other = ar.async_get(hass).async_create("Another adaptive fixture")
        er.async_get(hass).async_update_entity(light, area_id=other.id)
    else:
        runtime.lights = [switch]
    with patch.object(type(hass.services), "async_call") as call:
        with pytest.raises(ServiceValidationError):
            await async_toggle_room(hass, store, area, on=True)
    assert not calls
    call.assert_not_called()


async def test_adaptive_room_on_revalidates_after_stop(hass, store, adaptive):
    from custom_components.lichtzentrale.rooms import async_toggle_room

    area, _, switch, _, calls = adaptive
    await async_set_adaptive(hass, store, area, adaptive_switch=switch, default_on="adaptive")

    async def revoke(*args):
        await store.async_set_lights([])

    with patch("custom_components.lichtzentrale.dynamic_scenes.stop_dynamic", side_effect=revoke):
        with pytest.raises(ServiceValidationError):
            await async_toggle_room(hass, store, area, on=True)
    assert not calls


async def test_invalid_adaptive_room_on_preserves_pending_off_cycle(hass, store, adaptive):
    from custom_components.lichtzentrale.rooms import async_toggle_room

    area, light, switch, _, calls = adaptive
    await async_set_adaptive(hass, store, area, adaptive_switch=switch, default_on="adaptive")
    await store.async_update_room(
        area,
        {
            "pre_off_lights": {light: {"on": True, "brightness": 83}},
            "pre_off_pending": [light],
        },
    )
    hass.data.pop("adaptive_lighting")
    with pytest.raises(ServiceValidationError):
        await async_toggle_room(hass, store, area, on=True)
    reloaded = LichtzentraleStore(hass)
    await reloaded.async_load()
    assert reloaded.data["rooms"][area]["pre_off_pending"] == [light]
    assert reloaded.data["rooms"][area]["pre_off_lights"][light]["brightness"] == 83
    assert not calls
