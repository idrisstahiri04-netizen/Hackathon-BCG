// Frontend smoke checks. Run with the Playwright MCP tool browser_run_code_unsafe
// (filename: tests/e2e/frontend_checks.js) against `python3 -m http.server 8790`.
// Returns a JSON object of pass/fail per check. Read-only: changes nothing on disk.
async (page) => {
  const BASE = 'http://localhost:8790/';
  const res = {}; const pageErrors = []; const consoleErrors = [];
  page.on('pageerror', e => pageErrors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text() + ' ' + (m.location().url || '')); });
  await page.setViewportSize({ width: 1440, height: 900 });
  const go = async (url) => { await page.goto(url, { waitUntil: 'load' }); await page.waitForFunction(() => window.GEO_DATA && window.RISK_DATA && document.querySelector('#clock-date')); await page.waitForTimeout(1500); };

  // 1. Each live country: unit count in HUD and legend == geo file == risk file; disclaimer; no sim text.
  for (const [name, iso] of [['Zimbabwe', 'ZWE'], ['Kenya', 'KEN'], ['Malawi', 'MWI'], ['Zambia', 'ZMB']]) {
    await go(`${BASE}?country=${name}`);
    res[`count_${iso}`] = await page.evaluate((iso) => {
      const geoN = GEO_DATA[iso].features.length, riskN = RISK_DATA[iso].units.length;
      const hudN = parseInt(document.querySelector('#hud-sub').textContent, 10);
      const legendN = [...document.querySelectorAll('#legend-items li')].map(li => +li.innerText.trim().split('\n').pop()).reduce((a, b) => a + b, 0);
      const disc = document.querySelector('#disclaimer');
      return { pass: geoN === riskN && hudN === geoN && legendN === geoN && !disc.hidden && !/simulat/i.test(document.body.innerText),
        geoN, riskN, hudN, legendN, disclaimer: disc.textContent, simLoaded: typeof SIM !== 'undefined' };
    }, iso);
  }

  // 2. Values on screen match data/risk for spot-check units.
  for (const [c, iso, t, u] of [['Zimbabwe', 'ZWE', 62, 'Mbire'], ['Kenya', 'KEN', 48, 'Turkana'], ['Zambia', 'ZMB', 61, 'Sinazongwe'], ['Malawi', 'MWI', 62, 'Nsanje']]) {
    await go(`${BASE}?country=${c}&t=${t}&county=${u}`);
    res[`spot_${iso}_${u}_${t}`] = await page.evaluate(([iso, t, u]) => {
      const d = document.querySelector('#detail'); if (d.hidden) return { pass: false, why: 'panel hidden' };
      const r = RISK_DATA[iso].units.find(x => x.name === u).series[t];
      const big = [...d.querySelectorAll('.big')].map(x => x.textContent);
      const chip = d.querySelector('.chip').textContent;
      const ok = big[0] === `${Math.round(r.p * 100)}%` && big[1] === `${r.agreeing}/3` && chip.includes(`L${r.level}`);
      return { pass: ok, ui: { big, chip }, data: { p: r.p, agreeing: r.agreeing, level: r.level } };
    }, [iso, t, u]);
  }

  // 3. Keyboard + slider.
  await go(`${BASE}?country=Zimbabwe`);
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
  await page.keyboard.press('ArrowRight'); await page.keyboard.press('ArrowRight'); await page.keyboard.press('ArrowLeft');
  const s1 = await page.inputValue('#scrub');
  await page.keyboard.press('Space'); await page.waitForTimeout(2100); await page.keyboard.press('Space');
  const s2 = await page.inputValue('#scrub');
  await page.locator('#scrub').fill('63'); await page.waitForTimeout(300);
  res.keys_slider = { pass: s1 === '1' && +s2 > 1 && (await page.textContent('#clock-date')) === 'Apr 2024', afterArrows: s1, afterPlay: s2 };

  // 4. STUB country is not LIVE.
  await page.route('**/data/risk/MWI.js', async route => {
    const r = await route.fetch(); const body = (await r.text()).replace(/"model_version":"[^"]*"/, '"model_version":"STUB"');
    await route.fulfill({ response: r, body });
  });
  await go(BASE); await page.click('#search'); await page.waitForTimeout(200);
  const list = await page.locator('#results li').allInnerTexts();
  res.stub_not_live = { pass: list.some(x => /Malawi/.test(x) && !/LIVE$/i.test(x.trim())), list };
  await page.unrouteAll();

  res.pageErrors = pageErrors;
  res.consoleErrors = consoleErrors;
  return res;
}
