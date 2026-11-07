// Geändert für Lichtzentrale
import {useEffect, useRef, useState} from 'react';
import type {AdaptiveStatus} from './RuntimeControls';
import type {Hass, Light, MotionBoundary, MotionConfig, MotionResponse, MotionWindow, Scene} from './types';
const failure = (error: unknown) => error instanceof Error ? error.message : typeof error === 'object' && error !== null && 'message' in error ? String(error.message) : 'Bitte Zustand prüfen.';
const newWindow = (): MotionWindow => ({start: {type: 'time', value: '00:00'}, end: {type: 'time', value: '00:00'}, action: {type: 'lights', entity_ids: null, brightness: 128}});
const newConfig = (): MotionConfig => ({enabled: false, sensor_entity_ids: [], timeout_seconds: 120, dim_before_off: false, lux_sensor_entity_id: null, lux_below: null, windows: [newWindow()]});
const boundaryValid = (value: MotionBoundary) => value.type === 'time' ? /^([01]\d|2[0-3]):[0-5]\d$/.test(value.value) : Number.isInteger(value.offset_min) && Math.abs(value.offset_min) <= 1440;

export function MotionControls({hass, area, revision = 0}: {hass: Hass; area: string; revision?: number}) {
  const api = useRef(hass); api.current = hass;
  const generation = useRef(0), lock = useRef(false);
  const [data, setData] = useState<MotionResponse | null>(null), [lights, setLights] = useState<Light[]>([]), [scenes, setScenes] = useState<Scene[]>([]);
  const [adaptive, setAdaptive] = useState(false), [editing, setEditing] = useState(false), [loading, setLoading] = useState(true), [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [message, setMessage] = useState(''), [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const counter = generation, id = ++counter.current;
    setLoading(true); setData(null); setEditing(false); setError(''); setMessage(''); setBusy(false); lock.current = false;
    void Promise.all([
      api.current.callWS<MotionResponse>({type: 'lichtzentrale/motion/get', area_id: area}),
      api.current.callWS<Light[]>({type: 'lichtzentrale/lights/list'}),
      api.current.callWS<Scene[]>({type: 'lichtzentrale/scenes/list'}),
      api.current.callWS<AdaptiveStatus>({type: 'lichtzentrale/adaptive/status'}),
    ]).then(([result, candidates, savedScenes, status]) => {
      if (id !== counter.current) return;
      if (!result?.status || !Array.isArray(result.sensors) || !Array.isArray(result.lux_sensors)) throw new Error('Ungültige Serverantwort.');
      setData(result); setLights((candidates || []).filter(light => light.allowed && /^(light|switch)\./.test(light.entity_id))); setScenes((savedScenes || []).filter(scene => scene.area_id === area));
      setAdaptive(!!status?.available && !!status.rooms?.some(room => room.area_id === area && room.available));
    }).catch(error => {if (id === counter.current) setError(`Bewegungsautomatik konnte nicht geladen werden: ${failure(error)}`);})
      .finally(() => {if (id === counter.current) setLoading(false);});
    return () => {counter.current++;};
  }, [area, revision, refresh]);
  async function update(operation: 'save' | 'set_enabled', payload: Record<string, unknown>) {
    if (lock.current || loading) return;
    lock.current = true; const id = generation.current; setBusy(true); setError(''); setMessage('');
    try {
      const result = await api.current.callWS<MotionResponse>({type: `lichtzentrale/motion/${operation}`, area_id: area, ...payload});
      if (id !== generation.current) return;
      if (!result?.status || !Array.isArray(result.sensors) || !Array.isArray(result.lux_sensors)) throw new Error('Ungültige Serverantwort.');
      setData(result); setEditing(false); setMessage('Bewegungsautomatik in Home Assistant gespeichert.');
    } catch (error) {if (id === generation.current) setError(`Speichern fehlgeschlagen: ${failure(error)} Bei unklarem Zustand neu laden.`);}
    finally {if (id === generation.current) {lock.current = false; setBusy(false);}}
  }
  return <section className="card" aria-label="Bewegungsautomatik"><h3>Bewegungsautomatik</h3>
    <p>Manuelle Änderungen pausieren die Automatik, bis der Raum für die Ausschaltzeit leer war. Neue Bewegung stellt nach dem Abdunkeln die Helligkeit wieder her.</p>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}{loading && <p role="status">Bewegungsautomatik wird geladen …</p>}
    <button disabled={busy || loading} onClick={() => setRefresh(value => value + 1)}>Bewegungsautomatik neu laden</button>
    {data && <>{data.status.last_error && <p role="alert">Letzte Ausführung: {data.status.last_error}</p>}<p aria-label="Status der Bewegungsautomatik">{data.status.paused ? 'Pausiert durch manuelle Änderung' : data.status.active ? 'Bewegungslicht aktiv' : data.status.enabled ? 'Bereit für Bewegung' : 'Automatik ausgeschaltet'}</p>
      <label className="check"><input type="checkbox" checked={data.status.enabled} disabled={busy || loading || editing || !data.config} onChange={event => void update('set_enabled', {enabled: event.target.checked})}/>Bewegungsautomatik eingeschaltet</label>
      {!editing ? <button disabled={busy || loading} onClick={() => {setEditing(true); setError(''); setMessage('');}}>Bewegungsautomatik bearbeiten</button> : <MotionEditor initial={data.config || newConfig()} data={data} lights={lights} scenes={scenes} adaptive={adaptive} disabled={busy || loading} save={config => void update('save', {config})} cancel={() => {setEditing(false); setError('');}}/>}
    </>}
  </section>;
}

