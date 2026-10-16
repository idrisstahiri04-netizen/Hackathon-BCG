// Follow-ups to ui_a11y.js: (a) on a live tab, does Tab reach the map controls hidden under
// the overlay? (b) can the unit panel be opened by keyboard at all? (c) phone-size tab bar
// scrolls? (d) crowd badges overlapping each other on the globe (ZWE Apr 2024).
// Run: node tests/e2e/ui_extra.js -> tests/e2e/ui_results_extra.json
'use strict';
const L = require('./ui_lib');

(async () => {
  const browser = await L.launch();
  const out = {};
  const page = await L.newPage(browser, { w: 1440, h: 900, online: true });
  await L.gotoApp(page, { country: 'Zimbabwe', t: 63 }, { settle: 2500 });
  const focused = () => page.evaluate(() => { const e = document.activeElement; if (!e) return null;
    const r = e.getBoundingClientRect(); const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return { el: `${e.tagName.toLowerCase()}${e.id ? '#' + e.id : ''} "${(e.textContent || e.value || e.getAttribute('aria-label') || '').trim().slice(0, 20)}"`,
      coveredByOverlay: !!(top && !e.contains(top) && !top.contains(e) && top.closest('.live-page')) }; });
  await page.click('#tabs [data-page="alerts"]');
  await page.waitForTimeout(2500);
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
  const order = [];
  for (let i = 0; i < 14; i++) { await page.keyboard.press('Tab'); order.push(await focused()); }
  out.tabOrderOnAlertsPage = order;
  out.hiddenMapControlsFocusable = order.filter(o => o && o.coveredByOverlay).map(o => o.el);
  // Globe-only interactions by keyboard: any way to open a unit?
  await page.click('#tabs [data-page="map"]');
  await page.waitForTimeout(500);
  out.unitPanelKeyboard = await page.evaluate(() => ({
    canvasTabIndex: document.querySelector('#globe canvas') ? document.querySelector('#globe canvas').tabIndex : null,
    feedNotesFocusable: document.querySelectorAll('#feed .note[tabindex="0"], #feed .note button').length,
    feedNotes: document.querySelectorAll('#feed .note').length,
    verdict: 'no keyboard path to open a unit panel except the ?county= deep link',
  }));
  // Crowd badges overlapping each other.
  out.crowdBadges = await page.evaluate(() => {
    const b = [...document.querySelectorAll('.crowd-badge')].map(e => { const r = e.getBoundingClientRect(); return { t: e.title.slice(0, 40), x: r.left, y: r.top, r: r.right, b: r.bottom }; });
    const ov = [];
    for (let i = 0; i < b.length; i++) for (let j = i + 1; j < b.length; j++) if (b[i].x < b[j].r && b[j].x < b[i].r && b[i].y < b[j].b && b[j].y < b[i].b) ov.push([b[i].t, b[j].t]);
    return { n: b.length, overlapping: ov };
  });
  out.errors = page.errors;
  await page.context().close();

  // Phone-size tab bar: scrollable? all tabs reachable?
  const ph = await L.newPage(browser, { w: 390, h: 844, online: true });
  await L.gotoApp(ph, { country: 'Zimbabwe', t: 63 }, { settle: 2000 });
  out.phoneTabs = await ph.evaluate(() => { const t = document.querySelector('#tabs'); return { scrollW: t.scrollWidth, clientW: t.clientWidth,
    tabs: [...t.querySelectorAll('[role=tab]')].map(b => { const r = b.getBoundingClientRect(); return { t: b.textContent.trim(), l: Math.round(r.left), r: Math.round(r.right) }; }),
    beStatus: (s => { const r = s.getBoundingClientRect(); return { l: Math.round(r.left), r: Math.round(r.right), w: Math.round(r.width) }; })(document.querySelector('#be-status')) }; });
  // Mobile sheet vs legend / HUD: what does the sheet cover?
  await L.gotoApp(ph, { country: 'Zimbabwe', t: 63, county: L.worstUnit('ZWE', 63) }, { settle: 2000 });
  out.phoneSheet = await ph.evaluate(() => { const r = s => document.querySelector(s).getBoundingClientRect();
    const d = r('#detail'), lg = r('#legend'), hud = r('#hud'), feed = r('#feed-col'), tl = r('#timeline');
    return { sheetTop: Math.round(d.top), sheetBottom: Math.round(d.bottom), sheetH: Math.round(d.height), legendTop: Math.round(lg.top), legendBottom: Math.round(lg.bottom), hudBottom: Math.round(hud.bottom), feedTop: Math.round(feed.top), timelineTop: Math.round(tl.top),
      coversLegend: d.top < lg.bottom, coversHud: d.top < hud.bottom, coversFeed: d.top < feed.bottom, panelScrollable: document.querySelector('#detail').scrollHeight > document.querySelector('#detail').clientHeight }; });
  out.phoneErrors = ph.errors;
  await ph.context().close();

  const f = L.saveJSON('ui_results_extra.json', out);
  console.log(JSON.stringify(out, null, 1));
  console.log('->', f);
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
