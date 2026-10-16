// Visual / responsive matrix: 4 countries x 5 months x 5 viewports (unit panel open),
// the 4 tabs x 5 viewports x backend online/offline, and browser zoom 120 % / 150 %.
// Run:  node tests/e2e/ui_matrix.js      (needs :8401 static server and :8402 backend, see ui_lib.js)
// Output: tests/e2e/ui_results_matrix.json and tests/e2e/screens/ui_*.png
'use strict';
const L = require('./ui_lib');

(async () => {
  const browser = await L.launch();
  const out = { matrix: [], tabs: [], zoom: [], errors: {} };
  const t0 = Date.now();

  // ---- 1. Country x month x viewport ----------------------------------------
  for (const vp of L.VIEWPORTS) {
    const page = await L.newPage(browser, { w: vp.w, h: vp.h, online: true });
    const mobile = vp.w <= 720;
    for (const [iso, c] of Object.entries(L.COUNTRIES)) {
      for (const t of c.months) {
        const county = L.worstUnit(iso, t);
        const ready = await L.gotoApp(page, { country: c.name, t, county }, { settle: 1800 });
        const open = await L.layoutAudit(page, { mobile });
        const file = await L.shot(page, `ui_${iso}_t${String(t).padStart(2, '0')}_${vp.w}x${vp.h}`);
        await page.keyboard.press('Escape');
        await page.waitForTimeout(150);
        const closed = await L.layoutAudit(page, { mobile });
        // Forecast view (+3 months) with the panel re-opened, for the declaration month only.
        let f3 = null, file3 = null;
        if (t === c.decl && await page.$('#view-switch [data-view="f3"]')) {
          await page.evaluate(() => { const li = document.querySelector('#top10-list li[role=button]'); li && li.click(); });
          await page.click('#view-switch [data-view="f3"]');
          await page.waitForTimeout(900);
          const a = await L.layoutAudit(page, { mobile });
          f3 = { view: a.view, overlaps: a.overlaps, clipped: a.clipped, overflow: a.overflow, minFont: a.minFont, tiny: a.tiny, boxes: a.boxes, detailOpen: a.detailOpen,
            legendTitle: await page.textContent('#legend .legend-title'), legendRows: await page.$$eval('#legend-items li:not([hidden])', l => l.map(x => x.innerText.replace(/\s+/g, ' ').trim())) };
          file3 = await L.shot(page, `ui_${iso}_t${String(t).padStart(2, '0')}_f3_${vp.w}x${vp.h}`);
        }
        out.matrix.push({ iso, t, county, vp: `${vp.w}x${vp.h}`, ready_ms: ready, file, file3,
          hud: open.hud, clock: open.clock, detailOpen: open.detailOpen,
          open: { overlaps: open.overlaps, clipped: open.clipped, overflow: open.overflow, minFont: open.minFont, tiny: open.tiny, canvas: open.canvas, hscroll: open.hscroll, boxes: open.boxes },
          closed: { overlaps: closed.overlaps, clipped: closed.clipped, overflow: closed.overflow }, f3 });
        process.stdout.write(`${iso} t${t} ${vp.w}x${vp.h} ov=${open.overlaps.length}/${closed.overlaps.length}${f3 ? '/f3:' + f3.overlaps.length : ''} clip=${open.clipped.length}${f3 ? '/' + f3.clipped.length : ''} of=${open.overflow.length}${f3 ? '/' + f3.overflow.length : ''} min=${open.minFont}\n`);
      }
    }
    out.errors[`matrix_${vp.w}x${vp.h}`] = page.errors;
    await page.context().close();
  }

  // ---- 2. Tabs x viewport x online/offline ----------------------------------
  const TABS = ['map', 'alerts', 'users', 'phone'];
  for (const online of [true, false]) {
    for (const vp of L.VIEWPORTS) {
      const page = await L.newPage(browser, { w: vp.w, h: vp.h, online });
      const mobile = vp.w <= 720;
      await L.gotoApp(page, { country: 'Zimbabwe', t: 63, county: L.worstUnit('ZWE', 63) }, { online, settle: 2500 });
      for (const tab of TABS) {
        await page.click(`#tabs [data-page="${tab}"]`);
        await page.waitForTimeout(online ? 2600 : 1200);   // one poll cycle
        if (tab === 'phone' && online) {
          await page.fill('#ph-number', '+263770009' + String(vp.w).slice(-3));
          await page.click('#ph-quick button:has-text("JOIN Mbire farmer")');
          await page.waitForTimeout(2600);
        }
        const a = await L.layoutAudit(page, { mobile });
        const state = await page.evaluate((tab) => ({
          beStatus: document.querySelector('#be-status .be-lab').textContent,
          beClass: document.querySelector('#be-status').className,
          offlineBanner: [...document.querySelectorAll(`#page-${tab} .lp-offline`)].some(n => !n.hidden && getComputedStyle(n).display !== 'none'),
          pageVisible: tab === 'map' ? !document.body.classList.contains('on-live') : !document.querySelector(`#page-${tab}`).hidden,
          alerts: document.querySelectorAll('#alerts-list li').length,
          alertsEmptyShown: !document.querySelector('#alerts-empty').hidden,
          users: document.querySelectorAll('#join-body tr').length,
          ctrTotal: document.querySelector('#ctr-total').textContent,
          phoneBubbles: document.querySelectorAll('#ph-thread .ph-msg').length,
          phoneThem: [...document.querySelectorAll('#ph-thread .ph-msg.them .ph-txt')].map(n => n.textContent).slice(-1)[0] || null,
          runBtn: (b => ({ hidden: b.hidden, disabled: b.disabled }))(document.querySelector('#run-alerts')),
          badge: document.querySelector('#badge-alerts').hidden ? null : document.querySelector('#badge-alerts').textContent,
          approveBtns: document.querySelectorAll('.approve').length,
          tabsScrollable: document.querySelector('#tabs').scrollWidth > document.querySelector('#tabs').clientWidth + 1,
          tabsVisible: [...document.querySelectorAll('#tabs [role=tab]')].map(b => { const r = b.getBoundingClientRect(); return r.right <= innerWidth + 1 && r.left >= -1; }),
          urlPage: new URLSearchParams(location.search).get('page'),
        }), tab);
        const file = await L.shot(page, `ui_tab_${tab}_${vp.w}x${vp.h}_${online ? 'online' : 'offline'}`);
        out.tabs.push({ tab, vp: `${vp.w}x${vp.h}`, online, file, ...state,
          overlaps: a.overlaps, clipped: a.clipped, overflow: a.overflow, minFont: a.minFont, tiny: a.tiny, hscroll: a.hscroll, boxes: a.boxes });
        process.stdout.write(`tab ${tab} ${vp.w}x${vp.h} ${online ? 'on' : 'off'} be="${state.beStatus}" banner=${state.offlineBanner} alerts=${state.alerts} users=${state.users} ph=${state.phoneBubbles} ov=${a.overlaps.length} clip=${a.clipped.length} of=${a.overflow.length}\n`);
      }
      out.errors[`tabs_${vp.w}x${vp.h}_${online ? 'online' : 'offline'}`] = page.errors;
      await page.context().close();
    }
  }

  // ---- 3. Browser zoom: Chrome zoom = smaller CSS viewport + higher DPR ----
  const ZOOMS = [
    { win: [1920, 1080], zoom: 1.2 }, { win: [1920, 1080], zoom: 1.5 }, { win: [1440, 900], zoom: 1.2 }, { win: [1440, 900], zoom: 1.5 },
  ];
  for (const z of ZOOMS) {
    const w = Math.round(z.win[0] / z.zoom), h = Math.round(z.win[1] / z.zoom);
    const page = await L.newPage(browser, { w, h, dpr: z.zoom, online: true });
    await L.gotoApp(page, { country: 'Zimbabwe', t: 63, county: L.worstUnit('ZWE', 63) }, { settle: 2500 });
    const a = await L.layoutAudit(page, { mobile: w <= 720 });
    const tag = `${z.win[0]}x${z.win[1]}_zoom${Math.round(z.zoom * 100)}`;
    const file = await L.shot(page, `ui_zoom_${tag}_map`);
    await page.click('#tabs [data-page="alerts"]');
    await page.waitForTimeout(2600);
    const b = await L.layoutAudit(page, { mobile: w <= 720 });
    const file2 = await L.shot(page, `ui_zoom_${tag}_alerts`);
    out.zoom.push({ window: z.win, zoom: z.zoom, cssViewport: [w, h], files: [file, file2],
      map: { overlaps: a.overlaps, clipped: a.clipped, overflow: a.overflow, minFont: a.minFont, tiny: a.tiny, canvas: a.canvas, boxes: a.boxes },
      alerts: { overlaps: b.overlaps, clipped: b.clipped, overflow: b.overflow, minFont: b.minFont } });
    out.errors[`zoom_${tag}`] = page.errors;
    process.stdout.write(`zoom ${tag} css=${w}x${h} ov=${a.overlaps.length} clip=${a.clipped.length} of=${a.overflow.length} min=${a.minFont}\n`);
    await page.context().close();
  }

  out.duration_s = Math.round((Date.now() - t0) / 1000);
  const f = L.saveJSON('ui_results_matrix.json', out);
  const jsErr = Object.values(out.errors).reduce((n, e) => n + e.js.length + e.console.length, 0);
  console.log(`done in ${out.duration_s}s -> ${f}; JS/console errors: ${jsErr}`);
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
