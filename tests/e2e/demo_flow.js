#!/usr/bin/env node
/* Stage rehearsal: follows docs/demo_script.md end to end against an ISOLATED stack.
 *
 *   node tests/e2e/demo_flow.js [--runs 3] [--headed] [--keep]
 *
 * Per run it starts its own backend (uvicorn, port 8201, temp SQLite DB, GATEWAY=sim, own
 * ADMIN_TOKEN) and its own static server (port 8202), seeds backend/seed_demo.py and
 * backend/seed_crowd.py --district Hwange, drives Chrome (channel "chrome", fallback bundled
 * chromium) through the demo click path, times every step, screenshots each step to
 * tests/e2e/screens/demo_r<run>_<nn>_<step>.png, counts console/page errors, then shuts its
 * servers down. Nothing on 8000/8777 is touched. Results: tests/e2e/demo_results.json.
 */
'use strict';
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const http = require('http');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const PY = fs.existsSync('/home/looooo/bcg/.venv/bin/python') ? '/home/looooo/bcg/.venv/bin/python' : 'python3';
const UVICORN = fs.existsSync('/home/looooo/bcg/.venv/bin/uvicorn') ? '/home/looooo/bcg/.venv/bin/uvicorn' : 'uvicorn';
const API_PORT = +(process.env.E2E_API_PORT || 8201);
const UI_PORT = +(process.env.E2E_UI_PORT || 8202);
const API = `http://localhost:${API_PORT}`;
const UI = `http://localhost:${UI_PORT}`;
const SCREENS = path.join(__dirname, 'screens');
const args = process.argv.slice(2);
const RUNS = +(args[args.indexOf('--runs') + 1] || 0) || (args.includes('--runs') ? 3 : 3);
const HEADED = args.includes('--headed');
const KEEP = args.includes('--keep');
const DISTRICT = 'Hwange';
const T_START = 57, T_WATCH = 62, T_DEMO = 63, T_CLOSE = 66;
const PHONE = '+263770000001';
const GSM_TIMEOUT = 25000;

fs.mkdirSync(SCREENS, { recursive: true });

// ---- GSM 03.38 measure (same table as js/app.js smsCost / backend/composer.py) --------------
const BASIC = new Set(('@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !"#¤%&\'()*+,-./0123456789:;<=>?' +
  '¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà').split(''));
const EXT = new Set('^{}\\[~]|€\f'.split(''));
function measure(t) {
  const chars = [...t];
  const gsm = chars.every(c => BASIC.has(c) || EXT.has(c));
  const n = gsm ? chars.reduce((s, c) => s + (EXT.has(c) ? 2 : 1), 0) : chars.length;
  return { gsm, n, segs: gsm ? (n <= 160 ? 1 : Math.ceil(n / 153)) : (n <= 70 ? 1 : Math.ceil(n / 67)) };
}

// ---- stack --------------------------------------------------------------------------------
const sleep = ms => new Promise(r => setTimeout(r, ms));
function getJson(url, headers = {}) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, { headers }, res => {
      let b = ''; res.on('data', d => (b += d)); res.on('end', () => { try { resolve({ status: res.statusCode, json: JSON.parse(b) }); } catch (e) { resolve({ status: res.statusCode, json: null, body: b }); } });
    });
    req.on('error', reject);
  });
}
async function waitHealth(url, ms = 30000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    try { const r = await getJson(url); if (r.status === 200) return r.json; } catch (_) {}
    await sleep(300);
  }
  throw new Error(`no answer from ${url} after ${ms} ms`);
}
function portFree(port) {
  return new Promise(resolve => {
    const s = http.createServer().listen(port, '127.0.0.1');
    s.on('listening', () => s.close(() => resolve(true)));
    s.on('error', () => resolve(false));
  });
}

async function startStack(run) {
  if (!(await portFree(API_PORT)) || !(await portFree(UI_PORT))) {
    throw new Error(`port ${API_PORT} or ${UI_PORT} busy; another e2e stack is running (never kill 8000/8777)`);
  }
  const dbPath = `/tmp/e2e_demo_r${run}_${process.pid}.db`;
  for (const s of ['', '-shm', '-wal']) try { fs.unlinkSync(dbPath + s); } catch (_) {}
  const token = 'e2e-' + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
  const env = { ...process.env, DB_PATH: dbPath, GATEWAY: 'sim', ADMIN_TOKEN: token, LLM_WARMUP: '1' };
  const logPath = `/tmp/e2e_demo_r${run}_backend.log`;
  const logFd = fs.openSync(logPath, 'w');
  const be = spawn(UVICORN, ['backend.app:app', '--host', '127.0.0.1', '--port', String(API_PORT)],
    { cwd: ROOT, env, stdio: ['ignore', logFd, logFd] });
  const ui = spawn('python3', ['-m', 'http.server', String(UI_PORT), '--bind', '127.0.0.1'],
    { cwd: ROOT, stdio: 'ignore' });
  const health = await waitHealth(`${API}/health`);
  await waitHealth(`${UI}/index.html`).catch(() => {}); // static server answers HTML, not JSON: ignore parse
  // seed exactly like the pre-demo checklist (+ crowd demo reports in the demo district)
  for (const mod of [['backend.seed_demo'], ['backend.seed_crowd', '--district', DISTRICT]]) {
    const r = spawnSync(PY, ['-m', ...mod], { cwd: ROOT, env, encoding: 'utf8' });
    if (r.status !== 0) throw new Error(`${mod.join(' ')} failed: ${r.stderr}`);
  }
  return { be, ui, token, dbPath, logPath, health };
}
function stopStack(st) {
  if (!st) return;
  for (const p of [st.be, st.ui]) { try { p.kill('SIGTERM'); } catch (_) {} }
  if (!KEEP) for (const s of ['', '-shm', '-wal']) try { fs.unlinkSync(st.dbPath + s); } catch (_) {}
}

