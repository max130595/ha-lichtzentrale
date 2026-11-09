// Geändert für Lichtzentrale
import {useCallback, useEffect, useRef, useState} from 'react';
import type {AdaptiveStatus} from './RuntimeControls';
import type {Binding, BindingAction, ButtonEntity, Hass, Light, Room, Scene} from './types';

const actionLabels: Record<BindingAction, string> = {
  full_brightness: 'Volle Helligkeit', night: 'Nachtlicht', return_auto: 'Zurück zur Automatik', night_auto: 'Nachtlicht ⇄ Automatik',
  toggle_room: 'Raum ein / aus', turn_on_room: 'Raum einschalten', turn_off_room: 'Raum ausschalten',
  toggle_lights: 'Ausgewählte Lichter ein / aus', turn_on_lights: 'Ausgewählte Lichter einschalten', turn_off_lights: 'Ausgewählte Lichter ausschalten',
  next_scene: 'Nächste Szene im Zyklus', scene: 'Bestimmte Szene starten', dim_up: 'Heller (10 %)', dim_down: 'Dunkler (10 %)',
  adaptive_on: 'Natürliches Licht einschalten', adaptive_off: 'Natürliches Licht ausschalten', stop_dynamic: 'Dynamik stoppen',
};
const eventLabels: Record<string, string> = {
  press: 'Drücken', press_release: 'Kurz drücken', hold: 'Lang drücken', hold_release: 'Nach langem Drücken loslassen', dial_rotate: 'Drehen', brightness_step: 'Helligkeit ändern', on_press_release: 'An kurz drücken', button_1_press_release: 'Taste 1 kurz drücken', dial_rotate_right_step: 'Nach rechts drehen',
  initial_press: 'Drücken', repeat: 'Gedrückt halten (Wiederholung)', short_release: 'Kurz drücken',
  long_press: 'Lange drücken', long_release: 'Nach langem Drücken loslassen', double_short_release: 'Doppelklick (erkannt)',
  clock_wise: 'Im Uhrzeigersinn drehen', counter_clock_wise: 'Gegen den Uhrzeigersinn drehen',
  single_push: 'Einmal drücken', double_push: 'Doppelt drücken', triple_push: 'Dreimal drücken',
  long_push: 'Lange drücken', btn_down: 'Taste drücken', btn_up: 'Taste loslassen',
};
const eventLabel = (type: string) => eventLabels[type] || type;
const failure = (error: unknown) => error instanceof Error ? error.message : typeof error === 'object' && error !== null && 'message' in error ? String(error.message) : 'Bitte erneut versuchen.';
const hasAdaptive = (status: AdaptiveStatus | null, area: string) => !!status?.available && !!status.rooms?.some(room => room.area_id === area && room.available);
const approved = (light: Light) => light.allowed && /^(light|switch)\./.test(light.entity_id);
const targetsRequired = (action: BindingAction) => ['toggle_lights', 'turn_on_lights', 'turn_off_lights'].includes(action);
type Editing = {entity: string; event: string; binding?: Binding; attributes?: Record<string, unknown>; label?: string; suggestedAction?: BindingAction; suggestedArea?: string};
type RoomSettings = {cycle: string[]; default_on: string};

