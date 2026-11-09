// Geändert für Lichtzentrale
// @vitest-environment jsdom
import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {Zones} from './Zones';
import type {Hass} from './types';
afterEach(cleanup);
function setup() {
  const onSaved = vi.fn();
  const callWS = vi.fn(async (req: {type: string}): Promise<unknown> => req.type.endsWith('zones/list') ? [{id: 'test_zone', name: 'Testzone', entity_ids: ['light.missing_test']}] : req.type.endsWith('lights/list') ? [{entity_id: 'light.fixture', name: 'Testlampe', allowed: true, available: true}] : {});
  render(<Zones hass={{callWS} as Hass} onSaved={onSaved}/>); return {callWS, onSaved};
}
it('preserves missing references with a friendly label when editing', async () => {
  const {callWS} = setup(); fireEvent.click(await screen.findByRole('button', {name: 'Testzone'}));
  expect(screen.getByLabelText('Gespeicherte Lampe nicht gefunden')).toBeChecked();
  expect(document.body.textContent).not.toContain('light.missing_test');
  fireEvent.change(screen.getByLabelText('Zonenname'), {target: {value: 'Neue Testzone'}});
  fireEvent.click(screen.getByRole('button', {name: 'Zone speichern'}));
  await waitFor(() => expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/zone/save', zone: {id: 'test_zone', name: 'Neue Testzone', entity_ids: ['light.missing_test']}}));
});
it('cancels without storing and locks repeated save clicks', async () => {
  const {callWS, onSaved} = setup(); await screen.findByRole('button', {name: 'Testzone'});
  fireEvent.click(screen.getByRole('button', {name: '+ Neue Zone'}));
  fireEvent.change(screen.getByLabelText('Zonenname'), {target: {value: 'Entwurf'}});
  fireEvent.click(screen.getByRole('button', {name: 'Abbrechen'}));
  expect(callWS.mock.calls.some(([req]) => req.type.endsWith('zone/save'))).toBe(false);
  fireEvent.click(screen.getByRole('button', {name: '+ Neue Zone'}));
  expect(screen.getByLabelText('Zonenname')).toHaveValue('');
  fireEvent.change(screen.getByLabelText('Zonenname'), {target: {value: 'Testbereich'}});
  fireEvent.click(screen.getByLabelText('Testlampe'));
  let resolve: (value: unknown) => void = () => {};
  callWS.mockImplementationOnce(() => new Promise(done => {resolve = done;}));
  fireEvent.click(screen.getByRole('button', {name: 'Zone speichern'}));
  fireEvent.click(screen.getByRole('button', {name: 'Zone speichern'}));
  expect(callWS.mock.calls.filter(([req]) => req.type.endsWith('zone/save'))).toHaveLength(1);
  resolve({}); await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
});
it('keeps the draft on save failure', async () => {
  const {callWS} = setup(); fireEvent.click(await screen.findByRole('button', {name: 'Testzone'}));
  callWS.mockRejectedValueOnce(new Error('offline'));
  fireEvent.click(screen.getByRole('button', {name: 'Zone speichern'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('nicht gespeichert');
  expect(screen.getByLabelText('Zonenname')).toHaveValue('Testzone');
});
