'use strict';
const fs = require('fs'), path = require('path'), http = require('http');
const { spawn } = require('child_process');
const { chromium } = require('playwright');
const PORT = 8810, BASE = `http://127.0.0.1:${PORT}/`, REPO = path.resolve(__dirname, '..', '..');
const SCREENS = path.join(__dirname, 'screens');
const tag = 'RISK_DATA["KEN"] = ';
const src = fs.readFileSync(path.join(REPO, 'data/risk/KEN.js'), 'utf8');
const R = JSON.parse(src.slice(src.indexOf(tag) + tag.length).trim().replace(/;$/, ''));
const waitPort = () => new Promise((res, rej) => { const t0 = Date.now(); (function k() { http.get({ host: '127.0.0.1', port: PORT, path: '/' }, r => { r.resume(); res(); }).on('error', () => Date.now() - t0 > 8000 ? rej() : setTimeout(k, 150)); })(); });
(async () => {
  const server = spawn('python3', ['-m', 'http.server', String(PORT), '--bind', '127.0.0.1'], { cwd: REPO, stdio: 'ignore' });
  const out = []; const errs = [];
  try {
    await waitPort();
    const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--enable-unsafe-swiftshader'] });
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    page.on('pageerror', e => errs.push(String(e.message)));
    page.on('console', m => { if (m.type() === 'error' && !/ERR_CONNECTION_REFUSED|Failed to load resource|net::|Failed to fetch/.test(m.text())) errs.push(m.text()); });
    await page.route('**/js/config.local.js', r => r.fulfill({ status: 200, contentType: 'application/javascript', body: 'window.SMS_API_BASE="http://127.0.0.1:8805";' }));
    for (const t of [30, 32, 88, 92]) for (const view of ['now', 'f1', 'f3', 'f6']) for (const layer of (view === 'now' ? ['model'] : ['model', 'fews'])) {
      await page.goto(`${BASE}?country=Kenya&t=${t}&view=${view}&layer=${layer}`, { waitUntil: 'load' });
      await page.waitForFunction(() => window.RISK_DATA && window.GEO_DATA && document.querySelector('#clock-date') && window.APP);
      await page.waitForTimeout(1500);
      const s = await page.evaluate(() => ({
        clock: document.querySelector('#clock-date').textContent,
        stat: document.querySelector('#stat-units').textContent, statColor: getComputedStyle(document.querySelector('#stat-units')).color,
        legend: [...document.querySelectorAll('#legend-items li')].filter(li => !li.hidden && !li.classList.contains('lg-group')).map(li => li.textContent.trim().replace(/\s+/g, ' ')),
        sum: [...document.querySelectorAll('#legend-items li .ct')].map(x => +x.textContent).reduce((a, b) => a + b, 0),
        note: [...document.querySelectorAll('.vc-note,#legend-note:not([hidden]),.fc-note')].map(x => x.textContent),
      }));
      const L = view === 'now' ? 0 : +view.slice(1);
      let exp = null;
      if (L) { const k = layer === 'fews' ? 'fews_phase' : null;
        exp = { none: R.units.filter(u => { const f = u.series[t].forecast && u.series[t].forecast[L]; return !f || (k ? f[k] == null : (f.p_crisis == null && f.p == null)); }).length }; }
      out.push({ t, view, layer, ...s, exp });
      await page.screenshot({ path: path.join(SCREENS, `ken_gaps_t${t}_${view}_${layer}.png`) });
    }
    await browser.close();
  } finally { server.kill(); }
  fs.writeFileSync(path.join(__dirname, 'ken_gaps_results.json'), JSON.stringify({ errs, out }, null, 1));
  console.log('JS errors', errs.length, errs.slice(0, 3));
  for (const o of out) console.log(o.t, o.view, o.layer, o.stat, o.statColor, 'sum', o.sum, 'expNone', o.exp && o.exp.none, '|', o.legend.join(' / ').slice(0, 150), '|', o.note.join(' ; ').slice(0, 130));
})();
