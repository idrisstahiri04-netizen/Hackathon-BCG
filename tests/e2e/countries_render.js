// Geometry render check: paints each country's data/geo/<ISO3>.js polygons on the
// globe (no risk data needed) and screenshots it, so winding bugs (one district
// painting the whole globe) are visible before the risk files exist.
//
//   node tests/e2e/countries_render.js [ISO3 ...]
//
// Own static server on :8702, own Chrome. Screenshots -> tests/e2e/screens/countries_geo_<ISO3>.png

const http = require('http');
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..', '..');
const PORT = 8702;
const SCREENS = path.join(__dirname, 'screens');
const VIEW = {
  MOZ: [-18.67, 35.53, 0.60], TZA: [-6.37, 34.89, 0.55], ETH: [9.10, 40.50, 0.55], SOM: [5.15, 46.20, 0.55],
  NAM: [-22.96, 18.49, 0.55], BWA: [-22.33, 24.68, 0.50], ZAF: [-30.56, 22.94, 0.60], MDG: [-18.77, 46.87, 0.55],
  AGO: [-11.20, 17.87, 0.55], UGA: [1.37, 32.29, 0.40],
};
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.json': 'application/json' };

(async () => {
  const isos = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(VIEW);
  fs.mkdirSync(SCREENS, { recursive: true });
  const srv = http.createServer((req, res) => {
    let p = decodeURIComponent(req.url.split('?')[0]); if (p.endsWith('/')) p += 'index.html';
    const file = path.join(ROOT, p);
    if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream' });
    fs.createReadStream(file).pipe(res);
  });
  await new Promise(ok => srv.listen(PORT, '127.0.0.1', ok));
  let browser;
  try { browser = await chromium.launch({ channel: 'chrome', headless: true }); }
  catch (e) { browser = await chromium.launch({ headless: true }); }
  const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'load' });
  await page.waitForFunction(() => window.GEO_DATA && window.APP && window.APP.world);
  await page.waitForTimeout(800);
  const out = {};
  for (const iso of isos) {
    const [lat, lng, alt] = VIEW[iso];
    out[iso] = await page.evaluate(([iso, lat, lng, alt]) => {
      const geo = window.GEO_DATA[iso]; if (!geo) return { ok: false, why: 'no GEO_DATA' };
      const w = window.APP.world;
      w.controls().autoRotate = false;
      w.polygonsData(geo.features)
        .polygonCapColor(() => 'rgba(255,170,0,0.75)')
        .polygonSideColor(() => 'rgba(255,170,0,0.15)')
        .polygonStrokeColor(() => '#222')
        .polygonAltitude(0.006);
      w.pointOfView({ lat, lng, altitude: alt }, 0);
      return { ok: true, n: geo.features.length, nopop: geo.features.filter(f => f.properties.pop == null).length };
    }, [iso, lat, lng, alt]);
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(SCREENS, `countries_geo_${iso}.png`) });
  }
  // Whole-globe view: a winding bug shows as a painted hemisphere.
  await page.evaluate(() => { window.APP.world.pointOfView({ lat: 0, lng: 25, altitude: 2.3 }, 0); });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(SCREENS, 'countries_geo_world.png') });
  console.log(JSON.stringify({ out, errors }));
  await browser.close(); srv.close();
})().catch(e => { console.error(e); process.exit(1); });
