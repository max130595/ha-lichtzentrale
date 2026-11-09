# Geändert für Lichtzentrale
"""Native HA 2026.11 smoke for effects, ambient buttons and scene scripts.

Real service/state events, temporary Store, and real two-second effect delays.
Synthetic entities only; no pytest fixtures, timing patches, or physical devices.
Run: .venv-target/bin/python scripts/smoke_stage5e.py
"""
import asyncio
import sys
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

import homeassistant  # noqa: F401
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.helpers import area_registry, device_registry, entity_registry

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from custom_components.lichtzentrale.bindings import BindingManager
from custom_components.lichtzentrale.const import DOMAIN
from custom_components.lichtzentrale.dynamic_scenes import DynamicSceneManager
from custom_components.lichtzentrale.live_preview import LivePreviewManager
from custom_components.lichtzentrale.rooms import async_set_light
from custom_components.lichtzentrale.scenes import async_apply_scene, async_save_scene
from custom_components.lichtzentrale.storage import LichtzentraleStore


async def run(directory):
    hass = HomeAssistant(directory)
    hass.config_entries = ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    bindings = dynamic = preview = None
    try:
        await area_registry.async_load(hass)
        device_registry.async_setup(hass)
        await device_registry.async_load(hass)
        await entity_registry.async_load(hass)
        store = LichtzentraleStore(hass)
        await store.async_load()
        calls = []
        loop = asyncio.get_running_loop()

        @callback
        def capture(call):
            calls.append((loop.time(), call))
            if call.domain == 'script':
                return
            entity = call.data['entity_id']
            state = hass.states.get(entity)
            attributes = {**state.attributes, **{k: v for k, v in call.data.items() if k != 'entity_id'}}
            hass.states.async_set(entity, 'off' if call.service == 'turn_off' else 'on', attributes, context=call.context)

        for domain, services in [('light', ['turn_on', 'turn_off']), ('script', ['turn_on'])]:
            for service in services:
                hass.services.async_register(domain, service, capture)
        accent, ceiling = 'light.fixture_5e_accent', 'light.fixture_5e_ceiling'
        for entity in (accent, ceiling):
            hass.states.async_set(entity, 'off', {'supported_color_modes': ['xy'], 'color_mode': 'xy',
                'brightness': 80, 'xy_color': (.31, .33), 'effect': 'none',
                'effect_list': ['sparkle', 'candle', 'stop_hue_effect']})
        hass.states.async_set('script.fixture_5e_music', 'off')
        await store.async_set_lights([accent, ceiling])
        zone = await store.async_save_zone({'name': 'Synthetic stage 5e', 'entity_ids': [accent, ceiling]})
        area = 'zone:' + zone['id']
        dynamic = DynamicSceneManager(hass, store)
        preview = LivePreviewManager(hass, store)
        bindings = BindingManager(hass, store)
        hass.data.setdefault(DOMAIN, {}).update(store=store, dynamic=dynamic, live_preview=preview, bindings=bindings)
        bindings.start()
        scene = await async_save_scene(hass, store, {
            'name': 'Synthetic effects and script', 'kind': 'snapshot', 'area_id': area,
            'lights': {accent: {'on': True, 'brightness': 140, 'xy': [.55, .25]}},
            'lamp_settings': {accent: {'effect': 'sparkle'}}, 'start_script': 'script.fixture_5e_music',
        })
        result = await async_apply_scene(hass, store, scene['id'])
        assert result['applied'] == [accent], result
        assert [(c.domain, c.service) for _, c in calls] == [('light', 'turn_on'), ('light', 'turn_on'), ('script', 'turn_on')]
        assert 'effect' not in calls[0][1].data and calls[1][1].data['effect'] == 'sparkle'
        delay = calls[1][0] - calls[0][0]
        assert delay >= 1.95, delay
        assert calls[2][0] >= calls[1][0]
        calls.clear()
        await async_set_light(hass, store, accent, on=False)
        assert [c.service for _, c in calls] == ['turn_on', 'turn_off']
        assert calls[0][1].data['effect'] == 'stop_hue_effect'
        print(f'PASS native effects: separate effect after {delay:.3f}s; script once after lights; effect stopped before off')

        calls.clear()
        task = asyncio.create_task(async_apply_scene(hass, store, scene['id']))
        await asyncio.sleep(.2)
        await hass.services.async_call('light', 'turn_on', {'entity_id': accent, 'brightness': 77}, blocking=True, context=Context())
        result = await task
        assert accent in result['failed'], result
        assert not any(c.data.get('effect') == 'sparkle' or c.domain == 'script' for _, c in calls)
        print('PASS native effect cancellation: foreign service prevents delayed overwrite and failed-start script')

        calls.clear()
        owner = object()
        session = await preview.begin(area, owner)
        await preview.apply(session['preview_id'], owner, sequence=1, scene=scene)
        await preview.cancel(session['preview_id'], owner)
        assert not any(c.domain == 'script' for _, c in calls)
        print('PASS native live preview/cancel: effect visible, no script playback')

        ambient = await async_save_scene(hass, store, {
            'name': 'Synthetic ambient', 'kind': 'snapshot', 'area_id': area,
            'lights': {accent: {'on': True, 'brightness': 90}, ceiling: {'on': False}},
        })
        for entity in (accent, ceiling):
            await async_set_light(hass, store, entity, on=False)
        binding = {'action': 'toggle_lights', 'area_id': area, 'params': {
            'entity_ids': [ceiling], 'on_behavior': {'mode': 'brightness', 'brightness': 255},
            'ambient_first': {'scene_id': ambient['id'], 'window': {
                'after': {'type': 'time', 'value': '00:00'}, 'before': {'type': 'time', 'value': '00:00'}}},
        }}
        for step in range(3):
            await bindings._action(binding, Context())
            await hass.async_block_till_done()
            expected = [('on', 'off'), ('off', 'on'), ('off', 'off')][step]
            assert (hass.states.get(accent).state, hass.states.get(ceiling).state) == expected
            if step == 1:
                assert hass.states.get(ceiling).attributes['brightness'] == 255
        await bindings._action(binding, Context())
        await hass.async_block_till_done()
        assert bindings.ambient_first.running(area, ambient['id'])
        await hass.services.async_call('light', 'turn_on', {'entity_id': accent, 'brightness': 99}, blocking=True, context=Context())
        await hass.async_block_till_done()
        assert not bindings.ambient_first.running(area, ambient['id'])
        print('PASS native ambient: accent-only first press, forced ceiling second press, off third press, manual ends ownership')

        # Every seasonal start dispatches a single wrapper script; restart restores
        # the concrete dynamic run without replaying the scene startup action.
        palette = await async_save_scene(hass, store, {'name': 'Synthetic restart', 'kind': 'palette',
            'area_id': area, 'palette_id': 'kupfernest', 'start_script': 'script.fixture_5e_music',
            'dynamic': {'enabled': True, 'interval': 60, 'transition': 0}})
        wrapper = await async_save_scene(hass, store, {'name': 'Synthetic seasons', 'kind': 'seasonal',
            'area_id': area, 'start_script': 'script.fixture_5e_music',
            'seasonal': {'scenes': {season: palette['id'] for season in ('spring', 'summer', 'autumn', 'winter')}}})
        calls.clear()
        await async_apply_scene(hass, store, wrapper['id'])
        assert len([c for _, c in calls if c.domain == 'script']) == 1
        await dynamic.shutdown()
        reloaded = LichtzentraleStore(hass)
        await reloaded.async_load()
        dynamic = DynamicSceneManager(hass, reloaded)
        hass.data[DOMAIN].update(store=reloaded, dynamic=dynamic)
        calls.clear()
        await dynamic.restore(wait_for_start=False)
        assert area in dynamic.active
        await dynamic.tick(dynamic.active[area], 1)
        assert calls and not any(c.domain == 'script' for _, c in calls)
        print('PASS native seasonal and restart: wrapper runs script once, restored dynamic run/tick never does')
    finally:
        if bindings:
            await bindings.shutdown()
        if preview:
            await preview.shutdown()
        if dynamic:
            await dynamic.shutdown()
        await hass.async_stop(force=True)


if __name__ == '__main__':
    assert version('homeassistant') == '2026.11.0'
    with TemporaryDirectory(prefix='lichtzentrale-stage5e-') as directory:
        asyncio.run(run(directory))
    print('PASS Home Assistant 2026.11.0 native isolated smoke; no real-device acceptance')
