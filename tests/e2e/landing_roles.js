// Landing -> Government -> Kenya map -> orange county -> gov actions; switch to NGO -> NGO actions. Port 8840.
'use strict';
const http = require('http'), fs = require('fs'), path = require('path');
const { chromium } = require('playwright');
const ROOT = path.resolve(__dirname, '../..'), SCREENS = path.join(__dirname, 'screens'), PORT = 8840;
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.gif': 'image/gif', '.svg': 'image/svg+xml' };
const srv = http.createServer((q, r) => {
  let f = path.join(ROOT, decodeURIComponent(q.url.split('?')[0])); if (f.endsWith('/')) f += 'index.html';
  fs.readFile(f, (e, d) => { if (e) { r.writeHead(404); return r.end(); } r.writeHead(200, { 'content-type': MIME[path.extname(f)] || 'application/octet-stream' }); r.end(d); });
});
const ok = (c, m) => { if (!c) { console.error('FAIL', m); process.exitCode = 1; } else console.log('ok  ', m); };
(async () => {
  fs.mkdirSync(SCREENS, { recursive: true });
  await new Promise(r => srv.listen(PORT, r));
  let b; try { b = await chromium.launch({ channel: 'chrome' }); } catch (_) { b = await chromium.launch(); }
  const pg = await (await b.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; pg.on('pageerror', e => errs.push(e.message)); pg.on('console', m => m.type() === 'error' && !/Failed to load resource|8000|fetch/i.test(m.text()) && errs.push(m.text()));
  await pg.goto(`http://localhost:${PORT}/`, { waitUntil: 'domcontentloaded' });
  await pg.waitForSelector('#landing:not([hidden])');
  await pg.waitForTimeout(800);
  ok((await pg.getAttribute('#land-logo', 'src')).includes('typing'), 'typing logo first');
  await pg.screenshot({ path: path.join(SCREENS, 'landing_1_typing.png') });
  await pg.waitForFunction(() => document.getElementById('land-logo').src.includes('mapema.gif'), null, { timeout: 8000 });
  ok(true, 'loop logo took over');
  await pg.screenshot({ path: path.join(SCREENS, 'landing_2_loop.png') });
  await pg.click('[data-pick=gov]');
  await pg.waitForFunction(() => document.querySelector('#hud-name') && document.querySelector('#hud-name').textContent === 'Kenya', null, { timeout: 20000 });
  ok(pg.url().includes('role=gov') && await pg.evaluate(() => localStorage.getItem('mapema_role')) === 'gov', 'role in URL + localStorage');
  // find an orange/red month with log rows
  await pg.click('#alog-chips [data-f=warn]');
  let row = null;
  for (const t of [92, 100, 60, 80, 110, 70, 120]) {
    await pg.evaluate(t => { const s = document.getElementById('scrub'); s.value = t; s.dispatchEvent(new Event('input', { bubbles: true })); }, t);
    await pg.waitForTimeout(500);
    row = await pg.$('#alog-list .alog-row:has(.a-rec b)');
    if (row) break;
  }
  ok(!!row, 'orange/red log row exists');
  const txtGov = await row.innerText();
  ok(/Do:/.test(txtGov), 'gov log shows Do: line');
  await (await row.$('.a-tg')).click();
  const logGov = await row.innerText();
  ok(/Who:.*\n?.*When:/s.test(logGov) && /Evidence:/.test(logGov) && /Source:/.test(logGov), 'gov log expanded: who/when/evidence/source');
  await row.click({ position: { x: 20, y: 8 } });
  await pg.waitForSelector('#detail:not([hidden]) .d-role');
  const det = await pg.innerText('#detail');
  ok(/government: (prepare|respond)/i.test(det) && /(Activate|Declare)/.test(det) && !/Pre-position/i.test(det), 'detail shows government actions only');
  ok(!/message each audience/i.test(det), 'gov hides SMS preview');
  await pg.screenshot({ path: path.join(SCREENS, 'landing_3_gov_detail.png') });
  await pg.click('#role-switch [data-role=ngo]');
  await pg.waitForFunction(() => /ngo \/ food bank: /i.test(document.getElementById('detail').innerText));
  const det2 = await pg.innerText('#detail');
  ok(/(Target|Start)/.test(det2) && !/Declare|Activate/.test(det2) && /message each audience/i.test(det2), 'NGO actions + SMS preview');
  await pg.screenshot({ path: path.join(SCREENS, 'landing_4_ngo_detail.png') });
  ok(errs.length === 0, '0 JS errors ' + errs.join(' | '));
  await b.close(); srv.close();
})().catch(e => { console.error(e); process.exit(1); });
