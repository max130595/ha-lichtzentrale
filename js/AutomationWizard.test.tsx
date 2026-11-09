// Geändert für Lichtzentrale
// @vitest-environment jsdom
import {afterEach, describe, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {AutomationWizard, newAutomation} from './AutomationWizard';
import type {AutomationSchedule} from './AutomationTypes';
import type {Light, Room, Scene} from './types';
import type {AdaptiveStatus} from './RuntimeControls';
afterEach(cleanup);
const data = {lux_sensors: [{entity_id: 'sensor.synthetic_lux', name: 'Außenlicht', device_class: 'illuminance', available: true}], persons: [{entity_id: 'person.synthetic', name: 'Beispielperson', available: true}]};
const rooms = [{area_id: 'synthetic_corridor', name: 'Flur'}] as Room[];
const zones = [{id: 'synthetic_zone', name: 'Wohnbereich', entity_ids: ['light.synthetic_shared', 'switch.synthetic_ceiling']}];
const lights = [{entity_id: 'light.synthetic_shared', name: 'Orientierungslicht', area_id: 'synthetic_corridor', area_name: 'Flur', allowed: true, available: true}, {entity_id: 'switch.synthetic_ceiling', name: 'Deckenlicht', allowed: true, available: true}] as Light[];
const scenes = [{id: 'synthetic_evening', name: 'Abend', area_id: 'zone:synthetic_zone'}, {id: 'synthetic_night', name: 'Nachtlicht', area_id: 'synthetic_corridor'}] as Scene[];
function setup(initial = newAutomation(), disabled = false, adaptive?: AdaptiveStatus) {
  const save = vi.fn(), cancel = vi.fn();
  return {save, cancel, ...render(<AutomationWizard initial={initial} data={data} rooms={rooms} zones={zones} lights={lights} scenes={scenes} adaptive={adaptive} disabled={disabled} save={save} cancel={cancel}/>)};
}
const click = (name: string) => fireEvent.click(screen.getByRole('button', {name}));
const change = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), {target: {value}});
function firstTarget() {click('Weiter'); fireEvent.click(screen.getByLabelText('Wohnbereich')); click('Weiter');}
describe('Automation in drei Schritten', () => {
  it('defaults all weekdays and persists sun offset and zone scene without raw IDs', () => {
    const {save} = setup();
    expect(screen.getAllByRole('checkbox').filter(input => (input as HTMLInputElement).checked)).toHaveLength(7);
    click('-15 Min.'); firstTarget(); change('Szene 1', 'synthetic_evening');
    expect(screen.getByLabelText('Ziele aus Schritt 2')).toHaveTextContent('Wohnbereich');
    expect(screen.queryByLabelText('Wohnbereich')).not.toBeInTheDocument();
    expect(screen.queryByText(/light\.synthetic|zone:synthetic|sensor\.synthetic/)).not.toBeInTheDocument();
    click('Automation speichern');
    expect(save).toHaveBeenCalledOnce(); expect(save.mock.calls[0][0]).toMatchObject({enabled: false, trigger: {type: 'sun', event: 'sunset', offset_min: -15}, actions: [{type: 'scene', area_ids: ['zone:synthetic_zone'], entity_ids: [], scene_id: 'synthetic_evening'}]});
    expect(save.mock.calls[0][0]).not.toHaveProperty('action');
  });
  it('keeps additional action targets isolated across back, forward, reorder and edit', () => {
    const {save} = setup(); click('Uhrzeit'); change('Uhrzeit', '22:30'); firstTarget(); change('Aktion 1', 'off'); click('+ Weitere Aktion'); change('Aktion 2', 'night'); fireEvent.click(screen.getByLabelText('Flur'));
    click('Zurück'); expect(screen.getByLabelText('Wohnbereich')).toBeChecked(); expect(screen.getByLabelText('Flur')).not.toBeChecked(); click('Weiter');
    expect(screen.getByLabelText('Ziele aus Schritt 2')).toHaveTextContent('Wohnbereich');
    click('Automation speichern'); const saved = save.mock.calls[0][0] as AutomationSchedule;
    expect(saved.actions.map(a => a.area_ids)).toEqual([['zone:synthetic_zone'], ['synthetic_corridor']]);
    click('Aktion 2 nach oben'); expect(screen.getByLabelText('Ziele aus Schritt 2')).toHaveTextContent('Flur'); click('Zurück'); expect(screen.getByLabelText('Flur')).toBeChecked(); expect(screen.getByLabelText('Wohnbereich')).not.toBeChecked();
    cleanup(); const reopened = setup({...saved, id: 'synthetic_plan'}); click('Weiter'); click('Weiter'); click('Automation speichern'); expect(reopened.save.mock.calls[0][0].actions).toEqual(saved.actions);
  });
  it('supports several rooms, zones and lamps and excludes lamp targets for night actions', () => {
    const {save} = setup(); click('Weiter'); fireEvent.click(screen.getByLabelText('Wohnbereich')); fireEvent.click(screen.getByLabelText('Flur')); fireEvent.click(screen.getByLabelText('Orientierungslicht · Flur')); fireEvent.click(screen.getByLabelText('Deckenlicht · Nur Ein/Aus')); click('Weiter'); change('Aktion 1', 'night'); expect(screen.getByText('Automation speichern')).toBeDisabled(); change('Aktion 1', 'off'); click('Automation speichern'); expect(save.mock.calls[0][0].actions[0]).toMatchObject({area_ids: ['zone:synthetic_zone', 'synthetic_corridor'], entity_ids: ['light.synthetic_shared', 'switch.synthetic_ceiling']});
  });
  it('preserves all advanced settings and enabled state during ordinary edits', () => {
    const initial = newAutomation(); initial.id = 'synthetic_plan'; initial.enabled = true; initial.name = 'Gespeichert'; initial.actions = [{type: 'off', area_ids: ['zone:synthetic_zone']}]; initial.transition = 45;
    initial.condition = {weekdays: [1,3], person_entity_ids: ['person.synthetic'], light_state: 'on', time_window: {after: {type: 'sun', event: 'sunset', offset_min: -60}, before: {type: 'time', value: '01:00'}}};
    const {save} = setup(initial); const details = screen.getByText('Mehr Optionen').closest('details'); expect(details).not.toHaveAttribute('open'); click('Weiter'); click('Weiter'); click('Automation speichern'); expect(save.mock.calls[0][0]).toEqual(initial); expect(initial.actions[0].area_ids).toEqual(['zone:synthetic_zone']);
  });
  it('validates free offsets, weekdays, windows, lux and transition', () => {
    setup(); change('Versatz in Minuten', '1441'); expect(screen.getByText('Weiter')).toBeDisabled(); change('Versatz in Minuten', '-20'); click('Sonnenaufgang'); expect(screen.getByLabelText('Versatz in Minuten')).toHaveValue(-20);
    fireEvent.click(screen.getByLabelText('Außenhelligkeit als Auslöser')); expect(screen.getByText('Weiter')).toBeDisabled(); change('Lux-Sensor', 'sensor.synthetic_lux'); change('Mindestdauer in Sekunden', '0'); expect(screen.getByText('Weiter')).toBeDisabled(); change('Mindestdauer in Sekunden', '60'); firstTarget(); change('Aktion 1', 'off'); fireEvent.click(screen.getByLabelText('Nur zwischen … und …')); change('Beginn: Grenze', 'sun'); change('Beginn: Versatz in Minuten', '1441'); expect(screen.getByText('Automation speichern')).toBeDisabled(); change('Beginn: Versatz in Minuten', '-30'); fireEvent.click(screen.getByLabelText('Sanfter Übergang')); change('Übergangszeit in Sekunden', '1801'); expect(screen.getByText('Automation speichern')).toBeDisabled(); change('Übergangszeit in Sekunden', '1800'); expect(screen.getByText('Automation speichern')).toBeEnabled();
  });
  it('cancel does not mutate original actions and a new mount starts fresh', () => {
    const initial = newAutomation(); initial.actions = [{type: 'off', area_ids: ['zone:synthetic_zone']}]; const before = structuredClone(initial); const {cancel, save} = setup(initial); click('Weiter'); fireEvent.click(screen.getByLabelText('Flur')); click('Abbrechen'); expect(cancel).toHaveBeenCalledOnce(); expect(save).not.toHaveBeenCalled(); expect(initial).toEqual(before); cleanup(); setup(); click('Weiter'); expect(screen.getByLabelText('Flur')).not.toBeChecked(); expect(screen.getByLabelText('Wohnbereich')).not.toBeChecked();
  });
  it('retains advanced motion actions and hides unavailable natural light', () => {
    const initial = newAutomation(); initial.actions = [{type: 'motion', area_ids: ['synthetic_corridor'], entity_ids: [], enabled: false}];
    const {save} = setup(initial); click('Weiter'); click('Weiter');
    expect(screen.queryByRole('option', {name: 'Natürliches Licht'})).not.toBeInTheDocument();
    expect(screen.getByLabelText('Aktion 1 einschalten (sonst ausschalten)')).not.toBeChecked();
    click('Automation speichern'); expect(save.mock.calls[0][0].actions).toEqual(initial.actions);
  });
  it('allows natural light for a zone with an available adaptive mapping', () => {
    const initial = newAutomation(); initial.actions = [{type: 'adaptive', area_ids: ['zone:synthetic_zone'], entity_ids: [], enabled: true}];
    const adaptive: AdaptiveStatus = {available: true, switches: [], rooms: [{area_id: 'zone:synthetic_zone', switch_entity_id: 'switch.synthetic_adaptive', enabled: true, available: true, default_on: 'adaptive'}]};
    const {save} = setup(initial, false, adaptive); click('Weiter'); click('Weiter');
    expect(screen.getByText('Automation speichern')).toBeEnabled();
    expect(screen.getByText(/genau einen passend eingerichteten Raum oder eine Zone/)).toBeInTheDocument();
    click('Automation speichern'); expect(save.mock.calls[0][0].actions).toEqual(initial.actions);
    change('Aktion 1', 'motion'); expect(screen.getByText('Automation speichern')).toBeEnabled();
    expect(screen.getByText(/genau einen eingerichteten Raum oder eine Zone/)).toBeInTheDocument();
    click('Automation speichern'); expect(save.mock.calls[1][0].actions).toEqual([{type: 'motion', area_ids: ['zone:synthetic_zone'], entity_ids: [], enabled: true}]);
  });
  it('disables navigation, cancel and submission while saving', () => {
    const {save, cancel} = setup(newAutomation(), true); const form = screen.getByText('Neue Automation').closest('form')!;
    for (const button of within(form).getAllByRole('button')) expect(button).toBeDisabled(); fireEvent.submit(form); expect(save).not.toHaveBeenCalled(); expect(cancel).not.toHaveBeenCalled();
  });
});
