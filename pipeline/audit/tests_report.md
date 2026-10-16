# Model test report (audit)

## Re-run 2026-10-16 18:01 UTC (alert engine v1.1 "spec mode", data/risk/*.js exported 17:50)

**Result: 93 passed, 1 failed** (`/home/looooo/bcg/.venv/bin/python -m pytest pipeline/tests/audit -q`, ~25 s).

`test_alert_rules.py` is rewritten for the v1.1 API: `families(df, in_season, in_rainy, crop_dom)`,
`raw_levels(fam, decl_in_force)`, `hysteresis(raw) -> (levels, held)`. It checks all 16 family mixes,
with and without a declaration in force. Levels must be: Warning = vegetation + (rain or soil),
Emergency = Warning + declaration, else Watch if any core family is on. Also checked: rain+soil
(even strong) never goes above Watch; heat alone never raises a level and is not counted in `agreeing`;
missing signals raise nothing; rain and soil are off outside the rainy season; vegetation needs VCI low in
2 months in a row; `p` is not an input to the level; hysteresis is exactly 2 up (to the min of the last 2)
and 3 down (to the max of the last 3); a 1-month spike is ignored; `held` == (raw < shown level);
no fast entry in export. All 76 pass. Labels (2-of-3 months rule), leakage, CV/hold-out and the
synthetic export all pass.

### Failure
**Emergency is shown outside the declaration season.** In real `data/risk/ZWE.js`, 46 units show
level 3 at t=66 (Jul 2024), and `held=true`. The declaration is in force only for t=63..65 (Apr-Jun 2024,
the end of agyear 2023/24). Cause: the 3-runs-down hysteresis keeps level 3 after `dif` turns off
(`pipeline/export_risk.py:132-134`). Test: `pipeline/tests/audit/test_export_contract.py:143`
(check at line 92). Possible fix: after hysteresis, cap the shown level at 2 where no declaration is in
force (`lvl = np.where((lvl == 3) & ~dif, 2, lvl)`). Or decide that a held Emergency is allowed for 2 months
and change the spec.

---

## Earlier run (17:27 UTC, before v1.1)


**Result: 109 passed, 0 failed** (`/home/looooo/bcg/.venv/bin/python -m pytest pipeline/tests/audit -q`, ~20 s).

Changes since the first run:
1. cant_plant is no longer modelled (rule-based Watch reason only). `test_labels.py` now checks that the
   modelled labels (`train.MODEL_EVENTS` = crop_failure, no_grass) depend only on vci_*; new
   `test_cv_holdout.py::test_no_model_trained_on_cant_plant` checks that no fit, bundle entry or OOF row
   exists for cant_plant. PASS.
2. Fast entry disabled: `pipeline/export_risk.py:32` `FAST_ENTRY = False`. The test now checks the
   production path (flag off, and the real ZWE.js meta says `fast_entry: false`). PASS. Note:
   `alert_engine.hysteresis(fast=...)` still has the 1-run path; it is only off because export_risk
   does not pass it.
3. `held` (bool) is now in CONTRACT.md section 3; the contract test accepts it and checks it is a bool and
   never true at level 0. Synthetic export and real `data/risk/ZWE.js` both PASS.

---

## First run (history)

Run: 2026-10-16 17:20 UTC, against pipeline code stable since 17:02 (labels.py, features.py, train.py,
alert_engine.py, export_risk.py). Tests: `pipeline/tests/audit/` (small SYNTHETIC data, invented numbers).

    /home/looooo/bcg/.venv/bin/python -m pytest pipeline/tests/audit -q      # ~1.5 min

**Result: 104 passed, 4 failed.**

| # | Area | File | Result |
|---|---|---|---|
| 1 | No future leakage (features) | test_features_leakage.py | PASS (7/7) |
| 2 | Labels depend only on vci_* | test_labels.py | **FAIL** (1 of 3) |
| 3 | CV by season year, hold-out unused | test_cv_holdout.py | PASS (5/5) |
| 4 | Alert rules + hysteresis | test_alert_rules.py | **FAIL** (1 of 91) |
| 5 | export_risk matches CONTRACT §3 | test_export_contract.py | **FAIL** (2 of 2) |

## What passed
- Features at r = W0 - lead do not change when every signal after r is scrambled (2021, 2023/24 r values;
  every make_xy row of the 2023/24 targets). Inside the 2001-2020 baseline, only `rain_pct3` moves; that is
  its fixed baseline normal (documented in features.py), not leakage. Also r < W0 and lead >= 1 always hold.
- CV: every fold drops exactly one agricultural year, years are distinct, no training set (fold or final)
  ever has a hold-out row. OOF rows are all agyear 2001-2022. Two garbage versions of the 2023/24 hold-out
  (garbage feature rows + labels; scrambled raw signals from 2023-08) give **identical** CV metrics, winner,
  thresholds and OOF table. Hold-out metrics do change (sanity check).
- Alert rules: no Warning without vegetation (all 16 family mixes x 3 p values); rain+soil(+heat) is Watch
  at most; heat alone adds nothing and never counts toward `agreeing`; missing signals never raise a family;
  vegetation is off out of season. Hysteresis without fast entry: a 1-month spike is ignored, a rise needs
  2 runs, a fall needs 3 runs, an interrupted fall resets (plus 30 random sequences).
- Real `data/risk/ZWE.js` (model `sat-v1-ensemble-ZWE_KEN_MWI_ZMB`, 91 units): **only** the `held` key is
  wrong. Without it, everything matches §3 (keys, 72 months, t, level, p, enums, agreeing = core families,
  drivers <= 3, signals, declaration t=63). Every rise to Warning+ has vegetation + (rain or soil).

## Failures
1. **Labels use non-VCI signals.** `cant_plant` = spi_1m < -1 AND sm1_z < -1.
   `pipeline/labels.py:42-43` (event_outcome) and `pipeline/labels.py:53` (_outcome_np).
   Test: `pipeline/tests/audit/test_labels.py:29`. crop_failure / no_grass use only vci_*.
   This is by design (see docstring, labels.py:9). But it means the cant_plant target is built from
   the same rain/soil signals the model and the rain/soil families use, so its skill is partly circular.
   Either accept it and say so, or change the rule.
2. **Fast entry breaks "2 runs up".** `pipeline/alert_engine.py:107-108` (`if r > level and fast[k]:
   level = min(r, level + 2)`). `pipeline/export_risk.py:129` turns it on when p >= p_fast
   (real thresholds file: p_fast = 0.775). Raw [0,3,0,0,0] with fast at t=1 gives levels [0,2,2,2,1]:
   Warning after one month. Test: `pipeline/tests/audit/test_alert_rules.py:140`.
3. **Extra `held` key in every series row** (not in CONTRACT §3). `pipeline/export_risk.py:150`.
   Tests: `pipeline/tests/audit/test_export_contract.py:121` (synthetic export) and `:136` (real ZWE.js).
   Fix: drop the key, or add `held` (bool) to CONTRACT.md §3 and tell the frontend.

## Notes (not failures)
- Hysteresis now moves one level per month (0 -> 1 -> 2), which is stricter than "2 runs up";
  fine with the spec.
- Emergency no longer uses the declaration date (good, no hindsight).
