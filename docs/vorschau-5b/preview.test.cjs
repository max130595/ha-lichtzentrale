// Geändert für Lichtzentrale: tests only the isolated Phase-1 preview, never Home Assistant.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM, VirtualConsole } = require('jsdom');
const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');

function setup(t, width = 390) {
  const errors = [], forbidden = [];
  const vc = new VirtualConsole();
  vc.on('jsdomError', e => errors.push(e.message));
  const dom = new JSDOM(html, {
    url: `https://preview.invalid/?width=${width}`, runScripts: 'dangerously', virtualConsole: vc,
    beforeParse(w) {
      w.scrollTo = () => {};
      const deny = name => () => { forbidden.push(name); throw Error(`Forbidden: ${name}`); };
      for (const name of ['fetch', 'XMLHttpRequest', 'WebSocket', 'EventSource']) w[name] = deny(name);
      for (const name of ['localStorage', 'sessionStorage', 'indexedDB']) {
        Object.defineProperty(w, name, { get: deny(name), configurable: true });
      }
      Object.defineProperty(w.document, 'cookie', { get: deny('cookie'), set: deny('cookie') });
    },
  });
  const { window: w } = dom, d = w.document;
  const find = s => { const el = d.querySelector(s); assert.ok(el, `Element missing: ${s}`); return el; };
  const click = s => find(s).click();
  const change = (s, value) => {
    const el = find(s);
    if (el.type === 'checkbox') el.checked = value; else el.value = value;
    el.dispatchEvent(new w.Event('change', { bubbles: true }));
  };
  const nav = name => click(`[data-testid="nav-${name}"]`);
  const state = () => w.preview.getState();
  t.after(() => { dom.window.close(); assert.deepEqual(errors, []); assert.deepEqual(forbidden, []); });
  return { w, d, find, click, change, nav, state };
}

test('all five German tabs and explicit demo boundary; no external assets', t => {
  const a = setup(t);
  assert.equal(a.d.querySelectorAll('nav button').length, 5);
  for (const tab of ['home', 'scenes', 'automations', 'buttons', 'more']) {
    a.nav(tab); assert.ok(a.find('h1').textContent.trim());
    assert.match(a.find('[data-testid="prototype-banner"]').textContent, /keine Geräte/);
  }
  assert.equal(a.d.querySelectorAll('script[src],link[href],img[src],iframe').length, 0);
  assert.doesNotMatch(a.d.body.textContent, /\b(?:light|switch|event)\.[a-z0-9_]+/);
});

test('requested mobile review widths select the frame without persistent state', t => {
  for (const width of [320, 390, 430]) {
    const a = setup(t, width);
    assert.equal(a.d.documentElement.style.getPropertyValue('--frame-width'), `${width}px`);
  }
});

test('cross-room zone keeps existing memberships and is available to actions', t => {
  const a = setup(t); a.click('[data-testid="new-zone"]');
  a.find('#zone-name').value = 'Leserunde';
  a.change('[name="zone-lamp"][value="l1"]', true); a.change('[name="zone-lamp"][value="l3"]', true);
  a.click('[data-testid="save-zone"]');
  const s = a.state(), zone = s.groups.find(g => g.name === 'Leserunde');
  assert.deepEqual(Array.from(zone.lights), ['l1', 'l3']);
  assert.ok(s.groups.find(g => g.id === 'r1').lights.includes('l1'));
  assert.ok(s.groups.find(g => g.id === 'z1').lights.includes('l1'));
  a.nav('automations'); a.click('[data-testid="new-automation"]'); a.click('[data-testid="wizard-next"]');
  assert.ok(a.find(`[data-change="wizard-target"][value="${zone.id}"]`));
});

test('zone rejects missing name or lamps', t => {
  const a = setup(t); a.click('[data-testid="new-zone"]'); a.click('[data-testid="save-zone"]');
  assert.equal(a.state().groups.length, 4); assert.match(a.find('#toast').textContent, /Namen/);
});

