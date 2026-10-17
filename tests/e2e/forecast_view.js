// Forecast view checks (horizon Now | +1 … +8, layer Our model | FEWS NET |
// Both, unit panel chart with FEWS steps, Top 10, TODAY marker, deep links,
// keys F / L / 0-8) in headless Chrome via Node Playwright.
// Starts its OWN static server on :8803 and its own browser; never touches
// the shared :8777 / :8000 processes. The SMS backend is pointed at a dead
// port so js/live.js runs "offline" (its connection errors are not JS errors).
//
//   node tests/e2e/forecast_view.js          -> tests/e2e/forecast_results.json
//                                               tests/e2e/screens/forecast_*.png
'use strict';
const fs = require('fs');
const path = require('path');
const http = require('http');
const { spawn } = require('child_process');
const { chromium } = require('playwright');

const PORT = 8803;
const BASE = `http://127.0.0.1:${PORT}/`;
const DEAD_API = 'http://127.0.0.1:8805';
const REPO = path.resolve(__dirname, '..', '..');
const SCREENS = path.join(__dirname, 'screens');
fs.mkdirSync(SCREENS, { recursive: true });

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const lab = t => `${MON[t % 12]} ${2019 + Math.floor(t / 12)}`;

function loadRisk(iso) {
  const src = fs.readFileSync(path.join(REPO, 'data', 'risk', `${iso}.js`), 'utf8');
  const tag = `RISK_DATA["${iso}"] = `;
  let s = src.slice(src.indexOf(tag) + tag.length).trim();
  if (s.endsWith(';')) s = s.slice(0, -1);
  return JSON.parse(s);
}
// Same reading of the contract as js/real.js forecastAt (chance = p_crisis ?? p).
const fcOf = (row, lead) => {
  const f = row.forecast && row.forecast[String(lead)];
  if (f) return { chance: f.p_crisis != null ? f.p_crisis : f.p, phase: f.fews_phase ?? null };
  if (lead <= 3) return { chance: row.p_crisis != null ? row.p_crisis : (lead === 1 ? row.p : null), phase: null };
  return { chance: null, phase: null };
};

const waitPort = (port, ms = 8000) => new Promise((res, rej) => {
  const t0 = Date.now();
  (function tick() {
    const req = http.get({ host: '127.0.0.1', port, path: '/' }, r => { r.resume(); res(); });
    req.on('error', () => Date.now() - t0 > ms ? rej(new Error('server not up')) : setTimeout(tick, 150));
  })();
});

