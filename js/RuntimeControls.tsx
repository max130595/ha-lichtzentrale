// Geändert für Lichtzentrale
import {displayName, displayError} from './display';
import {useEffect, useRef, useState} from 'react';
import type {ApplyResult, Hass} from './types';
export interface DynamicRun {scene_id: string; area_id: string; name: string; interval: number; transition: number}
export interface AdaptiveStatus {available: boolean; rooms: {area_id: string; switch_entity_id: string | null; enabled: boolean; available: boolean; default_on: string; reason?: string}[]; switches: {entity_id: string; name: string; available: boolean}[]}
const failure = (error: unknown) => error instanceof Error ? error.message : typeof error === 'object' && error !== null && 'message' in error ? String(error.message) : 'Bitte Zustand prüfen.';
export function RuntimeControls({hass, area, revision = 0}: {hass: Hass; area: string; revision?: number}) {
  const api = useRef(hass); api.current = hass;
  const generation = useRef(0), lock = useRef(false), mounted = useRef(false);
  const currentArea = useRef(area); currentArea.current = area;
  useEffect(() => {mounted.current = true; return () => {mounted.current = false;};}, []);
  const [runs, setRuns] = useState<DynamicRun[]>([]), [adaptive, setAdaptive] = useState<AdaptiveStatus | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const counter = generation; const id = ++counter.current; let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const [d, a] = await Promise.all([api.current.callWS<DynamicRun[]>({type: 'lichtzentrale/dynamic/list'}), api.current.callWS<AdaptiveStatus>({type: 'lichtzentrale/adaptive/status'})]);
        if (id !== generation.current) return;
        setRuns(Array.isArray(d) ? d : []); setAdaptive(a?.available ? a : null); setError('');
      } catch (error) {if (id === generation.current) setError(`Lichtstatus konnte nicht geladen werden: ${failure(error)}`);}
      finally {if (id === generation.current) timer = setTimeout(() => void load(), 10000);}
    }
    void load(); return () => {counter.current++; clearTimeout(timer);};
  }, [area, revision, refresh]);
  async function update(type: string, data: Record<string, unknown>) {
    if (lock.current) return;
    const targetArea = area; lock.current = true; setBusy(true); setError(''); setMessage('');
    try {
      const result = await api.current.callWS<ApplyResult & {stopped?: boolean}>({type: `lichtzentrale/${type}`, area_id: area, ...data});
      if (mounted.current && targetArea === currentArea.current && type === 'dynamic/stop') setMessage(`Stopp ausgeführt. ${result.applied.length} Lampe(n) festgesetzt. ${result.skipped.length} übersprungen. ${result.failed?.length || 0} fehlgeschlagen.${result.failed?.length ? ' Bei diesen Lampen kann die Dynamik weiterlaufen. Zustand prüfen und erneut stoppen.' : ''}`);
      if (mounted.current && targetArea === currentArea.current) setRefresh(value => value + 1);
    } catch (error) {if (mounted.current && targetArea === currentArea.current) setError(`Änderung fehlgeschlagen: ${failure(error)} Bitte Lichtstatus neu laden und Zustand prüfen.`);}
    finally {lock.current = false; if (mounted.current) setBusy(false);}
  }
  const room = adaptive?.rooms?.find(item => item.area_id === area);
  return <section aria-label="Dynamik und natürliches Licht">
    {error && <p role="alert">{displayError(error)} <button onClick={() => setRefresh(value => value + 1)}>Lichtstatus neu laden</button></p>}
    <div className="card"><h3>Dynamik stoppen</h3><p>Stoppt Lichtzentrale-Szenen und Hue-Dynamik im Raum. Eingeschaltete, freigegebene Lampen werden mit ihrer aktuellen Farbe und Helligkeit festgesetzt. Ausgeschaltete Lampen, Schalter und nicht verfügbare Geräte bleiben unverändert.</p>
      {runs.filter(run => run.area_id === area).map(run => <p key={run.area_id}>Dynamische Szene läuft: {displayName(run.name)} · Wechsel alle {run.interval} Sekunden · Übergang {run.transition} Sekunden</p>)}
      <button disabled={busy} onClick={() => void update('dynamic/stop', {})}>Dynamik stoppen</button>{message && <p role="status">{message}</p>}
    </div>
    {adaptive?.available && <div className="card"><h3>Natürliches Licht</h3><p>Farbszenen pausieren natürliches Licht. Beim Einschalten kann es automatisch wieder starten.</p>
      {room?.reason && <p role="status">{room.reason}</p>}
      <label>Adaptive Lighting zuordnen<select className="text-input" value={room?.switch_entity_id || ''} disabled={busy} onChange={event => void update('adaptive/set', {adaptive_switch: event.target.value || null})}><option value="">Keine Zuordnung</option>{adaptive.switches?.map(item => <option key={item.entity_id} value={item.entity_id}>{displayName(item.name)}{item.available ? '' : ' · Nicht verfügbar'}</option>)}</select></label>
      {room?.switch_entity_id && <><label className="check"><input type="checkbox" checked={room.enabled} disabled={busy || !room.available} onChange={event => void update('adaptive/set', {enabled: event.target.checked})}/>Natürliches Licht aktiv</label>{!room.available && <p>Adaptive Lighting ist für diesen Raum nicht verfügbar.</p>}<label className="check"><input type="checkbox" checked={room.default_on === 'adaptive'} disabled={busy} onChange={event => void update('adaptive/set', {default_on: event.target.checked ? 'adaptive' : 'last'})}/>Beim Einschalten natürliches Licht starten</label></>}
    </div>}
  </section>;
}
