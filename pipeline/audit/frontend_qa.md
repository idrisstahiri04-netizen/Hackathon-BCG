# Frontend + SMS QA — 2026-10-16

Browser: **Google Chrome 154** (`/opt/google/chrome/chrome`, run by Playwright MCP, so Playwright on the "chrome" channel). Claude-in-Chrome tools were not available in this session.
Server: `python3 -m http.server 8790`. Code tested: `js/app.js` (mtime 16:15), `js/real.js` (16:00), `index.html` (16:15). `js/live.js` changed again at 16:49 and 16:53, during testing.
Data: `data/risk/*.js` were re-exported **during** testing (16:52–16:54). For about 2 minutes KEN.js was an empty placeholder and Kenya correctly showed "DATA IN PROGRESS". Final checks ran on the 16:54 files.
Re-runnable: `node tests/e2e/sms_audit.js` (SMS) and `tests/e2e/frontend_checks.js` (load it in Playwright `browser_run_code_unsafe` by filename). Screenshots: `tests/e2e/screens/qa_*.png`.

## Results

| # | Check | Result | Notes |
|---|---|---|---|
| 1 | Zero console errors | **FAIL (env)** | No JS errors and no page errors. The only errors are `ERR_CONNECTION_REFUSED http://localhost:8000/health` while the SMS backend is down (js/live.js polls every 10 s). They go away when the backend runs. |
| 2 | Search Zimbabwe / Kenya / Malawi / Zambia | PASS | Each shows LIVE, Enter opens it, globe flies there |
| 3 | Unit count = geo file | PASS | ZWE 91, KEN 47, MWI 28, ZMB 116. HUD, legend sum, GEO_DATA and RISK_DATA all match. No missing ids. |
| 4 | Space / arrows / slider / speed | PASS (1 minor bug) | See B4 |
| 5 | Click a unit → panel | PASS | Kwekwe opened on a globe click; Esc closes it |
| 6 | Click feed item → jump | PASS | Seke at t=70: clock went to Nov 2024 and the panel opened |
| 7 | Deep links | PASS | ZWE Mbire t62, ZWE Binga t63, case-insensitive "uzumba maramba pfungwe", KEN Marsabit/Turkana, ZMB Sinazongwe, MWI Nsanje |
| 8 | Real data only: js/sim.js not used, no "simulated" text | PASS | sim.js is deleted, not in `document.scripts`, and `SIM` is undefined. The map view has no "simulat" text. The only match is the "Phone simulator" tab title (index.html:159). That is the SMS test phone, not data. Renaming it to "Test phone" would remove any doubt. |
| 9 | STUB country not LIVE | PASS | I changed MWI `model_version` to "STUB" through a Playwright route. Malawi then showed "DATA IN PROGRESS", no polygons, no disclaimer, stats "—", and deep link `?country=Malawi&t=62&county=Nsanje` showed nothing. A 404 risk file is handled the same way. |
| 10 | LIVE values match data/risk | PASS | 7 unit-months checked (level, p, agreeing, confidence, 4 signals, drivers, event), final check on the 16:54 data |
| 11 | Kenya SIM fallback | N/A | Removed by the real-data-only rule. Kenya now runs on real output. |
| 12 | Disclaimer | PASS | "Real satellite + weather data (CHIRPS, MODIS, ERA5). Risk levels from our model." It shows for every live country and is hidden for the others. |
| 13 | 390 px mobile layout | **FAIL** | See B1 |
| 14 | SMS audit | PASS (2 minor bugs) | See the SMS section |

## Bugs

**B1 (high, if mobile matters): no responsive layout.** `css/app.css` has no width media query. Only `css/live.css:269` has one, and it covers the live pages only.
Repro: viewport 390x844, open `?country=Zimbabwe&t=63&county=Binga`.
- The feed column is squeezed to 130 px.
- The HUD is 0 px wide (hidden).
- The detail panel (352 px) is cut off under the feed, so the SMS text and chips are cut.
- The slider track is nearly zero width.
- The speed buttons are hidden.
- The disclaimer overlaps the legend.
Screens: `qa_08_mobile390_detail.png`, `qa_09_mobile390_map.png`.

