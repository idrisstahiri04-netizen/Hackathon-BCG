// Shared helpers for the Chrome UI tests (ui_matrix.js, ui_a11y.js, ui_perf.js).
// Uses our OWN servers: static UI on :8401, SMS backend on :8402 (temp DB, GATEWAY=sim).
// Nothing here touches the shared 8000/8777 processes or js/config.local.js: the
// operator key is injected by intercepting the request for js/config.local.js.
'use strict';
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const UI = process.env.UI_BASE || 'http://127.0.0.1:8401/';
const API_ON = process.env.UI_API || 'http://localhost:8402';
const API_OFF = process.env.UI_API_OFF || 'http://localhost:8403';   // nothing listens here
const API_KEY = process.env.UI_API_KEY || 'uitest-admin-key-8402';
const SCREENS = path.join(__dirname, 'screens');
const REPO = path.resolve(__dirname, '..', '..');
fs.mkdirSync(SCREENS, { recursive: true });

const VIEWPORTS = [
  { w: 1920, h: 1080, name: 'desktop' },
  { w: 1440, h: 900, name: 'laptop' },
  { w: 1280, h: 720, name: 'projector' },
  { w: 390, h: 844, name: 'phone' },
  { w: 768, h: 1024, name: 'tablet' },
];

// 5 months per country: declaration month, the months around it, a peak month and a wet (0 % Warning+) month.
const COUNTRIES = {
  ZWE: { name: 'Zimbabwe', months: [0, 27, 62, 63, 65], decl: 63 },
  KEN: { name: 'Kenya', months: [5, 22, 32, 48, 65], decl: 32 },
  MWI: { name: 'Malawi', months: [17, 30, 38, 62, 63], decl: 62 },
  ZMB: { name: 'Zambia', months: [4, 37, 45, 61, 64], decl: 61 },
};

function loadRisk(iso) {
  const src = fs.readFileSync(path.join(REPO, 'data', 'risk', `${iso}.js`), 'utf8');
  const tag = `RISK_DATA["${iso}"] = `;
  let s = src.slice(src.indexOf(tag) + tag.length).trim();
  if (s.endsWith(';')) s = s.slice(0, -1);
  return JSON.parse(s);
}
// The unit with the highest level (then highest p) in month t: the one worth opening in the panel.
function worstUnit(iso, t) {
  const R = loadRisk(iso);
  let best = null;
  for (const u of R.units) {
    const r = u.series[t];
    if (!r) continue;
    if (!best || r.level > best.r.level || (r.level === best.r.level && (r.p || 0) > (best.r.p || 0))) best = { u, r };
  }
  return best ? best.u.name : null;
}

async function launch(extraArgs = []) {
  return chromium.launch({
    channel: 'chrome', headless: true,
    args: ['--enable-unsafe-swiftshader', ...extraArgs],
  });
}

// A context with error collection and the config.local.js override.
async function newPage(browser, { w, h, dpr = 1, online = true } = {}) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: dpr });
  const page = await ctx.newPage();
  const errors = { js: [], console: [], net: [] };
  page.on('pageerror', e => errors.js.push(String(e.message)));
  page.on('console', m => {
    if (m.type() !== 'error') return;
    const txt = m.text() + ' @ ' + (m.location().url || '');
    (/ERR_CONNECTION_REFUSED|Failed to load resource|net::/.test(txt) ? errors.net : errors.console).push(txt);
  });
  page.on('requestfailed', r => errors.net.push(`${r.failure() && r.failure().errorText} ${r.url()}`));
  const api = online ? API_ON : API_OFF;
  await page.route('**/js/config.local.js', route => route.fulfill({
    status: 200, contentType: 'application/javascript',
    body: `window.SMS_API_BASE = ${JSON.stringify(api)};\n${online ? `window.SMS_API_KEY = ${JSON.stringify(API_KEY)};\n` : ''}`,
  }));
  page.errors = errors;
  page.apiBase = api;
  return page;
}

function appUrl(params = {}, online = true) {
  const q = new URLSearchParams(params);
  q.set('api', online ? API_ON : API_OFF);
  return `${UI}?${q.toString()}`;
}

async function gotoApp(page, params = {}, { online = true, settle = 1500 } = {}) {
  const t0 = Date.now();
  await page.goto(appUrl(params, online), { waitUntil: 'load' });
  await page.waitForFunction(() => window.APP && window.RISK_DATA && document.querySelector('#clock-date'), null, { timeout: 30000 });
  const ready = Date.now() - t0;
  if (settle) await page.waitForTimeout(settle);
  return ready;
}

async function shot(page, name) {
  const file = path.join(SCREENS, `${name}.png`);
  await page.screenshot({ path: file, fullPage: false });
  return path.basename(file);
}

