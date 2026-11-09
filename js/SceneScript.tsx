// Geändert für Lichtzentrale
import {useEffect, useRef, useState} from 'react';
import {displayError, displayName} from './display';
import {errorText} from './sceneControls';
import type {Hass, Scene} from './types';
export interface SceneScript {entity_id: string; name: string; available: boolean}
export function useSceneScripts(hass: Hass) {
  const api = useRef(hass); api.current = hass;
  const [scripts, setScripts] = useState<SceneScript[]>([]), [loading, setLoading] = useState(true), [error, setError] = useState(''), [revision, retry] = useState(0);
  useEffect(() => {
    let alive = true; setLoading(true); setError('');
    void api.current.callWS<SceneScript[]>({type: 'lichtzentrale/scripts/list'}).then(result => {
      if (!Array.isArray(result)) throw new Error('Ungültige Skriptliste.');
      if (alive) setScripts(result.filter(item => item.entity_id.startsWith('script.')));
    }).catch(e => {if (alive) {setScripts([]); setError(`Skripte konnten nicht geladen werden: ${errorText(e)}`);}}).finally(() => {if (alive) setLoading(false);});
    return () => {alive = false;};
  }, [revision]);
  return {scripts, loading, error, retry: () => retry(value => value + 1)};
}
export function SceneScriptField({value, change, catalogue, seasonal = false}: {value?: string | null; change: (value: string | null) => void; catalogue: ReturnType<typeof useSceneScripts>; seasonal?: boolean}) {
  const missing = !!value && !catalogue.scripts.some(item => item.entity_id === value);
  return <section aria-label="Zusätzliches Skript"><label>Skript beim Szenenstart<select className="text-input" value={value || ''} onChange={event => change(event.target.value || null)}><option value="">Kein Skript</option>{missing && <option value={value!}>{value} · nicht bestätigt</option>}{catalogue.scripts.map(item => <option key={item.entity_id} value={item.entity_id}>{displayName(item.name)}{!item.available ? ' · nicht verfügbar' : ''}</option>)}</select></label>
    <small>Startet nach den Lichtbefehlen. Nicht bei Live-Probe oder Fortsetzen nach einem Neustart.{seasonal ? ' Ein hier gewähltes Skript ersetzt das Skript der passenden Teil-Szene; sonst gilt deren Skript.' : ''}</small>
    {catalogue.loading && <p role="status">Skripte werden geladen …</p>}{catalogue.error && <p role="alert" className="error">{displayError(catalogue.error)} <button type="button" onClick={catalogue.retry}>Skripte erneut laden</button></p>}
    {missing && !catalogue.loading && <p role="alert">Das gespeicherte Skript wurde nicht gefunden. Bitte neu wählen oder „Kein Skript“ wählen.</p>}
  </section>;
}
export const scriptValid = (value: string | null | undefined, catalogue: ReturnType<typeof useSceneScripts>) => !value || (!catalogue.loading && !catalogue.error && catalogue.scripts.some(item => item.entity_id === value));
export function HueSceneEditor({hass, scene, onClose, onSaved}: {hass: Hass; scene: Scene; onClose: () => void; onSaved: () => void}) {
  const [draft, setDraft] = useState(scene), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const scripts = useSceneScripts(hass), lock = useRef(false), alive = useRef(true);
  useEffect(() => {alive.current = true; return () => {alive.current = false;};}, []);
  async function save() {
    if (lock.current || !draft.name.trim() || !scriptValid(draft.start_script, scripts)) return;
    lock.current = true; setBusy(true); setError('');
    try {await hass.callWS({type: 'lichtzentrale/scene/save', scene: {...draft, name: draft.name.trim()}}); if (alive.current) onSaved();}
    catch (e) {if (alive.current) setError(`Speichern fehlgeschlagen: ${errorText(e)}`);}
    finally {lock.current = false; if (alive.current) setBusy(false);}
  }
  return <section aria-label="Hue-Szene bearbeiten"><h2>Hue-Szene bearbeiten</h2>{error && <p role="alert" className="error">{displayError(error)}</p>}<fieldset disabled={busy}><label>Szenenname<input className="text-input" value={draft.name} maxLength={100} onChange={event => setDraft({...draft, name: event.target.value})}/></label><SceneScriptField value={draft.start_script} change={start_script => setDraft({...draft, start_script})} catalogue={scripts}/><button disabled={!draft.name.trim() || !scriptValid(draft.start_script, scripts)} onClick={() => void save()}>Szene speichern</button><button onClick={onClose}>Abbrechen</button></fieldset></section>;
}
