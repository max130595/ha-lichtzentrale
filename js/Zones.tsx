// Geändert für Lichtzentrale
import {displayName} from './display';
import {useEffect, useRef, useState} from 'react';
import type {Hass, Light, Zone} from './types';
export function Zones({hass, onSaved}: {hass: Hass; onSaved: () => void}) {
  const [zones, setZones] = useState<Zone[]>([]), [lights, setLights] = useState<Light[]>([]);
  const [draft, setDraft] = useState<Zone | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const lock = useRef(false), alive = useRef(false), api = useRef(hass); api.current = hass;
  async function load() {
    const [z, l] = await Promise.all([api.current.callWS<Zone[]>({type: 'lichtzentrale/zones/list'}), api.current.callWS<Light[]>({type: 'lichtzentrale/lights/list'})]);
    if (alive.current) {setZones(z); setLights(l);}
  }
  useEffect(() => {alive.current = true; void load().catch(() => {if (alive.current) setError('Zonen konnten nicht geladen werden. Bitte erneut öffnen.');}); return () => {alive.current = false;};}, []);
  async function save(remove = false) {
    if (!draft || lock.current) return;
    lock.current = true; setBusy(true); setError('');
    try {
      await api.current.callWS(remove ? {type: 'lichtzentrale/zone/delete', zone_id: draft.id} : {type: 'lichtzentrale/zone/save', zone: {...draft, id: draft.id || undefined, name: draft.name.trim()}});
      if (!alive.current) return;
      setDraft(null); onSaved(); await load();
    } catch {if (alive.current) setError('Zone konnte nicht gespeichert werden. Bitte erneut versuchen.');}
    finally {lock.current = false; if (alive.current) setBusy(false);}
  }
  return <section className="card"><h3>Zonen bearbeiten</h3>{error && <p role="alert">{error}</p>}
    {!draft ? <><button onClick={() => setDraft({id: '', name: '', entity_ids: []})}>+ Neue Zone</button>{zones.map(zone => <button key={zone.id} onClick={() => setDraft({...zone, entity_ids: [...zone.entity_ids]})}>{displayName(zone.name)}</button>)}</> : <><fieldset disabled={busy}><label>Zonenname<input className="text-input" maxLength={100} value={draft.name} onChange={event => setDraft({...draft, name: event.target.value})}/></label><p>Lampen können zu mehreren Zonen gehören.</p>{lights.filter(light => light.allowed || draft.entity_ids.includes(light.entity_id)).map(light => <label className="check" key={light.entity_id}><input type="checkbox" checked={draft.entity_ids.includes(light.entity_id)} onChange={event => setDraft({...draft, entity_ids: event.target.checked ? [...draft.entity_ids, light.entity_id] : draft.entity_ids.filter(id => id !== light.entity_id)})}/>{displayName(light.name)}{!light.allowed ? ' · Nicht freigegeben' : !light.available ? ' · Nicht verfügbar' : ''}</label>)}{draft.entity_ids.filter(id => !lights.some(light => light.entity_id === id)).map(id => <label className="check" key={id}><input type="checkbox" checked onChange={() => setDraft({...draft, entity_ids: draft.entity_ids.filter(value => value !== id)})}/>Gespeicherte Lampe nicht gefunden</label>)}</fieldset><button disabled={busy || !draft.name.trim() || !draft.entity_ids.length} onClick={() => void save()}>Zone speichern</button><button disabled={busy} onClick={() => setDraft(null)}>Abbrechen</button>{draft.id && <button disabled={busy} onClick={() => {if (window.confirm('Zone löschen? Gespeicherte Verweise bleiben erhalten.')) void save(true);}}>Zone löschen</button>}</>}
  </section>;
}
