// Accessibility checks: axe-core on each tab (online + map offline), colour contrast of the
// level chips and muted text, keyboard-only navigation, and "level is text+glyph, not colour alone".
// Run:  node tests/e2e/ui_a11y.js   -> tests/e2e/ui_results_a11y.json, screens/ui_a11y_*.png
'use strict';
const path = require('path');
const L = require('./ui_lib');
const AXE = path.join(__dirname, 'node_modules', 'axe-core', 'axe.min.js');

// WCAG 2.x relative luminance / contrast ratio.
const lum = hex => {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255).map(c => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return +((x + 0.05) / (y + 0.05)).toFixed(2); };
const blend = (fg, a, bg) => '#' + [1, 3, 5].map(i => Math.round(parseInt(fg.slice(i, i + 2), 16) * a + parseInt(bg.slice(i, i + 2), 16) * (1 - a)).toString(16).padStart(2, '0')).join('');

async function runAxe(page, label) {
  await page.addScriptTag({ path: AXE });
  const r = await page.evaluate(async () => {
    const res = await window.axe.run(document, { resultTypes: ['violations', 'incomplete'] });
    const pick = v => ({ id: v.id, impact: v.impact, help: v.help, n: v.nodes.length,
      nodes: v.nodes.slice(0, 4).map(n => ({ target: n.target.join(' '), html: n.html.slice(0, 120), msg: (n.any[0] || n.all[0] || {}).message })) });
    return { violations: res.violations.map(pick), incomplete: res.incomplete.map(pick), passes: res.passes ? res.passes.length : undefined };
  });
  return { label, ...r };
}

