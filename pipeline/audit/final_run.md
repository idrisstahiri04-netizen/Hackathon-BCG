# Final run (2026-10-16)

js/app.js changes: Warning+ HUD count excludes urban rows (the national spark in js/real.js already did); district panel shows "town unit — no farmer/herder SMS" and the Watch reason in plain words; the feed shows the reason on Watch escalations.

| Check | Result | Note |
| --- | --- | --- |
| tests/e2e/final_ui.js | 17/18 PASS | FAIL `live_f1_f8_render_and_notes`: test still expects the "some inputs missing" live note, which is gone now that live forecasts are real. Stale assertion. 0 JS errors, 14 countries. |
| tests/e2e/forecast_view.js | FAIL 2 checks | `oct2023_all_leads_1_to_8` (data now has model leads 1-6, so +7/+8 are FEWS-only); `fews_layer` (legend has 5 phases, test expects 6). Stale assertions. 0 JS errors. |
| tests/e2e/demo_flow.js | PASS 26/26 steps x3 runs | own ports 8201/8202 |
| tests/e2e/sms_audit.js | PASS | 0 failures, 0 UI count mismatches |
| pytest backend | 260 pass, 5 fail | The 5 failures are live Claude calls (no network/key): test_live_injection x3, test_live_haiku x2 |
| pytest pipeline/tests | PASS 94/94 | |
| ?country=Zimbabwe&t=92&view=f2 | PASS | live month Sep 2026, 50 districts >= 57% chance by Nov 2026, real forecasts |
| Mbire Oct 2023 +4..+7 FEWS | PASS | Phase 3 Crisis Feb-May 2024 (ML2, published 2023-10) |
| Chart label "Oct 2023" / 14 countries / JS errors | PASS | 0 errors |
