// Geändert für Lichtzentrale
// @vitest-environment jsdom
import {afterEach, describe, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen} from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {BasicBrightnessControls} from './BasicBrightnessControls';
import type {BrightnessConfig, BrightnessResponse, Hass} from './types';
afterEach(() => {cleanup(); vi.useRealTimers();});
const config = (): BrightnessConfig => ({enabled: false, lux_sensor_entity_id: 'sensor.test_lux', target_lux: 100, hysteresis_lux: 10, min_interval_seconds: 180, time_window: null, person_entity_ids: [], stages: [{entity_ids: ['light.test_one'], brightness: 128}]});
const response = (saved: BrightnessConfig | null = config()): BrightnessResponse => ({config: saved, status: {enabled: saved?.enabled || false, paused: false, current_lux: 62.5, active_stage: 0, learned_lux: [12.5], last_error: null}, lux_sensors: [{entity_id: 'sensor.test_lux', name: 'Testsensor', device_class: 'illuminance', available: true}], persons: [{entity_id: 'person.test_presence', name: 'Testanwesenheit', available: true}]});
function setup(initial = response(), options: {get?: (message: Record<string, unknown>) => Promise<BrightnessResponse>; mutation?: (message: Record<string, unknown>) => Promise<BrightnessResponse>} = {}) {
  const callWS = vi.fn(async (message: {type: string; [key: string]: unknown}): Promise<unknown> => {
    switch (message.type) {
      case 'lichtzentrale/brightness/get': return options.get ? options.get(message) : initial;
      case 'lichtzentrale/lights/list': return [{entity_id: 'light.test_one', name: 'Testlampe', area_id: 'test_room_a', allowed: true, available: true}, {entity_id: 'switch.test_two', name: 'Testschalter', area_id: 'test_room_a', allowed: true, available: true}, {entity_id: 'light.test_other', name: 'Fremdes Licht', area_id: 'test_room_b', allowed: true, available: true}, {entity_id: 'switch.test_blocked', name: 'Gesperrtes Licht', area_id: 'test_room_a', allowed: false, available: true}];
      case 'lichtzentrale/brightness/save': return options.mutation ? options.mutation(message) : response(message.config as BrightnessConfig);
      case 'lichtzentrale/brightness/set_enabled': return options.mutation ? options.mutation(message) : response({...config(), enabled: message.enabled as boolean});
      default: throw Error(message.type);
    }
  });
  const hass = {callWS} as Hass;
  return {callWS, hass, ...render(<BasicBrightnessControls hass={hass} area="test_room_a"/>)};
}
const edit = async () => fireEvent.click(await screen.findByText('Grundhelligkeit bearbeiten'));
const change = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), {target: {value}});
const save = () => screen.getByText('Grundhelligkeit speichern');
const mutations = (mock: ReturnType<typeof vi.fn>) => mock.mock.calls.filter(([message]) => /brightness\/(save|set_enabled)$/.test(message.type));
function deferred<T>() {let resolve!: (value: T) => void; let reject!: (reason: Error) => void; const promise = new Promise<T>((yes, no) => {resolve = yes; reject = no;}); return {promise, resolve, reject};}

