// Geändert für Lichtzentrale
// @vitest-environment jsdom
import {afterEach, describe, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {MotionControls} from './MotionControls';
import type {Hass, MotionConfig, MotionResponse} from './types';
afterEach(cleanup);
const config = (): MotionConfig => ({enabled: false, sensor_entity_ids: ['binary_sensor.test_motion'], timeout_seconds: 120, dim_before_off: false, lux_sensor_entity_id: null, lux_below: null, windows: [{start: {type: 'time', value: '00:00'}, end: {type: 'time', value: '00:00'}, action: {type: 'lights', entity_ids: null, brightness: 128}}]});
const response = (saved: MotionConfig | null = config()): MotionResponse => ({config: saved, status: {enabled: saved?.enabled || false, paused: false, active: false}, sensors: [{entity_id: 'binary_sensor.test_motion', name: 'Testbewegung', device_class: 'motion', available: true}, {entity_id: 'binary_sensor.test_presence', name: 'Testpräsenz', device_class: 'presence', available: false}], lux_sensors: [{entity_id: 'sensor.test_lux', name: 'Testhelligkeit', device_class: 'illuminance', available: true}]});
function setup(initial = response(), options: {adaptive?: boolean; mutation?: (message: Record<string, unknown>) => Promise<MotionResponse>; get?: (message: Record<string, unknown>) => Promise<MotionResponse>} = {}) {
  const callWS = vi.fn(async (message: {type: string; [key: string]: unknown}): Promise<unknown> => {
    switch (message.type) {
      case 'lichtzentrale/motion/get': return options.get ? options.get(message) : initial;
      case 'lichtzentrale/lights/list': return [{entity_id: 'light.test_one', name: 'Testlampe', area_id: 'test_room_a', area_name: 'Testraum A', allowed: true, available: true}, {entity_id: 'switch.test_two', name: 'Testschalter', area_id: 'test_room_b', area_name: 'Testraum B', allowed: true, available: true}, {entity_id: 'switch.test_blocked', name: 'Nicht freigegeben', allowed: false, available: true}];
      case 'lichtzentrale/scenes/list': return [{id: 'test_scene', name: 'Testszene', area_id: 'test_room_a'}, {id: 'test_other', name: 'Fremde Szene', area_id: 'test_room_b'}];
      case 'lichtzentrale/adaptive/status': return {available: !!options.adaptive, rooms: [{area_id: 'test_room_a', available: !!options.adaptive}]};
      case 'lichtzentrale/motion/save': return options.mutation ? options.mutation(message) : response(message.config as MotionConfig);
      case 'lichtzentrale/motion/set_enabled': return options.mutation ? options.mutation(message) : response({...config(), enabled: message.enabled as boolean});
      default: throw Error(message.type);
    }
  });
  const hass = {callWS} as Hass;
  const view = render(<MotionControls hass={hass} area="test_room_a"/>);
  return {callWS, hass, ...view};
}
const edit = async () => fireEvent.click(await screen.findByText('Bewegungsautomatik bearbeiten'));
const change = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), {target: {value}});
const saveButton = () => screen.getByText('Bewegungsautomatik speichern');
const mutations = (mock: ReturnType<typeof vi.fn>) => mock.mock.calls.filter(([message]) => /motion\/(save|set_enabled)$/.test(message.type));
function deferred<T>() {let resolve!: (value: T) => void; let reject!: (reason: Error) => void; const promise = new Promise<T>((yes, no) => {resolve = yes; reject = no;}); return {promise, resolve, reject};}

