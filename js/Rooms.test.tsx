// Geändert für Lichtzentrale
// @vitest-environment jsdom
import {afterEach, describe, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {StrictMode, useState} from 'react';
import {Rooms, rgbToXy} from './Rooms';
import {App} from './App';
import {styles} from './styles';
import type {Hass, Room, Scene} from './types';
const room: Room = {area_id: 'test_area', name: 'Testraum', on: false, brightness: null, available_count: 1, last_scene_id: 'test_scene', lights: [{entity_id: 'switch.test_fixture', name: 'Testschalter', area_id: 'test_area', area_name: 'Testraum', allowed: true, available: true, on: false, supported_color_modes: ['onoff']}]};
const scene: Scene = {id: 'test_scene', name: 'Testszene', area_id: room.area_id, kind: 'snapshot', favorite: false, order: 0, lights: {'switch.test_fixture': {on: true}}, preview: ['#abcdef']};
function setup(r = room) {
  const callWS = vi.fn(async (req: {type: string; [key: string]: unknown}): Promise<unknown> => {
    if (req.type.endsWith('rooms/list')) return [r];
    if (req.type.endsWith('hue_scenes/list')) return [{entity_id: 'scene.test_hue', area_id: r.area_id, name: 'Test Hue', available: true}];
    if (req.type.endsWith('scenes/list')) return [scene];
    if (req.type.endsWith('scene/snapshot')) return {scene, skipped: ['light.test_offline']};
    return {applied: ['switch.test_fixture'], skipped: []};
  });
  function Host() {const [detail, setDetail] = useState(false); return <Rooms hass={{callWS} as Hass} detail={detail} openRoom={() => setDetail(true)}/>;}
  render(<Host/>); return callWS;
}
afterEach(cleanup);
async function open() {fireEvent.click(await screen.findByRole('button', {name: 'Testraum'}));}
describe('Räume und Szenen', () => {
  it('renders a frameless room heading with a focusable native keyboard activation target', async () => {
    setup();
    const heading = await screen.findByRole('heading', {name: 'Testraum', level: 3});
    const button = within(heading).getByRole('button', {name: 'Testraum'});
    expect(button.tagName).toBe('BUTTON'); expect(button.tabIndex).toBe(0);
    button.focus(); expect(button).toHaveFocus();
    expect(styles).toMatch(/\.room-link\{[^}]*border:0[^}]*background:transparent/);
    // A browser generates a zero-detail click for Enter/Space on a native button.
    // jsdom does not synthesize that default action from a keydown by itself.
    fireEvent.click(button, {detail: 0});
    expect(await screen.findByRole('button', {name: 'Raum einschalten'})).toBeVisible();
    expect(screen.getByRole('heading', {name: 'Testraum', level: 2})).toBeVisible();
  });
  it('defaults to rooms and shows persisted last scene with restart', async () => {
    const callWS = vi.fn(async (req: {type: string}) => req.type.endsWith('rooms/list') ? [room] : req.type === 'lichtzentrale/scenes/list' ? [scene] : []);
    render(<App hass={{callWS} as Hass}/>);
    expect(screen.getByRole('button', {name: 'Räume'})).toHaveAttribute('aria-current', 'page');
    expect(await screen.findByText('Zuletzt über Lichtzentrale gestartet: Testszene')).toBeVisible();
    fireEvent.click(screen.getByRole('button', {name: 'Erneut starten'}));
    await waitFor(() => expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/scene/apply', scene_id: scene.id}));
  });
  it('switch-only room never exposes brightness, color or white controls', async () => {
    const callWS = setup(); await open();
    expect(screen.queryByRole('slider')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Testschalter Farbe')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Testschalter einschalten'}));
    await waitFor(() => expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/light/set', entity_id: 'switch.test_fixture', on: true}));
  });
  it('snapshots server state and reports unavailable omitted targets', async () => {
    const callWS = setup(); await open();
    fireEvent.change(screen.getByLabelText('Szenenname'), {target: {value: 'Neue Szene'}});
    fireEvent.click(screen.getByRole('button', {name: 'Aktuellen Zustand als Szene speichern'}));
    expect(await screen.findByRole('status')).toHaveTextContent('1 nicht verfügbare Lampe(n) fehlen');
    expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/scene/snapshot', area_id: room.area_id, name: 'Neue Szene'});
  });
  it('preserves scene data when favoriting and imports selected Hue scene', async () => {
    const callWS = setup(); await open();
    fireEvent.click(screen.getByRole('button', {name: 'Testszene als Favorit'}));
    await waitFor(() => expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/scene/save', scene: {...scene, favorite: true}}));
    await waitFor(() => expect(screen.getByLabelText('Hue-Szene')).toBeEnabled());
    fireEvent.change(screen.getByLabelText('Hue-Szene'), {target: {value: 'scene.test_hue'}});
    fireEvent.click(screen.getByRole('button', {name: 'Hue-Szene importieren'}));
    await waitFor(() => expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/scene/save', scene: {name: 'Test Hue', area_id: room.area_id, kind: 'hue', hue_scene: 'scene.test_hue'}}));
  });
  it('locks duplicate requests and ignores late success after unmount', async () => {
    const callWS = setup(); await open();
    let resolve: (value: unknown) => void = () => {};
    callWS.mockImplementationOnce(() => new Promise(done => {resolve = done;}));
    const button = screen.getByRole('button', {name: 'Anwenden'}); fireEvent.click(button); fireEvent.click(button);
    expect(callWS.mock.calls.filter(([req]) => req.type.endsWith('scene/apply'))).toHaveLength(1);
    cleanup(); await act(async () => resolve({applied: ['switch.test_fixture'], skipped: []}));
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
  it('reports errors without claiming success', async () => {
    const callWS = setup(); await open(); callWS.mockRejectedValueOnce(new Error('Testfehler'));
    fireEvent.click(screen.getByRole('button', {name: 'Anwenden'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Testfehler'); expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
  it('shows capability controls only for dimmable lights and converts RGB locally', async () => {
    setup({...room, lights: [{...room.lights[0], entity_id: 'light.test_color', supported_color_modes: ['xy', 'color_temp'], min_color_temp_kelvin: 2200, max_color_temp_kelvin: 6000}]}); await open();
    expect(screen.getAllByRole('slider')).toHaveLength(3);
    expect(screen.getByLabelText('Testschalter Farbe')).toHaveAttribute('type', 'color');
    expect(rgbToXy('#ff0000')[0]).toBeCloseTo(.7006, 3); expect(rgbToXy('#000000')).toEqual([.3127, .329]);
  });
  it('deletes only after explicit confirmation', async () => {
    const callWS = setup(); await open(); const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    fireEvent.click(screen.getByRole('button', {name: 'Löschen'})); expect(callWS.mock.calls.some(([req]) => req.type.endsWith('scene/delete'))).toBe(false);
    confirm.mockReturnValue(true); fireEvent.click(screen.getByRole('button', {name: 'Löschen'}));
    await waitFor(() => expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/scene/delete', scene_id: scene.id})); confirm.mockRestore();
  });
});

describe('Antwortreihenfolge und Sortierung', () => {
  it('rejects an obsolete load response after effect restart', async () => {
    let resolve: (value: unknown) => void = () => {}; let first = true;
    const callWS = vi.fn(async (request: {type: string}) => {
      if (request.type.endsWith('rooms/list')) {
        if (first) {first = false; return new Promise(done => {resolve = done;});}
        return [room];
      } return [];
    });
    render(<StrictMode><Rooms hass={{callWS} as Hass} detail={false} openRoom={() => {}}/></StrictMode>);
    await screen.findByRole('button', {name: 'Testraum'});
    await act(async () => resolve([{...room, name: 'Veralteter Raum'}]));
    expect(screen.queryByText('Veralteter Raum')).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Testraum'})).toBeVisible();
  });
  it('sends the complete reordered scene ID list', async () => {
    const callWS = vi.fn(async (request: {type: string}): Promise<unknown> => request.type.endsWith('rooms/list') ? [room] : request.type === 'lichtzentrale/scenes/list' ? [scene, {...scene, id: 'test_second', name: 'Zweite Testszene', order: 1}] : []);
    function Host() {const [detail, setDetail] = useState(false); return <Rooms hass={{callWS} as Hass} detail={detail} openRoom={() => setDetail(true)}/>;}
    render(<Host/>); await open();
    expect(screen.getByRole('button', {name: 'Testszene nach oben'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Testszene nach unten'}));
    await waitFor(() => expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/scenes/reorder', area_id: room.area_id, scene_ids: ['test_second', scene.id]}));
  });
});


it('shows the selected room in the main heading', async () => {
  const callWS = vi.fn(async (request: {type: string}) => request.type.endsWith('rooms/list') ? [room] : []);
  render(<App hass={{callWS} as Hass}/>);
  fireEvent.click(await screen.findByRole('button', {name: 'Testraum'}));
  expect(screen.getByRole('heading', {level: 1})).toHaveTextContent('Testraum');
});


it('remembers the selected room after visiting the gallery', async () => {
  const callWS = vi.fn(async (request: {type: string}) => request.type.endsWith('rooms/list') ? [room] : []);
  render(<App hass={{callWS} as Hass}/>);
  fireEvent.click(await screen.findByRole('button', {name: 'Testraum'}));
  fireEvent.click(screen.getByRole('button', {name: 'Galerie'}));
  fireEvent.click(screen.getByRole('button', {name: 'Raum'}));
  expect(await screen.findByRole('button', {name: 'Raum einschalten'})).toBeVisible();
  expect(screen.getByRole('heading', {level: 1})).toHaveTextContent('Testraum');
});