**B2 (medium, real-data rule): invented numbers on screen.**
- `js/app.js:438-441`: "SMS sent to date" = people × 0.11 × audiences/3. This is a made-up subscriber rate.
- `js/real.js:128-129`: the feed's "people" = pop × (0.25 + 0.20 × level). It is labelled as plain "people" and differs from the panel's population (e.g. Zvishavane Urban pop 0.05M shows as "0.03M people" in the feed).
- Suggested fix: hide the SMS stat, or take it from the backend. Show the real district population, or label the number as an estimate.

**B3 (low): the SMS counter ignores GSM-7 extension characters.** `js/app.js:576-578` puts `[ ] { } ^ ~ | € \` in the basic set, and `:684/686` uses `text.length` and 160 per segment (multi-part should be 153). Every `[link]` message costs 4 more septets than shown (e.g. "137 chars" is really 141). No message crosses 160 today, so the segment count is still right.

**B4 (low): Space does nothing while the slider has focus.** `js/app.js:314` returns for any `INPUT`, including `type=range`. Repro: drag the slider, then press Space. Playback does not start.

**B5 (low): the NGO driver is cut mid-phrase.** `js/real.js:74` uses `.slice(0, 40)`. Example: "3-month rainfall index -2.2 (well below . 2/3 families agree". Cut at a word boundary, or drop the bracket part.

**B6 (low, cosmetic): the panel covers other elements at 1440 px.** The detail panel overlaps the HUD subtitle (a stray "4" from "2024" shows) and the L0 row of the legend. Screen: `qa_02_zwe_binga_t63.png`.

**B7 (low): the declaration note drops out of the feed.** The feed keeps 120 DOM rows (`js/app.js:500`). A few months after the declaration, the OFFICIAL note is gone. Suggested fix: pin it.

**B8 (docs): README is out of date.**
- README.md:27 says KEN.js is an empty placeholder. It is real now.
- README.md:183 says six NGO messages run to 2 segments. The audit finds 0.
- The demo script says "Districts appear, all green". Final data for ZWE in Jan 2019: 40 Normal / 16 Watch / 31 Warning / 4 Emergency.

## Data findings (pipeline owner, not frontend; data as of 16:54)

- **Two-family rule broken.** About half of Warning+ rows have `agreeing < 2`, or no vegetation family: ZWE 217/428, KEN 220/441, MWI 43/86, ZMB 260/679. CONTRACT §3 says Warning needs vegetation + (rain or soil). The UI shows it as-is. Example: KEN Turkana t=48 is L3 EMERGENCY with "1/3 sources agree" (`qa_10_ken_turkana_L3_1of3.png`).
- **Levels skip steps.** Levels jump or drop 2+ steps in one month: ZWE 62 up / 103 down, ZMB 91 / 133, MWI 17 / 20. Example: ZWE Bikita t67→68 L2→L0. This is hard to square with "3 runs down".
- **Level and p disagree in many rows.** Under the earlier export, 724 rows had p ≥ 0.9 and ≥2 families agreeing but level < 2.

## SMS audit (`tests/e2e/sms_audit.js`)

Coverage: every routed audience × level 1–3 × event, over every real unit-month in all 4 countries, plus farmer/herder for every event at L2/L3. Total 29,363 messages and 37 audience/level/event combinations; longest names include "Uzumba Maramba Pfungwe" and "Centenary/ Muzarabani". The earlier, larger export (51 combinations, 63,901 messages) gave the same result.

- **Encoding:** all messages are GSM-7. `gsmSafe` strips accents and curly quotes.
- **Length:** 0 messages over 160 septets, counting the extension-character cost of `[link]`. Longest per audience: farmer 153–157, herder 150, coop 141–143, extension 139, ngo 135, foodbank 136, gov 131.
- **Farmers and herders get no probability:** 0 hits for `%`, `P(`, `0.x` or "risk N".
- **Reply codes:** every farmer and herder message has "Reply 1 ok 2 poor 3 …" and "STOP to quit". Institutional messages have no STOP. That is fine for B2B, but add it if they go to personal phones.
- **Routing:** herders get messages only when the event is no_grass, and farmers get them otherwise. Level 1 goes to extension, foodbank and ngo only.
- **Content notes:**
  - "[link]" is a literal placeholder. A real URL will change the length; with the headroom above, a link of up to about 15 characters still fits.
  - The extension template can say "WARNING … 0/3 sources agree". That comes from the two-family data bug above.
