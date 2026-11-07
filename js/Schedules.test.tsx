// Geändert für Lichtzentrale
// @vitest-environment jsdom
import {afterEach, describe, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {Schedules} from './Schedules';
import type {Hass, Schedule, ScheduleEntry, SchedulesResponse} from './types';
afterEach(() => {cleanup(); vi.useRealTimers(); vi.unstubAllGlobals();});
const plan = (): ScheduleEntry => ({id: 'test_plan', name: 'Testplan', enabled: false, trigger: {type: 'time', value: '18:00'}, condition: {weekdays: [0,1,2,3,4,5,6], person_entity_ids: [], light_state: 'any'}, action: {type: 'scene', scene_id: 'test_scene'}, transition: null, next_run: null, last_error: null});
const response = (schedules = [plan()]): SchedulesResponse => ({time_zone: 'Europe/Berlin', schedules, lux_sensors: [{entity_id: 'sensor.test_lux', name: 'Testhelligkeit', device_class: 'illuminance', available: true}], persons: [{entity_id: 'person.test_person', name: 'Testperson', available: true}]});
function deferred<T>() {let resolve!: (v: T) => void; let reject!: (e: Error) => void; const promise = new Promise<T>((yes, no) => {resolve = yes; reject = no;}); return {promise, resolve, reject};}
function setup(options: {initial?: SchedulesResponse; adaptive?: boolean; write?: (m: Record<string, unknown>) => Promise<unknown>; list?: () => Promise<SchedulesResponse>} = {}) {
  let data = options.initial || response();
  const callWS = vi.fn(async (m: {type: string; [key: string]: unknown}): Promise<unknown> => {
    if (m.type === 'lichtzentrale/schedules/list') return options.list ? options.list() : data;
    if (m.type === 'lichtzentrale/rooms/list') return [{area_id: 'test_area', name: 'Testraum'}];
    if (m.type === 'lichtzentrale/lights/list') return [{entity_id: 'light.test_light', name: 'Testlampe', area_id: 'test_area', area_name: 'Testraum', allowed: true, available: true}, {entity_id: 'switch.test_switch', name: 'Testschalter', area_id: null, area_name: null, allowed: true, available: true}, {entity_id: 'switch.test_blocked', name: 'Gesperrt', allowed: false, available: true}];
    if (m.type === 'lichtzentrale/scenes/list') return [{id: 'test_scene', name: 'Testszene', dynamic: {enabled: true}}];
    if (m.type === 'lichtzentrale/adaptive/status') return {available: !!options.adaptive, rooms: [{area_id: 'test_area', available: !!options.adaptive}]};
    if (options.write) return options.write(m);
    if (m.type.endsWith('/save')) {
      const saved = m.schedule as Partial<Schedule>;
      if (saved.id !== undefined && !data.schedules.some(item => item.id === saved.id)) throw Error('Unbekannte Zeitplan-ID');
      data = response([{...saved as Schedule, id: saved.id || 'test_created', next_run: null, last_error: null}]);
    }
    if (m.type.endsWith('/delete')) data = response([]);
    if (m.type.endsWith('/set_enabled')) data = response([{...data.schedules[0], enabled: m.enabled as boolean}]);
    if (m.type.endsWith('/test')) return {applied: [], skipped: [], condition_met: false};
    return data;
  });
  return {callWS, ...render(<Schedules hass={{callWS} as Hass}/>)};
}
const change = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), {target: {value}});
const edit = async () => fireEvent.click(await screen.findByText('Bearbeiten: Testplan'));
const writes = (mock: ReturnType<typeof vi.fn>) => mock.mock.calls.filter(([m]) => m.type.startsWith('lichtzentrale/schedule/'));
const save = () => fireEvent.click(screen.getByText('Zeitplan speichern'));
describe('Zeitpläne', () => {
  it('displays next execution in the Home Assistant timezone', async () => {
    setup({initial: response([{...plan(), enabled: true, next_run: '2026-11-07T23:15:00+00:00'}])});
    expect(await screen.findByText(/Nächste Ausführung: 08.11.26, 00:15/)).toBeInTheDocument();
    expect(screen.getByText(/Home-Assistant-Zeitzone.*Europe\/Berlin/)).toBeInTheDocument();
  });
  it('creates disabled time plans without display fields or secure-context crypto', async () => {
    vi.stubGlobal('crypto', {});
    const {callWS} = setup({initial: response([])}); await screen.findByText('Noch keine Zeitpläne.'); fireEvent.click(screen.getByText('Zeitplan hinzufügen')); expect(screen.getByText('Zeitplan speichern')).toBeDisabled(); change('Name', 'Neuer Testplan'); change('Uhrzeit', '07:35'); change('Szene', 'test_scene'); save();
    await screen.findByText('Zeitplan in Home Assistant gespeichert.'); const saved = writes(callWS)[0][0].schedule as Schedule; expect(saved).toMatchObject({enabled: false, trigger: {type: 'time', value: '07:35'}}); expect(saved).not.toHaveProperty('id'); expect(saved).not.toHaveProperty('next_run'); expect(saved).not.toHaveProperty('last_error');
  });
  it('edits solar triggers, conditions and transition', async () => {
    const {callWS} = setup(); await edit(); change('Auslöser', 'sun'); change('Sonnenereignis', 'sunrise'); change('Versatz in Minuten', '-20'); fireEvent.click(screen.getByLabelText('Montag')); fireEvent.click(screen.getByLabelText('Testperson')); change('Lampenzustand', 'on'); fireEvent.click(screen.getByLabelText('Sanfter Übergang')); change('Übergangszeit in Sekunden', '1800'); save(); await screen.findByText('Zeitplan in Home Assistant gespeichert.'); expect(writes(callWS)[0][0].schedule).toMatchObject({id: 'test_plan', trigger: {type: 'sun', event: 'sunrise', offset_min: -20}, condition: {weekdays: [1,2,3,4,5,6], person_entity_ids: ['person.test_person'], light_state: 'on'}, transition: 1800}); expect(writes(callWS)[0][0].schedule).not.toHaveProperty('next_run');
  });
  it('saves lux and switch-only selection without brightness', async () => {
    const {callWS} = setup(); await edit(); change('Auslöser', 'lux'); change('Lux-Sensor', 'sensor.test_lux'); change('Vergleich', 'above'); change('Schwelle in lx', '42.5'); change('Mindestdauer in Sekunden', '300'); change('Aktion', 'lights'); expect(screen.queryByText('Gesperrt')).not.toBeInTheDocument(); fireEvent.click(screen.getByLabelText('Testschalter · Nur Ein/Aus')); save(); await screen.findByText('Zeitplan in Home Assistant gespeichert.'); expect(writes(callWS)[0][0].schedule).toMatchObject({trigger: {type: 'lux', sensor_entity_id: 'sensor.test_lux', comparison: 'above', threshold: 42.5, duration_seconds: 300}, action: {type: 'lights', entity_ids: ['switch.test_switch'], on: true, brightness: null}}); expect(screen.getByText(/Lux-Pläne reagieren/)).toBeInTheDocument();
  });
  it('normalizes old plans without a time window to null on save', async () => {
    const {callWS} = setup(); await edit();
    expect(screen.getByLabelText('Nur zwischen … und …')).not.toBeChecked();
    expect(screen.queryByLabelText('Beginn: Grenze')).not.toBeInTheDocument();
    save(); await screen.findByText('Zeitplan in Home Assistant gespeichert.');
    expect(writes(callWS)[0][0].schedule).toMatchObject({condition: {time_window: null}});
  });
  it('persists a solar lower boundary, reloads and edits it repeatedly', async () => {
    const {callWS} = setup(); await edit();
    fireEvent.click(screen.getByLabelText('Nur zwischen … und …'));
    change('Beginn: Grenze', 'sun'); change('Beginn: Versatz in Minuten', '-60'); change('Ende: Grenze', 'none');
    save(); await screen.findByText('Zeitplan in Home Assistant gespeichert.');
    expect(writes(callWS)[0][0].schedule).toMatchObject({condition: {time_window: {after: {type: 'sun', event: 'sunset', offset_min: -60}, before: null}}});
    expect(screen.getByText('Zeitfenster: ab Sonnenuntergang −60 min')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Zeitpläne neu laden')); await edit();
    expect(screen.getByLabelText('Beginn: Versatz in Minuten')).toHaveValue(-60);
    expect(screen.getByLabelText('Ende: Grenze')).toHaveValue('none');
    change('Beginn: Sonnenereignis', 'sunrise'); change('Beginn: Versatz in Minuten', '30'); save();
    await screen.findByText('Zeitfenster: ab Sonnenaufgang +30 min');
    await edit(); change('Beginn: Grenze', 'time'); change('Beginn: Uhrzeit', '22:00'); change('Ende: Grenze', 'time'); change('Ende: Uhrzeit', '06:00'); save();
    await screen.findByText('Zeitfenster: ab 22:00 Uhr · bis 06:00 Uhr');
    expect(writes(callWS).at(-1)?.[0].schedule).toMatchObject({condition: {time_window: {after: {type: 'time', value: '22:00'}, before: {type: 'time', value: '06:00'}}}});
  });
  it.each(['time', 'sun', 'lux'] as const)('supports upper-only and open windows for %s triggers', async type => {
    const initial = plan(); initial.trigger = type === 'time' ? initial.trigger : type === 'sun' ? {type, event: 'sunset', offset_min: 0} : {type, sensor_entity_id: 'sensor.test_lux', comparison: 'below', threshold: 50, duration_seconds: 300};
    const {callWS} = setup({initial: response([initial])}); await edit();
    fireEvent.click(screen.getByLabelText('Nur zwischen … und …')); change('Beginn: Grenze', 'none'); change('Ende: Grenze', 'sun');
    save(); await screen.findByText('Zeitfenster: bis Sonnenaufgang');
    expect(writes(callWS).at(-1)?.[0].schedule).toMatchObject({condition: {time_window: {after: null, before: {type: 'sun', event: 'sunrise', offset_min: 0}}}});
    await edit(); change('Ende: Grenze', 'none'); save(); await screen.findByText('Zeitfenster: Ohne zeitliche Begrenzung');
    expect(writes(callWS).at(-1)?.[0].schedule).toMatchObject({condition: {time_window: {after: null, before: null}}});
  });
  it('disables windows explicitly and cancel never mutates the saved boundaries', async () => {
    const initial = plan(); initial.condition.time_window = {after: {type: 'time', value: '21:30'}, before: {type: 'sun', event: 'sunrise', offset_min: -15}};
    const {callWS} = setup({initial: response([initial])}); await edit();
    change('Beginn: Uhrzeit', '23:00'); fireEvent.click(screen.getByLabelText('Nur zwischen … und …')); fireEvent.click(screen.getByText('Abbrechen')); await edit();
    expect(screen.getByLabelText('Nur zwischen … und …')).toBeChecked(); expect(screen.getByLabelText('Beginn: Uhrzeit')).toHaveValue('21:30');
    expect(initial.condition.time_window.after).toEqual({type: 'time', value: '21:30'});
    fireEvent.click(screen.getByLabelText('Nur zwischen … und …')); save(); await screen.findByText('Zeitplan in Home Assistant gespeichert.');
    expect(writes(callWS)[0][0].schedule).toMatchObject({condition: {time_window: null}});
    expect(screen.queryByText(/^Zeitfenster:/)).not.toBeInTheDocument();
    await edit(); expect(screen.getByLabelText('Nur zwischen … und …')).not.toBeChecked();
  });
  it('validates both boundary offsets and times without blocking disabled windows', async () => {
    setup(); await edit(); fireEvent.click(screen.getByLabelText('Nur zwischen … und …'));
    for (const label of ['Beginn', 'Ende']) {
      change(`${label}: Grenze`, 'sun');
      for (const invalid of ['1441', '-1441', '1.5', '']) {change(`${label}: Versatz in Minuten`, invalid); expect(screen.getByText('Zeitplan speichern')).toBeDisabled();}
      for (const valid of ['-1440', '1440', '0']) {change(`${label}: Versatz in Minuten`, valid); expect(screen.getByText('Zeitplan speichern')).toBeEnabled();}
      change(`${label}: Grenze`, 'time'); change(`${label}: Uhrzeit`, ''); expect(screen.getByText('Zeitplan speichern')).toBeDisabled(); change(`${label}: Uhrzeit`, '00:00'); expect(screen.getByText('Zeitplan speichern')).toBeEnabled();
    }
    change('Ende: Uhrzeit', ''); fireEvent.click(screen.getByLabelText('Nur zwischen … und …')); expect(screen.getByText('Zeitplan speichern')).toBeEnabled();
  });
  it('keeps time window drafts after rejected saves and locks boundary controls while pending', async () => {
    const pending = deferred<SchedulesResponse>(); const {callWS} = setup({write: () => pending.promise}); await edit();
    fireEvent.click(screen.getByLabelText('Nur zwischen … und …')); change('Beginn: Grenze', 'sun'); change('Beginn: Versatz in Minuten', '-60'); save(); save();
    expect(writes(callWS)).toHaveLength(1); expect(screen.getByLabelText('Beginn: Grenze')).toBeDisabled(); expect(screen.getByLabelText('Nur zwischen … und …')).toBeDisabled();
    await act(async () => pending.reject(Error('Testfehler')));
    expect(screen.getByLabelText('Beginn: Versatz in Minuten')).toHaveValue(-60); expect(screen.getByLabelText('Beginn: Grenze')).toBeEnabled();
    fireEvent.click(screen.getByText('Abbrechen')); await edit(); expect(screen.getByLabelText('Nur zwischen … und …')).not.toBeChecked();
  });
  it('supports brightness, off and room actions', async () => {
    const {callWS} = setup({adaptive: true}); await edit(); change('Aktion', 'lights'); fireEvent.click(screen.getByLabelText('Testlampe')); fireEvent.click(screen.getByLabelText('Helligkeit festlegen')); change('Helligkeit (1–255)', '77'); save(); await waitFor(() => expect(screen.queryByText('Zeitplan speichern')).not.toBeInTheDocument()); expect(writes(callWS).at(-1)?.[0].schedule).toMatchObject({action: {brightness: 77, on: true}});
    await edit(); fireEvent.click(screen.getByLabelText('Lampen einschalten (sonst ausschalten)')); save(); await waitFor(() => expect(screen.queryByText('Zeitplan speichern')).not.toBeInTheDocument()); expect(writes(callWS).at(-1)?.[0].schedule).toMatchObject({action: {on: false, brightness: null}});
    for (const type of ['room_off', 'adaptive', 'motion']) {await edit(); change('Aktion', type); change('Raum', 'test_area'); if (type !== 'room_off') fireEvent.click(screen.getByLabelText('Aktion einschalten (sonst ausschalten)')); save(); await waitFor(() => expect(screen.queryByText('Zeitplan speichern')).not.toBeInTheDocument()); expect(writes(callWS).at(-1)?.[0].schedule).toMatchObject({action: {type, area_id: 'test_area', ...(type === 'room_off' ? {} : {enabled: false})}});}
  });
  it('does not optimistically enable and handles rejected writes', async () => {
    const pending = deferred<SchedulesResponse>(); const {callWS} = setup({write: () => pending.promise}); await screen.findByText('Bearbeiten: Testplan'); const toggle = screen.getByLabelText('Testplan eingeschaltet'); fireEvent.click(toggle); fireEvent.click(toggle); expect(toggle).not.toBeChecked(); expect(toggle).toBeDisabled(); expect(writes(callWS)).toHaveLength(1); await act(async () => pending.reject(Error('Testfehler'))); expect(screen.getByRole('alert')).toHaveTextContent('Testfehler'); expect(toggle).not.toBeChecked(); expect(toggle).toBeEnabled();
  });
  it('waits for confirmed enable and explicit delete confirmation', async () => {
    const pending = deferred<SchedulesResponse>(); const {callWS} = setup({write: () => pending.promise}); await screen.findByText('Bearbeiten: Testplan'); fireEvent.click(screen.getByLabelText('Testplan eingeschaltet')); await act(async () => pending.resolve(response([{...plan(), enabled: true}]))); expect(screen.getByLabelText('Testplan eingeschaltet')).toBeChecked(); fireEvent.click(screen.getByText('Löschen: Testplan')); expect(writes(callWS)).toHaveLength(1); fireEvent.click(screen.getByText('Löschen abbrechen')); expect(screen.queryByText('Löschen bestätigen')).not.toBeInTheDocument(); cleanup(); setup(); await screen.findByText('Bearbeiten: Testplan'); fireEvent.click(screen.getByText('Löschen: Testplan')); fireEvent.click(screen.getByText('Löschen bestätigen')); await screen.findByText('Zeitplan gelöscht.'); expect(screen.queryByText('Bearbeiten: Testplan')).not.toBeInTheDocument();
  });
  it('keeps failed drafts and resets on cancel', async () => {
    const pending = deferred<SchedulesResponse>(); const {callWS} = setup({write: () => pending.promise}); await edit(); change('Name', 'Entwurf'); save(); save(); expect(writes(callWS)).toHaveLength(1); expect(screen.getByText('Abbrechen')).toBeDisabled(); await act(async () => pending.reject(Error('Testfehler'))); expect(screen.getByLabelText('Name')).toHaveValue('Entwurf'); fireEvent.click(screen.getByText('Abbrechen')); await edit(); expect(screen.getByLabelText('Name')).toHaveValue('Testplan');
  });
  it('explains real actions and shows unmet conditions and partial results', async () => {
    setup(); await screen.findByText('Bearbeiten: Testplan'); expect(screen.getByText(/führt die tatsächliche Aktion aus/)).toBeInTheDocument(); fireEvent.click(screen.getByText('Jetzt testen: Testplan')); await screen.findByText('Test: Bedingungen nicht erfüllt. Keine Aktion ausgeführt.'); cleanup(); setup({write: async () => ({condition_met: true, applied: ['light.test_a'], skipped: ['light.test_b'], failed: ['light.test_c']})}); await screen.findByText('Bearbeiten: Testplan'); fireEvent.click(screen.getByText('Jetzt testen: Testplan')); expect(await screen.findByRole('status')).toHaveTextContent('1 angewendet, 1 übersprungen, 1 fehlgeschlagen. Nicht alle Ziele');
  });
  it('reports successful non-light actions without misleading zero counts', async () => {
    setup({write: async () => ({condition_met: true, applied: [], skipped: [], failed: []})});
    await screen.findByText('Bearbeiten: Testplan'); fireEvent.click(screen.getByText('Jetzt testen: Testplan'));
    expect(await screen.findByRole('status')).toHaveTextContent('Test erfolgreich ausgeführt.');
    expect(screen.queryByText(/0 angewendet/)).not.toBeInTheDocument();
  });
  it('validates limits and hides unavailable adaptive action', async () => {
    setup(); await edit(); expect(screen.queryByRole('option', {name: 'Natürliches Licht'})).not.toBeInTheDocument(); change('Auslöser', 'sun'); change('Versatz in Minuten', '1441'); expect(screen.getByText('Zeitplan speichern')).toBeDisabled(); change('Versatz in Minuten', '0'); fireEvent.click(screen.getByLabelText('Sanfter Übergang')); change('Übergangszeit in Sekunden', '1801'); expect(screen.getByText('Zeitplan speichern')).toBeDisabled(); change('Übergangszeit in Sekunden', '1800'); expect(screen.getByText('Zeitplan speichern')).toBeEnabled(); change('Auslöser', 'lux'); change('Lux-Sensor', 'sensor.test_lux'); change('Mindestdauer in Sekunden', '0'); expect(screen.getByText('Zeitplan speichern')).toBeDisabled(); change('Mindestdauer in Sekunden', '1'); expect(screen.getByText('Zeitplan speichern')).toBeEnabled();
  });
  it('ignores stale polling after writes and cleans up its timer', async () => {
    vi.useFakeTimers(); const poll = deferred<SchedulesResponse>(); let count = 0; const {callWS, unmount} = setup({list: async () => ++count === 1 ? response() : poll.promise}); await act(async () => {}); await act(async () => vi.advanceTimersByTime(30000)); fireEvent.click(screen.getByLabelText('Testplan eingeschaltet')); await act(async () => {}); expect(screen.getByLabelText('Testplan eingeschaltet')).toBeChecked(); await act(async () => poll.resolve(response())); expect(screen.getByLabelText('Testplan eingeschaltet')).toBeChecked(); unmount(); const total = callWS.mock.calls.length; await act(async () => vi.advanceTimersByTime(90000)); expect(callWS).toHaveBeenCalledTimes(total);
  });
});
