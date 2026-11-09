// Geändert für Lichtzentrale
import {useEffect, useMemo, useRef, useState} from 'react';
import {displayError, displayName} from './display';
import {brightnessValue, dimmable, moonIllumination, percent, rgbToXy, tempos, xyToHex} from './sceneControls';
import type {GuardRegistration} from './sceneControls';
import {useLivePreview} from './useLivePreview';
import type {LampSetting, Light, MoonSettings, Palette, Room, Scene, Tempo, Hass} from './types';
export function normalizeScene(scene: Scene, room: Room): Scene {
  const lights = {...scene.lights}, lamp_settings = {...scene.lamp_settings};
  for (const light of room.lights) {
    if (!dimmable(light)) {
      if (lamp_settings[light.entity_id]) lamp_settings[light.entity_id] = {mode: lamp_settings[light.entity_id].mode === 'off' ? 'off' : 'fixed', brightness: null};
      if (lights[light.entity_id]) lights[light.entity_id] = {on: lights[light.entity_id].on};
    }
  }
  return {...scene, ...(scene.kind === 'snapshot' ? {lights} : {}), lamp_settings};
}
const defaultMoon = (): MoonSettings => ({new_brightness: 26, full_brightness: 204, new_xy: [.25, .27], full_xy: [.3127, .329], breath: false});
export function snapshotLights(room: Room): NonNullable<Scene['lights']> {
  return Object.fromEntries(room.lights.filter(light => light.allowed && light.available).map(light => {
    const value: NonNullable<Scene['lights']>[string] = {on: !!light.on};
    if (light.on && dimmable(light)) {
      if (typeof light.brightness === 'number' && light.brightness > 0) value.brightness = light.brightness;
      if (light.color_mode === 'color_temp' && light.color_temp_kelvin) value.color_temp_kelvin = light.color_temp_kelvin;
      else if (light.xy_color) value.xy = light.xy_color;
      else if (light.rgb_color) value.xy = rgbToXy('#' + light.rgb_color.map(value => value.toString(16).padStart(2, '0')).join(''));
      else if (light.color_temp_kelvin) value.color_temp_kelvin = light.color_temp_kelvin;
    }
    return [light.entity_id, value];
  }));
}
export function LampSceneRow({light, setting, palette, sceneBrightness, moon, update, disabled, unchanged = false}: {unchanged?: boolean; light: Light; setting: LampSetting; palette?: Palette; sceneBrightness: number; moon: number; update: (value: LampSetting) => void; disabled: boolean}) {
  const name = displayName(light.name), isDimmable = dimmable(light);
  const moonSettings = {...defaultMoon(), ...setting.moon};
  const source = setting.palette_index !== undefined ? 'palette' : setting.color_temp_kelvin !== undefined ? 'white' : 'color';
  const setMoon = (patch: Partial<MoonSettings>) => update({...setting, moon: {...moonSettings, ...patch}});
  return <fieldset className="lamp-scene-row" data-testid="lamp-scene-row" disabled={disabled}>
    <legend>{name}</legend>
    {!light.available && <small>Nicht verfügbar. Einstellungen werden trotzdem gespeichert.</small>}
    {!isDimmable ? <label>{name} An / Aus<select className="text-input" aria-label={`${name} An / Aus`} value={unchanged ? 'unchanged' : setting.mode === 'off' ? 'off' : 'cycle'} onChange={event => update({mode: event.target.value === 'off' ? 'off' : 'fixed'})}>{unchanged && <option value="unchanged">Wie bisher · unverändert</option>}<option value="cycle">An</option><option value="off">Aus</option></select><small>Nur Ein/Aus · keine Helligkeits- oder Farbbefehle.</small></label> : <>
      {setting.mode !== 'off' && <><label>Helligkeit<select className="text-input" aria-label={`${name} Helligkeit`} value={setting.brightness == null ? 'scene' : 'fixed'} onChange={event => update({...setting, brightness: event.target.value === 'scene' ? null : sceneBrightness})}><option value="scene">Wie Szene</option><option value="fixed">Fest für diese Lampe</option></select></label>
        {setting.brightness != null && <label className="slider">Fest: {percent(setting.brightness)} %<input aria-label={`${name} feste Helligkeit`} type="range" min="1" max="100" value={percent(setting.brightness)} onChange={event => update({...setting, brightness: brightnessValue(Number(event.target.value))})}/></label>}</>}
      <label>Verhalten<select className="text-input" aria-label={`${name} Verhalten`} value={setting.mode} onChange={event => {
        const mode = event.target.value as LampSetting['mode'];
        update({mode, brightness: setting.brightness ?? null, ...(mode === 'fixed' ? palette?.preview.length ? {palette_index: 0} : {color_temp_kelvin: light.color_temp_kelvin || 2700} : {}), ...(mode === 'moon' ? {moon: defaultMoon()} : {})});
      }}><option value="cycle">Farbwechsel</option><option value="fixed">Feste Farbe</option><option value="moon">Mondlicht nach Mondphase</option><option value="off">In dieser Szene aus</option></select></label>
      {setting.mode === 'fixed' && <><label>Farbe auswählen<select className="text-input" aria-label={`${name} Farbquelle`} value={source} onChange={event => {
        const base: LampSetting = {mode: 'fixed', brightness: setting.brightness ?? null};
        update(event.target.value === 'palette' ? {...base, palette_index: 0} : event.target.value === 'white' ? {...base, color_temp_kelvin: light.color_temp_kelvin || 2700} : {...base, xy: rgbToXy('#ff9a2e')});
      }}>{palette && <option value="palette">Aus der Palette</option>}<option value="color">Eigene Farbe</option><option value="white">Weißton</option></select></label>
        {source === 'palette' && <div className="color-swatches" role="group" aria-label={`${name} Palettenfarbe`}>{palette?.preview.map((color, index) => <button type="button" key={index} aria-label={`${name} Palettenfarbe ${index + 1}`} aria-pressed={setting.palette_index === index} style={{background: color}} onClick={() => update({...setting, palette_index: index})}>{setting.palette_index === index ? '✓' : ''}</button>)}</div>}
        {source === 'color' && <label className="color-label">Eigene Farbe<input aria-label={`${name} eigene Farbe`} type="color" value={xyToHex(setting.xy)} onChange={event => update({...setting, xy: rgbToXy(event.target.value)})}/></label>}
        {source === 'white' && <label className="slider">Weißton: {setting.color_temp_kelvin} K<input aria-label={`${name} Weißton`} type="range" min={light.min_color_temp_kelvin || 2000} max={light.max_color_temp_kelvin || 6500} step="50" value={setting.color_temp_kelvin || 2700} onChange={event => update({...setting, color_temp_kelvin: Number(event.target.value)})}/></label>}
      </>}
      {setting.mode === 'moon' && <div className="moon-settings"><p>☾ Mond heute: {moon} %</p><small>{setting.brightness == null ? 'Mondphase bestimmt die Helligkeit zwischen diesen beiden Werten.' : 'Feste Helligkeit überschreibt Mondhelligkeit und Atmen. Die Farbe folgt weiter der Mondphase.'}</small>
        <label className="slider">Bei Neumond: {percent(moonSettings.new_brightness)} %<input aria-label={`${name} Helligkeit bei Neumond`} type="range" min="1" max="100" value={percent(moonSettings.new_brightness)} onChange={event => setMoon({new_brightness: brightnessValue(Number(event.target.value))})}/></label>
        <label className="slider">Bei Vollmond: {percent(moonSettings.full_brightness)} %<input aria-label={`${name} Helligkeit bei Vollmond`} type="range" min="1" max="100" value={percent(moonSettings.full_brightness)} onChange={event => setMoon({full_brightness: brightnessValue(Number(event.target.value))})}/></label>
        <div className="color-fields"><label>Neumond<input aria-label={`${name} Farbe bei Neumond`} type="color" value={xyToHex(moonSettings.new_xy)} onChange={event => setMoon({new_xy: rgbToXy(event.target.value)})}/></label><label>Vollmond<input aria-label={`${name} Farbe bei Vollmond`} type="color" value={xyToHex(moonSettings.full_xy)} onChange={event => setMoon({full_xy: rgbToXy(event.target.value)})}/></label></div>
        <label className="check"><input aria-label={`${name} bei Vollmond langsam atmen`} type="checkbox" checked={moonSettings.breath} onChange={event => setMoon({breath: event.target.checked})}/>Bei Vollmond langsam atmen</label>
      </div>}
    </>}
  </fieldset>;
}
export function SceneEditor({hass, room, palettes, scene, palette, onClose, onSaved, registerGuard}: {hass: Hass; room: Room; palettes: Palette[]; scene?: Scene; palette?: Palette; onClose: () => void; onSaved: (scene?: Scene, notice?: string) => void; registerGuard?: GuardRegistration}) {
  const [draft, setDraft] = useState<Partial<Scene>>(() => scene ? normalizeScene(scene, room) : {name: palette?.name || '', area_id: room.area_id, kind: palette ? 'palette' : 'snapshot', ...(palette ? {palette_id: palette.id, brightness: palette.bri} : {lights: snapshotLights(room)}), dynamic: {enabled: false, interval: tempos[palette?.tempo || 'slow'].interval, transition: tempos[palette?.tempo || 'slow'].transition, tempo: palette?.tempo || 'slow'}, favorite: false, order: 0, lamp_settings: {}});
  const [changed, setChanged] = useState(false);
  const operation = useRef(false), mounted = useRef(false);
  useEffect(() => {mounted.current = true; return () => {mounted.current = false;};}, []);
  const document = useMemo(() => ({scene: {...draft, name: draft.name?.trim() || 'Neue Szene'}}), [draft]);
  const live = useLivePreview(hass, room.area_id, document, changed, registerGuard);
  const captureUsed = useRef(false);
  useEffect(() => {
    if (!scene && !palette && live.capturedLights && !captureUsed.current) {
      captureUsed.current = true; setDraft(current => ({...current, lights: live.capturedLights}));
    }
  }, [scene, palette, live.capturedLights]);
  const selectedPalette = palettes.find(item => item.id === draft.palette_id) || (palette?.id === draft.palette_id ? palette : undefined);
  const targets = room.lights.filter(light => light.allowed);
  function updateLamp(light: Light, value: LampSetting) {
    const patch: Partial<Scene> = {lamp_settings: {...draft.lamp_settings, [light.entity_id]: value}};
    if (draft.kind === 'snapshot') {
      const current = draft.lights?.[light.entity_id] || snapshotLights({...room, lights: [light]})[light.entity_id] || {on: true};
      patch.lights = {...draft.lights, [light.entity_id]: value.mode === 'off' ? {on: false} : {...current, on: true}};
    }
    update(patch);
  }
  const brightness = draft.brightness || 128;
  const dynamic = draft.dynamic || {enabled: false, interval: 90, transition: 40, tempo: 'slow' as Tempo};
  const settings = draft.lamp_settings || {};
  const cycleTargets = targets.filter(light => dimmable(light) && (!settings[light.entity_id] || settings[light.entity_id].mode === 'cycle'));
  const order = [...(draft.wave_order || []).filter(id => cycleTargets.some(light => light.entity_id === id)), ...cycleTargets.map(light => light.entity_id).filter(id => !draft.wave_order?.includes(id))];
  const disabled = !live.ready || live.closing;
  const invalid = !draft.name?.trim() || (draft.kind === 'palette' && !selectedPalette) || dynamic.interval < 5 || dynamic.interval > 3600 || dynamic.transition < 0 || dynamic.transition > Math.min(dynamic.interval, 60);
  function update(patch: Partial<Scene>) {setDraft(current => ({...current, ...patch})); setChanged(true);}
  function updateDynamic(patch: Partial<NonNullable<Scene['dynamic']>>) {update({dynamic: {...dynamic, ...patch}});}
  async function cancel() {if (await live.cancel() && mounted.current) onClose();}
  async function save() {
    if (operation.current || invalid || disabled) return;
    operation.current = true;
    const result = await live.commit({scene: {...draft, name: draft.name!.trim()}});
    operation.current = false;
    if (result && mounted.current) onSaved(result.scene, [...(result.notes || []), ...(result.skipped?.length ? [`${result.skipped.length} Lampe(n) wurden übersprungen.`] : [])].join(' '));
  }
  return <section className="scene-editor" data-testid="scene-editor" aria-label="Szenen-Editor">
    <div className="section-heading"><h2>{scene ? 'Szene bearbeiten' : 'Neue Szene'}</h2><button onClick={() => void cancel()} disabled={live.closing && live.busy}>Abbrechen</button></div>
    <p className="editor-context">{displayName(room.name)} · Änderungen wirken live. Abbrechen stellt vorheriges Licht wieder her.</p>
    {live.error && <p className="error" role="alert">{displayError(live.error)}</p>}
    {!live.ready && !live.error && <p role="status">Vorherigen Zustand sichern …</p>}
    {live.message && <p className="preview-status" role="status">{live.message}</p>}
    <fieldset disabled={disabled}><label>Szenenname<input className="text-input" value={draft.name || ''} maxLength={100} onChange={event => update({name: event.target.value})}/></label>
      <label>Grundlage<select className="text-input" value={draft.kind} onChange={event => update(event.target.value === 'palette' ? {kind: 'palette', palette_id: selectedPalette?.id || palettes[0]?.id} : {kind: 'snapshot', lights: draft.lights || live.capturedLights || snapshotLights(room), dynamic: {...dynamic, enabled: false, welle: false}, wave_order: [], lamp_settings: Object.fromEntries(Object.entries(settings).map(([id, value]) => [id, value.palette_index !== undefined ? {mode: value.mode, brightness: value.brightness, xy: selectedPalette?.colors[value.palette_index] ? [selectedPalette.colors[value.palette_index].x, selectedPalette.colors[value.palette_index].y] : [.45, .41]} : value]))})}><option value="palette" disabled={!palettes.length}>Farbpalette</option><option value="snapshot">Momentaufnahme</option></select></label>
      {draft.kind === 'palette' && <><label>Palette<select className="text-input" value={draft.palette_id || ''} onChange={event => {const item = palettes.find(p => p.id === event.target.value); update({palette_id: event.target.value, lamp_settings: Object.fromEntries(Object.entries(settings).map(([id, value]) => [id, value.palette_index !== undefined && item ? {...value, palette_index: Math.min(value.palette_index, item.colors.length - 1)} : value])), ...(item ? {brightness: item.bri, dynamic: {...dynamic, interval: tempos[item.tempo || 'slow'].interval, transition: tempos[item.tempo || 'slow'].transition, tempo: item.tempo || 'slow'}} : {})});}}><option value="" disabled>Palette wählen</option>{palettes.map(item => <option key={item.id} value={item.id}>{displayName(item.name)}</option>)}</select></label>{selectedPalette && <div className="scene-strip editor-gradient" style={{background: `linear-gradient(100deg, ${selectedPalette.preview.join(',')})`}}/>}</>}
      {targets.some(dimmable) && <label className="slider">Gesamthelligkeit: {draft.kind === 'snapshot' && draft.brightness == null ? 'gespeicherte Werte' : `${percent(brightness)} %`}<input aria-label="Gesamthelligkeit" type="range" min="1" max="100" value={percent(brightness)} onChange={event => update({brightness: brightnessValue(Number(event.target.value))})}/><small>Feste Lampenwerte bleiben unverändert.</small></label>}
      {draft.kind === 'palette' && <label className="check"><input type="checkbox" checked={dynamic.enabled} onChange={event => updateDynamic({enabled: event.target.checked, ...(!event.target.checked ? {welle: false} : {})})}/>Dynamischer Farbwechsel</label>}
      {dynamic.enabled && <><label>Tempo<select className="text-input" value={dynamic.tempo || ''} onChange={event => {const tempo = event.target.value as Tempo; updateDynamic({tempo, interval: tempos[tempo].interval, transition: tempos[tempo].transition});}}>{!dynamic.tempo && <option value="">Eigene Sekunden</option>}{Object.entries(tempos).map(([value, item]) => <option key={value} value={value}>{item.label}</option>)}</select></label>
        <label className="check"><input type="checkbox" checked={!!dynamic.gentle} onChange={event => updateDynamic({gentle: event.target.checked})}/>Sanft lebendig</label><small>Farbwechsel-Lampen werden langsam bis zu 10 % heller und dunkler.</small>
        <label className="check"><input type="checkbox" checked={!!dynamic.welle} onChange={event => update({dynamic: {...dynamic, welle: event.target.checked}, ...(event.target.checked ? {wave_order: order, verteilung: draft.verteilung === 'zufall' || !draft.verteilung ? 'verlauf_links_rechts' : draft.verteilung} : {})})}/>Welle</label>
        {dynamic.welle && <section className="wave-settings" aria-label="Reihenfolge der Welle"><p>Welle läuft von {displayName(targets.find(light => light.entity_id === order[0])?.name || '…')} nach {displayName(targets.find(light => light.entity_id === order.at(-1))?.name || '…')}.</p><ol className="wave-list">{order.map((id, index) => <li key={id}><span>{displayName(targets.find(light => light.entity_id === id)?.name || 'Lampe')}</span><button type="button" aria-label={`${displayName(targets.find(light => light.entity_id === id)?.name || 'Lampe')} in Welle nach oben`} disabled={index === 0} onClick={() => {const next = [...order]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; update({wave_order: next});}}>↑</button><button type="button" aria-label={`${displayName(targets.find(light => light.entity_id === id)?.name || 'Lampe')} in Welle nach unten`} disabled={index === order.length - 1} onClick={() => {const next = [...order]; [next[index + 1], next[index]] = [next[index], next[index + 1]]; update({wave_order: next});}}>↓</button></li>)}</ol></section>}
      </>}
      <details><summary>Mehr Optionen</summary><label>Farbwechsel alle (Sekunden)<input className="text-input" type="number" min="5" max="3600" value={dynamic.interval} onChange={event => updateDynamic({interval: Number(event.target.value), tempo: undefined})}/></label><label>Übergangszeit (Sekunden)<input className="text-input" type="number" min="0" max={Math.min(dynamic.interval, 60)} value={dynamic.transition} onChange={event => updateDynamic({transition: Number(event.target.value), tempo: undefined})}/></label>
        <label>Farbverteilung<select className="text-input" value={draft.verteilung || 'zufall'} onChange={event => update({verteilung: event.target.value as Scene['verteilung']})}><option value="zufall" disabled={!!dynamic.welle}>Zufällig</option><option value="verlauf_links_rechts">Links nach rechts</option><option value="verlauf_vorne_hinten">Vorne nach hinten</option><option value="hoehe">Nach Höhe</option></select></label><small>Das Positionsraster bleibt auf der Raumseite unter „Mehr Optionen“.</small>
        <label className="check"><input type="checkbox" checked={!!draft.favorite} onChange={event => update({favorite: event.target.checked})}/>Lieblingsszene</label><label className="check"><input type="checkbox" checked={!!draft.night} onChange={event => update({night: event.target.checked})}/>Nachtlicht</label>
      </details>
    </fieldset>
    <h3>Lampen</h3>{targets.map(light => <LampSceneRow key={light.entity_id} light={light} unchanged={draft.kind === 'palette' && light.entity_id.startsWith('switch.') && !settings[light.entity_id]} setting={settings[light.entity_id] || {mode: draft.kind === 'snapshot' && draft.lights?.[light.entity_id]?.on === false ? 'off' : 'cycle', brightness: null}} palette={draft.kind === 'palette' ? selectedPalette : undefined} sceneBrightness={brightness} moon={live.moon ?? moonIllumination()} disabled={disabled} update={value => updateLamp(light, value)}/>)}
    {!targets.length && <p>Keine freigegebenen Lampen in diesem Ziel.</p>}
    <div className="editor-footer"><button className="primary" disabled={disabled || invalid || !targets.length} onClick={() => void save()}>{live.closing && live.busy ? 'Bitte warten …' : 'Szene speichern'}</button></div>
  </section>;
}
