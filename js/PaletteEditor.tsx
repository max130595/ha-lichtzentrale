// Geändert für Lichtzentrale
import {useEffect, useMemo, useRef, useState} from 'react';
import {displayError, displayName} from './display';
import {brightnessValue, errorText, percent, tempos} from './sceneControls';
import type {GuardRegistration} from './sceneControls';
import {useLivePreview} from './useLivePreview';
import type {Hass, Palette, Room, Tempo} from './types';
export function PaletteEditor({hass, palette, duplicate = false, onClose, onSaved, registerGuard}: {hass: Hass; palette?: Palette; duplicate?: boolean; onClose: () => void; onSaved: (palette: Palette, notice?: string) => void; registerGuard?: GuardRegistration}) {
  const [draft, setDraft] = useState<Partial<Palette>>(() => ({...(palette && !duplicate ? {id: palette.id} : {}), name: palette ? `${palette.name}${duplicate ? ' · Eigene Variante' : ''}` : '', category: palette?.category || 'Eigene', bri: palette?.bri || 140, tempo: palette?.tempo || 'slow', preview: palette?.preview.length ? [...palette.preview] : ['#ff9a2e', '#ff6a13']}));
  const [rooms, setRooms] = useState<Room[]>([]), [area, setArea] = useState('');
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const mounted = useRef(false), operation = useRef(false), api = useRef(hass); api.current = hass;
  useEffect(() => {let active = true; mounted.current = true; void api.current.callWS<Room[]>({type: 'lichtzentrale/rooms/list'}).then(value => {if (active) setRooms(Array.isArray(value) ? value : []);}).catch(e => {if (active) setError(errorText(e));}); return () => {active = false; mounted.current = false;};}, []);
  const document = useMemo(() => ({palette: {...draft, name: draft.name?.trim() || 'Neue Palette'}}), [draft]);
  const live = useLivePreview(hass, area, document, !!area, registerGuard);
  const colors = draft.preview || [];
  const disabled = busy || live.closing;
  const invalid = !draft.name?.trim() || !draft.category?.trim() || colors.length < 2 || colors.length > 6;
  function update(patch: Partial<Palette>) {setDraft(current => ({...current, ...patch}));}
  async function cancel() {if (operation.current) return; operation.current = true; if (await live.cancel()) onClose(); operation.current = false;}
  async function save() {
    if (operation.current || invalid || disabled) return;
    operation.current = true; setBusy(true); setError('');
    const final = {...draft, name: draft.name!.trim(), category: draft.category!.trim()};
    try {
      const committed = area ? await live.commit({palette: final}) : null;
      const result = area ? committed?.palette : await api.current.callWS<Palette>({type: 'lichtzentrale/palette/save', palette: final});
      if (result && mounted.current) onSaved(result, [...(committed?.notes || []), ...(committed?.skipped?.length ? [`${committed.skipped.length} Lampe(n) wurden übersprungen.`] : [])].join(' '));
    } catch (e) {if (mounted.current) setError(`Speichern fehlgeschlagen: ${errorText(e)}`);}
    finally {operation.current = false; if (mounted.current) setBusy(false);}
  }
  return <section className="palette-editor" data-testid="palette-editor" aria-label="Paletten-Editor">
    <div className="section-heading"><h2>{palette && !duplicate ? 'Palette bearbeiten' : 'Neue Palette'}</h2><button disabled={busy || (live.closing && live.busy)} onClick={() => void cancel()}>Abbrechen</button></div>
    {duplicate && <p>Eigene Variante aus „{displayName(palette?.name || '')}“.</p>}
    {(error || live.error) && <p className="error" role="alert">{displayError(error || live.error)}</p>}
    <div className="editor-gradient" aria-label="Farbvorschau" style={{background: `linear-gradient(110deg, ${colors.join(',')})`}}/>
    <fieldset disabled={disabled}><label>Palettenname<input className="text-input" maxLength={100} value={draft.name} onChange={event => update({name: event.target.value})}/></label><label>Kategorie<input className="text-input" list="palette-categories" maxLength={100} value={draft.category} onChange={event => update({category: event.target.value})}/></label><datalist id="palette-categories">{['Herbst', 'Winter', 'Weihnachten', 'Frühling', 'Sommer', 'Party', 'Entspannen', 'Romantik', 'Eigene'].map(category => <option key={category} value={category}/>)}</datalist>
      <h3 className="colors-title">Farben</h3><div className="palette-color-list">{colors.map((color, index) => <div className="palette-color-row" key={index}><label>Farbe {index + 1}<input type="color" aria-label={`Farbe ${index + 1}`} value={color} onChange={event => update({preview: colors.map((value, at) => at === index ? event.target.value : value)})}/></label><button aria-label={`Farbe ${index + 1} entfernen`} disabled={colors.length <= 2} onClick={() => update({preview: colors.filter((_, at) => at !== index)})}>Entfernen</button></div>)}</div><button disabled={colors.length >= 6} onClick={() => update({preview: [...colors, '#ffc247']})}>+ Farbe hinzufügen</button><small>2 bis 6 Farben</small>
      <label className="slider">Grundhelligkeit: {percent(draft.bri || 140)} %<input aria-label="Grundhelligkeit" type="range" min="1" max="100" value={percent(draft.bri || 140)} onChange={event => update({bri: brightnessValue(Number(event.target.value))})}/></label>
      <label>Tempo<select className="text-input" value={draft.tempo} onChange={event => update({tempo: event.target.value as Tempo})}>{Object.entries(tempos).map(([value, item]) => <option key={value} value={value}>{item.label}</option>)}</select></label>
      <section className="live-probe"><h3>Live-Probe</h3><p>Im Ziel ausprobieren. Abbrechen stellt vorheriges Licht wieder her.</p><label>Raum oder Zone<select className="text-input" value={area} disabled={!!area} onChange={event => setArea(event.target.value)}><option value="">Ohne Live-Probe</option>{rooms.map(room => <option key={room.area_id} value={room.area_id} disabled={!room.available_count}>{displayName(room.name)}</option>)}</select></label>
        {area && <button disabled={live.busy} onClick={() => {void live.cancel().then(ok => {if (ok) setArea('');});}}>Ziel wechseln</button>}
        {area && !live.ready && !live.error && <p role="status">Vorherigen Zustand sichern …</p>}{live.message && <p role="status">{live.message}</p>}
      </section>
    </fieldset><div className="editor-footer"><button className="primary" disabled={disabled || invalid || (!!area && !live.ready)} onClick={() => void save()}>{busy ? 'Bitte warten …' : 'Palette speichern'}</button></div>
  </section>;
}
