// Geändert für Lichtzentrale
// Synthetic WebSocket transport ONLY. UI, styles, and custom element are the production bundle.
// No live Home Assistant connections, accounts, device addresses, or user data.
(async () => {
  const clone = value => structuredClone(value);
  const palettes = await fetch('palettes.json').then(response => response.json());
  const autumn = palettes.find(item => item.id === 'herbstglut') || palettes[0];
  const lamps = [
    ['light.fixture_corner', 'Leseecke', 'fixture_living', 'Wohnzimmer', 46, ['xy', 'color_temp']],
    ['light.fixture_spot', 'Sofaspot', 'fixture_living', 'Wohnzimmer', 61, ['xy', 'color_temp']],
    ['light.fixture_shelf', 'Regallicht', 'fixture_living', 'Wohnzimmer', 140, ['xy', 'color_temp']],
    ['light.fixture_moon', 'Fensterlicht', 'fixture_corridor', 'Flur', 64, ['xy', 'color_temp']],
    ['light.fixture_ceiling', 'Deckenlicht', 'fixture_living', 'Wohnzimmer', null, ['onoff']],
    ['light.fixture_study', 'Schreibtisch', 'fixture_study', 'Arbeitszimmer', 160, ['color_temp']],
  ].map(([entity_id, name, area_id, area_name, brightness, supported_color_modes]) => ({entity_id, name, area_id, area_name, brightness, supported_color_modes, allowed: true, available: true, on: true, rgb_color: [255, 154, 46], color_mode: brightness === null ? 'onoff' : 'xy', color_temp_kelvin: 2700, min_color_temp_kelvin: 2000, max_color_temp_kelvin: 6500}));
  const replacement = {...lamps[0], entity_id: 'light.fixture_replacement', name: 'Neue Leuchte', allowed: true, color_mode: 'unknown', brightness: null};
  const custom = {...clone(autumn), id: 'fixture-custom', name: 'Holzlicht', category: 'Eigene', builtin: false};
  palettes.push(custom);
  const settings = {
    [lamps[0].entity_id]: {mode: 'cycle', brightness: 46},
    [lamps[1].entity_id]: {mode: 'cycle', brightness: 61},
    [lamps[2].entity_id]: {mode: 'fixed', brightness: 140, xy: [.612, .374]},
    [lamps[3].entity_id]: {mode: 'moon', brightness: null, moon: {new_brightness: 26, full_brightness: 204, new_xy: [.25, .27], full_xy: [.3127, .329], breath: true}},
    [lamps[4].entity_id]: {mode: 'off'},
  };
  let scenes = [
    {id: 'fixture-evening', name: 'Herbstabend', area_id: 'zone:fixture_evening', kind: 'palette', palette_id: autumn.id, brightness: 160, favorite: true, order: 0, preview: autumn.preview, lamp_settings: settings, wave_order: lamps.slice(0, 5).map(item => item.entity_id), dynamic: {enabled: true, interval: 90, transition: 40, tempo: 'slow', gentle: true, welle: true}, verteilung: 'verlauf_links_rechts'},
    {id: 'fixture-reading', name: 'Leselicht', area_id: 'fixture_living', kind: 'palette', palette_id: custom.id, brightness: 190, favorite: true, order: 0, preview: custom.preview, dynamic: {enabled: false, interval: 90, transition: 40, tempo: 'slow', welle: false}},
  ];
  let runs = [{scene_id: 'fixture-evening', area_id: 'zone:fixture_evening', name: 'Herbstabend', interval: 90, transition: 40}];
  const rooms = [
    {kind: 'zone', area_id: 'zone:fixture_evening', name: 'Abendzone', lights: lamps.slice(0, 5), last_scene_id: 'fixture-evening'},
    ...[['fixture_living', 'Wohnzimmer'], ['fixture_study', 'Arbeitszimmer'], ['fixture_corridor', 'Flur']].map(([area_id, name]) => ({kind: 'room', area_id, name, lights: lamps.filter(item => item.area_id === area_id), last_scene_id: area_id === 'fixture_living' ? 'fixture-reading' : null})),
  ].map(room => ({...room, on: true, brightness: 160, available_count: room.lights.length, cycle: [], default_on: 'last', positions: Object.fromEntries(room.lights.map((lamp, index) => [lamp.entity_id, {cell: [index % 3, Math.floor(index / 3)], height: index === 1 ? 'decke' : 'moebel'}]))}));
  let bindings = [{id: 'fixture-binding', event_entity: 'event.fixture_button', event_type: 'short_release', action: 'toggle_room', area_id: 'fixture_living', params: {on_behavior: {mode: 'brightness', brightness: 102}}}];
  let dimMinPct = 1;
  const requests = [], sessions = new Map();
  const result = area => ({applied: (rooms.find(item => item.area_id === area)?.lights || lamps).map(item => item.entity_id), skipped: [], failed: []});
  const saveScene = draft => {
    const scene = {...clone(draft), id: draft.id || `fixture-saved-${scenes.length}`, preview: palettes.find(item => item.id === draft.palette_id)?.preview || [], order: draft.order || 0};
    scenes = [...scenes.filter(item => item.id !== scene.id), scene];
    return scene;
  };
  const savePalette = draft => {
    const palette = {...clone(draft), id: draft.id || `fixture-palette-${palettes.length}`, builtin: false};
    const index = palettes.findIndex(item => item.id === palette.id);
    if (index >= 0) palettes[index] = palette; else palettes.push(palette);
    return palette;
  };
  const api = {
    async callWS(request) {
      requests.push(clone(request));
      await new Promise(resolve => setTimeout(resolve, 35));
      const type = request.type.replace('lichtzentrale/', '');
      if (type === 'settings/get') return {dim_min_pct: dimMinPct};
      if (type === 'settings/dimming') {
        if (!Number.isInteger(request.dim_min_pct) || request.dim_min_pct < 1 || request.dim_min_pct > 20) throw new Error('Ungültige Dimm-Untergrenze');
        dimMinPct = request.dim_min_pct; return {dim_min_pct: dimMinPct};
      }
      if (type === 'palettes/list') return clone(palettes);
      if (type === 'lights/list') return clone([...lamps, replacement]);
      if (type === 'rooms/list') return clone(rooms);
      if (type === 'scenes/list') return clone(scenes);
      if (type === 'dynamic/list') return clone(runs);
      if (type === 'adaptive/status') return {available: false, rooms: [], switches: []};
      if (type === 'hue_scenes/list') return [];
      if (type === 'buttons/list') return [{entity_id: 'event.fixture_button', name: 'Taste 1', device_id: 'fixture-device', device_name: 'Wohntaster', manufacturer: 'Fixture', model: 'Fixture button', area_id: 'fixture_living', event_types: ['short_release'], available: true}];
      if (type === 'bindings/list') return {bindings: clone(bindings), double_click_ms: 500};
      if (type === 'binding/save') {const saved = {...clone(request.binding), id: request.binding.id || 'fixture-binding-new'}; bindings = [...bindings.filter(item => item.id !== saved.id), saved]; return saved;}
      if (type === 'zones/list') return [{id: 'fixture_evening', name: 'Abendzone', entity_ids: lamps.slice(0, 5).map(item => item.entity_id)}];
      if (type === 'schedules/list') return {time_zone: 'Europe/Berlin', schedules: [], persons: [], lux_sensors: []};
      if (type === 'motion/get') return {config: null, status: {paused: false, active: false, enabled: false}, sensors: [], lux_sensors: []};
      if (type === 'brightness/get') return {config: null, status: {enabled: false, paused: false, current_lux: null, active_stage: 0, learned_lux: []}, lux_sensors: [], persons: []};
      if (type === 'preview/begin') {
        const preview_id = `fixture-preview-${sessions.size + 1}-${requests.length}`;
        sessions.set(preview_id, {area_id: request.area_id, sequence: -1});
        return {preview_id, area_id: request.area_id, expires_in: 120, moon_fraction: .37, lights: Object.fromEntries((rooms.find(room => room.area_id === request.area_id)?.lights || []).map(lamp => [lamp.entity_id, {on: lamp.on, ...(lamp.brightness ? {brightness: lamp.brightness} : {}), ...(lamp.supported_color_modes.includes('xy') ? {xy: [.5, .4]} : {})}]))};
      }
      if (type.startsWith('preview/')) {
        const session = sessions.get(request.preview_id);
        if (!session) throw new Error('Live-Probe ist nicht mehr aktiv.');
        if (type === 'preview/keepalive') return {preview_id: request.preview_id, expires_in: 120};
        if (type === 'preview/cancel') {sessions.delete(request.preview_id); return {...result(session.area_id), restored: true};}
        if (type === 'preview/apply') {session.sequence = request.sequence; return {...result(session.area_id), sequence: request.sequence, moon_fraction: .37};}
        if (type === 'preview/commit') {
          const committed = {...result(session.area_id)};
          if (request.scene) committed.scene = saveScene(request.scene);
          if (request.palette) committed.palette = savePalette(request.palette);
          sessions.delete(request.preview_id); return committed;
        }
      }
      if (type === 'scene/save') return saveScene(request.scene);
      if (type === 'palette/save') return savePalette(request.palette);
      if (type === 'palette/delete') {
        const used = scenes.filter(scene => scene.palette_id === request.palette_id);
        if (used.length) throw new Error(`Die Palette wird noch von diesen Szenen verwendet: ${used.map(item => item.name).join(', ')}`);
        const index = palettes.findIndex(item => item.id === request.palette_id);
        if (index >= 0) palettes.splice(index, 1); return {};
      }
      if (type === 'dynamic/stop') {runs = runs.filter(item => item.area_id !== request.area_id); return {...result(request.area_id), stopped: true};}
      if (type === 'scene/apply') {
        const scene = scenes.find(item => item.id === request.scene_id);
        if (scene?.dynamic?.enabled) runs = [...runs.filter(item => item.area_id !== scene.area_id), {scene_id: scene.id, area_id: scene.area_id, name: scene.name, interval: scene.dynamic.interval, transition: scene.dynamic.transition}];
        return result(scene?.area_id);
      }
      if (type === 'light/replace_options') return {sources: clone(lamps), targets: clone([...lamps, replacement])};
      if (type === 'light/replace_preview') return {old_entity_id: request.old_entity_id, new_entity_id: request.new_entity_id, source_name: lamps.find(lamp => lamp.entity_id === request.old_entity_id)?.name, target_name: replacement.name, preview_token: 'synthetic-token', can_replace: true, entries: [{kind: 'settings', name: 'Freigaben', count: 1}, {kind: 'zones', name: 'Abendzone', count: 1}, {kind: 'scenes', name: 'Herbstabend', count: 2}, {kind: 'rooms', name: 'Lampenpositionen', count: 2}], warnings: [], conflicts: []};
      if (type === 'light/replace') return {replaced: true, total: 6};
      if (['room/toggle', 'room/brightness', 'palette/apply', 'light/set', 'action/execute'].includes(type)) return result(request.area_id);
      throw new Error(`Synthetic QA fixture does not handle ${type}`);
    },
  };
  window.qaFixture = {requests, palettes, rooms, lamps, get scenes() {return scenes;}, get sessions() {return [...sessions.keys()];}, get bindings() {return bindings;}};
  document.querySelector('lichtzentrale-panel').hass = api;
})();
