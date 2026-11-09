// Geändert für Lichtzentrale
import {displayName, displayError} from './display';
import {useEffect, useRef, useState} from 'react';
import type {BrightnessConfig, BrightnessResponse, BrightnessStage, Hass, Light, Room, MotionBoundary} from './types';
const failure = (error: unknown) => error instanceof Error ? error.message : typeof error === 'object' && error !== null && 'message' in error ? String(error.message) : 'Bitte Zustand prüfen.';
const newConfig = (): BrightnessConfig => ({enabled: false, lux_sensor_entity_id: '', target_lux: 100, hysteresis_lux: 10, min_interval_seconds: 180, time_window: null, person_entity_ids: [], stages: [{entity_ids: [], brightness: 128}]});
const checked = (response: BrightnessResponse) => {
  if (!response?.status || !Array.isArray(response.status.learned_lux) || !Array.isArray(response.lux_sensors) || !Array.isArray(response.persons)) throw Error('Ungültige Serverantwort.');
  return response;
};
const lux = (value: number | null) => value === null ? 'Noch nicht verfügbar' : `${Math.round(value * 10) / 10} lx`;

export function BasicBrightnessControls({hass, area, revision = 0}: {hass: Hass; area: string; revision?: number}) {
  const api = useRef(hass); api.current = hass;
  const generation = useRef(0), request = useRef(0), lock = useRef(false);
  const [data, setData] = useState<BrightnessResponse | null>(null), [lights, setLights] = useState<Light[]>([]);
  const [editing, setEditing] = useState(false), [loading, setLoading] = useState(true), [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [pollError, setPollError] = useState(''), [message, setMessage] = useState(''), [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const counter = generation, id = ++counter.current;
    setLoading(true); setData(null); setEditing(false); setError(''); setPollError(''); setMessage(''); setBusy(false); lock.current = false;
    void Promise.all([
      api.current.callWS<BrightnessResponse>({type: 'lichtzentrale/brightness/get', area_id: area}),
      api.current.callWS<Light[]>({type: 'lichtzentrale/lights/list'}),
      area.startsWith('zone:') ? api.current.callWS<Room[]>({type: 'lichtzentrale/rooms/list'}) : Promise.resolve([] as Room[]),
    ]).then(([result, candidates, rooms]) => {
      if (id !== counter.current) return;
      setData(checked(result)); setLights((candidates || []).filter(light => light.allowed && (light.area_id === area || rooms.find(room => room.area_id === area)?.lights.some(item => item.entity_id === light.entity_id)) && /^(light|switch)\./.test(light.entity_id)));
    }).catch(error => {if (id === counter.current) setError(`Grundhelligkeit konnte nicht geladen werden: ${failure(error)}`);})
      .finally(() => {if (id === counter.current) setLoading(false);});
    let polling = false;
    const timer = window.setInterval(() => {
      if (lock.current || polling) return;
      polling = true; const version = request.current;
      void api.current.callWS<BrightnessResponse>({type: 'lichtzentrale/brightness/get', area_id: area}).then(result => {
        if (id !== counter.current || version !== request.current) return;
        checked(result); setData(current => current ? {...current, status: result.status} : current); setPollError('');
      }).catch(error => {if (id === counter.current && version === request.current) setPollError(`Status nicht aktuell: ${failure(error)}`);}).finally(() => {polling = false;});
    }, 15000);
    return () => {counter.current++; window.clearInterval(timer);};
  }, [area, revision, refresh]);
  async function update(operation: 'save' | 'set_enabled', payload: Record<string, unknown>) {
    if (lock.current || loading) return;
    lock.current = true; request.current++; const id = generation.current; setBusy(true); setError(''); setMessage('');
    try {
      const result = await api.current.callWS<BrightnessResponse>({type: `lichtzentrale/brightness/${operation}`, area_id: area, ...payload});
      if (id !== generation.current) return;
      setData(checked(result)); setEditing(false); setPollError(''); setMessage('Grundhelligkeit in Home Assistant gespeichert.');
    } catch (error) {if (id === generation.current) setError(`Speichern fehlgeschlagen: ${failure(error)} Bei unklarem Zustand neu laden.`);}
    finally {if (id === generation.current) {request.current++; lock.current = false; setBusy(false);}}
  }
  return <section className="card" aria-label="Grundhelligkeit"><h3>Grundhelligkeit</h3>
    <p>Bei zu wenig Licht werden Stufen nacheinander zugeschaltet, bei zu viel Licht rückwärts ausgeschaltet. Handbedienung pausiert die Regelung bis zum nächsten Zeitfenster-Beginn oder bis „Raum aus“.</p>
    {error && <p role="alert">{displayError(error)}</p>}{pollError && <p role="alert">{displayError(pollError)}</p>}{message && <p role="status">{message}</p>}{loading && <p role="status">Grundhelligkeit wird geladen …</p>}
    <button disabled={busy || loading} onClick={() => setRefresh(value => value + 1)}>Grundhelligkeit neu laden</button>
    {data && <>{data.status.last_error && <p role="alert">Letzte Ausführung: {displayError(data.status.last_error)}</p>}
      <p aria-label="Status der Grundhelligkeit">{data.status.paused ? 'Pausiert durch manuelle Änderung' : data.status.enabled ? 'Regelung eingeschaltet' : 'Regelung ausgeschaltet'}</p>
      <p>Aktuelle Helligkeit: {lux(data.status.current_lux)} · Ziel: {data.config ? lux(data.config.target_lux) : 'Noch nicht festgelegt'}</p>
      <p>Aktive Stufe: {data.status.active_stage} von {data.config?.stages.length || 0} ({data.status.active_stage ? `Stufen 1 bis ${data.status.active_stage} zugeschaltet` : 'Keine Stufe zugeschaltet'})</p>
      {!!data.config?.stages.length && <ul aria-label="Gelernte Lichtanteile">{data.config.stages.map((_, index) => <li key={index}>Stufe {index + 1}: {lux(data.status.learned_lux[index] ?? null)}</li>)}</ul>}
      <label className="check"><input type="checkbox" checked={data.status.enabled} disabled={busy || loading || editing || !data.config} onChange={event => void update('set_enabled', {enabled: event.target.checked})}/>Grundhelligkeit eingeschaltet</label>
      {!editing ? <button disabled={busy || loading} onClick={() => {setEditing(true); setError(''); setMessage('');}}>Grundhelligkeit bearbeiten</button> : <BrightnessEditor initial={data.config || newConfig()} data={data} lights={lights} disabled={busy || loading} save={config => void update('save', {config})} cancel={() => {setEditing(false); setError('');}}/>}
    </>}
  </section>;
}

