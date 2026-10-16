# All automated tests — consolidated run

Run: 2026-10-16 ~18:40–18:59 UTC, branch `zimbabwe-real-data`, venv `/home/looooo/bcg/.venv`,
Python from venv, node v24.18.0, Playwright 1.59.1 (`tests/e2e/node_modules`), Chrome channel.
Live demo on :8000 / :8777 was left untouched (robustness boots its own uvicorn on free ports;
frontend checks used a temporary `http.server` on :8301, released afterwards).

| Suite | Result | Passed | Failed | Skipped / other | Duration |
| --- | --- | --- | --- | --- | --- |
| `pytest backend` (incl. `backend/tests/audit`, live Claude tests) | PASS | 232 | 0 | 1 xfail (expected) | 43.5 s |
| `pytest pipeline/tests` (incl. `pipeline/tests/audit`) | PASS | 94 | 0 | 0 | 91.4 s |
| `scripts/robustness_tests.py` (10 scenarios) | PASS | 10 | 0 | 0 | 121 s |
| `tests/e2e/sms_audit.js` (27,549 unit-months x audiences) | PASS | 37 combos, 0 overs | 0 | 0 | 2 s |
| `tests/e2e/frontend_checks.js` (Chrome, :8301) | PASS | 10 checks | 0 | 0 page/console errors | 68 s |
| `pipeline/audit/verify_signals.py --no-ee` | PASS | 35 PASS | 0 FAIL | 4 WARN (see below) | 32 s |
| `pipeline/audit/judge/judge.py` | PASS (after infra fix) | 4 countries | 0 | — | 89 s |
| `pipeline/audit/compare_ipc.py` | PASS (ran, exit 0) | ZWE 84/91 units matched | 0 | — | 16 s |
| Data sanity (geo<->risk ids, JSON parse, NaN, GSM-7) | PASS | 4 countries | 0 | — | <1 s |
| `bash -n scripts/*.sh` | PASS | 2 | 0 | — | <1 s |
| `python -m py_compile` all `.py` (excl. vendor) | PASS | 112 | 0 | — | 2 s |
| `node --check` (js/, tests/e2e/, data/geo, data/risk, data/*.js) | PASS | 16 | 0 | — | <1 s |
| Secret scan (working tree + full git history + dangling blobs) | PASS — no real key found | — | — | — | 5 s |

## Failures

None.

## Notes / observations

- **Test-infra fix (only change made):** `judge.py` first failed with
  `pipeline/audit/judge/judge.py:173 ModuleNotFoundError: No module named 'matplotlib'`.
  Installed `matplotlib 3.11.2` into `/home/looooo/bcg/.venv` (no source edited) and re-ran; it then
  completed and rewrote `judge_{ZWE,KEN,MWI,ZMB}.json/.png` and `units_*.csv`.
- **Expected xfail:** `backend/tests/audit/test_privacy.py::test_phone_not_stored_in_plaintext`
  (finding P2: phone stored in plaintext; flagged MUST-FIX for pilot, acceptable for demo).
- **Live Claude tests ran for real** (not skipped): `test_live_haiku_intents`,
  `test_live_sonnet_advice_goats`, `test_live_1/2/3_*` in `backend/tests/audit/test_live_injection.py`.
- **verify_signals WARNs (4):** NDVI crop/grass anomaly sign for 2024-01 and 2015-01 drought
  spot-checks is positive (median anom +0.02..+0.05) for the sampled units — worth a look by Signals,
  but the script classifies it as WARN, not FAIL. Report: `pipeline/audit/data_check.md`.
- **compare_ipc:** 7 ZWE units have no FEWS match (Harare Rural, Hwange Urban, Kariba Urban,
  Marondera Urban, Mvurwi, Plumtree, Redcliff). 2023/24 season: T-warn precision 0.78 / recall 0.61,
  median lead 21.7 weeks, 83% of hits >= 4 weeks lead.
- **Robustness highlights:** free-text p50 1.4 s / p95 2.4 s, burst 50 req OK, blackhole fallback
  19.2 s (one request over the 4 s UI timeout — already noted in the script's own `note`).
  Results: `pipeline/audit/out/robustness_results.json`.
- **SMS audit:** longest templates hit exactly 160 GSM-7 septets (ngo L1/L2/L3), 0 over-length,
  0 UCS-2 fallbacks, no probabilities in farmer/herder texts.
- **Data sanity:** ZWE 91, KEN 47, MWI 28, ZMB 116 units — geo ids == risk ids both ways;
  risk literals parse as strict JSON; 0 non-finite numbers (missing values are `null`, not 0/NaN);
  all `level` in 0..3 and `p` in [0,1]; series length == `meta.n_months`.
- `frontend_checks.js` is written for the Playwright MCP `browser_run_code_unsafe` and hardcodes
  `localhost:8790`; it was run from a temp copy with BASE rewritten to :8301 (source untouched).
- Working tree has many unrelated modified/untracked files from other agents (prices, dryspell,
  `backend/tests/conv/`, `tests/e2e/node_modules` + `package.json`); the only files this run wrote are
  the report outputs listed above and `pipeline/audit/all_tests.md`.
