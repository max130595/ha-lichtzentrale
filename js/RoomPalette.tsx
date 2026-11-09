// Geändert für Lichtzentrale
import {displayName, displayError} from './display';
import {useEffect, useRef, useState} from 'react';
import {RuntimeControls} from './RuntimeControls';
import {SceneEditor} from './SceneEditor';
import {brightnessValue, errorText, percent} from './sceneControls';
import type {GuardRegistration} from './sceneControls';
import type {ApplyResult, Distribution, Hass, Palette, Room} from './types';
export function RoomPalette({hass, palette, palettes = [palette], registerGuard}: {hass: Hass; palette: Palette; palettes?: Palette[]; registerGuard?: GuardRegistration}) {
  const api = useRef(hass); api.current = hass;
  const generation = useRef(0), lock = useRef(false);
  const [rooms, setRooms] = useState<Room[]>([]), [area, setArea] = useState('');
  const [brightness, setBrightness] = useState(palette.bri), [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [error, setError] = useState(''), [message, setMessage] = useState(''), [revision, setRevision] = useState(0);
  const [distribution, setDistribution] = useState<Distribution>('zufall'), [transition, setTransition] = useState(10);
  useEffect(() => {
    const counter = generation; const id = ++counter.current;
    api.current.callWS<Room[]>({type: 'lichtzentrale/rooms/list'}).then(value => {if (id === generation.current) setRooms(Array.isArray(value) ? value : []);}).catch(e => {if (id === generation.current) setError(`Räume konnten nicht geladen werden: ${errorText(e)}`);}).finally(() => {if (id === generation.current) setLoading(false);});
    return () => {counter.current++;};
  }, []);
  const room = rooms.find(item => item.area_id === area), disabled = loading || busy;
  async function apply(target: string, value = brightness) {
    const selected = rooms.find(item => item.area_id === target);
    if (lock.current || !selected) return;
    lock.current = true; const id = generation.current; setBusy(true); setError(''); setMessage('');
    try {
      const result = await api.current.callWS<ApplyResult>({type: 'lichtzentrale/palette/apply', palette_id: palette.id, layout_area_id: target, entity_ids: selected.lights.filter(light => light.allowed).map(light => light.entity_id), brightness: value, transition, verteilung: distribution});
      if (id !== generation.current) return;
      setMessage(`${result.applied.length} Lampe(n) angewendet. ${result.skipped.length} übersprungen. ${result.failed?.length || 0} fehlgeschlagen.`); setRevision(value => value + 1);
    } catch (e) {if (id === generation.current) setError(`Anwenden fehlgeschlagen: ${errorText(e)} Einzelne Lampen könnten bereits geändert worden sein.`);}
    finally {lock.current = false; if (id === generation.current) setBusy(false);}
  }
  if (editing && room) return <SceneEditor hass={hass} room={room} palette={palette} palettes={palettes} onClose={() => setEditing(false)} onSaved={(_, notice) => {setEditing(false); setMessage(`Szene gespeichert.${notice ? ` ${notice}` : ''}`); setRevision(value => value + 1);}} registerGuard={registerGuard}/>;
  return <section className="card" aria-label="Palette im Raum anwenden"><h3>{displayName(palette.name)}</h3><div className="editor-gradient" style={{background: `linear-gradient(110deg, ${palette.preview.join(',')})`}}/>
    {error && <p role="alert">{displayError(error)}</p>}{message && <p role="status">{message}</p>}{loading && <p role="status">Räume werden geladen …</p>}
    <fieldset disabled={disabled}><label>Raum oder Zone<select className="text-input" value={area} onChange={event => {setArea(event.target.value); if (event.target.value) void apply(event.target.value);}}><option value="">Bitte Ziel wählen</option>{rooms.map(item => <option key={item.area_id} value={item.area_id} disabled={!item.available_count}>{displayName(item.name)}</option>)}</select></label><small>Die Palette wird beim Auswählen sofort angewendet.</small>
      {area && <><label className="slider">Helligkeit im Raum: {percent(brightness)} %<input aria-label="Helligkeit im Raum" type="range" min="1" max="100" value={percent(brightness)} onChange={event => setBrightness(brightnessValue(Number(event.target.value)))} onPointerUp={event => void apply(area, brightnessValue(Number(event.currentTarget.value)))} onKeyUp={event => {if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) void apply(area, brightnessValue(Number(event.currentTarget.value)));}}/></label>
      <details><summary>Mehr Optionen</summary><label>Farbverteilung<select className="text-input" value={distribution} onChange={event => setDistribution(event.target.value as Distribution)}><option value="zufall">Zufällig</option><option value="verlauf_links_rechts">Verlauf von links nach rechts</option><option value="verlauf_vorne_hinten">Verlauf von vorne nach hinten</option><option value="hoehe">Nach Höhe: unten nach oben</option></select></label><label>Übergangszeit (Sekunden)<input className="text-input" type="number" min="0" max="60" value={transition} onChange={event => setTransition(Number(event.target.value))}/></label><button disabled={!room || transition < 0 || transition > 60} onClick={() => void apply(area)}>Im gewählten Raum anwenden</button></details></>}
    </fieldset><button className="primary" disabled={disabled || !room || !room.available_count} onClick={() => setEditing(true)}>Als Szene speichern</button>
    {area && <details><summary>Mehr Optionen · Laufendes Licht</summary><RuntimeControls key={area} hass={hass} area={area} revision={revision}/></details>}
  </section>;
}
