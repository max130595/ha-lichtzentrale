// Geändert für Lichtzentrale
// @vitest-environment jsdom
import {useState} from 'react';
import {afterEach, expect, it} from 'vitest';
import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {BindingTimeWindows, bindingTimeWindowsValid, newBindingTimeWindow} from './BindingTimeWindows';
import type {BindingTimeWindow, Scene} from './types';

afterEach(cleanup);
const scenes: Scene[] = [{id: 'fixture_scene', name: 'Testszene', area_id: 'fixture_area', kind: 'snapshot', lights: {}, favorite: false, order: 0, preview: []}];
function Harness({initial = [newBindingTimeWindow()]}: {initial?: BindingTimeWindow[]}) {
  const [windows, setWindows] = useState(initial);
  return <><BindingTimeWindows windows={windows} scenes={scenes} change={setWindows} selectedTargets/><output data-testid="result">{JSON.stringify(windows)}</output><button disabled={!bindingTimeWindowsValid(windows, scenes)}>Test speichern</button></>;
}
const result = () => JSON.parse(screen.getByTestId('result').textContent || '[]') as BindingTimeWindow[];
it('edits clock, solar offsets and open boundaries with explicit priority/fallback help', () => {
  render(<Harness/>);
  expect(screen.getByText(/Das erste passende Zeitfenster/)).toHaveTextContent('Passt kein Fenster, gilt der letzte Zustand');
  expect(screen.getByText(/Diese Regeln gelten nur beim Einschalten/)).toHaveTextContent('nie Helligkeit oder Weißton');
  fireEvent.change(screen.getByLabelText('Einschaltfenster 1 Beginn: Uhrzeit'), {target: {value: '22:30'}});
  fireEvent.change(screen.getByLabelText('Einschaltfenster 1 Ende: Bezug'), {target: {value: 'sunrise'}});
  fireEvent.change(screen.getByLabelText('Einschaltfenster 1 Ende: Versatz in Minuten'), {target: {value: '-15'}});
  expect(result()[0].window).toEqual({after: {type: 'time', value: '22:30'}, before: {type: 'sun', event: 'sunrise', offset_min: -15}});
  fireEvent.change(screen.getByLabelText('Einschaltfenster 1 Beginn: Bezug'), {target: {value: 'sunset'}});
  fireEvent.change(screen.getByLabelText('Einschaltfenster 1 Beginn: Versatz in Minuten'), {target: {value: '30'}});
  expect(result()[0].window.after).toEqual({type: 'sun', event: 'sunset', offset_min: 30});
  fireEvent.change(screen.getByLabelText('Einschaltfenster 1 Ende: Bezug'), {target: {value: 'none'}});
  expect(result()[0].window.before).toBeNull();
  expect(screen.getByRole('button', {name: 'Test speichern'})).toBeEnabled();
});
it('converts percent brightness and validates optional white temperature without silent correction', () => {
  render(<Harness/>);
  fireEvent.change(screen.getByLabelText('Einschaltfenster 1 Helligkeit'), {target: {value: '5'}});
  expect(result()[0]).toMatchObject({mode: 'brightness', brightness: 13});
  const temperature = screen.getByLabelText('Einschaltfenster 1 Weißton in Kelvin');
  for (const value of ['999', '40001', '2700.5', '']) {
    fireEvent.change(temperature, {target: {value}});
    expect(screen.getByRole('button', {name: 'Test speichern'})).toBeDisabled();
  }
  fireEvent.change(temperature, {target: {value: '2700'}});
  expect(screen.getByRole('button', {name: 'Test speichern'})).toBeEnabled();
  fireEvent.click(screen.getByLabelText('Einschaltfenster 1 Weißton festlegen'));
  expect(result()[0]).not.toHaveProperty('color_temp_kelvin');
  fireEvent.click(screen.getByLabelText('Einschaltfenster 1 Weißton festlegen'));
  expect(result()[0]).toMatchObject({color_temp_kelvin: 2700});
});
it('requires a valid scene, retains boundaries when changing mode, and rejects stale scenes', () => {
  render(<Harness/>);
  const original = result()[0].window;
  fireEvent.change(screen.getByLabelText('Einschaltfenster 1 Aktion'), {target: {value: 'scene'}});
  expect(screen.getByRole('button', {name: 'Test speichern'})).toBeDisabled();
  expect(result()[0]).toEqual({window: original, mode: 'scene', scene_id: ''});
  fireEvent.change(screen.getByLabelText('Einschaltfenster 1 Szene'), {target: {value: scenes[0].id}});
  expect(screen.getByRole('button', {name: 'Test speichern'})).toBeEnabled();
  expect(screen.getByText(/Nur die ausgewählten Lampen/)).toBeVisible();
  expect(bindingTimeWindowsValid([{window: original, mode: 'scene', scene_id: 'fixture_missing'}], scenes)).toBe(false);
});
it('reorders priority without losing per-window values and supports removal', () => {
  const first = newBindingTimeWindow();
  const second: BindingTimeWindow = {window: {after: null, before: null}, mode: 'scene', scene_id: scenes[0].id};
  render(<Harness initial={[first, second]}/>);
  fireEvent.click(screen.getByRole('button', {name: 'Einschaltfenster 2 nach oben'}));
  expect(result()).toEqual([second, first]);
  expect(screen.getByRole('button', {name: 'Einschaltfenster 1 nach oben'})).toBeDisabled();
  expect(screen.getByRole('button', {name: 'Einschaltfenster 2 nach unten'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button', {name: 'Einschaltfenster 1 nach unten'}));
  expect(result()).toEqual([first, second]);
  fireEvent.click(screen.getByRole('button', {name: 'Einschaltfenster 1 entfernen'}));
  expect(result()).toEqual([second]);
});
it('enforces one to twenty-four windows and bounded integer solar offsets', () => {
  const {unmount} = render(<Harness initial={[]}/>);
  expect(screen.getByRole('button', {name: 'Test speichern'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button', {name: 'Einschaltfenster hinzufügen'}));
  expect(result()).toHaveLength(1);
  fireEvent.change(screen.getByLabelText('Einschaltfenster 1 Beginn: Bezug'), {target: {value: 'sunrise'}});
  for (const value of ['-1441', '1441', '0.5', '']) {
    fireEvent.change(screen.getByLabelText('Einschaltfenster 1 Beginn: Versatz in Minuten'), {target: {value}});
    expect(screen.getByRole('button', {name: 'Test speichern'})).toBeDisabled();
  }
  fireEvent.change(screen.getByLabelText('Einschaltfenster 1 Beginn: Versatz in Minuten'), {target: {value: '-1440'}});
  expect(screen.getByRole('button', {name: 'Test speichern'})).toBeEnabled();
  unmount();
  render(<Harness initial={Array.from({length: 24}, newBindingTimeWindow)}/>);
  expect(screen.getByRole('button', {name: 'Einschaltfenster hinzufügen'})).toBeDisabled();
  expect(screen.getByRole('button', {name: 'Test speichern'})).toBeEnabled();
  expect(bindingTimeWindowsValid(Array.from({length: 25}, newBindingTimeWindow), scenes)).toBe(false);
});
it('honors the parent fieldset lock for every edit and keeps stale saved values visible', () => {
  const stale: BindingTimeWindow = {window: {after: null, before: null}, mode: 'scene', scene_id: 'fixture_missing'};
  render(<fieldset disabled><Harness initial={[stale]}/></fieldset>);
  expect(within(screen.getByLabelText('Einschaltfenster 1 Szene')).getByRole('option', {name: 'Szene nicht mehr passend oder vorhanden'})).toHaveProperty('selected', true);
  expect(screen.getByLabelText('Einschaltfenster 1 Szene')).toBeDisabled();
  expect(screen.getByRole('button', {name: 'Einschaltfenster hinzufügen'})).toBeDisabled();
  expect(screen.getByRole('button', {name: 'Einschaltfenster 1 entfernen'})).toBeDisabled();
});
