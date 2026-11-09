// Geändert für Lichtzentrale
import {useCallback, useEffect, useRef, useState} from 'react';
import {boundaryValid} from './BindingTimeWindows';
import {displayName, displayError} from './display';
import type {Hass, MotionBoundary, Room, Scene} from './types';
import type {NavigationGuard} from './sceneControls';
import type {VacationConfig, VacationRoom, VacationStatus, VacationNotifyService} from './VacationTypes';

const integer = (n: number, min: number, max: number) => Number.isInteger(n) && n >= min && n <= max;
const canonical = (value: unknown): unknown => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object' ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => [k, canonical(v)])) : value;
const same = (a: unknown, b: unknown) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
function Boundary({label, value, change}: {label: string; value: MotionBoundary; change: (value: MotionBoundary) => void}) {
  return <fieldset><legend>{label}</legend><label>{label}: Bezug<select className="text-input" value={value.type === 'time' ? 'time' : value.event} onChange={e => change(e.target.value === 'time' ? {type: 'time', value: '22:30'} : {type: 'sun', event: e.target.value as 'sunrise' | 'sunset', offset_min: 0})}><option value="time">Uhrzeit</option><option value="sunset">Sonnenuntergang</option><option value="sunrise">Sonnenaufgang</option></select></label>{value.type === 'time' ? <label>{label}: Uhrzeit<input className="text-input" type="time" value={value.value} onChange={e => change({...value, value: e.target.value})}/></label> : <label>{label}: Versatz in Minuten<input className="text-input" type="number" min={-1440} max={1440} value={Number.isNaN(value.offset_min) ? '' : value.offset_min} onChange={e => change({...value, offset_min: e.target.value === '' ? NaN : Number(e.target.value)})}/></label>}</fieldset>;
}
export function Vacation({hass, registerGuard}: {hass: Hass; registerGuard?: (guard: NavigationGuard) => void}) {
  const api = useRef(hass); api.current = hass;
  const generation = useRef(0), operation = useRef(0), lock = useRef(false);
  const [status, setStatus] = useState<VacationStatus | null>(null), [draft, setDraft] = useState<VacationConfig | null>(null);
  const [rooms, setRooms] = useState<Room[]>([]), [scenes, setScenes] = useState<Scene[]>([]), [services, setServices] = useState<VacationNotifyService[]>([]);
  const [refreshError, setRefreshError] = useState('');
  const [until, setUntil] = useState(''), [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const dirty = !!status && (!same(draft, status.config) || until !== (status.until ?? ''));
  const guardState = useRef({dirty}); guardState.current = {dirty};
  useEffect(() => {
    registerGuard?.(busy || dirty ? async () => !lock.current && (!guardState.current.dirty || window.confirm('Ungespeicherte Urlaubseinstellungen verwerfen?')) : null);
    return () => registerGuard?.(null);
  }, [registerGuard, busy, dirty]);
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {if (lock.current || guardState.current.dirty) {e.preventDefault(); e.returnValue = '';}};
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn);
  }, []);
  const accept = useCallback((result: VacationStatus) => {setStatus(result); setDraft(structuredClone(result.config)); setUntil(result.until ?? '');}, []);
  const load = useCallback(async () => {
    if (lock.current) return;
    operation.current++; lock.current = true; setLoading(true); setError(''); setNotice(''); const rev = generation.current;
    try {
      const [s, r, c, n] = await Promise.all([api.current.callWS<VacationStatus>({type: 'lichtzentrale/vacation/get'}), api.current.callWS<Room[]>({type: 'lichtzentrale/rooms/list'}), api.current.callWS<Scene[]>({type: 'lichtzentrale/scenes/list'}), api.current.callWS<VacationNotifyService[]>({type: 'lichtzentrale/vacation/notify_services'})]);
      if (!s?.config || !Array.isArray(s.plan)) throw new Error('Ungültige Serverantwort.');
      if (generation.current === rev) {accept(s); setRooms(r); setScenes(c); setServices(n);}
    } catch {if (generation.current === rev) setError('Urlaubsmodus konnte nicht geladen werden. Bitte erneut versuchen.');}
    finally {if (generation.current === rev) {lock.current = false; setLoading(false);}}
  }, [accept]);
  useEffect(() => {const gen = generation; void load(); return () => {gen.current++; lock.current = false;};}, [load]);
  const hasStatus = status !== null;
  useEffect(() => {
    if (!hasStatus) return;
    let active = true, pending = false;
    const timer = window.setInterval(async () => {
      if (lock.current || pending) return;
      pending = true;
      const rev = operation.current;
      try {
        const result = await api.current.callWS<VacationStatus>({type: 'lichtzentrale/vacation/get'});
        if (!active || lock.current || rev !== operation.current) return;
        if (!result?.config || !Array.isArray(result.plan)) throw new Error('Ungültige Serverantwort.');
        // The response may arrive after the user started editing. Check the latest
        // dirty flag, not the flag when the read began. Mutations supersede reads.
        if (guardState.current.dirty) setStatus(result);
        else accept(result);
        setRefreshError('');
      } catch {
        if (active && !lock.current && rev === operation.current) setRefreshError('Statusaktualisierung fehlgeschlagen. Die Anzeige kann veraltet sein; der nächste Versuch erfolgt automatisch.');
      } finally {pending = false;}
    }, 10000);
    return () => {active = false; window.clearInterval(timer);};
  }, [accept, hasStatus]);
  const valid = !!draft && integer(draft.max_rooms, 1, 20) && draft.rooms.every(r => rooms.some(room => room.area_id === r.area_id && room.lights.some(l => l.allowed)) && Number.isFinite(r.weight) && r.weight >= 0 && r.weight <= 100 && (r.on_behavior.mode === 'last' || r.on_behavior.mode === 'brightness' && integer(r.on_behavior.brightness, 1, 255) || r.on_behavior.mode === 'scene' && scenes.some(s => r.on_behavior.mode === 'scene' && s.id === r.on_behavior.scene_id && s.area_id === r.area_id))) && [...Object.values(draft.evening), draft.morning.start, draft.morning.end].every(boundaryValid) && (!draft.notify_service || services.some(s => s.service === draft.notify_service));
  const dateValid = !until || /^\d{4}-\d{2}-\d{2}$/.test(until);
  async function perform(action: 'save' | 'set' | 'test', enabled?: boolean) {
    if (lock.current || !draft || !status) return;
    if (action === 'test' && !window.confirm('Probelauf jetzt starten? Für 5 Minuten werden echte Lampen in den gespeicherten ausgewählten Räumen geschaltet.')) return;
    operation.current++; lock.current = true; setBusy(true); setError(''); setNotice(''); const rev = generation.current;
    try {
      const result = await api.current.callWS<VacationStatus>({type: `lichtzentrale/vacation/${action}`, ...(action === 'save' ? {config: draft, until: until || null} : action === 'set' ? {enabled, until: until || null} : {})});
      if (!result?.config || !Array.isArray(result.plan) || action === 'set' && (result.enabled !== enabled || result.until !== (until || null)) || action === 'test' && !result.testing || action === 'save' && (!same(result.config, draft) || result.until !== (until || null))) throw new Error('Änderung nicht bestätigt.');
      if (generation.current === rev) {accept(result); if (action === 'set' && !same(draft, status.config)) setDraft(draft); setNotice(action === 'save' ? 'Urlaubseinstellungen in Home Assistant gespeichert.' : action === 'test' ? 'Probelauf vom Server bestätigt. Er schaltet echte Lampen für 5 Minuten.' : result.enabled ? 'Urlaubsmodus eingeschaltet.' : 'Urlaubsmodus ausgeschaltet.');}
    } catch (e) {if (generation.current === rev) setError(displayError(`Nicht bestätigt: ${e instanceof Error ? e.message : 'Anfrage fehlgeschlagen.'} ${action === 'save' ? 'Deine Eingaben bleiben erhalten. Du kannst erneut speichern.' : 'Bitte zuerst den Status aktualisieren, bevor du erneut schaltest.'}`));}
    finally {if (generation.current === rev) {lock.current = false; setBusy(false);}}
  }
  function change(config: VacationConfig) {setDraft(config); setNotice('');}
  function patchRoom(id: string, patch: Partial<VacationRoom>) {if (draft) change({...draft, rooms: draft.rooms.map(r => r.area_id === id ? {...r, ...patch} : r)});}
  const name = (id: string) => displayName(rooms.find(r => r.area_id === id)?.name, 'Nicht mehr verfügbarer Raum');
  const clock = (value: string) => {const d = new Date(value); return Number.isNaN(d.getTime()) ? 'Zeit nicht verfügbar' : d.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit', ...(status?.time_zone ? {timeZone: status.time_zone} : {})});};
  return <section className="card vacation" aria-label="Urlaubsmodus"><h2>Urlaubsmodus</h2><p>Abends belebt, morgens kurz an. Du schaltest die Simulation selbst ein.</p>
    {loading && <p role="status">Urlaubsmodus wird geladen …</p>}{error && <p role="alert" className="error">{error}</p>}{refreshError && <p role="status" className="notice">{refreshError}</p>}{notice && <p role="status" className="notice">{notice}</p>}
    {!loading && !status && <button onClick={() => void load()}>Urlaubsmodus erneut laden</button>}
    {status && draft && <><div className="vacation-status"><strong>{status.testing ? 'Probelauf läuft' : status.enabled ? 'Urlaubsmodus ist an' : 'Urlaubsmodus ist aus'}</strong><small>Nur manuell · keine Anwesenheitserkennung</small></div>
      <label>Enddatum (optional, einschließlich)<input className="text-input" type="date" disabled={busy || loading} value={until} onChange={e => {setUntil(e.target.value); setNotice('');}}/></label>
      <button role="switch" aria-checked={status.enabled} disabled={busy || loading || !dateValid || (!status.enabled && (status.testing || !valid || !draft.rooms.length || !same(draft, status.config)))} onClick={() => void perform('set', !status.enabled)}>{status.enabled ? 'Urlaubsmodus ausschalten' : 'Urlaubsmodus einschalten'}</button>
      {until !== (status.until ?? '') && <button disabled={busy || loading || !dateValid} onClick={() => void perform('set', status.enabled)}>Enddatum übernehmen</button>}
      <p>Währenddessen pausieren Zeitpläne, Bewegungsautomatik, Grundhelligkeit und Taster-Ambiente. Taster bleiben bedienbar und nehmen ihren Raum für diesen Abschnitt heraus.</p>
      <details><summary>Räume und Zonen · {draft.rooms.length} ausgewählt</summary><fieldset disabled={busy || loading}><legend>Teilnehmende Räume</legend>
        {rooms.filter(r => r.lights.some(l => l.allowed)).map(room => {const selected = draft.rooms.find(r => r.area_id === room.area_id); return <div className="vacation-room" key={room.area_id}><label className="check"><input type="checkbox" checked={!!selected} onChange={e => change({...draft, rooms: e.target.checked ? [...draft.rooms, {area_id: room.area_id, type: 'living', weight: 1, on_behavior: {mode: 'last'}}] : draft.rooms.filter(r => r.area_id !== room.area_id)})}/><span>{displayName(room.name)}<small>{room.kind === 'zone' ? 'Zone' : 'Raum'}</small></span></label>{selected && <>
          <label>{displayName(room.name)}: Typ<select className="text-input" value={selected.type} onChange={e => patchRoom(room.area_id, {type: e.target.value as VacationRoom['type']})}><option value="living">Wohnraum · 45–150 min</option><option value="passage">Durchgang · 2–12 min</option><option value="bedroom">Schlafraum · 10–40 min</option></select></label>
          <label>{displayName(room.name)}: Häufigkeit (Gewicht)<input className="text-input" type="number" min={0} max={100} step="any" value={Number.isNaN(selected.weight) ? '' : selected.weight} onChange={e => patchRoom(room.area_id, {weight: e.target.value === '' ? NaN : Number(e.target.value)})}/></label>
          <label>{displayName(room.name)}: Einschalten<select className="text-input" value={selected.on_behavior.mode} onChange={e => patchRoom(room.area_id, {on_behavior: e.target.value === 'scene' ? {mode: 'scene', scene_id: ''} : e.target.value === 'brightness' ? {mode: 'brightness', brightness: 128} : {mode: 'last'}})}><option value="last">Letzter Zustand</option><option value="brightness">Feste Helligkeit</option><option value="scene">Eine Szene</option></select></label>
          {selected.on_behavior.mode === 'brightness' && <label className="slider">Helligkeit: {Math.max(1, Math.round(selected.on_behavior.brightness / 255 * 100))} %<input aria-label={`${displayName(room.name)}: Helligkeit`} type="range" min={1} max={100} value={Math.max(1, Math.round(selected.on_behavior.brightness / 255 * 100))} onChange={e => patchRoom(room.area_id, {on_behavior: {mode: 'brightness', brightness: Math.round(Number(e.target.value) * 255 / 100)}})}/><small>Reine Lichtschalter erhalten nur An/Aus.</small></label>}
          {selected.on_behavior.mode === 'scene' && <label>{displayName(room.name)}: Szene<select className="text-input" value={selected.on_behavior.scene_id} onChange={e => patchRoom(room.area_id, {on_behavior: {mode: 'scene', scene_id: e.target.value}})}><option value="">Szene wählen</option>{scenes.filter(s => s.area_id === room.area_id).map(s => <option key={s.id} value={s.id}>{displayName(s.name)}</option>)}</select></label>}
        </>}</div>;})}
        {draft.rooms.filter(r => !rooms.some(room => room.area_id === r.area_id && room.lights.some(l => l.allowed))).map(r => <p key={r.area_id}>Ein ausgewählter Raum ist nicht mehr verfügbar. <button onClick={() => change({...draft, rooms: draft.rooms.filter(item => item !== r)})}>Aus Auswahl entfernen</button></p>)}
      </fieldset></details>
      <details><summary>Zeitfenster und Optionen</summary><fieldset disabled={busy || loading}><legend>Abend</legend><p>Lokale Home-Assistant-Zeit. Das Ende wird täglich neu zwischen beiden Grenzen gewählt.</p>{(['start', 'end_earliest', 'end_latest'] as const).map((key, i) => <Boundary key={key} label={['Abend beginnt', 'Abend endet frühestens', 'Abend endet spätestens'][i]} value={draft.evening[key]} change={value => change({...draft, evening: {...draft.evening, [key]: value}})}/>)}
        <label className="check"><input type="checkbox" checked={draft.morning.enabled} onChange={e => change({...draft, morning: {...draft.morning, enabled: e.target.checked}})}/>Morgens kurz einschalten</label><p>1–2 Räume für insgesamt 10–30 Minuten, nur wenn es noch dunkel ist.</p>{draft.morning.enabled && <><Boundary label="Morgen beginnt" value={draft.morning.start} change={start => change({...draft, morning: {...draft.morning, start}})}/><Boundary label="Morgen endet" value={draft.morning.end} change={end => change({...draft, morning: {...draft.morning, end}})}/></>}
        <label>Maximal gleichzeitig eingeschaltete Räume<input className="text-input" type="number" min={1} max={20} value={Number.isNaN(draft.max_rooms) ? '' : draft.max_rooms} onChange={e => change({...draft, max_rooms: e.target.value === '' ? NaN : Number(e.target.value)})}/></label>
        <label className="check"><input type="checkbox" checked={draft.safety_off} onChange={e => change({...draft, safety_off: e.target.checked})}/>Am Ende jedes Abschnitts alles ausschalten (empfohlen)</label>
        <label className="check"><input type="checkbox" checked={draft.learn_history} onChange={e => change({...draft, learn_history: e.target.checked})}/>Aus dem Verlauf lernen</label><small>Die letzten 14 Tage, mit ±20 Minuten Abwechslung. Ohne genügend Daten gilt der Zufallsplan.</small>
        <label>Push-Hinweis beim Ein- und Ausschalten<select className="text-input" value={draft.notify_service ?? ''} onChange={e => change({...draft, notify_service: e.target.value || null})}><option value="">Kein Hinweis</option>{draft.notify_service && !services.some(s => s.service === draft.notify_service) && <option value={draft.notify_service}>Dienst nicht mehr verfügbar</option>}{services.map(s => <option key={s.service} value={s.service}>{displayName(s.name, 'Benachrichtigungsdienst')}</option>)}</select></label>
      </fieldset></details>
      {!valid && <p role="alert">Bitte gültige Zeitgrenzen, Gewichte, Raumanzahl und passende Szenen oder Benachrichtigungsdienste wählen.</p>}
      <button disabled={busy || loading || !valid || !dateValid || !dirty} onClick={() => void perform('save')}>Urlaubseinstellungen speichern</button>{dirty && <p>Ungespeicherte Änderungen. Vor dem Einschalten oder Probelauf zuerst speichern.</p>}
      <section aria-label="Plan heute"><h3>Plan heute</h3><p>{status.next_switch ? `Nächste Schaltung: ${clock(status.next_switch.at)} · ${name(status.next_switch.area_id)} · ${status.next_switch.on ? 'an' : 'aus'}` : 'Keine nächste Schaltung geplant.'}</p>{status.plan.length ? <ol className="vacation-timeline">{status.plan.map((entry, i) => <li key={`${entry.area_id}-${entry.start}-${i}`}><strong>{clock(entry.start)}–{clock(entry.end)}</strong><span>{name(entry.area_id)}</span><small>{entry.section === 'test' ? 'Probelauf' : entry.section === 'morning' ? 'Morgens' : 'Abends'}{status.excluded.includes(entry.area_id) ? ' · Durch Handbedienung ausgenommen' : ''}</small></li>)}</ol> : <p>Noch kein Plan. Nach dem Einschalten wird der aktuelle Abschnitt geplant; verpasste Schaltungen werden nicht nachgeholt.</p>}
        {status.last_error && <p role="alert">{displayError(status.last_error)}</p>}
        {status.notes?.map((note, i) => <p key={i} className="notice">{displayError(note)}</p>)}
        {status.testing && <button disabled={busy || loading} onClick={() => void perform('set', false)}>Probelauf beenden</button>}
        <p>Der Probelauf schaltet <strong>echte Lampen für 5 Minuten</strong>, nur in den gespeicherten ausgewählten Räumen.</p><button disabled={busy || loading || dirty || !valid || !draft.rooms.length || status.testing || status.enabled} onClick={() => void perform('test')}>Probelauf 5 min · echte Lampen</button>
      </section><button disabled={busy || loading} onClick={() => {if (!dirty || window.confirm('Ungespeicherte Urlaubseinstellungen verwerfen und Status laden?')) void load();}}>Urlaubsstatus aktualisieren</button>
      {busy && <p role="status">Serverbestätigung wird abgewartet. Bitte hier bleiben.</p>}
    </>}
  </section>;
}
