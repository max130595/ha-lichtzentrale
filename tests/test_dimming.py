# Geändert für Lichtzentrale
"""Synthetic lower-bound, dispatch-race and persistence regressions."""
import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from custom_components.lichtzentrale.bindings import BindingManager
from custom_components.lichtzentrale.dimming import dim_payload
from custom_components.lichtzentrale.selected_lights import async_dim_lights
from custom_components.lichtzentrale.storage import LichtzentraleStore
from custom_components.lichtzentrale.websocket_api import async_setup_websocket_api


@pytest.mark.parametrize('pct', range(1, 21))
def test_every_brightness_matches_native_rounding(pct):
    floor = round(pct * 255 / 100)
    for bri in range(1, 256):
        state = State('light.synthetic', 'on', {'supported_color_modes': ['brightness'], 'brightness': bri})
        payload = dim_payload(state, -1, pct)
        native = round((round(bri / 255 * 100) - 10) / 100 * 255)
        if bri <= floor:
            assert payload is None
        elif native <= floor:
            assert payload == {'entity_id': state.entity_id, 'brightness': floor}
        else:
            assert payload == {'entity_id': state.entity_id, 'brightness_step_pct': -10}


@pytest.mark.parametrize('mode', ['onoff', 'unknown', None])
def test_bogus_brightness_does_not_make_dimmable(mode):
    state = State('light.synthetic', 'on', {'supported_color_modes': [mode] if mode else [], 'brightness': 128})
    assert dim_payload(state, -1, 1) is None
    assert dim_payload(state, 1, 1) is None


@pytest.mark.parametrize('brightness', [None, True, 1.5, '128', 0, 256])
def test_unknown_brightness_is_skipped(brightness):
    assert dim_payload(State('light.synthetic', 'on', {'supported_color_modes': ['xy'], 'brightness': brightness}), -1, 1) is None


def test_unknown_current_color_never_injects_color():
    assert dim_payload(State('light.synthetic', 'on', {'supported_color_modes': ['xy'], 'color_mode': 'unknown', 'brightness': 13}), -1, 1) == {'entity_id': 'light.synthetic', 'brightness': 3}


@pytest.fixture
async def rig(hass, store):
    area = ar.async_get(hass).async_create('Synthetic dim room').id
    ids = []
    for i, brightness in enumerate([13, 3, 128]):
        entry = er.async_get(hass).async_get_or_create('light', 'synthetic', f'dim-{i}')
        er.async_get(hass).async_update_entity(entry.entity_id, area_id=area)
        hass.states.async_set(entry.entity_id, 'on', {'supported_color_modes': ['brightness'], 'brightness': brightness})
        ids.append(entry.entity_id)
    await store.async_set_lights(ids)
    zone = await store.async_save_zone({'name': 'Synthetic dim zone', 'entity_ids': ids})
    return area, ids, 'zone:' + zone['id']


async def invoke(hass, store, rig, route):
    area, ids, zone = rig
    if route == 'selected':
        return await async_dim_lights(hass, store, ids, -1)
    return await BindingManager(hass, store)._dim(zone if route == 'zone' else area, -1, None)


@pytest.mark.parametrize('route', ['room', 'zone', 'selected'])
async def test_mixed_floor_normal_and_hold_repeat(hass, store, rig, route):
    calls = []
    async def dispatch(domain, service, data, **kwargs):
        assert service == 'turn_on'
        calls.append(dict(data))
        previous = hass.states.get(data['entity_id'])
        bri = data.get('brightness', round((round(previous.attributes['brightness']/255*100)-10)/100*255))
        hass.states.async_set(previous.entity_id, 'on', {**previous.attributes, 'brightness': bri})
    with patch.object(type(hass.services), 'async_call', side_effect=dispatch):
        for _ in range(8):
            await invoke(hass, store, rig, route)
    assert calls[0] == {'entity_id': rig[1][0], 'brightness': 3}
    assert calls[1] == {'entity_id': rig[1][2], 'brightness_step_pct': -10}
    assert rig[1][1] not in [c['entity_id'] for c in calls]
    assert all(hass.states.get(entity).attributes['brightness'] == 3 for entity in rig[1])


