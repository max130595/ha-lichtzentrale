// Geändert für Lichtzentrale
// Real production bundle, synthetic transport. Run with official Playwright installed.
// node qa_stage6_capture.cjs --site <prepared-site> --out <screenshots> [--browser <Chrome path>]
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
      report.screenshots.push({filename, sha256: crypto.createHash('sha256').update(fs.readFileSync(path.join(output, filename))).digest('hex'), ...dimensions});
    }
    await page.goto(url); await page.getByRole('navigation').waitFor();
    await nav('Mehr');
    const card = page.getByRole('region', {name: 'Urlaubsmodus', exact: true});
    const date = page.getByLabel('Enddatum (optional, einschließlich)', {exact: false});
    const save = page.getByRole('button', {name: 'Urlaubseinstellungen speichern', exact: true});
    const test = page.getByRole('button', {name: 'Probelauf 5 min · echte Lampen', exact: true});
    const toggle = page.getByRole('switch', {name: 'Urlaubsmodus einschalten', exact: true});
    await date.waitFor();
    await screenshot('01-urlaubsmodus', card);
    await page.getByText('Räume und Zonen · 2 ausgewählt', {exact: true}).click();
    await page.getByLabel('Wohnzimmer: Typ', {exact: false}).selectOption('bedroom');
    await page.getByLabel('Wohnzimmer: Typ', {exact: false}).selectOption('living');
    await page.getByLabel('Wohnzimmer: Häufigkeit (Gewicht)', {exact: false}).fill('4');
    await page.getByLabel('Wohnzimmer: Einschalten', {exact: false}).selectOption('brightness');
    await page.getByLabel('Wohnzimmer: Helligkeit', {exact: false}).fill('40');
    await screenshot('02-raumauswahl', page.getByRole('group', {name: 'Teilnehmende Räume', exact: true}));
    assert.equal(await test.isDisabled(), true); assert.equal(await toggle.isDisabled(), true);
    await page.getByLabel('Wohnzimmer: Einschalten', {exact: false}).selectOption('scene');
    assert.equal(await save.isDisabled(), true);
    await page.getByLabel('Wohnzimmer: Szene', {exact: false}).selectOption('fixture-reading');
    await page.getByText('Räume und Zonen · 2 ausgewählt', {exact: true}).click();
    await page.getByText('Zeitfenster und Optionen', {exact: true}).click();
    await page.getByLabel('Abend beginnt: Versatz in Minuten', {exact: false}).fill('-20');
    await page.getByLabel('Morgen beginnt: Bezug', {exact: false}).selectOption('sunrise');
    await page.getByLabel('Morgen beginnt: Versatz in Minuten', {exact: false}).fill('-30');
    await page.getByLabel('Maximal gleichzeitig eingeschaltete Räume', {exact: false}).fill('2');
    await page.getByLabel('Aus dem Verlauf lernen', {exact: false}).check();
    await page.getByLabel('Push-Hinweis beim Ein- und Ausschalten', {exact: false}).selectOption('notify.fixture_phone');
    await screenshot('03-abendfenster', page.getByRole('group', {name: 'Abend', exact: true}));
    await screenshot('04-morgen-optionen', page.getByRole('group', {name: 'Morgen beginnt', exact: true}));
    await page.getByText('Zeitfenster und Optionen', {exact: true}).click();
    await date.fill('2030-11-20');
    await page.evaluate(() => window.qaFixture.failNext.add('vacation/save'));
    await save.click(); await page.getByRole('alert').filter({hasText: 'Synthetischer Speicherfehler'}).waitFor();
    assert.equal(await date.inputValue(), '2030-11-20');
    await page.evaluate(() => window.qaFixture.delayMs = 450);
    await save.click(); assert.equal(await save.isDisabled(), true); assert.equal(await date.isDisabled(), true);
    await page.getByText('Urlaubseinstellungen in Home Assistant gespeichert.', {exact: true}).waitFor();
    const saved = await latest('vacation/save');
    assert.equal(saved.config.rooms[0].weight, 4); assert.equal(saved.config.evening.start.offset_min, -20);
    assert.equal(saved.config.morning.start.event, 'sunrise'); assert.equal(saved.config.max_rooms, 2);
    assert.equal(saved.config.learn_history, true); assert.equal(saved.config.notify_service, 'notify.fixture_phone');
    assert.equal(saved.until, '2030-11-20');
    report.passed.push('Room type/action editors, brightness, scene validation, time/sun boundaries, learning and push options; dirty guards; failed-save retention and server-confirmed retry.');
    await toggle.click(); await page.getByText('Urlaubsmodus eingeschaltet.', {exact: true}).waitFor();
    assert.equal(await test.isDisabled(), true);
    await screenshot('05-plan-heute', page.getByRole('region', {name: 'Plan heute', exact: true}));
    await date.fill('2030-11-22'); await page.getByRole('button', {name: 'Enddatum übernehmen', exact: true}).click();
    await page.waitForFunction(() => window.qaFixture.vacation.until === '2030-11-22');
    await page.getByRole('switch', {name: 'Urlaubsmodus ausschalten', exact: true}).click();
    await page.getByText('Urlaubsmodus ausgeschaltet.', {exact: true}).waitFor();
    report.passed.push('Enable/disable and changed end date reflect server state; enabled mode prevents trial.');
    const before = await page.evaluate(() => window.qaFixture.requests.filter(r => r.type.endsWith('vacation/test')).length);
    page.once('dialog', dialog => dialog.dismiss()); await test.click();
    assert.equal(await page.evaluate(() => window.qaFixture.requests.filter(r => r.type.endsWith('vacation/test')).length), before);
    page.once('dialog', async dialog => {assert.match(dialog.message(), /echte Lampen/); await dialog.accept();}); await test.click();
    await page.getByText('Probelauf läuft', {exact: true}).waitFor();
    assert.equal(await test.isDisabled(), true);
    await screenshot('06-probelauf', page.getByRole('region', {name: 'Plan heute', exact: true}));
    await page.getByRole('button', {name: 'Probelauf beenden', exact: true}).click();
    await page.getByText('Urlaubsmodus ausgeschaltet.', {exact: true}).waitFor();
    report.passed.push('Trial cancellation sends no command; explicit real-lamp warning confirmation starts synthetic transport only; active trial and stop verified.');
    await date.fill('2030-12-01');
    page.once('dialog', dialog => dialog.dismiss()); await nav('Zuhause'); assert.equal(await date.count(), 1);
    page.once('dialog', dialog => dialog.accept()); await nav('Zuhause');
    await page.getByRole('button', {name: 'Abendzone', exact: true}).waitFor();
    await nav('Mehr'); await date.waitFor(); assert.equal(await date.inputValue(), '2030-11-22');
    report.passed.push('Dirty navigation supports stay/discard; reopening reads server-confirmed state.');
    assert.deepEqual(report.errors, []);
  } catch (error) {report.errors.push(error.stack || String(error)); process.exitCode = 1;}
  finally {if (browser) await browser.close(); await new Promise(resolve => server.close(resolve)); fs.writeFileSync(path.join(output, 'qa-report.json'), JSON.stringify(report, null, 2)); console.log(JSON.stringify(report, null, 2));}
})();