describe('Bewegungsautomatik', () => {
  it('saves runtime sensor selection, lux, solar windows and selected cross-room lights', async () => {
    const {callWS} = setup(response(null)); await edit();
    expect(saveButton()).toBeDisabled();
    fireEvent.click(screen.getByLabelText('Testbewegung')); fireEvent.click(screen.getByLabelText('Testpräsenz · Nicht verfügbar'));
    change('Ausschaltzeit in Sekunden', '90'); fireEvent.click(screen.getByLabelText('20 Sekunden vorher auf 30 % abdunkeln'));
    change('Lux-Sensor (optional)', 'sensor.test_lux'); change('Nur unter Helligkeit in lx', '42.5');
    change('Fenster 1 Beginn: Bezug', 'sunset'); change('Fenster 1 Beginn: Versatz in Minuten', '-15');
    change('Fenster 1 Ende: Uhrzeit', '06:00'); change('Fenster 1 Lichtauswahl', 'selected');
    expect(screen.queryByText('Nicht freigegeben')).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Testlampe')); fireEvent.click(screen.getByLabelText('Testschalter · Nur Ein/Aus')); change('Fenster 1 Helligkeit', '30');
    fireEvent.click(screen.getByText('Zeitfenster hinzufügen')); change('Fenster 2 Aktion', 'scene'); change('Fenster 2 Szene', 'test_scene');
    expect(screen.queryByText('Fremde Szene')).not.toBeInTheDocument();
    fireEvent.click(saveButton()); await screen.findByText('Bewegungsautomatik in Home Assistant gespeichert.');
    const saved = mutations(callWS)[0][0].config as MotionConfig;
    expect(saved).toMatchObject({enabled: false, sensor_entity_ids: ['binary_sensor.test_motion', 'binary_sensor.test_presence'], timeout_seconds: 90, dim_before_off: true, lux_sensor_entity_id: 'sensor.test_lux', lux_below: 42.5});
    expect(saved.windows).toEqual([{start: {type: 'sun', event: 'sunset', offset_min: -15}, end: {type: 'time', value: '06:00'}, action: {type: 'lights', entity_ids: ['light.test_one', 'switch.test_two'], brightness: 30}}, {start: {type: 'time', value: '00:00'}, end: {type: 'time', value: '00:00'}, action: {type: 'scene', scene_id: 'test_scene'}}]);
  });
  it('waits for server confirmation and ignores repeated enable clicks', async () => {
    const pending = deferred<MotionResponse>(); const {callWS} = setup(response(), {mutation: () => pending.promise}); await screen.findByText('Bewegungsautomatik bearbeiten');
    const toggle = screen.getByLabelText('Bewegungsautomatik eingeschaltet'); fireEvent.click(toggle); fireEvent.click(toggle);
    expect(toggle).not.toBeChecked(); expect(toggle).toBeDisabled(); expect(mutations(callWS)).toHaveLength(1);
    await act(async () => pending.resolve(response({...config(), enabled: true}))); expect(toggle).toBeChecked();
  });
  it('preserves disabled state on enable failure', async () => {
    setup(response(), {mutation: async () => {throw Error('Testfehler');}}); await screen.findByText('Bewegungsautomatik bearbeiten'); fireEvent.click(screen.getByLabelText('Bewegungsautomatik eingeschaltet'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Testfehler'); expect(screen.getByLabelText('Bewegungsautomatik eingeschaltet')).not.toBeChecked();
  });
  it('keeps failed drafts, blocks duplicate save and cancels without changing saved data', async () => {
    const pending = deferred<MotionResponse>(); const {callWS} = setup(response(), {mutation: () => pending.promise}); await edit(); change('Ausschaltzeit in Sekunden', '321');
    fireEvent.click(saveButton()); fireEvent.click(saveButton()); expect(mutations(callWS)).toHaveLength(1); expect(screen.getByText('Abbrechen')).toBeDisabled();
    await act(async () => pending.reject(Error('Testfehler'))); expect(screen.getByLabelText('Ausschaltzeit in Sekunden')).toHaveValue(321);
    fireEvent.click(screen.getByText('Abbrechen')); await edit(); expect(screen.getByLabelText('Ausschaltzeit in Sekunden')).toHaveValue(120);
  });
  it('ignores an old save after navigating to another room', async () => {
    const pending = deferred<MotionResponse>(); const {hass, rerender} = setup(response(), {mutation: () => pending.promise}); await edit(); fireEvent.click(saveButton());
    rerender(<MotionControls hass={hass} area="test_room_b"/>); await screen.findByText('Bewegungsautomatik bearbeiten');
    await act(async () => pending.resolve(response({...config(), enabled: true})));
    expect(screen.getByLabelText('Bewegungsautomatik eingeschaltet')).not.toBeChecked(); expect(screen.queryByText('Bewegungsautomatik in Home Assistant gespeichert.')).not.toBeInTheDocument();
  });
  it('ignores stale initial fetches after switching rooms', async () => {
    const pending = deferred<MotionResponse>(); const {hass, rerender} = setup(response(), {get: message => message.area_id === 'test_room_a' ? pending.promise : Promise.resolve(response())});
    rerender(<MotionControls hass={hass} area="test_room_b"/>); await screen.findByText('Bewegungsautomatik bearbeiten');
    await act(async () => pending.resolve(response({...config(), enabled: true}))); expect(screen.getByLabelText('Bewegungsautomatik eingeschaltet')).not.toBeChecked();
  });
  it('requires removal of missing sensors and disallowed light selections', async () => {
    const saved = config(); saved.sensor_entity_ids.push('binary_sensor.test_removed'); saved.windows[0].action = {type: 'lights', entity_ids: ['light.test_removed'], brightness: 100};
    setup(response(saved)); await edit(); expect(saveButton()).toBeDisabled(); fireEvent.click(screen.getByText('Sensor entfernen')); fireEvent.click(screen.getByText('Licht entfernen')); expect(saveButton()).toBeDisabled(); fireEvent.click(screen.getByLabelText('Testlampe')); expect(saveButton()).toBeEnabled();
  });
  it('validates timeout, dimming, lux, offsets and empty windows', async () => {
    setup(); await edit(); change('Ausschaltzeit in Sekunden', ''); expect(saveButton()).toBeDisabled(); change('Ausschaltzeit in Sekunden', '20'); fireEvent.click(screen.getByLabelText('20 Sekunden vorher auf 30 % abdunkeln')); expect(saveButton()).toBeDisabled(); change('Ausschaltzeit in Sekunden', '21'); expect(saveButton()).toBeEnabled();
    change('Lux-Sensor (optional)', 'sensor.test_lux'); change('Nur unter Helligkeit in lx', '-1'); expect(saveButton()).toBeDisabled(); change('Nur unter Helligkeit in lx', '0'); expect(saveButton()).toBeEnabled();
    change('Fenster 1 Beginn: Bezug', 'sunrise'); change('Fenster 1 Beginn: Versatz in Minuten', '1441'); expect(saveButton()).toBeDisabled(); change('Fenster 1 Beginn: Versatz in Minuten', '0'); expect(saveButton()).toBeEnabled(); fireEvent.click(screen.getByText('Fenster 1 entfernen')); expect(saveButton()).toBeDisabled();
  });
  it('hides unavailable adaptive action and requires replacement of stale adaptive or scene actions', async () => {
    const saved = config(); saved.windows[0].action = {type: 'adaptive'}; setup(response(saved)); await edit(); expect(screen.queryByRole('option', {name: 'Natürliches Licht'})).not.toBeInTheDocument(); expect(saveButton()).toBeDisabled(); change('Fenster 1 Aktion', 'scene'); expect(saveButton()).toBeDisabled(); change('Fenster 1 Szene', 'test_scene'); expect(saveButton()).toBeEnabled();
  });
  it('saves available adaptive action and supports ordered windows', async () => {
    const {callWS} = setup(response(), {adaptive: true}); await edit(); change('Fenster 1 Aktion', 'adaptive'); fireEvent.click(screen.getByText('Zeitfenster hinzufügen')); fireEvent.click(screen.getByText('Fenster 2 nach oben')); fireEvent.click(saveButton());
    await waitFor(() => expect(mutations(callWS)).toHaveLength(1)); expect((mutations(callWS)[0][0].config as MotionConfig).windows.map(window => window.action.type)).toEqual(['lights', 'adaptive']);
  });
  it('reload discards the draft and uses fresh server state', async () => {
    const {callWS} = setup(); await edit(); change('Ausschaltzeit in Sekunden', '99'); fireEvent.click(screen.getByText('Bewegungsautomatik neu laden')); await edit(); expect(screen.getByLabelText('Ausschaltzeit in Sekunden')).toHaveValue(120); expect(callWS.mock.calls.filter(([message]) => message.type === 'lichtzentrale/motion/get')).toHaveLength(2);
  });
  it('shows runtime dispatch errors without claiming success', async () => {
    const data = response(); data.status.last_error = 'Testszene nicht mehr vorhanden'; setup(data);
    expect(await screen.findByRole('alert')).toHaveTextContent('Letzte Ausführung: Testszene nicht mehr vorhanden');
  });
  it('does not permit enable before creating a configuration', async () => {
    setup(response(null)); await screen.findByText('Bewegungsautomatik bearbeiten'); expect(screen.getByLabelText('Bewegungsautomatik eingeschaltet')).toBeDisabled();
  });
});

it('saves switch-only motion with null brightness and no dimmer', async () => {
  const saved = config(); saved.windows[0].action = {type: 'lights', entity_ids: ['switch.test_two'], brightness: null};
  const {callWS} = setup(response(saved)); await edit();
  expect(screen.queryByLabelText('Fenster 1 Helligkeit')).not.toBeInTheDocument(); expect(saveButton()).toBeEnabled();
  fireEvent.click(saveButton()); await screen.findByText('Bewegungsautomatik in Home Assistant gespeichert.');
  expect((mutations(callWS)[0][0].config as MotionConfig).windows[0].action).toEqual({type: 'lights', entity_ids: ['switch.test_two'], brightness: null});
});