// ---- browser ------------------------------------------------------------------------------
async function launch() {
  const opts = { headless: !HEADED, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] };
  try { return { browser: await chromium.launch({ ...opts, channel: 'chrome' }), channel: 'chrome' }; }
  catch (e) { console.warn('chrome channel unavailable, falling back to bundled chromium:', e.message.split('\n')[0]); return { browser: await chromium.launch(opts), channel: 'chromium' }; }
}

// ---- one rehearsal ------------------------------------------------------------------------
async function rehearse(run, browser, st) {
  const steps = [];
  const consoleErrors = [], pageErrors = [];
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  // The shared js/config.local.js (other testers' token) must not leak in: serve our own.
  await ctx.route('**/js/config.local.js', route => route.fulfill({ contentType: 'application/javascript',
    body: `window.SMS_API_BASE=${JSON.stringify(API)};window.SMS_API_KEY=${JSON.stringify(st.token)};` }));
  await ctx.addInitScript(([api, key]) => { window.SMS_API_BASE = api; window.SMS_API_KEY = key; }, [API, st.token]);
  const page = await ctx.newPage();
  page.on('pageerror', e => pageErrors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push(`${m.text()} @ ${m.location().url || ''}:${m.location().lineNumber || ''}`); });

  let n = 0;
  const shot = async name => { const f = path.join(SCREENS, `demo_r${run}_${String(++n).padStart(2, '0')}_${name}.png`); await page.screenshot({ path: f }); return path.relative(ROOT, f); };
  async function step(name, fn) {
    const t0 = Date.now();
    const rec = { step: name, pass: false, ms: 0, note: '' };
    try {
      const out = await fn(rec);
      rec.pass = out !== false;
      if (out && typeof out === 'object') Object.assign(rec, out);
    } catch (e) {
      rec.pass = false; rec.error = String(e.message || e).split('\n')[0];
    }
    rec.ms = Date.now() - t0;
    try { rec.shot = await shot(name.replace(/[^a-z0-9]+/gi, '_').toLowerCase()); } catch (_) {}
    steps.push(rec);
    console.log(`  ${rec.pass ? 'PASS' : 'FAIL'} ${String(rec.ms).padStart(6)} ms  ${name}${rec.error ? '  -- ' + rec.error : ''}${rec.note ? '  (' + rec.note + ')' : ''}`);
    return rec;
  }
  const themTexts = () => page.$$eval('#ph-thread .ph-msg.them .ph-txt', ns => ns.map(x => x.textContent));
  // Send one SMS from the on-screen phone and wait for the next reply bubble. Returns reply + latency.
  async function sms(text, pred, timeout = GSM_TIMEOUT) {
    const before = (await themTexts()).length;
    await page.fill('#ph-text', text);
    const resp = page.waitForResponse(r => r.url().endsWith('/sim/inbound') && r.request().method() === 'POST', { timeout });
    const t0 = Date.now();
    await page.click('#ph-send');
    const r = await resp;
    const apiMs = Date.now() - t0;
    const body = await r.json().catch(() => ({}));
    await page.waitForFunction(([b, src]) => {
      const t = [...document.querySelectorAll('#ph-thread .ph-msg.them:not(.thinking) .ph-txt')].map(x => x.textContent);
      return t.length > b && (!src || new RegExp(src, 'i').test(t[t.length - 1]));
    }, [before, pred ? pred.source : null], { timeout, polling: 100 });
    const latency = Date.now() - t0;
    const all = await themTexts();
    return { reply: all[all.length - 1], latency, apiMs, intent: body.intent, confidence: body.intent_confidence, source: body.parsed && body.parsed.source };
  }
  const openUrl = async q => {
    await page.goto(`${UI}/?${q}&api=${encodeURIComponent(API)}`, { waitUntil: 'load' });
    await page.waitForFunction(() => window.GEO_DATA && window.RISK_DATA && window.APP && document.querySelector('#clock-date'));
    await page.waitForSelector('#be-status.up', { timeout: 15000, polling: 100 });
    await page.waitForTimeout(1800); // camera fly-in
  };

  // 0:00 globe
  await step('globe loads', async rec => {
    await page.goto(`${UI}/?api=${encodeURIComponent(API)}`, { waitUntil: 'load' });
    await page.waitForFunction(() => window.GEO_DATA && window.RISK_DATA && window.APP && document.querySelector('#globe canvas'));
    await page.waitForSelector('#be-status.up', { timeout: 15000, polling: 100 });
    const lab = await page.textContent('#be-status .be-lab');
    const hint = await page.textContent('#empty-hint');
    rec.note = lab.trim();
    if (!/backend online/.test(lab) || /no admin key/.test(lab)) throw new Error(`status bar: ${lab}`);
    if (!/Live:.*Zimbabwe/.test(hint)) throw new Error(`Zimbabwe not listed live: ${hint}`);
    const focused = await page.evaluate(() => document.activeElement && document.activeElement.id);
    if (focused !== 'search') rec.note += ' · search box NOT focused';
  });

  await step('search Zimbabwe', async rec => {
    await page.fill('#search', 'Zimbabwe');
    await page.waitForSelector('#results li[role=option]');
    const tag = await page.textContent('#results li[role=option] .tag');
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.querySelector('#hud-name').textContent === 'Zimbabwe', null, { polling: 100 });
    await page.waitForTimeout(2500); // camera fly-in (1500 ms tween, slower under software GL)
    const sub = await page.textContent('#hud-sub');
    rec.note = `${tag} · ${sub}`;
    if (tag.trim() !== 'Live') throw new Error(`tag ${tag}`);
    if (!/^91 districts · disaster declared 3 Apr 2024/.test(sub)) throw new Error(`hud-sub: ${sub}`);
    const clock = await page.textContent('#clock-date');
    if (clock !== 'Jan 2019') throw new Error(`clock ${clock}`);
  });

  const counts = {};
  const readCounts = async () => page.evaluate(() => {
    const c = {}; [...document.querySelectorAll('#legend-items li')].forEach(li => { c['L' + li.dataset.level] = +li.querySelector('.ct').textContent; });
    return { clock: document.querySelector('#clock-date').textContent, warnPlus: +document.querySelector('#stat-units').textContent, ...c };
  });

  await step('slider to Oct 2023 (t=57)', async rec => {
    await page.locator('#scrub').fill(String(T_START));
    await page.waitForTimeout(500);
    counts.t57 = await readCounts();
    rec.note = JSON.stringify(counts.t57);
    if (counts.t57.clock !== 'Oct 2023') throw new Error(counts.t57.clock);
    rec.scriptSays = '13 Watch, 0 Warning';
    rec.matchesScript = counts.t57.L1 === 13 && counts.t57.warnPlus === 0;
  });

  await step('play 2x to Mar 2024 (t=62), pause', async rec => {
    await page.click('#speeds [data-speed="2"]');
    await page.evaluate(() => document.activeElement && document.activeElement.blur());
    const t0 = Date.now();
    await page.keyboard.press('Space');
    // 5 months at 2x = 5 x 475 ms. Poll on a timer, not rAF: under software GL frames can take
    // longer than a month, so the clock may skip straight past Mar 2024 between frames.
    await page.waitForFunction(t => +document.querySelector('#scrub').value >= t, T_WATCH, { timeout: 15000, polling: 50 });
    await page.keyboard.press('Space');
    const playMs = Date.now() - t0;
    await page.waitForTimeout(600);
    let v = +(await page.inputValue('#scrub'));
    const landed = v;
    // Driver recovery: step back with the arrow keys if the pause overshot
    for (let i = 0; i < 12 && v !== T_WATCH; i++) { await page.keyboard.press(v > T_WATCH ? 'ArrowLeft' : 'ArrowRight'); await page.waitForTimeout(150); v = +(await page.inputValue('#scrub')); }
    await page.waitForTimeout(400);
    counts.t62 = await readCounts();
    rec.ms_per_month = Math.round(playMs / (T_WATCH - T_START));
    rec.landed_t = landed;
    rec.note = `play ${playMs} ms (${rec.ms_per_month} ms/month, nominal 475) · paused at t=${landed}${landed !== T_WATCH ? ' OVERSHOOT, recovered with arrows' : ''} · ${JSON.stringify(counts.t62)}`;
    if (v !== T_WATCH || counts.t62.clock !== 'Mar 2024') throw new Error(`could not land on t=62 (at ${v})`);
    rec.scriptSays = '22 Watch, 4 Warning (Mbire, Karoi, Rushinga at Watch)';
    rec.matchesScript = counts.t62.L1 === 22 && counts.t62.warnPlus === 4;
    if (landed !== T_WATCH) rec.warn = `pause overshot to t=${landed}: at ${rec.ms_per_month} ms/month the machine cannot keep 2x`;
  });

  await step('arrow right to Apr 2024 (t=63)', async rec => {
    await page.keyboard.press('ArrowRight');
    await page.waitForTimeout(600);
    counts.t63 = await readCounts();
    rec.note = JSON.stringify(counts.t63);
    if (counts.t63.clock !== 'Apr 2024') throw new Error(counts.t63.clock);
    rec.scriptSays = '26 Warning';
    rec.matchesScript = counts.t63.warnPlus === 26;
  });

  let row63;
  await step(`click ${DISTRICT} on the globe`, async rec => {
    // click where globe.gl projects the district centroid; fall back to the deep-link path if occluded
    const box = await page.locator('#globe').boundingBox();
    const pt = await page.evaluate(name => {
      const f = GEO_DATA.ZWE.features.find(x => x.properties.name === name).properties;
      const c = APP.world.getScreenCoords(f.lat, f.lng, 0.02);
      return { x: c.x, y: c.y, lat: f.lat, lng: f.lng };
    }, DISTRICT);
    await page.mouse.move(box.x + pt.x, box.y + pt.y);
    await page.waitForTimeout(250);
    await page.mouse.click(box.x + pt.x, box.y + pt.y);
    await page.waitForTimeout(700);
    let name = await page.evaluate(() => (document.querySelector('#detail h3') || {}).textContent || null);
    if (name !== DISTRICT) {
      rec.note = `globe click hit "${name}" at (${pt.x | 0},${pt.y | 0}); used feed-note fallback`;
      // same code path a Driver would use: click the Hwange notification in the feed
      const note = page.locator(`#feed .note[data-county="${DISTRICT}"]`).first();
      if (await note.count()) { await note.click(); await page.waitForTimeout(1200); }
      name = await page.evaluate(() => (document.querySelector('#detail h3') || {}).textContent || null);
      if (name !== DISTRICT) throw new Error(`panel shows ${name}`);
      return { clickedOnGlobe: false };
    }
    return { clickedOnGlobe: true, note: `hit at (${pt.x | 0},${pt.y | 0})` };
  });

  await step('district panel: drivers, families, held, p, p_crisis', async rec => {
    const d = await page.evaluate(() => {
      const d = document.querySelector('#detail');
      return {
        hidden: d.hidden, name: d.querySelector('h3').textContent, sub: d.querySelector('.sub').textContent,
        evt: (d.querySelector('.sub .evt') || {}).textContent, chip: d.querySelector('.chip').textContent,
        big: [...d.querySelectorAll('.big')].map(x => x.textContent), units: [...d.querySelectorAll('.unit')].map(x => x.textContent),
        held: !!d.querySelector('.held'), fams: [...d.querySelectorAll('.fam')].map(f => ({ k: f.querySelector('.fn').textContent, hit: f.classList.contains('hit') })),
        drivers: [...d.querySelectorAll('ul.drivers li')].map(x => x.textContent.replace(/^\d+/, '')),
        tabs: [...d.querySelectorAll('.aud-tabs button')].map(b => b.textContent), crowd: (d.querySelector('.crowd-sect') || {}).textContent,
      };
    });
    row63 = await page.evaluate(([name, t]) => RISK_DATA.ZWE.units.find(u => u.name === name).series[t], [DISTRICT, T_DEMO]);
    rec.note = `${d.chip} · ${d.evt} · p ${d.big[0]} · ${d.big[1]} · drivers ${d.drivers.length} · p_crisis ${row63.p_crisis}`;
    const bad = [];
    if (d.hidden || d.name !== DISTRICT) bad.push('panel');
    if (!/Apr 2024/.test(d.sub)) bad.push('month');
    if (d.evt !== 'No grass') bad.push(`event ${d.evt}`);
    if (!/L2 WARNING/.test(d.chip)) bad.push(`chip ${d.chip}`);
    if (d.big[0] !== `${Math.round(row63.p * 100)}%`) bad.push(`p ${d.big[0]} vs ${row63.p}`);
    if (d.held || row63.held) bad.push('held shown (script: not held)');
    if (d.big[1] !== `${row63.agreeing}/3` || !/high confidence/.test(d.units[1])) bad.push(`agree ${d.big[1]} ${d.units[1]}`);
    const hits = d.fams.filter(f => f.hit).map(f => f.k);
    if (!['Rain', 'Green', 'Soil'].every(k => hits.includes(k))) bad.push(`families ${hits}`);
    if (d.drivers.length !== 3 || !d.drivers.some(x => /grazing land greenness/.test(x))) bad.push(`drivers ${d.drivers}`);
    if (!d.tabs.includes('Herders') || d.tabs.includes('Farmers')) bad.push(`tabs ${d.tabs}`);
    if (!/Crowd reports/.test(d.crowd || '')) bad.push('no crowd section');
    rec.drivers = d.drivers; rec.p = row63.p; rec.p_crisis = row63.p_crisis;
    if (bad.length) throw new Error(bad.join('; '));
  });

  await step('Herders tab: SMS preview one segment', async rec => {
    await page.click('.aud-tabs button:text-is("Herders")');
    const text = await page.textContent('#detail .sms');
    const meta = await page.textContent('#detail .sms-meta');
    const m = measure(text);
    rec.sms = text; rec.note = `${m.n} septets · ${meta.replace(/\s+/g, ' ')}`;
    if (!m.gsm || m.n > 160 || m.segs !== 1) throw new Error(`not one GSM-7 segment: ${JSON.stringify(m)}`);
    if (!/Sell weak animals/.test(text) || /%/.test(text) || !/^WARNING Hwange/.test(text)) throw new Error(`herder text: ${text}`);
    if (!/1 segment\b/.test(meta) || !/GSM-7/.test(meta) || !new RegExp(`\\b${m.n} septets`).test(meta)) throw new Error(`meta: ${meta}`);
    // NGO tab is the one with the number (p_crisis)
    await page.click('.aud-tabs button:text-is("NGOs & funds")');
    const ngo = await page.textContent('#detail .sms');
    rec.ngo_sms = ngo;
    if (row63.p_crisis != null && !ngo.includes(`${Math.round(row63.p_crisis * 100)}%`)) throw new Error(`NGO text lacks p_crisis: ${ngo}`);
    if (measure(ngo).segs !== 1) throw new Error('NGO text > 1 segment');
    await page.click('.aud-tabs button:text-is("Herders")');
  });

  await step('Phone tab: JOIN Hwange herder', async rec => {
    await page.click('#tabs [data-page="phone"]');
    await page.waitForSelector('#page-phone:not([hidden])');
    await page.fill('#ph-number', PHONE);
    const r = await sms(`JOIN ${DISTRICT} herder`, /Reply YES to confirm/);
    rec.latency_ms = r.latency; rec.api_ms = r.apiMs; rec.reply = r.reply; rec.note = `${r.latency} ms (backend ${r.apiMs} ms, ${r.source})`;
    if (!new RegExp(`Join drought alerts for ${DISTRICT} as herder`).test(r.reply)) throw new Error(r.reply);
  });

  await step('Phone: YES confirms sign-up', async rec => {
    const r = await sms('YES', /registered for Hwange \(herder\)/);
    rec.latency_ms = r.latency; rec.api_ms = r.apiMs; rec.reply = r.reply; rec.note = `${r.latency} ms (backend ${r.apiMs} ms, ${r.source})`;
    if (!/1 ok 2 poor 3 bad/.test(r.reply)) throw new Error(r.reply);
  });

  let created;
  await step('Map: Run alerts for Apr 2024', async rec => {
    await page.click('#tabs [data-page="map"]');
    const clock = await page.textContent('#clock-date');
    if (clock !== 'Apr 2024') throw new Error(`clock ${clock}`);
    const btn = page.locator('#run-alerts');
    if (await btn.isHidden() || await btn.isDisabled()) throw new Error('Run alerts button hidden/disabled');
    const t0 = Date.now();
    await btn.click();
    await page.waitForSelector('#live-toast:not([hidden])', { timeout: 35000, polling: 100 });
    const toast = await page.textContent('#live-toast');
    rec.note = `${Date.now() - t0} ms · ${toast}`;
    const m = toast.match(/^(\d+) alert event/);
    if (!m) throw new Error(`toast: ${toast}`);
    created = +m[1];
    const badge = await page.textContent('#badge-alerts');
    rec.pending_badge = +badge;
  });

  let hwRow;
  await step('Alert feed: Hwange Warning pending approval', async rec => {
    await page.click('#tabs [data-page="alerts"]');
    await page.waitForSelector('#page-alerts:not([hidden])');
    hwRow = page.locator('#alerts-list li.al-row', { has: page.locator(`.al-unit:text-is("${DISTRICT}")`) });
    await hwRow.waitFor({ timeout: 10000, polling: 100 });
    const info = await hwRow.evaluate(li => ({ chip: li.querySelector('.chip').textContent, evt: (li.querySelector('.evt') || {}).textContent,
      month: (li.querySelector('.al-month') || {}).textContent, status: li.querySelector('.al-status').textContent, sent: (li.querySelector('.al-sent') || {}).textContent,
      drivers: li.querySelectorAll('.n-drivers li').length, approve: !!li.querySelector('button.approve') }));
    rec.note = `${info.chip} · ${info.evt} · ${info.month} · ${info.status} · ${info.sent}`;
    if (!/L2 WARNING/.test(info.chip) || info.evt !== 'No grass' || info.status !== 'Waiting for approval' || !info.approve || info.month !== 'Apr 2024') throw new Error(JSON.stringify(info));
    rec.n_rows = await page.locator('#alerts-list li.al-row').count();
    rec.crowd_rows = await page.locator('#alerts-list li.al-row.crowd').count();
  });

  let approveAt;
  await step('Approve & send Hwange only', async rec => {
    approveAt = Date.now();
    await hwRow.locator('button.approve').click();
    await page.waitForFunction(name => {
      const li = [...document.querySelectorAll('#alerts-list li.al-row')].find(x => (x.querySelector('.al-unit') || {}).textContent === name);
      return li && li.querySelector('.al-status').textContent === 'Sent';
    }, DISTRICT, { timeout: 35000, polling: 100 });
    const li = page.locator('#alerts-list li.al-row', { has: page.locator(`.al-unit:text-is("${DISTRICT}")`) });
    const foot = await li.locator('.al-foot').textContent();
    rec.note = `${Date.now() - approveAt} ms · ${foot.replace(/\s+/g, ' ').trim()}`;
    const m = foot.match(/sent to (\d+) user/);
    if (!m || +m[1] < 1) throw new Error(foot);
    if (/failed/.test(foot)) throw new Error(foot);
    const others = await page.locator('#alerts-list li.al-row .al-status:text-is("Waiting for approval")').count();
    rec.still_pending = others;
    if (others === 0) throw new Error('no other event left pending: approve hit more than Hwange?');
  });

  let warning;
  await step('Phone receives Warning SMS', async rec => {
    await page.click('#tabs [data-page="phone"]');
    await page.waitForFunction(() => [...document.querySelectorAll('#ph-thread .ph-msg.them .ph-txt')].some(x => /^WARNING Hwange/.test(x.textContent)), null, { timeout: 15000, polling: 100 });
    const lat = Date.now() - approveAt;
    warning = (await themTexts()).find(x => /^WARNING Hwange/.test(x));
    const m = measure(warning);
    const meta = await page.locator('#ph-thread .ph-msg.them', { hasText: 'WARNING Hwange' }).locator('.ph-meta').textContent();
    rec.sms = warning; rec.latency_from_approve_ms = lat; rec.note = `${lat} ms after approve · ${m.n} septets · ${meta.trim()}`;
    if (!m.gsm || m.n > 160 || m.segs !== 1) throw new Error(`segments ${JSON.stringify(m)}`);
    if (/%/.test(warning) || !/Sell weak animals early/.test(warning)) throw new Error(`herder action missing or % present: ${warning}`);
    if (!/sent \(simulator\)/.test(meta)) throw new Error(`delivery meta: ${meta}`);
    if (lat > 15000) throw new Error('15-second rule broken');
  });

  await step('Reply: how do I save my cattle? -> livestock advice', async rec => {
    const r = await sms('how do I save my cattle?');
    rec.latency_ms = r.latency; rec.api_ms = r.apiMs; rec.reply = r.reply; rec.confidence = r.confidence;
    const m = measure(r.reply);
    const meta = await page.locator('#ph-thread .ph-msg.me', { hasText: 'how do I save my cattle?' }).locator('.ph-meta').textContent();
    rec.note = `${r.latency} ms (backend ${r.apiMs} ms) · ${m.n} septets · intent ${meta.split('·').pop().trim()} conf ${r.confidence}`;
    if (!/ask_advice/.test(meta)) throw new Error(`intent ${meta}`);
    if (!/(animal|cattle|herd|breeding|livestock|water)/i.test(r.reply) || /did not understand|no advice/i.test(r.reply)) throw new Error(`not livestock advice: ${r.reply}`);
    if (!m.gsm || m.segs !== 1) throw new Error('advice > 1 segment');
  });

  await step('Reply: 3 -> grazing report saved', async rec => {
    const r = await sms('3', /saved for Hwange/);
    rec.latency_ms = r.latency; rec.api_ms = r.apiMs; rec.reply = r.reply; rec.note = `${r.latency} ms (backend ${r.apiMs} ms, ${r.source})`;
    if (!/Grazing and animals report 'bad'/.test(r.reply)) throw new Error(r.reply);
  });

  await step('Map: crowd badge + crowd-confirmed in panel', async rec => {
    const t0 = Date.now();
    await page.click('#tabs [data-page="map"]');
    // crowd poll every 5 s; the panel re-renders through APP.repaint
    await page.waitForFunction(name => {
      const b = [...document.querySelectorAll('.crowd-badge')].find(x => (x.title || '').startsWith(name + ':'));
      return b && b.classList.contains('confirmed') && b.querySelector('.n').textContent === '5';
    }, DISTRICT, { timeout: 12000, polling: 100 });
    const badge = await page.evaluate(name => { const b = [...document.querySelectorAll('.crowd-badge')].find(x => (x.title || '').startsWith(name + ':')); return { cls: b.className, title: b.title, n: b.querySelector('.n').textContent }; }, DISTRICT);
    const panel = await page.evaluate(() => { const s = document.querySelector('#detail .crowd-sect'); return s ? { line: s.querySelector('.crowd-line').textContent, rule: s.querySelector('.crowd-rule').textContent, cls: s.querySelector('.crowd-rule').className, mark: !!s.querySelector('.crowd-mark') } : null; });
    rec.note = `${Date.now() - t0} ms · badge "${badge.title}" · panel "${panel && panel.rule}"`;
    if (!panel) throw new Error('detail panel closed');
    if (!/3 of 5 say failed/.test(badge.title) || !/3 of 5 say failed/.test(panel.line)) throw new Error(`${badge.title} / ${panel.line}`);
    if (!/crowd-confirmed/.test(panel.rule) || !panel.mark || !/st-confirms/.test(panel.cls)) throw new Error(`rule: ${panel.rule} ${panel.cls}`);
    if (!/4 demo/.test(panel.line)) rec.note += ' · demo tag missing';
    // Alert feed row for the crowd report
    await page.click('#tabs [data-page="alerts"]');
    const crow = page.locator('#alerts-list li.al-row.crowd', { hasText: `crowd report: ${DISTRICT}` });
    await crow.waitFor({ timeout: 6000, polling: 100 });
    const ctext = await crow.textContent();
    rec.crowd_row = ctext.replace(/\s+/g, ' ').trim();
    if (!/3 of 5 say failed/.test(ctext) || !/crowd-confirmed/.test(ctext)) throw new Error(`crowd row: ${rec.crowd_row}`);
    await page.click('#tabs [data-page="map"]');
    await page.waitForTimeout(300);
  });

  await step('Reply: We can\'t manage -> ask_help', async rec => {
    await page.click('#tabs [data-page="phone"]');
    const r = await sms("We can't manage");
    const meta = await page.locator('#ph-thread .ph-msg.me', { hasText: "We can't manage" }).locator('.ph-meta').textContent();
    rec.latency_ms = r.latency; rec.api_ms = r.apiMs; rec.reply = r.reply; rec.confidence = r.confidence; rec.note = `${r.latency} ms (backend ${r.apiMs} ms) · intent ${meta.split('·').pop().trim()} conf ${r.confidence}`;
    if (!/ask_help/.test(meta) || !/officer will contact you/i.test(r.reply)) throw new Error(`${meta} / ${r.reply}`);
  });

  await step('Users joining shows sign-up with Claude understood', async rec => {
    await page.click('#tabs [data-page="users"]');
    await page.waitForSelector('#page-users:not([hidden])');
    const head = await page.$$eval('#join-table thead th', ths => ths.map(t => t.textContent));
    if (!head.includes('Claude understood')) throw new Error(`headers ${head}`);
    const tr = page.locator('#join-body tr', { has: page.locator(`.bubble:text-is("JOIN ${DISTRICT} herder")`) });
    await tr.waitFor({ timeout: 8000, polling: 100 });
    const rowInfo = tr => ({ intent: (tr.querySelector('.intent') || {}).textContent, conf: (tr.querySelector('.conf-n') || {}).textContent,
      saved: tr.querySelector('.c-saved').textContent, phone: tr.querySelector('.c-phone').textContent });
    const info = await tr.evaluate(rowInfo);
    const yes = await page.locator('#join-body tr', { has: page.locator('.bubble:text-is("YES")') }).first().evaluate(rowInfo);
    const ctr = await page.evaluate(() => ({ total: document.querySelector('#ctr-total').textContent, today: document.querySelector('#ctr-today').textContent,
      herders: (document.querySelector('#ctr-roles [data-role="herder"] .ctr-val') || {}).textContent }));
    rec.join_row = info; rec.yes_row = yes;
    rec.note = `JOIN row: ${info.intent} ${info.conf} saved "${info.saved}" · YES row: saved "${yes.saved}" · ${info.phone} · subscribers ${ctr.total}, today ${ctr.today}, herders ${ctr.herders}`;
    if (info.intent !== 'subscribe') throw new Error(JSON.stringify(info));
    if (!/Hwange · herder · English/.test(yes.saved)) throw new Error(`sign-up not shown as saved: ${JSON.stringify(yes)}`);
    if (/\*\*\*\*/.test(info.phone) && !/•••/.test(info.phone)) throw new Error(`phone masked by backend (admin key not sent): ${info.phone}`);
    // Known cosmetic bug: the JOIN row keeps "not saved yet" after YES because the inbound JOIN
    // message was logged before the user row existed (user_id NULL) and js/live.js:372 only
    // looks users up by m.user_id (usersByPhone is built at :338 but never used here).
    if (/not saved yet/.test(info.saved)) rec.bug = 'JOIN row stays "not saved yet (asked to confirm)" after YES (js/live.js:372, :398)';
  });

  await step('close: scrub to Jul 2024 (t=66)', async rec => {
    await page.click('#tabs [data-page="map"]');
    await page.locator('#scrub').fill(String(T_CLOSE));
    await page.waitForTimeout(600);
    counts.t66 = await readCounts();
    const hw = await page.evaluate(([name, t]) => RISK_DATA.ZWE.units.find(u => u.name === name).series[t].level, [DISTRICT, T_CLOSE]);
    rec.note = `${JSON.stringify(counts.t66)} · Hwange L${hw}`;
    rec.scriptSays = 'Hwange back to Normal at t=66; 33 Warning+';
    rec.matchesScript = hw === 0 && counts.t66.warnPlus === 33;
    if (counts.t66.clock !== 'Jul 2024') throw new Error(counts.t66.clock);
    await page.keyboard.press('Escape');
    if (!(await page.locator('#detail').isHidden())) throw new Error('esc did not close the panel');
  });

  // Deep links (Tab 2) - stage insurance
  const links = [
    ['country=Zimbabwe&t=57', { clock: 'Oct 2023' }],
    ['country=Zimbabwe&t=62', { clock: 'Mar 2024' }],
    ['country=Zimbabwe&t=63', { clock: 'Apr 2024' }],
    ['country=Zimbabwe&t=63&county=Hwange', { clock: 'Apr 2024', county: 'Hwange', tab: 'Herders' }],
    ['country=Zimbabwe&t=62&county=Mbire', { clock: 'Mar 2024', county: 'Mbire' }],
    ['country=Zimbabwe&t=66', { clock: 'Jul 2024' }],
  ];
  for (const [q, exp] of links) {
    await step(`deep link ?${q}`, async rec => {
      await openUrl(q);
      const c = await readCounts();
      const hud = await page.textContent('#hud-name');
      const d = await page.evaluate(() => { const d = document.querySelector('#detail'); return d.hidden ? null : { name: d.querySelector('h3').textContent, chip: d.querySelector('.chip').textContent, tabs: [...d.querySelectorAll('.aud-tabs button')].map(b => b.textContent), big: [...d.querySelectorAll('.big')].map(x => x.textContent) }; });
      rec.note = `${JSON.stringify(c)}${d ? ` · panel ${d.name} ${d.chip} ${d.big.join(' ')} tabs[${d.tabs}]` : ''}`;
      if (hud !== 'Zimbabwe' || c.clock !== exp.clock) throw new Error(`${hud} ${c.clock}`);
      if (exp.county && (!d || d.name !== exp.county)) throw new Error(`panel ${d && d.name}`);
      if (exp.tab && !d.tabs.includes(exp.tab)) throw new Error(`tabs ${d.tabs}`);
      if (!exp.county && d) throw new Error('panel open without county param');
    });
  }

  await ctx.close();
  return { steps, consoleErrors, pageErrors, counts, created };
}

