// Geändert für Lichtzentrale
import {useEffect, useRef, useState} from 'react';
import {RuntimeControls} from './RuntimeControls';
import type {ApplyResult, Distribution, Hass, Palette, Room, Scene} from './types';
export function RoomPalette({hass, palette}: {hass: Hass; palette: Palette}) {
  const api = useRef(hass); api.current = hass;
  const generation = useRef(0), lock = useRef(false);
  const [rooms, setRooms] = useState<Room[]>([]), [area, setArea] = useState('');
  const [save, setSave] = useState(false), [dynamic, setDynamic] = useState(false), [name, setName] = useState(palette.name);
  const [brightness, setBrightness] = useState(palette.bri), [interval, setInterval] = useState(60), [transition, setTransition] = useState(10);
  const [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [error, setError] = useState(''), [message, setMessage] = useState(''), [revision, setRevision] = useState(0);
  const [distribution, setDistribution] = useState<Distribution>('zufall'), [wave, setWave] = useState(false);
  const saved = useRef<{signature: string; scene: Scene} | null>(null);
  useEffect(() => {
    const counter = generation; const id = ++counter.current;
    api.current.callWS<Room[]>({type: 'lichtzentrale/rooms/list'}).then(value => {if (id === generation.current) setRooms(Array.isArray(value) ? value : []);}).catch(() => {if (id === generation.current) setError('Räume konnten nicht geladen werden. Wähle die Palette erneut.');}).finally(() => {if (id === generation.current) setLoading(false);});
    return () => {counter.current++;};
  }, []);
  const room = rooms.find(item => item.area_id === area), disabled = loading || busy;
  async function apply() {
    if (lock.current || !room) return;
    lock.current = true; const id = generation.current; setBusy(true); setError(''); setMessage('');
    let stored = false;
    try {
      let result: ApplyResult;
      if (save || dynamic) {
        const data = {name: name.trim(), area_id: area, kind: 'palette', palette_id: palette.id, brightness, verteilung: distribution, dynamic: {enabled: dynamic, interval, transition, welle: dynamic && wave}};
        const signature = JSON.stringify(data);
        let scene = saved.current?.signature === signature ? saved.current.scene : null;
        if (!scene) {
          scene = await api.current.callWS<Scene>({type: 'lichtzentrale/scene/save', scene: data});
          if (id !== generation.current) return;
          saved.current = {signature, scene};
        }
        stored = true;
        result = await api.current.callWS<ApplyResult>({type: 'lichtzentrale/scene/apply', scene_id: scene.id});
      } else {
        result = await api.current.callWS<ApplyResult>({type: 'lichtzentrale/palette/apply', palette_id: palette.id, entity_ids: room.lights.filter(light => light.allowed).map(light => light.entity_id), brightness, transition, verteilung: distribution});
      }
      if (id !== generation.current) return;
      setMessage(`${stored ? 'Szene gespeichert. ' : ''}${result.applied.length} Lampe(n) angewendet. ${result.skipped.length} übersprungen. ${result.failed?.length || 0} fehlgeschlagen.`); setRevision(value => value + 1);
    } catch (e) {
      if (id === generation.current) setError(`${stored ? 'Die Szene ist gespeichert. ' : ''}Anwenden fehlgeschlagen: ${e instanceof Error ? e.message : 'Bitte Zustand prüfen.'} Einzelne Lampen könnten bereits geändert worden sein.`);
    } finally {lock.current = false; if (id === generation.current) setBusy(false);}
  }
  return <section className="card" aria-label="Palette im Raum anwenden"><h3>Im Raum anwenden</h3>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    {loading && <p role="status">Räume werden geladen …</p>}
    <fieldset disabled={disabled}><legend>Raum und Szeneneinstellungen</legend><label>Zielraum<select className="text-input" value={area} onChange={event => {setArea(event.target.value); setMessage(''); setError('');}}><option value="">Bitte Raum wählen</option>{rooms.map(item => <option key={item.area_id} value={item.area_id} disabled={!item.available_count}>{item.name}</option>)}</select></label>
      {area && <><label className="slider">Helligkeit im Raum: {Math.round(brightness / 255 * 100)} %<input aria-label="Helligkeit im Raum" type="range" min="1" max="255" value={brightness} onChange={event => setBrightness(Number(event.target.value))}/></label>
      <label>Farbverteilung<select className="text-input" value={distribution} onChange={event => setDistribution(event.target.value as Distribution)}><option value="zufall" disabled={dynamic && wave}>Zufällig</option><option value="verlauf_links_rechts">Verlauf von links nach rechts</option><option value="verlauf_vorne_hinten">Verlauf von vorne nach hinten</option><option value="hoehe">Nach Höhe: unten nach oben</option></select></label>
      <p>Lampen ohne Position kommen zuletzt. Bei Höhe erhält Hintergrund die kräftigste Farbe.</p>
      <label className="check"><input type="checkbox" checked={save || dynamic} disabled={dynamic} onChange={event => setSave(event.target.checked)}/>Als Szene im Raum speichern</label>
      <label className="check"><input type="checkbox" checked={dynamic} onChange={event => {setDynamic(event.target.checked); if (!event.target.checked) setWave(false);}}/>Dynamischer Farbwechsel</label>
      {dynamic && <><label className="check"><input type="checkbox" checked={wave} onChange={event => {setWave(event.target.checked); if (event.target.checked && distribution === 'zufall') setDistribution('verlauf_links_rechts');}}/>Welle durch den Raum</label><p>Die Palette wandert schrittweise entlang der gewählten Farbverteilung. Ohne gewählte Achse startet die Welle von links nach rechts.</p></>}
      {dynamic && <p>Dynamische Paletten werden als Szene gespeichert. Pro Raum läuft eine dynamische Szene.</p>}
      {(save || dynamic) && <label>Name der Palettenszene<input className="text-input" maxLength={100} value={name} onChange={event => setName(event.target.value)}/></label>}
      {dynamic && <label>Farbwechsel alle (Sekunden)<input className="text-input" type="number" min="5" max="3600" value={interval} onChange={event => setInterval(Number(event.target.value))}/></label>}
      <label>Übergangszeit (Sekunden)<input className="text-input" type="number" min="0" max={dynamic ? Math.min(interval, 60) : 60} value={transition} onChange={event => setTransition(Number(event.target.value))}/></label>
    </>} </fieldset><button disabled={disabled || !room || !room.available_count || ((save || dynamic) && !name.trim()) || (dynamic && (interval < 5 || interval > 3600)) || transition < 0 || transition > (dynamic ? Math.min(interval, 60) : 60)} onClick={() => void apply()}>{busy ? 'Bitte warten …' : save || dynamic ? 'Szene speichern und anwenden' : 'Im gewählten Raum anwenden'}</button>
    {area && <RuntimeControls key={area} hass={hass} area={area} revision={revision}/>}
  </section>;
}
