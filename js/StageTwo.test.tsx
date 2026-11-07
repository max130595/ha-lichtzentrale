// Geändert für Lichtzentrale
// @vitest-environment jsdom
import {afterEach, describe, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {RoomPalette} from './RoomPalette';
import {RuntimeControls} from './RuntimeControls';
import type {Hass, Palette} from './types';
const palette: Palette = {id: 'test_palette', name: 'Testfarben', category: 'Test', bri: 120, colors: [], preview: ['#abcdef']};
const room = {area_id: 'test_area', name: 'Testraum', available_count: 1, lights: [{entity_id: 'light.test_fixture', allowed: true}, {entity_id: 'light.test_denied', allowed: false}]};
const adaptive = {available: true, rooms: [{area_id: room.area_id, switch_entity_id: 'switch.test_adaptive', enabled: true, available: true, default_on: 'last'}], switches: [{entity_id: 'switch.test_adaptive', name: 'Testautomatik', available: true}]};
function mock() {return vi.fn(async (request: {type: string; [key: string]: unknown}): Promise<unknown> => {
  if (request.type.endsWith('rooms/list')) return [room];
  if (request.type.endsWith('adaptive/status')) return adaptive;
  if (request.type.endsWith('dynamic/list')) return [];
  if (request.type.endsWith('scene/save')) return {...request.scene as object, id: 'test_saved'};
  return {applied: ['light.test_fixture'], skipped: [], failed: []};
});}
afterEach(() => {cleanup(); vi.useRealTimers();});
async function selectRoom() {await waitFor(() => expect(screen.getByLabelText('Zielraum')).toBeEnabled()); fireEvent.change(screen.getByLabelText('Zielraum'), {target: {value: room.area_id}});}
describe('Stufe 2 Galerie', () => {
  it('applies static room palette only to approved targets', async () => {
    const callWS = mock(); render(<RoomPalette hass={{callWS} as Hass} palette={palette}/>); await selectRoom();
    fireEvent.click(screen.getByRole('button', {name: 'Im gewählten Raum anwenden'}));
    await waitFor(() => expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/palette/apply', palette_id: palette.id, entity_ids: ['light.test_fixture'], brightness: 120, transition: 10}));
  });
  it('saves dynamic palette then starts by saved ID and validates timing', async () => {
    const callWS = mock(); render(<RoomPalette hass={{callWS} as Hass} palette={palette}/>); await selectRoom();
    fireEvent.click(screen.getByLabelText('Dynamischer Farbwechsel'));
    expect(screen.getByLabelText('Als Szene im Raum speichern')).toBeChecked();
    fireEvent.change(screen.getByLabelText('Farbwechsel alle (Sekunden)'), {target: {value: '5'}});
    expect(screen.getByRole('button', {name: 'Szene speichern und anwenden'})).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Übergangszeit (Sekunden)'), {target: {value: '3'}});
    fireEvent.click(screen.getByRole('button', {name: 'Szene speichern und anwenden'}));
    await waitFor(() => expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/scene/apply', scene_id: 'test_saved'}));
    expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/scene/save', scene: {name: palette.name, area_id: room.area_id, kind: 'palette', palette_id: palette.id, brightness: 120, dynamic: {enabled: true, interval: 5, transition: 3}}});
  });
  it('reuses saved scene after an apply failure instead of duplicating it', async () => {
    const callWS = mock(); const normal = callWS.getMockImplementation()!;
    callWS.mockImplementation(async req => {if (req.type.endsWith('scene/apply')) throw new Error('Testfehler'); return normal(req);});
    render(<RoomPalette hass={{callWS} as Hass} palette={palette}/>); await selectRoom(); fireEvent.click(screen.getByLabelText('Dynamischer Farbwechsel'));
    fireEvent.click(screen.getByRole('button', {name: 'Szene speichern und anwenden'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Die Szene ist gespeichert.');
    fireEvent.click(screen.getByRole('button', {name: 'Szene speichern und anwenden'}));
    await waitFor(() => expect(callWS.mock.calls.filter(([req]) => req.type.endsWith('scene/apply'))).toHaveLength(2));
    expect(callWS.mock.calls.filter(([req]) => req.type.endsWith('scene/save'))).toHaveLength(1);
  });
  it('does not apply a newly saved scene after unmount', async () => {
    const callWS = mock(); const normal = callWS.getMockImplementation()!; let resolve: (value: unknown) => void = () => {};
    callWS.mockImplementation(req => req.type.endsWith('scene/save') ? new Promise(done => {resolve = done;}) : normal(req));
    render(<RoomPalette hass={{callWS} as Hass} palette={palette}/>); await selectRoom(); fireEvent.click(screen.getByLabelText('Dynamischer Farbwechsel'));
    const button = screen.getByRole('button', {name: 'Szene speichern und anwenden'}); fireEvent.click(button); fireEvent.click(button);
    expect(callWS.mock.calls.filter(([req]) => req.type.endsWith('scene/save'))).toHaveLength(1);
    cleanup(); await act(async () => resolve({id: 'test_saved'}));
    expect(callWS.mock.calls.filter(([req]) => req.type.endsWith('scene/apply'))).toHaveLength(0);
  });
});
describe('Laufende Dynamik und Adaptive Lighting', () => {
  it('hides optional controls when Adaptive Lighting is absent', async () => {
    const callWS = vi.fn().mockResolvedValue({available: false, rooms: [], switches: []});
    render(<RuntimeControls hass={{callWS}} area={room.area_id}/>);
    await waitFor(() => expect(callWS).toHaveBeenCalledTimes(2)); expect(screen.queryByText('Natürliches Licht')).not.toBeInTheDocument();
  });
  it('shows and stops the current room only', async () => {
    const callWS = mock(); const normal = callWS.getMockImplementation()!;
    callWS.mockImplementation(req => req.type.endsWith('dynamic/list') ? Promise.resolve([{scene_id: 'test_scene', area_id: room.area_id, name: 'Testdynamik', interval: 60, transition: 10}, {scene_id: 'other', area_id: 'other_area', name: 'Andere Dynamik'}]) : normal(req));
    render(<RuntimeControls hass={{callWS} as Hass} area={room.area_id}/>);
    fireEvent.click(await screen.findByRole('button', {name: 'Dynamik stoppen'}));
    expect(screen.queryByText('Andere Dynamik')).not.toBeInTheDocument();
    await waitFor(() => expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/dynamic/stop', area_id: room.area_id}));
  });
  it('configures natural light activation and default-on server-side', async () => {
    const callWS = mock(); render(<RuntimeControls hass={{callWS} as Hass} area={room.area_id}/>);
    fireEvent.click(await screen.findByLabelText('Natürliches Licht aktiv'));
    await waitFor(() => expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/adaptive/set', area_id: room.area_id, enabled: false}));
    await waitFor(() => expect(screen.getByLabelText('Beim Einschalten natürliches Licht starten')).toBeEnabled());
    fireEvent.click(screen.getByLabelText('Beim Einschalten natürliches Licht starten'));
    await waitFor(() => expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/adaptive/set', area_id: room.area_id, default_on: 'adaptive'}));
  });
  it('ignores obsolete status responses when the selected room changes', async () => {
    let resolve: (value: unknown) => void = () => {}; const callWS = mock(); const normal = callWS.getMockImplementation()!; let first = true;
    callWS.mockImplementation(req => {if (req.type.endsWith('adaptive/status') && first) {first = false; return new Promise(done => {resolve = done;});} return normal(req);});
    const view = render(<RuntimeControls hass={{callWS} as Hass} area="old_area"/>);
    view.rerender(<RuntimeControls hass={{callWS} as Hass} area={room.area_id}/>);
    await screen.findByLabelText('Natürliches Licht aktiv');
    await act(async () => resolve({available: false, rooms: [], switches: []}));
    expect(screen.getByLabelText('Natürliches Licht aktiv')).toBeChecked();
  });
  it('releases the mutation lock when a revision refresh happens while saving', async () => {
    let resolve: (value: unknown) => void = () => {}; const callWS = mock(); const normal = callWS.getMockImplementation()!;
    callWS.mockImplementation(req => req.type.endsWith('adaptive/set') ? new Promise(done => {resolve = done;}) : normal(req));
    const view = render(<RuntimeControls hass={{callWS} as Hass} area={room.area_id} revision={0}/>);
    fireEvent.click(await screen.findByLabelText('Natürliches Licht aktiv'));
    expect(screen.getByLabelText('Natürliches Licht aktiv')).toBeDisabled();
    view.rerender(<RuntimeControls hass={{callWS} as Hass} area={room.area_id} revision={1}/>);
    await act(async () => resolve(adaptive));
    await waitFor(() => expect(screen.getByLabelText('Natürliches Licht aktiv')).toBeEnabled());
    fireEvent.click(screen.getByLabelText('Natürliches Licht aktiv'));
    expect(callWS.mock.calls.filter(([req]) => req.type.endsWith('adaptive/set'))).toHaveLength(2);
  });
  it('shows mapping reasons and Home Assistant error details', async () => {
    const callWS = mock(); const normal = callWS.getMockImplementation()!;
    callWS.mockImplementation(async req => {
      if (req.type.endsWith('adaptive/status')) return {...adaptive, rooms: [{...adaptive.rooms[0], reason: 'Testzuordnung prüfen'}]};
      if (req.type.endsWith('adaptive/set')) throw {message: 'Die Zuordnung enthält fremde Lampen.'};
      return normal(req);
    });
    render(<RuntimeControls hass={{callWS} as Hass} area={room.area_id}/>);
    await screen.findByText('Testzuordnung prüfen');
    fireEvent.click(screen.getByLabelText('Natürliches Licht aktiv'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Die Zuordnung enthält fremde Lampen.');
    expect(screen.getByLabelText('Adaptive Lighting zuordnen')).toBeEnabled();
  });
  it('clears polling timers on unmount', async () => {
    vi.useFakeTimers(); const callWS = mock(); const view = render(<RuntimeControls hass={{callWS} as Hass} area={room.area_id}/>);
    await act(async () => {await Promise.resolve();}); expect(callWS).toHaveBeenCalledTimes(2);
    view.unmount(); await act(async () => {vi.advanceTimersByTime(30000);}); expect(callWS).toHaveBeenCalledTimes(2);
  });
});