test('sunset minus15 wizard saves a readable disabled plan with all weekdays', t => {
  const a = setup(t); a.nav('automations'); a.click('[data-testid="new-automation"]');
  a.click('[data-testid="offset--15"]'); a.click('[data-testid="wizard-next"]');
  a.change('[data-change="wizard-target"][value="z1"]', true); a.click('[data-testid="wizard-next"]');
  a.click('[data-testid="wizard-next"]');
  const plan = a.state().automations.at(-1);
  assert.equal(plan.trigger, 'sunset'); assert.equal(plan.offset, -15); assert.equal(plan.days.length, 7);
  assert.deepEqual(Array.from(plan.actions[0].targets), ['z1']); assert.equal(plan.actions[0].scene, 'Abend');
  assert.equal(plan.enabled, false); assert.match(a.find('main').textContent, /15 Min. vor Sonnenuntergang · Wohnbereich → Szene Abend/);
  a.change(`[data-change="automation-toggle"][data-id="${plan.id}"]`, true);
  assert.equal(a.state().automations.at(-1).enabled, true);
});

test('wizard supports sunrise, free offsets and validates missing targets', t => {
  const a = setup(t); a.nav('automations'); a.click('[data-testid="new-automation"]');
  a.change('#trigger', 'sunrise'); a.change('#free-offset', '-42'); a.click('[data-testid="wizard-next"]');
  a.click('[data-testid="wizard-next"]'); assert.equal(a.state().wizard.step, 2);
  a.change('[data-change="wizard-target"][value="r1"]', true); a.click('[data-testid="wizard-next"]');
  a.click('[data-testid="wizard-next"]'); const p = a.state().automations.at(-1);
  assert.equal(p.trigger, 'sunrise'); assert.equal(Number(p.offset), -42);
});

test('22:30 multi-action creation and test preserve each target automatic state', t => {
  const a = setup(t); a.nav('automations'); a.click('[data-testid="new-automation"]');
  a.change('#trigger', 'clock'); a.change('#trigger-time', '22:30'); a.click('[data-testid="wizard-next"]');
  a.change('[data-change="wizard-target"][value="z1"]', true); a.click('[data-testid="wizard-next"]');
  a.change('[data-testid="action-type-0"]', 'off'); a.click('[data-testid="add-action"]');
  a.change('[data-testid="action-type-1"]', 'night'); a.change('[data-change="action-target"][data-index="1"][value="r3"]', true);
  a.click('[data-testid="wizard-next"]'); const plan = a.state().automations.at(-1);
  assert.equal(plan.time, '22:30'); assert.equal(plan.actions.length, 2);
  a.click(`[data-testid="test-${plan.id}"]`);
  assert.equal(a.state().automatic.z1.label, 'Aus'); assert.equal(a.state().automatic.r3.label, 'Nachtlicht');
});

test('night toggle returns to last automation; manual change does not replace it', t => {
  const a = setup(t); a.nav('automations'); a.click('[data-testid="test-a1"]');
  a.nav('home'); a.click('[data-testid="open-z1"]');
  assert.equal(a.find('h1').textContent, 'Wohnbereich');
  a.click('[data-testid="night-auto"]'); assert.equal(a.state().current.z1, 'Nachtlicht');
  assert.equal(a.state().automatic.z1.label, 'Abend');
  a.click('[data-testid="night-auto"]'); assert.equal(a.state().current.z1, 'Abend');
  a.change('#detail-brightness', '87'); assert.equal(a.state().automatic.z1.label, 'Abend');
  a.click('[data-testid="return-auto"]'); assert.equal(a.state().current.z1, 'Abend');
});

test('missing automatic state leaves lights unchanged, logs, and new day clears it', t => {
  const a = setup(t); a.click('[data-testid="open-z1"]'); const before = JSON.stringify(a.state().lights);
  a.click('[data-testid="return-auto"]'); assert.equal(JSON.stringify(a.state().lights), before);
  assert.match(a.state().logs[0], /kein Automatik-Stand/);
  a.nav('automations'); a.click('[data-testid="test-a1"]'); a.nav('more'); a.click('[data-testid="new-day"]');
  assert.equal(Object.keys(a.state().automatic).length, 0);
});

