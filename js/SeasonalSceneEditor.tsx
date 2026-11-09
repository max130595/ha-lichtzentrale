// Geändert für Lichtzentrale
import {useEffect, useRef, useState} from 'react';
import {displayError, displayName} from './display';
import {errorText} from './sceneControls';
import type {Hass, Room, Scene, SeasonalConfig, SeasonName} from './types';
export const seasons: Record<SeasonName, string> = {spring: 'Frühling', summer: 'Sommer', autumn: 'Herbst', winter: 'Winter'};
export const defaultSeasonal = (): SeasonalConfig => ({scenes: {spring: null, summer: null, autumn: null, winter: null}, boundaries: {spring: '03-01', summer: '06-01', autumn: '09-01', winter: '12-01'}, christmas: {enabled: false, scene_id: null, start: '12-01', end: '12-26'}});
const months = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
export function validMonthDay(value: string): boolean {
  if (!/^\d{2}-\d{2}$/.test(value)) return false;
  const [month, day] = value.split('-').map(Number);
  return month >= 1 && month <= 12 && day >= 1 && day <= new Date(2000, month, 0).getDate();
}
export function validSeasonBoundaries(boundaries: SeasonalConfig['boundaries']): boolean {
  const values = Object.keys(seasons).map(key => boundaries[key as SeasonName]);
  return values.every(validMonthDay) && new Set(values.map(value => value === '02-29' ? '02-28' : value)).size === 4 && values.filter((value, index) => values[(index + 1) % 4] < value).length === 1;
}
export function MonthDaySelect({label, value, change}: {label: string; value: string; change: (value: string) => void}) {
  const [month, day] = value.split('-').map(Number), days = new Date(2000, month, 0).getDate();
  const format = (nextMonth: number, nextDay: number) => `${String(nextMonth).padStart(2, '0')}-${String(nextDay).padStart(2, '0')}`;
  return <fieldset className="month-day"><legend>{label}</legend><div className="month-day-fields"><label>Tag<select className="text-input" aria-label={`${label} Tag`} value={day} onChange={event => change(format(month, Number(event.target.value)))}>{Array.from({length: days}, (_, index) => <option key={index + 1} value={index + 1}>{index + 1}.</option>)}</select></label><label>Monat<select className="text-input" aria-label={`${label} Monat`} value={month} onChange={event => {const next = Number(event.target.value); change(format(next, Math.min(day, new Date(2000, next, 0).getDate())));}}>{months.map((name, index) => <option key={name} value={index + 1}>{name}</option>)}</select></label></div></fieldset>;
}
export function SeasonalSceneEditor({hass, room, scenes, scene, onClose, onSaved}: {hass: Hass; room: Room; scenes: Scene[]; scene?: Scene; onClose: () => void; onSaved: (scene: Scene) => void}) {
  const [name, setName] = useState(scene?.name || 'Nach Jahreszeit');
  const [config, setConfig] = useState<SeasonalConfig>(() => scene?.seasonal ? {scenes: {...scene.seasonal.scenes}, boundaries: {...scene.seasonal.boundaries}, christmas: {...scene.seasonal.christmas}} : defaultSeasonal());
  const [favorite, setFavorite] = useState(scene?.favorite ?? true), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const mounted = useRef(false), lock = useRef(false), api = useRef(hass); api.current = hass;
  useEffect(() => {mounted.current = true; return () => {mounted.current = false;};}, []);
  const candidates = scenes.filter(item => item.area_id === room.area_id && item.kind !== 'seasonal');
  const ids = Object.values(config.scenes).filter(Boolean);
  const boundaries = Object.values(config.boundaries);
  const valid = name.trim() && ids.some(id => candidates.some(item => item.id === id)) && validSeasonBoundaries(config.boundaries) && (!config.christmas.enabled || (validMonthDay(config.christmas.start) && validMonthDay(config.christmas.end)));
  function select(label: string, value: string | null, change: (value: string | null) => void) {
    const missing = value && !candidates.some(item => item.id === value);
    return <label>{label}<select className="text-input" value={value || ''} onChange={event => change(event.target.value || null)}><option value="">Keine · nächste Jahreszeit verwenden</option>{missing && <option value={value}>Szene nicht mehr vorhanden</option>}{candidates.map(item => <option key={item.id} value={item.id}>{displayName(item.name)}</option>)}</select></label>;
  }
  async function save() {
    if (lock.current || !valid) return;
    lock.current = true; setBusy(true); setError('');
    try {
      const result = await api.current.callWS<Scene>({type: 'lichtzentrale/scene/save', scene: {...scene, name: name.trim(), area_id: room.area_id, kind: 'seasonal', favorite, seasonal: config}});
      if (mounted.current) onSaved(result);
    } catch (e) {if (mounted.current) setError(`Speichern fehlgeschlagen: ${errorText(e)}`);}
    finally {lock.current = false; if (mounted.current) setBusy(false);}
  }
  return <section className="seasonal-editor" data-testid="seasonal-editor" aria-label="Szene nach Jahreszeit">
    <div className="section-heading"><h2>Szene nach Jahreszeit</h2><button disabled={busy} onClick={onClose}>Abbrechen</button></div>
    <p className="editor-context">{displayName(room.name)} · Beim Start wird die passende gespeicherte Szene gewählt.</p>
    {error && <p role="alert" className="error">{displayError(error)}</p>}
    <fieldset disabled={busy}><label>Szenenname<input className="text-input" value={name} maxLength={100} onChange={event => setName(event.target.value)}/></label>
      {Object.entries(seasons).map(([key, label]) => <section className="season-choice" key={key}>{select(label, config.scenes[key as SeasonName], value => setConfig(current => ({...current, scenes: {...current.scenes, [key]: value}})))}</section>)}
      {!candidates.length && <p className="notice">Speichere zuerst mindestens eine normale Szene für dieses Ziel.</p>}
      <small>Fehlt eine Zuordnung, startet die nächstliegende Jahreszeit. Ein Hinweis nennt die Ersatzszene.</small>
      <label className="check"><input type="checkbox" checked={config.christmas.enabled} onChange={event => setConfig(current => ({...current, christmas: {...current.christmas, enabled: event.target.checked}}))}/>Weihnachten zusätzlich verwenden</label>
      {config.christmas.enabled && <section className="christmas-settings">{select('Weihnachten', config.christmas.scene_id, value => setConfig(current => ({...current, christmas: {...current.christmas, scene_id: value}})))}<MonthDaySelect label="Weihnachten ab" value={config.christmas.start} change={value => setConfig(current => ({...current, christmas: {...current.christmas, start: value}}))}/><MonthDaySelect label="Weihnachten bis einschließlich" value={config.christmas.end} change={value => setConfig(current => ({...current, christmas: {...current.christmas, end: value}}))}/></section>}
      <label className="check"><input type="checkbox" checked={favorite} onChange={event => setFavorite(event.target.checked)}/>Lieblingsszene auf Zuhause</label>
      <details><summary>Mehr Optionen · Jahreszeitenbeginn</summary>{Object.entries(seasons).map(([key, label]) => <MonthDaySelect key={key} label={`${label} ab`} value={config.boundaries[key as SeasonName]} change={value => setConfig(current => ({...current, boundaries: {...current.boundaries, [key]: value}}))}/>)}{!validSeasonBoundaries(config.boundaries) && <p role="alert">{new Set(boundaries.map(value => value === '02-29' ? '02-28' : value)).size !== 4 ? 'Jede Jahreszeit braucht einen eigenen Beginn.' : 'Die Beginne müssen aufeinander folgen: Frühling, Sommer, Herbst, Winter.'}</p>}</details>
    </fieldset><div className="editor-footer"><button className="primary" disabled={busy || !valid} onClick={() => void save()}>{busy ? 'Bitte warten …' : 'Jahreszeiten-Szene speichern'}</button></div>
  </section>;
}
