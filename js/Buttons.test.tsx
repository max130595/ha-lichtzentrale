// Geändert für Lichtzentrale
// @vitest-environment jsdom
import {afterEach, describe, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {Buttons} from './Buttons';
import {App} from './App';
import type {AdaptiveStatus} from './RuntimeControls';
import type {Binding, ButtonEntity, Hass, Light, Room, Scene} from './types';

const rooms: Room[] = [
  {area_id: 'test_room_a', name: 'Testraum A', lights: [], on: false, brightness: null, available_count: 0, cycle: ['test_scene_a'], default_on: 'last'},
  {area_id: 'test_room_b', name: 'Testraum B', lights: [], on: false, brightness: null, available_count: 0, cycle: [], default_on: 'last'},
];
const scenes: Scene[] = [
  {id: 'test_scene_a', name: 'Testszene A', area_id: 'test_room_a', kind: 'snapshot', favorite: false, order: 0, preview: []},
  {id: 'test_scene_a2', name: 'Testszene A2', area_id: 'test_room_a', kind: 'snapshot', favorite: false, order: 1, preview: []},
  {id: 'test_scene_b', name: 'Testszene B', area_id: 'test_room_b', kind: 'snapshot', favorite: false, order: 0, preview: []},
];
const buttons: ButtonEntity[] = [
  {entity_id: 'event.test_button_one', name: 'Testtaste eins', device_id: 'test_device', device_name: 'Testgerät', area_id: 'test_room_a', event_types: ['short_release', 'double_short_release', 'repeat'], available: true},
  {entity_id: 'event.test_button_two', name: 'Testdrehrad', device_id: 'test_device', device_name: 'Testgerät', area_id: 'test_room_a', event_types: ['clock_wise', 'counter_clock_wise'], available: true},
  {entity_id: 'event.test_native', name: 'Testtaste nativ', device_id: null, device_name: '', area_id: null, event_types: ['single_push', 'double_push', 'custom_event'], available: false},
];
const binding: Binding = {id: 'test_binding', event_entity: buttons[0].entity_id, event_type: 'short_release', action: 'toggle_room', area_id: rooms[0].area_id, params: {}};
const unavailable: AdaptiveStatus = {available: false, rooms: [], switches: []};
const adaptive: AdaptiveStatus = {available: true, rooms: [{area_id: rooms[0].area_id, switch_entity_id: 'switch.test_adaptive', enabled: true, available: true, default_on: 'last'}], switches: []};
type Request = {type: string; [key: string]: unknown};
type Options = {scenes?: Scene[]; lights?: Light[]; bindings?: Binding[]; buttons?: ButtonEntity[]; rooms?: Room[]; adaptive?: AdaptiveStatus};
function makeApi(options: Options = {}) {
  let savedBindings = options.bindings || [], savedRooms = options.rooms || rooms, double_click_ms = 500;
  const callWS = vi.fn(async (request: Request): Promise<unknown> => {
    switch (request.type) {
      case 'lichtzentrale/lights/list': return options.lights || [];
      case 'lichtzentrale/schedules/list': return {time_zone: 'Europe/Berlin', schedules: [], lux_sensors: [], persons: []};
      case 'lichtzentrale/buttons/list': return options.buttons || buttons;
      case 'lichtzentrale/bindings/list': return {bindings: savedBindings, double_click_ms};
      case 'lichtzentrale/rooms/list': return savedRooms;
      case 'lichtzentrale/scenes/list': return options.scenes || scenes;
      case 'lichtzentrale/adaptive/status': return options.adaptive || unavailable;
      case 'lichtzentrale/binding/save': {
        const saved = {...(request.binding as Binding), id: (request.binding as Binding).id || 'test_new_binding'};
        savedBindings = [...savedBindings.filter(item => item.id !== saved.id), saved]; return saved;
      }
      case 'lichtzentrale/binding/delete': savedBindings = savedBindings.filter(item => item.id !== request.binding_id); return {};
      case 'lichtzentrale/binding/settings': double_click_ms = request.double_click_ms as number; return {double_click_ms};
      case 'lichtzentrale/room/settings': {
        const result = {cycle: request.cycle as string[], default_on: request.default_on as string};
        savedRooms = savedRooms.map(room => room.area_id === request.area_id ? {...room, ...result} : room); return result;
      }
      default: return [];
    }
  });
  return callWS;
}
async function setup(options: Options = {}) {
  const callWS = makeApi(options), view = render(<Buttons hass={{callWS} as Hass}/>);
  await screen.findByRole('region', {name: 'Szenenzyklus und Einschalten'});
  for (const summary of screen.queryAllByText('Alle Ereignisse und gespeicherte Belegungen')) fireEvent.click(summary);
  return {callWS, ...view};
}
const writes = (callWS: ReturnType<typeof makeApi>) => callWS.mock.calls.filter(([request]) => !request.type.endsWith('/list') && !request.type.endsWith('/status'));
function eventGroup(type = 'Kurz drücken', button = 'Testtaste eins') {return within(within(screen.getByRole('region', {name: button})).getByRole('group', {name: type}));}
function editEvent(type = 'Kurz drücken', button = 'Testtaste eins') {fireEvent.click(eventGroup(type, button).getByRole('button', {name: 'Belegen'}));}
function chooseRoom(area = rooms[0].area_id) {fireEvent.change(screen.getByLabelText('Raum oder Zone'), {target: {value: area}});}
function chooseAction(action: string) {fireEvent.change(screen.getByLabelText('Aktion'), {target: {value: action}});}
function openSettings(area = rooms[0].area_id) {fireEvent.change(screen.getByLabelText('Raum für Einstellungen'), {target: {value: area}});}
afterEach(cleanup);

describe('Tasterbelegungen', () => {
  it('groups device buttons and explains native/raw, offline and synthetic events', async () => {
    await setup();
    const group = within(screen.getByRole('region', {name: 'Testgerät'}));
    expect(group.getByRole('region', {name: 'Testtaste eins'})).toBeVisible();
    expect(group.getByRole('region', {name: 'Testdrehrad'})).toBeVisible();
    expect(eventGroup('Doppelklick (erkannt)').getByText('double_short_release')).toBeVisible();
    const native = within(screen.getByRole('region', {name: 'Testtaste nativ'}));
    expect(native.getByText(/Taster nicht verfügbar/)).toBeVisible();
    expect(native.queryByText('double_short_release')).not.toBeInTheDocument();
    expect(native.getByText('double_push')).toBeVisible();
    expect(native.getByText('custom_event')).toBeVisible();
    expect(eventGroup('Einmal drücken', 'Testtaste nativ').getByRole('button', {name: 'Belegen'})).toBeEnabled();
  });
  it('creates a binding only after explicit save and preserves it across remount from the server', async () => {
    const {callWS, unmount} = await setup(); editEvent(); chooseRoom(); chooseAction('next_scene');
    expect(writes(callWS)).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith({type: 'lichtzentrale/binding/save', binding: {event_entity: buttons[0].entity_id, event_type: 'short_release', action: 'next_scene', area_id: rooms[0].area_id, params: {}}});
    expect(eventGroup().getByText(/Nächste Szene im Zyklus · Testraum A/)).toBeVisible();
    expect(screen.queryByLabelText('Raum oder Zone')).not.toBeInTheDocument();
    unmount(); render(<Buttons hass={{callWS} as Hass}/>);
    await screen.findAllByText(/Nächste Szene im Zyklus · Testraum A/);
  });
  it('requires a room and a matching scene, resetting scene selection on a room change', async () => {
    const {callWS} = await setup(); editEvent();
    expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeDisabled();
    chooseRoom(); chooseAction('scene');
    expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeDisabled();
    expect(within(screen.getByLabelText('Szene')).queryByRole('option', {name: 'Testszene B'})).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Szene'), {target: {value: scenes[0].id}});
    chooseRoom(rooms[1].area_id);
    expect(screen.getByLabelText('Szene')).toHaveValue('');
    expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Szene'), {target: {value: scenes[2].id}});
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith(expect.objectContaining({binding: expect.objectContaining({area_id: rooms[1].area_id, params: {scene_id: scenes[2].id}})}));
  });
  it('updates existing bindings by id and clears scene params when changing to another action', async () => {
    const {callWS} = await setup({bindings: [{...binding, action: 'scene', params: {scene_id: scenes[0].id}}]});
    fireEvent.click(eventGroup().getByRole('button', {name: 'Belegung bearbeiten'}));
    expect(screen.getByLabelText('Szene')).toHaveValue(scenes[0].id);
    chooseAction('dim_down'); fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith({type: 'lichtzentrale/binding/save', binding: {...binding, action: 'dim_down'}});
    expect(eventGroup().getByText(/Dunkler \(10 %\) · Testraum A/)).toBeVisible();
  });
  it('does not persist canceled edits or reuse another event draft', async () => {
    const {callWS} = await setup(); editEvent(); chooseRoom(); chooseAction('scene');
    fireEvent.change(screen.getByLabelText('Szene'), {target: {value: scenes[0].id}});
    fireEvent.click(screen.getByRole('button', {name: 'Abbrechen'}));
    expect(writes(callWS)).toHaveLength(0);
    editEvent(); expect(screen.getByLabelText('Raum oder Zone')).toHaveValue('');
    chooseRoom(); chooseAction('dim_up');
    editEvent('Im Uhrzeigersinn drehen', 'Testdrehrad');
    expect(screen.getByLabelText('Raum oder Zone')).toHaveValue('');
    expect(screen.getByLabelText('Aktion')).toHaveValue('toggle_room');
  });
  it('keeps a failed write unsaved and the draft available for an explicit retry', async () => {
    const {callWS} = await setup(); editEvent(); chooseRoom(); chooseAction('turn_off_room');
    callWS.mockRejectedValueOnce({message: 'Test-Speicher nicht erreichbar'});
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Test-Speicher nicht erreichbar');
    expect(eventGroup().getByText('Noch nicht belegt')).toBeVisible();
    expect(screen.getByLabelText('Aktion')).toHaveValue('turn_off_room');
    expect(screen.queryByText('Belegung in Home Assistant gespeichert.')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(writes(callWS)).toHaveLength(2);
  });
  it('locks repeated saves and all competing edits, then trusts the normalized server response', async () => {
    const {callWS} = await setup(); editEvent(); chooseRoom(); chooseAction('dim_up');
    let finish: (value: Binding) => void = () => {};
    callWS.mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
    const save = screen.getByRole('button', {name: 'Belegung speichern'});
    fireEvent.click(save); fireEvent.click(save);
    expect(writes(callWS)).toHaveLength(1);
    expect(screen.getByLabelText('Raum oder Zone')).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Abbrechen'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Taster neu laden'})).toBeDisabled();
    expect(eventGroup('Gedrückt halten (Wiederholung)').getByRole('button', {name: 'Belegen'})).toBeDisabled();
    expect(eventGroup().getByText('Noch nicht belegt')).toBeVisible();
    await act(async () => finish({...binding, action: 'dim_down'}));
    expect(eventGroup().getByText(/Dunkler \(10 %\) · Testraum A/)).toBeVisible();
  });
  it('deletes vanished and obsolete bindings with cancel, failure and repeated-click protection', async () => {
    const vanished = {...binding, id: 'test_vanished_binding', event_entity: 'event.test_vanished', event_type: 'old_event'};
    const {callWS} = await setup({bindings: [vanished]});
    const group = within(screen.getByRole('region', {name: 'Nicht mehr gefundene Taster'}));
    expect(group.getByText(/Dieser Taster wurde nicht mehr gefunden/)).toBeVisible();
    expect(group.getByRole('button', {name: 'Belegung bearbeiten'})).toBeDisabled();
    fireEvent.click(group.getByRole('button', {name: 'Belegung löschen'}));
    fireEvent.click(screen.getByRole('button', {name: 'Abbrechen'})); expect(writes(callWS)).toHaveLength(0);
    fireEvent.click(group.getByRole('button', {name: 'Belegung löschen'}));
    callWS.mockRejectedValueOnce(new Error('Testfehler beim Löschen'));
    fireEvent.click(screen.getByRole('button', {name: 'Endgültig löschen'}));
    await screen.findByRole('alert'); expect(group.getByRole('button', {name: 'Belegung löschen'})).toBeInTheDocument();
    let finish: (value: object) => void = () => {};
    callWS.mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
    const remove = screen.getByRole('button', {name: 'Endgültig löschen'}); fireEvent.click(remove); fireEvent.click(remove);
    expect(writes(callWS)).toHaveLength(2);
    expect(callWS).toHaveBeenLastCalledWith({type: 'lichtzentrale/binding/delete', binding_id: vanished.id});
    await act(async () => finish({}));
    expect(screen.queryByRole('region', {name: 'Nicht mehr gefundene Taster'})).not.toBeInTheDocument();
    expect(screen.getByText('Belegung gelöscht.')).toBeVisible();
  });
  it('retains obsolete event assignments on present buttons so they can be deleted', async () => {
    await setup({bindings: [{...binding, event_type: 'obsolete_test_event'}]});
    const old = eventGroup('obsolete_test_event');
    expect(old.getByText('obsolete_test_event')).toBeVisible();
    expect(old.getByRole('button', {name: 'Belegung löschen'})).toBeEnabled();
    expect(old.getByRole('button', {name: 'Belegung bearbeiten'})).toBeDisabled();
  });
  it('hides adaptive actions when unavailable and only offers them for configured available rooms', async () => {
    const {unmount} = await setup(); editEvent(); chooseRoom();
    expect(screen.queryByRole('option', {name: 'Natürliches Licht einschalten'})).not.toBeInTheDocument();
    unmount(); await setup({adaptive}); editEvent(); chooseRoom();
    const actions = within(screen.getByLabelText('Aktion'));
    expect(actions.getAllByRole('option')).toHaveLength(18); // placeholder + 13 actions
    chooseAction('adaptive_on'); chooseRoom(rooms[1].area_id);
    expect(screen.getByLabelText('Aktion')).toHaveValue('toggle_room');
    expect(screen.queryByRole('option', {name: 'Natürliches Licht einschalten'})).not.toBeInTheDocument();
  });
  it('handles bindings whose room or adaptive configuration disappeared without silent overwrites', async () => {
    await setup({bindings: [{...binding, area_id: 'test_missing_room', action: 'adaptive_on'}]});
    expect(eventGroup().getByText(/Raum nicht mehr vorhanden/)).toBeVisible();
    fireEvent.click(eventGroup().getByRole('button', {name: 'Belegung bearbeiten'}));
    expect(screen.getByLabelText('Raum oder Zone')).toHaveValue('');
    expect(screen.getByLabelText('Aktion')).toHaveValue('');
    expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeDisabled();
  });
  it('loads a successful empty state and disables new bindings without controllable rooms', async () => {
    const {unmount} = await setup({buttons: [], rooms: []});
    expect(screen.getByText(/Keine Taster mit Event-Entities gefunden/)).toBeVisible();
    expect(screen.getByText('Keine Räume mit freigegebenen Lampen vorhanden.')).toBeVisible();
    unmount(); await setup({rooms: []});
    expect(eventGroup().getByRole('button', {name: 'Belegen'})).toBeDisabled();
  });
  it('retries failed initial loads without falsely displaying an empty success state', async () => {
    const callWS = makeApi(); callWS.mockRejectedValueOnce(new Error('Test-Verbindung getrennt'));
    render(<Buttons hass={{callWS} as Hass}/>);
    expect(await screen.findByRole('alert')).toHaveTextContent('Test-Verbindung getrennt');
    expect(screen.queryByText(/Keine Taster mit Event-Entities gefunden/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Taster neu laden'}));
    await screen.findByRole('region', {name: 'Testgerät'});
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
  it('does not surface late responses after leaving the Taster page and reloads on returning', async () => {
    const callWS = makeApi();
    render(<App hass={{callWS} as Hass}/>);
    fireEvent.click(screen.getByRole('button', {name: 'Taster'}));
    await screen.findByRole('region', {name: 'Testgerät'}); editEvent(); chooseRoom();
    let finish: (value: Binding) => void = () => {};
    callWS.mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    fireEvent.click(screen.getByRole('button', {name: 'Automationen'}));
    await act(async () => finish(binding));
    expect(await screen.findByText(/Noch keine (Zeitpläne|Automationen)/)).toBeVisible();
    expect(screen.queryByText('Belegung in Home Assistant gespeichert.')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Taster'}));
    await screen.findByRole('region', {name: 'Testgerät'});
    expect(callWS.mock.calls.filter(([request]) => request.type === 'lichtzentrale/bindings/list')).toHaveLength(2);
    expect(screen.queryByLabelText('Raum oder Zone')).not.toBeInTheDocument();
  });
});

describe('Szenenzyklus und Einschalten', () => {
  it('edits inclusion and order as a draft, saves both settings and reloads confirmed values', async () => {
    const {callWS} = await setup(); openSettings();
    fireEvent.click(screen.getByRole('checkbox', {name: 'Testszene A2'}));
    fireEvent.click(screen.getByRole('button', {name: 'Testszene A2 im Zyklus nach oben'}));
    fireEvent.change(screen.getByLabelText('Beim Einschalten'), {target: {value: scenes[1].id}});
    expect(writes(callWS)).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', {name: 'Raumeinstellungen speichern'}));
    await screen.findByText('Raumeinstellungen in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith({type: 'lichtzentrale/room/settings', area_id: rooms[0].area_id, cycle: [scenes[1].id, scenes[0].id], default_on: scenes[1].id});
    openSettings(); expect(screen.getByLabelText('Beim Einschalten')).toHaveValue(scenes[1].id);
    const items = screen.getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('Testszene A2'); expect(items[1]).toHaveTextContent('Testszene A');
    expect(screen.getByRole('button', {name: 'Testszene A2 im Zyklus nach oben'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Testszene A im Zyklus nach unten'})).toBeDisabled();
  });
  it('cancels edits and resets room-local drafts after changing rooms', async () => {
    const {callWS} = await setup(); openSettings();
    fireEvent.click(screen.getByRole('checkbox', {name: 'Testszene A'}));
    fireEvent.change(screen.getByLabelText('Beim Einschalten'), {target: {value: scenes[1].id}});
    fireEvent.click(screen.getByRole('button', {name: 'Abbrechen'})); openSettings();
    expect(screen.getByRole('checkbox', {name: 'Testszene A'})).toBeChecked();
    expect(screen.getByLabelText('Beim Einschalten')).toHaveValue('last');
    fireEvent.click(screen.getByRole('checkbox', {name: 'Testszene A2'}));
    openSettings(rooms[1].area_id);
    expect(screen.queryByRole('checkbox', {name: 'Testszene A2'})).not.toBeInTheDocument();
    expect(screen.getByRole('checkbox', {name: 'Testszene B'})).not.toBeChecked();
    openSettings(); expect(screen.getByRole('checkbox', {name: 'Testszene A2'})).not.toBeChecked();
    expect(writes(callWS)).toHaveLength(0);
  });
  it('keeps failed cycle writes as drafts and accepts only the server settings on success', async () => {
    const {callWS} = await setup(); openSettings();
    fireEvent.click(screen.getByRole('checkbox', {name: 'Testszene A2'}));
    callWS.mockRejectedValueOnce({message: 'Testzyklus nicht gespeichert'});
    fireEvent.click(screen.getByRole('button', {name: 'Raumeinstellungen speichern'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Testzyklus nicht gespeichert');
    expect(screen.getByRole('checkbox', {name: 'Testszene A2'})).toBeChecked();
    let finish: (value: unknown) => void = () => {};
    callWS.mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
    const save = screen.getByRole('button', {name: 'Raumeinstellungen speichern'}); fireEvent.click(save); fireEvent.click(save);
    expect(writes(callWS)).toHaveLength(2);
    expect(screen.getByLabelText('Raum für Einstellungen')).toBeDisabled();
    await act(async () => finish({cycle: [scenes[1].id], default_on: scenes[1].id}));
    openSettings(); expect(screen.getByRole('checkbox', {name: 'Testszene A'})).not.toBeChecked();
    expect(screen.getByLabelText('Beim Einschalten')).toHaveValue(scenes[1].id);
  });
  it('supports an empty cycle and removal, with unavailable default and missing scenes repaired explicitly', async () => {
    const {callWS} = await setup({rooms: [{...rooms[0], cycle: ['test_deleted_scene'], default_on: 'adaptive'}, rooms[1]]});
    openSettings();
    expect(screen.queryByRole('option', {name: 'Natürliches Licht starten'})).not.toBeInTheDocument();
    expect(screen.getByLabelText('Beim Einschalten')).toHaveValue('');
    expect(screen.getByRole('button', {name: 'Raumeinstellungen speichern'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Szene nicht mehr vorhanden aus Zyklus entfernen'}));
    fireEvent.change(screen.getByLabelText('Beim Einschalten'), {target: {value: 'last'}});
    fireEvent.click(screen.getByRole('button', {name: 'Raumeinstellungen speichern'}));
    await screen.findByText('Raumeinstellungen in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith({type: 'lichtzentrale/room/settings', area_id: rooms[0].area_id, cycle: [], default_on: 'last'});
  });
  it('offers natural light only for an available adaptive room and room-local scene defaults', async () => {
    await setup({adaptive}); openSettings();
    expect(screen.getByRole('option', {name: 'Natürliches Licht starten'})).toBeInTheDocument();
    expect(screen.queryByRole('option', {name: 'Szene: Testszene B'})).not.toBeInTheDocument();
    openSettings(rooms[1].area_id);
    expect(screen.queryByRole('option', {name: 'Natürliches Licht starten'})).not.toBeInTheDocument();
    expect(screen.queryByRole('option', {name: 'Szene: Testszene A'})).not.toBeInTheDocument();
  });
});

describe('Doppelklick-Zeit', () => {
  it('validates inclusive bounds, saves explicitly and discards unsaved edits', async () => {
    const {callWS} = await setup();
    const input = screen.getByLabelText('Doppelklick-Zeit in Millisekunden');
    const save = screen.getByRole('button', {name: 'Doppelklick-Zeit speichern'});
    for (const value of ['', '199', '1001', '500.5', '500']) {fireEvent.change(input, {target: {value}}); expect(save).toBeDisabled();}
    fireEvent.change(input, {target: {value: '200'}}); expect(save).toBeEnabled();
    fireEvent.click(save); await screen.findByText('Gespeichert: 200 ms');
    expect(callWS).toHaveBeenLastCalledWith({type: 'lichtzentrale/binding/settings', double_click_ms: 200});
    fireEvent.change(screen.getByLabelText('Doppelklick-Zeit in Millisekunden'), {target: {value: '1000'}});
    fireEvent.click(screen.getByRole('button', {name: 'Änderung verwerfen'}));
    expect(screen.getByLabelText('Doppelklick-Zeit in Millisekunden')).toHaveValue(200);
    expect(writes(callWS)).toHaveLength(1);
    fireEvent.change(screen.getByLabelText('Doppelklick-Zeit in Millisekunden'), {target: {value: '1000'}});
    fireEvent.click(screen.getByRole('button', {name: 'Doppelklick-Zeit speichern'}));
    await screen.findByText('Gespeichert: 1000 ms');
  });
  it('does not change the saved time on error and prevents duplicate pending saves', async () => {
    const {callWS} = await setup();
    fireEvent.change(screen.getByLabelText('Doppelklick-Zeit in Millisekunden'), {target: {value: '650'}});
    callWS.mockRejectedValueOnce(new Error('Testzeit nicht gespeichert'));
    fireEvent.click(screen.getByRole('button', {name: 'Doppelklick-Zeit speichern'}));
    await screen.findByRole('alert'); expect(screen.getByText('Gespeichert: 500 ms')).toBeVisible();
    expect(screen.getByLabelText('Doppelklick-Zeit in Millisekunden')).toHaveValue(650);
    let finish: (value: unknown) => void = () => {};
    callWS.mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
    const save = screen.getByRole('button', {name: 'Doppelklick-Zeit speichern'}); fireEvent.click(save); fireEvent.click(save);
    expect(writes(callWS)).toHaveLength(2);
    await act(async () => finish({double_click_ms: 600}));
    expect(screen.getByLabelText('Doppelklick-Zeit in Millisekunden')).toHaveValue(600);
    expect(screen.getByText('Gespeichert: 600 ms')).toBeVisible();
  });
});

const testLights: Light[] = [
  {entity_id: 'light.test_a', name: 'Testlicht A', area_id: rooms[0].area_id, area_name: rooms[0].name, available: true, allowed: true},
  {entity_id: 'switch.test_b', name: 'Testlicht B', area_id: rooms[1].area_id, area_name: rooms[1].name, available: true, allowed: true},
  {entity_id: 'light.test_unassigned', name: 'Testlicht ohne Raum', area_id: null, area_name: null, available: false, allowed: true},
  {entity_id: 'light.test_denied', name: 'Nicht freigegeben', area_id: null, area_name: null, available: true, allowed: false},
  {entity_id: 'lock.test_invalid', name: 'Falsche Domain', area_id: null, area_name: null, available: true, allowed: true},
];
const selectLight = (name: string) => fireEvent.click(screen.getByRole('checkbox', {name: new RegExp(name)}));
describe('Einzellampen für Taster', () => {
  it.each(['toggle_lights', 'turn_on_lights', 'turn_off_lights'])('saves %s across rooms without an area, with approved targets only', async action => {
    const {callWS, unmount} = await setup({lights: testLights}); editEvent(); chooseAction(action);
    expect(screen.queryByLabelText('Raum oder Zone')).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeDisabled();
    expect(screen.queryByRole('checkbox', {name: /Nicht freigegeben|Falsche Domain/})).not.toBeInTheDocument();
    expect(screen.getByRole('group', {name: 'Testraum A'})).toBeVisible();
    expect(screen.getByRole('group', {name: 'Testraum B'})).toBeVisible();
    expect(screen.getByRole('group', {name: 'Ohne Raum'})).toBeVisible();
    selectLight('Testlicht A'); selectLight('Testlicht B');
    expect(writes(callWS)).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith({type: 'lichtzentrale/binding/save', binding: {event_entity: buttons[0].entity_id, event_type: 'short_release', action, area_id: null, params: {entity_ids: ['light.test_a', 'switch.test_b']}}});
    unmount(); render(<Buttons hass={{callWS} as Hass}/>);
    await screen.findByRole('region', {name: 'Testgerät'});
    fireEvent.click(eventGroup().getByRole('button', {name: 'Belegung bearbeiten'}));
    expect(screen.getByRole('checkbox', {name: /Testlicht A/})).toBeChecked();
    expect(screen.getByRole('checkbox', {name: /Testlicht B/})).toBeChecked();
  });
  it('allows no-room approved lights even when no controllable room exists', async () => {
    const {callWS} = await setup({rooms: [], lights: [testLights[2]]}); editEvent(); chooseAction('turn_on_lights');
    selectLight('Testlicht ohne Raum');
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith(expect.objectContaining({binding: expect.objectContaining({area_id: null, params: {entity_ids: ['light.test_unassigned']}})}));
  });
  it.each(['dim_up', 'dim_down'])('retains room-wide %s and omits entity_ids until individual targets are requested', async action => {
    const {callWS} = await setup({lights: testLights}); editEvent(); chooseRoom(); chooseAction(action);
    expect(screen.getByLabelText('Ziel')).toHaveValue('room');
    fireEvent.change(screen.getByLabelText('Ziel'), {target: {value: 'lights'}});
    expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeDisabled();
    selectLight('Testlicht B');
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith(expect.objectContaining({binding: expect.objectContaining({action, area_id: null, params: {entity_ids: ['switch.test_b']}})}));
    fireEvent.click(eventGroup().getByRole('button', {name: 'Belegung bearbeiten'}));
    expect(screen.getByLabelText('Ziel')).toHaveValue('lights');
    fireEvent.change(screen.getByLabelText('Ziel'), {target: {value: 'room'}}); chooseRoom();
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith(expect.objectContaining({binding: expect.objectContaining({action, area_id: rooms[0].area_id, params: {}})}));
  });
  it('shows and requires explicit removal of stale targets, including revoked approvals', async () => {
    const {callWS} = await setup({lights: testLights, bindings: [{...binding, action: 'toggle_lights', params: {entity_ids: ['light.test_a', 'light.test_missing', 'light.test_denied']}}]});
    fireEvent.click(eventGroup().getByRole('button', {name: 'Belegung bearbeiten'}));
    expect(screen.getByRole('alert')).toHaveTextContent('nicht mehr freigegeben oder vorhanden');
    expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeDisabled();
    fireEvent.click(screen.getAllByRole('button', {name: 'Fehlendes Licht aus Auswahl entfernen'})[0]);
    expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Fehlendes Licht aus Auswahl entfernen'}));
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith(expect.objectContaining({binding: expect.objectContaining({params: {entity_ids: ['light.test_a']}})}));
  });
  it('drops irrelevant targets and scene parameters when changing action families', async () => {
    const {callWS} = await setup({lights: testLights}); editEvent(); chooseRoom(); chooseAction('scene');
    fireEvent.change(screen.getByLabelText('Szene'), {target: {value: scenes[0].id}});
    chooseAction('toggle_lights'); selectLight('Testlicht A'); chooseAction('turn_on_room');
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith(expect.objectContaining({binding: expect.objectContaining({action: 'turn_on_room', params: {}})}));
    fireEvent.click(eventGroup().getByRole('button', {name: 'Belegung bearbeiten'})); chooseAction('toggle_lights');
    expect(screen.getByRole('checkbox', {name: /Testlicht A/})).not.toBeChecked();
    expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeDisabled();
  });
  it('keeps failed selected-light drafts and locks checkboxes during pending saves', async () => {
    const {callWS} = await setup({lights: testLights}); editEvent(); chooseAction('toggle_lights'); selectLight('Testlicht A');
    callWS.mockRejectedValueOnce(new Error('Testfehler'));
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'})); await screen.findByRole('alert');
    expect(screen.getByRole('checkbox', {name: /Testlicht A/})).toBeChecked();
    expect(eventGroup().getByText('Noch nicht belegt')).toBeVisible();
    let finish: (value: Binding) => void = () => {};
    callWS.mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
    const save = screen.getByRole('button', {name: 'Belegung speichern'}); fireEvent.click(save); fireEvent.click(save);
    expect(writes(callWS)).toHaveLength(2);
    expect(screen.getByRole('checkbox', {name: /Testlicht A/})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Abbrechen'})).toBeDisabled();
    await act(async () => finish({...binding, action: 'toggle_lights', area_id: null, params: {entity_ids: ['switch.test_b']}}));
    expect(eventGroup().getByText(/Ausgewählte Lichter ein \/ aus · Testlicht B/)).toBeVisible();
  });
});

describe('Gerätezeichnung und Anlernen', () => {
  it('learns runtime attributes, uses template defaults and saves no irrelevant scene parameter', async () => {
    const {callWS} = await setup({lights: testLights});
    const group = within(screen.getByRole('region', {name: 'Testgerät'}));
    fireEvent.click(group.getByText('Dimmer-Vorlage'));
    fireEvent.change(group.getByLabelText('Ziel für die Vorlage'), {target: {value: rooms[0].area_id}});
    fireEvent.click(group.getByRole('button', {name: 'Vorlage verwenden'}));
    const original = callWS.getMockImplementation()!;
    callWS.mockImplementation(async request => {
      if (request.type === 'lichtzentrale/buttons/learn/start') return {token: 'synthetic-token'};
      if (request.type === 'lichtzentrale/buttons/learn/status') return {status: 'captured', observation: {event_entity: buttons[0].entity_id, event_type: 'short_release', event_attributes: {arbitrary_runtime_key: 'first', arbitrary_direction: 1}}};
      if (request.type === 'lichtzentrale/buttons/learn/cancel') return {cancelled: true};
      return original(request);
    });
    fireEvent.click(group.getByRole('button', {name: 'Taste anlernen'}));
    await group.findByText('Erkannt: Kurz drücken');
    fireEvent.click(group.getAllByRole('button', {name: 'Aktion und Ziel auswählen'})[0]);
    expect(screen.getByLabelText('Aktion')).toHaveValue('full_brightness');
    expect(screen.getByLabelText('Raum oder Zone')).toHaveValue(rooms[0].area_id);
    expect(screen.queryByLabelText('Szene')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    const save = callWS.mock.calls.find(([request]) => request.type === 'lichtzentrale/binding/save')![0];
    expect(save.binding).toEqual({event_entity: buttons[0].entity_id, event_type: 'short_release', event_attributes: {arbitrary_runtime_key: 'first', arbitrary_direction: 1}, control_label: 'An · Kurz drücken', action: 'full_brightness', area_id: rooms[0].area_id, params: {}});
    expect(document.body.textContent).not.toContain(buttons[0].entity_id);
    expect(document.body.textContent).not.toContain(testLights[0].entity_id);
  });

  it('cancels a late learning start without opening or saving a stale draft', async () => {
    const {callWS} = await setup();
    const group = within(screen.getByRole('region', {name: 'Testgerät'}));
    fireEvent.click(group.getByRole('button', {name: 'Hue Dimmer An'}));
    let finish: (value: unknown) => void = () => {};
    callWS.mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
    fireEvent.click(group.getByRole('button', {name: 'Taste anlernen'}));
    fireEvent.click(group.getByRole('button', {name: 'Anlernen abbrechen'}));
    await act(async () => finish({token: 'late-synthetic-token'}));
    expect(callWS).toHaveBeenLastCalledWith({type: 'lichtzentrale/buttons/learn/cancel', token: 'late-synthetic-token'});
    expect(group.queryByText(/Erkannt:/)).not.toBeInTheDocument();
    expect(callWS.mock.calls.some(([request]) => request.type === 'lichtzentrale/binding/save')).toBe(false);
  });

  it('offers each drawing, preserves unknown event names and displays learning failures', async () => {
    const {callWS} = await setup();
    const group = within(screen.getByRole('region', {name: 'Testgerät'}));
    for (const shape of ['Tap Dial', 'Wandschalter-Modul', 'Shelly']) {
      fireEvent.change(group.getByLabelText('Gerätezeichnung'), {target: {value: shape}});
      expect(group.getByRole('group', {name: `Zeichnung ${shape}`})).toBeInTheDocument();
    }
    fireEvent.click(group.getByRole('button', {name: 'Shelly Taste'}));
    callWS.mockRejectedValueOnce(new Error('Taster nicht erreichbar'));
    fireEvent.click(group.getByRole('button', {name: 'Taste anlernen'}));
    expect(await group.findByRole('alert')).toHaveTextContent('Taster nicht erreichbar');
    expect(screen.getByRole('group', {name: 'custom_event'})).toBeInTheDocument();
  });
});

async function captureLearnedEvent(eventType: string, attributes: Record<string, unknown>) {
  const source = {...buttons[0], event_types: [eventType], model: 'Tap Dial'};
  const result = await setup({buttons: [source]});
  const group = within(screen.getByRole('region', {name: 'Testgerät'}));
  fireEvent.click(group.getByRole('button', {name: 'Tap Dial Drehrad'}));
  fireEvent.click(group.getByRole('button', {name: 'Drehen nach rechts'}));
  const original = result.callWS.getMockImplementation()!;
  result.callWS.mockImplementation(async request => {
    if (request.type === 'lichtzentrale/buttons/learn/start') return {token: 'synthetic-wildcard-token'};
    if (request.type === 'lichtzentrale/buttons/learn/status') return {status: 'captured', observation: {event_entity: source.entity_id, event_type: eventType, event_attributes: attributes}};
    if (request.type === 'lichtzentrale/buttons/learn/cancel') return {cancelled: true};
    return original(request);
  });
  fireEvent.click(group.getByRole('button', {name: 'Taste anlernen'}));
  await group.findByText(/^Erkannt:/);
  return {...result, group};
}

describe('Gelernte Merkmale und Egal-Auswahl', () => {
  it('defaults only observed dial speed to egal and retains it through save, reload and edit', async () => {
    const {callWS, group, unmount} = await captureLearnedEvent('dial_rotate', {direction: 'right', speed: 2, runtime_marker: 'synthetic'});
    expect(group.getByLabelText('Geschwindigkeit beachten')).toHaveValue('ignore');
    expect(group.getByLabelText('Richtung beachten')).toHaveValue('match');
    expect(group.getByLabelText('runtime_marker beachten')).toHaveValue('match');
    fireEvent.click(group.getAllByRole('button', {name: 'Aktion und Ziel auswählen'})[0]);
    expect(screen.getByLabelText('Geschwindigkeit beachten')).toHaveValue('ignore');
    chooseRoom(); chooseAction('dim_up');
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    const saved = callWS.mock.calls.find(([request]) => request.type === 'lichtzentrale/binding/save')![0].binding;
    expect(saved).toMatchObject({event_attributes: {direction: 'right', speed: 2, runtime_marker: 'synthetic'}, ignored_event_attributes: ['speed']});
    unmount(); render(<Buttons hass={{callWS} as Hass}/>);
    await screen.findByRole('region', {name: 'Testgerät'});
    fireEvent.click(screen.getByText('Alle Ereignisse und gespeicherte Belegungen'));
    fireEvent.click(eventGroup('Drehen').getByRole('button', {name: 'Belegung bearbeiten'}));
    expect(screen.getByLabelText('Geschwindigkeit beachten')).toHaveValue('ignore');
    expect(screen.getByLabelText('Richtung beachten')).toHaveValue('match');
    fireEvent.change(screen.getByLabelText('Geschwindigkeit beachten'), {target: {value: 'match'}});
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith(expect.objectContaining({type: 'lichtzentrale/binding/save', binding: expect.objectContaining({ignored_event_attributes: [], event_attributes: {direction: 'right', speed: 2, runtime_marker: 'synthetic'}})}));
    expect(document.body.textContent).not.toContain(buttons[0].entity_id);
  });

  it('can ignore unknown observed attributes while required fields remain exact', async () => {
    const {callWS, group} = await captureLearnedEvent('press_release', {button: 'button_1', unexpected_detail: {nested: 3}, speed: 5});
    expect(group.getByLabelText('Taste beachten')).toHaveValue('match');
    expect(group.getByLabelText('Geschwindigkeit beachten')).toHaveValue('match');
    fireEvent.change(group.getByLabelText('unexpected_detail beachten'), {target: {value: 'ignore'}});
    fireEvent.click(group.getAllByRole('button', {name: 'Aktion und Ziel auswählen'})[0]);
    expect(screen.getByLabelText('unexpected_detail beachten')).toHaveValue('ignore');
    chooseRoom();
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith(expect.objectContaining({type: 'lichtzentrale/binding/save', binding: expect.objectContaining({ignored_event_attributes: ['unexpected_detail'], event_attributes: {button: 'button_1', unexpected_detail: {nested: 3}, speed: 5}})}));
  });

  it('never adds an unobserved speed field or changes old exact dial bindings by default', async () => {
    const {group, unmount} = await captureLearnedEvent('dial_rotate', {direction: 'right'});
    expect(group.queryByLabelText('Geschwindigkeit beachten')).not.toBeInTheDocument();
    expect(group.getByLabelText('Richtung beachten')).toHaveValue('match');
    fireEvent.click(group.getByRole('button', {name: 'Anlernen abbrechen'}));
    expect(group.queryByText(/^Erkannt:/)).not.toBeInTheDocument();
    unmount();
    const exact = {...binding, event_type: 'dial_rotate', event_attributes: {direction: 'right', speed: 2}};
    const {callWS} = await setup({buttons: [{...buttons[0], event_types: ['dial_rotate']}], bindings: [exact]});
    fireEvent.click(eventGroup('Drehen').getByRole('button', {name: 'Belegung bearbeiten'}));
    expect(screen.getByLabelText('Geschwindigkeit beachten')).toHaveValue('match');
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith({type: 'lichtzentrale/binding/save', binding: exact});
  });

  it('keeps conflicting edits as an unsaved draft and cancellation restores saved matching', async () => {
    const existing = {...binding, event_attributes: {button: 'button_1', unknown_observed_key: 'synthetic'}};
    const {callWS} = await setup({bindings: [existing]});
    fireEvent.click(eventGroup().getByRole('button', {name: 'Belegung bearbeiten'}));
    fireEvent.change(screen.getByLabelText('unknown_observed_key beachten'), {target: {value: 'ignore'}});
    callWS.mockRejectedValueOnce(new Error('Für dieses Ereignis gibt es bereits eine gleich genaue Belegung.'));
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('gleich genaue Belegung');
    expect(screen.getByLabelText('unknown_observed_key beachten')).toHaveValue('ignore');
    expect(screen.queryByText('Belegung in Home Assistant gespeichert.')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Abbrechen'}));
    fireEvent.click(eventGroup().getByRole('button', {name: 'Belegung bearbeiten'}));
    expect(screen.getByLabelText('unknown_observed_key beachten')).toHaveValue('match');
  });
});

describe('Beim Einschalten', () => {
  it('keeps legacy bindings unchanged and saves fixed brightness only for on actions', async () => {
    const {callWS} = await setup({bindings: [binding]});
    fireEvent.click(eventGroup().getByRole('button', {name: 'Belegung bearbeiten'}));
    expect(screen.getByLabelText('Beim Einschalten')).toHaveValue('last');
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith({type: 'lichtzentrale/binding/save', binding});
    fireEvent.click(eventGroup().getByRole('button', {name: 'Belegung bearbeiten'}));
    fireEvent.change(screen.getByLabelText('Beim Einschalten'), {target: {value: 'brightness'}});
    expect(screen.getByLabelText('Helligkeit beim Einschalten')).toHaveValue('100');
    fireEvent.change(screen.getByLabelText('Helligkeit beim Einschalten'), {target: {value: '40'}});
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith({type: 'lichtzentrale/binding/save', binding: {...binding, params: {on_behavior: {mode: 'brightness', brightness: 102}}}});
    expect(eventGroup().getByText(/beim Einschalten 40 %/)).toBeVisible();
    fireEvent.click(eventGroup().getByRole('button', {name: 'Belegung bearbeiten'}));
    chooseAction('turn_off_room');
    expect(screen.queryByLabelText('Beim Einschalten')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith(expect.objectContaining({binding: expect.objectContaining({action: 'turn_off_room', params: {}})}));
  });
  it('requires a matching room scene and invalidates it when the room changes', async () => {
    const {callWS} = await setup(); editEvent(); chooseRoom();
    fireEvent.change(screen.getByLabelText('Beim Einschalten'), {target: {value: 'scene'}});
    expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeDisabled();
    const select = within(screen.getByLabelText('Szene beim Einschalten'));
    expect(select.getByRole('option', {name: 'Testszene A'})).toBeInTheDocument();
    expect(select.queryByRole('option', {name: 'Testszene B'})).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Szene beim Einschalten'), {target: {value: scenes[0].id}});
    chooseRoom(rooms[1].area_id);
    expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Szene beim Einschalten'), {target: {value: scenes[2].id}});
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith(expect.objectContaining({binding: expect.objectContaining({area_id: rooms[1].area_id, params: {on_behavior: {mode: 'scene', scene_id: scenes[2].id}}})}));
  });
  it('restricts selected-lamp scenes to eligible subsets and never widens the selection', async () => {
    const ownLights = testLights.slice(0, 2);
    const palette = {...scenes[0], id: 'test_palette', kind: 'palette' as const, name: 'Testpalette'};
    const snapshot = {...scenes[0], lights: {'light.test_a': {on: true}, 'switch.test_b': {on: true}}};
    const hue = {...scenes[0], id: 'test_hue', kind: 'hue' as const, name: 'Testbridge'};
    const mixedRoom = {...rooms[0], lights: ownLights};
    const {callWS} = await setup({lights: ownLights, rooms: [mixedRoom], scenes: [snapshot, palette, hue]});
    editEvent(); chooseAction('toggle_lights'); selectLight('Testlicht A');
    fireEvent.change(screen.getByLabelText('Beim Einschalten'), {target: {value: 'scene'}});
    expect(within(screen.getByLabelText('Szene beim Einschalten')).getByRole('option', {name: 'Testpalette'})).toBeInTheDocument();
    expect(within(screen.getByLabelText('Szene beim Einschalten')).queryByRole('option', {name: 'Testbridge'})).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Szene beim Einschalten'), {target: {value: snapshot.id}});
    selectLight('Testlicht B');
    expect(within(screen.getByLabelText('Szene beim Einschalten')).queryByRole('option', {name: 'Testpalette'})).not.toBeInTheDocument();
    expect(screen.getByText('Nur die ausgewählten Lampen übernehmen die Szene. Andere Lampen bleiben unverändert.')).toBeVisible();
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith(expect.objectContaining({binding: expect.objectContaining({area_id: null, params: {entity_ids: ['light.test_a', 'switch.test_b'], on_behavior: {mode: 'scene', scene_id: snapshot.id}}})}));
  });
  it('preserves failed brightness drafts and cancels without changing saved behavior', async () => {
    const existing = {...binding, params: {on_behavior: {mode: 'brightness' as const, brightness: 127}}};
    const {callWS} = await setup({bindings: [existing]});
    fireEvent.click(eventGroup().getByRole('button', {name: 'Belegung bearbeiten'}));
    expect(screen.getByLabelText('Helligkeit beim Einschalten')).toHaveValue('50');
    fireEvent.change(screen.getByLabelText('Helligkeit beim Einschalten'), {target: {value: '100'}});
    callWS.mockRejectedValueOnce(new Error('Synthetischer Speicherfehler'));
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByRole('alert');
    expect(screen.getByLabelText('Helligkeit beim Einschalten')).toHaveValue('100');
    fireEvent.click(screen.getByRole('button', {name: 'Abbrechen'}));
    fireEvent.click(eventGroup().getByRole('button', {name: 'Belegung bearbeiten'}));
    expect(screen.getByLabelText('Helligkeit beim Einschalten')).toHaveValue('50');
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith({type: 'lichtzentrale/binding/save', binding: existing});
  });
  it('retains stale scene behavior visibly until explicitly repaired', async () => {
    const existing = {...binding, params: {on_behavior: {mode: 'scene' as const, scene_id: 'test_missing_scene'}}};
    const {callWS} = await setup({bindings: [existing]});
    fireEvent.click(eventGroup().getByRole('button', {name: 'Belegung bearbeiten'}));
    expect(screen.getByRole('alert')).toHaveTextContent('passt nicht mehr');
    expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Beim Einschalten'), {target: {value: 'last'}});
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith({type: 'lichtzentrale/binding/save', binding: {...binding, params: {on_behavior: {mode: 'last'}}}});
  });
});

describe('Beim Einschalten nach Tageszeit', () => {
  it('saves ordered clock/solar windows with brightness, white temperature and scene', async () => {
    const {callWS, unmount} = await setup(); editEvent(); chooseRoom();
    fireEvent.change(screen.getByLabelText('Beim Einschalten'), {target: {value: 'time'}});
    fireEvent.change(screen.getByLabelText('Einschaltfenster 1 Beginn: Uhrzeit'), {target: {value: '08:00'}});
    fireEvent.change(screen.getByLabelText('Einschaltfenster 1 Ende: Bezug'), {target: {value: 'sunset'}});
    fireEvent.change(screen.getByLabelText('Einschaltfenster 1 Ende: Versatz in Minuten'), {target: {value: '-15'}});
    fireEvent.change(screen.getByLabelText('Einschaltfenster 1 Helligkeit'), {target: {value: '30'}});
    fireEvent.change(screen.getByLabelText('Einschaltfenster 1 Weißton in Kelvin'), {target: {value: '2700'}});
    fireEvent.click(screen.getByRole('button', {name: 'Einschaltfenster hinzufügen'}));
    fireEvent.change(screen.getByLabelText('Einschaltfenster 2 Aktion'), {target: {value: 'scene'}});
    fireEvent.change(screen.getByLabelText('Einschaltfenster 2 Szene'), {target: {value: scenes[0].id}});
    fireEvent.click(screen.getByRole('button', {name: 'Einschaltfenster 2 nach oben'}));
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    const saved = callWS.mock.calls.find(([request]) => request.type === 'lichtzentrale/binding/save')![0].binding as Binding;
    expect(saved.params.on_behavior).toEqual({mode: 'time', windows: [
      {window: {after: {type: 'time', value: '07:00'}, before: {type: 'time', value: '22:00'}}, mode: 'scene', scene_id: scenes[0].id},
      {window: {after: {type: 'time', value: '08:00'}, before: {type: 'sun', event: 'sunset', offset_min: -15}}, mode: 'brightness', brightness: 77, color_temp_kelvin: 2700},
    ]});
    expect(eventGroup().getByText(/nach Tageszeit \(2 Zeitfenster\)/)).toBeVisible();
    unmount(); render(<Buttons hass={{callWS} as Hass}/>);
    await screen.findByRole('region', {name: 'Testgerät'});
    fireEvent.click(screen.getAllByText('Alle Ereignisse und gespeicherte Belegungen')[0]);
    fireEvent.click(eventGroup().getByRole('button', {name: 'Belegung bearbeiten'}));
    expect(screen.getByLabelText('Beim Einschalten')).toHaveValue('time');
    expect(screen.getByLabelText('Einschaltfenster 1 Szene')).toHaveValue(scenes[0].id);
    expect(screen.getByLabelText('Einschaltfenster 2 Weißton in Kelvin')).toHaveValue(2700);
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect((callWS.mock.calls.at(-1)![0].binding as Binding).params).toEqual(saved.params);
  });
  it('blocks invalid ranges or stale scene targets and keeps failed edits until cancellation', async () => {
    const existing: Binding = {...binding, params: {on_behavior: {mode: 'time', windows: [
      {window: {after: null, before: null}, mode: 'brightness', brightness: 13, color_temp_kelvin: 2200},
    ]}}};
    const {callWS} = await setup({bindings: [existing]});
    fireEvent.click(eventGroup().getByRole('button', {name: 'Belegung bearbeiten'}));
    fireEvent.change(screen.getByLabelText('Einschaltfenster 1 Weißton in Kelvin'), {target: {value: '999'}});
    expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Einschaltfenster 1 Weißton in Kelvin'), {target: {value: '3000'}});
    callWS.mockRejectedValueOnce(new Error('Synthetischer Schreibfehler'));
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByRole('alert');
    expect(screen.getByLabelText('Einschaltfenster 1 Weißton in Kelvin')).toHaveValue(3000);
    fireEvent.click(screen.getByRole('button', {name: 'Abbrechen'}));
    fireEvent.click(eventGroup().getByRole('button', {name: 'Belegung bearbeiten'}));
    expect(screen.getByLabelText('Einschaltfenster 1 Weißton in Kelvin')).toHaveValue(2200);
    fireEvent.change(screen.getByLabelText('Einschaltfenster 1 Aktion'), {target: {value: 'scene'}});
    fireEvent.change(screen.getByLabelText('Einschaltfenster 1 Szene'), {target: {value: scenes[0].id}});
    chooseRoom(rooms[1].area_id);
    expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeDisabled();
    expect(screen.getByRole('option', {name: 'Szene nicht mehr passend oder vorhanden'})).toHaveProperty('selected', true);
  });
});

it('offers seasonal selected-lamp behavior only when every usable season child fits', async () => {
  const child = {...scenes[0], lights: {'light.test_a': {on: true}, 'switch.test_b': {on: true}}};
  const palette: Scene = {...scenes[0], id: 'test_season_palette', name: 'Testpalette', kind: 'palette'};
  const hue: Scene = {...scenes[0], id: 'test_season_hue', name: 'Testbridge', kind: 'hue'};
  const seasonal: Scene = {...scenes[0], id: 'test_seasonal_safe', name: 'Testjahreszeiten', kind: 'seasonal', seasonal: {
    scenes: {spring: child.id, summer: 'test_missing_season', autumn: null, winter: null},
    boundaries: {spring: '03-01', summer: '06-01', autumn: '09-01', winter: '12-01'},
    christmas: {enabled: false, scene_id: hue.id, start: '12-01', end: '12-26'},
  }};
  const withPalette: Scene = {...seasonal, id: 'test_seasonal_palette', name: 'Testjahreszeiten mit Palette', seasonal: {...seasonal.seasonal!, scenes: {...seasonal.seasonal!.scenes, winter: palette.id}}};
  const withHue: Scene = {...seasonal, id: 'test_seasonal_hue', name: 'Testjahreszeiten mit Bridge', seasonal: {...seasonal.seasonal!, christmas: {...seasonal.seasonal!.christmas, enabled: true}}};
  const stale: Scene = {...seasonal, id: 'test_seasonal_stale', name: 'Testjahreszeiten ohne Szene', seasonal: {...seasonal.seasonal!, scenes: {spring: 'test_missing_season', summer: null, autumn: null, winter: null}}};
  const mixedRoom = {...rooms[0], lights: testLights.slice(0, 2)};
  const {callWS} = await setup({lights: testLights.slice(0, 2), rooms: [mixedRoom], scenes: [child, palette, hue, seasonal, withPalette, withHue, stale]});
  editEvent(); chooseAction('toggle_lights'); selectLight('Testlicht A');
  fireEvent.change(screen.getByLabelText('Beim Einschalten'), {target: {value: 'scene'}});
  let choices = within(screen.getByLabelText('Szene beim Einschalten'));
  expect(choices.getByRole('option', {name: 'Testjahreszeiten'})).toBeInTheDocument();
  expect(choices.getByRole('option', {name: 'Testjahreszeiten mit Palette'})).toBeInTheDocument();
  expect(choices.queryByRole('option', {name: 'Testjahreszeiten mit Bridge'})).not.toBeInTheDocument();
  expect(choices.queryByRole('option', {name: 'Testjahreszeiten ohne Szene'})).not.toBeInTheDocument();
  selectLight('Testlicht B');
  choices = within(screen.getByLabelText('Szene beim Einschalten'));
  expect(choices.queryByRole('option', {name: 'Testjahreszeiten mit Palette'})).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Szene beim Einschalten'), {target: {value: seasonal.id}});
  fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
  await screen.findByText('Belegung in Home Assistant gespeichert.');
  expect(callWS).toHaveBeenLastCalledWith(expect.objectContaining({binding: expect.objectContaining({params: {entity_ids: ['light.test_a', 'switch.test_b'], on_behavior: {mode: 'scene', scene_id: seasonal.id}}})}));
});

describe('Stufe 5e Ambiente zuerst', () => {
  const light: Light = {entity_id: 'light.test_ambient', name: 'Testlicht Ambiente', area_id: rooms[0].area_id, area_name: rooms[0].name, allowed: true, available: true};
  const foreign: Light = {...light, entity_id: 'light.test_foreign', name: 'Testlicht anderer Raum', area_id: rooms[1].area_id};
  const targetRooms = [{...rooms[0], lights: [light]}, {...rooms[1], lights: [foreign]}];
  const ambient = {scene_id: scenes[0].id, window: {after: {type: 'sun' as const, event: 'sunset' as const, offset_min: -15}, before: {type: 'time' as const, value: '22:30'}}};
  it('requires explicit shared container for selected lights and saves scene plus sun window with normal behavior', async () => {
    const {callWS} = await setup({rooms: targetRooms, lights: [light, foreign]}); editEvent();
    fireEvent.change(screen.getByLabelText('Aktion'), {target: {value: 'toggle_lights'}});
    fireEvent.click(screen.getByLabelText(light.name)); fireEvent.click(screen.getByLabelText('Zur Ambiente-Zeit zuerst Szene'));
    expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Ambiente-Raum oder Zone'), {target: {value: rooms[0].area_id}});
    fireEvent.change(screen.getByLabelText('Ambiente-Szene'), {target: {value: scenes[0].id}});
    fireEvent.change(screen.getByLabelText('Beim Einschalten'), {target: {value: 'brightness'}});
    fireEvent.click(screen.getByLabelText(foreign.name)); expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeDisabled();
    fireEvent.click(screen.getByLabelText(foreign.name)); fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/binding/save', binding: expect.objectContaining({area_id: rooms[0].area_id, action: 'toggle_lights', params: {entity_ids: [light.entity_id], on_behavior: {mode: 'brightness', brightness: 255}, ambient_first: ambient}})});
  });
  it('explicit opt-out restores legacy null area and removes ambient data without losing on behavior', async () => {
    const {callWS} = await setup({rooms: targetRooms, lights: [light], bindings: [{...binding, action: 'toggle_lights', params: {entity_ids: [light.entity_id], ambient_first: ambient, on_behavior: {mode: 'brightness', brightness: 120}}}]});
    fireEvent.click(eventGroup().getByRole('button', {name: 'Belegung bearbeiten'}));
    expect(screen.getByLabelText('Zur Ambiente-Zeit zuerst Szene')).toBeChecked();
    fireEvent.click(screen.getByLabelText('Zur Ambiente-Zeit zuerst Szene')); fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/binding/save', binding: expect.objectContaining({area_id: null, params: {entity_ids: [light.entity_id], on_behavior: {mode: 'brightness', brightness: 120}}})});
  });
  it('shows stale scene and invalid window for repair; offers only toggle actions', async () => {
    await setup({rooms: targetRooms, lights: [light], bindings: [{...binding, params: {ambient_first: {...ambient, scene_id: 'test_deleted'}}}]});
    fireEvent.click(eventGroup().getByRole('button', {name: 'Belegung bearbeiten'}));
    expect(screen.getByLabelText('Ambiente-Szene')).toHaveValue('test_deleted'); expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Ambiente-Szene'), {target: {value: scenes[0].id}});
    fireEvent.change(screen.getByLabelText('Ambiente Beginn: Versatz in Minuten'), {target: {value: '1441'}});
    expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Ambiente Beginn: Bezug'), {target: {value: 'none'}});
    fireEvent.change(screen.getByLabelText('Ambiente Ende: Bezug'), {target: {value: 'none'}});
    expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Aktion'), {target: {value: 'turn_on_room'}});
    expect(screen.queryByLabelText('Zur Ambiente-Zeit zuerst Szene')).not.toBeInTheDocument();
  });
  it('keeps dialog pending and retains failed saves without claiming persistence', async () => {
    let rejectSave: (reason: Error) => void = () => {};
    const callWS = makeApi({rooms: targetRooms, lights: [light], bindings: [{...binding, params: {ambient_first: ambient}}]});
    const wrapped = vi.fn((request: Request) => request.type === 'lichtzentrale/binding/save' ? new Promise((_, reject) => {rejectSave = reject;}) : callWS(request));
    render(<Buttons hass={{callWS: wrapped} as Hass}/>);
    await screen.findByRole('region', {name: 'Szenenzyklus und Einschalten'});
    for (const summary of screen.queryAllByText('Alle Ereignisse und gespeicherte Belegungen')) fireEvent.click(summary);
    fireEvent.click(eventGroup().getByRole('button', {name: 'Belegung bearbeiten'}));
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeDisabled();
    expect(screen.queryByText('Belegung in Home Assistant gespeichert.')).not.toBeInTheDocument();
    await act(async () => rejectSave(new Error('Testfehler')));
    expect(screen.getByRole('alert')).toHaveTextContent('Testfehler'); expect(screen.getByLabelText('Ambiente-Szene')).toHaveValue(ambient.scene_id);
    expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeEnabled();
  });
});
