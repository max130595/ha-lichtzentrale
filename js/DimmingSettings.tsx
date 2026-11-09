// Geändert für Lichtzentrale
import {useEffect, useId, useRef, useState} from 'react';
import type {Hass} from './types';
import type {NavigationGuard} from './sceneControls';

type Settings = {dim_min_pct: number};
const valid = (value: unknown): value is number => typeof value === 'number' && Number.isInteger(value) && value >= 1 && value <= 20;

/** Only a confirmed server response changes the saved value. No lamp commands. */
export function DimmingSettings({hass, registerGuard}: {hass: Hass; registerGuard?: (guard: NavigationGuard) => void}) {
  const api = useRef(hass); api.current = hass;
  const generation = useRef(0), lock = useRef(false);
  const [saved, setSaved] = useState<number | null>(null), [draft, setDraft] = useState('');
  const [loading, setLoading] = useState(true), [saving, setSaving] = useState(false);
  const [error, setError] = useState(''), [success, setSuccess] = useState('');
  const hintId = useId(), validationId = useId();
  const value = draft.trim() === '' ? NaN : Number(draft);
  const invalid = !valid(value);
  async function load() {
    if (lock.current) return;
    lock.current = true; setLoading(true); setError('');
    const current = generation.current;
    try {
      const result = await api.current.callWS<Settings>({type: 'lichtzentrale/settings/get'});
      if (!valid(result?.dim_min_pct)) throw new Error('Invalid settings');
      if (current === generation.current) {setSaved(result.dim_min_pct); setDraft(String(result.dim_min_pct));}
    } catch {
      if (current === generation.current) setError('Einstellungen konnten nicht geladen werden. Bitte erneut versuchen.');
    } finally {
      if (current === generation.current) {lock.current = false; setLoading(false);}
    }
  }
  useEffect(() => {
    const revision = generation;
    void load();
    return () => {revision.current++; lock.current = false;};
  }, []);
  useEffect(() => {
    registerGuard?.(saving ? async () => !lock.current : null);
    return () => registerGuard?.(null);
  }, [registerGuard, saving]);
  async function save() {
    if (lock.current || saved === null || invalid || value === saved) return;
    const current = generation.current;
    lock.current = true; setSaving(true); setError(''); setSuccess('');
    try {
      const result = await api.current.callWS<Settings>({type: 'lichtzentrale/settings/dimming', dim_min_pct: value});
      if (!valid(result?.dim_min_pct) || result.dim_min_pct !== value) throw new Error('Unconfirmed settings');
      if (current === generation.current) {setSaved(result.dim_min_pct); setSuccess(`Dimm-Untergrenze von ${result.dim_min_pct} % in Home Assistant gespeichert.`);}
    } catch {
      if (current === generation.current) setError('Speichern nicht bestätigt. Bitte erneut versuchen oder die Einstellungen neu öffnen.');
    } finally {
      if (current === generation.current) {lock.current = false; setSaving(false);}
    }
  }
  return <section className="card" aria-label="Einstellungen">
    <h2>Einstellungen</h2>
    <p>Beim Herunterdimmen bleiben eingeschaltete Lampen mindestens so hell. Ausschalten funktioniert weiterhin wie gewohnt.</p>
    {loading && <p role="status">Einstellungen werden geladen …</p>}
    {error && <p role="alert" className="error">{error}</p>}
    {!loading && saved === null && <button onClick={() => void load()}>Einstellungen erneut laden</button>}
    {saved !== null && <>
      <label>Dimm-Untergrenze (%)<input className="text-input" type="number" inputMode="numeric" min="1" max="20" step="1" value={draft} disabled={saving}
        aria-describedby={`${hintId}${invalid ? ` ${validationId}` : ''}`} aria-invalid={invalid}
        onChange={event => {setDraft(event.target.value); setSuccess(''); setError('');}}/></label>
      <p id={hintId}>Global für alle dimmbaren Lampen. 1 bis 20 %, Standard: 1 %. Reine An/Aus-Lichter werden nicht gedimmt.</p>
      {invalid && <p id={validationId} role="alert">Bitte eine ganze Zahl von 1 bis 20 eingeben.</p>}
      <button disabled={saving || invalid || value === saved} onClick={() => void save()}>{saving ? 'Wird gespeichert …' : 'Untergrenze speichern'}</button>
      {saving && <p role="status">Serverbestätigung wird abgewartet. Bitte hier bleiben.</p>}
      {success && <p role="status" className="notice">{success}</p>}
    </>}
  </section>;
}