@pytest.mark.parametrize('route', ['room', 'zone', 'selected'])
@pytest.mark.parametrize('change', ['lower', 'floor', 'off', 'onoff', 'setting'])
async def test_final_dispatch_refreshes_state_and_setting(hass, store, rig, route, change):
    from custom_components.lichtzentrale.rooms import async_dispatch
    entity = rig[1][2]
    async def delayed(hass, calls, skipped=None, context=None, guard=None):
        previous = hass.states.get(entity)
        attrs = dict(previous.attributes)
        if change in {'lower', 'floor'}:
            attrs['brightness'] = 13 if change == 'lower' else 3
        if change == 'onoff':
            attrs['supported_color_modes'] = ['onoff']
        hass.states.async_set(entity, 'off' if change == 'off' else 'on', attrs)
        if change == 'setting':
            await store.async_set_dim_min_pct(20)
            hass.states.async_set(entity, 'on', {**attrs, 'brightness': 60})
        return await async_dispatch(hass, calls, skipped, context, guard)
    module = 'selected_lights' if route == 'selected' else 'bindings'
    with (patch(f'custom_components.lichtzentrale.{module}.async_dispatch', delayed),
          patch.object(type(hass.services), 'async_call', AsyncMock()) as call):
        await invoke(hass, store, rig, route)
    payloads = {c.args[2]['entity_id']: c.args[2] for c in call.await_args_list}
    if change in {'floor', 'off', 'onoff'}:
        assert entity not in payloads
    else:
        assert payloads[entity] == {'entity_id': entity, 'brightness': 51 if change == 'setting' else 3}


@pytest.mark.parametrize('invalid', [None, True, False, 0, 21, -1, 1.5, 1.0, '5', [], {}])
async def test_invalid_settings_never_write(store, invalid):
    before = store.data
    with patch.object(store._store, 'async_save', AsyncMock()) as save:
        with pytest.raises(ServiceValidationError):
            await store.async_set_dim_min_pct(invalid)
    save.assert_not_awaited()
    assert store.data == before


async def test_load_defaults_no_migration_and_preserves_fields(hass):
    store = LichtzentraleStore(hass)
    saved = {'settings': {'light_entity_ids': [], 'future': {'x': 1}}, 'future': [7]}
    with (patch.object(store._store, 'async_load', AsyncMock(return_value=saved)),
          patch.object(store._store, 'async_save', AsyncMock()) as save):
        await store.async_load()
    save.assert_not_awaited()
    assert store.data['settings']['dim_min_pct'] == 1
    await asyncio.gather(store.async_set_dim_min_pct(20), store.async_set_lights(['light.synthetic']))
    loaded = LichtzentraleStore(hass)
    await loaded.async_load()
    assert loaded.data['settings'] == {'dim_min_pct': 20, 'light_entity_ids': ['light.synthetic'], 'future': {'x': 1}}
    assert loaded.data['future'] == [7]


async def test_persistence_failure_is_atomic(store):
    before = deepcopy(store.data)
    with patch.object(store._store, 'async_save', AsyncMock(side_effect=HomeAssistantError('synthetic failure'))):
        with pytest.raises(HomeAssistantError):
            await store.async_set_dim_min_pct(15)
    assert store.data == before


async def test_settings_websocket(hass, store, hass_ws_client):
    hass.data['lichtzentrale'] = {'store': store}
    async_setup_websocket_api(hass)
    client = await hass_ws_client(hass)
    async def request(command, **data):
        await client.send_json_auto_id({'type': f'lichtzentrale/settings/{command}', **data})
        return await client.receive_json()
    assert (await request('get'))['result'] == {'dim_min_pct': 1}
    for invalid in [None, True, 0, 21, 1.5, '5']:
        assert not (await request('dimming', dim_min_pct=invalid))['success']
    assert not (await request('dimming'))['success']
    assert (await request('dimming', dim_min_pct=20))['result'] == {'dim_min_pct': 20}
    assert (await request('get'))['result'] == {'dim_min_pct': 20}


@pytest.mark.parametrize('command,data', [('get', {}), ('dimming', {'dim_min_pct': 10})])
async def test_settings_require_admin(hass, store, hass_ws_client, hass_read_only_access_token, command, data):
    hass.data['lichtzentrale'] = {'store': store}
    async_setup_websocket_api(hass)
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    await client.send_json_auto_id({'type': f'lichtzentrale/settings/{command}', **data})
    result = await client.receive_json()
    assert result['error']['code'] == 'unauthorized'
    assert store.data['settings']['dim_min_pct'] == 1


async def test_websocket_save_failure_returns_error_without_publish(hass, store, hass_ws_client):
    hass.data['lichtzentrale'] = {'store': store}
    async_setup_websocket_api(hass)
    client = await hass_ws_client(hass)
    with patch.object(store._store, 'async_save', AsyncMock(side_effect=HomeAssistantError('synthetic disk failure'))):
        await client.send_json_auto_id({'type': 'lichtzentrale/settings/dimming', 'dim_min_pct': 10})
        result = await client.receive_json()
    assert result['error']['code'] == 'invalid_request'
    assert store.data['settings']['dim_min_pct'] == 1
