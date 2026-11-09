// Geändert für Lichtzentrale
// @vitest-environment jsdom
import {afterEach, describe, expect, it, vi} from 'vitest';
import {act, cleanup, renderHook} from '@testing-library/react';
import {LivePreview, useLivePreview} from './useLivePreview';
import type {Hass} from './types';
import type {NavigationGuard} from './sceneControls';

const result = {applied: ['light.fixture'], skipped: [], failed: []};
const doc = (brightness: number) => ({scene: {name: 'Fixture', brightness}});
function deferred<T>() {let resolve!: (value: T) => void; const promise = new Promise<T>(done => {resolve = done;}); return {promise, resolve};}
function setup() {
  vi.useFakeTimers();
  const callWS = vi.fn(async (request: {type: string; [key: string]: unknown}): Promise<unknown> => request.type.endsWith('/begin') ? {preview_id: 'fixture-session', moon_fraction: .37} : result);
  const publish = vi.fn();
  const controller = new LivePreview(() => ({callWS} as Hass), 'zone:fixture', publish);
  return {callWS, publish, controller, hass: {callWS} as Hass};
}
const flush = async () => {await Promise.resolve(); await Promise.resolve(); await Promise.resolve();};
const calls = (spy: ReturnType<typeof setup>['callWS'], suffix: string) => spy.mock.calls.filter(([request]) => request.type.endsWith(suffix)).map(([request]) => request);
afterEach(() => {cleanup(); vi.useRealTimers();});

describe('LivePreview serial transaction QA', () => {
  it('publishes the server-authoritative captured lights without modifying them', async () => {
    const {controller, callWS, publish} = setup();
    const lights = {'light.fixture': {on: false, brightness: 51, xy: [.4, .3]}};
    callWS.mockResolvedValueOnce({preview_id: 'fixture-session', moon_fraction: .37, lights});
    controller.begin(); await flush();
    expect(publish.mock.calls.at(-1)?.[0]).toMatchObject({ready: true, moon: 37, capturedLights: lights});
    await controller.cancel();
  });
  it('coalesces repeated live edits and assigns monotonically increasing sequences', async () => {
    const {controller, callWS} = setup(); controller.begin(); await flush();
    controller.schedule(doc(30)); controller.schedule(doc(60)); controller.schedule(doc(90));
    await vi.advanceTimersByTimeAsync(349); expect(calls(callWS, '/apply')).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(1);
    expect(calls(callWS, '/apply')).toEqual([{type: 'lichtzentrale/preview/apply', preview_id: 'fixture-session', sequence: 1, ...doc(90)}]);
    controller.schedule(doc(100)); await vi.advanceTimersByTimeAsync(350);
    expect(calls(callWS, '/apply').at(-1)).toMatchObject({sequence: 2, scene: {brightness: 100}});
    await controller.cancel();
  });
  it('waits for pending begin then cancels the returned session once', async () => {
    const {controller, callWS} = setup(); const start = deferred<{preview_id: string}>(); callWS.mockImplementationOnce(() => start.promise);
    controller.begin(); const first = controller.cancel(), second = controller.cancel();
    expect(first).toBe(second); expect(calls(callWS, '/cancel')).toHaveLength(0);
    start.resolve({preview_id: 'late-session'});
    expect(await first).toBe(true); expect(calls(callWS, '/cancel')).toEqual([{type: 'lichtzentrale/preview/cancel', preview_id: 'late-session'}]);
    await vi.advanceTimersByTimeAsync(60000); expect(calls(callWS, '/keepalive')).toHaveLength(0);
  });
  it('waits for an in-flight apply before cancel and drops queued edits', async () => {
    const {controller, callWS} = setup(); controller.begin(); await flush();
    const apply = deferred<typeof result>(); callWS.mockImplementationOnce(() => apply.promise);
    controller.schedule(doc(20)); await vi.advanceTimersByTimeAsync(350);
    controller.schedule(doc(30)); await vi.advanceTimersByTimeAsync(350);
    const cancelled = controller.cancel();
    expect(calls(callWS, '/cancel')).toHaveLength(0);
    apply.resolve(result); expect(await cancelled).toBe(true);
    expect(calls(callWS, '/apply')).toHaveLength(1);
    expect(callWS.mock.calls.at(-1)?.[0].type).toBe('lichtzentrale/preview/cancel');
  });
  it('skips obsolete queued work when a more recent draft arrives', async () => {
    const {controller, callWS} = setup(); controller.begin(); await flush();
    const pending = deferred<typeof result>(); callWS.mockImplementationOnce(() => pending.promise);
    controller.schedule(doc(10)); await vi.advanceTimersByTimeAsync(350);
    controller.schedule(doc(20)); await vi.advanceTimersByTimeAsync(350);
    controller.schedule(doc(30)); await vi.advanceTimersByTimeAsync(350);
    pending.resolve(result); await flush(); await vi.advanceTimersByTimeAsync(0);
    expect(calls(callWS, '/apply').map(request => (request.scene as {brightness: number}).brightness)).toEqual([10, 30]);
    await controller.cancel();
  });
  it('commits the latest supplied draft once despite pending debounce and repeated clicks', async () => {
    const {controller, callWS} = setup(); controller.begin(); await flush();
    const pending = deferred<typeof result>(); callWS.mockImplementationOnce(() => pending.promise);
    controller.schedule(doc(50));
    const first = controller.commit(doc(80)), second = controller.commit(doc(90));
    expect(first).toBe(second); await flush();
    expect(calls(callWS, '/commit')).toHaveLength(1);
    expect(calls(callWS, '/commit')[0]).toMatchObject(doc(80));
    pending.resolve(result); await first; await vi.advanceTimersByTimeAsync(60000);
    expect(calls(callWS, '/apply')).toHaveLength(0); expect(calls(callWS, '/keepalive')).toHaveLength(0);
  });
  it('does not restore after a successful commit, including dispose', async () => {
    const {controller, callWS} = setup(); controller.begin(); await flush(); await controller.commit(doc(90));
    expect(await controller.cancel()).toBe(true); controller.dispose(); await flush();
    expect(calls(callWS, '/cancel')).toHaveLength(0);
  });
  it('waits for a commit before deciding that navigation may proceed', async () => {
    const {controller, callWS} = setup(); controller.begin(); await flush();
    const pending = deferred<typeof result>(); callWS.mockImplementationOnce(() => pending.promise);
    const committed = controller.commit(doc(70)); const cancelled = controller.cancel();
    let done = false; void cancelled.then(() => {done = true;}); await flush(); expect(done).toBe(false);
    pending.resolve(result); await committed; expect(await cancelled).toBe(true);
    expect(calls(callWS, '/cancel')).toHaveLength(0);
  });
  it('retries a failed cancellation and does not claim restoration', async () => {
    const {controller, callWS, publish} = setup(); controller.begin(); await flush();
    callWS.mockRejectedValueOnce(new Error('Restore failed'));
    expect(await controller.cancel()).toBe(false);
    expect(publish.mock.calls.at(-1)?.[0].error).toContain('Abbrechen fehlgeschlagen');
    expect(await controller.cancel()).toBe(true); expect(calls(callWS, '/cancel')).toHaveLength(2);
  });
  it('rejects a partial restoration and allows an explicit retry', async () => {
    const {controller, callWS, publish} = setup(); controller.begin(); await flush();
    callWS.mockResolvedValueOnce({...result, failed: ['light.fixture']});
    expect(await controller.cancel()).toBe(false); expect(publish.mock.calls.at(-1)?.[0].error).toContain('1 Lampe(n)');
    expect(await controller.cancel()).toBe(true);
  });
  it('can cancel after failed commit without losing its preview session', async () => {
    const {controller, callWS} = setup(); controller.begin(); await flush(); callWS.mockRejectedValueOnce(new Error('Save failed'));
    expect(await controller.commit(doc(80))).toBeNull(); expect(await controller.cancel()).toBe(true);
    expect(calls(callWS, '/cancel')[0].preview_id).toBe('fixture-session');
  });
  it('keeps the session alive every 30 seconds and stops when cancelled', async () => {
    const {controller, callWS} = setup(); controller.begin(); await flush();
    await vi.advanceTimersByTimeAsync(60000); expect(calls(callWS, '/keepalive')).toHaveLength(2);
    await controller.cancel(); await vi.advanceTimersByTimeAsync(60000); expect(calls(callWS, '/keepalive')).toHaveLength(2);
  });
  it('disposal cleans up a late begin and suppresses publish after unmount', async () => {
    const {controller, callWS, publish} = setup(); const pending = deferred<{preview_id: string}>(); callWS.mockImplementationOnce(() => pending.promise);
    controller.begin(); controller.dispose(); pending.resolve({preview_id: 'late'}); await flush(); await vi.advanceTimersByTimeAsync(0);
    expect(calls(callWS, '/cancel')).toHaveLength(1); expect(publish).not.toHaveBeenCalled();
  });
});

