// Recommendation check: Kenya t=32 shows recommendations in the detail panel and the alert log.
//   node tests/e2e/recommendations.js   (own static server :8820, own Chrome; backend :8821 not needed)
const http = require('http'), fs = require('fs'), path = require('path');
const { chromium } = require('playwright');
const ROOT = path.resolve(__dirname, '..', '..'), PORT = 8820, SCREENS = path.join(__dirname, 'screens');
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml' };
(async () => {
  const srv = http.createServer((req, res) => {
    let p = decodeURIComponent(req.url.split('?')[0]); if (p.endsWith('/')) p += 'index.html';
    const f = path.join(ROOT, p);
    if (!f.startsWith(ROOT) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(f)] || 'application/octet-stream' }); fs.createReadStream(f).pipe(res);
  }).listen(PORT);
  let browser;
  try { browser = await chromium.launch({ channel: 'chrome' }); } catch (_) { browser = await chromium.launch(); }
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource|ERR_/.test(m.text())) errors.push(m.text()); });
  await page.goto(`http://127.0.0.1:${PORT}/index.html`, { waitUntil: 'load' });
  await page.waitForFunction(() => window.RISK_DATA && window.RECS && document.querySelector('#clock-date'));
  const county = await page.evaluate(() => {
    const u = RISK_DATA.KEN.units.find(u => (u.series[32] || {}).level >= 2); return u && u.name;
  });
  await page.goto(`http://127.0.0.1:${PORT}/index.html?country=Kenya&t=32&county=${encodeURIComponent(county)}`, { waitUntil: 'load' });
  await page.waitForSelector('#detail .a-recs', { timeout: 15000 });
  const res = await page.evaluate(() => ({
    detail: document.querySelector('#detail .a-recs').innerText.slice(0, 200),
    label: [...document.querySelectorAll('#detail .d-lab')].map(x => x.innerText),
    logRecs: document.querySelectorAll('#alog-list .a-rec').length,
  }));
  await page.click('#alog-list .a-tg');
  res.expanded = await page.evaluate(() => document.querySelectorAll('#alog-list .a-recs').length);
  await page.screenshot({ path: path.join(SCREENS, 'kenya_t32_recommendations.png') });
  res.county = county; res.errors = errors;
  console.log(JSON.stringify(res, null, 1));
  const ok = /recommended actions/i.test(res.label.join('|')) && res.logRecs > 0 && res.expanded === 1 && !errors.length;
  console.log(ok ? 'PASS' : 'FAIL');
  await browser.close(); srv.close(); process.exit(ok ? 0 : 1);
})();
