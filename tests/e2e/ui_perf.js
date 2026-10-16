// Performance: cold page load (x3), globe frame rate during playback (rAF sampling + long tasks),
// JS heap before/after a full 72-month playback (two passes, GC forced via CDP), DOM growth,
// and time to switch countries (sync cost + time to next painted frame).
// Note: headless Chrome here renders WebGL with SwiftShader (CPU). Frame rates are a floor,
// not what a GPU laptop shows; relative numbers (growth, sync costs) are still meaningful.
// Run alone (no other browser load):  node tests/e2e/ui_perf.js  -> tests/e2e/ui_results_perf.json
'use strict';
const L = require('./ui_lib');

const MB = n => +(n / 1048576).toFixed(1);

async function heap(cdp) {
  await cdp.send('HeapProfiler.collectGarbage');
  await new Promise(r => setTimeout(r, 400));
  const { metrics } = await cdp.send('Performance.getMetrics');
  const m = Object.fromEntries(metrics.map(x => [x.name, x.value]));
  return { usedMB: MB(m.JSHeapUsedSize), totalMB: MB(m.JSHeapTotalSize), nodes: m.Nodes, listeners: m.JSEventListeners, documents: m.Documents };
}

// Count rAF frames for `ms` milliseconds; return fps, worst gap and long tasks.
async function sampleFrames(page, ms) {
  return page.evaluate(async (ms) => {
    const gaps = []; let last = performance.now(), frames = 0, longTasks = 0, longMs = 0;
    const po = new PerformanceObserver(list => { for (const e of list.getEntries()) { longTasks++; longMs += e.duration; } });
    try { po.observe({ type: 'longtask', buffered: false }); } catch (_) {}
    const end = performance.now() + ms;
    await new Promise(res => {
      const tick = () => { const n = performance.now(); gaps.push(n - last); last = n; frames++; if (n < end) requestAnimationFrame(tick); else res(); };
      requestAnimationFrame(tick);
    });
    po.disconnect();
    gaps.sort((a, b) => a - b);
    const p = q => gaps[Math.min(gaps.length - 1, Math.floor(q * gaps.length))];
    return { frames, seconds: ms / 1000, fps: +(frames / (ms / 1000)).toFixed(1), gapP50: +p(0.5).toFixed(1), gapP95: +p(0.95).toFixed(1), gapMax: +Math.max(...gaps).toFixed(1), longTasks, longTaskMs: Math.round(longMs) };
  }, ms);
}