function BoundaryEditor({label, value, change}: {label: string; value: MotionBoundary; change: (value: MotionBoundary) => void}) {
  return <fieldset><legend>{label}</legend><label>{label}: Bezug<select className="text-input" value={value.type === 'time' ? 'time' : value.event} onChange={event => change(event.target.value === 'time' ? {type: 'time', value: '00:00'} : {type: 'sun', event: event.target.value as 'sunrise' | 'sunset', offset_min: 0})}><option value="time">Uhrzeit</option><option value="sunrise">Sonnenaufgang</option><option value="sunset">Sonnenuntergang</option></select></label>
    {value.type === 'time' ? <label>{label}: Uhrzeit<input className="text-input" type="time" value={value.value} onChange={event => change({...value, value: event.target.value})}/></label> : <label>{label}: Versatz in Minuten<input className="text-input" type="number" min={-1440} max={1440} step={1} value={Number.isNaN(value.offset_min) ? '' : value.offset_min} onChange={event => change({...value, offset_min: event.target.value === '' ? NaN : Number(event.target.value)})}/></label>}
  </fieldset>;
}
function MotionEditor({initial, data, lights, scenes, adaptive, disabled, save, cancel}: {initial: MotionConfig; data: MotionResponse; lights: Light[]; scenes: Scene[]; adaptive: boolean; disabled: boolean; save: (config: MotionConfig) => void; cancel: () => void}) {
  const [draft, setDraft] = useState<MotionConfig>(() => structuredClone(initial));
  const sensors = (data.sensors || []).filter(sensor => sensor.entity_id.startsWith('binary_sensor.') && ['motion', 'occupancy', 'presence'].includes(sensor.device_class));
  const missingSensors = draft.sensor_entity_ids.filter(id => !sensors.some(sensor => sensor.entity_id === id));
  const luxSensors = data.lux_sensors || [];
  const valid = draft.sensor_entity_ids.length > 0 && !missingSensors.length && Number.isInteger(draft.timeout_seconds) && draft.timeout_seconds >= 1 && draft.timeout_seconds <= 86400 && (!draft.dim_before_off || draft.timeout_seconds > 20)
    && (!draft.lux_sensor_entity_id || (luxSensors.some(sensor => sensor.entity_id === draft.lux_sensor_entity_id) && draft.lux_below !== null && Number.isFinite(draft.lux_below) && draft.lux_below >= 0))
    && draft.windows.length > 0 && draft.windows.every(window => boundaryValid(window.start) && boundaryValid(window.end) && (window.action.type === 'scene' ? scenes.some(scene => window.action.type === 'scene' && scene.id === window.action.scene_id) : window.action.type === 'adaptive' ? adaptive : Number.isInteger(window.action.brightness) && window.action.brightness >= 1 && window.action.brightness <= 255 && (window.action.entity_ids === null || window.action.entity_ids.length > 0 && window.action.entity_ids.every(id => lights.some(light => light.entity_id === id)))));
  const patchWindow = (index: number, patch: Partial<MotionWindow>) => setDraft(current => ({...current, windows: current.windows.map((window, i) => i === index ? {...window, ...patch} : window)}));
  const groups = [...new Set(lights.map(light => light.area_id))].map(area => ({area, name: lights.find(light => light.area_id === area)?.area_name || 'Ohne Raum', lights: lights.filter(light => light.area_id === area)}));
  return <form onSubmit={event => {event.preventDefault(); if (!disabled && valid) save(draft);}}><fieldset disabled={disabled}><legend>Bewegungsautomatik einstellen</legend>
    <fieldset><legend>Bewegungs- und Präsenzsensoren</legend>{sensors.map(sensor => <label className="check" key={sensor.entity_id}><input type="checkbox" checked={draft.sensor_entity_ids.includes(sensor.entity_id)} onChange={() => setDraft({...draft, sensor_entity_ids: draft.sensor_entity_ids.includes(sensor.entity_id) ? draft.sensor_entity_ids.filter(id => id !== sensor.entity_id) : [...draft.sensor_entity_ids, sensor.entity_id]})}/>{sensor.name}{sensor.area_name ? ` · ${sensor.area_name}` : ''}{!sensor.available && ' · Nicht verfügbar'}</label>)}{!sensors.length && <p>Keine passenden Sensoren gefunden.</p>}
      {missingSensors.map(id => <p key={id}>{id}: Sensor nicht mehr vorhanden. <button type="button" onClick={() => setDraft({...draft, sensor_entity_ids: draft.sensor_entity_ids.filter(item => item !== id)})}>Sensor entfernen</button></p>)}
    </fieldset>
    <label>Ausschaltzeit in Sekunden<input className="text-input" type="number" min={1} max={86400} step={1} value={Number.isNaN(draft.timeout_seconds) ? '' : draft.timeout_seconds} onChange={event => setDraft({...draft, timeout_seconds: event.target.value === '' ? NaN : Number(event.target.value)})}/></label>
    <label className="check"><input type="checkbox" checked={draft.dim_before_off} onChange={event => setDraft({...draft, dim_before_off: event.target.checked})}/>20 Sekunden vorher auf 30 % abdunkeln</label><p>Nur bei mehr als 20 Sekunden Ausschaltzeit. Schalter werden nie gedimmt. Dunklere Nachtlichter werden nicht heller.</p>
    <label>Lux-Sensor (optional)<select className="text-input" value={draft.lux_sensor_entity_id || ''} onChange={event => setDraft({...draft, lux_sensor_entity_id: event.target.value || null, lux_below: event.target.value ? draft.lux_below ?? 50 : null})}><option value="">Keine Lux-Bedingung</option>{draft.lux_sensor_entity_id && !luxSensors.some(sensor => sensor.entity_id === draft.lux_sensor_entity_id) && <option value={draft.lux_sensor_entity_id}>Sensor nicht mehr vorhanden</option>}{luxSensors.map(sensor => <option key={sensor.entity_id} value={sensor.entity_id}>{sensor.name}{!sensor.available && ' · Nicht verfügbar'}</option>)}</select></label>
    {draft.lux_sensor_entity_id && <label>Nur unter Helligkeit in lx<input className="text-input" type="number" min={0} step="any" value={draft.lux_below === null || Number.isNaN(draft.lux_below) ? '' : draft.lux_below} onChange={event => setDraft({...draft, lux_below: event.target.value === '' ? null : Number(event.target.value)})}/></label>}
    <p>Das erste passende Zeitfenster gilt. Fenster dürfen über Mitternacht reichen. Gleiche Uhrzeiten bedeuten ganztägig.</p>
    {draft.windows.map((window, index) => <fieldset key={index}><legend>Zeitfenster {index + 1}</legend>
      <BoundaryEditor label={`Fenster ${index + 1} Beginn`} value={window.start} change={start => patchWindow(index, {start})}/><BoundaryEditor label={`Fenster ${index + 1} Ende`} value={window.end} change={end => patchWindow(index, {end})}/>
      <label>Fenster {index + 1} Aktion<select className="text-input" value={window.action.type} onChange={event => patchWindow(index, {action: event.target.value === 'scene' ? {type: 'scene', scene_id: ''} : event.target.value === 'adaptive' ? {type: 'adaptive'} : {type: 'lights', entity_ids: null, brightness: 128}})}><option value="lights">Lampenauswahl / Nachtlicht</option><option value="scene">Szene</option>{adaptive && <option value="adaptive">Natürliches Licht</option>}{!adaptive && window.action.type === 'adaptive' && <option value="adaptive" disabled>Bisherige Aktion nicht verfügbar</option>}</select></label>
      {window.action.type === 'scene' && <label>Fenster {index + 1} Szene<select className="text-input" value={window.action.scene_id} onChange={event => patchWindow(index, {action: {type: 'scene', scene_id: event.target.value}})}><option value="">Szene wählen</option>{!scenes.some(scene => window.action.type === 'scene' && scene.id === window.action.scene_id) && window.action.scene_id && <option value={window.action.scene_id}>Szene nicht mehr vorhanden</option>}{scenes.map(scene => <option value={scene.id} key={scene.id}>{scene.name}</option>)}</select></label>}
      {window.action.type === 'lights' && <><label>Fenster {index + 1} Lichtauswahl<select className="text-input" value={window.action.entity_ids === null ? 'room' : 'selected'} onChange={event => {if (window.action.type === 'lights') patchWindow(index, {action: {...window.action, entity_ids: event.target.value === 'room' ? null : []}});}}><option value="room">Ganzer Raum</option><option value="selected">Einzelne Lampen und Schalter</option></select></label>
        {window.action.entity_ids !== null && <>{groups.map(group => <fieldset key={group.area || 'unassigned'}><legend>{group.name}</legend>{group.lights.map(light => <label className="check" key={light.entity_id}><input type="checkbox" checked={window.action.type === 'lights' && !!window.action.entity_ids?.includes(light.entity_id)} onChange={() => {if (window.action.type === 'lights') {const ids = window.action.entity_ids || []; patchWindow(index, {action: {...window.action, entity_ids: ids.includes(light.entity_id) ? ids.filter(id => id !== light.entity_id) : [...ids, light.entity_id]}});}}}/>{light.name}{light.entity_id.startsWith('switch.') && ' · Nur Ein/Aus'}{!light.available && ' · Nicht verfügbar'}</label>)}</fieldset>)}{window.action.entity_ids.filter(id => !lights.some(light => light.entity_id === id)).map(id => <p key={id}>{id}: Nicht mehr freigegeben oder vorhanden. <button type="button" onClick={() => {if (window.action.type === 'lights') patchWindow(index, {action: {...window.action, entity_ids: window.action.entity_ids?.filter(item => item !== id) || []}});}}>Licht entfernen</button></p>)}</>}
        <label>Fenster {index + 1} Helligkeit: {Math.round(window.action.brightness / 255 * 100)} %<input aria-label={`Fenster ${index + 1} Helligkeit`} type="range" min={1} max={255} value={window.action.brightness} onChange={event => {if (window.action.type === 'lights') patchWindow(index, {action: {...window.action, brightness: Number(event.target.value)}});}}/></label><p>Helligkeit gilt nur für dimmbare Lampen.</p>
      </>}
      <button type="button" disabled={index === 0} onClick={() => setDraft({...draft, windows: draft.windows.map((item, i) => i === index - 1 ? window : i === index ? draft.windows[index - 1] : item)})}>Fenster {index + 1} nach oben</button>
      <button type="button" onClick={() => setDraft({...draft, windows: draft.windows.filter((_, i) => i !== index)})}>Fenster {index + 1} entfernen</button>
    </fieldset>)}
    <button type="button" onClick={() => setDraft({...draft, windows: [...draft.windows, newWindow()]})}>Zeitfenster hinzufügen</button>
    {!valid && <p>Mindestens einen Sensor und ein vollständiges Zeitfenster wählen. Ungültige oder entfernte Auswahlen korrigieren.</p>}
    <button type="submit" disabled={!valid}>Bewegungsautomatik speichern</button><button type="button" className="secondary" onClick={cancel}>Abbrechen</button>
  </fieldset></form>;
}
