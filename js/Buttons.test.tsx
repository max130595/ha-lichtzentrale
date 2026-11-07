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
type Options = {lights?: Light[]; bindings?: Binding[]; buttons?: ButtonEntity[]; rooms?: Room[]; adaptive?: AdaptiveStatus};
function makeApi(options: Options = {}) {
  let savedBindings = options.bindings || [], savedRooms = options.rooms || rooms, double_click_ms = 500;
  const callWS = vi.fn(async (request: Request): Promise<unknown> => {
    switch (request.type) {
      case 'lichtzentrale/lights/list': return options.lights || [];
      case 'lichtzentrale/schedules/list': return {time_zone: 'Europe/Berlin', schedules: [], lux_sensors: [], persons: []};
      case 'lichtzentrale/buttons/list': return options.buttons || buttons;
      case 'lichtzentrale/bindings/list': return {bindings: savedBindings, double_click_ms};
      case 'lichtzentrale/rooms/list': return savedRooms;
      case 'lichtzentrale/scenes/list': return scenes;
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
  return {callWS, ...view};
}
const writes = (callWS: ReturnType<typeof makeApi>) => callWS.mock.calls.filter(([request]) => !request.type.endsWith('/list') && !request.type.endsWith('/status'));
function eventGroup(type = 'Kurz drücken', button = 'Testtaste eins') {return within(within(screen.getByRole('region', {name: button})).getByRole('group', {name: type}));}
function editEvent(type = 'Kurz drücken', button = 'Testtaste eins') {fireEvent.click(eventGroup(type, button).getByRole('button', {name: 'Belegen'}));}
function chooseRoom(area = rooms[0].area_id) {fireEvent.change(screen.getByLabelText('Zielraum'), {target: {value: area}});}
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
    expect(eventGroup().getByText('Nächste Szene im Zyklus · Testraum A')).toBeVisible();
    expect(screen.queryByLabelText('Zielraum')).not.toBeInTheDocument();
    unmount(); render(<Buttons hass={{callWS} as Hass}/>);
    await screen.findByText('Nächste Szene im Zyklus · Testraum A');
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
    expect(eventGroup().getByText('Dunkler (10 %) · Testraum A')).toBeVisible();
  });
  it('does not persist canceled edits or reuse another event draft', async () => {
    const {callWS} = await setup(); editEvent(); chooseRoom(); chooseAction('scene');
    fireEvent.change(screen.getByLabelText('Szene'), {target: {value: scenes[0].id}});
    fireEvent.click(screen.getByRole('button', {name: 'Abbrechen'}));
    expect(writes(callWS)).toHaveLength(0);
    editEvent(); expect(screen.getByLabelText('Zielraum')).toHaveValue('');
    chooseRoom(); chooseAction('dim_up');
    editEvent('Im Uhrzeigersinn drehen', 'Testdrehrad');
    expect(screen.getByLabelText('Zielraum')).toHaveValue('');
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
    expect(screen.getByLabelText('Zielraum')).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Abbrechen'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Taster neu laden'})).toBeDisabled();
    expect(eventGroup('Gedrückt halten (Wiederholung)').getByRole('button', {name: 'Belegen'})).toBeDisabled();
    expect(eventGroup().getByText('Noch nicht belegt')).toBeVisible();
    await act(async () => finish({...binding, action: 'dim_down'}));
    expect(eventGroup().getByText('Dunkler (10 %) · Testraum A')).toBeVisible();
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
    const old = eventGroup('Geräteereignis');
    expect(old.getByText('obsolete_test_event')).toBeVisible();
    expect(old.getByRole('button', {name: 'Belegung löschen'})).toBeEnabled();
    expect(old.getByRole('button', {name: 'Belegung bearbeiten'})).toBeDisabled();
  });
  it('hides adaptive actions when unavailable and only offers them for configured available rooms', async () => {
    const {unmount} = await setup(); editEvent(); chooseRoom();
    expect(screen.queryByRole('option', {name: 'Natürliches Licht einschalten'})).not.toBeInTheDocument();
    unmount(); await setup({adaptive}); editEvent(); chooseRoom();
    const actions = within(screen.getByLabelText('Aktion'));
    expect(actions.getAllByRole('option')).toHaveLength(14); // placeholder + 13 actions
    chooseAction('adaptive_on'); chooseRoom(rooms[1].area_id);
    expect(screen.getByLabelText('Aktion')).toHaveValue('toggle_room');
    expect(screen.queryByRole('option', {name: 'Natürliches Licht einschalten'})).not.toBeInTheDocument();
  });
  it('handles bindings whose room or adaptive configuration disappeared without silent overwrites', async () => {
    await setup({bindings: [{...binding, area_id: 'test_missing_room', action: 'adaptive_on'}]});
    expect(eventGroup().getByText(/Raum nicht mehr vorhanden/)).toBeVisible();
    fireEvent.click(eventGroup().getByRole('button', {name: 'Belegung bearbeiten'}));
    expect(screen.getByLabelText('Zielraum')).toHaveValue('');
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
    fireEvent.click(screen.getByRole('button', {name: 'Zeitpläne'}));
    await act(async () => finish(binding));
    expect(await screen.findByText('Noch keine Zeitpläne.')).toBeVisible();
    expect(screen.queryByText('Belegung in Home Assistant gespeichert.')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Taster'}));
    await screen.findByRole('region', {name: 'Testgerät'});
    expect(callWS.mock.calls.filter(([request]) => request.type === 'lichtzentrale/bindings/list')).toHaveLength(2);
    expect(screen.queryByLabelText('Zielraum')).not.toBeInTheDocument();
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
    expect(screen.queryByLabelText('Zielraum')).not.toBeInTheDocument();
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
    expect(screen.getByLabelText('Dimmziel')).toHaveValue('room');
    fireEvent.change(screen.getByLabelText('Dimmziel'), {target: {value: 'lights'}});
    expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeDisabled();
    selectLight('Testlicht B');
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith(expect.objectContaining({binding: expect.objectContaining({action, area_id: null, params: {entity_ids: ['switch.test_b']}})}));
    fireEvent.click(eventGroup().getByRole('button', {name: 'Belegung bearbeiten'}));
    expect(screen.getByLabelText('Dimmziel')).toHaveValue('lights');
    fireEvent.change(screen.getByLabelText('Dimmziel'), {target: {value: 'room'}}); chooseRoom();
    fireEvent.click(screen.getByRole('button', {name: 'Belegung speichern'}));
    await screen.findByText('Belegung in Home Assistant gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith(expect.objectContaining({binding: expect.objectContaining({action, area_id: rooms[0].area_id, params: {}})}));
  });
  it('shows and requires explicit removal of stale targets, including revoked approvals', async () => {
    const {callWS} = await setup({lights: testLights, bindings: [{...binding, action: 'toggle_lights', params: {entity_ids: ['light.test_a', 'light.test_missing', 'light.test_denied']}}]});
    fireEvent.click(eventGroup().getByRole('button', {name: 'Belegung bearbeiten'}));
    expect(screen.getByRole('alert')).toHaveTextContent('nicht mehr freigegeben oder vorhanden');
    expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'light.test_missing aus Auswahl entfernen'}));
    expect(screen.getByRole('button', {name: 'Belegung speichern'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'light.test_denied aus Auswahl entfernen'}));
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
    expect(eventGroup().getByText('Ausgewählte Lichter ein / aus · Testlicht B')).toBeVisible();
  });
});
