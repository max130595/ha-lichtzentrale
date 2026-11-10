# Geändert für Lichtzentrale
"""Vacation API boundaries, native switch and atomic Store persistence."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError, Unauthorized
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lichtzentrale.const import DOMAIN
from custom_components.lichtzentrale.storage import LichtzentraleStore
from custom_components.lichtzentrale.vacation_api import list_notify_services
from custom_components.lichtzentrale.vacation_config import default_vacation_config
from custom_components.lichtzentrale.websocket_api import async_setup_websocket_api


async def test_vacation_store_defaults_and_reload(hass, store):
    assert store.data['vacation'] == {'enabled': False, 'until': None, 'config': default_vacation_config(), 'runtime': {}}
    await store.async_update_vacation({'until': '2027-01-10', 'runtime': {'future': 'preserved'}})
    await store.async_update_vacation({'enabled': True})
    fresh = LichtzentraleStore(hass)
    await fresh.async_load()
    assert fresh.data == store.data
    assert fresh.data['vacation']['runtime']['future'] == 'preserved'
    assert fresh.data['vacation']['until'] == '2027-01-10'
    await fresh.async_update_vacation({'until': None})
    assert fresh.data['vacation']['until'] is None


async def test_vacation_failed_store_write_keeps_all_state(store):
    before = deepcopy(store.data)
    store._store.async_save = AsyncMock(side_effect=OSError('Synthetic disk failure'))
    with pytest.raises(OSError):
        await store.async_update_vacation({'enabled': True, 'until': '2027-01-10'})
    assert store.data == before


@pytest.mark.parametrize('patch', [{'enabled': 1}, {'enabled': 'yes'}, {'until': '2027-02-30'}, {'until': 'tomorrow'}, {'config': {}}])
async def test_vacation_store_rejects_invalid_values(store, patch):
    before = store.data
    with pytest.raises(ServiceValidationError):
        await store.async_update_vacation(patch)
    assert store.data == before


def test_notify_catalogue_only_named_services(hass):
    for name in ['fixture_mobile', 'send_message', 'fixture_mail']:
        hass.services.async_register('notify', name, lambda call: None)
    assert list_notify_services(hass) == [
        {'service': 'notify.fixture_mail', 'name': 'fixture mail'},
        {'service': 'notify.fixture_mobile', 'name': 'fixture mobile'},
    ]


@pytest.fixture
async def api(hass, store):
    state = {'enabled': False, 'until': None, 'config': default_vacation_config(), 'plan': [],
             'next_switch': None, 'section': None, 'excluded': [], 'testing': False, 'notes': []}
    manager = SimpleNamespace(closed=False, status=Mock(return_value=state),
        async_save_config=AsyncMock(return_value=state), async_set_enabled=AsyncMock(return_value=state),
        async_test=AsyncMock(return_value=state))
    hass.data[DOMAIN] = {'store': store, 'vacation': manager}
    async_setup_websocket_api(hass)
    return manager


async def test_vacation_websocket_get_save_set_test(hass, hass_ws_client, api):
    client = await hass_ws_client(hass)
    for command, extra in [
        ('get', {}), ('save', {'config': default_vacation_config(), 'until': '2027-01-10'}),
        ('set', {'enabled': True, 'until': None}), ('test', {}), ('notify_services', {}),
    ]:
        await client.send_json_auto_id({'type': f'lichtzentrale/vacation/{command}', **extra})
        assert (await client.receive_json())['success']
    api.async_save_config.assert_awaited_once_with(default_vacation_config(), until='2027-01-10')
    assert api.async_set_enabled.call_args.args == (True,)
    assert api.async_set_enabled.call_args.kwargs['until'] is None
    assert isinstance(api.async_set_enabled.call_args.kwargs['context'], Context)
    api.async_test.assert_awaited_once()


@pytest.mark.parametrize('command,extra', [
    ('get', {}), ('save', {'config': {}}), ('set', {'enabled': True}), ('test', {}), ('notify_services', {}),
])
async def test_vacation_websocket_requires_admin(hass, hass_ws_client, hass_read_only_access_token, api, command, extra):
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    await client.send_json_auto_id({'type': f'lichtzentrale/vacation/{command}', **extra})
    result = await client.receive_json()
    assert not result['success'] and result['error']['code'] == 'unauthorized'
    api.async_save_config.assert_not_awaited()
    api.async_set_enabled.assert_not_awaited()
    api.async_test.assert_not_awaited()


async def test_vacation_api_after_unload_fails_cleanly(hass, hass_ws_client, api):
    client = await hass_ws_client(hass)
    hass.data[DOMAIN].pop('vacation')
    await client.send_json_auto_id({'type': 'lichtzentrale/vacation/get'})
    result = await client.receive_json()
    assert not result['success']
    assert 'nicht geladen' in result['error']['message']


async def test_native_vacation_switch_service_reload_and_unload(hass, hass_read_only_user):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get('switch.lichtzentrale_urlaubsmodus')
    assert state and state.state == 'off'
    assert hass.services.has_service(DOMAIN, 'set_vacation')
    with pytest.raises(Unauthorized):
        await hass.services.async_call(DOMAIN, 'set_vacation', {'enabled': True},
            blocking=True, context=Context(user_id=hass_read_only_user.id))
    manager = hass.data[DOMAIN]['vacation']
    # An explicit dashboard command delegates to the same manager; no device IO.
    manager.async_set_enabled = AsyncMock(return_value=manager.status())
    await hass.services.async_call('switch', 'turn_on', {'entity_id': state.entity_id}, blocking=True)
    manager.async_set_enabled.assert_awaited_once()
    assert manager.async_set_enabled.call_args.args == (True,)
    assert 'until' not in manager.async_set_enabled.call_args.kwargs
    manager.async_set_enabled.reset_mock()
    await hass.services.async_call(DOMAIN, 'set_vacation', {'enabled': False, 'until': '2027-01-10'}, blocking=True)
    assert manager.async_set_enabled.call_args.kwargs['until'] == '2027-01-10'
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not hass.services.has_service(DOMAIN, 'set_vacation')
    assert 'vacation' not in hass.data[DOMAIN]
    assert hass.states.get(state.entity_id).state == 'unavailable'
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(state.entity_id).state == 'off'


async def test_explicit_unloaded_vacation_is_not_available(hass):
    from custom_components.lichtzentrale.vacation_api import get_vacation
    with pytest.raises(HomeAssistantError):
        get_vacation(hass)