async function main() {
  const server = spawn('python3', ['-m', 'http.server', String(PORT), '--bind', '127.0.0.1'], { cwd: REPO, stdio: 'ignore' });
  const results = { pass: true, checks: {}, errors: { js: [], console: [] } };
  const check = (name, ok, info) => { results.checks[name] = { pass: !!ok, ...(info !== undefined ? { info } : {}) }; if (!ok) results.pass = false; };
  let browser;
  try {
    await waitPort(PORT);
    browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--enable-unsafe-swiftshader'] });

    const R = loadRisk('ZWE');
    const NU = R.units.length, NM = R.meta.n_months, LIVE_T = R.meta.live_t ?? null;
    const thr = (R.meta.metrics && R.meta.metrics.p_crisis && R.meta.metrics.p_crisis.watch_threshold) || 0.57;
    let maxModelLead = 0, hasFews = false;
    for (const u of R.units) for (const r of u.series) if (r.forecast) for (const k of Object.keys(r.forecast)) {
      const f = r.forecast[k]; if (f && (f.p != null || f.p_crisis != null)) maxModelLead = Math.max(maxModelLead, +k); if (f && f.fews_phase != null) hasFews = true;
    }
    const hot = (t, L) => R.units.filter(u => { const v = fcOf(u.series[t], L).chance; return v != null && v >= thr; }).length;
    const noneAt = (t, L) => R.units.filter(u => fcOf(u.series[t], L).chance == null).length;
    const ranked = t => R.units.map(u => ({ n: u.name, v: Math.max(...[1, 2, 3].map(L => fcOf(u.series[t], L).chance ?? -1)) }))
      .filter(x => x.v >= 0).sort((a, b) => b.v - a.v || a.n.localeCompare(b.n));
    results.data = { n_units: NU, n_months: NM, live_t: LIVE_T, thr, maxModelLead, hasFews, hot3_oct2023: hot(57, 3), hot3_feb2024: hot(61, 3), top_feb2024: ranked(61).slice(0, 3) };

    async function newPage(w, h) {
      const ctx = await browser.newContext({ viewport: { width: w, height: h } });
      const page = await ctx.newPage();
      page.on('pageerror', e => results.errors.js.push(String(e.message)));
      page.on('console', m => {
        if (m.type() !== 'error') return;
        const txt = m.text() + ' @ ' + (m.location().url || '');
        if (!/ERR_CONNECTION_REFUSED|Failed to load resource|net::|Failed to fetch/.test(txt)) results.errors.console.push(txt);
      });
      await page.route('**/js/config.local.js', route => route.fulfill({ status: 200, contentType: 'application/javascript',
        body: `window.SMS_API_BASE = ${JSON.stringify(DEAD_API)};\n` }));
      return page;
    }
    const go = async (page, q) => {
      await page.goto(BASE + q, { waitUntil: 'load' });
      await page.waitForFunction(() => window.RISK_DATA && window.GEO_DATA && document.querySelector('#clock-date') && window.APP);
      await page.waitForTimeout(1800);
    };
    const state = page => page.evaluate(() => ({
      clock: document.querySelector('#clock-date').textContent,
      fcView: document.body.classList.contains('fc-view'),
      on: document.querySelector('#horizon button.on')?.dataset.view,
      layer: document.querySelector('#layer-switch button.on')?.dataset.layer,
      layerHidden: document.querySelector('#layer-switch').hidden,
      nBtns: document.querySelectorAll('#horizon button').length,
      title: document.querySelector('#legend .legend-title').textContent.replace(/^FORECAST/, ''),
      badge: !!document.querySelector('#legend .legend-title .fc-badge'),
      swatches: [...document.querySelectorAll('#legend-items li[data-bin] .sw')].map(x => x.style.backgroundColor + '|' + x.textContent),
      legend: [...document.querySelectorAll('#legend-items li')].filter(li => !li.hidden && !li.classList.contains('lg-group')).map(li => li.textContent.trim().replace(/\s+/g, ' ')),
      groups: [...document.querySelectorAll('#legend-items li.lg-group')].map(li => li.textContent),
      legendSum: [...document.querySelectorAll('#legend-items li[data-bin] .ct')].map(x => +x.textContent).reduce((a, b) => a + b, 0),
      phaseSum: [...document.querySelectorAll('#legend-items li[data-phase] .ct')].map(x => +x.textContent).reduce((a, b) => a + b, 0),
      noneCt: +(document.querySelector('#legend-items li[data-bin="-1"] .ct')?.textContent ?? -1),
      statUnits: +document.querySelector('#stat-units').textContent,
      statLab: document.querySelector('#stat-units + .stat-lab').textContent,
      note: document.querySelector('#legend-note').hidden ? null : document.querySelector('#legend-note').textContent,
      cap: document.querySelector('#view-cap').hidden ? null : document.querySelector('#view-cap').textContent,
      smalls: [...document.querySelectorAll('#horizon button[data-view^=f] small')].map(x => x.textContent),
      conf: [...document.querySelectorAll('#horizon .vs-conf')].map(x => x.textContent),
      url: location.search,
      top10: [...document.querySelectorAll('#top10-list li')].map(li => ({ name: li.querySelector('.nm')?.textContent, pc: li.querySelector('.pc')?.textContent })),
      top10note: document.querySelector('#top10-note').textContent,
      goToday: document.querySelector('#go-today').hidden, todayMark: !!document.querySelector('#today-mark'),
      scrubMax: +document.querySelector('#scrub').max,
    }));
    const panel = page => page.evaluate(() => {
      const d = document.querySelector('#detail');
      return {
        hidden: d.hidden, name: d.querySelector('h3')?.textContent,
        big: d.querySelector('.fc-big')?.textContent, target: d.querySelector('.fc-lab b')?.textContent, lab: d.querySelector('.fc-lab')?.textContent,
        fews: d.querySelector('.fc-fews-line, .fc-fews-head')?.textContent,
        chip: d.querySelector('.fc-conf-chip')?.textContent, confs: d.querySelector('.fc-confs')?.textContent,
        hasChart: !!d.querySelector('svg.fc-chart'), dotted: !!d.querySelector('.fc-dotted'), thr: !!d.querySelector('.fc-thr'),
        solid: !!d.querySelector('path.fc-line:not(.fc-dotted)'), noModel: !!d.querySelector('.fc-nomodel'),
        futDots: d.querySelectorAll('.fc-dot.fut').length, steps: d.querySelectorAll('.fc-step').length, stepsNone: d.querySelectorAll('.fc-step.none').length,
        braces: [...d.querySelectorAll('.fc-brace-lab')].map(x => x.textContent), pub: d.querySelector('.fc-pub')?.textContent,
        xLabels: [...d.querySelectorAll('.fc-chart .fc-ax.fut')].map(x => x.textContent),
        notes: [...d.querySelectorAll('.fc-note')].map(x => x.textContent), read: d.querySelector('.fc-read')?.textContent,
        pending: d.querySelector('.fc-pending')?.textContent, oldBig: [...d.querySelectorAll('.d-pm .big')].map(x => x.textContent),
        selRow: document.querySelector('#top10-list li.is-sel .nm')?.textContent,
      };
    });

    // ---- 1440: ZWE Oct 2023 (t=57), leads 1..8 ---------------------------------
    let page = await newPage(1440, 900);
    await go(page, '?country=Zimbabwe&t=57&view=f3');
    let s = await state(page);
    check('oct2023_f3_view', s.fcView && s.on === 'f3' && s.clock === 'Oct 2023' && s.nBtns === 9 && !s.layerHidden && s.layer === 'model', s);
    check('forecast_colours_same_ramp_and_badge', s.badge && s.legend.length === 4 + (s.noneCt > 0 ? 1 : 0) && s.swatches.slice(0, 4).join(',') === 'rgb(12, 163, 12)|1,rgb(255, 212, 59)|2,rgb(236, 131, 58)|3,rgb(208, 59, 59)|4'
      && ['Low', 'Moderate', 'High', 'Very high'].every((n, i) => s.legend[i].includes(n)) && /≥ 80%/.test(s.legend[3]) && /30% – <57%/.test(s.legend[1]), { badge: s.badge, legend: s.legend, sw: s.swatches });
    check('oct2023_title', s.title === 'Forecast issued end of Oct 2023 for Jan 2024 — using only data available then', s.title);
    check('oct2023_legend_counts', s.legendSum === NU && s.statUnits === hot(57, 3) && /chance of Crisis by Jan 2024/.test(s.statLab), { sum: s.legendSum, stat: s.statUnits, data: hot(57, 3), lab: s.statLab });
    const expConf = Array.from({ length: 8 }, (_, i) => i < 3 ? ['M-H', 'M', 'L-M'][i] : (i + 1 <= maxModelLead ? '?' : 'FEWS'));
    check('conf_short_labels_buttons', s.conf.join('|') === expConf.join('|') && s.smalls[0] === `${MON[58 % 12]} '23` && s.smalls[2] === 'Jan \'24', { conf: s.conf, exp: expConf, smalls: s.smalls });
    check('caption_confidence_and_season_note', /Confidence Low-Medium — based on back-tests/.test(s.cap) && /\+3-month forecasts show season-level risk/.test(s.cap)
      && /Confidence Low-Medium/.test(s.note) && !/some inputs missing/.test(s.cap), { cap: s.cap, note: s.note });
    await page.screenshot({ path: path.join(SCREENS, 'forecast_1440_oct2023_f3.png') });

    const perLead = {};
    for (let L = 1; L <= 8; L++) {
      await page.keyboard.press(String(L));
      await page.waitForTimeout(250);
      const st = await state(page);
      perLead[L] = { on: st.on, stat: st.statUnits, exp: hot(57, L), none: st.noneCt, expNone: noneAt(57, L), title: st.title, cap: st.cap };
      if (L === 6) await page.screenshot({ path: path.join(SCREENS, 'forecast_1440_oct2023_f6.png') });
    }
    check('oct2023_all_leads_1_to_8', Object.entries(perLead).every(([L, v]) => v.on === `f${L}` && (+L > maxModelLead ? !(v.stat > 0) : v.stat === v.exp) && (v.expNone === 0 ? v.none === -1 || v.none === 0 : (v.none === v.expNone || (+L > maxModelLead && v.none === -1)))
      && v.title === `Forecast issued end of Oct 2023 for ${lab(57 + +L)} — using only data available then`), perLead);
    const beyond = Object.entries(perLead).filter(([L]) => +L > Math.max(3, maxModelLead));
    check('leads_beyond_model_say_pending', beyond.length === 0 || beyond.every(([L, v]) => new RegExp(`no model forecast fields for \\+${L} yet`).test(v.cap) && /no model forecast — FEWS NET only/.test(v.cap)),
      beyond.map(([L, v]) => ({ L, cap: v.cap })));

    // Colour screenshots: ZWE t=57 +5 (model + FEWS), t=61 +2, t=92 +2
    for (const [t, L, nm] of [[57, 5, 'oct2023_f5'], [61, 2, 'feb2024_f2'], [92, 2, 'live_f2']]) {
      await go(page, `?country=Zimbabwe&t=${t}&view=f${L}&county=Mbire`);
      await page.screenshot({ path: path.join(SCREENS, `forecast_colours_${nm}.png`) });
      if (t === 57) {
        await page.click('#layer-switch button[data-layer=fews]');
        await page.waitForTimeout(400);
        await page.screenshot({ path: path.join(SCREENS, `forecast_colours_${nm}_fews.png`) });
      }
    }
    await go(page, '?country=Zimbabwe&t=57&view=f3');
    // Layers at +4
    await page.keyboard.press('4');
    await page.click('#layer-switch button[data-layer=fews]');
    await page.waitForTimeout(300);
    s = await state(page);
    const phase3 = R.units.filter(u => (fcOf(u.series[57], 4).phase ?? 0) >= 3).length;
    check('fews_layer', s.layer === 'fews' && s.phaseSum === NU && s.legend.length === 5 + (s.legend.some(l => /no outlook/.test(l)) ? 1 : 0) && /Phase 3 Crisis/.test(s.legend[2]) && s.statUnits === phase3 && /\(FEWS NET\)/.test(s.statLab)
      && /How to read: FEWS NET outlook updates ~3×\/year/.test(s.cap) && /layer=fews/.test(s.url) && (hasFews || /FEWS NET outlook fields pending/.test(s.cap)), s);
    await page.screenshot({ path: path.join(SCREENS, 'forecast_1440_oct2023_f4_fews.png') });
    await page.keyboard.press('l');          // fews -> both
    await page.waitForTimeout(300);
    s = await state(page);
    check('both_layer_via_L_key', s.layer === 'both' && s.groups.length === 2 && s.legendSum === NU && s.phaseSum === NU && /fill, FEWS NET projected phase on the outline/.test(s.cap), { layer: s.layer, groups: s.groups, cap: s.cap });
    await page.screenshot({ path: path.join(SCREENS, 'forecast_1440_oct2023_f4_both.png') });
    await page.keyboard.press('l');          // both -> model
    s = await state(page);
    check('L_cycles_back_to_model', s.layer === 'model' && !/layer=/.test(s.url), { layer: s.layer, url: s.url });

    // ---- Feb 2024 (t=61), +3: high risk before the 3 Apr 2024 declaration -----
    await go(page, '?country=Zimbabwe&t=61&view=f3');
    s = await state(page);
    const rk = ranked(61);
    check('feb2024_high_risk_before_declaration', s.clock === 'Feb 2024' && s.statUnits === hot(61, 3) && hot(61, 3) >= 20 && rk[0].v >= 0.7, { ui: s.statUnits, data: hot(61, 3), of: NU, top: rk[0] });
    check('top10_matches_data', s.top10.length === 10 && s.top10[0].name === rk[0].n && s.top10[0].pc === `${Math.round(rk[0].v * 100)}%` && /Confidence \+1 Medium-High · \+2 Medium · \+3 Low-Medium/.test(s.top10note), { ui: s.top10.slice(0, 3), data: rk.slice(0, 3), note: s.top10note });
    check('today_marker_live_t', (LIVE_T == null) === s.goToday && (LIVE_T != null) === s.todayMark && s.scrubMax === NM - 1, { live_t: LIVE_T, goTodayHidden: s.goToday, mark: s.todayMark, max: s.scrubMax });
    await page.screenshot({ path: path.join(SCREENS, 'forecast_1440_f3_feb2024.png') });

    await page.click('#top10-list li:first-child');
    await page.waitForTimeout(1200);
    let p = await panel(page);
    const want = fcOf(R.units.find(u => u.name === rk[0].n).series[61], 3).chance;
    check('panel_headline_and_chart', !p.hidden && p.name === rk[0].n && p.big === `${Math.round(want * 100)}%` && /Chance of Crisis by/.test(p.lab) && p.hasChart && p.dotted && p.thr && p.solid
      && p.xLabels.join(',') === '+1,+2,+3,+4,+5,+6,+7,+8' && p.steps === 8 && (hasFews || (p.stepsNone === 8 && p.braces.join('|') === 'FEWS NET outlook: pending'))
      && (maxModelLead >= 8 || p.noModel) && p.chip === 'Low-Medium confidence' && /based on back-tests/.test(p.confs) && /How to read/.test(p.read)
      && p.notes.some(n => /season-level risk/.test(n)) && p.selRow === rk[0].n && p.oldBig.length === 2, p);
    await page.screenshot({ path: path.join(SCREENS, 'forecast_1440_panel.png') });

    // Keyboard: Esc, F toggles Now <-> +3, digit 8, deep link with layer
    await page.keyboard.press('Escape');
    await page.keyboard.press('f');
    const k1 = await state(page);
    await page.keyboard.press('f');
    const k2 = await state(page);
    await page.keyboard.press('8');
    const k3 = await state(page);
    check('key_F_and_digits', !k1.fcView && k1.on === 'now' && k1.title === 'Shortage risk level' && k1.layerHidden && !/view=/.test(k1.url)
      && k2.on === 'f3' && k3.on === 'f8' && /for Oct 2024/.test(k3.title) && /view=f8/.test(k3.url), { k1: k1.on, k2: k2.on, k3: { on: k3.on, title: k3.title, url: k3.url } });
    await go(page, '?country=Zimbabwe&t=57&view=f6&layer=both');
    s = await state(page);
    check('deeplink_view_layer', s.clock === 'Oct 2023' && s.on === 'f6' && s.layer === 'both', { clock: s.clock, on: s.on, layer: s.layer });
    if (LIVE_T != null) {
      await page.click('#go-today');
      await page.waitForTimeout(400);
      const g = await state(page);
      check('go_today', g.clock === lab(LIVE_T), { clock: g.clock, exp: lab(LIVE_T) });
    }
    // Play in forecast view advances time without errors
    await go(page, '?country=Zimbabwe&t=63&view=f3');
    await page.keyboard.press('Space');
    const advanced = await page.waitForFunction(() => document.querySelector('#clock-date').textContent !== 'Apr 2024', null, { timeout: 8000 }).then(() => true).catch(() => false);
    await page.keyboard.press('Space');
    check('play_in_forecast_view', advanced, advanced);
    await page.context().close();

    // ---- 390 phone ---------------------------------------------------------------
    page = await newPage(390, 844);
    await go(page, '?country=Zimbabwe&t=61&view=f3');
    const m1 = await page.evaluate(() => {
      const r = document.querySelector('#view-switch').getBoundingClientRect();
      const l = document.querySelector('#legend').getBoundingClientRect();
      const overlap = !(r.left >= l.right || r.right <= l.left || r.top >= l.bottom || r.bottom <= l.top);
      return { inView: r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight, overlapLegend: overlap, w: r.width, h: r.height,
        shortLabels: getComputedStyle(document.querySelector('.vs-short')).display !== 'none', top10open: document.querySelector('#top10').open };
    });
    check('mobile_switch_visible', m1.inView && !m1.overlapLegend && m1.shortLabels && !m1.top10open, m1);
    await page.screenshot({ path: path.join(SCREENS, 'forecast_390_f3_feb2024.png') });
    await page.click('#top10 summary');
    await page.waitForTimeout(200);
    await page.click('#top10-list li:first-child');
    await page.waitForTimeout(1200);
    const m2 = await page.evaluate(() => {
      const d = document.querySelector('#detail'); const r = d.getBoundingClientRect();
      return { hidden: d.hidden, big: d.querySelector('.fc-big')?.textContent, chart: !!d.querySelector('svg.fc-chart'), steps: d.querySelectorAll('.fc-step').length, fits: r.right <= innerWidth + 1 && r.width > 300 };
    });
    check('mobile_panel_chart', !m2.hidden && m2.chart && m2.steps === 8 && m2.fits && !!m2.big, m2);
    await page.screenshot({ path: path.join(SCREENS, 'forecast_390_panel.png') });
    await page.context().close();

    // ---- Synthetic contract check (section 4b) ------------------------------------
    // Served ONLY to this test page through a route (nothing on disk changes):
    // per-lead skill, model leads 1..6, FEWS NET ML1/ML2 phases on the Oct 2023
    // rows, and a live month (t=85) with partly-null model fields.
    {
      const S = JSON.parse(JSON.stringify(R));
      S.meta.metrics.forecast_skill = { '1': { roc_auc: 0.7 }, '2': { confidence: 'Medium' }, '3': { roc_auc: 0.5 }, '4': { roc_auc: 0.5 }, '5': { roc_auc: 0.5 }, '6': { roc_auc: 0.5 } };
      const PH = [2, 2, 3, 3, 3, 4, 4, 3];
      S.units.forEach((u, i) => {
        const r = u.series[57];
        const base = r.p_crisis != null ? r.p_crisis : 0.5;
        r.forecast = {};
        for (let L = 1; L <= 8; L++) {
          r.forecast[String(L)] = { p: L === 1 ? r.p : null, p_crisis: L <= 6 ? Math.min(1, base * (0.7 + 0.05 * L)) : null,
            fews_phase: (i % 2 && L >= 7) ? null : PH[L - 1], fews_scenario: L <= 4 ? 'ML1' : 'ML2', fews_published: 'Oct 2023',
            target_label: lab(57 + L), source: L <= 6 ? `model+FEWS ${L <= 4 ? 'ML1' : 'ML2'}` : 'FEWS ML2' };
        }
        const lv = u.series[85];
        if (lv && lv.forecast && lv.forecast['2'] && i % 2) { lv.forecast['2'].p = null; lv.forecast['2'].p_crisis = null; }
      });
      const body = `window.RISK_DATA = window.RISK_DATA || {};\nRISK_DATA["ZWE"] = ${JSON.stringify(S)};\n`;
      page = await newPage(1440, 900);
      await page.route('**/data/risk/ZWE.js', route => route.fulfill({ status: 200, contentType: 'application/javascript', body }));
      const first = S.units[0].name;
      await go(page, `?country=Zimbabwe&t=57&view=f6&layer=both&county=${encodeURIComponent(first)}`);
      s = await state(page);
      p = await panel(page);
      const want6 = Math.round(Math.min(1, (R.units[0].series[57].p_crisis ?? 0.5) * (0.7 + 0.3)) * 100);
      const ph6 = S.units.filter(u => u.series[57].forecast['6'].fews_phase >= 3).length;
      check('synthetic_skill_and_model_leads', s.conf.join('|') === 'M-H|M|L|L|L|L|FEWS|FEWS' && /tested skill per lead \(ROC AUC 0.50\)/.test(s.cap) && !/pending/.test(s.cap)
        && p.big === `${want6}%` && p.chip === 'Low confidence' && p.noModel === true, { conf: s.conf, cap: s.cap, big: p.big, chip: p.chip, noModel: p.noModel });
      check('synthetic_fews_steps_in_panel', p.steps === 8 && p.stepsNone === 0 && p.braces.join('|') === 'ML1|ML2' && p.pub === 'outlook published Oct 2023' && /FEWS NET projected Phase 4 Emergency for Apr 2024 · ML2 · published Oct 2023/.test(p.fews)
        && p.futDots === 6 && !p.pending, { steps: p.steps, none: p.stepsNone, braces: p.braces, fews: p.fews, futDots: p.futDots, pending: p.pending });
      check('synthetic_both_layer_legend', s.groups.length === 2 && s.phaseSum === NU && s.legendSum === NU, { groups: s.groups, phaseSum: s.phaseSum, legendSum: s.legendSum });
      await page.screenshot({ path: path.join(SCREENS, 'forecast_1440_synthetic_both_f6.png') });
      await page.click('#layer-switch button[data-layer=fews]');
      await page.waitForTimeout(300);
      s = await state(page); p = await panel(page);
      check('synthetic_fews_layer_stats', s.statUnits === ph6 && /projected IPC 3\+ by Apr 2024 \(FEWS NET\)/.test(s.statLab) && p.big == null && /Phase 4 Emergency/.test(p.fews), { stat: s.statUnits, exp: ph6, lab: s.statLab, fews: p.fews });
      await page.keyboard.press('8');
      await page.waitForTimeout(300);
      s = await state(page);
      const nullPh8 = S.units.filter(u => u.series[57].forecast['8'].fews_phase == null).length;
      check('synthetic_fews_f8_partial', s.legend.some(l => /no outlook/.test(l) && l.endsWith(String(nullPh8))) && /no model forecast — FEWS NET only/.test(s.cap), { legend: s.legend, cap: s.cap });
      await page.screenshot({ path: path.join(SCREENS, 'forecast_1440_synthetic_fews_f8.png') });
      // live month with partly-null model fields
      await go(page, '?country=Zimbabwe&t=85&view=f2');
      s = await state(page);
      check('synthetic_live_gap_note', s.clock === lab(85) && /live: some inputs missing \(see data notes\)/.test(s.cap) && /live: some inputs missing/.test(s.note) && /live: some inputs missing/.test(s.top10note), { clock: s.clock, cap: s.cap });
      await page.context().close();
    }

    check('zero_js_errors', results.errors.js.length === 0, results.errors.js);
    check('zero_console_errors', results.errors.console.length === 0, results.errors.console);
  } catch (e) {
    results.pass = false;
    results.fatal = String(e && e.stack || e);
  } finally {
    if (browser) await browser.close().catch(() => {});
    server.kill();
  }
  fs.writeFileSync(path.join(__dirname, 'forecast_results.json'), JSON.stringify(results, null, 2));
  const failed = Object.entries(results.checks).filter(([, v]) => !v.pass).map(([k]) => k);
  console.log(JSON.stringify({ pass: results.pass, data: results.data, failed, fatal: results.fatal || null,
    js_errors: results.errors.js, console_errors: results.errors.console }, null, 2));
  process.exit(results.pass ? 0 : 1);
}
main();