describe('Grundhelligkeit', () => {
  it('creates disabled configuration with default interval, conditions and ordered same-room targets', async () => {
    const {callWS} = setup(response(null)); await edit(); expect(save()).toBeDisabled();
    expect(screen.getByLabelText('Mindestzeit zwischen Stufenwechseln in Sekunden')).toHaveValue(180);
    change('Lux-Sensor', 'sensor.test_lux'); change('Zielhelligkeit in lx', '120'); change('Hysterese in lx', '15');
    expect(screen.queryByText('Fremdes Licht')).not.toBeInTheDocument(); expect(screen.queryByText('Gesperrtes Licht')).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Stufe 1: Testlampe')); change('Stufe 1 Helligkeit', '90');
    fireEvent.click(screen.getByLabelText('Zeitfenster begrenzen')); change('Beginn: Bezug', 'sunset'); change('Beginn: Versatz in Minuten', '-30'); change('Ende: Bezug', 'none');
    fireEvent.click(screen.getByLabelText('Testanwesenheit')); fireEvent.click(screen.getByText('Stufe hinzufügen'));
    expect(screen.getByLabelText('Stufe 2: Testlampe')).toBeDisabled(); fireEvent.click(screen.getByLabelText('Stufe 2: Testschalter'));
    expect(screen.queryByLabelText('Stufe 2 Helligkeit')).not.toBeInTheDocument();
    fireEvent.click(save()); await screen.findByText('Grundhelligkeit in Home Assistant gespeichert.');
    expect(mutations(callWS)[0][0].config).toEqual({enabled: false, lux_sensor_entity_id: 'sensor.test_lux', target_lux: 120, hysteresis_lux: 15, min_interval_seconds: 180, time_window: {after: {type: 'sun', event: 'sunset', offset_min: -30}, before: null}, person_entity_ids: ['person.test_presence'], stages: [{entity_ids: ['light.test_one'], brightness: 90}, {entity_ids: ['switch.test_two'], brightness: null}]});
  });
  it('supports both reorder directions and removal without mixing stage values', async () => {
    const saved = config(); saved.stages.push({entity_ids: ['switch.test_two'], brightness: null}); const {callWS} = setup(response(saved)); await edit();
    fireEvent.click(screen.getByText('Stufe 1 nach unten')); expect(screen.getByLabelText('Stufe 1: Testschalter')).toBeChecked();
    fireEvent.click(screen.getByText('Stufe 2 nach oben')); expect(screen.getByLabelText('Stufe 1 Helligkeit')).toHaveValue('128');
    fireEvent.click(screen.getByText('Stufe 1 entfernen')); expect(screen.queryByLabelText('Stufe 1 Helligkeit')).not.toBeInTheDocument(); fireEvent.click(save());
    await screen.findByText('Grundhelligkeit in Home Assistant gespeichert.'); expect((mutations(callWS)[0][0].config as BrightnessConfig).stages).toEqual([{entity_ids: ['switch.test_two'], brightness: null}]);
  });
  it('preserves stale sensor, person and light selections until corrected', async () => {
    const saved = config(); saved.lux_sensor_entity_id = 'sensor.test_removed'; saved.person_entity_ids = ['person.test_removed']; saved.stages[0].entity_ids = ['light.test_other'];
    setup(response(saved)); await edit(); expect(save()).toBeDisabled(); expect(screen.getByText(/sensor.test_removed/)).toBeInTheDocument(); expect(screen.getByText(/person.test_removed/)).toBeInTheDocument(); expect(screen.getByText(/light.test_other/)).toBeInTheDocument();
    change('Lux-Sensor', 'sensor.test_lux'); fireEvent.click(screen.getByText('Person entfernen')); fireEvent.click(screen.getByText('Licht aus Stufe 1 entfernen')); expect(save()).toBeDisabled(); fireEvent.click(screen.getByLabelText('Stufe 1: Testlampe')); expect(save()).toBeEnabled();
  });
  it('blocks invalid numbers, duplicate targets and empty stages', async () => {
    const saved = config(); saved.stages.push({...saved.stages[0]}); setup(response(saved)); await edit(); expect(save()).toBeDisabled(); fireEvent.click(screen.getByText('Stufe 2 entfernen')); expect(save()).toBeEnabled();
    for (const [label, invalid, valid] of [['Zielhelligkeit in lx', '', '100'], ['Hysterese in lx', '-1', '10'], ['Mindestzeit zwischen Stufenwechseln in Sekunden', '1.5', '180']]) {change(label, invalid); expect(save()).toBeDisabled(); change(label, valid); expect(save()).toBeEnabled();}
    fireEvent.click(screen.getByLabelText('Zeitfenster begrenzen')); change('Beginn: Bezug', 'sunrise'); change('Beginn: Versatz in Minuten', '1441'); expect(save()).toBeDisabled(); change('Beginn: Versatz in Minuten', '-1440'); expect(save()).toBeEnabled();
    fireEvent.click(screen.getByText('Stufe 1 entfernen')); expect(save()).toBeDisabled();
  });
  it('waits for enable confirmation, blocks repeat clicks and preserves errors', async () => {
    const pending = deferred<BrightnessResponse>(); const {callWS} = setup(response(), {mutation: () => pending.promise}); await screen.findByText('Grundhelligkeit bearbeiten');
    const toggle = screen.getByLabelText('Grundhelligkeit eingeschaltet'); fireEvent.click(toggle); fireEvent.click(toggle); expect(toggle).not.toBeChecked(); expect(toggle).toBeDisabled(); expect(mutations(callWS)).toHaveLength(1);
    await act(async () => pending.reject(Error('Testfehler'))); expect(toggle).not.toBeChecked(); expect(await screen.findByRole('alert')).toHaveTextContent('Testfehler');
  });
  it('keeps failed drafts and cancels to persisted state', async () => {
    const pending = deferred<BrightnessResponse>(); const {callWS} = setup(response(), {mutation: () => pending.promise}); await edit(); change('Zielhelligkeit in lx', '321'); fireEvent.click(save()); fireEvent.click(save()); expect(mutations(callWS)).toHaveLength(1);
    expect(screen.getByText('Abbrechen')).toBeDisabled(); await act(async () => pending.reject(Error('Testfehler'))); expect(screen.getByLabelText('Zielhelligkeit in lx')).toHaveValue(321);
    fireEvent.click(screen.getByText('Abbrechen')); await edit(); expect(screen.getByLabelText('Zielhelligkeit in lx')).toHaveValue(100);
  });
  it('ignores responses from the previous room', async () => {
    const pending = deferred<BrightnessResponse>(); const {hass, rerender} = setup(response(), {mutation: () => pending.promise}); await edit(); fireEvent.click(save()); rerender(<BasicBrightnessControls hass={hass} area="test_room_b"/>); await screen.findByText('Grundhelligkeit bearbeiten');
    await act(async () => pending.resolve(response({...config(), enabled: true}))); expect(screen.getByLabelText('Grundhelligkeit eingeschaltet')).not.toBeChecked(); expect(screen.queryByText('Grundhelligkeit in Home Assistant gespeichert.')).not.toBeInTheDocument();
  });
  it('refreshes status without overwriting an edited draft and reports stale status', async () => {
    vi.useFakeTimers(); let count = 0;
    setup(response(), {get: async () => {count++; if (count > 2) throw Error('Offline'); const data = response(); data.status.current_lux = count === 1 ? 62.5 : 77; return data;}});
    await act(async () => {}); fireEvent.click(screen.getByText('Grundhelligkeit bearbeiten')); change('Zielhelligkeit in lx', '222');
    await act(async () => {await vi.advanceTimersByTimeAsync(15000);}); expect(screen.getByText(/Aktuelle Helligkeit: 77 lx/)).toBeInTheDocument(); expect(screen.getByLabelText('Zielhelligkeit in lx')).toHaveValue(222);
    await act(async () => {await vi.advanceTimersByTimeAsync(15000);}); expect(screen.getByRole('alert')).toHaveTextContent('Status nicht aktuell: Offline'); expect(screen.getByLabelText('Zielhelligkeit in lx')).toHaveValue(222);
  });
  it('ignores a delayed initial fetch after navigation', async () => {
    const pending = deferred<BrightnessResponse>(); const {hass, rerender} = setup(response(), {get: message => message.area_id === 'test_room_a' ? pending.promise : Promise.resolve(response())});
    rerender(<BasicBrightnessControls hass={hass} area="test_room_b"/>); await screen.findByText('Grundhelligkeit bearbeiten');
    await act(async () => pending.resolve(response({...config(), enabled: true}))); expect(screen.getByLabelText('Grundhelligkeit eingeschaltet')).not.toBeChecked();
  });
  it('does not let an older poll overwrite a confirmed toggle', async () => {
    vi.useFakeTimers(); let count = 0; const pending = deferred<BrightnessResponse>();
    setup(response(), {get: async () => ++count === 1 ? response() : pending.promise}); await act(async () => {});
    await act(async () => {await vi.advanceTimersByTimeAsync(15000);}); fireEvent.click(screen.getByLabelText('Grundhelligkeit eingeschaltet')); await act(async () => {});
    expect(screen.getByLabelText('Grundhelligkeit eingeschaltet')).toBeChecked(); await act(async () => pending.resolve(response())); expect(screen.getByLabelText('Grundhelligkeit eingeschaltet')).toBeChecked();
  });
  it('shows paused status, learned shares and execution errors', async () => {
    const data = response(); data.status.paused = true; data.status.last_error = 'Testsensor nicht verfügbar'; setup(data);
    expect(await screen.findByText('Pausiert durch manuelle Änderung')).toBeInTheDocument(); expect(screen.getByText('Stufe 1: 12.5 lx')).toBeInTheDocument(); expect(screen.getByRole('alert')).toHaveTextContent('Testsensor nicht verfügbar');
  });
  it('cannot enable without saved configuration', async () => {setup(response(null)); await screen.findByText('Grundhelligkeit bearbeiten'); expect(screen.getByLabelText('Grundhelligkeit eingeschaltet')).toBeDisabled();});
});
