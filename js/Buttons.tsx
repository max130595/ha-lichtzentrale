// Geändert für Lichtzentrale
import {useCallback, useEffect, useRef, useState} from 'react';
import type {AdaptiveStatus} from './RuntimeControls';
import type {Binding, BindingAction, ButtonEntity, Hass, Room, Scene} from './types';

const actionLabels: Record<BindingAction, string> = {
  toggle_room: 'Raum ein / aus', turn_on_room: 'Raum einschalten', turn_off_room: 'Raum ausschalten',
  next_scene: 'Nächste Szene im Zyklus', scene: 'Bestimmte Szene starten', dim_up: 'Heller (10 %)', dim_down: 'Dunkler (10 %)',
  adaptive_on: 'Natürliches Licht einschalten', adaptive_off: 'Natürliches Licht ausschalten', stop_dynamic: 'Dynamik stoppen',
};
const eventLabels: Record<string, string> = {
  initial_press: 'Drücken', repeat: 'Gedrückt halten (Wiederholung)', short_release: 'Kurz drücken',
  long_press: 'Lange drücken', long_release: 'Nach langem Drücken loslassen', double_short_release: 'Doppelklick (erkannt)',
  clock_wise: 'Im Uhrzeigersinn drehen', counter_clock_wise: 'Gegen den Uhrzeigersinn drehen',
  single_push: 'Einmal drücken', double_push: 'Doppelt drücken', triple_push: 'Dreimal drücken',
  long_push: 'Lange drücken', btn_down: 'Taste drücken', btn_up: 'Taste loslassen',
};
const eventLabel = (type: string) => eventLabels[type] || 'Geräteereignis';
const failure = (error: unknown) => error instanceof Error ? error.message : typeof error === 'object' && error !== null && 'message' in error ? String(error.message) : 'Bitte erneut versuchen.';
const hasAdaptive = (status: AdaptiveStatus | null, area: string) => !!status?.available && !!status.rooms?.some(room => room.area_id === area && room.available);
type Editing = {entity: string; event: string; binding?: Binding};
type RoomSettings = {cycle: string[]; default_on: string};

