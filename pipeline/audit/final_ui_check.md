# Final UI check (tests/e2e/final_ui.js, port 8801, Chrome headless)
Run: `node tests/e2e/final_ui.js` -> tests/e2e/final_results.json, screens/final_*.png (1440 + 390).
- PASS: 14 countries searchable, all LIVE, units render (geo = risk = legend count), 0 JS/console errors.
- PASS: ZWE Oct 2023 Mbire: FEWS +1..+3 Phase 2, +4..+7 Phase 3 (matches data/risk/ZWE.js), +8 pending; model layer, ML1->ML2 step, publication month, confidence labels.
- PASS: Feb 2024 +2/+3 hot counts match data (33 of 91 at threshold). Go to today -> Sep 2026; +1..+8 render.
- FAIL (minor) live month Sep 2026: all 91 units null at every lead; headline stat shows "0" (reads as zero districts at risk) and no "inputs missing" note, because js/app.js:175 `nul < tot` is false when everything is null. Legend does show "no forecast 91".
- Cosmetic: chart publication label shows "outlook published 2023-10" (raw) while rest of UI uses "Oct 2023".
- Data: live_t=92 forecast fields are all null in data/risk/ZWE.js.
