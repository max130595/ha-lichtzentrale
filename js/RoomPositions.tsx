// Geändert für Lichtzentrale
import {displayName, displayError} from './display';
import {useEffect, useRef, useState} from 'react';
import type {Distribution, Hass, Position, Room} from './types';
const heights: Record<Position['height'], string> = {boden: 'Boden · unter 50 cm', moebel: 'Möbelhöhe · etwa 1,20 m', hintergrund: 'Hintergrund · hinter TV/Möbeln, indirekt', decke: 'Decke · oben im Raum'};
const columns = ['links', 'mitte', 'rechts'], rows = ['vorne', 'mitte', 'hinten'];
export const distributionLabel = (value?: Distribution) => ({zufall: 'Zufällig', verlauf_links_rechts: 'Links nach rechts', verlauf_vorne_hinten: 'Vorne nach hinten', hoehe: 'Nach Höhe'}[value || 'zufall']);
type Props = {hass: Hass; room: Room; disabled?: boolean; onBusy?: (busy: boolean) => void; onSaved: (entity: string, position: Position | null) => void};
export function RoomPositions(props: Props) {return <PositionEditor key={props.room.area_id} {...props}/>;}
function PositionEditor({hass, room, disabled = false, onBusy, onSaved}: Props) {
  const [selected, setSelected] = useState(''), [height, setHeight] = useState<Position['height']>('moebel');
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('');
  const busyCallback = useRef(onBusy); busyCallback.current = onBusy;
  const alive = useRef(false), lock = useRef(false);
  useEffect(() => {alive.current = true; return () => {alive.current = false; busyCallback.current?.(false);};}, []);
  const lights = room.lights.filter(light => light.allowed);
  const lamp = lights.find(light => light.entity_id === selected);
  const position = lamp ? room.positions?.[lamp.entity_id] : undefined;
  async function save(next: Position | null) {
    if (lock.current || disabled || !lamp) return;
    lock.current = true; setBusy(true); busyCallback.current?.(true); setError(''); setMessage('');
    try {
      const result = await hass.callWS<Position | null>({type: 'lichtzentrale/room/position', area_id: room.area_id, entity_id: lamp.entity_id, position: next});
      if (!alive.current) return;
      onSaved(lamp.entity_id, result);
      if (result) setHeight(result.height);
      setMessage(result ? `Position für ${displayName(lamp.name)} gespeichert.` : `Position für ${displayName(lamp.name)} entfernt.`);
    } catch (error) {
      if (alive.current) setError(`Position konnte nicht gespeichert werden: ${error instanceof Error ? error.message : typeof error === 'object' && error && 'message' in error ? String(error.message) : 'Bitte erneut versuchen.'} Bei unklarem Zustand Räume neu laden.`);
    } finally {lock.current = false; if (alive.current) {setBusy(false); busyCallback.current?.(false);}}
  }
  return <section className="card" aria-label="Lampen anordnen"><h3>Lampen anordnen</h3><p>1. Lampe antippen. 2. Feld wählen. 3. Höhe einstellen. Mehrere Lampen dürfen dasselbe Feld belegen. Nicht verfügbare Lampen lassen sich ebenfalls anordnen.</p>
    {error && <p role="alert">{displayError(error)}</p>}{message && <p role="status">{message}</p>}{busy && <p role="status">Position wird gespeichert …</p>}
    <fieldset disabled={disabled || busy}><legend>Lampe auswählen</legend><div className="position-lamps">{lights.map(light => <button key={light.entity_id} aria-pressed={selected === light.entity_id} onClick={() => {setSelected(light.entity_id); setHeight(room.positions?.[light.entity_id]?.height || 'moebel'); setError(''); setMessage('');}}>{displayName(light.name)}{' '}<small>{room.positions?.[light.entity_id] ? heights[room.positions[light.entity_id].height] : 'Ohne Position'}</small></button>)}</div></fieldset>
    <fieldset disabled={disabled || busy || !lamp}><legend>Position im Raum{lamp ? `: ${displayName(lamp.name)}` : ' · zuerst Lampe wählen'}</legend><p>Obere Reihe: vorne. Untere Reihe: hinten.</p><div className="position-grid">{rows.flatMap((row, y) => columns.map((column, x) => <button key={`${x}-${y}`} aria-label={`${row} ${column}`} aria-pressed={!!position && position.cell[0] === x && position.cell[1] === y} onClick={() => void save({cell: [x, y], height: position?.height || height})}><strong>{row}<br/>{column}</strong><span>{lights.filter(light => room.positions?.[light.entity_id]?.cell[0] === x && room.positions?.[light.entity_id]?.cell[1] === y).map(light => <small key={light.entity_id}>{displayName(light.name)}</small>)}</span></button>))}</div>
    <label>Höhe der Lampe<select className="text-input" value={position?.height || height} onChange={event => {const next = event.target.value as Position['height']; if (position) void save({...position, height: next}); else setHeight(next);}}>{Object.entries(heights).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><p>Ohne Position werden Lampen bei räumlichen Effekten zuletzt einsortiert. Die Höhe wird zusammen mit dem Feld gespeichert.</p><button disabled={!position} onClick={() => void save(null)}>Position entfernen</button></fieldset>
  </section>;
}