(async () => {
  const browser = await L.launch();
  const out = { load: [], frames: {}, memory: {}, switchCountry: [], monthStep: [], errors: {} };

  // ---- 1. Cold load x3 (fresh context = empty cache) ----------------------------
  for (let i = 0; i < 3; i++) {
    const page = await L.newPage(browser, { w: 1440, h: 900, online: true });
    const t0 = Date.now();
    await page.goto(L.appUrl({ country: 'Zimbabwe', t: 63 }), { waitUntil: 'domcontentloaded' });
    const dcl = Date.now() - t0;
    await page.waitForFunction(() => window.APP && document.querySelector('#clock-date'));
    const appReady = Date.now() - t0;
    await page.waitForFunction(() => document.querySelector('#globe canvas'));
    const canvas = Date.now() - t0;
    await page.waitForLoadState('load');
    const loadEv = Date.now() - t0;
    await page.waitForTimeout(500);
    const nav = await page.evaluate(() => {
      const n = performance.getEntriesByType('navigation')[0];
      const res = performance.getEntriesByType('resource');
      const big = res.map(r => ({ name: r.name.split('/').slice(-2).join('/'), kb: Math.round((r.transferSize || r.encodedBodySize || 0) / 1024), ms: Math.round(r.duration) })).sort((a, b) => b.kb - a.kb).slice(0, 8);
      return { domContentLoaded: Math.round(n.domContentLoadedEventEnd), loadEvent: Math.round(n.loadEventEnd), resources: res.length,
        transferKB: Math.round(res.reduce((s, r) => s + (r.transferSize || 0), 0) / 1024), biggest: big,
        fcp: Math.round((performance.getEntriesByName('first-contentful-paint')[0] || {}).startTime || 0) };
    });
    out.load.push({ run: i + 1, dcl_ms: dcl, appReady_ms: appReady, canvas_ms: canvas, loadEvent_ms: loadEv, nav });
    out.errors[`load${i + 1}`] = page.errors;
    await page.context().close();
  }

  // ---- 2-4. One long-lived page for frames, memory and switching ------------------
  const page = await L.newPage(browser, { w: 1440, h: 900, online: true });
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Performance.enable');
  await cdp.send('HeapProfiler.enable');
  await L.gotoApp(page, { country: 'Zimbabwe', t: 0 }, { settle: 3000 });

  out.frames.idle_autoRotateOff = await sampleFrames(page, 3000);
  const setSpeed = s => page.click(`#speeds [data-speed="${s}"]`);
  const isPlaying = () => page.evaluate(() => !document.querySelector('.ic-pause').hidden);
  const month = () => page.evaluate(() => +document.querySelector('#scrub').value);

  await setSpeed(1);
  await page.click('#play');
  out.frames.play_1x = await sampleFrames(page, 5000);
  await page.click('#play');
  await setSpeed(4);
  await page.click('#play');
  out.frames.play_4x = await sampleFrames(page, 5000);
  await page.click('#play');
  // With the unit panel open and the feed filling (heaviest DOM path).
  await page.evaluate(() => { const li = document.querySelector('#feed .note:not(.decl)'); li && li.click(); });
  await page.waitForTimeout(500);
  await page.click('#play');
  out.frames.play_4x_panelOpen = await sampleFrames(page, 5000);
  await page.click('#play');
  await page.keyboard.press('Escape');

  // Memory: baseline, then two full 72-month playbacks at 4x.
  await page.evaluate(() => { document.querySelector('#scrub').value = '0'; document.querySelector('#scrub').dispatchEvent(new Event('input')); });
  await page.waitForTimeout(500);
  out.memory.baseline = await heap(cdp);
  const playFull = async () => {
    const t0 = Date.now();
    await page.click('#play');
    await page.waitForFunction(() => document.querySelector('.ic-pause').hidden && +document.querySelector('#scrub').value >= 71, null, { timeout: 90000 });
    return Date.now() - t0;
  };
  out.memory.pass1_ms = await playFull();
  out.memory.afterPass1 = await heap(cdp);
  out.memory.feedItemsAfterPass1 = await page.evaluate(() => document.querySelectorAll('#feed li').length);
  out.memory.pass2_ms = await playFull();
  out.memory.afterPass2 = await heap(cdp);
  out.memory.pass3_ms = await playFull();
  out.memory.afterPass3 = await heap(cdp);
  out.memory.growthPass1to3_MB = +(out.memory.afterPass3.usedMB - out.memory.afterPass1.usedMB).toFixed(1);
  out.memory.perfMemory = await page.evaluate(() => performance.memory ? { usedMB: Math.round(performance.memory.usedJSHeapSize / 1048576), limitMB: Math.round(performance.memory.jsHeapSizeLimit / 1048576) } : null);
  out.frames.after3Playbacks_idle = await sampleFrames(page, 3000);

  // Country switch: sync cost of selecting + time until the 2nd rAF after it.
  for (const name of ['Kenya', 'Malawi', 'Zambia', 'Zimbabwe', 'Kenya', 'Zimbabwe']) {
    await page.fill('#search', name);
    await page.waitForTimeout(150);
    const r = await page.evaluate(async (name) => {
      const li = [...document.querySelectorAll('#results li')].find(l => l.dataset.name === name);
      if (!li) return { error: 'no result for ' + name };
      const t0 = performance.now();
      li.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
      const t1 = performance.now();
      await new Promise(res => requestAnimationFrame(() => requestAnimationFrame(res)));
      const t2 = performance.now();
      // wait for the camera flight (1500 ms) + polygon tween (420 ms) to finish, then sample 1 s of frames
      await new Promise(res => setTimeout(res, 2000));
      return { sync_ms: +(t1 - t0).toFixed(1), toSecondFrame_ms: +(t2 - t0).toFixed(1), hud: document.querySelector('#hud-name').textContent, units: document.querySelector('#hud-sub').textContent };
    }, name);
    const fr = await sampleFrames(page, 1500);
    out.switchCountry.push({ to: name, ...r, fpsAfter: fr.fps, heap: (await heap(cdp)).usedMB });
  }
  // Month step cost (ArrowRight) at the crisis peak for the largest country (ZMB, 116 units).
  await L.gotoApp(page, { country: 'Zambia', t: 62, county: L.worstUnit('ZMB', 63) }, { settle: 2500 });
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
  for (let i = 0; i < 5; i++) {
    const r = await page.evaluate(async () => {
      const t0 = performance.now();
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', code: 'ArrowRight', bubbles: true }));
      const t1 = performance.now();
      await new Promise(res => requestAnimationFrame(() => requestAnimationFrame(res)));
      return { sync_ms: +(t1 - t0).toFixed(1), toSecondFrame_ms: +(performance.now() - t0).toFixed(1), month: document.querySelector('#clock-date').textContent };
    });
    out.monthStep.push(r);
    await page.waitForTimeout(500);
  }
  out.errors.main = page.errors;
  await page.context().close();

  const f = L.saveJSON('ui_results_perf.json', out);
  console.log('load:', out.load.map(l => `app ${l.appReady_ms}ms / load ${l.loadEvent_ms}ms / ${l.nav.transferKB}KB`).join(' | '));
  console.log('frames:', JSON.stringify(out.frames));
  console.log('memory:', JSON.stringify(out.memory));
  console.log('switch:', JSON.stringify(out.switchCountry));
  console.log('monthStep:', JSON.stringify(out.monthStep));
  console.log('errors:', JSON.stringify(Object.fromEntries(Object.entries(out.errors).map(([k, v]) => [k, { js: v.js.length, console: v.console.length, net: v.net.length }]))));
  console.log('->', f);
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