// ---- Layout audit (runs in the page) ---------------------------------------
// Returns bounding boxes of the main regions, overlaps between regions that must
// never overlap, elements clipped by the viewport, text overflow, and min font size.
async function layoutAudit(page, { mobile = false } = {}) {
  return page.evaluate((mobile) => {
    const vw = window.innerWidth, vh = window.innerHeight;
    const vis = e => {
      if (!e || e.hidden) return false;
      const cs = getComputedStyle(e);
      if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0) return false;
      const r = e.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    };
    const box = sel => {
      const e = document.querySelector(sel);
      if (!vis(e)) return null;
      const r = e.getBoundingClientRect();
      return { x: +r.left.toFixed(1), y: +r.top.toFixed(1), w: +r.width.toFixed(1), h: +r.height.toFixed(1), r: +r.right.toFixed(1), b: +r.bottom.toFixed(1) };
    };
    const REGIONS = ['#tabs', '#search-wrap', '#hud', '#hud-country', '#hud-stats', '#legend', '#detail', '#feed-col', '#feed-head', '#timeline',
      '#play', '#track-wrap', '#clock', '#run-alerts', '#speeds', '#disclaimer', '#empty-hint', '#be-status', '#live-toast',
      '#view-switch', '#view-cap', '#top10', '#top10-list', '#go-today', '#legend-note', '#today-mark',
      '.live-page:not([hidden])', '.live-page:not([hidden]) .lp-head', '#phone', '#ph-quick', '#counters'];
    const boxes = {};
    for (const s of REGIONS) { const b = box(s); if (b) boxes[s] = b; }
    const inter = (a, b, tol = 1) => a && b && a.x < b.r - tol && b.x < a.r - tol && a.y < b.b - tol && b.y < a.b - tol;
    const area = (a, b) => Math.max(0, Math.min(a.r, b.r) - Math.max(a.x, b.x)) * Math.max(0, Math.min(a.b, b.b) - Math.max(a.y, b.y));
    // Pairs that must never overlap. On phones the unit panel is a bottom sheet
    // over the feed by design, so those pairs are skipped there.
    const PAIRS = [
      ['#search-wrap', '#hud'], ['#search-wrap', '#detail'], ['#hud-country', '#hud-stats'],
      ['#hud', '#legend'], ['#hud', '#feed-col'], ['#hud', '#timeline'],
      ['#detail', '#legend'], ['#detail', '#feed-col'], ['#detail', '#hud'], ['#detail', '#timeline'], ['#detail', '#disclaimer'],
      ['#legend', '#feed-col'], ['#legend', '#timeline'], ['#legend', '#disclaimer'],
      ['#disclaimer', '#feed-col'], ['#disclaimer', '#timeline'],
      ['#feed-col', '#timeline'], ['#tabs', '#search-wrap'], ['#tabs', '#hud'], ['#tabs', '#feed-col'],
      ['#play', '#track-wrap'], ['#track-wrap', '#clock'], ['#clock', '#run-alerts'], ['#clock', '#speeds'], ['#run-alerts', '#speeds'], ['#play', '#clock'],
      ['#empty-hint', '#legend'], ['#empty-hint', '#search-wrap'],
      // Forecast view switch (top-right under the HUD; bottom-right on phones) and Top 10 / Go-to-today additions.
      ['#view-switch', '#hud'], ['#view-switch', '#hud-stats'], ['#view-switch', '#hud-country'], ['#view-switch', '#detail'],
      ['#view-switch', '#search-wrap'], ['#view-switch', '#legend'], ['#view-switch', '#feed-col'], ['#view-switch', '#timeline'], ['#view-switch', '#disclaimer'],
      ['#view-cap', '#detail'], ['#view-cap', '#legend'],
      ['#hud-stats', '#feed-col'], ['#hud-stats', '#search-wrap'], ['#hud-country', '#feed-col'],
      ['#go-today', '#clock'], ['#go-today', '#run-alerts'], ['#go-today', '#speeds'], ['#go-today', '#track-wrap'], ['#go-today', '#play'],
    ];
    const skipMobile = new Set(['#detail|#feed-col', '#detail|#legend', '#detail|#hud', '#detail|#disclaimer']);
    const overlaps = [];
    for (const [a, b] of PAIRS) {
      if (mobile && skipMobile.has(`${a}|${b}`)) continue;
      if (inter(boxes[a], boxes[b])) overlaps.push({ a, b, px: Math.round(area(boxes[a], boxes[b])) });
    }
    // Clipped by the viewport.
    const clipped = [];
    for (const [s, b] of Object.entries(boxes)) {
      if (s === '#track-wrap' || s === '#spark') continue;
      if (b.x < -1 || b.y < -1 || b.r > vw + 1 || b.b > vh + 1) clipped.push({ sel: s, box: b });
    }
    // Timeline children must sit inside the timeline bar.
    const tl = boxes['#timeline'];
    if (tl) for (const s of ['#play', '#clock', '#run-alerts', '#speeds', '#track-wrap', '#go-today']) {
      const b = boxes[s]; if (!b) continue;
      if (b.y < tl.y - 1 || b.b > tl.b + 1 || b.x < tl.x - 1 || b.r > tl.r + 1) clipped.push({ sel: s, box: b, by: '#timeline', parent: tl });
    }
    // Text overflow in single-line / fixed boxes.
    const TEXT = ['#hud-name', '#hud-sub', '.stat-lab', '.stat-val', '#clock-date', '#clock-sub', '#feed-sub', '#feed-head h2', '#legend li', '#legend .ct',
      '.d-head h3', '.d-head .sub', '.chip', '.n-date', '.n-county', '#tabs [role=tab]', '#be-status', '.lp-head h2', '.lp-sub', '.al-unit', '.ctr-val', '.ctr-lab',
      '#run-alerts', '#disclaimer', '#decl-mark span', '.fam .fn', '.fam .fv', '#detail', '.sms', '.d-pm .unit', '#tabs', '#timeline', '.ph-quick button', '.bubble', '.c-saved',
      '.vs-row button', '#view-cap', '#top10-list li', '.t10-title', '#top10-sub', '#go-today', '.fc-lab', '.fc-big', '#legend .legend-title', '#today-mark span'];
    const overflow = [];
    for (const s of TEXT) for (const e of document.querySelectorAll(s)) {
      if (!vis(e)) continue;
      const cs = getComputedStyle(e);
      const scrollable = /auto|scroll/.test(cs.overflowY) || /auto|scroll/.test(cs.overflowX);
      const ox = e.scrollWidth - e.clientWidth, oy = e.scrollHeight - e.clientHeight;
      if ((ox > 2 && !/auto|scroll/.test(cs.overflowX)) || (oy > 2 && !scrollable && cs.overflow !== 'visible' && cs.overflowY !== 'visible')) {
        overflow.push({ sel: s, text: (e.textContent || '').trim().slice(0, 40), ox, oy, w: e.clientWidth });
      }
    }
    // Minimum rendered font size among visible text, plus the offenders < 10px.
    let minFont = 99; const tiny = {};
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walker.nextNode())) {
      if (!n.textContent.trim()) continue;
      const e = n.parentElement; if (!e || !vis(e) || e.closest('[aria-hidden="true"]') || e.closest('[hidden]')) continue;
      const fs = parseFloat(getComputedStyle(e).fontSize);
      if (fs < minFont) minFont = fs;
      if (fs < 10) { const k = (e.id ? '#' + e.id : e.className ? '.' + String(e.className).split(' ')[0] : e.tagName) + '@' + fs; tiny[k] = (tiny[k] || 0) + 1; }
    }
    // Globe canvas size vs container (resize handling).
    const g = document.querySelector('#globe'), c = document.querySelector('#globe canvas');
    const canvas = g && c ? { el: [g.clientWidth, g.clientHeight], canvas: [c.clientWidth, c.clientHeight], ok: Math.abs(g.clientWidth - c.clientWidth) <= 2 && Math.abs(g.clientHeight - c.clientHeight) <= 2 } : null;
    // Horizontal page scroll should never appear.
    const hscroll = document.documentElement.scrollWidth > vw + 1;
    // #hud-stats is a flex child; when the HUD gets narrow it overflows its parent box (clipped under the feed column).
    const hs = boxes['#hud-stats'], hb = boxes['#hud'];
    if (hs && hb && (hs.r > hb.r + 1 || hs.b > hb.b + 1)) clipped.push({ sel: '#hud-stats', box: hs, by: '#hud', parent: hb });
    return { vw, vh, boxes, overlaps, clipped, overflow, minFont, tiny, canvas, hscroll,
      view: (document.querySelector('#view-switch .on') || {}).dataset ? document.querySelector('#view-switch .on').dataset.view : null,
      hud: (document.querySelector('#hud-name') || {}).textContent, clock: (document.querySelector('#clock-date') || {}).textContent,
      detailOpen: !!(document.querySelector('#detail') && !document.querySelector('#detail').hidden),
      beStatus: (document.querySelector('#be-status .be-lab') || {}).textContent };
  }, mobile);
}

function saveJSON(name, data) {
  const file = path.join(__dirname, name);
  fs.writeFileSync(file, JSON.stringify(data, null, 1));
  return file;
}

module.exports = { UI, API_ON, API_OFF, API_KEY, SCREENS, VIEWPORTS, COUNTRIES, loadRisk, worstUnit, launch, newPage, appUrl, gotoApp, shot, layoutAudit, saveJSON };