describe('useLivePreview navigation integration', () => {
  it('blocks registered navigation on failed restore and permits retry', async () => {
    const {hass, callWS} = setup(); let guard: NavigationGuard = null;
    const registerGuard = vi.fn((value: NavigationGuard) => {guard = value;});
    const document = doc(50);
    const hook = renderHook(() => useLivePreview(hass, 'zone:fixture', document, false, registerGuard));
    await act(flush); expect(hook.result.current.ready).toBe(true); expect(guard).toBeTypeOf('function');
    callWS.mockRejectedValueOnce(new Error('Cannot restore'));
    await act(async () => {expect(await guard!()).toBe(false);});
    expect(hook.result.current.error).toContain('Abbrechen fehlgeschlagen');
    await act(async () => {expect(await guard!()).toBe(true);});
    hook.unmount(); expect(guard).toBeNull();
  });
  it('cancels the old target before activating a fresh hook transaction', async () => {
    const {hass, callWS} = setup(); const document = doc(40);
    const hook = renderHook(({area}) => useLivePreview(hass, area, document, false), {initialProps: {area: 'fixture_living'}});
    await act(flush); hook.rerender({area: 'fixture_study'}); await act(flush);
    expect(calls(callWS, '/begin').map(request => request.area_id)).toEqual(['fixture_living', 'fixture_study']);
    expect(calls(callWS, '/cancel')).toHaveLength(1);
    hook.unmount(); await act(flush); expect(calls(callWS, '/cancel')).toHaveLength(2);
  });
});
