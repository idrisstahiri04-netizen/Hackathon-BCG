# Code review — drought pipeline (branch zimbabwe-real-data)

Reviewed 2026-10-16 16:15–18:05 UTC against the files as they stood after the 17:38 edits (stable ≥15 min)
and the `data/risk/*.js` regenerated 17:50. Scope: `pipeline/*.py`, `js/real.js`, `js/app.js`,
`data/geo/*.js`, `data/risk/*.js`. Every claim was checked by running code on the real parquet / risk
files (isolated copy in `/tmp/review_pipe`; nothing in the repo was modified except this file).
Only correctness issues are listed, ranked by severity.

## Findings

### 1. HIGH — `pipeline/tests/audit/test_alert_rules.py` is broken by the alert-engine API change
`alert_engine.raw_levels` is now `raw_levels(fam, decl_in_force=None)` and `hysteresis` returns
`(levels, held)`; the test adapter (`test_alert_rules.py:14-22, 41-42, 86-88`) still calls
`raw_levels(fam, p, s, after_decl, th)`. `pytest pipeline/tests/audit` → **56 failed, 53 passed**; all 56
are in `test_alert_rules.py`, all with `TypeError: raw_levels() takes from 1 to 2 positional arguments
but 4 were given` (the other four audit files pass). The rule tests (Warning needs vegetation + weather,
hysteresis, NaN never alarms) therefore give **no coverage** of the v1.1 engine.
Fix: adapter → `A.raw_levels(fam, [after_decl])`, `lvl, _ = A.hysteresis(raw)`.

### 2. MEDIUM — Emergency is defined by the real declaration date (design, but affects the pitch)
`export_risk.build`: `dif = (m >= decl_m) and agyear(m) == agyear(decl_m)`; `conditions()`:
`emerg = warn & dif`. Level 3 can only appear from the official declaration month to the end of that
agricultural year (ZWE Apr–Jun 2024). Verified in output: ZWE Emergency months are May/Jun/Jul only
(Jul = hysteresis hold). Consequences: (a) the demo's "model warned before the government" comparison
must be made on **Warning**, never Emergency; (b) with the v1.1 rule + 1-month latency the ZWE Warning+
share is 0.08 in Mar 2024 and 0.24 in Apr 2024 (declaration 3 Apr), 0.55 in May — the lead over the
declaration is one month at best. Not a code bug; `meta.metrics.alert_rule` documents it. Make sure
slides say so.

### 3. MEDIUM — Units jump 0/1 → Emergency without ever being at Warning
Spec hysteresis has no one-step limit, so a unit whose raw level is 3 for two months goes straight to
L3: 28 ZWE, 48 ZMB, 14 KEN unit-months. Farmers (minLevel 2) then receive the EMERGENCY text as their
first message. `hysteresis(..., one_step=True)` exists but is off. Decide explicitly; if kept, say so in
the pitch.

### 4. LOW — Stale callers of `train.add_families` ignore `crop_dom`
`pipeline/experiments/expand.py:43`, `harness.py:74` call `add_families(X, P["ss"])` → `crop_dom or {}`
→ every unit treated as grassland for the vegetation family. Experiments silently use a different rule
than train/export. Pass `crop_dominant(P["c"])`.

### 5. LOW — Persistence baseline peeks past the feature month for bimodal units
`labels.build_targets` sets `prev_label` = previous instance of the same event regardless of season
index. For KEN units whose seasons are 4 months apart the previous window ends after `r = W0−3`:
141 of 5869 KEN target rows. Only affects the `persistence` baseline. Group the `shift(1)` on
`["unit_id","season","event"]`.

### 6. LOW — `export_risk.main` model auto-discovery dies on a custom `--tag`
`next(f for f in cands if iso3 in f.stem.split("_")[1:])` raises bare `StopIteration` when `train.py
--tag X` was used. Match on `bundle["iso3s"]` or print a clear error.

### 7. LOW — `worldpop_pop.py` rounds `pop_millions` to 2 dp
Mvurwi (ZWE) exports `0.00` → `prep_geo.num()` → `0.0` → UI "population 0". Write 3–4 dp or persons.

### 8. LOW — Feed never shows a unit's state at t=0
`real.js build()` emits events for `t ≥ 1` only; 72 ZWE / 58 ZMB units are already at level ≥1 in
Jan 2019 (12-month warm-up) and appear coloured on the map with no feed entry and an undercounted
"alerts" total. Emit a synthetic escalation at t=0 when `series[0].level > 0`.

## Verified correct (no action)
- Month indexing: t=0 = Jan 2019; `decl_t` 63/32/62/61 (ZWE/KEN/MWI/ZMB) match the dates.
- Season-year grouping: `agyear` Jul–Jun; ZWE Nov 2023 planting, Jan–Mar 2024 crop, Apr–Jun 2024 grass all
  → agyear 2023 (hold-out). ZWE/MWI/ZMB unimodal (core Dec–Feb), KEN 35/47 bimodal (Apr, Sep). `off_plant`
  wrap-around correct. `dif` for KEN = Sep 2021–Jun 2022.
- Latency: `apply_latency` shifts per unit (`groupby(level="unit_id").shift(1)`) so month r uses r−1;
  labels built from unshifted `c.wide`; static/calendar/lead columns unshifted; `vci_*_l1` (r−2) consistent
  between train (`feat`) and export (`du.shift(1)`); `_rainy`/`add_families` gates shifted identically.
- Lags, trend and `rain_pct3` recomputed by hand for one ZWE unit: exact match.
- Sign conventions: lower SPI/NDVI-z/VCI/soil-z = worse everywhere; heat `≥ +1.5`.
- NaN: `_lt/_le/_ge` → False on NaN; labels NaN when < 2 valid months; `p` exported as `null` (36 rows
  KEN+ZMB, no candidate window within 6 months) and handled in `real.js`/`app.js` (`—`, `n/a`);
  `allow_nan=False`; no `NaN`/`Infinity` token in any risk file; all parse in node; 72 rows per unit,
  `t == index`.
- Unit ids identical across geo ⇄ parquet ⇄ risk (91/47/28/116); no duplicate or non-ASCII names, so the
  deep-link `byName` match works (`Centenary/ Muzarabani`, `Murang'a` decode fine).
- Rule/hysteresis consistency on the exported files: 0 rows with level ≥2, `held=false` and the Warning
  rule unsatisfied; 0 rows with level ≥1, `held=false`, `agreeing=0`; `held` never true at level 0; every
  non-held level ≥2 row has drivers. Hysteresis edge sequences (0→2 needs 2 runs, 3→0 needs 3, 1/2/1/2
  oscillation stays 1) behave as specified.
- SMS: worst case per audience with the longest name ("Uzumba Maramba Pfungwe") is 133–160 septets, all
  GSM-7 (`[link]` brackets counted as 2); NGO text hits exactly 160 with the "level held" variant.

## Worth knowing (not bugs)
- `cant_plant` model dropped for no CV skill — correct call; crop_failure PR-AUC 0.27 vs base 0.20 and
  no_grass 0.40 vs 0.29 are modest. Spec Warning rule on CV rows: precision 0.34, recall 0.10.
- `data/risk/*.js` in the repo now match the v1.1 code (`alert_rule`, `held`, `data_latency_months`
  present); `pipeline/out/model_report.md` was regenerated 17:49.
