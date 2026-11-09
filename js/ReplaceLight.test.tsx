// Geändert für Lichtzentrale
// @vitest-environment jsdom
import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {ReplaceLight} from './ReplaceLight';
import type {Hass} from './types';

afterEach(cleanup);
const oldId = 'light.fixture_old', newId = 'light.fixture_new';
const preview = {old_entity_id: oldId, new_entity_id: newId, source_name: 'Alte Testlampe', target_name: 'Neue Testlampe', preview_token: 'current-token', can_replace: true, entries: [{kind: 'scenes', name: 'Testszene', count: 2}], warnings: ['Gespeicherte Farben bleiben erhalten.'], conflicts: []};
function setup() {
  const callWS = vi.fn(async (request: {type: string}): Promise<unknown> => {
    if (request.type.endsWith('replace_options')) return {sources: [{entity_id: oldId, name: 'Alte Testlampe', available: false}], targets: [{entity_id: newId, name: 'Neue Testlampe', available: true}, {entity_id: 'switch.fixture_offline', name: 'Testschalter', available: false, domain: 'switch'}]};
    if (request.type.endsWith('replace_preview')) return preview;
    return {...preview, replaced: true};
  });
  const view = render(<ReplaceLight hass={{callWS} as Hass}/>);
  return {callWS, ...view};
}
async function select() {
  fireEvent.change(await screen.findByLabelText('Bisherige Lampe'), {target: {value: oldId}});
  fireEvent.change(screen.getByLabelText('Neue Lampe'), {target: {value: newId}});
}
it('shows read-only impact preview and only saves after explicit confirmation', async () => {
  const {callWS} = setup(); await select();
  expect(screen.getByRole('option', {name: 'Testschalter · Nur An/Aus · Nicht verfügbar'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button', {name: 'Betroffene Einträge prüfen'}));
  expect(await screen.findByText('Alte Testlampe → Neue Testlampe')).toBeVisible();
  expect(screen.getByText('Testszene · 2 Verweise')).toBeVisible();
  expect(callWS.mock.calls.some(([request]) => request.type === 'lichtzentrale/light/replace')).toBe(false);
  expect(document.body.textContent).not.toContain('light.fixture');
  fireEvent.click(screen.getByRole('button', {name: 'Diese Ersetzung bestätigen'}));
  await screen.findByRole('status');
  expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/light/replace', old_entity_id: oldId, new_entity_id: newId, preview_token: 'current-token'});
});
it('cancels without saving and changing a target invalidates its preview', async () => {
  const {callWS} = setup(); await select();
  fireEvent.click(screen.getByRole('button', {name: 'Betroffene Einträge prüfen'}));
  fireEvent.click(await screen.findByRole('button', {name: 'Abbrechen'}));
  expect(screen.queryByRole('button', {name: 'Diese Ersetzung bestätigen'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', {name: 'Betroffene Einträge prüfen'}));
  await screen.findByRole('button', {name: 'Abbrechen'});
  fireEvent.change(screen.getByLabelText('Neue Lampe'), {target: {value: ''}});
  expect(screen.queryByRole('button', {name: 'Diese Ersetzung bestätigen'})).not.toBeInTheDocument();
  expect(callWS.mock.calls.some(([request]) => request.type === 'lichtzentrale/light/replace')).toBe(false);
});
it('blocks conflicting destination values and shows the server explanation', async () => {
  const {callWS} = setup(); await select();
  callWS.mockResolvedValueOnce({...preview, can_replace: false, conflicts: ['Testszene: Unterschiedliche gespeicherte Lampenwerte.']});
  fireEvent.click(screen.getByRole('button', {name: 'Betroffene Einträge prüfen'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Unterschiedliche gespeicherte Lampenwerte');
  expect(screen.getByRole('button', {name: 'Diese Ersetzung bestätigen'})).toBeDisabled();
});
it('locks repeated confirmation and requires a new preview after stale or failed save', async () => {
  const {callWS} = setup(); await select();
  fireEvent.click(screen.getByRole('button', {name: 'Betroffene Einträge prüfen'}));
  const confirm = await screen.findByRole('button', {name: 'Diese Ersetzung bestätigen'});
  let reject: (error: Error) => void = () => {};
  callWS.mockImplementationOnce(() => new Promise((_, fail) => {reject = fail;}));
  fireEvent.click(confirm); fireEvent.click(confirm);
  expect(callWS.mock.calls.filter(([request]) => request.type === 'lichtzentrale/light/replace')).toHaveLength(1);
  reject(new Error('Die Vorschau ist nicht mehr aktuell. Bitte neu prüfen.'));
  expect(await screen.findByRole('alert')).toHaveTextContent('nicht mehr aktuell');
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', {name: 'Diese Ersetzung bestätigen'})).not.toBeInTheDocument();
  expect(screen.getByLabelText('Bisherige Lampe')).toHaveValue(oldId);
});
it('does not accept an unconfirmed server result or mismatched preview', async () => {
  const {callWS} = setup(); await select();
  callWS.mockResolvedValueOnce({...preview, new_entity_id: 'light.fixture_other'});
  fireEvent.click(screen.getByRole('button', {name: 'Betroffene Einträge prüfen'}));
  await waitFor(() => expect(screen.getByRole('button', {name: 'Betroffene Einträge prüfen'})).toBeEnabled());
  expect(screen.queryByRole('button', {name: 'Diese Ersetzung bestätigen'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', {name: 'Betroffene Einträge prüfen'}));
  await screen.findByRole('button', {name: 'Diese Ersetzung bestätigen'});
  callWS.mockResolvedValueOnce({...preview, replaced: false});
  fireEvent.click(screen.getByRole('button', {name: 'Diese Ersetzung bestätigen'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('nicht bestätigt');
});
it('ignores late previews after leaving the component', async () => {
  const {callWS, unmount} = setup(); await select();
  let resolve: (value: unknown) => void = () => {};
  callWS.mockImplementationOnce(() => new Promise(done => {resolve = done;}));
  fireEvent.click(screen.getByRole('button', {name: 'Betroffene Einträge prüfen'}));
  unmount(); resolve(preview);
  await Promise.resolve();
  expect(callWS.mock.calls.some(([request]) => request.type === 'lichtzentrale/light/replace')).toBe(false);
});
it('shows a recoverable error instead of crashing when server options are malformed', async () => {
  render(<ReplaceLight hass={{callWS: vi.fn(async () => [])} as Hass}/>);
  expect(await screen.findByRole('alert')).toHaveTextContent('Lampen konnten nicht geladen werden');
  expect(screen.queryByRole('button', {name: 'Diese Ersetzung bestätigen'})).not.toBeInTheDocument();
});
it('does not accept an incomplete preview', async () => {
  const {callWS} = setup(); await select();
  callWS.mockResolvedValueOnce({can_replace: true});
  fireEvent.click(screen.getByRole('button', {name: 'Betroffene Einträge prüfen'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('unvollständig');
});