test('night scene name and brightness are editable per target', t => {
  const a = setup(t); a.click('[data-testid="open-z1"]');
  a.find('#night-name').value = 'Sanftes Licht'; a.find('#night-bri').value = '7';
  a.click('[data-action="night-save"]'); a.click('[data-testid="night-auto"]');
  assert.equal(a.state().night.z1.name, 'Sanftes Licht');
  for (const id of ['l1', 'l3', 'l5']) assert.equal(a.state().lights.find(l => l.id === id).bri, 7);
});

test('dimmer template maps five buttons and full means100 percent neutral white', t => {
  const a = setup(t); a.nav('buttons'); a.click('[data-testid="device-0"]'); a.click('[data-testid="dimmer-template"]');
  const expected = { An: 'full', Hue: 'nightauto', Hoch: 'up', Runter: 'down', Aus: 'off' };
  for (const [key, type] of Object.entries(expected)) assert.equal(a.state().bindings[`Hue Dimmer|${key}|Kurz drücken`].type, type);
  a.click('[data-testid="test-binding"]');
  for (const id of ['l1', 'l3', 'l5']) { const l = a.state().lights.find(l => l.id === id); assert.equal(l.bri, 100); assert.equal(l.kelvin, 4000); }
  a.click('[data-action="physical-button"][data-button="Aus"]'); a.click('[data-testid="test-binding"]');
  for (const id of ['l1', 'l3', 'l5']) assert.equal(a.state().lights.find(l => l.id === id).on, false);
});

test('Zigbee2MQTT same type different learned attributes stays distinct; unknown retained', t => {
  const a = setup(t); a.nav('buttons');
  for (const value of ['1', '2', 'right', 'unknown']) {
    a.find('#capture-kind').value = value; a.click('[data-testid="capture-event"]'); a.click('[data-action="capture-bind"]');
  }
  const events = a.state().captured; assert.equal(events.length, 4);
  assert.equal(events[0].source, events[1].source); assert.equal(events[0].type, events[1].type);
  assert.notEqual(events[0].key, events[1].key); assert.equal(events[3].label, 'experimental_click');
});

test('switch target never receives brightness or color fields; palette leaves it unchanged', t => {
  const a = setup(t), before = JSON.stringify(a.state().lights.find(l => l.id === 'l4'));
  a.nav('scenes'); a.click('[data-testid="palette-0"]'); a.change('#palette-target', 'r3');
  a.click('[data-testid="apply-palette"]');
  assert.equal(JSON.stringify(a.state().lights.find(l => l.id === 'l4')), before);
  a.nav('home'); a.click('[data-testid="open-r3"]'); a.change('#detail-brightness', '80');
  const sw = a.state().lights.find(l => l.id === 'l4'); assert.equal(sw.bri, undefined); assert.equal(sw.kelvin, undefined);
});

test('optional natural-light actions hidden until explicit simulated availability', t => {
  const a = setup(t); a.nav('buttons'); a.click('[data-testid="device-0"]');
  assert.equal(a.d.querySelectorAll('#binding-action option[value^="natural"]').length, 0);
  a.nav('more'); a.change('[data-testid="optional-al"]', true); a.nav('buttons'); a.click('[data-testid="device-0"]');
  assert.equal(a.d.querySelectorAll('#binding-action option[value^="natural"]').length, 2);
});

test('revoked light excluded from scene and reset restores only synthetic defaults', t => {
  const a = setup(t); a.nav('more'); a.change('[data-change="grant"][data-id="l1"]', false);
  const before = JSON.stringify(a.state().lights.find(l => l.id === 'l1'));
  a.nav('automations'); a.click('[data-testid="test-a1"]');
  assert.equal(JSON.stringify(a.state().lights.find(l => l.id === 'l1')), before);
  a.nav('more'); a.click('[data-testid="reset-demo"]');
  assert.equal(a.state().lights.find(l => l.id === 'l1').grant, true); assert.equal(Object.keys(a.state().automatic).length, 0);
});
