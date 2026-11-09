// Geändert für Lichtzentrale
// @vitest-environment jsdom
import {StrictMode} from 'react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {DimmingSettings} from './DimmingSettings';
import type {Hass} from './types';
import type {NavigationGuard} from './sceneControls';

afterEach(cleanup);
const input = () => screen.getByRole('spinbutton', {name: 'Dimm-Untergrenze (%)'});
const save = () => screen.getByRole('button', {name: 'Untergrenze speichern'});
function setup(initial = 1) {
  const callWS = vi.fn(async (request: {type: string; dim_min_pct?: number}) => ({dim_min_pct: request.dim_min_pct ?? initial}));
  const view = render(<DimmingSettings hass={{callWS} as Hass}/>);
  return {callWS, ...view};
}
async function ready() {await screen.findByRole('spinbutton');}
describe('Globale Dimm-Untergrenze', () => {
  it.each([1, 9, 20])('loads the server value %i without a save or lamp command', async initial => {
    const {callWS} = setup(initial); await ready();
    expect(input()).toHaveValue(initial); expect(save()).toBeDisabled();
    expect(input()).toHaveAttribute('min', '1'); expect(input()).toHaveAttribute('max', '20');
    expect(callWS.mock.calls).toEqual([[{type: 'lichtzentrale/settings/get'}]]);
  });
  it.each(['', '0', '21', '1.5', '-1'])('rejects invalid input %s without a request', async value => {
    const {callWS} = setup(); await ready(); fireEvent.change(input(), {target: {value}});
    expect(save()).toBeDisabled(); expect(input()).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('alert')).toHaveTextContent('ganze Zahl von 1 bis 20');
    fireEvent.click(save()); expect(callWS).toHaveBeenCalledTimes(1);
  });
  it('waits for server confirmation, blocks repeated saves and navigation, then unlocks', async () => {
    let guard: NavigationGuard = null;
    const callWS = vi.fn().mockResolvedValueOnce({dim_min_pct: 1});
    render(<DimmingSettings hass={{callWS} as Hass} registerGuard={next => {guard = next;}}/>); await ready();
    let resolve!: (value: {dim_min_pct: number}) => void;
    callWS.mockImplementationOnce(() => new Promise(done => {resolve = done;}));
    fireEvent.change(input(), {target: {value: '12'}}); const button = save();
    fireEvent.click(button); fireEvent.click(button);
    expect(callWS).toHaveBeenCalledTimes(2); expect(callWS).toHaveBeenLastCalledWith({type: 'lichtzentrale/settings/dimming', dim_min_pct: 12});
    expect(input()).toBeDisabled(); expect(screen.queryByText(/in Home Assistant gespeichert/)).not.toBeInTheDocument();
    expect(await guard!()).toBe(false);
    await act(async () => {resolve({dim_min_pct: 12});});
    expect(screen.getByRole('status')).toHaveTextContent('12 % in Home Assistant gespeichert');
    expect(guard).toBeNull(); expect(save()).toBeDisabled();
  });
  it('keeps the draft after failed save and allows retry without premature success', async () => {
    const {callWS} = setup(); await ready();
    fireEvent.change(input(), {target: {value: '8'}}); callWS.mockRejectedValueOnce(new Error('Offline'));
    fireEvent.click(save()); await screen.findByRole('alert');
    expect(input()).toHaveValue(8); expect(save()).toBeEnabled(); expect(screen.queryByRole('status')).not.toBeInTheDocument();
    fireEvent.click(save()); await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('8 % in Home Assistant gespeichert'));
  });
  it('rejects a mismatching server acknowledgement', async () => {
    const {callWS} = setup(); await ready(); fireEvent.change(input(), {target: {value: '8'}});
    callWS.mockResolvedValueOnce({dim_min_pct: 1}); fireEvent.click(save());
    expect(await screen.findByRole('alert')).toHaveTextContent('Speichern nicht bestätigt');
    expect(screen.queryByRole('status')).not.toBeInTheDocument(); expect(save()).toBeEnabled();
  });
  it('shows load errors instead of an assumed default and retries explicitly', async () => {
    const callWS = vi.fn().mockRejectedValueOnce(new Error('Offline')).mockResolvedValueOnce({dim_min_pct: 7});
    render(<DimmingSettings hass={{callWS} as Hass}/>);
    expect(await screen.findByRole('alert')).toHaveTextContent('nicht geladen'); expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Einstellungen erneut laden'})); await ready(); expect(input()).toHaveValue(7);
  });
  it('ignores late save after unmount and re-reads persisted state on return', async () => {
    const {callWS, unmount} = setup(); await ready();
    let resolve!: (value: {dim_min_pct: number}) => void;
    callWS.mockImplementationOnce(() => new Promise(done => {resolve = done;}));
    fireEvent.change(input(), {target: {value: '10'}}); fireEvent.click(save()); unmount();
    await act(async () => {resolve({dim_min_pct: 10});}); expect(screen.queryByRole('status')).not.toBeInTheDocument();
    setup(10); await ready(); expect(input()).toHaveValue(10); expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
  it('ignores stale StrictMode load responses', async () => {
    let resolve!: (value: {dim_min_pct: number}) => void;
    const callWS = vi.fn().mockImplementationOnce(() => new Promise(done => {resolve = done;})).mockResolvedValueOnce({dim_min_pct: 4});
    render(<StrictMode><DimmingSettings hass={{callWS} as Hass}/></StrictMode>); await ready();
    await act(async () => {resolve({dim_min_pct: 19});}); await waitFor(() => expect(input()).toHaveValue(4));
  });
});