(async () => {
  const browser = await L.launch();
  const out = { axe: [], contrast: {}, keyboard: {}, levelText: {}, errors: {} };

  // ---- 1. axe on each tab -----------------------------------------------------
  {
    const page = await L.newPage(browser, { w: 1440, h: 900, online: true });
    await L.gotoApp(page, { country: 'Zimbabwe', t: 63, county: L.worstUnit('ZWE', 63) }, { settle: 2600 });
    out.axe.push(await runAxe(page, 'map (ZWE Apr 2024, panel open, online)'));
    for (const tab of ['alerts', 'users', 'phone']) {
      await page.click(`#tabs [data-page="${tab}"]`);
      await page.waitForTimeout(2600);
      out.axe.push(await runAxe(page, `${tab} tab (online)`));
    }
    out.errors.axe_online = page.errors;
    await page.context().close();
    const off = await L.newPage(browser, { w: 1440, h: 900, online: false });
    await L.gotoApp(off, { country: 'Zimbabwe', t: 63 }, { online: false, settle: 2000 });
    await off.click('#tabs [data-page="alerts"]');
    await off.waitForTimeout(1200);
    out.axe.push(await runAxe(off, 'alerts tab (backend offline)'));
    out.errors.axe_offline = off.errors;
    await off.context().close();
  }

  // ---- 2. Contrast ------------------------------------------------------------
  {
    const page = await L.newPage(browser, { w: 1440, h: 900, online: true });
    await L.gotoApp(page, { country: 'Zimbabwe', t: 63, county: L.worstUnit('ZWE', 63) }, { settle: 2000 });
    const palette = await page.evaluate(() => {
      const cs = getComputedStyle(document.querySelector('.viz-root'));
      const v = k => cs.getPropertyValue(k).trim();
      const chip = document.querySelector('#detail .chip');
      return { lvl: [v('--lvl-0'), v('--lvl-1'), v('--lvl-2'), v('--lvl-3')], s0: v('--surface-0'), s1: v('--surface-1'), s2: v('--surface-2'), s3: v('--surface-3'),
        muted: v('--text-muted'), secondary: v('--text-secondary'), accent: v('--accent'),
        chipText: chip ? getComputedStyle(chip).color : null, chipFont: chip ? getComputedStyle(chip).fontSize : null,
        swGlyph: getComputedStyle(document.querySelector('#legend .sw')).color, swFont: getComputedStyle(document.querySelector('#legend .sw')).fontSize };
    });
    const chipText = '#0e0e0d';
    const names = ['Normal', 'Watch', 'Warning', 'Emergency'];
    out.contrast.palette = palette;
    out.contrast.chipTextOnLevel = palette.lvl.map((c, i) => ({ level: `L${i} ${names[i]}`, bg: c, text: chipText, ratio: ratio(chipText, c), font: palette.chipFont,
      pass_AA_small: ratio(chipText, c) >= 4.5 }));
    out.contrast.chipOnSurface = palette.lvl.map((c, i) => ({ level: `L${i}`, bg: c, surface: palette.s2, ratio: ratio(c, palette.s2), pass_nonText_3: ratio(c, palette.s2) >= 3 }));
    out.contrast.adjacentLevels = [[0, 1], [1, 2], [2, 3]].map(([a, b]) => ({ pair: `L${a}/L${b}`, ratio: ratio(palette.lvl[a], palette.lvl[b]) }));
    const glyph = blend('#000000', 0.72, palette.lvl[1]);
    out.contrast.legendGlyph = palette.lvl.map((c, i) => ({ level: `L${i}`, glyph_on_bg: ratio(blend('#000000', 0.72, c), c), font: palette.swFont }));
    out.contrast.mutedText = [
      { text: 'text-muted', fg: palette.muted, bg: palette.s1, ratio: ratio(palette.muted, palette.s1), pass_AA_small: ratio(palette.muted, palette.s1) >= 4.5 },
      { text: 'text-muted', fg: palette.muted, bg: palette.s2, ratio: ratio(palette.muted, palette.s2), pass_AA_small: ratio(palette.muted, palette.s2) >= 4.5 },
      { text: 'text-secondary', fg: palette.secondary, bg: palette.s1, ratio: ratio(palette.secondary, palette.s1), pass_AA_small: ratio(palette.secondary, palette.s1) >= 4.5 },
      { text: 'white on accent (buttons)', fg: '#ffffff', bg: palette.accent, ratio: ratio('#ffffff', palette.accent), pass_AA_small: ratio('#ffffff', palette.accent) >= 4.5 },
      { text: 'pending status (lvl-1 on surface-2)', fg: palette.lvl[1], bg: palette.s2, ratio: ratio(palette.lvl[1], palette.s2) },
      { text: 'decl-mark label (lvl-3 on surface-1, 9.5px)', fg: palette.lvl[3], bg: palette.s1, ratio: ratio(palette.lvl[3], palette.s1), pass_AA_small: ratio(palette.lvl[3], palette.s1) >= 4.5 },
    ];

    // ---- 4. Level conveyed by text + glyph --------------------------------------
    out.levelText = await page.evaluate(() => {
      const chips = [...document.querySelectorAll('.chip')].filter(c => c.offsetParent !== null);
      const re = /^[●▲■] L[0-3] (NORMAL|WATCH|WARNING|EMERGENCY)/;
      const bad = chips.map(c => c.textContent.trim()).filter(t => !re.test(t) && t !== 'OFFICIAL' && !/CROWD/.test(t));
      const legend = [...document.querySelectorAll('#legend li')].map(li => li.innerText.replace(/\s+/g, ' ').trim());
      const feedMoves = [...document.querySelectorAll('#feed .n-move')].slice(0, 3).map(n => n.textContent);
      const glyphs = [...new Set(chips.map(c => c.textContent.trim()[0]))];
      return { chips: chips.length, nonConforming: bad, legend, feedMoves, glyphs,
        watchVsWarningSameGlyph: /▲ L1/.test(chips.map(c => c.textContent).join()) && /▲ L2/.test(chips.map(c => c.textContent).join()),
        globeHoverLabel: 'polygonLabel is empty: on the globe itself the level is colour + extrusion height only (legend gives the key)' };
    });
    out.errors.contrast = page.errors;
    await page.context().close();
  }

  // ---- 3. Keyboard-only navigation --------------------------------------------
  {
    const page = await L.newPage(browser, { w: 1440, h: 900, online: true });
    await L.gotoApp(page, {}, { settle: 1500 });   // idle: search is focused by app.js
    const K = out.keyboard;
    const focused = () => page.evaluate(() => { const e = document.activeElement; return e ? `${e.tagName.toLowerCase()}${e.id ? '#' + e.id : ''}${e.getAttribute('role') ? '[' + e.getAttribute('role') + ']' : ''} "${(e.textContent || e.value || e.getAttribute('aria-label') || '').trim().slice(0, 24)}"` : null; });
    K.initialFocus = await focused();
    // Pick a country by keyboard: type, ArrowDown, Enter.
    await page.keyboard.type('Ken');
    await page.waitForTimeout(150);
    K.resultsOpenAfterTyping = await page.evaluate(() => !document.querySelector('#results').hidden && [...document.querySelectorAll('#results li')].map(l => l.textContent));
    await page.keyboard.press('Enter');
    await page.waitForTimeout(1800);
    K.enterSelectsCountry = await page.evaluate(() => document.querySelector('#hud-name').textContent);
    // Tab order from the top of the document.
    await page.evaluate(() => document.activeElement && document.activeElement.blur());
    const order = [];
    for (let i = 0; i < 18; i++) { await page.keyboard.press('Tab'); order.push(await focused()); }
    K.tabOrder = order;
    // Arrow keys on the tablist (WAI-ARIA tabs pattern) and activation with Enter / Space.
    await page.focus('#tabs [data-page="map"]');
    await page.keyboard.press('ArrowRight');
    await page.waitForTimeout(200);
    K.arrowRightOnTab = { focus: await focused(), selected: await page.evaluate(() => document.querySelector('#tabs [aria-selected=true]').dataset.page), month: await page.textContent('#clock-date') };
    await page.focus('#tabs [data-page="alerts"]');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(400);
    K.enterOnAlertsTab = await page.evaluate(() => ({ page: document.querySelector('#tabs [aria-selected=true]').dataset.page, visible: !document.querySelector('#page-alerts').hidden }));
    await page.focus('#tabs [data-page="users"]');
    await page.keyboard.press('Space');
    await page.waitForTimeout(400);
    K.spaceOnUsersTab = await page.evaluate(() => ({ page: document.querySelector('#tabs [aria-selected=true]').dataset.page, visible: !document.querySelector('#page-users').hidden,
      playing: !document.querySelector('.ic-pause').hidden }));
    // Escape does not close the live page?  Back to map by keyboard.
    await page.keyboard.press('Escape');
    await page.waitForTimeout(200);
    K.escapeOnLivePage = await page.evaluate(() => document.querySelector('#tabs [aria-selected=true]').dataset.page);
    await page.focus('#tabs [data-page="map"]');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(600);
    if (await page.evaluate(() => !document.querySelector('.ic-pause').hidden)) await page.keyboard.press('Space');   // make sure we are paused
    await page.waitForTimeout(200);
    // Timeline: Space play/pause from body, arrows step months, slider arrows.
    await page.evaluate(() => document.activeElement && document.activeElement.blur());
    const m0 = await page.textContent('#clock-date');
    await page.keyboard.press('ArrowRight'); await page.keyboard.press('ArrowRight');
    const m2 = await page.textContent('#clock-date');
    await page.keyboard.press('Space'); await page.waitForTimeout(1200);
    const playing = await page.evaluate(() => !document.querySelector('.ic-pause').hidden);
    await page.keyboard.press('Space'); await page.waitForTimeout(100);
    const stopped = await page.evaluate(() => document.querySelector('.ic-pause').hidden);
    await page.focus('#scrub');
    await page.keyboard.press('End');
    await page.waitForTimeout(200);
    const atEnd = await page.inputValue('#scrub');
    await page.keyboard.press('Home'); await page.keyboard.press('ArrowRight');
    await page.waitForTimeout(200);
    const afterHome = await page.inputValue('#scrub');
    K.timeline = { before: m0, afterTwoArrowRight: m2, spaceStartsPlay: playing, spaceStops: stopped, sliderEnd: atEnd, sliderHomePlusOne: afterHome };
    // Play/pause button with Space (app.js intercepts Space on buttons).
    await page.focus('#play');
    await page.keyboard.press('Space'); await page.waitForTimeout(600);
    const p1 = await page.evaluate(() => !document.querySelector('.ic-pause').hidden);
    await page.keyboard.press('Space'); await page.waitForTimeout(100);
    const p2 = await page.evaluate(() => !document.querySelector('.ic-pause').hidden);
    await page.keyboard.press('Enter'); await page.waitForTimeout(300);
    const p3 = await page.evaluate(() => !document.querySelector('.ic-pause').hidden);
    if (p3) await page.keyboard.press('Enter');
    K.playButton = { spaceToggles: p1 && !p2, enterToggles: p3 };
    // Speed buttons: Enter works, Space is hijacked?
    await page.focus('#speeds [data-speed="2"]');
    await page.keyboard.press('Enter'); await page.waitForTimeout(100);
    const sp = await page.evaluate(() => document.querySelector('#speeds .on').dataset.speed);
    await page.focus('#speeds [data-speed="4"]');
    await page.keyboard.press('Space'); await page.waitForTimeout(300);
    const sp2 = await page.evaluate(() => ({ speed: document.querySelector('#speeds .on').dataset.speed, playing: !document.querySelector('.ic-pause').hidden }));
    if (sp2.playing) await page.keyboard.press('Space');
    K.speedButtons = { enterSets2x: sp === '2', spaceOn4x: sp2 };
    // Forecast view keys (F toggles, 0-3 pick) and the Top 10 list (role=button, tabindex=0).
    if (await page.$('#view-switch')) {
      await page.evaluate(() => document.activeElement && document.activeElement.blur());
      const viewNow = () => page.evaluate(() => ({ view: (document.querySelector('#view-switch .on') || {}).dataset?.view, pressed: [...document.querySelectorAll('#view-switch button')].map(b => b.getAttribute('aria-pressed')).join(''),
        legend: document.querySelector('#legend .legend-title').textContent.slice(0, 40) }));
      await page.keyboard.press('f'); await page.waitForTimeout(300); const vF = await viewNow();
      await page.keyboard.press('2'); await page.waitForTimeout(300); const v2 = await viewNow();
      await page.keyboard.press('0'); await page.waitForTimeout(300); const v0 = await viewNow();
      await page.focus('#view-switch [data-view="f1"]');
      await page.keyboard.press('Space'); await page.waitForTimeout(300); const vSpace = await viewNow();
      const playingAfterSpace = await page.evaluate(() => !document.querySelector('.ic-pause').hidden);
      if (playingAfterSpace) await page.keyboard.press('Space');
      await page.keyboard.press('Enter'); await page.waitForTimeout(300); const vEnter = await viewNow();
      await page.keyboard.press('0');
      let t10 = null;
      const li = await page.$('#top10-list li[role=button]');
      if (li) {
        await li.focus();
        const name = await li.$eval('.nm', n => n.textContent);
        await page.keyboard.press('Enter'); await page.waitForTimeout(1200);
        t10 = { focusable: true, name, panelOpened: await page.evaluate(() => !document.querySelector('#detail').hidden), panelName: await page.$eval('#detail h3', h => h.textContent).catch(() => null) };
        await page.keyboard.press('Escape');
      } else t10 = { focusable: false };
      K.forecastKeys = { fToggles: vF, key2: v2, key0: v0, spaceOnViewButton: { ...vSpace, startedPlayback: playingAfterSpace }, enterOnViewButton: vEnter, top10: t10 };
    }
    // Feed items + globe polygons: reachable by keyboard?
    K.feedKeyboard = await page.evaluate(() => {
      const notes = document.querySelectorAll('#feed .note');
      const focusable = document.querySelectorAll('#feed .note[tabindex], #feed .note button, #feed .note a, #feed .note[role=button]');
      const results = document.querySelectorAll('#results li');
      return { notes: notes.length, focusableNotes: focusable.length, notesHaveRole: [...notes].some(n => n.getAttribute('role')),
        globeCanvasFocusable: (document.querySelector('#globe canvas') || {}).tabIndex, resultsOptionsFocusable: [...results].some(l => l.tabIndex >= 0) };
    });
    // Open a unit by deep link, then Esc closes it; the close button is reachable.
    await L.gotoApp(page, { country: 'Zimbabwe', t: 63, county: L.worstUnit('ZWE', 63) }, { settle: 1500 });
    const openBefore = await page.evaluate(() => !document.querySelector('#detail').hidden);
    await page.evaluate(() => document.activeElement && document.activeElement.blur());
    await page.keyboard.press('Escape');
    await page.waitForTimeout(150);
    const openAfter = await page.evaluate(() => !document.querySelector('#detail').hidden);
    // Re-open and tab to the close button.
    await page.evaluate(() => { const li = document.querySelector('#feed .note:not(.decl)'); li && li.click(); });
    await page.waitForTimeout(1200);
    let reachedClose = false, reachedAud = false;
    for (let i = 0; i < 40 && !reachedClose; i++) {
      await page.keyboard.press('Tab');
      const f = await focused();
      if (/d-close|"Close"|"×"/.test(f)) reachedClose = true;
      if (/Farmers|Herders|Extension/.test(f)) reachedAud = true;
    }
    K.detailPanel = { openedByDeepLink: openBefore, escapeCloses: !openAfter, closeButtonReachableByTab: reachedClose, audienceTabsReachable: reachedAud,
      focusMovedIntoPanelOnOpen: await page.evaluate(() => !!document.activeElement && !!document.activeElement.closest('#detail')) };
    await L.shot(page, 'ui_a11y_keyboard_focus');
    // Focus-visible styles on the main controls.
    K.focusRing = await page.evaluate(async () => {
      const res = {};
      for (const sel of ['#tabs [data-page="alerts"]', '#play', '#scrub', '#speeds button', '#search', '.d-close', '.aud-tabs button', '#run-alerts']) {
        const e = document.querySelector(sel); if (!e || e.hidden) { res[sel] = 'absent'; continue; }
        e.focus();
        const cs = getComputedStyle(e);
        res[sel] = { outline: cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0 ? `${cs.outlineWidth} ${cs.outlineStyle} ${cs.outlineColor}` : 'none', boxShadow: cs.boxShadow !== 'none' };
      }
      return res;
    });
    out.errors.keyboard = page.errors;
    await page.context().close();
  }

  const f = L.saveJSON('ui_results_a11y.json', out);
  for (const a of out.axe) console.log(a.label, 'violations:', a.violations.map(v => `${v.id}(${v.impact},${v.n})`).join(' '), '| incomplete:', a.incomplete.map(v => `${v.id}(${v.n})`).join(' '));
  console.log('contrast chips:', out.contrast.chipTextOnLevel.map(c => `${c.level}=${c.ratio}`).join(' '), '| muted:', out.contrast.mutedText.map(m => `${m.text}=${m.ratio}`).join(' '));
  console.log('keyboard:', JSON.stringify(out.keyboard));
  console.log('levelText:', JSON.stringify(out.levelText));
  console.log('errors:', JSON.stringify(Object.fromEntries(Object.entries(out.errors).map(([k, v]) => [k, { js: v.js.length, console: v.console.length, net: v.net.length }]))));
  console.log('->', f);
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