export function Buttons({hass}: {hass: Hass}) {
  const api = useRef(hass); api.current = hass;
  const alive = useRef(false), lock = useRef(false), generation = useRef(0);
  const [buttons, setButtons] = useState<ButtonEntity[]>([]), [bindings, setBindings] = useState<Binding[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]), [scenes, setScenes] = useState<Scene[]>([]);
  const [adaptive, setAdaptive] = useState<AdaptiveStatus | null>(null), [doubleClick, setDoubleClick] = useState(500);
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(''), [message, setMessage] = useState('');
  const [editing, setEditing] = useState<Editing | null>(null), [deleting, setDeleting] = useState<Binding | null>(null), [roomEditor, setRoomEditor] = useState('');
  const editorRef = useRef<HTMLElement>(null);
  const load = useCallback(async () => {
    const id = ++generation.current; setLoading(true); setError('');
    try {
      const [b, saved, r, s, a] = await Promise.all([
        api.current.callWS<ButtonEntity[]>({type: 'lichtzentrale/buttons/list'}),
        api.current.callWS<{bindings: Binding[]; double_click_ms: number}>({type: 'lichtzentrale/bindings/list'}),
        api.current.callWS<Room[]>({type: 'lichtzentrale/rooms/list'}),
        api.current.callWS<Scene[]>({type: 'lichtzentrale/scenes/list'}),
        api.current.callWS<AdaptiveStatus>({type: 'lichtzentrale/adaptive/status'}),
      ]);
      if (!alive.current || id !== generation.current) return;
      setButtons(b); setBindings(saved.bindings); setDoubleClick(saved.double_click_ms); setRooms(r); setScenes(s); setAdaptive(a); setLoaded(true);
    } catch (error) {if (alive.current && id === generation.current) setError(`Taster konnten nicht geladen werden: ${failure(error)}`);}
    finally {if (alive.current && id === generation.current) setLoading(false);}
  }, []);
  useEffect(() => {const counter = generation; alive.current = true; void load(); return () => {alive.current = false; counter.current++;};}, [load]);
  useEffect(() => {
    if (editing || deleting) {editorRef.current?.scrollIntoView?.({block: 'nearest'}); editorRef.current?.focus({preventScroll: true});}
  }, [editing, deleting]);
  async function mutate<T,>(type: string, data: Record<string, unknown>, saved: (result: T) => void, text: string) {
    if (lock.current || loading) return;
    lock.current = true; setBusy(true); setError(''); setMessage('');
    try {
      const result = await api.current.callWS<T>({type: `lichtzentrale/${type}`, ...data});
      if (!alive.current) return;
      saved(result); setMessage(text);
    } catch (error) {if (alive.current) setError(`Speichern fehlgeschlagen: ${failure(error)} Bei unklarem Zustand Daten neu laden.`);}
    finally {lock.current = false; if (alive.current) setBusy(false);}
  }
  const disabled = busy || loading;
  const listedEntities = new Set(buttons.map(button => button.entity_id));
  const missingEntities = [...new Set(bindings.map(binding => binding.event_entity))].filter(entity => !listedEntities.has(entity));
  const allButtons: ButtonEntity[] = [...buttons, ...missingEntities.map(entity => ({entity_id: entity, name: entity, device_id: null, device_name: '', area_id: null, event_types: [], available: false}))];
  const groups = new Map<string, {name: string; buttons: ButtonEntity[]}>();
  for (const button of allButtons) {
    const missing = !listedEntities.has(button.entity_id);
    const key = missing ? 'missing' : button.device_id ? `device:${button.device_id}` : 'unassigned';
    const group = groups.get(key) || {name: missing ? 'Nicht mehr gefundene Taster' : button.device_name || 'Taster ohne Gerät', buttons: []};
    group.buttons.push(button); groups.set(key, group);
  }
  const description = (binding: Binding) => `${actionLabels[binding.action] || binding.action} · ${rooms.find(room => room.area_id === binding.area_id)?.name || 'Raum nicht mehr vorhanden'}${binding.action === 'scene' ? ` · ${scenes.find(scene => scene.id === binding.params.scene_id)?.name || 'Szene nicht mehr vorhanden'}` : ''}`;
  function openEdit(edit: Editing) {setEditing(edit); setDeleting(null); setRoomEditor(''); setError(''); setMessage('');}
  return <section aria-label="Tasterbelegungen">
    <div className="section-heading"><div><h2>Taster</h2><p>Taste und Ereignis wählen, Raum und Aktion zuordnen.</p></div><button disabled={disabled} onClick={() => {setEditing(null); setDeleting(null); setRoomEditor(''); setMessage(''); void load();}}>Taster neu laden</button></div>
    {loading && <p role="status">Taster und Belegungen werden geladen …</p>}
    {error && <p role="alert" className="error">{error}</p>}{message && <p role="status" className="notice">{message}</p>}
    {busy && <p role="status">Änderung wird in Home Assistant gespeichert …</p>}
    {loaded && <>
      {!allButtons.length && <p>Keine Taster mit Event-Entities gefunden. Richte sie zuerst in Home Assistant ein.</p>}
      {[...groups].map(([key, group]) => <section className="card button-device" key={key} aria-label={group.name}><h3>{group.name}</h3>{group.buttons.map(button => {
        const missing = !listedEntities.has(button.entity_id);
        const events = [...new Set([...button.event_types, ...bindings.filter(binding => binding.event_entity === button.entity_id).map(binding => binding.event_type)])];
        return <section key={button.entity_id} className="button-entity" aria-label={button.name}><h4>{button.name}</h4><small>{button.entity_id}</small>
          {button.area_id && <p>Geräteraum: {rooms.find(room => room.area_id === button.area_id)?.name || 'Ohne freigegebene Lampen'}</p>}
          {!button.available && <p className="notice">{missing ? 'Dieser Taster wurde nicht mehr gefunden. Alte Belegungen können gelöscht werden.' : 'Taster nicht verfügbar. Belegungen bleiben gespeichert und können bearbeitet werden.'}</p>}
          {!events.length && <p>Für diesen Taster sind noch keine Ereignistypen bekannt.</p>}
          {events.map(event => {
            const assigned = bindings.filter(binding => binding.event_entity === button.entity_id && binding.event_type === event);
            const supported = button.event_types.includes(event);
            return <div className="button-event" role="group" aria-label={eventLabel(event)} key={event}><h5>{eventLabel(event)}</h5><small>{event}</small>{!supported && <p>Ereignis wird nicht mehr vom Taster angeboten.</p>}
              {assigned.length ? assigned.map(binding => <div key={binding.id}><p>{description(binding)}</p><div className="actions"><button disabled={disabled || !supported} onClick={() => openEdit({entity: button.entity_id, event, binding})}>Belegung bearbeiten</button><button disabled={disabled} onClick={() => {setDeleting(binding); setEditing(null); setRoomEditor(''); setError(''); setMessage('');}}>Belegung löschen</button></div></div>) : <><p>Noch nicht belegt</p><button disabled={disabled || !supported || !rooms.length} onClick={() => openEdit({entity: button.entity_id, event})}>Belegen</button></>}
            </div>;
          })}
        </section>;
      })}</section>)}
      {editing && <section ref={editorRef} tabIndex={-1} className="card" aria-label="Belegung bearbeiten"><h3>{eventLabel(editing.event)} belegen</h3><p>{buttons.find(button => button.entity_id === editing.entity)?.name || editing.entity}<small>{editing.event}</small></p>
        <BindingEditor key={`${editing.entity}/${editing.event}/${editing.binding?.id || 'new'}`} editing={editing} rooms={rooms} scenes={scenes} adaptive={adaptive} disabled={disabled} cancel={() => {setEditing(null); setError('');}} save={binding => void mutate<Binding>('binding/save', {binding}, result => {setBindings(items => [...items.filter(item => item.id !== result.id), result]); setEditing(null);}, 'Belegung in Home Assistant gespeichert.')}/>
      </section>}
      {deleting && <section ref={editorRef} tabIndex={-1} className="card" aria-label="Belegung löschen bestätigen"><h3>Belegung löschen?</h3><p>{eventLabel(deleting.event_type)} · {description(deleting)}</p><p>Der Taster bleibt in Home Assistant erhalten.</p><button disabled={disabled} onClick={() => void mutate('binding/delete', {binding_id: deleting.id}, () => {setBindings(items => items.filter(item => item.id !== deleting.id)); setDeleting(null);}, 'Belegung gelöscht.')}>Endgültig löschen</button><button className="secondary" disabled={disabled} onClick={() => {setDeleting(null); setError('');}}>Abbrechen</button></section>}
      <DoubleClickSettings key={doubleClick} value={doubleClick} disabled={disabled} save={double_click_ms => void mutate<{double_click_ms: number}>('binding/settings', {double_click_ms}, result => setDoubleClick(result.double_click_ms), 'Doppelklick-Zeit gespeichert.')}/>
      <section className="card" aria-label="Szenenzyklus und Einschalten"><h3>Szenenzyklus und Einschalten</h3><p>„Nächste Szene“ folgt dieser Reihenfolge. Nach 10 Minuten Pause startet der Zyklus wieder mit der ersten Szene.</p>
        <label>Raum für Einstellungen<select className="text-input" disabled={disabled} value={roomEditor} onChange={event => {setRoomEditor(event.target.value); setEditing(null); setDeleting(null); setError(''); setMessage('');}}><option value="">Raum wählen</option>{rooms.map(room => <option key={room.area_id} value={room.area_id}>{room.name}</option>)}</select></label>
        {!rooms.length && <p>Keine Räume mit freigegebenen Lampen vorhanden.</p>}
        {rooms.filter(room => room.area_id === roomEditor).map(room => <RoomSettingsEditor key={room.area_id} room={room} scenes={scenes.filter(scene => scene.area_id === room.area_id).sort((a, b) => a.order - b.order)} adaptive={hasAdaptive(adaptive, room.area_id)} disabled={disabled} cancel={() => {setRoomEditor(''); setError('');}} save={settings => void mutate<RoomSettings>('room/settings', {area_id: room.area_id, ...settings}, result => {setRooms(items => items.map(item => item.area_id === room.area_id ? {...item, ...result} : item)); setRoomEditor('');}, 'Raumeinstellungen in Home Assistant gespeichert.')}/>)}
      </section>
    </>}
  </section>;
}

