// Geändert für Lichtzentrale
// @vitest-environment jsdom
import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {SceneEditor} from './SceneEditor';
import {HueSceneEditor} from './SceneScript';
import {SeasonalSceneEditor, defaultSeasonal} from './SeasonalSceneEditor';
import type {Hass, Light, Room, Scene, Palette} from './types';
const light: Light = {entity_id: 'light.test_filament', name: 'Testfilament', area_id: 'test_area', area_name: 'Testbereich', allowed: true, available: true, supported_color_modes: ['brightness'], effect_list: ['candle', 'sparkle'], on: true, brightness: 140};
const room: Room = {area_id: 'test_area', name: 'Testbereich', lights: [light, {...light, entity_id: 'light.test_onoff', name: 'Testschalter', supported_color_modes: ['onoff']}], on: true, brightness: 140, available_count: 2};
const palette: Palette = {id: 'test_palette', name: 'Testglut', category: 'Herbst', bri: 140, colors: [{x: .5, y: .4}, {x: .4, y: .4}], preview: ['#ff9a2e', '#ff6a13']};
const scene: Scene = {id: 'test_scene', name: 'Testszene', area_id: room.area_id, kind: 'palette', palette_id: palette.id, favorite: true, order: 2, preview: palette.preview};
const scripts = [{entity_id: 'script.test_music', name: 'Testmusik', available: true}];
const api = () => vi.fn(async (request: {type: string; [key: string]: unknown}): Promise<unknown> => {
  if (request.type === 'lichtzentrale/scripts/list') return scripts;
  if (request.type === 'lichtzentrale/preview/begin') return {preview_id: 'test_preview'};
  if (request.type === 'lichtzentrale/preview/commit') return {scene: request.scene};
  return {applied: [], skipped: []};
});
afterEach(cleanup);
it.each(['palette', 'snapshot'] as const)('edits a current Filament effect and script for %s without dropping settings', async kind => {
  const callWS = api(); render(<SceneEditor hass={{callWS} as Hass} room={room} palettes={[palette]} scene={{...scene, kind}} onSaved={vi.fn()} onClose={vi.fn()}/>);
  await waitFor(() => expect(screen.getByLabelText('Testfilament Effekt')).toBeEnabled());
  expect(screen.queryByLabelText('Testschalter Effekt')).not.toBeInTheDocument();
  expect(within(screen.getByLabelText('Testfilament Effekt')).getByRole('option', {name: 'Kerze'})).toHaveValue('candle');
  fireEvent.change(screen.getByLabelText('Testfilament Effekt'), {target: {value: 'candle'}});
  fireEvent.change(screen.getByLabelText('Testfilament Verhalten'), {target: {value: 'fixed'}});
  fireEvent.change(screen.getByLabelText('Testfilament Helligkeit'), {target: {value: 'fixed'}});
  fireEvent.change(screen.getByLabelText('Skript beim Szenenstart'), {target: {value: scripts[0].entity_id}});
  fireEvent.click(screen.getByRole('button', {name: 'Szene speichern'}));
  await waitFor(() => expect(callWS).toHaveBeenCalledWith(expect.objectContaining({type: 'lichtzentrale/preview/commit', scene: expect.objectContaining({start_script: scripts[0].entity_id, lamp_settings: {[light.entity_id]: expect.objectContaining({effect: 'candle', mode: 'fixed'})}})})));
  expect(callWS.mock.calls.some(([request]) => request.type.includes('script.turn_on'))).toBe(false);
});
it('retains a stale effect for repair and allows explicit removal including on/off replacements', async () => {
  const callWS = api(); render(<SceneEditor hass={{callWS} as Hass} room={room} palettes={[palette]} scene={{...scene, lamp_settings: {'light.test_onoff': {mode: 'fixed', effect: 'cosmos'}}}} onSaved={vi.fn()} onClose={vi.fn()}/>);
  await waitFor(() => expect(screen.getByLabelText('Szenenname')).toBeEnabled());
  expect(screen.getByLabelText('Testschalter Effekt')).toHaveValue('cosmos'); expect(screen.getByRole('button', {name: 'Szene speichern'})).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Testschalter Effekt'), {target: {value: ''}});
  fireEvent.click(screen.getByRole('button', {name: 'Szene speichern'}));
  await waitFor(() => expect(callWS).toHaveBeenCalledWith(expect.objectContaining({type: 'lichtzentrale/preview/commit', scene: expect.objectContaining({lamp_settings: {'light.test_onoff': {mode: 'fixed', brightness: null}}})})));
});
it('preserves script and effect when switching palette to snapshot', async () => {
  const callWS = api(); render(<SceneEditor hass={{callWS} as Hass} room={room} palettes={[palette]} scene={{...scene, start_script: scripts[0].entity_id, lamp_settings: {[light.entity_id]: {mode: 'fixed', palette_index: 0, effect: 'sparkle'}}}} onSaved={vi.fn()} onClose={vi.fn()}/>);
  await waitFor(() => expect(screen.getByRole('button', {name: 'Szene speichern'})).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Grundlage'), {target: {value: 'snapshot'}}); fireEvent.click(screen.getByRole('button', {name: 'Szene speichern'}));
  await waitFor(() => expect(callWS).toHaveBeenCalledWith(expect.objectContaining({type: 'lichtzentrale/preview/commit', scene: expect.objectContaining({kind: 'snapshot', start_script: scripts[0].entity_id, lamp_settings: {[light.entity_id]: expect.objectContaining({effect: 'sparkle', xy: [.5, .4]})}})})));
});
it('keeps missing script visible until explicitly cleared and preserves Hue metadata', async () => {
  const callWS = api(); render(<HueSceneEditor hass={{callWS} as Hass} scene={{...scene, kind: 'hue', hue_scene: 'scene.test_hue', start_script: 'script.test_deleted'}} onClose={vi.fn()} onSaved={vi.fn()}/>);
  await screen.findByText(/Das gespeicherte Skript wurde nicht gefunden/);
  expect(screen.getByRole('button', {name: 'Szene speichern'})).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Skript beim Szenenstart'), {target: {value: ''}}); fireEvent.click(screen.getByRole('button', {name: 'Szene speichern'}));
  await waitFor(() => expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/scene/save', scene: {...scene, kind: 'hue', hue_scene: 'scene.test_hue', start_script: null}}));
});
it('shows script catalogue failures, retries, and does not save selected scripts before verification', async () => {
  const callWS = api(); callWS.mockRejectedValueOnce(new Error('Testverbindung unterbrochen'));
  render(<HueSceneEditor hass={{callWS} as Hass} scene={{...scene, kind: 'hue', start_script: scripts[0].entity_id}} onClose={vi.fn()} onSaved={vi.fn()}/>);
  fireEvent.click(await screen.findByRole('button', {name: 'Skripte erneut laden'}));
  await waitFor(() => expect(screen.getByRole('button', {name: 'Szene speichern'})).toBeEnabled());
});
it('saves a seasonal wrapper script while preserving season configuration', async () => {
  const callWS = api(), seasonal = {...scene, kind: 'seasonal' as const, seasonal: {...defaultSeasonal(), scenes: {...defaultSeasonal().scenes, autumn: scene.id}}};
  render(<SeasonalSceneEditor hass={{callWS} as Hass} room={room} scenes={[scene]} scene={seasonal} onClose={vi.fn()} onSaved={vi.fn()}/>);
  await screen.findByRole('option', {name: 'Testmusik'}); fireEvent.change(screen.getByLabelText('Skript beim Szenenstart'), {target: {value: scripts[0].entity_id}});
  fireEvent.click(screen.getByRole('button', {name: 'Jahreszeiten-Szene speichern'}));
  await waitFor(() => expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/scene/save', scene: {...seasonal, start_script: scripts[0].entity_id}}));
});