export function BoundaryEditor({label, value, change}: {label: string; value: MotionBoundary | null; change: (value: MotionBoundary | null) => void}) {
  return <fieldset><legend>{label}</legend><label>{label}: Bezug<select className="text-input" value={value === null ? 'none' : value.type === 'time' ? 'time' : value.event} onChange={event => change(event.target.value === 'none' ? null : event.target.value === 'time' ? {type: 'time', value: '00:00'} : {type: 'sun', event: event.target.value as 'sunrise' | 'sunset', offset_min: 0})}><option value="none">Offene Grenze</option><option value="time">Uhrzeit</option><option value="sunrise">Sonnenaufgang</option><option value="sunset">Sonnenuntergang</option></select></label>
    {value?.type === 'time' && <label>{label}: Uhrzeit<input className="text-input" type="time" value={value.value} onChange={event => change({...value, value: event.target.value})}/></label>}
    {value?.type === 'sun' && <label>{label}: Versatz in Minuten<input className="text-input" type="number" min={-1440} max={1440} step={1} value={Number.isNaN(value.offset_min) ? '' : value.offset_min} onChange={event => change({...value, offset_min: event.target.value === '' ? NaN : Number(event.target.value)})}/></label>}
  </fieldset>;
}
function BrightnessEditor({initial, data, lights, disabled, save, cancel}: {initial: BrightnessConfig; data: BrightnessResponse; lights: Light[]; disabled: boolean; save: (config: BrightnessConfig) => void; cancel: () => void}) {
  const [draft, setDraft] = useState(() => structuredClone(initial));
  const sensors = data.lux_sensors.filter(sensor => sensor.entity_id.startsWith('sensor.') && sensor.device_class === 'illuminance');
  const persons = data.persons.filter(person => person.entity_id.startsWith('person.'));
  const missingPersons = draft.person_entity_ids.filter(id => !persons.some(person => person.entity_id === id));
  const boundaryValid = (value: MotionBoundary | null) => value === null || (value.type === 'time' ? /^([01]\d|2[0-3]):[0-5]\d$/.test(value.value) : Number.isInteger(value.offset_min) && Math.abs(value.offset_min) <= 1440);
  const allIds = draft.stages.flatMap(stage => stage.entity_ids);
  const switchOnly = (stage: BrightnessStage) => stage.entity_ids.length > 0 && stage.entity_ids.every(id => id.startsWith('switch.'));
  const valid = sensors.some(sensor => sensor.entity_id === draft.lux_sensor_entity_id) && Number.isFinite(draft.target_lux) && draft.target_lux > 0 && Number.isFinite(draft.hysteresis_lux) && draft.hysteresis_lux >= 0
    && Number.isInteger(draft.min_interval_seconds) && draft.min_interval_seconds >= 1 && draft.min_interval_seconds <= 86400 && !missingPersons.length
    && (!draft.time_window || boundaryValid(draft.time_window.after) && boundaryValid(draft.time_window.before))
    && draft.stages.length > 0 && draft.stages.length <= 500 && new Set(allIds).size === allIds.length && draft.stages.every(stage => stage.entity_ids.length > 0 && stage.entity_ids.every(id => lights.some(light => light.entity_id === id)) && (switchOnly(stage) || stage.brightness !== null && Number.isInteger(stage.brightness) && stage.brightness >= 1 && stage.brightness <= 255));
  const patchStage = (index: number, patch: Partial<BrightnessStage>) => setDraft(current => ({...current, stages: current.stages.map((stage, i) => i === index ? {...stage, ...patch} : stage)}));
  const reorder = (index: number, direction: number) => setDraft(current => {const stages = [...current.stages]; [stages[index], stages[index + direction]] = [stages[index + direction], stages[index]]; return {...current, stages};});
  return <form onSubmit={event => {event.preventDefault(); if (!disabled && valid) save({...draft, stages: draft.stages.map(stage => ({...stage, brightness: switchOnly(stage) ? null : stage.brightness}))});}}><fieldset disabled={disabled}><legend>Grundhelligkeit einstellen</legend>
    <label>Lux-Sensor<select className="text-input" value={draft.lux_sensor_entity_id} onChange={event => setDraft({...draft, lux_sensor_entity_id: event.target.value})}><option value="">Sensor wählen</option>{draft.lux_sensor_entity_id && !sensors.some(sensor => sensor.entity_id === draft.lux_sensor_entity_id) && <option value={draft.lux_sensor_entity_id}>Gespeicherter Sensor · Sensor nicht mehr vorhanden</option>}{sensors.map(sensor => <option key={sensor.entity_id} value={sensor.entity_id}>{displayName(sensor.name)}{!sensor.available && ' · Nicht verfügbar'}</option>)}</select></label>
    <p>Zur Auswahl stehen Beleuchtungsstärkesensoren mit der Einheit lx.</p>
    {(['target_lux', 'hysteresis_lux', 'min_interval_seconds'] as const).map((key, index) => <label key={key}>{['Zielhelligkeit in lx', 'Hysterese in lx', 'Mindestzeit zwischen Stufenwechseln in Sekunden'][index]}<input className="text-input" type="number" min={key === 'hysteresis_lux' ? 0 : key === 'target_lux' ? 0 : 1} max={key === 'min_interval_seconds' ? 86400 : undefined} step={key === 'min_interval_seconds' ? 1 : 'any'} value={Number.isNaN(draft[key]) ? '' : draft[key]} onChange={event => setDraft({...draft, [key]: event.target.value === '' ? NaN : Number(event.target.value)})}/></label>)}
    <label className="check"><input type="checkbox" checked={draft.time_window !== null} onChange={event => setDraft({...draft, time_window: event.target.checked ? {after: {type: 'time', value: '18:00'}, before: {type: 'time', value: '23:00'}} : null})}/>Zeitfenster begrenzen</label>
    {draft.time_window && <><p>Lokale Home-Assistant-Zeit. Beginn inklusive, Ende exklusive; über Mitternacht möglich.</p><BoundaryEditor label="Beginn" value={draft.time_window.after} change={after => setDraft({...draft, time_window: {...draft.time_window!, after}})}/><BoundaryEditor label="Ende" value={draft.time_window.before} change={before => setDraft({...draft, time_window: {...draft.time_window!, before}})}/></>}
    <fieldset><legend>Anwesenheit (optional)</legend><p>Ohne Auswahl immer; sonst muss mindestens eine ausgewählte Person zu Hause sein.</p>{persons.map(person => <label className="check" key={person.entity_id}><input type="checkbox" checked={draft.person_entity_ids.includes(person.entity_id)} onChange={() => setDraft({...draft, person_entity_ids: draft.person_entity_ids.includes(person.entity_id) ? draft.person_entity_ids.filter(id => id !== person.entity_id) : [...draft.person_entity_ids, person.entity_id]})}/>{displayName(person.name)}{!person.available && ' · Nicht verfügbar'}</label>)}{missingPersons.map(id => <p key={id}>Gespeicherte Person: Person nicht mehr vorhanden. <button type="button" onClick={() => setDraft({...draft, person_entity_ids: draft.person_entity_ids.filter(item => item !== id)})}>Person entfernen</button></p>)}</fieldset>
    <p>Stufen bauen aufeinander auf. Jedes Licht darf nur in einer Stufe vorkommen. Schalter eignen sich als letzte Stufe und werden nie gedimmt. Falls zugeordnet, übernehmen Lampen den Weißton von Adaptive Lighting.</p>
    {draft.stages.map((stage, index) => <fieldset key={index}><legend>Stufe {index + 1}</legend>{lights.map(light => <label className="check" key={light.entity_id}><input aria-label={`Stufe ${index + 1}: ${displayName(light.name)}`} type="checkbox" checked={stage.entity_ids.includes(light.entity_id)} disabled={!stage.entity_ids.includes(light.entity_id) && allIds.includes(light.entity_id)} onChange={() => {const entity_ids = stage.entity_ids.includes(light.entity_id) ? stage.entity_ids.filter(id => id !== light.entity_id) : [...stage.entity_ids, light.entity_id]; patchStage(index, {entity_ids, brightness: entity_ids.some(id => id.startsWith('light.')) ? stage.brightness ?? 128 : null});}}/>{displayName(light.name)}{light.entity_id.startsWith('switch.') && ' · Nur Ein/Aus'}{!light.available && ' · Nicht verfügbar'}</label>)}
      {stage.entity_ids.filter(id => !lights.some(light => light.entity_id === id)).map(id => <p key={id}>Gespeicherte Lampe: Nicht mehr freigegeben, vorhanden oder in diesem Raum. <button type="button" onClick={() => patchStage(index, {entity_ids: stage.entity_ids.filter(item => item !== id)})}>Licht aus Stufe {index + 1} entfernen</button></p>)}
      {switchOnly(stage) ? <p>Nur Schalter ausgewählt: Ein/Aus ohne Helligkeitswert.</p> : <div className="slider"><label>Stufe {index + 1} Helligkeit: {stage.brightness === null ? 'Bitte wählen' : `${Math.round(stage.brightness / 255 * 100)} %`}<input aria-label={`Stufe ${index + 1} Helligkeit`} type="range" min={1} max={255} value={stage.brightness ?? 128} onChange={event => patchStage(index, {brightness: Number(event.target.value)})}/></label></div>}
      <div className="actions"><button type="button" disabled={index === 0} onClick={() => reorder(index, -1)}>Stufe {index + 1} nach oben</button><button type="button" disabled={index === draft.stages.length - 1} onClick={() => reorder(index, 1)}>Stufe {index + 1} nach unten</button><button type="button" onClick={() => setDraft({...draft, stages: draft.stages.filter((_, i) => i !== index)})}>Stufe {index + 1} entfernen</button></div>
    </fieldset>)}
    <button type="button" onClick={() => setDraft({...draft, stages: [...draft.stages, {entity_ids: [], brightness: 128}]})}>Stufe hinzufügen</button>
    {!valid && <p>Bitte Sensor, gültige Werte und mindestens eine vollständige Stufe wählen. Fehlende oder doppelte Auswahlen korrigieren.</p>}
    <div className="actions"><button type="submit" disabled={!valid}>Grundhelligkeit speichern</button><button type="button" onClick={cancel}>Abbrechen</button></div>
  </fieldset></form>;
}
