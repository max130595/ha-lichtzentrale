// Geändert für Lichtzentrale
// @vitest-environment jsdom
import {useState} from 'react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {RoomPositions, distributionLabel} from './RoomPositions';
import {SceneEditor} from './SceneEditor';
import {RoomPalette} from './RoomPalette';
import {RuntimeControls} from './RuntimeControls';
import type {Hass, Palette, Position, Room} from './types';
const room: Room = {area_id: 'test_area', name: 'Testraum', on: false, brightness: null, available_count: 1, lights: [
  {entity_id: 'light.test_one', name: 'Testlampe eins', area_id: 'test_area', area_name: 'Testraum', allowed: true, available: true},
  {entity_id: 'light.test_two', name: 'Testlampe zwei', area_id: 'test_area', area_name: 'Testraum', allowed: true, available: false},
  {entity_id: 'light.test_denied', name: 'Nicht freigegeben', area_id: 'test_area', area_name: 'Testraum', allowed: false, available: true},
]};
function Editor({hass}: {hass: Hass}) {
  const [positions, setPositions] = useState<Record<string, Position>>({});
  return <RoomPositions hass={hass} room={{...room, positions}} onSaved={(id, position) => setPositions(old => {const next = {...old}; if (position) next[id] = position; else delete next[id]; return next;})}/>;
}
afterEach(cleanup);
describe('Lampenpositionen', () => {
  it('requires a selected approved lamp and persists coordinates, height and removal', async () => {
    const callWS = vi.fn(async (request: Record<string, unknown>) => request.position);
    render(<Editor hass={{callWS} as Hass}/>);
    expect(screen.getByRole('button', {name: 'vorne links'})).toBeDisabled();
    expect(screen.queryByText('Nicht freigegeben')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: /Testlampe eins/}));
    fireEvent.change(screen.getByLabelText('Höhe der Lampe'), {target: {value: 'boden'}});
    expect(callWS).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: 'hinten rechts'}));
    await screen.findByText('Position für Testlampe eins gespeichert.');
    expect(callWS).toHaveBeenLastCalledWith({type: 'lichtzentrale/room/position', area_id: room.area_id, entity_id: 'light.test_one', position: {cell: [2, 2], height: 'boden'}});
    expect(screen.getByRole('button', {name: 'hinten rechts'})).toHaveAttribute('aria-pressed', 'true');
    expect(within(screen.getByRole('button', {name: 'hinten rechts'})).getByText('Testlampe eins')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Höhe der Lampe'), {target: {value: 'hintergrund'}});
    await waitFor(() => expect(screen.getByLabelText('Höhe der Lampe')).toHaveValue('hintergrund'));
    expect(callWS).toHaveBeenLastCalledWith(expect.objectContaining({position: {cell: [2, 2], height: 'hintergrund'}}));
    fireEvent.click(screen.getByRole('button', {name: 'Position entfernen'}));
    await screen.findByText('Position für Testlampe eins entfernt.');
    expect(callWS).toHaveBeenLastCalledWith(expect.objectContaining({position: null}));
    expect(screen.getByRole('button', {name: 'hinten rechts'})).toHaveAttribute('aria-pressed', 'false');
  });
  it('keeps failed writes unassigned and unlocks retry; offline lamps can be arranged', async () => {
    const callWS = vi.fn().mockRejectedValueOnce({message: 'Speicherfehler'}).mockResolvedValue({cell: [0, 0], height: 'moebel'});
    render(<Editor hass={{callWS}}/>);
    fireEvent.click(screen.getByRole('button', {name: /Testlampe zwei/}));
    fireEvent.click(screen.getByRole('button', {name: 'vorne links'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Speicherfehler');
    expect(screen.getByRole('button', {name: 'vorne links'})).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(screen.getByRole('button', {name: 'vorne links'}));
    await screen.findByText('Position für Testlampe zwei gespeichert.');
    expect(callWS).toHaveBeenCalledTimes(2);
  });
  it('locks repeated taps and ignores an old room write after navigation', async () => {
    let finish: (value: Position) => void = () => {};
    const callWS = vi.fn(() => new Promise<Position>(resolve => {finish = resolve;})), onSaved = vi.fn();
    const view = render(<RoomPositions hass={{callWS} as Hass} room={room} onSaved={onSaved}/>);
    fireEvent.click(screen.getByRole('button', {name: /Testlampe eins/}));
    const cell = screen.getByRole('button', {name: 'vorne links'});
    fireEvent.click(cell); fireEvent.click(cell);
    expect(callWS).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText('Höhe der Lampe')).toBeDisabled();
    view.rerender(<RoomPositions hass={{callWS} as Hass} room={{...room, area_id: 'test_other'}} onSaved={onSaved}/>);
    await act(async () => finish({cell: [0, 0], height: 'boden'}));
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.queryByText('Position für Testlampe eins gespeichert.')).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'vorne links'})).toBeDisabled();
    expect(screen.getByRole('button', {name: /Testlampe eins/})).toBeEnabled();
  });
  it('retains a position after removal fails and reports busy state to the room', async () => {
    const onSaved = vi.fn(), onBusy = vi.fn(), callWS = vi.fn().mockRejectedValue(new Error('Speicherfehler'));
    render(<RoomPositions hass={{callWS}} room={{...room, positions: {'light.test_one': {cell: [0, 0], height: 'boden'}}}} onSaved={onSaved} onBusy={onBusy}/>);
    fireEvent.click(screen.getByRole('button', {name: /Testlampe eins/}));
    fireEvent.click(screen.getByRole('button', {name: 'Position entfernen'}));
    expect(onBusy).toHaveBeenCalledWith(true);
    await screen.findByRole('alert');
    expect(onBusy).toHaveBeenLastCalledWith(false);
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.getByRole('button', {name: 'vorne links'})).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', {name: 'Position entfernen'})).toBeEnabled();
  });
  it('shows multiple occupants and preserves the confirmed height after a failed height write', async () => {
    const positions: Record<string, Position> = {'light.test_one': {cell: [1, 1], height: 'decke'}, 'light.test_two': {cell: [1, 1], height: 'boden'}};
    const callWS = vi.fn().mockRejectedValue(new Error('Testfehler'));
    render(<RoomPositions hass={{callWS}} room={{...room, positions}} onSaved={vi.fn()}/>);
    expect(within(screen.getByRole('button', {name: 'mitte mitte'})).getAllByText(/Testlampe/)).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', {name: /Testlampe eins Decke/}));
    fireEvent.change(screen.getByLabelText('Höhe der Lampe'), {target: {value: 'boden'}});
    await screen.findByRole('alert');
    expect(screen.getByLabelText('Höhe der Lampe')).toHaveValue('decke');
  });
});
const palette: Palette = {id: 'test_palette', name: 'Testfarben', category: 'Test', bri: 120, colors: [], preview: []};
function api() {return vi.fn(async (request: Record<string, unknown>) => {
  if (request.type === 'lichtzentrale/rooms/list') return [room];
  if (request.type === 'lichtzentrale/dynamic/list') return [];
  if (request.type === 'lichtzentrale/adaptive/status') return {available: false};
  if (request.type === 'lichtzentrale/preview/begin') return {preview_id: 'test_preview'};
  if (request.type === 'lichtzentrale/preview/commit') return {scene: {...request.scene as object, id: 'test_scene'}};
  if (request.type === 'lichtzentrale/scene/save') return {...request.scene as object, id: 'test_scene'};
  return {stopped: false, applied: ['light.test_one'], skipped: ['light.test_off'], failed: ['light.test_two']};
});}
describe('Räumliche Paletten und Hue-Stopp', () => {
  it('sends spatial distribution on direct static applications', async () => {
    const callWS = api(); render(<RoomPalette hass={{callWS} as Hass} palette={palette}/>);
    await waitFor(() => expect(screen.getByLabelText('Raum oder Zone')).toBeEnabled());
    fireEvent.change(screen.getByLabelText('Raum oder Zone'), {target: {value: room.area_id}}); fireEvent.click(screen.getByText('Mehr Optionen'));
    expect(screen.queryByLabelText('Welle durch den Raum')).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText('Farbverteilung')).toBeEnabled());
    fireEvent.change(screen.getByLabelText('Farbverteilung'), {target: {value: 'hoehe'}});
    fireEvent.click(screen.getByRole('button', {name: 'Im gewählten Raum anwenden'}));
    await waitFor(() => expect(callWS).toHaveBeenCalledWith(expect.objectContaining({type: 'lichtzentrale/palette/apply', layout_area_id: room.area_id, verteilung: 'hoehe'})));
    expect(await screen.findByText(/1 fehlgeschlagen/)).toBeInTheDocument();
  });
  it('chooses an explicit wave axis in the scene editor and clears wave on static scenes', async () => {
    const callWS = api(); render(<SceneEditor hass={{callWS} as Hass} room={room} palette={palette} palettes={[palette]} onClose={vi.fn()} onSaved={vi.fn()}/>);
    await waitFor(() => expect(screen.getByLabelText('Dynamischer Farbwechsel')).toBeEnabled());
    fireEvent.click(screen.getByLabelText('Dynamischer Farbwechsel')); fireEvent.click(screen.getByLabelText('Welle'));
    fireEvent.click(screen.getByText('Mehr Optionen'));
    expect(screen.getByLabelText('Farbverteilung')).toHaveValue('verlauf_links_rechts');
    expect(screen.getByRole('option', {name: 'Zufällig'})).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Farbverteilung'), {target: {value: 'verlauf_vorne_hinten'}});
    fireEvent.click(screen.getByLabelText('Dynamischer Farbwechsel'));
    fireEvent.click(screen.getByRole('button', {name: 'Szene speichern'}));
    await waitFor(() => expect(callWS).toHaveBeenCalledWith(expect.objectContaining({type: 'lichtzentrale/preview/commit', scene: expect.objectContaining({verteilung: 'verlauf_vorne_hinten', dynamic: expect.objectContaining({enabled: false, welle: false})})})));
    expect(distributionLabel()).toBe('Zufällig');
  });
  it('clears wave when disabling dynamics so re-enabling random distribution stays valid', async () => {
    const callWS = api(); render(<SceneEditor hass={{callWS} as Hass} room={room} palette={palette} palettes={[palette]} onClose={vi.fn()} onSaved={vi.fn()}/>);
    await waitFor(() => expect(screen.getByLabelText('Dynamischer Farbwechsel')).toBeEnabled());
    fireEvent.click(screen.getByLabelText('Dynamischer Farbwechsel')); fireEvent.click(screen.getByLabelText('Welle'));
    fireEvent.click(screen.getByLabelText('Dynamischer Farbwechsel'));
    fireEvent.click(screen.getByText('Mehr Optionen'));
    fireEvent.change(screen.getByLabelText('Farbverteilung'), {target: {value: 'zufall'}});
    fireEvent.click(screen.getByLabelText('Dynamischer Farbwechsel'));
    expect(screen.getByLabelText('Welle')).not.toBeChecked();
    fireEvent.click(screen.getByRole('button', {name: 'Szene speichern'}));
    await waitFor(() => expect(callWS).toHaveBeenCalledWith(expect.objectContaining({type: 'lichtzentrale/preview/commit', scene: expect.objectContaining({verteilung: 'zufall', dynamic: expect.objectContaining({enabled: true, welle: false})})})));
  });
  it('stops Hue without any local run and reports partial failure without claiming all stopped', async () => {
    const callWS = api(); render(<RuntimeControls hass={{callWS} as Hass} area={room.area_id}/>);
    fireEvent.click(screen.getByRole('button', {name: 'Dynamik stoppen'}));
    await waitFor(() => expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/dynamic/stop', area_id: room.area_id}));
    expect(await screen.findByRole('status')).toHaveTextContent('1 Lampe(n) festgesetzt. 1 übersprungen. 1 fehlgeschlagen. Bei diesen Lampen kann die Dynamik weiterlaufen.');
  });
});
