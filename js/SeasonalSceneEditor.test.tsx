// Geändert für Lichtzentrale
// @vitest-environment jsdom
import {afterEach, describe, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {SeasonalSceneEditor, defaultSeasonal, validMonthDay, validSeasonBoundaries} from './SeasonalSceneEditor';
import {AutomationWizard, newAutomation} from './AutomationWizard';
import {Rooms} from './Rooms';
import type {Hass, Room, Scene} from './types';
const room: Room = {area_id: 'zone:season_test', name: 'Testzone', kind: 'zone', lights: [], on: true, brightness: null, available_count: 1, last_scene_id: 'test_seasonal'};
const autumn: Scene = {id: 'test_autumn', name: 'Testglut', kind: 'palette', area_id: room.area_id, palette_id: 'test_palette', favorite: false, order: 0, preview: ['#ff9a2e', '#ff6a13']};
const winter: Scene = {...autumn, id: 'test_winter', name: 'Testwinter'};
const seasonal: Scene = {...autumn, id: 'test_seasonal', name: 'Testjahreszeit', kind: 'seasonal', seasonal: {...defaultSeasonal(), scenes: {spring: null, summer: null, autumn: autumn.id, winter: winter.id}}, favorite: true, resolved_scene_id: autumn.id, resolved_name: autumn.name, resolution_note: 'Frühling fehlt. Testglut wird verwendet.'};
const foreign: Scene = {...autumn, id: 'test_foreign', name: 'Fremde Szene', area_id: 'test_other'};
afterEach(cleanup);
function setup(scene?: Scene, api?: ReturnType<typeof vi.fn>) {
  const callWS = api || vi.fn(async (request: Record<string, unknown>) => ({...request.scene as object, id: scene?.id || 'test_created'}));
  const saved = vi.fn(), closed = vi.fn();
  render(<SeasonalSceneEditor hass={{callWS} as Hass} room={room} scenes={[autumn, winter, seasonal, foreign]} scene={scene} onClose={closed} onSaved={saved}/>);
  return {callWS, saved, closed};
}
describe('Jahreszeiten-Szenen', () => {
  it('starts with meteorological boundaries, permits gaps, and saves without controlling lamps', async () => {
    const {callWS, saved} = setup(); expect(screen.getByRole('button', {name: 'Jahreszeiten-Szene speichern'})).toBeDisabled();
    expect(within(screen.getByLabelText('Herbst')).queryByText('Fremde Szene')).not.toBeInTheDocument();
    expect(within(screen.getByLabelText('Herbst')).queryByText('Testjahreszeit')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Herbst'), {target: {value: autumn.id}});
    fireEvent.click(screen.getByRole('button', {name: 'Jahreszeiten-Szene speichern'}));
    await waitFor(() => expect(saved).toHaveBeenCalledOnce());
    expect(callWS).toHaveBeenCalledExactlyOnceWith({type: 'lichtzentrale/scene/save', scene: {name: 'Nach Jahreszeit', area_id: room.area_id, kind: 'seasonal', favorite: true, seasonal: {...defaultSeasonal(), scenes: {...defaultSeasonal().scenes, autumn: autumn.id}}}});
  });
  it('edits Christmas inclusive dates and rejects Christmas-only assignments', async () => {
    const {callWS} = setup(); fireEvent.click(screen.getByLabelText('Weihnachten zusätzlich verwenden'));
    expect(screen.getByLabelText('Weihnachten ab Tag')).toHaveValue('1'); expect(screen.getByLabelText('Weihnachten bis einschließlich Tag')).toHaveValue('26');
    fireEvent.change(screen.getByLabelText('Weihnachten'), {target: {value: winter.id}});
    expect(screen.getByRole('button', {name: 'Jahreszeiten-Szene speichern'})).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Herbst'), {target: {value: autumn.id}});
    fireEvent.change(screen.getByLabelText('Weihnachten bis einschließlich Monat'), {target: {value: '1'}});
    fireEvent.change(screen.getByLabelText('Weihnachten bis einschließlich Tag'), {target: {value: '6'}});
    fireEvent.click(screen.getByRole('button', {name: 'Jahreszeiten-Szene speichern'}));
    await waitFor(() => expect(callWS).toHaveBeenCalledWith(expect.objectContaining({scene: expect.objectContaining({seasonal: expect.objectContaining({christmas: {enabled: true, scene_id: winter.id, start: '12-01', end: '01-06'}})})})));
  });
  it('preserves existing scene metadata and configurable annual boundaries', async () => {
    const {callWS} = setup({...seasonal, night: true, order: 4});
    fireEvent.click(screen.getByText('Mehr Optionen · Jahreszeitenbeginn'));
    fireEvent.change(screen.getByLabelText('Frühling ab Monat'), {target: {value: '2'}}); fireEvent.change(screen.getByLabelText('Frühling ab Tag'), {target: {value: '15'}});
    fireEvent.change(screen.getByLabelText('Szenenname'), {target: {value: '  Testjahr  '}});
    fireEvent.click(screen.getByRole('button', {name: 'Jahreszeiten-Szene speichern'}));
    await waitFor(() => expect(callWS).toHaveBeenCalledWith(expect.objectContaining({scene: expect.objectContaining({id: seasonal.id, name: 'Testjahr', night: true, order: 4, seasonal: expect.objectContaining({boundaries: {...defaultSeasonal().boundaries, spring: '02-15'}})})})));
  });
  it('validates month lengths, distinct boundaries and cyclic season ordering', () => {
    expect(validSeasonBoundaries({spring: '02-28', summer: '02-29', autumn: '09-01', winter: '12-01'})).toBe(false);
    expect(validMonthDay('02-29')).toBe(true); expect(validMonthDay('02-30')).toBe(false); expect(validMonthDay('13-01')).toBe(false);
    expect(validSeasonBoundaries({spring: '12-01', summer: '03-01', autumn: '06-01', winter: '09-01'})).toBe(true);
    expect(validSeasonBoundaries({spring: '03-01', summer: '02-01', autumn: '09-01', winter: '12-01'})).toBe(false);
    setup(seasonal); fireEvent.click(screen.getByText('Mehr Optionen · Jahreszeitenbeginn'));
    fireEvent.change(screen.getByLabelText('Frühling ab Monat'), {target: {value: '6'}});
    expect(screen.getByRole('button', {name: 'Jahreszeiten-Szene speichern'})).toBeDisabled(); expect(screen.getByRole('alert')).toHaveTextContent('eigenen Beginn');
  });
  it('locks repeated saves, ignores late success after unmount and cancels without requests', async () => {
    let finish: (value: unknown) => void = () => {}; const callWS = vi.fn(() => new Promise(resolve => {finish = resolve;}));
    const {saved} = setup(seasonal, callWS); const button = screen.getByRole('button', {name: 'Jahreszeiten-Szene speichern'}); fireEvent.click(button); fireEvent.click(button); expect(callWS).toHaveBeenCalledOnce();
    cleanup(); await act(async () => finish(seasonal)); expect(saved).not.toHaveBeenCalled();
    const next = setup(); fireEvent.click(screen.getByRole('button', {name: 'Abbrechen'})); expect(next.closed).toHaveBeenCalledOnce(); expect(next.callWS).not.toHaveBeenCalled();
  });
  it('shows failed persistence and retains the draft for correction', async () => {
    const callWS = vi.fn().mockRejectedValue({message: 'Eine Jahreszeiten-Szene existiert bereits.'}); setup(seasonal, callWS);
    fireEvent.click(screen.getByRole('button', {name: 'Jahreszeiten-Szene speichern'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('existiert bereits'); expect(screen.getByLabelText('Herbst')).toHaveValue(autumn.id); expect(screen.getByRole('button', {name: 'Jahreszeiten-Szene speichern'})).toBeEnabled();
  });
  it('is selectable by the existing automation wizard without resolving on the client', () => {
    const save = vi.fn(); render(<AutomationWizard initial={newAutomation()} data={{lux_sensors: [], persons: []}} rooms={[]} zones={[{id: 'season_test', name: room.name, entity_ids: []}]} lights={[]} scenes={[seasonal]} disabled={false} save={save} cancel={vi.fn()}/>);
    fireEvent.click(screen.getByRole('button', {name: 'Weiter'})); fireEvent.click(screen.getByLabelText(room.name)); fireEvent.click(screen.getByRole('button', {name: 'Weiter'}));
    fireEvent.change(screen.getByLabelText('Szene 1'), {target: {value: seasonal.id}}); fireEvent.click(screen.getByRole('button', {name: 'Automation speichern'}));
    expect(save).toHaveBeenCalledWith(expect.objectContaining({actions: [{type: 'scene', area_ids: [room.area_id], entity_ids: [], scene_id: seasonal.id}]}));
  });
  it('shows the wrapper as favorite and opens the existing seasonal editor rather than a second wrapper', async () => {
    const callWS = vi.fn(async (request: {type: string; [key: string]: unknown}): Promise<unknown> => request.type.endsWith('rooms/list') ? [room] : request.type === 'lichtzentrale/scenes/list' ? [autumn, winter, seasonal] : request.type.endsWith('adaptive/status') ? {available: false} : request.type.endsWith('dynamic/list') || request.type.endsWith('hue_scenes/list') ? [] : {applied: [], skipped: [], failed: [], resolution_note: seasonal.resolution_note, notes: [seasonal.resolution_note]});
    const view = render(<Rooms hass={{callWS} as Hass} detail={false} openRoom={vi.fn()}/>);
    fireEvent.click(await screen.findByRole('button', {name: 'Testjahreszeit in Testzone starten'})); await waitFor(() => expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/scene/apply', scene_id: seasonal.id}));
    expect(await screen.findByRole('status')).toHaveTextContent('Frühling fehlt. Testglut wird verwendet.');
    expect(screen.getByRole('status').textContent?.match(/Frühling fehlt/g)).toHaveLength(1);
    view.unmount(); render(<Rooms hass={{callWS} as Hass} detail initialArea={room.area_id} openRoom={vi.fn()}/>);
    fireEvent.click(await screen.findByRole('button', {name: 'Szene nach Jahreszeit'}));
    expect(screen.getByTestId('seasonal-editor')).toBeInTheDocument(); expect(screen.getByLabelText('Szenenname')).toHaveValue(seasonal.name); expect(screen.getByLabelText('Herbst')).toHaveValue(autumn.id);
  });
});
