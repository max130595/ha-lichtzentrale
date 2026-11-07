// @vitest-environment jsdom
import {afterEach, describe, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {App} from './App';
import type {Hass, Light, Palette} from './types';
import LichtzentralePanel from './LichtzentralePanel';
const palette: Palette = {id: 'test-palette', name: 'Testpalette', category: 'Testkategorie', bri: 128, colors: [{x: .3, y: .3}], preview: ['#aabbcc', '#bbccdd']};
const lamp: Light = {entity_id: 'light.test_fixture', name: 'Testlampe', area_id: null, area_name: null, available: true, allowed: false};
function setup(lights: Light[] = [lamp]) {
  const callWS = vi.fn(async (request: {type: string; [key: string]: unknown}): Promise<unknown> => {
    if (request.type === 'lichtzentrale/palettes/list') return [palette];
    if (request.type === 'lichtzentrale/lights/list') return lights;
    if (request.type === 'lichtzentrale/settings/save') {
      lights = lights.map(light => ({...light, allowed: (request.light_entity_ids as string[]).includes(light.entity_id)}));
      return {};
    }
    return {applied: [lamp.entity_id], skipped: []};
  });
  render(<App hass={{callWS} as Hass}/>);
  return callWS;
}
afterEach(cleanup);
describe('Galerie', () => {
  it('loads the gallery, five tabs and honest placeholders', async () => {
    setup(); await screen.findByText('Testpalette');
    expect(screen.getByRole('navigation').querySelectorAll('button')).toHaveLength(5);
    fireEvent.click(screen.getByRole('button', {name: 'Zeitpläne'}));
    expect(screen.getByText('Zeitpläne folgen in Stufe 4.')).toBeVisible();
  });
  it('does not offer unapproved lamps as application targets', async () => {
    setup(); fireEvent.click(await screen.findByText('Testpalette'));
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Auf 0 Lampe(n) anwenden'})).toBeDisabled();
  });
  it('saves explicit grants on the server before allowing selection', async () => {
    const callWS = setup(); await screen.findByText('Testpalette');
    fireEvent.click(screen.getByRole('button', {name: 'Lampen freigeben'}));
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', {name: 'Freigaben speichern'}));
    await waitFor(() => expect(callWS).toHaveBeenCalledWith({type: 'lichtzentrale/settings/save', light_entity_ids: ['light.test_fixture']}));
    await screen.findByText('Lampenfreigaben wurden in Home Assistant gespeichert.');
    fireEvent.click(screen.getByText('Testpalette'));
    expect(screen.getByRole('checkbox')).not.toBeChecked();
  });
  it('applies only explicit selection and prevents repeated clicks while pending', async () => {
    const callWS = setup([{...lamp, allowed: true}]);
    fireEvent.click(await screen.findByText('Testpalette'));
    fireEvent.click(screen.getByRole('checkbox'));
    let resolve: (value: unknown) => void = () => {};
    callWS.mockImplementationOnce(() => new Promise(done => { resolve = done; }));
    const button = screen.getByRole('button', {name: 'Auf 1 Lampe(n) anwenden'});
    fireEvent.click(button); fireEvent.click(button);
    expect(callWS.mock.calls.filter(([request]) => request.type === 'lichtzentrale/palette/apply')).toHaveLength(1);
    expect(callWS).toHaveBeenLastCalledWith({type: 'lichtzentrale/palette/apply', palette_id: palette.id, entity_ids: ['light.test_fixture'], brightness: 128, transition: 2});
    resolve({applied: [], skipped: ['light.test_fixture']});
    expect(await screen.findByRole('status')).toHaveTextContent('0 Lampe(n) angewendet. 1 Lampe(n) übersprungen.');
  });
  it('disables unavailable lamps', async () => {
    setup([{...lamp, allowed: true, available: false}]);
    fireEvent.click(await screen.findByText('Testpalette'));
    expect(screen.getByRole('checkbox')).toBeDisabled();
  });
  it('shows loading errors and retries explicitly', async () => {
    const callWS = vi.fn().mockRejectedValueOnce(new Error('Verbindung getrennt')).mockResolvedValue([]);
    render(<App hass={{callWS}}/>);
    expect(await screen.findByRole('alert')).toHaveTextContent('Verbindung getrennt');
    fireEvent.click(screen.getByRole('button', {name: 'Neu laden'}));
    await screen.findByText('Keine Paletten verfügbar. Lade die Daten erneut.');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
  it('shows application failures without claiming success', async () => {
    const callWS = setup([{...lamp, allowed: true}]);
    fireEvent.click(await screen.findByText('Testpalette')); fireEvent.click(screen.getByRole('checkbox'));
    callWS.mockRejectedValueOnce({message: 'Nicht erlaubt'});
    fireEvent.click(screen.getByRole('button', {name: 'Auf 1 Lampe(n) anwenden'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Anwenden fehlgeschlagen: Nicht erlaubt');
  });
  it('does not persist browser selection across remount', async () => {
    setup([{...lamp, allowed: true}]); fireEvent.click(await screen.findByText('Testpalette')); fireEvent.click(screen.getByRole('checkbox'));
    cleanup(); setup([{...lamp, allowed: true}]); fireEvent.click(await screen.findByText('Testpalette'));
    expect(screen.getByRole('checkbox')).not.toBeChecked();
  });
  it('clears selected lamps when their grants are revoked on reload', async () => {
    const callWS = setup([{...lamp, allowed: true}]); fireEvent.click(await screen.findByText('Testpalette')); fireEvent.click(screen.getByRole('checkbox'));
    callWS.mockImplementation(async request => request.type.endsWith('palettes/list') ? [palette] : [lamp]);
    fireEvent.click(screen.getByRole('button', {name: 'Neu laden'}));
    await waitFor(() => expect(screen.queryByRole('checkbox')).not.toBeInTheDocument());
    expect(screen.getByRole('button', {name: 'Auf 0 Lampe(n) anwenden'})).toBeDisabled();
  });
  it('keeps unsaved grants when saving fails', async () => {
    const callWS = setup(); await screen.findByText('Testpalette');
    fireEvent.click(screen.getByRole('button', {name: 'Lampen freigeben'}));
    fireEvent.click(screen.getByRole('checkbox'));
    callWS.mockRejectedValueOnce(new Error('Speicher nicht erreichbar'));
    fireEvent.click(screen.getByRole('button', {name: 'Freigaben speichern'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Speichern fehlgeschlagen');
    expect(screen.getByRole('checkbox')).toBeChecked();
  });
  it('ignores a late application response after unmount', async () => {
    const callWS = setup([{...lamp, allowed: true}]);
    fireEvent.click(await screen.findByText('Testpalette')); fireEvent.click(screen.getByRole('checkbox'));
    let resolve: (value: unknown) => void = () => {};
    callWS.mockImplementationOnce(() => new Promise(done => { resolve = done; }));
    fireEvent.click(screen.getByRole('button', {name: 'Auf 1 Lampe(n) anwenden'}));
    cleanup(); resolve({applied: [lamp.entity_id], skipped: []});
    await Promise.resolve();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
  it('custom element disconnects and reconnects without duplicate shadow roots', async () => {
    if (!customElements.get('test-lichtzentrale')) customElements.define('test-lichtzentrale', LichtzentralePanel);
    const element = document.createElement('test-lichtzentrale') as LichtzentralePanel;
    element.hass = {callWS: vi.fn().mockResolvedValue([])};
    document.body.append(element);
    await waitFor(() => expect(element.shadowRoot?.textContent).toContain('Galerie'));
    element.remove(); document.body.append(element);
    await waitFor(() => expect(element.shadowRoot?.textContent).toContain('Galerie'));
    element.remove();
  });
});
