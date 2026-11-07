// Geändert für Lichtzentrale
import {useCallback, useEffect, useRef, useState} from 'react';
import {RoomPalette} from './RoomPalette';
import {Rooms} from './Rooms';
import type {ApplyResult, Distribution, Hass, Light, Palette} from './types';

const tabs = ['Räume', 'Raum', 'Galerie', 'Taster', 'Zeitpläne'] as const;
type Tab = typeof tabs[number];
const later: Record<Exclude<Tab, 'Galerie' | 'Räume' | 'Raum'>, string> = {
  Taster: 'Tasterbelegungen folgen in Stufe 3.', Zeitpläne: 'Zeitpläne folgen in Stufe 4.',
};
const errorText = (error: unknown) => error instanceof Error ? error.message : typeof error === 'object' && error !== null && 'message' in error ? String(error.message) : 'Die Anfrage konnte nicht abgeschlossen werden.';
export function App({hass, onMenu}: {hass: Hass; onMenu?: () => void}) {
  const api = useRef(hass);
  api.current = hass;
  const alive = useRef(false);
  const lock = useRef(false);
  const loadId = useRef(0);
  const preserveGrants = useRef(false);
  const [showHidden, setShowHidden] = useState(false);
  const application = useRef<HTMLElement>(null);
  const [tab, setTab] = useState<Tab>('Räume');
  const [roomName, setRoomName] = useState('');
  const [roomArea, setRoomArea] = useState('');
  const [palettes, setPalettes] = useState<Palette[]>([]);
  const [lights, setLights] = useState<Light[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [settings, setSettings] = useState(false);
  const [grants, setGrants] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [palette, setPalette] = useState<Palette | null>(null);
  const [brightness, setBrightness] = useState(128);
  const [transition, setTransition] = useState(2);
  const [distribution, setDistribution] = useState<Distribution>('zufall');
  const load = useCallback(async () => {
    const id = ++loadId.current; const keepGrants = preserveGrants.current; preserveGrants.current = false; setLoading(true); setError('');
    try {
      const [nextPalettes, nextLights] = await Promise.all([
        api.current.callWS<Palette[]>({type: 'lichtzentrale/palettes/list'}),
        api.current.callWS<Light[]>({type: 'lichtzentrale/lights/list', include_hidden: showHidden}),
      ]);
      if (!alive.current || id !== loadId.current) return;
      setPalettes(nextPalettes); setLights(nextLights);
      if (!keepGrants) setGrants(nextLights.filter(light => light.allowed).map(light => light.entity_id));
      setSelected(current => current.filter(id => nextLights.some(light => light.entity_id === id && light.allowed && light.available)));
    } catch (error) { if (alive.current && id === loadId.current) setError(`Laden fehlgeschlagen: ${errorText(error)}`); }
    finally { if (alive.current && id === loadId.current) setLoading(false); }
  }, [showHidden]);
  useEffect(() => { const counter = loadId; alive.current = true; void load(); return () => { alive.current = false; counter.current++; }; }, [load]);
  useEffect(() => {
    if (palette) {
      application.current?.scrollIntoView?.({block: 'start'});
      application.current?.focus({preventScroll: true});
    }
  }, [palette]);
  const toggle = (values: string[], id: string) => values.includes(id) ? values.filter(value => value !== id) : [...values, id];
  async function saveGrants() {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError(''); setMessage('');
    try {
      await api.current.callWS({type: 'lichtzentrale/settings/save', light_entity_ids: grants});
      if (!alive.current) return;
      setSettings(false); setMessage('Lampenfreigaben wurden in Home Assistant gespeichert.');
      await load();
    } catch (error) { if (alive.current) setError(`Speichern fehlgeschlagen: ${errorText(error)}`); }
    finally { lock.current = false; if (alive.current) setBusy(false); }
  }
  async function apply() {
    if (lock.current || !palette || !selected.length) return;
    lock.current = true; setBusy(true); setError(''); setMessage('');
    try {
      const result = await api.current.callWS<ApplyResult>({type: 'lichtzentrale/palette/apply', palette_id: palette.id, entity_ids: selected, brightness, transition, verteilung: distribution});
      if (!alive.current) return;
      setMessage(`${result.applied.length} Lampe(n) angewendet. ${result.skipped.length} Lampe(n) übersprungen. ${result.failed?.length || 0} Lampe(n) fehlgeschlagen.${result.skipped.length || result.failed?.length ? ' Nicht alle Lampen konnten geändert werden. Verfügbarkeit und Freigaben prüfen.' : ''}`);
    } catch (error) { if (alive.current) setError(`Anwenden fehlgeschlagen: ${errorText(error)} Einzelne Lampen könnten bereits geändert worden sein. Prüfe ihren Zustand vor einem erneuten Versuch.`); }
    finally { lock.current = false; if (alive.current) setBusy(false); }
  }
  const allowed = lights.filter(light => light.allowed);
  const disabled = busy || loading;
  return <div className="app">
    <header><button className="menu" aria-label="Seitenleiste öffnen" onClick={onMenu}>☰</button><div><h1>{tab === 'Raum' && roomName ? roomName : 'Lichtzentrale'}</h1><p>Dein Licht. Deine Farben.</p></div><span className="stage">Stufe 2b</span></header>
    <main>
      {error && <div role="alert" className="error">{error}</div>}
      {message && <div role="status" className="notice">{message}</div>}
      {(tab === 'Räume' || tab === 'Raum') && <><Rooms hass={hass} detail={tab === 'Raum'} openRoom={() => setTab('Raum')} initialArea={roomArea} onRoomChange={(name, area) => {setRoomName(name); setRoomArea(area);}}/><button onClick={() => {setTab('Galerie'); setSettings(true);}}>Lampen freigeben</button></>}
      {tab === 'Taster' || tab === 'Zeitpläne' ? <section className="empty"><h2>{tab}</h2><p>{later[tab]}</p><button onClick={() => setTab('Galerie')}>Zur Galerie</button></section> : tab === 'Galerie' ? <>
        <div className="section-heading"><div><h2>Galerie</h2><p>Eigene Farbpaletten, direkt aus ihren Farben.</p></div><button disabled={disabled} onClick={() => { setGrants(lights.filter(light => light.allowed).map(light => light.entity_id)); setSettings(!settings); }}>Lampen freigeben</button></div>
        {loading && <p role="status">Lampen und Paletten werden geladen …</p>}
        <button className="refresh" disabled={disabled} onClick={() => { setSettings(false); void load(); }}>Neu laden</button>
        {settings && <section className="card"><h3>Lampen freigeben</h3><p>Nur bewusst freigegebene Einzellampen sind steuerbar. Drucker-, Geräte- und andere Funktionsbeleuchtung nicht auswählen. Gruppen werden nicht angeboten.</p>
          {!lights.length && <p>Keine Einzellampen gefunden.</p>}
          <label className="check"><input type="checkbox" checked={showHidden} disabled={disabled} onChange={event => {preserveGrants.current = true; setShowHidden(event.target.checked);}}/>Ausgeblendete Druckerbeleuchtung anzeigen</label><fieldset disabled={disabled}><legend>Erlaubte Einzellampen und Lichtschalter</legend>{lights.map(light => <label className="check" key={light.entity_id}><input type="checkbox" checked={grants.includes(light.entity_id)} onChange={() => setGrants(toggle(grants, light.entity_id))}/><span>{light.name}<small>{light.area_name || 'Ohne Bereich'}{!light.available ? ' · Nicht verfügbar' : ''}</small></span></label>)}</fieldset>
          <button disabled={disabled} onClick={() => void saveGrants()}>Freigaben speichern</button><button className="secondary" disabled={disabled} onClick={() => setSettings(false)}>Abbrechen</button>
        </section>}
        {!loading && !allowed.length && <p className="notice">Noch keine Lampen freigegeben. Wähle zuerst unter „Lampen freigeben“ die gewünschten Einzellampen aus.</p>}
        {!loading && !palettes.length && <p>Keine Paletten verfügbar. Lade die Daten erneut.</p>}
        {[...new Set(palettes.map(item => item.category))].map(category => <section key={category}><h3>{category}</h3><div className="grid">{palettes.filter(item => item.category === category).map(item => <button className="palette" disabled={disabled} key={item.id} aria-pressed={palette?.id === item.id} onClick={() => { setPalette(item); setBrightness(item.bri); setMessage(''); }}><span className="gradient" style={{background: `linear-gradient(120deg, ${item.preview.join(', ')})`}}/><span className="palette-name">{item.name}</span></button>)}</div></section>)}
        {palette && <section ref={application} tabIndex={-1}><RoomPalette key={palette.id} hass={hass} palette={palette}/></section>}
        {palette && <section className="card" aria-label="Palette anwenden"><h3>{palette.name} anwenden</h3><p>Wähle freigegebene Lampen. Farblose Lampen erhalten nur die Helligkeit, reine Ein/Aus-Lampen werden eingeschaltet.</p>
          <fieldset disabled={disabled}><legend>Lampen auswählen</legend>{allowed.length === 0 && <p>Bitte zuerst Lampen freigeben.</p>}{allowed.map(light => <label className="check" key={light.entity_id}><input type="checkbox" disabled={!light.available} checked={selected.includes(light.entity_id)} onChange={() => setSelected(toggle(selected, light.entity_id))}/><span>{light.name}<small>{light.area_name || 'Ohne Bereich'}{!light.available ? ' · Nicht verfügbar' : ''}</small></span></label>)}
          <label>Farbverteilung für einzelne Lampen<select className="text-input" value={distribution} onChange={event => setDistribution(event.target.value as Distribution)}><option value="zufall">Zufällig</option><option value="verlauf_links_rechts">Verlauf von links nach rechts</option><option value="verlauf_vorne_hinten">Verlauf von vorne nach hinten</option><option value="hoehe">Nach Höhe: unten nach oben</option></select></label><p>Die Positionen stammen aus den jeweiligen Räumen. Lampen ohne Position kommen zuletzt. Bei Höhe erhält Hintergrund die kräftigste Farbe.</p>
          <label className="slider">Helligkeit: {Math.round(brightness / 255 * 100)} %<input aria-label="Helligkeit" type="range" min="1" max="255" value={brightness} onChange={event => setBrightness(Number(event.target.value))}/></label>
          <label className="slider">Übergang: {transition} Sekunden<input aria-label="Übergang" type="range" min="0" max="60" value={transition} onChange={event => setTransition(Number(event.target.value))}/></label></fieldset>
          <button disabled={disabled || !selected.length} onClick={() => void apply()}>{busy ? 'Bitte warten …' : `Auf ${selected.length} Lampe(n) anwenden`}</button>
        </section>}
      </> : null}
    </main>
    <nav aria-label="Hauptnavigation">{tabs.map(name => <button key={name} aria-current={tab === name ? 'page' : undefined} onClick={() => setTab(name)}>{name}</button>)}</nav>
  </div>;
}
