// Geändert für Lichtzentrale
import {displayName, displayError} from './display';
import {RoomSettingsEditor} from './Buttons';
import type {AdaptiveStatus} from './RuntimeControls';
import {Zones} from './Zones';
import {RoomPositions, distributionLabel} from './RoomPositions';
import {BasicBrightnessControls} from './BasicBrightnessControls';
import {MotionControls} from './MotionControls';
import {RuntimeControls} from './RuntimeControls';
import {useEffect, useRef, useState} from 'react';
import type {ApplyResult, Hass, HueScene, Light, Room, Scene} from './types';
export const dimmable = (light: Light) => !light.entity_id.startsWith('switch.') && (light.supported_color_modes || []).some(mode => !['onoff', 'unknown'].includes(mode));
export function rgbToXy(hex: string): [number, number] {
  const rgb = [1, 3, 5].map(index => parseInt(hex.slice(index, index + 2), 16) / 255).map(value => value > .04045 ? ((value + .055) / 1.055) ** 2.4 : value / 12.92);
  const [r, g, b] = rgb; const x = r * .664511 + g * .154324 + b * .162028; const y = r * .283881 + g * .668433 + b * .047685; const z = r * .000088 + g * .07231 + b * .986039;
  return x + y + z ? [x / (x + y + z), y / (x + y + z)] : [.3127, .329];
}
function Slider({label, value, min = 1, max = 255, disabled, save, compact = false}: {compact?: boolean; label: string; value: number; min?: number; max?: number; disabled: boolean; save: (value: number) => void}) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  return <div className="slider"><label>{label}: {max === 255 ? `${Math.round(draft / 255 * 100)} %` : `${draft} K`}<input aria-label={label} type="range" min={min} max={max} value={draft} disabled={disabled} onChange={event => setDraft(Number(event.target.value))} onPointerUp={event => {if (compact) save(Number(event.currentTarget.value));}} onKeyUp={event => {if (compact && ['ArrowLeft', 'ArrowRight', 'Home', 'End', 'ArrowUp', 'ArrowDown'].includes(event.key)) save(Number(event.currentTarget.value));}}/></label>{!compact && <button disabled={disabled} onClick={() => save(draft)}>{label} setzen</button>}</div>;
}
const failure = (error: unknown) => error instanceof Error ? error.message : typeof error === 'object' && error && 'message' in error ? String(error.message) : 'Anfrage fehlgeschlagen';
export function Rooms({hass, detail, openRoom, onRoomChange, initialArea = ''}: {hass: Hass; detail: boolean; openRoom: () => void; onRoomChange?: (name: string, area: string) => void; initialArea?: string}) {
  const api = useRef(hass); api.current = hass;
  const alive = useRef(false), lock = useRef(false), generation = useRef(0);
  const [rooms, setRooms] = useState<Room[]>([]), [scenes, setScenes] = useState<Scene[]>([]), [hue, setHue] = useState<HueScene[]>([]);
  const [area, setArea] = useState(initialArea), [name, setName] = useState(''), [candidate, setCandidate] = useState('');
  const [revision, setRevision] = useState(0), [positioning, setPositioning] = useState(false);
  const [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [error, setError] = useState(''), [message, setMessage] = useState('');
  const [creating, setCreating] = useState(false), [naming, setNaming] = useState(false);
  const [editingZones, setEditingZones] = useState(false), [editingSettings, setEditingSettings] = useState(false);
  const [rename, setRename] = useState<{id: string; name: string} | null>(null);
  const [adaptive, setAdaptive] = useState<AdaptiveStatus | null>(null);
  async function load() {
    const id = ++generation.current; setLoading(true); setError('');
    try {
      const [r, s, h, a] = await Promise.all([api.current.callWS<Room[]>({type: 'lichtzentrale/rooms/list'}), api.current.callWS<Scene[]>({type: 'lichtzentrale/scenes/list'}), api.current.callWS<HueScene[]>({type: 'lichtzentrale/hue_scenes/list'}), api.current.callWS<AdaptiveStatus>({type: 'lichtzentrale/adaptive/status'})]);
      if (!alive.current || id !== generation.current) return;
      setRooms(r); setScenes(s); setHue(h); setAdaptive(a?.available ? a : null);
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
  const disabled = busy || loading || positioning;
  const room = rooms.find(item => item.area_id === area);
  const roomScenes = scenes.filter(scene => scene.area_id === area).sort((a, b) => a.order - b.order);
  function reorder(index: number, offset: number) {
    const ids = roomScenes.map(scene => scene.id); [ids[index], ids[index + offset]] = [ids[index + offset], ids[index]];
    void run('scenes/reorder', {area_id: area, scene_ids: ids});
  }
  const strip = (scene?: Scene) => scene && <div className="scene-strip" style={{background: scene.preview.length > 1 ? `linear-gradient(110deg, ${scene.preview.join(',')})` : scene.preview[0] || '#87978e'}}/>;
  return <section>
    {error && <p role="alert" className="error">{displayError(error)}</p>}{message && <p role="status" className="notice">{message}</p>}
    <div className="section-heading"><h2>{detail ? room?.name || 'Raum wählen' : 'Zuhause'}</h2><button disabled={disabled} onClick={() => void load()}>Räume neu laden</button></div>
    {loading && <p role="status">Räume und Szenen werden geladen …</p>}
    {!loading && !rooms.length && <p>Noch keine Räume mit freigegebenen Lampen. Gib zuerst Lampen frei und ordne sie in Home Assistant einem Bereich zu.</p>}
    {!detail && <button onClick={() => setEditingZones(!editingZones)}>{editingZones ? 'Zonen schließen' : 'Zonen bearbeiten'}</button>}
    {!detail && editingZones && <Zones hass={hass} onSaved={() => void load()}/>}
    {(!detail || !room) && ['zone', 'room'].map(kind => <section key={kind}><h3>{kind === 'zone' ? 'Zonen' : 'Räume'}</h3><div className="home-grid">{rooms.filter(item => (item.kind || 'room') === kind).map(item => <article className="card room-card" key={item.area_id}><div className="section-heading"><h3 className="room-heading"><button className="room-link" disabled={disabled} onClick={() => {setArea(item.area_id); onRoomChange?.(item.name, item.area_id); setName(''); setCandidate(''); setMessage(''); setCreating(false); setNaming(false); openRoom();}}>{displayName(item.name)}</button></h3><button disabled={disabled || !item.available_count} aria-label={`${displayName(item.name)} ${item.on ? 'ausschalten' : 'einschalten'}`} onClick={() => void run('room/toggle', {area_id: item.area_id, on: !item.on})}>{item.on ? 'An' : 'Aus'}</button></div>{item.lights.some(dimmable) && <Slider compact label={`${displayName(item.name)} Helligkeit`} value={item.brightness || 128} disabled={disabled || !item.available_count} save={brightness => void run('room/brightness', {area_id: item.area_id, brightness})}/>}</article>)}</div></section>)}
    {detail && room && <>
      <section className="card"><button disabled={disabled || !room.available_count} onClick={() => void run('room/toggle', {area_id: area, on: !room.on})}>{room.on ? 'Ausschalten' : 'Einschalten'}</button><button className="secondary" disabled={disabled || !roomScenes.some(scene => scene.night)} onClick={() => void run('action/execute', {action: {type: 'night', area_id: area}})}>Nachtlicht</button>{room.lights.some(dimmable) && <Slider compact label="Raumhelligkeit" value={room.brightness || 128} disabled={disabled || !room.available_count} save={brightness => void run('room/brightness', {area_id: area, brightness})}/>}</section>
      <button disabled={disabled} onClick={() => {setCreating(true); setNaming(false); setName('');}}>+ Neue Szene</button>
      {creating && <section className="card"><h3>Neue Szene</h3>{!naming ? <><p>Stelle die Lampen unten so ein, wie du sie speichern möchtest.</p><button disabled={disabled} onClick={() => setNaming(true)}>Weiter · Name</button></> : <><label>Szenenname<input className="text-input" value={name} maxLength={100} disabled={disabled} onChange={event => setName(event.target.value)}/></label><button disabled={disabled || !name.trim()} onClick={() => void run('scene/snapshot', {area_id: area, name: name.trim()}, result => {const snapshot = result as {skipped?: string[]}; setCreating(false); setNaming(false); setName(''); setMessage(snapshot.skipped?.length ? `Szene gespeichert. ${snapshot.skipped.length} nicht verfügbare Lampe(n) fehlen.` : 'Szene gespeichert.');})}>Szene speichern</button></>}<button className="secondary" disabled={disabled} onClick={() => {setCreating(false); setNaming(false);}}>Abbrechen</button></section>}
      <details><summary>Mehr Optionen</summary>
      {!editingSettings ? <button onClick={() => setEditingSettings(true)}>Szenenfolge und Einschalten</button> : <RoomSettingsEditor key={area} room={room} scenes={roomScenes} adaptive={!!adaptive?.rooms?.some(item => item.area_id === area && item.available && item.switch_entity_id)} disabled={disabled} cancel={() => setEditingSettings(false)} save={settings => void run('room/settings', {area_id: area, ...settings}, () => setEditingSettings(false))}/>}
      <RuntimeControls key={area} hass={hass} area={area} revision={revision}/>
      <MotionControls key={`motion:${area}`} hass={hass} area={area} revision={revision}/>
      <BasicBrightnessControls key={`brightness:${area}`} hass={hass} area={area} revision={revision}/>
      <RoomPositions hass={hass} room={room} disabled={busy || loading} onBusy={setPositioning} onSaved={(entity, position) => setRooms(items => items.map(item => {if (item.area_id !== area) return item; const positions = {...item.positions}; if (position) positions[entity] = position; else delete positions[entity]; return {...item, positions};}))}/>
      </details><h3>Szenen</h3>{!roomScenes.length && <p>Noch keine Szene gespeichert.</p>}
      <div className="grid">{roomScenes.map((scene, index) => <article className="card scene" key={scene.id}>{strip(scene)}<h4>{scene.name}</h4>{scene.dynamic?.enabled && <p>Dynamisch · {scene.dynamic.interval} Sekunden</p>}{scene.kind === 'palette' && <p>{distributionLabel(scene.verteilung)}{scene.dynamic?.enabled && scene.dynamic.welle ? ' · Welle' : ''}</p>}<small>{scene.kind === 'hue' ? 'Hue-Szene' : scene.kind === 'palette' ? 'Farbpalette' : 'Gespeicherter Zustand'}</small><button disabled={disabled} onClick={() => void run('scene/apply', {scene_id: scene.id})}>Anwenden</button><button aria-label={`${displayName(scene.name)} als Favorit`} aria-pressed={scene.favorite} disabled={disabled} onClick={() => void run('scene/save', {scene: {...scene, favorite: !scene.favorite}})}>{scene.favorite ? '★' : '☆'}</button><details><summary>Szene bearbeiten</summary>{rename?.id === scene.id ? <div><label>Neuer Szenenname<input className="text-input" maxLength={100} disabled={disabled} value={rename.name} onChange={event => setRename({id: scene.id, name: event.target.value})}/></label><button disabled={disabled || !rename.name.trim()} onClick={() => void run('scene/save', {scene: {...scene, name: rename.name.trim()}}, () => {setRename(null); setMessage('Szenenname gespeichert.');})}>Namen speichern</button><button disabled={disabled} onClick={() => setRename(null)}>Umbenennen abbrechen</button></div> : <button disabled={disabled} onClick={() => setRename({id: scene.id, name: scene.name})}>Szene umbenennen</button>}<label className="check"><input type="checkbox" checked={!!scene.night} disabled={disabled} onChange={event => void run('scene/save', {scene: {...scene, night: event.target.checked}})}/>Nachtlicht</label><div className="actions"><button aria-label={`${displayName(scene.name)} nach oben`} disabled={disabled || index === 0} onClick={() => reorder(index, -1)}>↑</button><button aria-label={`${displayName(scene.name)} nach unten`} disabled={disabled || index === roomScenes.length - 1} onClick={() => reorder(index, 1)}>↓</button><button disabled={disabled} onClick={() => {if (window.confirm(`Szene „${displayName(scene.name)}“ löschen?`)) void run('scene/delete', {scene_id: scene.id});}}>Löschen</button></div></details></article>)}</div>
      <details><summary>Mehr Optionen · Hue-Szene importieren</summary><section className="card"><h4>Hue-Szene importieren</h4><p>Nur passende Hue-Szenen mit vollständig freigegebenen Zielen werden importiert.</p><label>Hue-Szene<select className="text-input" disabled={disabled} value={candidate} onChange={event => setCandidate(event.target.value)}><option value="">Bitte wählen</option>{hue.filter(scene => scene.area_id === area).map(scene => <option key={scene.entity_id} value={scene.entity_id} disabled={!scene.available}>{scene.name}{!scene.available ? ' · Nicht verfügbar' : ''}</option>)}</select></label><button disabled={disabled || !candidate} onClick={() => void run('scene/save', {scene: {name: name.trim() || hue.find(scene => scene.entity_id === candidate)?.name, area_id: area, kind: 'hue', hue_scene: candidate}}, () => {setCandidate(''); setMessage('Hue-Szene importiert.');})}>Hue-Szene importieren</button></section></details>
      <h3>Einzelne Lampen</h3>{room.lights.map(light => <section className="card" key={light.entity_id}><h4>{displayName(light.name)}</h4><p>{!light.available ? 'Nicht verfügbar' : light.on ? 'An' : 'Aus'}{light.entity_id.startsWith('switch.') ? ' · Nur Ein/Aus' : ''}</p><button disabled={disabled || !light.available} aria-label={`${displayName(light.name)} ${light.on ? 'ausschalten' : 'einschalten'}`} onClick={() => void run('light/set', {entity_id: light.entity_id, on: !light.on})}>{light.on ? 'Ausschalten' : 'Einschalten'}</button>{dimmable(light) && <Slider label={`${displayName(light.name)} Helligkeit`} value={light.brightness || 128} disabled={disabled || !light.available} save={brightness => void run('light/set', {entity_id: light.entity_id, brightness})}/>}{!light.entity_id.startsWith('switch.') && light.supported_color_modes?.some(mode => ['xy', 'hs', 'rgb', 'rgbw', 'rgbww'].includes(mode)) && <label className="color-label">{displayName(light.name)} Farbe<input aria-label={`${displayName(light.name)} Farbe`} type="color" disabled={disabled || !light.available} defaultValue={light.rgb_color ? '#' + light.rgb_color.map(value => value.toString(16).padStart(2, '0')).join('') : '#ffffff'} onChange={event => void run('light/set', {entity_id: light.entity_id, xy: rgbToXy(event.target.value)})}/></label>}{!light.entity_id.startsWith('switch.') && light.supported_color_modes?.includes('color_temp') && <Slider label={`${displayName(light.name)} Weißton`} value={light.color_temp_kelvin || light.min_color_temp_kelvin || 2700} min={light.min_color_temp_kelvin || 2000} max={light.max_color_temp_kelvin || 6500} disabled={disabled || !light.available} save={color_temp_kelvin => void run('light/set', {entity_id: light.entity_id, color_temp_kelvin})}/>}</section>)}
    </>}
  </section>;
}
