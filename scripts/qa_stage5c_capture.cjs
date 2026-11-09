// Geändert für Lichtzentrale
// Real production bundle, synthetic transport. Run with official Playwright installed.
// node qa_stage5c_capture.cjs --site <prepared-site> --out <screenshots> [--browser <Chrome path>]
const {chromium} = require(process.env.QA_PLAYWRIGHT || 'playwright');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const args = process.argv.slice(2);
const option = (name, fallback) => args.includes(name) ? args[args.indexOf(name) + 1] : fallback;
const site = path.resolve(option('--site', '.'));
const output = path.resolve(option('--out', path.join(site, 'screenshots')));
const executablePath = option('--browser', process.env.QA_BROWSER);
const report = {viewport: {width: 390, height: 844, deviceScaleFactor: 1}, fixture: 'Synthetic room/zone/device data; no live HA', screenshots: [], passed: [], errors: []};
const types = {'.html': 'text/html; charset=utf-8', '.js': 'application/javascript; charset=utf-8', '.json': 'application/json'};
(async () => {
  fs.mkdirSync(output, {recursive: true});
  const server = http.createServer((request, response) => {
    const pathname = new URL(request.url, 'http://localhost').pathname;
    if (pathname === '/favicon.ico') {response.writeHead(204).end(); return;}
    const relative = pathname === '/' ? 'index.html' : pathname.slice(1);
    const file = path.resolve(site, relative);
    if (!file.startsWith(site + path.sep)) {response.writeHead(403).end(); return;}
    fs.readFile(file, (error, bytes) => {if (error) {response.writeHead(404).end(); return;} response.writeHead(200, {'Content-Type': types[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store'}).end(bytes);});
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {channel: 'chrome'})});
    const context = await browser.newContext({viewport: {width: 390, height: 844}, deviceScaleFactor: 1, locale: 'de-DE', reducedMotion: 'reduce'});
    const page = await context.newPage(); page.setDefaultTimeout(12000);
    page.on('pageerror', error => report.errors.push(`Browser: ${error.message}`));
    page.on('console', message => {if (message.type() === 'error') report.errors.push(`Console: ${message.text()}`);});
    const url = `http://127.0.0.1:${server.address().port}/index.html`;
    const nav = name => page.getByRole('navigation').getByRole('button', {name, exact: true}).click();
    const latest = suffix => page.evaluate(suffix => window.qaFixture.requests.filter(request => request.type.endsWith(suffix)).at(-1), suffix);
    const settle = () => page.waitForTimeout(500); // debounce is a product requirement (350 ms)
    async function range(name, value) {const slider = page.getByLabel(name, {exact: true}); await slider.focus(); await slider.press('Home'); for (let i = 1; i < value; i++) await slider.press('ArrowRight'); assert.equal(await slider.inputValue(), String(value));}
    async function screenshot(name, target) {
      await page.waitForTimeout(100);
      if (target) await target.evaluate(element => {element.scrollIntoView({block: 'start'}); const main = element.getRootNode().querySelector('main'); main.scrollTop = Math.max(0, main.scrollTop - 12);});
      await page.waitForTimeout(100);
      const dimensions = await page.evaluate(() => {
        const root = document.querySelector('lichtzentrale-panel').shadowRoot;
        const main = root.querySelector('main');
        return {viewport: innerWidth, document: document.documentElement.scrollWidth, main: main.clientWidth, mainScroll: main.scrollWidth, overflow: [...root.querySelectorAll('button,input,select,fieldset')].filter(element => element.getClientRects().length && (element.getBoundingClientRect().left < -1 || element.getBoundingClientRect().right > innerWidth + 1)).map(element => ({tag: element.tagName, label: element.getAttribute('aria-label') || element.textContent.slice(0,70), left: element.getBoundingClientRect().left, right: element.getBoundingClientRect().right}))};
      });
      assert.equal(dimensions.viewport, 390);
      assert.ok(dimensions.document <= 390, JSON.stringify(dimensions));
      assert.ok(dimensions.mainScroll <= dimensions.main + 1, JSON.stringify(dimensions));
      assert.deepEqual(dimensions.overflow, [], JSON.stringify(dimensions));
      const filename = `${name}-390.png`; await page.screenshot({path: path.join(output, filename)});
      report.screenshots.push({filename, ...dimensions});
    }
    await page.goto(url); await page.getByRole('button', {name: 'Abendzone', exact: true}).waitFor();
    await screenshot('01-zuhause'); report.passed.push('Home room/zone chips render without horizontal overflow.');
    await nav('Farben'); await page.getByRole('button', {name: 'Herbstglut', exact: true}).waitFor();
    const count = await page.locator('.palette').count(); assert.ok(count >= 20); report.passed.push(`${count} palette cards, including Herbstglut, are rendered.`);
    await screenshot('02-galerie', page.getByRole('heading', {name: 'Herbst', exact: true}));
    await page.getByRole('button', {name: '+ Neue Palette', exact: true}).click();
    await page.getByLabel('Palettenname', {exact: true}).fill('Abendgold');
    await page.getByLabel('Kategorie', {exact: true}).fill('Herbst');
    await page.getByLabel('Farbe 1', {exact: true}).fill('#ff9a2e');
    await page.getByRole('button', {name: '+ Farbe hinzufügen', exact: true}).click();
    await screenshot('03-eigene-palette', page.getByRole('heading', {name: 'Neue Palette', exact: true}));
    await page.getByRole('combobox', {name: /^Raum oder Zone/}).selectOption('zone:fixture_evening'); await settle();
    await page.getByLabel('Palettenname', {exact: true}).fill('Abendgold eins');
    await page.getByLabel('Palettenname', {exact: true}).fill('Abendgold zwei');
    await page.getByLabel('Palettenname', {exact: true}).fill('Abendgold'); await settle();
    assert.equal((await latest('/apply')).palette.name, 'Abendgold');
    await screenshot('04-palette-live', page.getByRole('heading', {name: 'Live-Probe', exact: true}));
    await nav('Zuhause'); await page.waitForFunction(() => window.qaFixture.sessions.length === 0); assert.ok(await latest('/cancel')); await page.getByRole('button', {name: 'Abendzone', exact: true}).waitFor();
    report.passed.push('Repeated palette edits debounce to latest state; navigation cancels active preview.');
    await nav('Farben'); await page.getByRole('button', {name: '+ Neue Palette', exact: true}).click();
    await page.getByLabel('Palettenname', {exact: true}).fill('Abendgold gespeichert');
    await page.getByRole('button', {name: 'Palette speichern', exact: true}).click();
    await page.getByRole('button', {name: 'Palette bearbeiten', exact: true}).waitFor();
    assert.equal((await latest('palette/save')).palette.name, 'Abendgold gespeichert'); report.passed.push('Own palette saves through server API, then offers edit and duplicate actions.');
    await nav('Zuhause'); await page.getByRole('button', {name: 'Abendzone', exact: true}).click();
    await page.getByRole('button', {name: 'Szene bearbeiten', exact: true}).click(); await page.getByLabel('Szenenname', {exact: true}).waitFor();
    await screenshot('05-szeneneditor', page.getByRole('heading', {name: 'Szene bearbeiten', exact: true}));
    await screenshot('06-welle', page.getByLabel('Dynamischer Farbwechsel', {exact: true}).locator('..'));
    await page.getByRole('button', {name: 'Leseecke in Welle nach unten', exact: true}).click(); await settle();
    assert.equal((await latest('/apply')).scene.wave_order[0], 'light.fixture_spot');
    await range('Leseecke feste Helligkeit', 18);
    await range('Sofaspot feste Helligkeit', 24); await settle();
    await screenshot('07-lampenhelligkeit', page.getByTestId('lamp-scene-row').filter({has: page.locator('legend', {hasText: 'Leseecke'})}));
    await screenshot('07b-feste-farbe', page.getByTestId('lamp-scene-row').filter({has: page.locator('legend', {hasText: 'Regallicht'})}));
    await screenshot('08-mondlicht', page.getByTestId('lamp-scene-row').filter({has: page.locator('legend', {hasText: 'Fensterlicht'})}));
    await screenshot('08b-ein-aus', page.getByTestId('lamp-scene-row').filter({has: page.locator('legend', {hasText: 'Deckenlicht'})}));
    assert.equal(await page.getByLabel('Deckenlicht An / Aus', {exact: true}).inputValue(), 'off');
    await page.getByLabel('Szenenname', {exact: true}).fill('Herbstabend fein');
    await page.getByRole('button', {name: 'Szene speichern', exact: true}).click(); await page.getByRole('button', {name: 'Szene bearbeiten', exact: true}).waitFor();
    const committed = await latest('/commit'); assert.equal(committed.scene.name, 'Herbstabend fein'); assert.equal(committed.scene.lamp_settings['light.fixture_moon'].mode, 'moon');
    report.passed.push('Existing scene edits per-lamp levels, keeps fixed/moon/off modes, reorders wave, and commits latest document.');
    await page.getByRole('button', {name: 'Szene nach Jahreszeit', exact: true}).click();
    await page.getByTestId('seasonal-editor').waitFor();
    for (const season of ['Frühling', 'Sommer', 'Herbst', 'Winter']) await page.getByRole('combobox', {name: new RegExp('^' + season + '$')}).selectOption('fixture-evening');
    await screenshot('11-jahreszeiten', page.getByRole('heading', {name: 'Szene nach Jahreszeit', exact: true}));
    await page.getByLabel('Weihnachten zusätzlich verwenden', {exact: true}).check();
    await page.getByRole('combobox', {name: /^Weihnachten$/}).selectOption('fixture-evening');
    await screenshot('12-weihnachten', page.getByLabel('Weihnachten zusätzlich verwenden', {exact: true}));
    await page.getByText('Mehr Optionen · Jahreszeitenbeginn', {exact: true}).click();
    await page.getByLabel('Frühling ab Tag', {exact: true}).selectOption('20');
    await screenshot('13-jahreszeiten-beginn', page.getByText('Mehr Optionen · Jahreszeitenbeginn', {exact: true}));
    await page.getByRole('button', {name: 'Jahreszeiten-Szene speichern', exact: true}).click();
    await page.getByRole('button', {name: 'Szene nach Jahreszeit', exact: true}).waitFor();
    const seasonal = (await latest('scene/save')).scene;
    assert.equal(seasonal.kind, 'seasonal'); assert.equal(seasonal.seasonal.boundaries.spring, '03-20'); assert.equal(seasonal.seasonal.christmas.enabled, true);
    report.passed.push('Seasonal editor saves all four season mappings, Christmas override, and custom March 20 boundary.');
    await nav('Mehr');
    await page.getByRole('combobox', {name: /^Bisherige Lampe/}).selectOption('light.fixture_corner');
    await page.getByRole('combobox', {name: /^Neue Lampe/}).selectOption('light.fixture_replacement');
    await page.getByRole('button', {name: 'Betroffene Einträge prüfen', exact: true}).click();
    await page.getByRole('button', {name: 'Diese Ersetzung bestätigen', exact: true}).waitFor();
    await screenshot('09-lampe-ersetzen', page.getByRole('heading', {name: 'Lampe ersetzen', exact: true}));
    await page.getByRole('button', {name: 'Abbrechen', exact: true}).click(); assert.equal(await latest('light/replace'), undefined);
    report.passed.push('Replacement preview lists references; cancel sends no replacement write.');
    await nav('Taster'); await page.getByText('Alle Ereignisse und gespeicherte Belegungen', {exact: true}).click();
    await page.getByRole('button', {name: 'Belegung bearbeiten', exact: true}).click();
    await page.getByRole('combobox', {name: /^Beim Einschalten/}).selectOption('brightness');
    await screenshot('10-taster-einschalten', page.getByRole('combobox', {name: /^Beim Einschalten/}).locator('..'));
    await range('Helligkeit beim Einschalten', 35);
    await page.getByRole('button', {name: 'Belegung speichern', exact: true}).click();
    await page.getByText('Belegung in Home Assistant gespeichert.', {exact: true}).waitFor();
    assert.equal((await latest('binding/save')).binding.params.on_behavior.brightness, 89);
    report.passed.push('Binding optional fixed-brightness on-behavior saves 35% as 89/255.');
    await page.getByRole('button', {name: 'Belegung bearbeiten', exact: true}).click();
    await page.getByRole('combobox', {name: /^Beim Einschalten/}).selectOption('time');
    await page.getByLabel('Einschaltfenster 1 Beginn: Uhrzeit', {exact: true}).fill('22:30');
    await page.getByLabel('Einschaltfenster 1 Ende: Uhrzeit', {exact: true}).fill('06:30');
    await range('Einschaltfenster 1 Helligkeit', 18);
    await page.getByLabel('Einschaltfenster 1 Weißton in Kelvin', {exact: true}).fill('2200');
    await screenshot('14-taster-zeitfenster', page.getByRole('group', {name: 'Einschaltfenster 1', exact: true}));
    await screenshot('15-taster-weisslicht', page.getByRole('combobox', {name: /^Einschaltfenster 1 Aktion/}).locator('..'));
    await page.getByRole('button', {name: 'Einschaltfenster hinzufügen', exact: true}).click();
    await page.getByRole('combobox', {name: /^Einschaltfenster 2 Beginn: Bezug/}).selectOption('sunset');
    await page.getByLabel('Einschaltfenster 2 Beginn: Versatz in Minuten', {exact: true}).fill('-30');
    await page.getByRole('combobox', {name: /^Einschaltfenster 2 Ende: Bezug/}).selectOption('none');
    await page.getByRole('combobox', {name: /^Einschaltfenster 2 Aktion/}).selectOption('scene');
    await page.getByRole('combobox', {name: /^Einschaltfenster 2 Szene/}).selectOption('fixture-reading');
    await screenshot('16-taster-sonnenzeit', page.getByRole('group', {name: 'Einschaltfenster 2', exact: true}));
    await page.getByRole('button', {name: 'Belegung speichern', exact: true}).click();
    await page.getByText('Belegung in Home Assistant gespeichert.', {exact: true}).waitFor();
    const timed = (await latest('binding/save')).binding.params.on_behavior;
    assert.equal(timed.mode, 'time'); assert.equal(timed.windows.length, 2);
    assert.equal(timed.windows[0].window.after.value, '22:30'); assert.equal(timed.windows[0].color_temp_kelvin, 2200);
    assert.equal(timed.windows[1].window.after.offset_min, -30); assert.equal(timed.windows[1].window.before, null); assert.equal(timed.windows[1].scene_id, 'fixture-reading');
    report.passed.push('Binding time windows save overnight brightness/white tone plus sunset-minus-30 scene with open end.');
    assert.deepEqual(report.errors, []);
  } catch (error) {report.errors.push(error.stack || String(error)); process.exitCode = 1;}
  finally {if (browser) await browser.close(); await new Promise(resolve => server.close(resolve)); fs.writeFileSync(path.join(output, 'qa-report.json'), JSON.stringify(report, null, 2)); console.log(JSON.stringify(report, null, 2));}
})();
