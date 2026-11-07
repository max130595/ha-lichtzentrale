// Geändert für Lichtzentrale
import {RuntimeControls} from './RuntimeControls';
import {useEffect, useRef, useState} from 'react';
import type {ApplyResult, Hass, HueScene, Light, Room, Scene} from './types';
export const dimmable = (light: Light) => !light.entity_id.startsWith('switch.') && (light.supported_color_modes || []).some(mode => !['onoff', 'unknown'].includes(mode));
export function rgbToXy(hex: string): [number, number] {
  const rgb = [1, 3, 5].map(index => parseInt(hex.slice(index, index + 2), 16) / 255).map(value => value > .04045 ? ((value + .055) / 1.055) ** 2.4 : value / 12.92);
  const [r, g, b] = rgb; const x = r * .664511 + g * .154324 + b * .162028; const y = r * .283881 + g * .668433 + b * .047685; const z = r * .000088 + g * .07231 + b * .986039;
  return x + y + z ? [x / (x + y + z), y / (x + y + z)] : [.3127, .329];
}
function Slider({label, value, min = 1, max = 255, disabled, save}: {label: string; value: number; min?: number; max?: number; disabled: boolean; save: (value: number) => void}) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  return <div className="slider"><label>{label}: {max === 255 ? `${Math.round(draft / 255 * 100)} %` : `${draft} K`}<input aria-label={label} type="range" min={min} max={max} value={draft} disabled={disabled} onChange={event => setDraft(Number(event.target.value))}/></label><button disabled={disabled} onClick={() => save(draft)}>{label} setzen</button></div>;
}
const failure = (error: unknown) => error instanceof Error ? error.message : typeof error === 'object' && error && 'message' in error ? String(error.message) : 'Anfrage fehlgeschlagen';
export function Rooms({hass, detail, openRoom, onRoomChange, initialArea = ''}: {hass: Hass; detail: boolean; openRoom: () => void; onRoomChange?: (name: string, area: string) => void; initialArea?: string}) {
  const api = useRef(hass); api.current = hass;
  const alive = useRef(false), lock = useRef(false), generation = useRef(0);
  const [rooms, setRooms] = useState<Room[]>([]), [scenes, setScenes] = useState<Scene[]>([]), [hue, setHue] = useState<HueScene[]>([]);
  const [area, setArea] = useState(initialArea), [name, setName] = useState(''), [candidate, setCandidate] = useState('');
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [error, setError] = useState(''), [message, setMessage] = useState('');
  const last = Object.fromEntries(rooms.map(room => [room.area_id, scenes.find(scene => scene.id === room.last_scene_id)]));
  async function load() {
    const id = ++generation.current; setLoading(true); setError('');
    try {
      const [r, s, h] = await Promise.all([api.current.callWS<Room[]>({type: 'lichtzentrale/rooms/list'}), api.current.callWS<Scene[]>({type: 'lichtzentrale/scenes/list'}), api.current.callWS<HueScene[]>({type: 'lichtzentrale/hue_scenes/list'})]);
      if (!alive.current || id !== generation.current) return;
      setRooms(r); setScenes(s); setHue(h);
    } catch (e) {if (alive.current && id === generation.current) setError(`Laden fehlgeschlagen: ${failure(e)}`);}
    finally {if (alive.current && id === generation.current) setLoading(false);}
  }
  useEffect(() => {const counter = generation; alive.current = true; void load(); return () => {alive.current = false; counter.current++;};}, []);
  async function run(type: string, data: Record<string, unknown>, success?: (result: unknown) => void) {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError(''); setMessage('');
    try {
      const result = await api.current.callWS({type: `lichtzentrale/${type}`, ...data});
      if (!alive.current) return;
      if (result && typeof result === 'object' && 'applied' in result) {
        const outcome = result as ApplyResult;
        setMessage(`${outcome.applied.length} Lampe(n) angewendet. ${outcome.skipped.length} übersprungen. ${outcome.failed?.length || 0} fehlgeschlagen.${outcome.skipped.length || outcome.failed?.length ? ' Nicht alle Lampen konnten geändert werden.' : ''}`);
      }
      success?.(result); setRevision(value => value + 1); await load();
    } catch (e) {if (alive.current) setError(`Aktion fehlgeschlagen: ${failure(e)}. Bei Steuerbefehlen können einzelne Lampen bereits geändert sein. Zustand neu laden.`);}
    finally {lock.current = false; if (alive.current) setBusy(false);}
  }
  const disabled = busy || loading;
  const room = rooms.find(item => item.area_id === area);
  const roomScenes = scenes.filter(scene => scene.area_id === area).sort((a, b) => a.order - b.order);
  function reorder(index: number, offset: number) {
    const ids = roomScenes.map(scene => scene.id); [ids[index], ids[index + offset]] = [ids[index + offset], ids[index]];
    void run('scenes/reorder', {area_id: area, scene_ids: ids});
  }
  const strip = (scene?: Scene) => scene && <div className="scene-strip" style={{background: scene.preview.length > 1 ? `linear-gradient(110deg, ${scene.preview.join(',')})` : scene.preview[0] || '#87978e'}}/>;
  return <section>
    {error && <p role="alert" className="error">{error}</p>}{message && <p role="status" className="notice">{message}</p>}
    <div className="section-heading"><h2>{detail ? room?.name || 'Raum wählen' : 'Räume'}</h2><button disabled={disabled} onClick={() => void load()}>Räume neu laden</button></div>
    {loading && <p role="status">Räume und Szenen werden geladen …</p>}
    {!loading && !rooms.length && <p>Noch keine Räume mit freigegebenen Lampen. Gib zuerst Lampen frei und ordne sie in Home Assistant einem Bereich zu.</p>}
    {(!detail || !room) && <div className="grid">{rooms.map(item => <article className="card" key={item.area_id}>{strip(last[item.area_id])}<button className="room-link" disabled={disabled} onClick={() => {setArea(item.area_id); onRoomChange?.(item.name, item.area_id); setName(''); setCandidate(''); setMessage(''); openRoom();}}>{item.name}</button><p>{item.lights.length} Lampe(n) · {item.available_count} verfügbar</p>{last[item.area_id] && <small>Zuletzt über Lichtzentrale gestartet: {last[item.area_id]?.name}</small>}{last[item.area_id] && <button disabled={disabled} onClick={() => void run('scene/apply', {scene_id: item.last_scene_id})}>Erneut starten</button>}<button disabled={disabled || !item.available_count} aria-label={`${item.name} ${item.on ? 'ausschalten' : 'einschalten'}`} onClick={() => void run('room/toggle', {area_id: item.area_id, on: !item.on})}>{item.on ? 'Ausschalten' : 'Einschalten'}</button></article>)}</div>}
    {detail && room && <>
      <section className="card">{last[area] && <><p>Zuletzt über Lichtzentrale gestartet: {last[area]?.name}</p>{strip(last[area])}<button disabled={disabled} onClick={() => void run('scene/apply', {scene_id: room.last_scene_id})}>Erneut starten</button></>}<button disabled={disabled || !room.available_count} onClick={() => void run('room/toggle', {area_id: area, on: !room.on})}>Raum {room.on ? 'ausschalten' : 'einschalten'}</button>{room.lights.some(dimmable) && <Slider label="Raumhelligkeit" value={room.brightness || 128} disabled={disabled || !room.available_count} save={brightness => void run('room/brightness', {area_id: area, brightness})}/>}</section>
      <RuntimeControls key={area} hass={hass} area={area} revision={revision}/>
      <h3>Szenen</h3>{!roomScenes.length && <p>Noch keine Szene gespeichert.</p>}
      <div className="grid">{roomScenes.map((scene, index) => <article className="card scene" key={scene.id}>{strip(scene)}<h4>{scene.name}</h4>{scene.dynamic?.enabled && <p>Dynamisch · {scene.dynamic.interval} Sekunden</p>}<small>{scene.kind === 'hue' ? 'Hue-Szene' : scene.kind === 'palette' ? 'Farbpalette' : 'Gespeicherter Zustand'}</small><button disabled={disabled} onClick={() => void run('scene/apply', {scene_id: scene.id})}>Anwenden</button><button aria-label={`${scene.name} als Favorit`} aria-pressed={scene.favorite} disabled={disabled} onClick={() => void run('scene/save', {scene: {...scene, favorite: !scene.favorite}})}>{scene.favorite ? '★' : '☆'}</button><div className="actions"><button aria-label={`${scene.name} nach oben`} disabled={disabled || index === 0} onClick={() => reorder(index, -1)}>↑</button><button aria-label={`${scene.name} nach unten`} disabled={disabled || index === roomScenes.length - 1} onClick={() => reorder(index, 1)}>↓</button><button disabled={disabled} onClick={() => {if (window.confirm(`Szene „${scene.name}“ löschen?`)) void run('scene/delete', {scene_id: scene.id});}}>Löschen</button></div></article>)}</div>
      <section className="card"><h3>Szene speichern</h3><label>Szenenname<input className="text-input" value={name} maxLength={100} disabled={disabled} onChange={event => setName(event.target.value)}/></label><button disabled={disabled || !name.trim()} onClick={() => void run('scene/snapshot', {area_id: area, name: name.trim()}, result => {const snapshot = result as {skipped?: string[]}; setName(''); setMessage(snapshot.skipped?.length ? `Szene gespeichert. ${snapshot.skipped.length} nicht verfügbare Lampe(n) fehlen im Snapshot.` : 'Aktueller Zustand als Szene gespeichert.');})}>Aktuellen Zustand als Szene speichern</button><h4>Hue-Szene importieren</h4><p>Nur passende Hue-Szenen mit vollständig freigegebenen Zielen werden importiert.</p><label>Hue-Szene<select className="text-input" disabled={disabled} value={candidate} onChange={event => setCandidate(event.target.value)}><option value="">Bitte wählen</option>{hue.filter(scene => scene.area_id === area).map(scene => <option key={scene.entity_id} value={scene.entity_id} disabled={!scene.available}>{scene.name}{!scene.available ? ' · Nicht verfügbar' : ''}</option>)}</select></label><button disabled={disabled || !candidate} onClick={() => void run('scene/save', {scene: {name: name.trim() || hue.find(scene => scene.entity_id === candidate)?.name, area_id: area, kind: 'hue', hue_scene: candidate}}, () => {setCandidate(''); setMessage('Hue-Szene importiert.');})}>Hue-Szene importieren</button></section>
      <h3>Einzelne Lampen</h3>{room.lights.map(light => <section className="card" key={light.entity_id}><h4>{light.name}</h4><p>{!light.available ? 'Nicht verfügbar' : light.on ? 'An' : 'Aus'}{light.entity_id.startsWith('switch.') ? ' · Nur Ein/Aus' : ''}</p><button disabled={disabled || !light.available} aria-label={`${light.name} ${light.on ? 'ausschalten' : 'einschalten'}`} onClick={() => void run('light/set', {entity_id: light.entity_id, on: !light.on})}>{light.on ? 'Ausschalten' : 'Einschalten'}</button>{dimmable(light) && <Slider label={`${light.name} Helligkeit`} value={light.brightness || 128} disabled={disabled || !light.available} save={brightness => void run('light/set', {entity_id: light.entity_id, brightness})}/>}{!light.entity_id.startsWith('switch.') && light.supported_color_modes?.some(mode => ['xy', 'hs', 'rgb', 'rgbw', 'rgbww'].includes(mode)) && <label className="color-label">{light.name} Farbe<input aria-label={`${light.name} Farbe`} type="color" disabled={disabled || !light.available} defaultValue={light.rgb_color ? '#' + light.rgb_color.map(value => value.toString(16).padStart(2, '0')).join('') : '#ffffff'} onChange={event => void run('light/set', {entity_id: light.entity_id, xy: rgbToXy(event.target.value)})}/></label>}{!light.entity_id.startsWith('switch.') && light.supported_color_modes?.includes('color_temp') && <Slider label={`${light.name} Weißton`} value={light.color_temp_kelvin || light.min_color_temp_kelvin || 2700} min={light.min_color_temp_kelvin || 2000} max={light.max_color_temp_kelvin || 6500} disabled={disabled || !light.available} save={color_temp_kelvin => void run('light/set', {entity_id: light.entity_id, color_temp_kelvin})}/>}</section>)}
    </>}
  </section>;
}
