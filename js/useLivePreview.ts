// Geändert für Lichtzentrale
import {useEffect, useRef, useState} from 'react';
import {errorText} from './sceneControls';
import type {GuardRegistration} from './sceneControls';
import type {ApplyResult, Hass, Palette, Scene} from './types';
export type PreviewDocument = {scene: Partial<Scene>} | {palette: Partial<Palette>};
interface PreviewState {ready: boolean; busy: boolean; closing: boolean; error: string; message: string; moon?: number; capturedLights?: Scene['lights']}
const initial: PreviewState = {ready: false, busy: false, closing: false, error: '', message: ''};
export interface PreviewCommit extends Partial<ApplyResult> {scene?: Scene; palette?: Palette}
/** One serial server transaction. No light state is persisted in the browser. */
export class LivePreview {
  private id = '';
  private sequence = 0;
  private tail: Promise<unknown> = Promise.resolve();
  private timer?: ReturnType<typeof setTimeout>;
  private heartbeat?: ReturnType<typeof setInterval>;
  private finishing = false;
  private finished = false;
  private disposed = false;
  private cancelPending?: Promise<boolean>;
  private commitPending?: Promise<PreviewCommit | null>;
  private revision = 0;
  private state = {...initial};
  constructor(private api: () => Hass, private area: string, private publish: (state: PreviewState) => void) {}
  private update(patch: Partial<PreviewState>) {this.state = {...this.state, ...patch}; if (!this.disposed) this.publish(this.state);}
  begin() {
    this.tail = this.api().callWS<{preview_id: string; moon_fraction?: number; lights?: Scene['lights']}>({type: 'lichtzentrale/preview/begin', area_id: this.area}).then(result => {
      if (!result.preview_id) throw new Error('Live-Probe konnte nicht gestartet werden.');
      this.id = result.preview_id;
      this.update({ready: true, capturedLights: result.lights, moon: typeof result.moon_fraction === 'number' ? Math.round(result.moon_fraction * 100) : undefined});
      if (!this.finishing) this.heartbeat = setInterval(() => {
        if (this.finishing || this.finished) return;
        void this.api().callWS({type: 'lichtzentrale/preview/keepalive', preview_id: this.id}).catch(error => this.update({error: `Live-Verbindung unterbrochen: ${errorText(error)}. Bitte abbrechen und neu öffnen.`}));
      }, 30000);
    }).catch(error => {this.update({error: errorText(error)});});
  }
  schedule(document: PreviewDocument) {
    if (this.finishing || this.finished) return;
    clearTimeout(this.timer);
    const version = ++this.revision;
    this.timer = setTimeout(() => {
      this.tail = this.tail.then(async () => {
        if (this.finishing || this.finished || version !== this.revision || !this.id) return;
        this.update({busy: true, error: ''});
        try {await this.apply(document, version);} catch (error) {if (version === this.revision) this.update({error: `Live-Probe fehlgeschlagen: ${errorText(error)}`});}
        finally {this.update({busy: false});}
      });
    }, 350);
  }
  private async apply(document: PreviewDocument, version: number) {
    const result = await this.api().callWS<ApplyResult>({type: 'lichtzentrale/preview/apply', preview_id: this.id, sequence: ++this.sequence, ...document});
    if (version !== this.revision || this.finishing) return;
    const failed = result.failed?.length || 0, skipped = result.skipped?.length || 0;
    this.update({message: failed || skipped ? `${failed} fehlgeschlagen, ${skipped} übersprungen. Bitte Lampenzustand prüfen.` : 'Live im Ziel angewendet.'});
  }
  cancel(): Promise<boolean> {
    if (this.cancelPending) return this.cancelPending;
    if (this.finished) return Promise.resolve(true);
    if (this.commitPending) return this.commitPending.then(result => result ? true : this.cancel());
    this.finishing = true; ++this.revision; clearTimeout(this.timer); clearInterval(this.heartbeat);
    this.update({closing: true, busy: true, error: '', message: 'Vorherigen Zustand wiederherstellen …'});
    this.cancelPending = this.tail.then(async () => {
      if (this.id) {
        const result = await this.api().callWS<Partial<ApplyResult>>({type: 'lichtzentrale/preview/cancel', preview_id: this.id});
        if (result.failed?.length) throw new Error(`${result.failed.length} Lampe(n) konnten nicht wiederhergestellt werden. Bitte erneut abbrechen.`);
      }
      this.finished = true; return true;
    }).catch(error => {this.update({error: `Abbrechen fehlgeschlagen: ${errorText(error)}`, message: ''}); return false;}).finally(() => {this.cancelPending = undefined; this.update({busy: false});});
    return this.cancelPending;
  }
  commit(document: PreviewDocument): Promise<PreviewCommit | null> {
    if (this.commitPending) return this.commitPending;
    if (this.finishing || this.finished) return Promise.resolve(null);
    this.finishing = true; ++this.revision; clearTimeout(this.timer);
    this.update({closing: true, busy: true, error: '', message: ''});
    this.commitPending = this.tail.then(async () => {
      if (!this.id) throw new Error('Keine aktive Live-Probe. Bitte abbrechen und neu öffnen.');
      const result = await this.api().callWS<PreviewCommit>({type: 'lichtzentrale/preview/commit', preview_id: this.id, ...document});
      this.finished = true; clearInterval(this.heartbeat); return result;
    }).catch(error => {this.finishing = false; this.update({closing: false, error: `Speichern fehlgeschlagen: ${errorText(error)}`}); return null;}).finally(() => {this.commitPending = undefined; this.update({busy: false});});
    return this.commitPending;
  }
  dispose() {this.disposed = true; void this.cancel();}
}
export function useLivePreview(hass: Hass, area: string, document: PreviewDocument, changed: boolean, registerGuard?: GuardRegistration) {
  const api = useRef(hass); api.current = hass;
  const transaction = useRef<LivePreview | null>(null);
  const [state, setState] = useState<PreviewState>(initial);
  useEffect(() => {
    setState({...initial});
    if (!area) return;
    const current = new LivePreview(() => api.current, area, setState);
    transaction.current = current; current.begin();
    return () => {transaction.current = null; current.dispose();};
  }, [area]);
  useEffect(() => {if (changed && area) transaction.current?.schedule(document);}, [document, changed, area]);
  useEffect(() => {
    if (!registerGuard || !area) return;
    registerGuard(() => transaction.current?.cancel() || Promise.resolve(true));
    return () => registerGuard(null);
  }, [registerGuard, area]);
  return {...state, cancel: () => transaction.current?.cancel() || Promise.resolve(true), commit: (value: PreviewDocument) => transaction.current?.commit(value) || Promise.resolve(null)};
}
