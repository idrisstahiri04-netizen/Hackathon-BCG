# Code review — drought pipeline (branch zimbabwe-real-data)

Reviewer run: 2026-10-16 16:15–17:00 UTC. Scope: `pipeline/*.py`, `js/real.js`, `js/app.js`,
`data/geo/*.js`, `data/risk/*.js`. Every claim below was checked by running the code on the real
parquet / risk files (isolated copy in `/tmp/review_pipe`, outputs in `/tmp/review_out`,
`/tmp/review_risk`; nothing in the repo was modified). Only correctness issues are listed, ranked.

## What was verified and is correct (no action)

- `t=0` = Jan 2019; `decl_t` = 63 (Apr 2024) for ZWE, 32 / 62 / 61 for KEN / MWI / ZMB. `months_between`,
  `dateAt`, year ticks all agree.
- Season-year grouping: `agyear` (Jul–Jun) puts Nov 2023 planting, Jan–Mar 2024 crop and Apr–Jun 2024
  grass windows all in agyear 2023 (hold-out). ZWE/MWI/ZMB detected unimodal (core Dec–Feb); KEN 35/47
  bimodal (Apr, Sep). `off_plant` wrap-around (Nov planting, Dec core → −1) correct.
- Lags / trend / `rain_pct3` recomputed by hand for one ZWE unit: exact match.
- Sign conventions: every threshold is "lower SPI/NDVI/VCI/soil = worse", `heat` is `>= +1.5`.
- NaN handling: `_lt/_le/_ge` return False on NaN; `nanmin2` uses `fmin`; labels return NaN (not 0)
  when the window has no observation; `rnd()` → `null`; export uses `allow_nan=False`. No `NaN`/`Infinity`
  token in any `data/risk/*.js`; all four files parse in node; every unit has 72 rows with `t == index`.
- Unit ids: geo ⇄ parquet ⇄ risk sets identical for ZWE (91), KEN (47), MWI (28), ZMB (116); no duplicate
  names; all names ASCII, so the deep-link `byName` lower-case match works (`?county=Centenary/ Muzarabani`
  and `Murang'a` decode fine through URLSearchParams).
- Hysteresis: tested 8 edge sequences (0→2 needs 2 runs, 3→0 needs 3 runs, oscillation 1/2/1/2 stays 1,
  3→2,2,0 steps down to 2 then 0). Recomputed raw levels from the exported families/p/signals for all
  ZWE unit-months: 1540 of 6279 months have level > raw, **all 1540** explained by the 3-run hold; 0
  unexplained.
- SMS: longest template with the longest unit name ("Uzumba Maramba Pfungwe") is 158 GSM-7 chars,
  all templates GSM-7 safe (`gsmSafe` strips curly quotes/dashes/accents).
- Latency (new code): `apply_latency` shifts per unit with `groupby(level="unit_id").shift(1)` (value at
  issue month r describes r−1), labels are built from the unshifted `c.wide`, `source_of` leaves
  `crop_frac/grass_frac/month_sin/cos/lead/phase/bimodal` unshifted, and export's `_rainy` /
  `add_families` gates are shifted by the same lag. Consistent.

## Findings (ranked)

### 1. HIGH — Emergency rule is gated on the real declaration month (`alert_engine.raw_levels`, `export_risk.build`)
`after = (m.month-7)%12 >= decl_agm` makes Emergency (via `p >= p_emerg`) possible only in calendar
months ≥ the month the government actually declared — Apr–Jun for ZWE, Feb–Jun ZMB, Mar–Jun MWI,
Sep–Jun KEN — in **every** year. The pitch compares "when the model first warned" against the
declaration; this rule hard-codes the answer for Level 3 (the model can only reach Emergency at/after
the declaration month, except via the `extreme` path). It is also leakage of the target event into the
rule. Scenario: ZWE Mar 2024, p=0.9, vegetation+rain+soil all alarmed → still Warning; Apr 2024 same
inputs → Emergency. Fix: replace the gate with a season-phase gate derived from the detected season
(e.g. Emergency only from the crop window onward), or drop it and rely on `p_emerg` + hysteresis.
File: `pipeline/export_risk.py:103,116-118`, `pipeline/alert_engine.py:77`.

### 2. HIGH (fixed in the latest edit, verify after rerun) — Watch was almost always on
With the version that produced the current `data/risk/*.js` (Watch = any family OR p ≥ 0.25, thresholds
tuned to the grid edge p_watch = p_warn = 0.25), Watch covers 68% of all ZWE unit-months (80% KEN), all
91 ZWE units are already at level ≥1 at t=0, and `cv_f1_warn` = 0.25 ≈ base rate. The 16:33 edit
changes the rule to `(anyfam & p>=p_watch) | p>=p_warn` and constrains the alarm rate ≤ base rate; the
risk files in `data/risk/` were generated **before** that edit (16:28–16:31) and still carry the old
behaviour (`meta.metrics.thresholds = {0.25,0.25,0.75}`, no `data_latency_months`). Re-run
`train.py` + `export_risk.py` before the demo.

### 3. MEDIUM — Level ≥ 2 shown with empty `drivers` during hysteresis hold
181 ZWE (111 KEN, 33 MWI, 220 ZMB) unit-months are at Warning/Emergency with `drivers: []` because
`ae.drivers()` only emits text for families that are alarmed *this* month, while the level is held for
up to 3 months after the raw level fell. The detail panel then shows "WARNING … 0 drivers" and the NGO
SMS falls back to "dry conditions". Fix: in `export_risk.build`, when `lvl[k] > raw[k]` carry the last
non-empty drivers forward (or add a "holding: conditions easing" line). File: `pipeline/export_risk.py`
series loop (`"drivers": ae.drivers(s, f)`).

### 4. MEDIUM — Persistence baseline peeks past the feature month for bimodal units
`labels.build_targets` sets `prev_label` = previous instance of the same event regardless of season
index. For KEN units whose two seasons are 4 months apart (3 units) the previous window ends after
`r = W0−3`: 141 of 5869 KEN target rows (72 no_grass, 69 crop_failure). Only affects the `persistence`
model (not a winner) — fix by grouping `shift(1)` on `["unit_id","season","event"]`.

### 5. LOW — `export_risk.main` model auto-discovery breaks with a custom `--tag`
`next(f for f in cands if iso3 in f.stem.split("_")[1:])` raises a bare `StopIteration` when
`train.py --tag X` was used. Give a clear error or match on `bundle["iso3s"]`.

### 6. LOW — `pop_millions` rounded to 2 dp in `worldpop_pop.py`
Mvurwi (ZWE) exports `0.00`, which `prep_geo.num()` turns into `0.0`, so the UI prints "0.00M people"
instead of treating it as unknown. Use 3–4 dp or write persons.

### 7. LOW — Feed never shows a unit's state at t=0
`real.js build()` emits events only for `t >= 1`, so a unit already at Warning in Jan 2019 (after the
12-month warm-up) appears on the map but never in the alert feed; the "N alerts" counter undercounts.
Emit a synthetic escalation at t=0 when `series[0].level > 0`.

## Not bugs, but worth knowing
- `cant_plant` has no skill in CV (PR-AUC 0.168 vs base 0.168, every model); crop_failure Brier 0.244 vs
  0.249 for the base rate. The ensemble wins mainly on `no_grass`.
- `p == 0.000` appears for 39 ZWE unit-months (Jun 2022) — this is the isotonic calibrator's floor, not a
  NaN→0 conversion.
- KEN national Warning+ share peaks in May 2019 (0.64), only 0.15 around the Sep 2021 declaration.
