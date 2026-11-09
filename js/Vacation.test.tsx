// Geändert für Lichtzentrale
// @vitest-environment jsdom
import {StrictMode} from 'react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {Vacation} from './Vacation';
import type {Hass, Room} from './types';
import type {NavigationGuard} from './sceneControls';
import type {VacationStatus} from './VacationTypes';
afterEach(() => {cleanup(); vi.useRealTimers(); vi.restoreAllMocks();});
const state = (): VacationStatus => ({enabled: false, until: null, config: {rooms: [{area_id: 'demo_living', type: 'living', weight: 1, on_behavior: {mode: 'last'}}], evening: {start: {type: 'sun', event: 'sunset', offset_min: -15}, end_earliest: {type: 'time', value: '22:30'}, end_latest: {type: 'time', value: '23:30'}}, morning: {enabled: false, start: {type: 'time', value: '06:30'}, end: {type: 'time', value: '07:30'}}, max_rooms: 3, learn_history: false, notify_service: null}, plan: [], next_switch: null, section: null, excluded: [], testing: false, notes: [], time_zone: 'Europe/Berlin'});
const rooms = [{area_id: 'demo_living', name: 'Wohnbereich', lights: [{allowed: true}]}, {area_id: 'zone_demo', name: 'Lesezone', kind: 'zone', lights: [{allowed: true}]}] as Room[];
function setup(initial = state(), guard?: (g: NavigationGuard) => void) {
  const mutate = vi.fn(async (request: Record<string, unknown>) => ({...initial, ...(request.type === 'lichtzentrale/vacation/save' ? {config: request.config, until: request.until} : request.type === 'lichtzentrale/vacation/set' ? {enabled: request.enabled, until: request.until} : {testing: true})}));
  const callWS = vi.fn(async (request: {type: string}) => request.type.endsWith('vacation/get') ? initial : request.type.endsWith('rooms/list') ? rooms : request.type.endsWith('scenes/list') ? [{id: 'demo_scene', area_id: 'demo_living', name: 'Abendlicht'}] : request.type.endsWith('notify_services') ? [{service: 'notify.demo', name: 'Mobilgerät'}] : mutate(request));
  const view = render(<Vacation hass={{callWS} as Hass} registerGuard={guard}/>); return {callWS, mutate, ...view};
}
const ready = () => screen.findByRole('switch');
const max = () => screen.getByLabelText('Maximal gleichzeitig eingeschaltete Räume');
const save = () => screen.getByRole('button', {name: 'Urlaubseinstellungen speichern'});
const testButton = () => screen.getByRole('button', {name: 'Probelauf 5 min · echte Lampen'});
describe('Urlaubsmodus', () => {
  it('loads server defaults without any lamp command and shows selectable zones and all boundaries', async () => {
    const {callWS, mutate} = setup(); await ready();
    expect(max()).toHaveValue(3); expect(screen.getByLabelText(/Lesezone/)).toBeInTheDocument();
    expect(screen.getByLabelText('Abend beginnt: Bezug')).toHaveValue('sunset');
    expect(screen.getByLabelText('Abend beginnt: Versatz in Minuten')).toHaveValue(-15);
    expect(save()).toBeDisabled(); expect(mutate).not.toHaveBeenCalled(); expect(callWS).toHaveBeenCalledTimes(4);
  });
  it('saves chosen types, weights, brightness, windows and notification server-side', async () => {
    const {mutate} = setup(); await ready();
    fireEvent.change(screen.getByLabelText('Wohnbereich: Typ'), {target: {value: 'passage'}});
    fireEvent.change(screen.getByLabelText('Wohnbereich: Häufigkeit (Gewicht)'), {target: {value: '5'}});
    fireEvent.change(screen.getByLabelText('Wohnbereich: Einschalten'), {target: {value: 'brightness'}});
    fireEvent.change(max(), {target: {value: '2'}});
    fireEvent.click(screen.getByLabelText('Morgens kurz einschalten'));
    fireEvent.change(screen.getByLabelText('Push-Hinweis beim Ein- und Ausschalten'), {target: {value: 'notify.demo'}});
    fireEvent.click(save()); await screen.findByText('Urlaubseinstellungen in Home Assistant gespeichert.');
    expect(mutate).toHaveBeenCalledWith(expect.objectContaining({type: 'lichtzentrale/vacation/save', config: expect.objectContaining({max_rooms: 2, notify_service: 'notify.demo', rooms: [expect.objectContaining({type: 'passage', weight: 5, on_behavior: {mode: 'brightness', brightness: 128}})]})}));
  });
  it.each(['', '0', '21', '1.5'])('rejects invalid maximum %s', async value => {setup(); await ready(); fireEvent.change(max(), {target: {value}}); expect(save()).toBeDisabled(); expect(testButton()).toBeDisabled();});
  it('requires a scene belonging to the selected room', async () => {setup(); await ready(); fireEvent.change(screen.getByLabelText('Wohnbereich: Einschalten'), {target: {value: 'scene'}}); expect(save()).toBeDisabled(); fireEvent.change(screen.getByLabelText('Wohnbereich: Szene'), {target: {value: 'demo_scene'}}); expect(save()).toBeEnabled();});
  it('blocks duplicate saves and navigation until confirmed, then allows navigation', async () => {
    let guard: NavigationGuard = null; const {mutate} = setup(state(), next => {guard = next;}); await ready();
    let resolve!: (result: VacationStatus) => void; mutate.mockImplementationOnce(() => new Promise(done => {resolve = done;}));
    fireEvent.change(max(), {target: {value: '2'}}); fireEvent.click(save()); fireEvent.click(save());
    expect(mutate).toHaveBeenCalledTimes(1); expect(await guard!()).toBe(false); expect(max()).toBeDisabled();
    expect(screen.queryByText('Urlaubseinstellungen in Home Assistant gespeichert.')).not.toBeInTheDocument();
    await act(async () => {resolve({...state(), config: {...state().config, max_rooms: 2}});});
    expect(guard).toBeNull(); expect(save()).toBeDisabled();
  });
  it('retains edits after failed save and supports retry', async () => {
    const {mutate} = setup(); await ready(); fireEvent.change(max(), {target: {value: '2'}}); mutate.mockRejectedValueOnce(new Error('Offline')); fireEvent.click(save()); await screen.findByRole('alert'); expect(max()).toHaveValue(2); expect(save()).toBeEnabled(); fireEvent.click(save()); await screen.findByText('Urlaubseinstellungen in Home Assistant gespeichert.');
  });
  it('does not accept mismatching save acknowledgements', async () => {const {mutate} = setup(); await ready(); fireEvent.change(max(), {target: {value: '2'}}); mutate.mockResolvedValueOnce(state()); fireEvent.click(save()); expect(await screen.findByRole('alert')).toHaveTextContent('nicht bestätigt'); expect(max()).toHaveValue(2);});
  it('guards unsaved navigation, and never tests a dirty draft', async () => {
    let guard: NavigationGuard = null; setup(state(), next => {guard = next;}); await ready(); fireEvent.change(max(), {target: {value: '2'}});
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false); expect(await guard!()).toBe(false); expect(testButton()).toBeDisabled(); confirm.mockReturnValue(true); expect(await guard!()).toBe(true);
  });
  it('explicitly confirms genuine test actions and allows stopping a running test', async () => {
    const {mutate} = setup(); await ready(); const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false); fireEvent.click(testButton()); expect(mutate).not.toHaveBeenCalled(); confirm.mockReturnValue(true); fireEvent.click(testButton()); await screen.findByText('Probelauf läuft'); expect(mutate).toHaveBeenCalledWith({type: 'lichtzentrale/vacation/test'}); expect(testButton()).toBeDisabled(); fireEvent.click(screen.getByRole('button', {name: 'Probelauf beenden'})); await waitFor(() => expect(mutate).toHaveBeenLastCalledWith({type: 'lichtzentrale/vacation/set', enabled: false, until: null}));
  });
  it('shows HA-local timeline and excludes hand-operated rooms; prevents test during vacation', async () => {
    setup({...state(), enabled: true, plan: [{area_id: 'demo_living', start: '2026-11-09T17:00:00Z', end: '2026-11-09T18:00:00Z', section: 'evening'}], next_switch: {at: '2026-11-09T18:00:00Z', area_id: 'demo_living', on: false}, excluded: ['demo_living']}); await ready(); expect(screen.getByText('18:00–19:00')).toBeInTheDocument(); expect(screen.getByText(/Nächste Schaltung: 19:00 · Wohnbereich · aus/)).toBeInTheDocument(); expect(screen.getByText(/Durch Handbedienung ausgenommen/)).toBeInTheDocument(); expect(testButton()).toBeDisabled();
  });
  it('loads failure explicitly and retries', async () => {
    const callWS = vi.fn().mockRejectedValue(new Error('Offline')); render(<Vacation hass={{callWS} as Hass}/>); await screen.findByRole('alert'); expect(screen.queryByRole('switch')).not.toBeInTheDocument(); fireEvent.click(screen.getByText('Urlaubsmodus erneut laden')); await waitFor(() => expect(callWS).toHaveBeenCalledTimes(8));
  });
  it('ignores stale StrictMode responses and unmounted saves', async () => {
    let resolve!: (result: VacationStatus) => void; let gets = 0;
    const callWS = vi.fn(async (r: {type: string}) => r.type.endsWith('vacation/get') ? ++gets === 1 ? new Promise<VacationStatus>(done => {resolve = done;}) : {...state(), enabled: true} : r.type.endsWith('rooms/list') ? rooms : []);
    const view = render(<StrictMode><Vacation hass={{callWS} as Hass}/></StrictMode>); await ready(); await act(async () => {resolve(state());}); expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'); view.unmount();
  });
  it('atomically saves the enddate with configuration', async () => {
    setup(); await ready(); fireEvent.change(screen.getByLabelText('Enddatum (optional, einschließlich)'), {target: {value: '2027-01-10'}}); fireEvent.change(max(), {target: {value: '2'}}); fireEvent.click(save()); await screen.findByText('Urlaubseinstellungen in Home Assistant gespeichert.'); expect(screen.getByLabelText('Enddatum (optional, einschließlich)')).toHaveValue('2027-01-10'); expect(screen.queryByText('Enddatum übernehmen')).not.toBeInTheDocument(); expect(save()).toBeDisabled();
  });
});


