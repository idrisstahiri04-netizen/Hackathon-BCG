'use strict';
// Kenya (290 sub-counties) live check: loads, Go to today -> Sep 2026, forecasts +1/+3/+6, Kacheliba t=56, 0 JS errors, load time.
const path = require('path'), http = require('http');
const { spawn } = require('child_process');
const { chromium } = require('playwright');
const PORT = 8870, BASE = `http://127.0.0.1:${PORT}/`, REPO = path.resolve(__dirname, '..', '..');
const waitPort = () => new Promise((res, rej) => { const t0 = Date.now(); (function k() { http.get({ host: '127.0.0.1', port: PORT, path: '/' }, r => { r.resume(); res(); }).on('error', () => Date.now() - t0 > 8000 ? rej() : setTimeout(k, 150)); })(); });
(async () => {
  const server = spawn('python3', ['-m', 'http.server', String(PORT), '--bind', '127.0.0.1'], { cwd: REPO, stdio: 'ignore' });
  const errs = [];
  try {
    await waitPort();
    const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--enable-unsafe-swiftshader'] });
    const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
    page.on('pageerror', e => errs.push(String(e.message)));
    page.on('console', m => { if (m.type() === 'error' && !/ERR_CONNECTION_REFUSED|Failed to load resource|net::|Failed to fetch/.test(m.text())) errs.push(m.text()); });
    await page.route('**/js/config.local.js', r => r.fulfill({ status: 200, contentType: 'application/javascript', body: 'window.SMS_API_BASE="http://127.0.0.1:8805";' }));
    const t0 = Date.now();
    await page.goto(`${BASE}?role=gov&country=Kenya&t=56&county=Kacheliba`, { waitUntil: 'load' });
    await page.waitForFunction(() => window.RISK_DATA && window.RISK_DATA.KEN && window.GEO_DATA && document.querySelector('#clock-date') && window.APP);
    const load = Date.now() - t0; await page.waitForTimeout(2000);
    const info = () => page.evaluate(() => ({ clock: document.querySelector('#clock-date').textContent, stat: document.querySelector('#stat-units').textContent,
      detail: (document.querySelector('#detail') || document.body).innerText.replace(/\s+/g, ' ').slice(0, 220) }));
    const kach = await info();
    await page.screenshot({ path: path.join(__dirname, 'screens', 'ken_live_kacheliba.png') });
    console.log('load ms', load, '| kacheliba', JSON.stringify(kach));
    await page.goto(`${BASE}?country=Kenya&role=gov`, { waitUntil: 'load' });
    await page.waitForFunction(() => window.APP && document.querySelector('#go-today') && !document.querySelector('#go-today').hidden, null, { timeout: 15000 });
    await page.click('#go-today'); await page.waitForTimeout(1500);
    console.log('today', JSON.stringify(await info()));
    const meta = await page.evaluate(() => { const m = RISK_DATA.KEN.meta; const u = RISK_DATA.KEN.units; const n = {}; for (const L of [1, 3, 6]) n[L] = u.filter(x => { const f = x.series[m.live_t].forecast; return f && f[L] && (f[L].p != null || f[L].p_crisis != null || f[L].fews_phase != null); }).length; return { n_months: m.n_months, live_t: m.live_t, units: u.length, withFc: n, sample: u[0].series[m.live_t].forecast && u[0].series[m.live_t].forecast[1] }; });
    console.log(JSON.stringify(meta));
    for (const v of ['f1', 'f3', 'f6']) {
      await page.goto(`${BASE}?role=gov&country=Kenya&t=${meta.live_t}&view=${v}`, { waitUntil: 'load' });
      await page.waitForFunction(() => window.APP && document.querySelector('#clock-date')); await page.waitForTimeout(1500);
      console.log(v, JSON.stringify(await info()));
      await page.screenshot({ path: path.join(__dirname, 'screens', `ken_live_${v}.png`) });
    }
    await browser.close();
  } finally { server.kill(); }
  console.log('JS errors', errs.length, errs.slice(0, 3));
})();
