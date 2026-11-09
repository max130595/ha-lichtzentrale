// Geändert für Lichtzentrale
import {BoundaryEditor} from './BasicBrightnessControls';
import {displayName} from './display';
import type {BindingTimeWindow, MotionBoundary, Scene} from './types';

const integer = (value: number, min: number, max: number) => Number.isInteger(value) && value >= min && value <= max;
const boundaryValid = (value: MotionBoundary | null) => value === null || (value.type === 'time'
  ? /^([01]\d|2[0-3]):[0-5]\d$/.test(value.value)
  : ['sunrise', 'sunset'].includes(value.event) && integer(value.offset_min, -1440, 1440));
export const newBindingTimeWindow = (): BindingTimeWindow => ({
  window: {after: {type: 'time', value: '07:00'}, before: {type: 'time', value: '22:00'}},
  mode: 'brightness', brightness: 255, color_temp_kelvin: 4000,
});
export const bindingTimeWindowsValid = (windows: BindingTimeWindow[], scenes: Scene[]) => windows.length >= 1 && windows.length <= 24 && windows.every(item =>
  boundaryValid(item.window.after) && boundaryValid(item.window.before) && (item.mode === 'scene'
    ? scenes.some(scene => scene.id === item.scene_id)
    : integer(item.brightness, 1, 255) && (item.color_temp_kelvin === undefined || integer(item.color_temp_kelvin, 1000, 40000))));

export function BindingTimeWindows({windows, scenes, change, selectedTargets = false}: {
  windows: BindingTimeWindow[]; scenes: Scene[]; change: (windows: BindingTimeWindow[]) => void; selectedTargets?: boolean;
}) {
  function replace(index: number, value: BindingTimeWindow) {change(windows.map((item, i) => i === index ? value : item));}
  function move(index: number, direction: number) {
    const next = [...windows];
    [next[index], next[index + direction]] = [next[index + direction], next[index]];
    change(next);
  }
  return <section aria-label="Einschalten nach Tageszeit">
    <p>Das erste passende Zeitfenster in dieser Reihenfolge gilt. Passt kein Fenster, gilt der letzte Zustand wie bisher.</p>
    <p>Lokale Home-Assistant-Zeit. Beginn inklusive, Ende exklusive. Über Mitternacht möglich; gleiche Grenzen gelten ganztägig. Sonnenzeiten werden lokal berechnet.</p>
    <p>Diese Regeln gelten nur beim Einschalten, nicht als laufender Zeitplan. Reine Lichtschalter erhalten nur An/Aus, nie Helligkeit oder Weißton.</p>
    {windows.map((item, index) => <fieldset key={index}><legend>Einschaltfenster {index + 1}</legend>
      <BoundaryEditor label={`Einschaltfenster ${index + 1} Beginn`} value={item.window.after} change={after => replace(index, {...item, window: {...item.window, after}})}/>
      <BoundaryEditor label={`Einschaltfenster ${index + 1} Ende`} value={item.window.before} change={before => replace(index, {...item, window: {...item.window, before}})}/>
      <label>Einschaltfenster {index + 1} Aktion<select className="text-input" value={item.mode} onChange={event => replace(index, event.target.value === 'scene' ? {window: item.window, mode: 'scene', scene_id: ''} : {...newBindingTimeWindow(), window: item.window})}>
        <option value="brightness">Helligkeit und Weißton</option><option value="scene">Eine Szene</option>
      </select></label>
      {item.mode === 'brightness' ? <>
        <label>Einschaltfenster {index + 1} Helligkeit: {Math.max(1, Math.round(item.brightness * 100 / 255))} %<input aria-label={`Einschaltfenster ${index + 1} Helligkeit`} type="range" min={1} max={100} step={1} value={Math.max(1, Math.round(item.brightness * 100 / 255))} onChange={event => replace(index, {...item, brightness: Math.round(Number(event.target.value) * 255 / 100)})}/></label>
        <label className="check"><input type="checkbox" checked={item.color_temp_kelvin !== undefined} onChange={event => {if (event.target.checked) replace(index, {...item, color_temp_kelvin: 2700}); else replace(index, {window: item.window, mode: 'brightness', brightness: item.brightness});}}/>Einschaltfenster {index + 1} Weißton festlegen</label>
        {item.color_temp_kelvin !== undefined && <label>Einschaltfenster {index + 1} Weißton in Kelvin<input className="text-input" type="number" min={1000} max={40000} step={1} value={Number.isNaN(item.color_temp_kelvin) ? '' : item.color_temp_kelvin} onChange={event => replace(index, {...item, color_temp_kelvin: event.target.value === '' ? NaN : Number(event.target.value)})}/></label>}
        <small>Niedrige Kelvinwerte sind wärmer. Der Weißton wird an die Fähigkeiten jeder Lampe angepasst.</small>
      </> : <>
        <label>Einschaltfenster {index + 1} Szene<select className="text-input" value={item.scene_id} onChange={event => replace(index, {...item, scene_id: event.target.value})}>
          <option value="">Passende Szene wählen</option>{item.scene_id && !scenes.some(scene => scene.id === item.scene_id) && <option value={item.scene_id}>Szene nicht mehr passend oder vorhanden</option>}{scenes.map(scene => <option key={scene.id} value={scene.id}>{displayName(scene.name, 'Gespeicherte Szene')}</option>)}
        </select></label>
        {!scenes.some(scene => scene.id === item.scene_id) && <p>Bitte eine passende Szene wählen.</p>}
        {selectedTargets && <p>Nur die ausgewählten Lampen übernehmen die Szene. Andere Lampen bleiben unverändert.</p>}
      </>}
      <div className="actions"><button type="button" disabled={index === 0} onClick={() => move(index, -1)}>Einschaltfenster {index + 1} nach oben</button><button type="button" disabled={index === windows.length - 1} onClick={() => move(index, 1)}>Einschaltfenster {index + 1} nach unten</button><button type="button" onClick={() => change(windows.filter((_, i) => i !== index))}>Einschaltfenster {index + 1} entfernen</button></div>
    </fieldset>)}
    <button type="button" disabled={windows.length >= 24} onClick={() => {if (windows.length < 24) change([...windows, newBindingTimeWindow()]);}}>Einschaltfenster hinzufügen</button>
    {!bindingTimeWindowsValid(windows, scenes) && <p role="alert">Bitte 1–24 vollständige Zeitfenster mit gültigen Uhrzeiten, Versatzwerten, Weißtönen und passenden Szenen wählen.</p>}
  </section>;
}
