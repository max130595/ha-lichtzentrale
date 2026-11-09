// Geändert für Lichtzentrale
import {useEffect, useRef, useState} from 'react';
import {displayError, displayName} from './display';
import type {Hass} from './types';

type Choice = {entity_id: string; name: string; available: boolean; domain?: string};
type Options = {sources: Choice[]; targets: Choice[]};
export interface ReplacementPreview {
  old_entity_id: string; new_entity_id: string; source_name: string; target_name: string;
  preview_token: string; can_replace: boolean;
  entries: {kind: string; name: string; count: number}[];
  warnings: string[]; conflicts: string[];
}

/** This workflow only migrates saved configuration. A preview never controls lights. */
export function ReplaceLight({hass}: {hass: Hass}) {
  const [options, setOptions] = useState<Options>({sources: [], targets: []});
  const [oldId, setOldId] = useState(''), [newId, setNewId] = useState('');
  const [preview, setPreview] = useState<ReplacementPreview | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [success, setSuccess] = useState(''), [loaded, setLoaded] = useState(false);
  const alive = useRef(false), lock = useRef(false), revision = useRef(0), api = useRef(hass);
  api.current = hass;
  async function load() {
    const result = await api.current.callWS<Options>({type: 'lichtzentrale/light/replace_options'});
    if (!result || !Array.isArray(result.sources) || !Array.isArray(result.targets)
      || [...result.sources, ...result.targets].some(item => !item || typeof item.entity_id !== 'string' || typeof item.name !== 'string')) {
      throw new Error('Die Lampenliste ist unvollständig. Bitte erneut öffnen.');
    }
    if (alive.current) {setOptions(result); setLoaded(true);}
  }
  useEffect(() => {
    alive.current = true;
    void load().catch(() => {if (alive.current) setError('Lampen konnten nicht geladen werden. Bitte erneut öffnen.');});
    return () => {alive.current = false; revision.current += 1;};
  }, []);
  function resetPreview() {revision.current += 1; setPreview(null); setError(''); setSuccess('');}
  function failure(reason: unknown, fallback: string) {
    const message = reason && typeof reason === 'object' && 'message' in reason ? String(reason.message) : '';
    return displayError(message || fallback);
  }
  async function inspect() {
    if (lock.current || !oldId || !newId || oldId === newId) return;
    lock.current = true; setBusy(true); setError(''); setSuccess(''); setPreview(null);
    const current = ++revision.current;
    try {
      const result = await api.current.callWS<ReplacementPreview>({type: 'lichtzentrale/light/replace_preview', old_entity_id: oldId, new_entity_id: newId});
      if (!result || !Array.isArray(result.entries) || !Array.isArray(result.warnings) || !Array.isArray(result.conflicts)
        || typeof result.preview_token !== 'string' || typeof result.can_replace !== 'boolean') throw new Error('Die Vorschau ist unvollständig. Bitte neu prüfen.');
      if (alive.current && current === revision.current && result.old_entity_id === oldId && result.new_entity_id === newId) setPreview(result);
    } catch (reason) {if (alive.current && current === revision.current) setError(failure(reason, 'Die Vorschau konnte nicht geladen werden.'));}
    finally {lock.current = false; if (alive.current) setBusy(false);}
  }
  async function replace() {
    if (lock.current || !preview?.can_replace || preview.old_entity_id !== oldId || preview.new_entity_id !== newId) return;
    lock.current = true; setBusy(true); setError('');
    const current = ++revision.current;
    try {
      const result = await api.current.callWS<ReplacementPreview & {replaced: boolean; runtime_warnings?: string[]}>({type: 'lichtzentrale/light/replace', old_entity_id: oldId, new_entity_id: newId, preview_token: preview.preview_token});
      if (!alive.current || current !== revision.current) return;
      if (!result.replaced) throw new Error('Das Ersetzen wurde vom Server nicht bestätigt. Bitte neu prüfen.');
      setPreview(null); setOldId(''); setNewId('');
      setSuccess(`${displayName(preview.source_name)} wurde durch ${displayName(preview.target_name)} ersetzt. ${(result.runtime_warnings || []).map(displayError).join(' ')}`.trim());
      await load();
    } catch (reason) {
      if (alive.current && current === revision.current) {
        setPreview(null);
        setError(failure(reason, 'Nicht ersetzt. Bitte die aktuelle Vorschau erneut prüfen.'));
      }
    } finally {lock.current = false; if (alive.current) setBusy(false);}
  }
  return <section className="card" aria-label="Lampe ersetzen">
    <h3>Lampe ersetzen</h3>
    <p>Überträgt Freigaben, Szenen, Positionen und Regeln auf eine andere Lampe. Die neue Lampe muss bereits freigegeben sein.</p>
    {error && <p role="alert">{error}</p>}{success && <p role="status">{success}</p>}
    {!loaded && !error && <p>Lampen werden geladen …</p>}
    {loaded && <>
      <fieldset disabled={busy}>
        <label>Bisherige Lampe<select className="text-input" value={oldId} onChange={event => {setOldId(event.target.value); resetPreview();}}>
          <option value="">Lampe auswählen</option>{options.sources.map(item => <option key={item.entity_id} value={item.entity_id}>{displayName(item.name)}{!item.available ? ' · Nicht verfügbar' : ''}</option>)}
        </select></label>
        <label>Neue Lampe<select className="text-input" value={newId} onChange={event => {setNewId(event.target.value); resetPreview();}}>
          <option value="">Freigegebene Lampe auswählen</option>{options.targets.filter(item => item.entity_id !== oldId).map(item => <option key={item.entity_id} value={item.entity_id} disabled={!item.available}>{displayName(item.name)}{item.domain === 'switch' ? ' · Nur An/Aus' : ''}{!item.available ? ' · Nicht verfügbar' : ''}</option>)}
        </select></label>
      </fieldset>
      {!options.targets.length && <p>Bitte zuerst eine neue Lampe unter Freigaben erlauben.</p>}
      <button disabled={busy || !oldId || !newId || oldId === newId} onClick={() => void inspect()}>Betroffene Einträge prüfen</button>
    </>}
    {preview && <div className="replacement-preview">
      <h4>{displayName(preview.source_name)} → {displayName(preview.target_name)}</h4>
      <p>{preview.entries.length} betroffene Einträge. Noch nichts geändert.</p>
      <ul>{preview.entries.map((entry, index) => <li key={`${entry.kind}-${index}`}>{displayName(entry.name, 'Gespeicherter Eintrag')} · {entry.count} {entry.count === 1 ? 'Verweis' : 'Verweise'}</li>)}</ul>
      {preview.warnings.map((warning, index) => <p key={index}>{displayError(warning)}</p>)}
      {preview.conflicts.length > 0 && <div role="alert"><p>Nicht ersetzbar: Bitte widersprüchliche Werte zuerst bereinigen.</p><ul>{preview.conflicts.map((conflict, index) => <li key={index}>{displayError(conflict)}</li>)}</ul></div>}
      <button disabled={busy || !preview.can_replace} onClick={() => void replace()}>Diese Ersetzung bestätigen</button>
      <button disabled={busy} onClick={resetPreview}>Abbrechen</button>
    </div>}
  </section>;
}
