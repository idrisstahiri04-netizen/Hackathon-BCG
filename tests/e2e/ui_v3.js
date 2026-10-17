// UI v3 check: Map + Alert log, Users add/delete, no Phone tab, 0 JS errors.
// Own servers: static :8805, backend :8806 (temp DB). Start them first (see bottom of file).
'use strict';
const path = require('path');
const { chromium } = require('playwright');
const UI = 'http://127.0.0.1:8805/', API = 'http://127.0.0.1:8806', KEY = 'v3-test-key';
const OUT = path.join(__dirname, 'screens');
(async () => {
  const b = await chromium.launch({ channel: 'chrome', headless: true });
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = [], fails = [];
  p.on('pageerror', e => errs.push(String(e)));
  p.on('console', m => { if (m.type() === 'error' && !/favicon|ERR_CONNECTION|status of 422/.test(m.text())) errs.push(m.text()); });
  await p.route('**/js/config.local.js', r => r.fulfill({ contentType: 'text/javascript',
    body: `window.SMS_API_BASE=${JSON.stringify(API)};window.SMS_API_KEY=${JSON.stringify(KEY)};` }));
  const ck = (n, ok) => { console.log(ok ? 'ok  ' : 'FAIL', n); if (!ok) fails.push(n); };
  await p.goto(UI + '?country=Zimbabwe&t=63', { waitUntil: 'load' });
  await p.waitForSelector('#alog-list .alog-row', { timeout: 15000 });
  const rows = await p.locator('#alog-list .alog-row').count();
  ck(`alert log rows (${rows})`, rows > 0 && rows <= 300);
  ck('no Top 10', (await p.locator('#top10').count()) === 0);
  ck('no Run alerts button', (await p.locator('#run-alerts').count()) === 0);
  ck('no Phone tab', (await p.locator('[data-page=phone]').count()) === 0 && (await p.locator('#page-phone').count()) === 0);
  await p.screenshot({ path: path.join(OUT, 'ui_v3_map_alert_log.png') });
  await p.click('#alog-chips [data-f=month]');
  ck('This month filter', (await p.locator('#alog-list .alog-row').count()) <= rows);
  await p.click('#alog-chips [data-f=warn]');
  await p.locator('#alog-list .alog-row').first().click();
  await p.waitForTimeout(500);
  await p.screenshot({ path: path.join(OUT, 'ui_v3_map_row_click.png') });
  await p.click('[data-page=users]');
  await p.waitForSelector('#u-district option', { state: 'attached', timeout: 5000 });
  await p.fill('#u-name', 'Test Farmer');
  await p.fill('#u-phone', '+263771555001');
  await p.selectOption('#u-role', 'herder');
  await p.click('#u-add');
  await p.waitForSelector('#users-body tr', { timeout: 5000 });
  ck('user added', (await p.locator('#users-body tr').count()) === 1 && /Test Farmer/.test(await p.locator('#users-body').innerText()));
  await p.fill('#u-phone', '12345');
  await p.click('#u-add');
  await p.waitForTimeout(500);
  ck('bad phone rejected', /Phone must/.test(await p.locator('#u-err').innerText()));
  await p.screenshot({ path: path.join(OUT, 'ui_v3_users.png') });
  p.once('dialog', d => d.accept());
  await p.click('#users-body .row-btn.danger');
  await p.waitForFunction(() => document.querySelectorAll('#users-body tr').length === 0, null, { timeout: 5000 });
  ck('user deleted', true);
  ck('0 JS errors', errs.length === 0);
  if (errs.length) console.log(errs.slice(0, 5));
  await b.close();
  process.exit(fails.length ? 1 : 0);
})();
// servers:
//   python3 -m http.server 8805 --bind 127.0.0.1   (repo root)
//   SCHEDULER=off GATEWAY=sim ADMIN_TOKEN=v3-test-key DB_PATH=/tmp/v3.db uvicorn backend.app:app --port 8806