export function Buttons({hass}: {hass: Hass}) {
  const api = useRef(hass); api.current = hass;
  const alive = useRef(false), lock = useRef(false), generation = useRef(0);
  const [buttons, setButtons] = useState<ButtonEntity[]>([]), [bindings, setBindings] = useState<Binding[]>([]);
  const [lights, setLights] = useState<Light[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]), [scenes, setScenes] = useState<Scene[]>([]);
  const [adaptive, setAdaptive] = useState<AdaptiveStatus | null>(null), [doubleClick, setDoubleClick] = useState(500);
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(''), [message, setMessage] = useState('');
  const [editing, setEditing] = useState<Editing | null>(null), [deleting, setDeleting] = useState<Binding | null>(null), [roomEditor, setRoomEditor] = useState('');
  const editorRef = useRef<HTMLElement>(null);
  const load = useCallback(async () => {
    const id = ++generation.current; setLoading(true); setError('');
    try {
      const [b, saved, r, s, a, l] = await Promise.all([
        api.current.callWS<ButtonEntity[]>({type: 'lichtzentrale/buttons/list'}),
        api.current.callWS<{bindings: Binding[]; double_click_ms: number}>({type: 'lichtzentrale/bindings/list'}),
        api.current.callWS<Room[]>({type: 'lichtzentrale/rooms/list'}),
        api.current.callWS<Scene[]>({type: 'lichtzentrale/scenes/list'}),
        api.current.callWS<AdaptiveStatus>({type: 'lichtzentrale/adaptive/status'}),
        api.current.callWS<Light[]>({type: 'lichtzentrale/lights/list'}),
      ]);
      if (!alive.current || id !== generation.current) return;
      setLights(l.filter(approved)); setButtons(b); setBindings(saved.bindings); setDoubleClick(saved.double_click_ms); setRooms(r); setScenes(s); setAdaptive(a); setLoaded(true);
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
  const allButtons: ButtonEntity[] = [...buttons, ...missingEntities.map(entity => ({entity_id: entity, name: 'Nicht mehr vorhandener Taster', device_id: null, device_name: '', area_id: null, event_types: [], available: false}))];
  const groups = new Map<string, {name: string; buttons: ButtonEntity[]}>();
  for (const button of allButtons) {
    const missing = !listedEntities.has(button.entity_id);
    const key = missing ? 'missing' : button.device_id ? `device:${button.device_id}` : 'unassigned';
    const group = groups.get(key) || {name: missing ? 'Nicht mehr gefundene Taster' : button.device_name || 'Taster ohne Gerät', buttons: []};
    group.buttons.push(button); groups.set(key, group);
  }
  const description = (binding: Binding) => `${actionLabels[binding.action] || binding.action} · ${binding.params.entity_ids ? binding.params.entity_ids.map(id => lights.find(light => light.entity_id === id)?.name || 'Licht nicht mehr vorhanden').join(', ') || 'Keine Lichter ausgewählt' : rooms.find(room => room.area_id === binding.area_id)?.name || 'Raum nicht mehr vorhanden'}${binding.action === 'scene' ? ` · ${scenes.find(scene => scene.id === binding.params.scene_id)?.name || 'Szene nicht mehr vorhanden'}` : ''}`;
  function openEdit(edit: Editing) {setEditing(edit); setDeleting(null); setRoomEditor(''); setError(''); setMessage('');}
  return <section aria-label="Tasterbelegungen">
    <div className="section-heading"><div><h2>Taster</h2></div><button disabled={disabled} onClick={() => {setEditing(null); setDeleting(null); setRoomEditor(''); setMessage(''); void load();}}>Taster neu laden</button></div>
    {loading && <p role="status">Taster und Belegungen werden geladen …</p>}
    {error && <p role="alert" className="error">{error}</p>}{message && <p role="status" className="notice">{message}</p>}
    {busy && <p role="status">Änderung wird in Home Assistant gespeichert …</p>}
    {loaded && <>
      {!allButtons.length && <p>Keine Taster mit Event-Entities gefunden. Richte sie zuerst in Home Assistant ein.</p>}
      {[...groups].map(([key, group]) => <section className="card button-device" key={key} aria-label={group.name}><h3>{group.name}</h3><ul>{bindings.filter(binding => group.buttons.some(button => button.entity_id === binding.event_entity)).map(binding => <li key={binding.id}>{binding.control_label || group.buttons.find(button => button.entity_id === binding.event_entity)?.name} · {eventLabel(binding.event_type)} · {description(binding)}</li>)}</ul><DeviceSetup buttons={group.buttons} rooms={rooms} hass={hass} disabled={disabled} edit={openEdit}/><details><summary>Alle Ereignisse und gespeicherte Belegungen</summary>{group.buttons.map(button => {
        const missing = !listedEntities.has(button.entity_id);
        const events = [...new Set([...button.event_types, ...bindings.filter(binding => binding.event_entity === button.entity_id).map(binding => binding.event_type)])];
        return <section key={button.entity_id} className="button-entity" aria-label={button.name}><h4>{button.name}</h4>
          {button.area_id && <p>Geräteraum: {rooms.find(room => room.area_id === button.area_id)?.name || 'Ohne freigegebene Lampen'}</p>}
          {!button.available && <p className="notice">{missing ? 'Dieser Taster wurde nicht mehr gefunden. Alte Belegungen können gelöscht werden.' : 'Taster nicht verfügbar. Belegungen bleiben gespeichert und können bearbeitet werden.'}</p>}
          {!events.length && <p>Für diesen Taster sind noch keine Ereignistypen bekannt.</p>}
          {events.map(event => {
            const assigned = bindings.filter(binding => binding.event_entity === button.entity_id && binding.event_type === event);
            const supported = button.event_types.includes(event);
            return <div className="button-event" role="group" aria-label={eventLabel(event)} key={event}><h5>{eventLabel(event)}</h5>{eventLabels[event] && <small>{event}</small>}{!supported && <p>Ereignis wird nicht mehr vom Taster angeboten.</p>}
              {assigned.length ? assigned.map(binding => <div key={binding.id}><p>{binding.control_label || button.name} · {eventLabel(binding.event_type)} · {description(binding)}</p><div className="actions"><button disabled={disabled || !supported} onClick={() => openEdit({entity: button.entity_id, event, binding})}>Belegung bearbeiten</button><button disabled={disabled} onClick={() => {setDeleting(binding); setEditing(null); setRoomEditor(''); setError(''); setMessage('');}}>Belegung löschen</button></div></div>) : <><p>Noch nicht belegt</p><button disabled={disabled || !supported || (!rooms.length && !lights.length)} onClick={() => openEdit({entity: button.entity_id, event})}>Belegen</button></>}
            </div>;
          })}
        </section>;
      })}</details></section>)}
      {editing && <section ref={editorRef} tabIndex={-1} className="card" aria-label="Belegung bearbeiten"><h3>{eventLabel(editing.event)} belegen</h3><p>{buttons.find(button => button.entity_id === editing.entity)?.name || 'Taster nicht mehr vorhanden'}<small>{editing.event}</small></p>
        <BindingEditor key={`${editing.entity}/${editing.event}/${editing.binding?.id || editing.label || 'new'}/${JSON.stringify(editing.attributes || {})}`} editing={editing} lights={lights} rooms={rooms} scenes={scenes} adaptive={adaptive} disabled={disabled} cancel={() => {setEditing(null); setError('');}} save={binding => void mutate<Binding>('binding/save', {binding}, result => {setBindings(items => [...items.filter(item => item.id !== result.id), result]); setEditing(null);}, 'Belegung in Home Assistant gespeichert.')}/>
      </section>}
      {deleting && <section ref={editorRef} tabIndex={-1} className="card" aria-label="Belegung löschen bestätigen"><h3>Belegung löschen?</h3><p>{eventLabel(deleting.event_type)} · {description(deleting)}</p><p>Der Taster bleibt in Home Assistant erhalten.</p><button disabled={disabled} onClick={() => void mutate('binding/delete', {binding_id: deleting.id}, () => {setBindings(items => items.filter(item => item.id !== deleting.id)); setDeleting(null);}, 'Belegung gelöscht.')}>Endgültig löschen</button><button className="secondary" disabled={disabled} onClick={() => {setDeleting(null); setError('');}}>Abbrechen</button></section>}
      <DoubleClickSettings key={doubleClick} value={doubleClick} disabled={disabled} save={double_click_ms => void mutate<{double_click_ms: number}>('binding/settings', {double_click_ms}, result => setDoubleClick(result.double_click_ms), 'Doppelklick-Zeit gespeichert.')}/>
      <section className="card" aria-label="Szenenzyklus und Einschalten"><h3>Szenenzyklus und Einschalten</h3><p>„Nächste Szene“ folgt dieser Reihenfolge. Nach 10 Minuten Pause startet der Zyklus wieder mit der ersten Szene.</p>
        <label>Raum für Einstellungen<select className="text-input" disabled={disabled} value={roomEditor} onChange={event => {setRoomEditor(event.target.value); setEditing(null); setDeleting(null); setError(''); setMessage('');}}><option value="">Raum oder Zone wählen</option>{rooms.map(room => <option key={room.area_id} value={room.area_id}>{room.name}</option>)}</select></label>
        {!rooms.length && <p>Keine Räume mit freigegebenen Lampen vorhanden.</p>}
        {rooms.filter(room => room.area_id === roomEditor).map(room => <RoomSettingsEditor key={room.area_id} room={room} scenes={scenes.filter(scene => scene.area_id === room.area_id).sort((a, b) => a.order - b.order)} adaptive={hasAdaptive(adaptive, room.area_id)} disabled={disabled} cancel={() => {setRoomEditor(''); setError('');}} save={settings => void mutate<RoomSettings>('room/settings', {area_id: room.area_id, ...settings}, result => {setRooms(items => items.map(item => item.area_id === room.area_id ? {...item, ...result} : item)); setRoomEditor('');}, 'Raumeinstellungen in Home Assistant gespeichert.')}/>)}
      </section>
    </>}
  </section>;
}

function BindingEditor({editing, lights, rooms, scenes, adaptive, disabled, save, cancel}: {editing: Editing; lights: Light[]; rooms: Room[]; scenes: Scene[]; adaptive: AdaptiveStatus | null; disabled: boolean; save: (binding: Omit<Binding, 'id'> & {id?: string}) => void; cancel: () => void}) {
  const [area, setArea] = useState(editing.binding?.area_id || editing.suggestedArea || '');
  const [action, setAction] = useState<BindingAction>(editing.binding?.action || editing.suggestedAction || 'toggle_room');
  const [scene, setScene] = useState(editing.binding?.params.scene_id || '');
  const [entityIds, setEntityIds] = useState<string[]>(editing.binding?.params.entity_ids || []);
  const [individual, setIndividual] = useState(editing.binding?.params.entity_ids !== undefined);
  const dimming = action === 'dim_up' || action === 'dim_down';
  const flexible = dimming || action === 'full_brightness';
  const selectedTargets = targetsRequired(action) || (flexible && individual);
  const invalidIds = entityIds.filter(id => !lights.some(light => light.entity_id === id));
  const targetGroups = new Map<string, {name: string; lights: Light[]}>();
  for (const light of lights) {
    const key = light.area_id || '';
    const group = targetGroups.get(key) || {name: rooms.find(room => room.area_id === light.area_id)?.name || light.area_name || 'Ohne Raum', lights: []};
    group.lights.push(light); targetGroups.set(key, group);
  }
  const roomScenes = scenes.filter(item => item.area_id === area).sort((a, b) => a.order - b.order);
  const adaptiveAvailable = hasAdaptive(adaptive, area);
  const valid = (selectedTargets ? entityIds.length > 0 && !invalidIds.length : rooms.some(room => room.area_id === area)) && (action !== 'scene' || roomScenes.some(item => item.id === scene)) && (!action.startsWith('adaptive_') || adaptiveAvailable);
  return <form onSubmit={event => {event.preventDefault(); if (!disabled && valid) save({...editing.binding, event_entity: editing.entity, event_type: editing.event, ...(editing.attributes ? {event_attributes: editing.attributes} : {}), ...(editing.label ? {control_label: editing.label} : {}), area_id: selectedTargets ? null : area, action, params: selectedTargets ? {entity_ids: entityIds} : action === 'scene' ? {scene_id: scene} : {}});}}><fieldset disabled={disabled}><legend>Aktion zuordnen</legend>
    {!selectedTargets && <label>Raum oder Zone<select className="text-input" value={rooms.some(room => room.area_id === area) ? area : ''} onChange={event => {const next = event.target.value; setArea(next); setScene(''); if (action.startsWith('adaptive_') && !hasAdaptive(adaptive, next)) setAction('toggle_room');}}><option value="">Raum oder Zone wählen</option>{rooms.map(room => <option key={room.area_id} value={room.area_id}>{room.name}</option>)}</select></label>}
    <label>Aktion<select className="text-input" value={action.startsWith('adaptive_') && !adaptiveAvailable ? '' : action} onChange={event => {const next = event.target.value as BindingAction; setAction(next); setScene(''); if (!targetsRequired(next) && next !== 'dim_up' && next !== 'dim_down' && next !== 'full_brightness') {setEntityIds([]); setIndividual(false);}}}><option value="" disabled>Aktion wählen</option>{(Object.entries(actionLabels) as [BindingAction, string][]).filter(([value]) => !value.startsWith('adaptive_') || adaptiveAvailable).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    {flexible && <label>Ziel<select className="text-input" value={individual ? 'lights' : 'room'} onChange={event => {setIndividual(event.target.value === 'lights'); setEntityIds([]);}}><option value="room">Raum oder Zone</option><option value="lights">Einzelne Lichter auswählen</option></select></label>}
    {selectedTargets && <fieldset><legend>Lichter auswählen</legend><p>Freigegebene Lampen und Lichtschalter aus beliebigen Räumen. Mindestens ein Licht auswählen.</p>
      {[...targetGroups].map(([key, group]) => <fieldset key={key}><legend>{group.name}</legend>{group.lights.map(light => <label className="check" key={light.entity_id} style={{minHeight: 44, overflowWrap: 'anywhere'}}><input type="checkbox" checked={entityIds.includes(light.entity_id)} onChange={() => setEntityIds(ids => ids.includes(light.entity_id) ? ids.filter(id => id !== light.entity_id) : [...ids, light.entity_id])}/><span>{light.name}{!light.available && ' (nicht verfügbar)'}</span></label>)}</fieldset>)}
      {!lights.length && <p>Keine freigegebenen Lichter vorhanden.</p>}
      {!!invalidIds.length && <div role="alert"><p>Diese Lichter sind nicht mehr freigegeben oder vorhanden. Vor dem Speichern entfernen.</p>{invalidIds.map(id => <p key={id} style={{overflowWrap: 'anywhere'}}>Licht nicht mehr vorhanden <button type="button" aria-label="Fehlendes Licht aus Auswahl entfernen" onClick={() => setEntityIds(ids => ids.filter(item => item !== id))}>Entfernen</button></p>)}</div>}
      <p>{entityIds.length} Lichter ausgewählt.</p>
      {dimming && <p>Nur eingeschaltete, dimmbare Lampen werden geändert. Lichtschalter bleiben unverändert.</p>}
    </fieldset>}
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

export function RoomSettingsEditor({room, scenes, adaptive, disabled, save, cancel}: {room: Room; scenes: Scene[]; adaptive: boolean; disabled: boolean; save: (settings: RoomSettings) => void; cancel: () => void}) {
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

const deviceKeys: Record<string, string[]> = {
  'Hue Dimmer': ['An', 'Hoch', 'Runter', 'Hue', 'Aus'],
  'Tap Dial': ['1', '2', '3', '4', 'Drehrad'],
  'Wandschalter-Modul': ['Links', 'Rechts'], Shelly: ['Taste'],
};
const templateActions: Record<string, BindingAction> = {An: 'full_brightness', Hoch: 'dim_up', Runter: 'dim_down', Hue: 'night_auto', Aus: 'turn_off_room'};
type Observation = {event_entity: string; event_type: string; event_attributes: Record<string, unknown>};

function DeviceSetup({buttons, rooms, hass, disabled, edit}: {buttons: ButtonEntity[]; rooms: Room[]; hass: Hass; disabled: boolean; edit: (editing: Editing) => void}) {
  const model = `${buttons[0]?.model || ''} ${buttons[0]?.device_name || ''}`.toLowerCase();
  const [shape, setShape] = useState(model.includes('tap') ? 'Tap Dial' : model.includes('shelly') ? 'Shelly' : model.includes('wall') ? 'Wandschalter-Modul' : 'Hue Dimmer');
  const [physical, setPhysical] = useState(''), [gesture, setGesture] = useState('Kurz drücken');
  const [source, setSource] = useState(buttons[0]?.entity_id || ''), [eventType, setEventType] = useState('');
  const [template, setTemplate] = useState(false), [target, setTarget] = useState('');
  const [token, setToken] = useState(''), [starting, setStarting] = useState(false), [error, setError] = useState('');
  const [observation, setObservation] = useState<Observation | null>(null);
  const api = useRef(hass); api.current = hass;
  const generation = useRef(0), mounted = useRef(true), startLock = useRef(false);
  useEffect(() => {const counter = generation; mounted.current = true; return () => {mounted.current = false; counter.current++;};}, []);
  useEffect(() => {
    if (!token) return;
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const result = await api.current.callWS<{status: string; observation: Observation | null}>({type: 'lichtzentrale/buttons/learn/status', token});
        if (!live) return;
        if (result.observation) {setObservation(result.observation); setToken('');}
        else timer = setTimeout(() => void poll(), 700);
      } catch (failureValue) {if (live) {setError(failure(failureValue)); setToken('');}}
    }
    void poll();
    return () => {live = false; clearTimeout(timer); void api.current.callWS({type: 'lichtzentrale/buttons/learn/cancel', token}).catch(() => undefined);};
  }, [token]);
  function cancel() {generation.current++; setToken(''); setObservation(null); setStarting(false); setError('');}
  async function learn() {
    if (startLock.current || disabled || !physical) return;
    startLock.current = true; const version = ++generation.current; setStarting(true); setError(''); setObservation(null);
    try {
      const result = await api.current.callWS<{token: string}>({type: 'lichtzentrale/buttons/learn/start', entity_id: source});
      if (!mounted.current || generation.current !== version) {await api.current.callWS({type: 'lichtzentrale/buttons/learn/cancel', token: result.token}); return;}
      setToken(result.token);
    } catch (failureValue) {if (mounted.current && generation.current === version) setError(failure(failureValue));}
    finally {startLock.current = false; if (mounted.current && generation.current === version) setStarting(false);}
  }
  const selected = buttons.find(button => button.entity_id === source);
  const frozen = disabled || starting || !!token;
  const open = (observed: Observation | null) => {
    const rawEvent = observed?.event_type || eventType;
    const event = gesture === 'Doppelklick' && rawEvent === 'short_release' ? 'double_short_release' : rawEvent;
    if (!event || !physical) return;
    edit({entity: observed?.event_entity || source, event, attributes: observed?.event_attributes, label: `${physical} · ${gesture}`, suggestedAction: template ? templateActions[physical] : undefined, suggestedArea: template ? target : undefined});
    setObservation(null);
  };
  return <div>
    <label>Gerätezeichnung<select className="text-input" disabled={frozen} value={shape} onChange={event => {cancel(); setShape(event.target.value); setPhysical(''); setTemplate(false);}}>{Object.keys(deviceKeys).map(name => <option key={name}>{name}</option>)}</select></label>
    <div role="group" aria-label={`Zeichnung ${shape}`} style={{margin: '16px auto', padding: 16, maxWidth: shape === 'Hue Dimmer' ? 160 : 250, border: '3px solid var(--border, #aaa)', borderRadius: shape === 'Tap Dial' ? 80 : 24, display: 'grid', gridTemplateColumns: shape === 'Hue Dimmer' ? '1fr' : '1fr 1fr', gap: 8}}>
      {deviceKeys[shape].map(key => <button key={key} type="button" disabled={frozen} aria-pressed={physical === key} aria-label={`${shape} ${key}`} style={{minHeight: 48}} onClick={() => {cancel(); setPhysical(key); setEventType('');}}>{key}</button>)}
    </div>
    {shape === 'Hue Dimmer' && <details><summary>Dimmer-Vorlage</summary><p>An: volle Helligkeit · Hue: Nachtlicht ⇄ Automatik · Hoch/Runter: dimmen · Aus: ausschalten.</p>
      <label>Ziel für die Vorlage<select className="text-input" value={target} disabled={frozen} onChange={event => setTarget(event.target.value)}><option value="">Raum oder Zone wählen</option>{rooms.map(room => <option key={room.area_id} value={room.area_id}>{room.name}</option>)}</select></label>
      <button type="button" disabled={frozen || !target} onClick={() => {setTemplate(true); setPhysical('An'); setError('');}}>Vorlage verwenden</button>
      {template && <p role="status">Vorlage ausgewählt. Jede Taste antippen, ihr echtes Ereignis anlernen und speichern. Das Ziel kann pro Taste geändert werden. Nachtlicht und Automatik brauchen einen Raum oder eine Zone.</p>}
    </details>}
    {physical && <section aria-label={`Taste ${physical}`}><h4>Taste {physical}</h4>
      <div className="actions">{['Kurz drücken', 'Lang drücken', 'Drehen nach links', 'Drehen nach rechts', 'Doppelklick'].map(value => <button type="button" disabled={frozen} key={value} aria-pressed={gesture === value} onClick={() => {cancel(); setGesture(value);}}>{value}</button>)}</div>
      <label>Ereignisquelle<select className="text-input" disabled={frozen} value={source} onChange={event => {cancel(); setSource(event.target.value); setEventType('');}}>{buttons.map(button => <option key={button.entity_id} value={button.entity_id}>{button.name}</option>)}</select></label>
      <button type="button" disabled={frozen || !selected?.available} onClick={() => void learn()}>Taste anlernen</button>
      {(token || starting) && <p role="status">Jetzt die gewählte Taste am Gerät betätigen. Die erste neue Meldung wird erfasst. Eine gespeicherte Lichtzentrale-Aktion für diese Meldung wird dabei nicht ausgeführt.</p>}
      {(token || starting || observation) && <button type="button" onClick={cancel}>Anlernen abbrechen</button>}
      {observation && <div><p role="status">Erkannt: {eventLabel(observation.event_type)}</p><p>Gelernte Merkmale: {Object.entries(observation.event_attributes).map(([key, value]) => `${key}: ${JSON.stringify(value)}`).join(' · ') || 'Keine zusätzlichen Merkmale'}</p><button type="button" disabled={disabled} onClick={() => open(observation)}>Aktion und Ziel auswählen</button></div>}
      {error && <p className="error" role="alert">{error}</p>}
      <details><summary>Bekanntes Ereignis direkt auswählen</summary><p>Nur verwenden, wenn die Ereignisquelle und der Typ bereits genau eine Taste bezeichnen. Bei gemeinsamen Typen die Taste anlernen.</p><select className="text-input" aria-label="Ereignis auswählen" disabled={frozen} value={eventType} onChange={event => setEventType(event.target.value)}><option value="">Ereignis wählen</option>{selected?.event_types.map(value => <option key={value} value={value}>{eventLabel(value)}</option>)}</select><button type="button" disabled={frozen || !eventType || !selected?.available} onClick={() => open(null)}>Aktion und Ziel auswählen</button></details>
    </section>}
  </div>;
}