// ---- main ---------------------------------------------------------------------------------
(async () => {
  const results = { started_at: new Date().toISOString(), api: API, ui: UI, runs: [] };
  let st = null, browser = null, channel = null;
  const cleanup = () => { stopStack(st); if (browser) browser.close().catch(() => {}); };
  process.on('SIGINT', () => { cleanup(); process.exit(130); });
  try {
    ({ browser, channel } = await launch());
    results.browser = `${channel} ${browser.version()}`;
    console.log(`browser: ${results.browser}`);
    for (let run = 1; run <= RUNS; run++) {
      console.log(`\n=== run ${run}/${RUNS} ===`);
      const t0 = Date.now();
      st = await startStack(run);
      console.log(`  stack up: backend ${API} (db ${st.dbPath}, gateway ${st.health.gateway}, llm ${st.health.llm}), ui ${UI}`);
      let r;
      try { r = await rehearse(run, browser, st); }
      catch (e) { r = { steps: [], fatal: String(e.stack || e) }; console.error('  FATAL', e); }
      r.run = run; r.total_ms = Date.now() - t0; r.db = st.dbPath; r.backend_log = st.logPath;
      r.js_errors = (r.consoleErrors || []).length + (r.pageErrors || []).length;
      console.log(`  console errors: ${(r.consoleErrors || []).length}, page errors: ${(r.pageErrors || []).length}, total ${r.total_ms} ms`);
      results.runs.push(r);
      stopStack(st); st = null;
      await sleep(500);
    }
  } finally { cleanup(); }
  // flakiness: steps that did not pass in every run
  const names = [...new Set(results.runs.flatMap(r => r.steps.map(s => s.step)))];
  results.summary = names.map(name => {
    const recs = results.runs.map(r => r.steps.find(s => s.step === name)).filter(Boolean);
    const ms = recs.map(s => s.ms);
    return { step: name, pass: recs.filter(s => s.pass).length, of: recs.length, ms_min: Math.min(...ms), ms_max: Math.max(...ms),
      flaky: recs.some(s => s.pass) && recs.some(s => !s.pass), errors: [...new Set(recs.filter(s => !s.pass).map(s => s.error))] };
  });
  fs.writeFileSync(path.join(__dirname, 'demo_results.json'), JSON.stringify(results, null, 2));
  console.log('\n=== summary ===');
  for (const s of results.summary) console.log(`  ${s.pass}/${s.of} ${s.flaky ? 'FLAKY ' : ''}${String(s.ms_min).padStart(6)}-${String(s.ms_max).padEnd(6)} ms  ${s.step}${s.errors.length ? '  -- ' + s.errors.join(' | ') : ''}`);
  console.log(`results: ${path.relative(ROOT, path.join(__dirname, 'demo_results.json'))}`);
  const allPass = results.summary.every(s => s.pass === s.of) && results.runs.every(r => r.js_errors === 0 && !r.fatal);
  process.exit(allPass ? 0 : 1);
})().catch(e => { console.error(e); process.exit(2); });