describe('Urlaubsstatus automatisch aktuell halten', () => {
  async function polling(initial = state()) {
    vi.useFakeTimers(); const view = setup(initial);
    await act(async () => {await Promise.resolve();});
    return view;
  }
  it('refreshes trial auto-end and next switch without reopening the page', async () => {
    const {callWS} = await polling({...state(), testing: true, plan: [{area_id: 'demo_living', start: '2026-11-09T17:00:00Z', end: '2026-11-09T17:05:00Z', section: 'test'}]});
    expect(screen.getByText('Probelauf läuft')).toBeInTheDocument();
    expect(screen.getByText('Probelauf', {selector: 'small'})).toBeInTheDocument();
    callWS.mockResolvedValueOnce({...state(), next_switch: {at: '2026-11-09T18:00:00Z', area_id: 'demo_living', on: true}});
    await act(async () => {await vi.advanceTimersByTimeAsync(10000);});
    expect(screen.getByText('Urlaubsmodus ist aus')).toBeInTheDocument();
    expect(screen.queryByText('Probelauf läuft')).not.toBeInTheDocument();
    expect(screen.getByText('Nächste Schaltung: 19:00 · Wohnbereich · an')).toBeInTheDocument();
    expect(testButton()).toBeEnabled();
  });
  it('preserves dirty config and enddate even when editing starts during a read', async () => {
    const {callWS} = await polling();
    let resolve!: (result: VacationStatus) => void;
    callWS.mockImplementationOnce(() => new Promise(done => {resolve = done;}));
    await act(async () => {await vi.advanceTimersByTimeAsync(10000);});
    fireEvent.change(max(), {target: {value: '2'}});
    fireEvent.change(screen.getByLabelText('Enddatum (optional, einschließlich)'), {target: {value: '2027-01-10'}});
    await act(async () => {resolve({...state(), enabled: true, config: {...state().config, max_rooms: 4}});});
    expect(max()).toHaveValue(2);
    expect(screen.getByLabelText('Enddatum (optional, einschließlich)')).toHaveValue('2027-01-10');
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true');
    expect(save()).toBeEnabled();
  });
  it('accepts external settings into a clean editor and cleans up on unmount', async () => {
    const {callWS, unmount} = await polling();
    callWS.mockResolvedValueOnce({...state(), config: {...state().config, max_rooms: 4}, until: '2027-01-10'});
    await act(async () => {await vi.advanceTimersByTimeAsync(10000);});
    expect(max()).toHaveValue(4); expect(save()).toBeDisabled();
    unmount(); const count = callWS.mock.calls.length;
    await act(async () => {await vi.advanceTimersByTimeAsync(30000);});
    expect(callWS).toHaveBeenCalledTimes(count); expect(vi.getTimerCount()).toBe(0);
  });
  it('skips overlapping reads and mutation waits, ignores superseded read responses', async () => {
    const {callWS, mutate} = await polling();
    let resolve!: (result: VacationStatus) => void;
    callWS.mockImplementationOnce(() => new Promise(done => {resolve = done;}));
    await act(async () => {await vi.advanceTimersByTimeAsync(10000);});
    const count = callWS.mock.calls.length;
    await act(async () => {await vi.advanceTimersByTimeAsync(20000);});
    expect(callWS).toHaveBeenCalledTimes(count);
    fireEvent.change(max(), {target: {value: '2'}});
    let saved!: (result: VacationStatus) => void;
    mutate.mockImplementationOnce(() => new Promise(done => {saved = done;}));
    fireEvent.click(save());
    await act(async () => {resolve({...state(), enabled: true}); await vi.advanceTimersByTimeAsync(10000);});
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false');
    expect(callWS).toHaveBeenCalledTimes(count + 1);
    await act(async () => {saved({...state(), config: {...state().config, max_rooms: 2}});});
    expect(max()).toHaveValue(2); expect(save()).toBeDisabled();
  });
});