function BindingEditor({editing, rooms, scenes, adaptive, disabled, save, cancel}: {editing: Editing; rooms: Room[]; scenes: Scene[]; adaptive: AdaptiveStatus | null; disabled: boolean; save: (binding: Omit<Binding, 'id'> & {id?: string}) => void; cancel: () => void}) {
  const [area, setArea] = useState(editing.binding?.area_id || '');
  const [action, setAction] = useState<BindingAction>(editing.binding?.action || 'toggle_room');
  const [scene, setScene] = useState(editing.binding?.params.scene_id || '');
  const roomScenes = scenes.filter(item => item.area_id === area).sort((a, b) => a.order - b.order);
  const adaptiveAvailable = hasAdaptive(adaptive, area);
  const valid = rooms.some(room => room.area_id === area) && (action !== 'scene' || roomScenes.some(item => item.id === scene)) && (!action.startsWith('adaptive_') || adaptiveAvailable);
  return <form onSubmit={event => {event.preventDefault(); if (!disabled && valid) save({...editing.binding, event_entity: editing.entity, event_type: editing.event, area_id: area, action, params: action === 'scene' ? {scene_id: scene} : {}});}}><fieldset disabled={disabled}><legend>Aktion zuordnen</legend>
    <label>Zielraum<select className="text-input" value={rooms.some(room => room.area_id === area) ? area : ''} onChange={event => {const next = event.target.value; setArea(next); setScene(''); if (action.startsWith('adaptive_') && !hasAdaptive(adaptive, next)) setAction('toggle_room');}}><option value="">Raum wählen</option>{rooms.map(room => <option key={room.area_id} value={room.area_id}>{room.name}</option>)}</select></label>
    <label>Aktion<select className="text-input" value={action.startsWith('adaptive_') && !adaptiveAvailable ? '' : action} onChange={event => {setAction(event.target.value as BindingAction); setScene('');}}><option value="" disabled>Aktion wählen</option>{(Object.entries(actionLabels) as [BindingAction, string][]).filter(([value]) => !value.startsWith('adaptive_') || adaptiveAvailable).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    {action === 'scene' && <label>Szene<select className="text-input" value={roomScenes.some(item => item.id === scene) ? scene : ''} onChange={event => setScene(event.target.value)}><option value="">Szene wählen</option>{roomScenes.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>{!roomScenes.length && <small>In diesem Raum ist noch keine Szene gespeichert.</small>}</label>}
    {action === 'next_scene' && <p>Den Szenenzyklus legst du unter „Szenenzyklus und Einschalten“ fest.</p>}
    {action === 'turn_on_room' && <p>Verwendet die Einschalt-Einstellung des Zielraums.</p>}
    {action.startsWith('adaptive_') && !adaptiveAvailable && <p>Natürliches Licht ist für diesen Raum nicht verfügbar. Bitte eine andere Aktion wählen.</p>}
    <button type="submit" disabled={!valid}>Belegung speichern</button><button type="button" className="secondary" onClick={cancel}>Abbrechen</button>
  </fieldset></form>;
}

function DoubleClickSettings({value, disabled, save}: {value: number; disabled: boolean; save: (value: number) => void}) {
  const [draft, setDraft] = useState(String(value));
  const number = Number(draft), valid = draft.trim() !== '' && Number.isInteger(number) && number >= 200 && number <= 1000;
  return <section className="card" aria-label="Doppelklick einstellen"><h3>Doppelklick einstellen</h3><p>Nur Taster mit „short_release“ erhalten den erkannten Doppelklick. Eine Einfach-Aktion wartet nur dann auf diese Zeit, wenn für dieselbe Taste ein Doppelklick belegt ist. Native Doppelklick-Ereignisse bleiben unverändert.</p><p>Gespeichert: {value} ms</p>
    <form onSubmit={event => {event.preventDefault(); if (!disabled && valid && number !== value) save(number);}}><fieldset disabled={disabled}><legend>Zeitfenster</legend><label>Doppelklick-Zeit in Millisekunden<input className="text-input" type="number" min={200} max={1000} step={1} value={draft} onChange={event => setDraft(event.target.value)}/></label><small>200 bis 1000 Millisekunden</small><button type="submit" disabled={!valid || number === value}>Doppelklick-Zeit speichern</button><button type="button" className="secondary" disabled={draft === String(value)} onClick={() => setDraft(String(value))}>Änderung verwerfen</button></fieldset></form>
  </section>;
}

function RoomSettingsEditor({room, scenes, adaptive, disabled, save, cancel}: {room: Room; scenes: Scene[]; adaptive: boolean; disabled: boolean; save: (settings: RoomSettings) => void; cancel: () => void}) {
  const [cycle, setCycle] = useState(room.cycle || []), [defaultOn, setDefaultOn] = useState(room.default_on || 'last');
  const exists = (id: string) => scenes.some(scene => scene.id === id);
  const validDefault = defaultOn === 'last' || (defaultOn === 'adaptive' && adaptive) || exists(defaultOn);
  const valid = validDefault && cycle.every(exists);
  const reorder = (index: number, offset: number) => setCycle(items => {const next = [...items]; [next[index], next[index + offset]] = [next[index + offset], next[index]]; return next;});
  return <form onSubmit={event => {event.preventDefault(); if (!disabled && valid) save({cycle, default_on: defaultOn});}}><fieldset disabled={disabled}><legend>{room.name}: Einstellungen bearbeiten</legend>
    <label>Beim Einschalten<select className="text-input" value={validDefault ? defaultOn : ''} onChange={event => setDefaultOn(event.target.value)}><option value="" disabled>Bisherige Einstellung nicht verfügbar: bitte wählen</option><option value="last">Letzten Zustand wiederherstellen</option>{adaptive && <option value="adaptive">Natürliches Licht starten</option>}{scenes.map(scene => <option key={scene.id} value={scene.id}>Szene: {scene.name}</option>)}</select></label>
    <h4>Szenen im Zyklus</h4>{!scenes.length && <p>Speichere zuerst eine Szene auf der Raum-Seite.</p>}{scenes.map(scene => <label className="check" key={scene.id}><input type="checkbox" checked={cycle.includes(scene.id)} onChange={() => setCycle(items => items.includes(scene.id) ? items.filter(id => id !== scene.id) : [...items, scene.id])}/>{scene.name}</label>)}
    <h4>Reihenfolge</h4>{!cycle.length && <p>Der Zyklus ist leer. „Nächste Szene“ startet dann keine Szene.</p>}
    <ol className="cycle-list">{cycle.map((id, index) => {const name = scenes.find(scene => scene.id === id)?.name || 'Szene nicht mehr vorhanden'; return <li key={id}><span>{name}</span><div className="actions"><button type="button" aria-label={`${name} im Zyklus nach oben`} disabled={index === 0} onClick={() => reorder(index, -1)}>↑</button><button type="button" aria-label={`${name} im Zyklus nach unten`} disabled={index === cycle.length - 1} onClick={() => reorder(index, 1)}>↓</button><button type="button" aria-label={`${name} aus Zyklus entfernen`} onClick={() => setCycle(items => items.filter(item => item !== id))}>Entfernen</button></div></li>;})}</ol>
    {!cycle.every(exists) && <p>Entferne nicht mehr vorhandene Szenen vor dem Speichern.</p>}
    <button type="submit" disabled={!valid}>Raumeinstellungen speichern</button><button type="button" className="secondary" onClick={cancel}>Abbrechen</button>
  </fieldset></form>;
}
