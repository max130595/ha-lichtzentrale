// Geändert für Lichtzentrale
// Real production bundle, synthetic transport. Run with official Playwright installed.
// node qa_stage5e_capture.cjs --site <prepared-site> --out <screenshots> [--browser <Chrome path>]
const {chromium} = require(process.env.QA_PLAYWRIGHT || 'playwright');
const fs = require('node:fs');
const crypto = require('node:crypto');
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
    report.browser = browser.version();
    report.productionBundleSha256 = crypto.createHash('sha256').update(fs.readFileSync(path.join(site, 'assets/lichtzentrale_panel.js'))).digest('hex');
    const context = await browser.newContext({viewport: {width: 390, height: 844}, deviceScaleFactor: 1, locale: 'de-DE', reducedMotion: 'reduce'});
    const page = await context.newPage(); page.setDefaultTimeout(12000);
    page.on('pageerror', error => report.errors.push(`Browser: ${error.message}`));
    page.on('console', message => {if (message.type() === 'error') report.errors.push(`Console: ${message.text()}`);});
    const url = `http://127.0.0.1:${server.address().port}/index.html`;
    const nav = name => page.getByRole('navigation').getByRole('button', {name, exact: true}).click();
    const latest = suffix => page.evaluate(suffix => window.qaFixture.requests.filter(request => request.type.endsWith(suffix)).at(-1), suffix);
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
    await page.goto(url); await page.getByRole('navigation').waitFor();
    const settle = () => page.waitForTimeout(550);
    await page.getByRole('button', {name: 'Abendzone', exact: true}).click();
    await page.getByRole('button', {name: 'Szene bearbeiten', exact: true}).click();
    const effect = page.getByLabel('Leseecke Effekt', {exact: true});
    await effect.selectOption('sparkle');
    await page.getByLabel('Sofaspot Effekt', {exact: true}).selectOption('candle');
    await settle();
    assert.equal((await latest('preview/apply')).scene.lamp_settings['light.fixture_corner'].effect, 'sparkle');
    assert.equal((await latest('preview/apply')).scene.lamp_settings['light.fixture_spot'].effect, 'candle');
    assert.equal(await page.getByLabel('Deckenlicht Effekt', {exact: true}).count(), 0);
    assert.equal(await effect.locator('option', {hasText: 'Funkeln'}).count(), 1);
    await screenshot('01-lampen-effekt', page.getByTestId('lamp-scene-row').filter({has: page.locator('legend', {hasText: 'Leseecke'})}));
    report.passed.push('Color and brightness-only lamp effects reach the real live-preview payload; German effect labels and no effect field for on/off lamps.');
    const script = page.getByRole('combobox', {name: 'Skript beim Szenenstart', exact: true});
    await script.selectOption('script.fixture_music'); await settle();
    await screenshot('03-szenen-skript', script.locator('..'));
    await page.evaluate(() => window.qaFixture.failNext.add('preview/commit'));
    await page.getByRole('button', {name: 'Szene speichern', exact: true}).click();
    await page.getByRole('alert').filter({hasText: 'Synthetischer Speicherfehler'}).waitFor();
    assert.equal(await effect.inputValue(), 'sparkle'); assert.equal(await script.inputValue(), 'script.fixture_music');
    await page.getByRole('button', {name: 'Szene speichern', exact: true}).click();
    await page.getByRole('button', {name: 'Szene bearbeiten', exact: true}).waitFor();
    const saved = (await latest('preview/commit')).scene;
    assert.equal(saved.start_script, 'script.fixture_music'); assert.equal(saved.lamp_settings['light.fixture_corner'].effect, 'sparkle');
    report.passed.push('Scene save failure retains edits; retry commits effect and start_script.');
    await page.getByRole('button', {name: 'Szene bearbeiten', exact: true}).click();
    await effect.waitFor(); assert.equal(await effect.inputValue(), 'sparkle'); assert.equal(await script.inputValue(), 'script.fixture_music');
    await effect.selectOption('candle'); await settle();
    await nav('Taster'); await page.waitForFunction(() => window.qaFixture.sessions.length === 0);
    assert.equal(await page.evaluate(() => window.qaFixture.scenes.find(s => s.id === 'fixture-evening').lamp_settings['light.fixture_corner'].effect), 'sparkle');
    report.passed.push('Reopening preserves saved fields; navigation cancels unsaved live changes.');
    await page.getByText('Alle Ereignisse und gespeicherte Belegungen', {exact: true}).click();
    await page.getByRole('button', {name: 'Belegung bearbeiten', exact: true}).click();
    await page.getByLabel('Zur Ambiente-Zeit zuerst Szene', {exact: true}).check();
    await page.getByRole('combobox', {name: 'Ambiente-Szene', exact: true}).selectOption('fixture-reading');
    await page.getByRole('combobox', {name: 'Ambiente Beginn: Bezug', exact: true}).selectOption('sunset');
    await page.getByLabel('Ambiente Beginn: Versatz in Minuten', {exact: true}).fill('-15');
    await page.getByLabel('Ambiente Ende: Uhrzeit', {exact: true}).fill('22:30');
    await screenshot('02-taster-ambiente-zuerst', page.getByRole('group', {name: 'Ambiente zuerst', exact: true}));
    await page.evaluate(() => window.qaFixture.failNext.add('binding/save'));
    await page.getByRole('button', {name: 'Belegung speichern', exact: true}).click();
    await page.getByText(/Synthetischer Speicherfehler/).waitFor();
    assert.equal(await page.getByLabel('Zur Ambiente-Zeit zuerst Szene', {exact: true}).isChecked(), true);
    await page.getByRole('button', {name: 'Belegung speichern', exact: true}).click();
    await page.getByText('Belegung in Home Assistant gespeichert.', {exact: true}).waitFor();
    const ambient = (await latest('binding/save')).binding.params.ambient_first;
    assert.equal(ambient.scene_id, 'fixture-reading'); assert.equal(ambient.window.after.offset_min, -15); assert.equal(ambient.window.before.value, '22:30');
    await page.getByRole('button', {name: 'Belegung bearbeiten', exact: true}).click();
    assert.equal(await page.getByLabel('Zur Ambiente-Zeit zuerst Szene', {exact: true}).isChecked(), true);
    assert.equal(await page.getByRole('combobox', {name: 'Ambiente-Szene', exact: true}).inputValue(), 'fixture-reading');
    report.passed.push('Ambient-first scene and sunset-minus-15 to 22:30 window survive failed save, retry, and reopening.');
    assert.deepEqual(report.errors, []);
  } catch (error) {report.errors.push(error.stack || String(error)); process.exitCode = 1;}
  finally {if (browser) await browser.close(); await new Promise(resolve => server.close(resolve)); fs.writeFileSync(path.join(output, 'qa-report.json'), JSON.stringify(report, null, 2)); console.log(JSON.stringify(report, null, 2));}
})();
