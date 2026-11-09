// Geändert für Lichtzentrale
// Real production bundle, synthetic transport. Run with official Playwright installed.
// node qa_stage5d_capture.cjs --site <prepared-site> --out <screenshots> [--browser <Chrome path>]
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
    await nav('Mehr');
    await page.getByRole('heading', {name: 'Einstellungen', exact: true}).waitFor();
    const input = page.getByLabel('Dimm-Untergrenze (%)', {exact: true});
    await input.waitFor();
    assert.equal(await input.inputValue(), '1');
    assert.equal(await input.getAttribute('min'), '1');
    assert.equal(await input.getAttribute('max'), '20');
    await screenshot('01-einstellungen', page.getByRole('heading', {name: 'Einstellungen', exact: true}));
    report.passed.push('Production settings display default dim floor of 1%, with bounds 1–20%.');
    await input.fill('20');
    await page.getByRole('button', {name: 'Untergrenze speichern', exact: true}).click();
    await page.waitForFunction(() => window.qaFixture.requests.some(request => request.type === 'lichtzentrale/settings/dimming' && request.dim_min_pct === 20));
    await page.getByRole('button', {name: 'Untergrenze speichern', exact: true}).waitFor({state: 'visible'});
    await page.waitForTimeout(150);
    assert.equal((await latest('settings/dimming')).dim_min_pct, 20);
    await nav('Zuhause'); await nav('Mehr');
    assert.equal(await input.inputValue(), '20');
    report.passed.push('20% saves through settings/dimming and survives navigation.');
    await input.fill('1');
    await page.getByRole('button', {name: 'Untergrenze speichern', exact: true}).click();
    await page.waitForFunction(() => window.qaFixture.requests.filter(request => request.type === 'lichtzentrale/settings/dimming').at(-1)?.dim_min_pct === 1);
    await page.waitForTimeout(150);
    const readsBeforeRefresh = await page.evaluate(() => window.qaFixture.requests.filter(request => request.type === 'lichtzentrale/settings/get').length);
    await page.getByRole('button', {name: 'Neu laden', exact: true}).click();
    await page.waitForFunction(count => window.qaFixture.requests.filter(request => request.type === 'lichtzentrale/settings/get').length === count + 1, readsBeforeRefresh);
    await input.waitFor({state: 'visible'});
    assert.equal(await page.evaluate(() => window.qaFixture.requests.filter(request => request.type === 'lichtzentrale/settings/get').length), readsBeforeRefresh + 1);
    assert.equal(await input.inputValue(), '1');
    await screenshot('02-einstellungen-gespeichert', page.getByRole('heading', {name: 'Einstellungen', exact: true}));
    report.passed.push('1% saves and survives server refresh. Both settings screenshots have no horizontal overflow at 390px.');
    assert.deepEqual(report.errors, []);
  } catch (error) {report.errors.push(error.stack || String(error)); process.exitCode = 1;}
  finally {if (browser) await browser.close(); await new Promise(resolve => server.close(resolve)); fs.writeFileSync(path.join(output, 'qa-report.json'), JSON.stringify(report, null, 2)); console.log(JSON.stringify(report, null, 2));}
})();
