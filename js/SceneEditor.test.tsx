// Geändert für Lichtzentrale
// @vitest-environment jsdom
import {afterEach, describe, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {SceneEditor, snapshotLights, normalizeScene} from './SceneEditor';
import {PaletteEditor} from './PaletteEditor';
import {App} from './App';
import {Rooms} from './Rooms';
import type {Hass, Light, Palette, Room, Scene} from './types';
const lamp: Light = {entity_id: 'light.test_color', name: 'Testspot', allowed: true, available: true, area_id: 'test_area', area_name: 'Testbereich', on: true, brightness: null, color_mode: 'unknown', supported_color_modes: ['xy', 'color_temp'], xy_color: [.5, .4], color_temp_kelvin: 2700};
const room: Room = {area_id: 'zone:test_area', kind: 'zone', name: 'Testzone', lights: [lamp, {...lamp, entity_id: 'light.test_second', name: 'Testleiste'}, {...lamp, entity_id: 'light.test_onoff', name: 'Teststeckdose', supported_color_modes: ['onoff']}, {...lamp, entity_id: 'switch.test_light', name: 'Testschalter', supported_color_modes: ['onoff']}], on: true, brightness: null, available_count: 4, last_scene_id: 'test_scene'};
const palette: Palette = {id: 'test_palette', name: 'Testglut', category: 'Herbst', bri: 140, tempo: 'slow', builtin: true, preview: ['#ff9a2e', '#ff6a13', '#9e2a2b'], colors: [{x: .5, y: .4}, {x: .6, y: .3}, {x: .6, y: .2}]};
const scene: Scene = {id: 'test_scene', name: 'Testabend', area_id: room.area_id, kind: 'palette', palette_id: palette.id, brightness: 140, dynamic: {enabled: true, interval: 90, transition: 40, tempo: 'slow'}, favorite: true, order: 0, preview: palette.preview};
function mock() {return vi.fn(async (request: {type: string; [key: string]: unknown}): Promise<unknown> => {
  switch (request.type) {
    case 'lichtzentrale/rooms/list': return [room];
    case 'lichtzentrale/lights/list': return room.lights;
    case 'lichtzentrale/palettes/list': return [palette];
    case 'lichtzentrale/scenes/list': return [scene];
    case 'lichtzentrale/dynamic/list': return [{scene_id: scene.id, area_id: room.area_id, name: scene.name}];
    case 'lichtzentrale/hue_scenes/list': return [];
    case 'lichtzentrale/light/replace_options': return {sources: [], targets: []};
    case 'lichtzentrale/adaptive/status': return {available: false};
    case 'lichtzentrale/preview/begin': return {preview_id: 'test_preview', moon_fraction: .37, lights: {'light.test_color': {on: true, brightness: 99, xy: [.4, .4]}}};
    case 'lichtzentrale/preview/commit': return {...(request.scene ? {scene: {...request.scene as object, id: 'test_saved'}} : {palette: {...request.palette as object, id: 'test_saved'}}), applied: [], skipped: []};
    case 'lichtzentrale/palette/save': return {...request.palette as object, id: 'test_saved'};
    default: return {applied: ['light.test_color'], skipped: [], failed: []};
  }
});}
afterEach(() => {cleanup(); vi.useRealTimers();});
async function ready() {await waitFor(() => expect(screen.getByLabelText('Szenenname')).toBeEnabled());}
describe('Stufe 5c Szenen-Editor', () => {
  it('keeps fixed lamp brightness when the overall scene brightness changes and commits latest draft', async () => {
    const callWS = mock(), saved = vi.fn(); render(<SceneEditor hass={{callWS} as Hass} room={room} scene={scene} palettes={[palette]} onClose={vi.fn()} onSaved={saved}/>); await ready();
    fireEvent.change(screen.getByLabelText('Testspot Helligkeit'), {target: {value: 'fixed'}});
    fireEvent.change(screen.getByLabelText('Testspot feste Helligkeit'), {target: {value: '12'}});
    fireEvent.change(screen.getByLabelText('Testleiste Helligkeit'), {target: {value: 'fixed'}});
    fireEvent.change(screen.getByLabelText('Testleiste feste Helligkeit'), {target: {value: '25'}});
    fireEvent.change(screen.getByLabelText('Gesamthelligkeit'), {target: {value: '80'}});
    fireEvent.click(screen.getByRole('button', {name: 'Szene speichern'}));
    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(callWS).toHaveBeenCalledWith(expect.objectContaining({type: 'lichtzentrale/preview/commit', scene: expect.objectContaining({id: scene.id, brightness: 204, lamp_settings: {'light.test_color': {mode: 'cycle', brightness: 31}, 'light.test_second': {mode: 'cycle', brightness: 64}}})}));
    expect(callWS.mock.calls.some(([req]) => req.type.endsWith('scene/save'))).toBe(false);
  });
  it('edits fixed palette/custom/white colors, moon settings and off without dimming onoff targets', async () => {
    const callWS = mock(); render(<SceneEditor hass={{callWS} as Hass} room={room} scene={scene} palettes={[palette]} onClose={vi.fn()} onSaved={vi.fn()}/>); await ready();
    expect(screen.queryByLabelText('Teststeckdose Helligkeit')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Testspot Verhalten'), {target: {value: 'fixed'}});
    fireEvent.click(screen.getByLabelText('Testspot Palettenfarbe 2'));
    expect(screen.getByLabelText('Testspot Palettenfarbe 2')).toHaveAttribute('aria-pressed', 'true');
    fireEvent.change(screen.getByLabelText('Testspot Farbquelle'), {target: {value: 'color'}});
    fireEvent.change(screen.getByLabelText('Testspot eigene Farbe'), {target: {value: '#ff6a13'}});
    fireEvent.change(screen.getByLabelText('Testspot Farbquelle'), {target: {value: 'white'}});
    fireEvent.change(screen.getByLabelText('Testspot Weißton'), {target: {value: '3000'}});
    fireEvent.change(screen.getByLabelText('Testleiste Verhalten'), {target: {value: 'moon'}});
    expect(screen.getByText('☾ Mond heute: 37 %')).toBeVisible();
    expect(screen.getByLabelText('Testleiste Helligkeit bei Neumond')).toHaveValue('10');
    expect(screen.getByLabelText('Testleiste Helligkeit bei Vollmond')).toHaveValue('80');
    fireEvent.click(screen.getByLabelText('Testleiste bei Vollmond langsam atmen'));
    fireEvent.change(screen.getByLabelText('Teststeckdose An / Aus'), {target: {value: 'off'}});
    fireEvent.click(screen.getByRole('button', {name: 'Szene speichern'}));
    await waitFor(() => expect(callWS).toHaveBeenCalledWith(expect.objectContaining({type: 'lichtzentrale/preview/commit', scene: expect.objectContaining({lamp_settings: {'light.test_color': {mode: 'fixed', brightness: null, color_temp_kelvin: 3000}, 'light.test_second': {mode: 'moon', brightness: null, moon: expect.objectContaining({new_brightness: 26, full_brightness: 204, breath: true})}, 'light.test_onoff': {mode: 'off'}}})})));
  });
  it('uses named tempos and reorders only eligible wave lamps with thumb buttons', async () => {
    const callWS = mock(); render(<SceneEditor hass={{callWS} as Hass} room={room} scene={scene} palettes={[palette]} onClose={vi.fn()} onSaved={vi.fn()}/>); await ready();
    fireEvent.change(screen.getByLabelText('Tempo'), {target: {value: 'fast'}}); fireEvent.click(screen.getByLabelText('Welle'));
    fireEvent.click(screen.getByLabelText('Testleiste in Welle nach oben')); fireEvent.click(screen.getByLabelText('Sanft lebendig'));
    expect(screen.getByText('Welle läuft von Testleiste nach Testspot.')).toBeVisible();
    fireEvent.click(screen.getByRole('button', {name: 'Szene speichern'}));
    await waitFor(() => expect(callWS).toHaveBeenCalledWith(expect.objectContaining({type: 'lichtzentrale/preview/commit', scene: expect.objectContaining({wave_order: ['light.test_second', 'light.test_color'], dynamic: {enabled: true, tempo: 'fast', interval: 8, transition: 3, welle: true, gentle: true}})})));
  });
  it('preserves an existing snapshot and explicitly turns an off switch on without color or brightness', async () => {
    const callWS = mock(), snapshot = {...scene, kind: 'snapshot' as const, lights: {'light.test_onoff': {on: false}}, dynamic: {enabled: false, interval: 60, transition: 10}};
    render(<SceneEditor hass={{callWS} as Hass} room={room} scene={snapshot} palettes={[palette]} onClose={vi.fn()} onSaved={vi.fn()}/>); await ready();
    expect(screen.getByLabelText('Grundlage')).toHaveValue('snapshot'); expect(screen.queryByLabelText('Dynamischer Farbwechsel')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Teststeckdose An / Aus'), {target: {value: 'cycle'}});
    fireEvent.click(screen.getByRole('button', {name: 'Szene speichern'}));
    await waitFor(() => expect(callWS).toHaveBeenCalledWith(expect.objectContaining({type: 'lichtzentrale/preview/commit', scene: expect.objectContaining({lights: {'light.test_onoff': {on: true}}})})));
  });
  it('captures a new snapshot on the server and never mistakes unknown brightness for zero', async () => {
    const callWS = mock(); render(<SceneEditor hass={{callWS} as Hass} room={room} palettes={[palette]} onClose={vi.fn()} onSaved={vi.fn()}/>); await ready();
    fireEvent.change(screen.getByLabelText('Szenenname'), {target: {value: 'Testaufnahme'}});
    fireEvent.click(screen.getByRole('button', {name: 'Szene speichern'}));
    await waitFor(() => expect(callWS).toHaveBeenCalledWith(expect.objectContaining({type: 'lichtzentrale/preview/commit', scene: expect.objectContaining({lights: {'light.test_color': {on: true, brightness: 99, xy: [.4, .4]}}})})));
    expect(snapshotLights({...room, lights: [{...lamp, on: false}]})).toEqual({'light.test_color': {on: false}});
    expect(snapshotLights({...room, lights: [lamp]})).toEqual({'light.test_color': {on: true, xy: [.5, .4]}});
  });
  it('normalizes old dimming and moon values after replacement with an onoff-only light', () => {
    const migrated: Scene = {...scene, kind: 'snapshot', lights: {'light.test_onoff': {on: true, brightness: 64, xy: [.4, .4]}}, lamp_settings: {'light.test_onoff': {mode: 'moon', brightness: 31, moon: {new_brightness: 26, full_brightness: 204, new_xy: [.25, .27], full_xy: [.31, .33], breath: true}}}};
    const value = normalizeScene(migrated, room);
    expect(value.lights).toEqual({'light.test_onoff': {on: true}});
    expect(value.lamp_settings).toEqual({'light.test_onoff': {mode: 'fixed', brightness: null}});
    expect(migrated.lights?.['light.test_onoff'].brightness).toBe(64);
  });
  it('returns persistence confirmation with playback warnings instead of inviting a duplicate save', async () => {
    const callWS = mock(), normal = callWS.getMockImplementation()!, saved = vi.fn();
    callWS.mockImplementation(request => request.type.endsWith('preview/commit') ? Promise.resolve({scene, applied: [], skipped: ['light.test_second'], notes: ['Bitte die gespeicherte Szene erneut starten.']}) : normal(request));
    render(<SceneEditor hass={{callWS} as Hass} room={room} scene={scene} palettes={[palette]} onClose={vi.fn()} onSaved={saved}/>); await ready();
    fireEvent.click(screen.getByRole('button', {name: 'Szene speichern'}));
    await waitFor(() => expect(saved).toHaveBeenCalledWith(scene, 'Bitte die gespeicherte Szene erneut starten. 1 Lampe(n) wurden übersprungen.'));
  });
  it('debounces edits and cancels before closing rather than saving or persisting browser state', async () => {
    vi.useFakeTimers(); const callWS = mock(), closed = vi.fn(); render(<SceneEditor hass={{callWS} as Hass} room={room} scene={scene} palettes={[palette]} onClose={closed} onSaved={vi.fn()}/>);
    await act(async () => {});
    fireEvent.change(screen.getByLabelText('Szenenname'), {target: {value: 'Erster Entwurf'}}); fireEvent.change(screen.getByLabelText('Szenenname'), {target: {value: 'Letzter Entwurf'}});
    await act(async () => {await vi.advanceTimersByTimeAsync(350);});
    expect(callWS.mock.calls.filter(([req]) => req.type.endsWith('preview/apply'))).toHaveLength(1);
    expect(callWS).toHaveBeenCalledWith(expect.objectContaining({scene: expect.objectContaining({name: 'Letzter Entwurf'}), sequence: 1}));
    fireEvent.click(screen.getByRole('button', {name: 'Abbrechen'})); await act(async () => {});
    expect(closed).toHaveBeenCalledOnce(); expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/preview/cancel', preview_id: 'test_preview'});
  });
});
describe('Eigene Paletten', () => {
  it('enforces 2–6 colors and saves a new variant without replacing the built-in ID', async () => {
    const callWS = mock(), saved = vi.fn(); render(<PaletteEditor hass={{callWS} as Hass} palette={palette} duplicate onClose={vi.fn()} onSaved={saved}/>);
    expect(screen.getByLabelText('Palettenname')).toHaveValue('Testglut · Eigene Variante');
    fireEvent.click(screen.getByLabelText('Farbe 3 entfernen')); expect(screen.getByLabelText('Farbe 1 entfernen')).toBeDisabled();
    for (let count = 0; count < 4; count++) fireEvent.click(screen.getByRole('button', {name: '+ Farbe hinzufügen'}));
    expect(screen.getByRole('button', {name: '+ Farbe hinzufügen'})).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Farbe 1'), {target: {value: '#ff6a13'}});
    fireEvent.click(screen.getByRole('button', {name: 'Palette speichern'}));
    await waitFor(() => expect(saved).toHaveBeenCalledOnce());
    const request = callWS.mock.calls.find(([req]) => req.type.endsWith('palette/save'))![0];
    expect(request.palette).not.toHaveProperty('id'); expect(request.palette).not.toHaveProperty('builtin');
    expect(request.palette).toMatchObject({preview: ['#ff6a13', '#ff6a13', '#ffc247', '#ffc247', '#ffc247', '#ffc247']});
  });
  it('probes the target and restores it before changing target or closing', async () => {
    vi.useFakeTimers(); const callWS = mock(), closed = vi.fn(); render(<PaletteEditor hass={{callWS} as Hass} palette={{...palette, builtin: false}} onClose={closed} onSaved={vi.fn()}/>); await act(async () => {});
    fireEvent.change(screen.getByLabelText('Raum oder Zone'), {target: {value: room.area_id}}); await act(async () => {await vi.advanceTimersByTimeAsync(350);});
    expect(callWS).toHaveBeenCalledWith(expect.objectContaining({type: 'lichtzentrale/preview/apply', palette: expect.objectContaining({id: palette.id})}));
    expect(screen.getByLabelText('Raum oder Zone')).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Ziel wechseln'})); await act(async () => {});
    expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/preview/cancel', preview_id: 'test_preview'}); expect(screen.getByLabelText('Raum oder Zone')).toBeEnabled();
    fireEvent.click(screen.getByRole('button', {name: 'Abbrechen'})); await act(async () => {}); expect(closed).toHaveBeenCalled();
  });
  it('retains a referenced custom palette and names the scenes that block deletion', async () => {
    const callWS = mock(), normal = callWS.getMockImplementation()!;
    callWS.mockImplementation(request => request.type.endsWith('palettes/list') ? Promise.resolve([{...palette, builtin: false}]) : request.type.endsWith('palette/delete') ? Promise.reject({message: 'Die Palette wird von „Testabend“ verwendet.'}) : normal(request));
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<App hass={{callWS} as Hass}/>); fireEvent.click(screen.getByRole('button', {name: 'Farben'}));
    fireEvent.click(await screen.findByText('Testglut')); fireEvent.click(screen.getByRole('button', {name: 'Palette löschen'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Testabend'); expect(screen.getByRole('button', {name: 'Palette bearbeiten'})).toBeInTheDocument();
    expect(callWS.mock.calls.filter(([req]) => req.type.endsWith('palette/delete'))).toHaveLength(1); confirm.mockRestore();
  });
  it('keeps a failed palette save editable and does not claim success', async () => {
    const callWS = mock(), normal = callWS.getMockImplementation()!, saved = vi.fn(); callWS.mockImplementation(request => request.type.endsWith('palette/save') ? Promise.reject({message: 'Speicher nicht erreichbar'}) : normal(request));
    render(<PaletteEditor hass={{callWS} as Hass} palette={palette} duplicate onClose={vi.fn()} onSaved={saved}/>);
    fireEvent.click(screen.getByRole('button', {name: 'Palette speichern'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Speicher nicht erreichbar'); expect(saved).not.toHaveBeenCalled(); expect(screen.getByRole('button', {name: 'Palette speichern'})).toBeEnabled();
  });
});
describe('Sichere Navigation und Zuhause', () => {
  it('waits for restore before switching tabs and stays in the editor when cancel fails', async () => {
    const callWS = mock(), normal = callWS.getMockImplementation()!; let finish: (value: unknown) => void = () => {};
    callWS.mockImplementation(request => request.type.endsWith('preview/cancel') ? new Promise(resolve => {finish = resolve;}) : normal(request));
    render(<App hass={{callWS} as Hass}/>); fireEvent.click(screen.getByRole('button', {name: 'Farben'}));
    fireEvent.click(await screen.findByRole('button', {name: '+ Neue Palette'}));
    await waitFor(() => expect(within(screen.getByLabelText('Raum oder Zone')).getByText('Testzone')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Raum oder Zone'), {target: {value: room.area_id}});
    await waitFor(() => expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/preview/begin', area_id: room.area_id}));
    fireEvent.click(screen.getByRole('button', {name: 'Zuhause'}));
    expect(screen.getByTestId('palette-editor')).toBeInTheDocument();
    await waitFor(() => expect(callWS.mock.calls.filter(([req]) => req.type.endsWith('preview/cancel'))).toHaveLength(1));
    await act(async () => finish({failed: ['light.test_color']}));
    expect(screen.getByTestId('palette-editor')).toBeInTheDocument(); expect(screen.getByRole('alert')).toHaveTextContent('Abbrechen fehlgeschlagen');
    fireEvent.click(screen.getByRole('button', {name: 'Zuhause'})); await waitFor(() => expect(callWS.mock.calls.filter(([req]) => req.type.endsWith('preview/cancel'))).toHaveLength(2)); await act(async () => finish({applied: [], skipped: [], failed: []}));
    await waitFor(() => expect(screen.queryByTestId('palette-editor')).not.toBeInTheDocument());
  });
  it('shows favorite chips and toggles the live dynamic scene without opening a room', async () => {
    const callWS = mock(); render(<Rooms hass={{callWS} as Hass} detail={false} openRoom={vi.fn()}/>);
    fireEvent.click(await screen.findByRole('button', {name: 'Testabend in Testzone starten'}));
    await waitFor(() => expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/scene/apply', scene_id: scene.id}));
    await waitFor(() => expect(screen.getByRole('button', {name: 'Testabend Dynamik stoppen'})).toBeEnabled());
    fireEvent.click(screen.getByRole('button', {name: 'Testabend Dynamik stoppen'}));
    await waitFor(() => expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/dynamic/stop', area_id: room.area_id}));
    expect(screen.getByText('Testzone Helligkeit: noch unbekannt')).toBeVisible();
  });
});
