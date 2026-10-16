// Country coverage check for the globe (14 countries).
//
//   node tests/e2e/countries.js            # one pass
//   node tests/e2e/countries.js --poll     # re-run every 10 min (max 2 h) until all 14 are LIVE
//
// Starts its own static server on :8701 (repo root) and its own Chrome
// (channel "chrome", falls back to bundled Chromium). Does not touch :8777/:8000.
// Checks: every country is searchable, the 4 main ones are LIVE, each other
// country is LIVE exactly when data/geo/<ISO3>.js and a real data/risk/<ISO3>.js
// exist, HUD shows the declaration or "no national declaration in replay window",
// 0 uncaught JS errors. Screenshots -> tests/e2e/screens/countries_*.png.
// Results -> tests/e2e/countries_results.json.

const http = require('http');
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..', '..');
const PORT = 8701;
const BASE = `http://127.0.0.1:${PORT}/`;
const SCREENS = path.join(__dirname, 'screens');
const MAIN = ['ZWE', 'KEN', 'MWI', 'ZMB'];
const COUNTRIES = [
  ['Zimbabwe', 'ZWE'], ['Kenya', 'KEN'], ['Malawi', 'MWI'], ['Zambia', 'ZMB'],
  ['Mozambique', 'MOZ'], ['Tanzania', 'TZA'], ['Ethiopia', 'ETH'], ['Somalia', 'SOM'],
  ['Namibia', 'NAM'], ['Botswana', 'BWA'], ['South Africa', 'ZAF'], ['Madagascar', 'MDG'],
  ['Angola', 'AGO'], ['Uganda', 'UGA'],
];
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };

function serve() {
  const srv = http.createServer((req, res) => {
    let p = decodeURIComponent(req.url.split('?')[0]);
    if (p.endsWith('/')) p += 'index.html';
    const file = path.join(ROOT, p);
    if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404); res.end('not found'); return;
    }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream' });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((ok, bad) => srv.listen(PORT, '127.0.0.1', () => ok(srv)).on('error', bad));
}

// A risk file counts as real when it exists and meta.model_version is not STUB.
function onDisk(iso) {
  const geo = fs.existsSync(path.join(ROOT, 'data', 'geo', `${iso}.js`));
  const rp = path.join(ROOT, 'data', 'risk', `${iso}.js`);
  let risk = false;
  if (fs.existsSync(rp)) {
    const head = fs.readFileSync(rp, { encoding: 'utf8' }).slice(0, 4000);
    const m = head.match(/"model_version":\s*"([^"]*)"/);
    risk = !!(m && m[1].toUpperCase() !== 'STUB');
  }
  return { geo, risk, expectLive: geo && risk };
}

async function onePass(browser) {
  const res = { startedAt: new Date().toISOString(), countries: {}, pageErrors: [], consoleErrors: [], resourceErrors: [] };
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on('pageerror', e => res.pageErrors.push(e.message));
  page.on('console', m => {
    if (m.type() !== 'error') return;
    const txt = m.text() + ' ' + (m.location().url || '');
    (/Failed to load resource/.test(txt) ? res.resourceErrors : res.consoleErrors).push(txt);
  });
  await page.goto(BASE, { waitUntil: 'load' });
  await page.waitForFunction(() => window.GEO_DATA && window.RISK_DATA && document.querySelector('#clock-date'));
  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(SCREENS, 'countries_00_globe.png') });

  for (const [name, iso] of COUNTRIES) {
    const disk = onDisk(iso);
    await page.fill('#search', '');
    await page.click('#search');
    await page.fill('#search', name);
    await page.waitForTimeout(150);
    const rows = await page.locator('#results li').evaluateAll(lis => lis.map(li => ({
      name: li.dataset.name, tag: (li.querySelector('.tag') || {}).textContent || '' })));
    const hit = rows.find(r => r.name === name);
    const tag = hit ? hit.tag.trim() : null;
    const r = { searchable: !!hit, tag, disk, pass: false };
    if (hit) {
      await page.keyboard.press('Enter');
      await page.waitForTimeout(1800);              // camera flight
      r.hud = (await page.textContent('#hud-sub')).trim();
      r.loaded = await page.evaluate(iso => ({
        geo: !!(window.GEO_DATA || {})[iso], risk: !!(window.RISK_DATA || {})[iso],
        polys: (window.APP && window.APP.world) ? window.APP.world.polygonsData().length : null,
        decl: ((window.RISK_DATA || {})[iso] || { meta: {} }).meta.declaration || null,
      }), iso);
      await page.screenshot({ path: path.join(SCREENS, `countries_${iso}.png`) });
      const live = tag === 'Live';
      const hudOk = !live || (r.loaded.decl ? /disaster declared/.test(r.hud) : /no national declaration in replay window/.test(r.hud));
      r.pass = live === disk.expectLive && (!live || r.loaded.polys === r.loaded.geoN || r.loaded.polys > 0) && hudOk
        && (!MAIN.includes(iso) || live);
      r.live = live;
    }
    res.countries[iso] = r;
  }
  await page.close();
  res.liveCount = Object.values(res.countries).filter(c => c.live).length;
  res.allSearchable = Object.values(res.countries).every(c => c.searchable);
  res.mainLive = MAIN.every(iso => res.countries[iso].live);
  res.allPass = Object.values(res.countries).every(c => c.pass) && res.pageErrors.length === 0;
  return res;
}

(async () => {
  const poll = process.argv.includes('--poll');
  fs.mkdirSync(SCREENS, { recursive: true });
  const srv = await serve();
  let browser;
  try { browser = await chromium.launch({ channel: 'chrome', headless: true }); }
  catch (e) { console.error('chrome channel unavailable, using bundled chromium:', e.message.split('\n')[0]); browser = await chromium.launch({ headless: true }); }
  const t0 = Date.now();
  const history = [];
  try {
    for (;;) {
      const r = await onePass(browser);
      history.push({ at: r.startedAt, live: Object.entries(r.countries).filter(([, c]) => c.live).map(([k]) => k), pass: r.allPass, pageErrors: r.pageErrors.length });
      r.history = history;
      fs.writeFileSync(path.join(__dirname, 'countries_results.json'), JSON.stringify(r, null, 1));
      console.log(`[${r.startedAt}] live ${r.liveCount}/14: ${history[history.length - 1].live.join(' ')} | searchable ${res_ok(r.allSearchable)} main ${res_ok(r.mainLive)} pass ${res_ok(r.allPass)} pageErrors ${r.pageErrors.length} consoleErrors ${r.consoleErrors.length}`);
      if (!poll || r.liveCount === 14 || Date.now() - t0 > 2 * 3600e3) break;
      await new Promise(ok => setTimeout(ok, 10 * 60e3));
    }
  } finally {
    await browser.close();
    srv.close();
  }
})().catch(e => { console.error(e); process.exit(1); });

function res_ok(b) { return b ? 'ok' : 'FAIL'; }
