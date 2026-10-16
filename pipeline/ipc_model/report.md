# IPC-target model — report

Code: `pipeline/ipc_model/{ipc_data.py,train_ipc.py}`. Trained on Kaggle (kernel `drought-ipc`,
`pipeline/out/kaggle/20261016T182039Z/`, 186 s). Outputs copied to `pipeline/ipc_model/out/`
(`tables.md` = every table, `metrics.json`, `replay_ZWE_*.csv`, `replay_ZWE_monthly.csv`, `importance.csv`).
Nothing was tuned on the hold-out; it was scored once. Nothing committed.

## What is predicted
`y_h13` = district is in FEWS NET IPC Phase 3+ (Current Situation) in any of months t+1..t+3 after issue
month t; `y_h46` = months t+4..t+6. Issue t = end of month t.

**Truth construction (documented choice).** CS maps exist ~3x/year (Feb, Jun, Oct; Dec 2018 instead of Oct 2018).
District phase = max over its livelihood-zone pieces (as `audit/compare_ipc.py`). The phase of a map is
carried forward month by month until the next map (ffill, limit 5 months). No back-fill, no interpolation
between phases: a district that moves 2 -> 3 between maps "enters" at the month of the map that shows it.
So lead times are measured to the map month and are upper bounds; a conservative lead (onset right after
the previous map, i.e. minus 3 months) is also given. Unit matching: ZWE 84/91 (same 7 small urban units
unmatched as the audit), MWI 28/28, KEN 47/47 counties (any element of the FEWS name that is a county; county
phase = max over many pieces, generous). ZMB excluded: its FEWS IPC stops 2017-10 and never shows Phase 3+.
ZWE labels reproduce ground_truth.md exactly (27 districts IPC3+ in Oct 2023, 57 transitions: 15 Feb, 3 Jun, 39 Oct 2024).

**Inputs, all known at issue t:** signals via `common.apply_latency` (1-month lag), NMME MME3 seasonal
forecast issued in t, ONI of the trimester ending t-1, FEWS NET outlook text (`outlook_<ISO3>.parquet`,
publish month <= t, latest report within 3 months; ZWE only — MWI has 2023-24 only, KEN/ZMB none), FEWS NET FDW
ML1/ML2 projections (reporting month <= t-1), lagged IPC state (CS phase at t-1 + history). `prices_<ISO3>.parquet`
hook is in place but the file did not exist at run time, so no price feature was used.

Three feature sets: **eo** (signals + seasonal forecast + ONI + statics), **eo_fews** (eo + FEWS text/FDW
projections, no IPC state), **full** (eo_fews + lagged IPC state). Models per set: logreg, LightGBM (400 trees,
fixed params), ensemble = mean of calibrated probabilities. Baselines: persistence (lagged phase only), fews
(FEWS NET's own projection overlapping the horizon). Cross-fitted isotonic calibration. CV = leave-one-season-out
2015/16..2022/23 (KEN only to 2019/20), with training rows whose label window reaches into the held-out season
purged. Hold-out = ZWE/MWI 2023/24+, KEN 2020-24. Rows: 12,282 CV / 4,554 hold-out with known state (h13).

## Results (ROC-AUC / PR-AUC on raw score / Brier on calibrated p)

**CV, pooled, h13.** "transition rows" = known state < IPC3 at issue (the early-warning case).

| model | all rows (base 0.331) | transition rows (base 0.157) | PR 5-95 % season bootstrap (transition) |
|---|---|---|---|
| persistence | 0.847 / 0.670 / 0.136 | 0.709 / 0.255 / 0.123 | 0.20-0.32 |
| fews (FEWS NET projection) | 0.903 / 0.757 / 0.097 | 0.863 / 0.525 / 0.089 | 0.45-0.62 |
| eo:lgbm | 0.780 / 0.626 / 0.180 | 0.742 / 0.349 / 0.145 | 0.30-0.42 |
| eo_fews:lgbm | 0.916 / 0.840 / 0.105 | **0.868 / 0.600 / 0.093** | 0.47-0.72 |
| full:lgbm | **0.921 / 0.869 / 0.101** | 0.849 / 0.494 / 0.096 | 0.38-0.66 |

ZWE-only CV transition rows (base 0.221): persistence 0.627/0.279, fews 0.826/0.559, eo:ens 0.675/0.351,
eo_fews:ens 0.799/0.590, full:ens 0.775/0.486. ZWE skill varies a lot by season: 2019/20 nobody beats
chance (full 0.54, fews 0.52, eo 0.45), 2022/23 and 2015/16 are easy (>0.95).
h46 CV transition rows (base 0.214): persistence 0.687/0.317, fews 0.839/0.620 (n 5,407 only), eo:lgbm 0.722/0.427,
eo_fews:lgbm 0.810/0.589, full:lgbm 0.795/0.581.

**Hold-out (once), h13 transition rows.** Pooled (base 0.150): persistence 0.781/0.288, fews 0.938/0.735,
eo:lgbm 0.887/0.521, eo_fews:lgbm 0.944/0.751, full:lgbm 0.948/0.720.
ZWE 2023/24 (n 888, base 0.378): persistence 0.525/0.391/0.243, **fews 0.981/0.967/0.034**, eo:lgbm 0.734/0.579/0.204,
eo_fews:lgbm 0.939/0.917/0.114, full:lgbm 0.971/0.954/0.114. MWI (base 0.227): eo 0.769/0.456, eo_fews 0.922/0.799,
full 0.914/0.715, persistence 0.880/0.582. KEN (base 0.042): eo 0.891/0.289, eo_fews 0.933/0.361, persistence 0.842/0.122.
h46 ZWE transition (base 0.571): eo 0.635/0.745, eo_fews 0.890/0.926, full 0.873/0.917, persistence 0.537/0.590.

**CV-tuned thresholds (transition rows, max F1; applied unchanged to the replay):**
eo:lgbm 0.36 (CV precision 0.32, recall 0.56, alarm rate 28 %); eo_fews:lgbm 0.31 (0.575 / 0.715 / 20 %);
full:lgbm 0.27 (0.54 / 0.70 / 21 %). A precision >= 0.6 point exists only for eo_fews (thr 0.57: 0.60 / 0.62).

## Replay ZWE 2023/24 (h13, CV thresholds)
Season window = issues Oct 2023 .. Sep 2024; a crossing counts only while the district's *known* state is
still < IPC3 (before FEWS NET published Crisis for it). 57 transitions, 0 calm districts (all 84 were IPC3+
by Oct 2024), so the replay measures timing and coverage only, not false alarms.

| model (thr) | transitions crossed | crossed before 2024-04-03 (2 runs) | first crossing months | median lead to map (conservative) |
|---|---|---|---|---|
| eo:lgbm (0.36) | 54/57 | 36 (34) | Oct-23 35, Jun-24 14 | 4 mo (1 mo) |
| eo_fews:lgbm (0.31) | 57/57 | 34 (21) | Nov-Dec-23 26, Mar-May-24 21 | 5 mo (2 mo) |
| full:lgbm (0.27) | 57/57 | 44 (23) | Oct-Dec-23 35, Mar-May-24 19 | 6 mo (3 mo) |
| FEWS NET own projection | 56/57 | 15 | — | 3 mo |

Reading: the FEWS-informed models flag most Feb-2024 entrants in Nov-Dec 2023 (issued ~4 months before the
declaration, 2-3 months before the Feb map) and the Oct-2024 entrants in Mar-May 2024. The eo-only model
crossed in 35 districts already at the Oct 2023 issue, but its early-season alarm rate is not season-specific:
among not-yet-Crisis ZWE districts at Oct-Dec issues it was >= 0.36 in 65 % of 2023/24, 72 % of 2021/22 (La Niña,
y13 0.34) and 58 % of 2017/18 (y13 0.15). Its LightGBM gain is led by grass_frac, crop_frac, south, ONI — chronic
geography plus ENSO, not in-season satellite dynamics. Mean calibrated p of the eo model in ZWE was 0.4-0.6 every
month of 2023/24: directionally right for a season where every district went IPC3+, but it does not rank districts.
MWI 2023/24 (full, thr 0.27): 4/4 transitions flagged, 1 before the declaration, 2 false alarms among 10 calm districts.

## Caveats
1. FEWS NET projection features dominate (top 3 gains in eo_fews/full are fdw_ml1, fdw_ml2, fdw_ml1_share3). On the
   2023/24 hold-out FEWS NET's own projection alone (ROC 0.98, Brier 0.034) beats every model; our added value is
   turning projections + weather into a calibrated monthly district probability, not beating FEWS NET.
2. Adding the lagged IPC state (full) helps "all rows" (persistence) but slightly hurts transition-row ranking vs eo_fews.
3. Truth is 3 maps/year; "entry month" is binned; leads to the map are upper bounds (conservative values given).
4. KEN county = max over many pieces; ZMB has no truth; 7 ZWE urban units have none. No prices were available.
5. One hold-out season for ZWE/MWI; the season bootstrap on CV shows wide PR-AUC intervals (eo 0.30-0.42, eo_fews 0.47-0.72).

## Recommendation
Complement, do not replace. Levels stay with the spec family rule. Use the **eo_fews** calibrated p_h13 as the
"chance of Crisis within 3 months" shown to NGOs/government and as an NGO-only Watch trigger at thr 0.31 (or 0.57 for
a precision-first list); it needs the FEWS NET outlook/FDW feed (announcement family) and so may never raise a public
level above 1 on its own. Show p_h46 only as a season-level indication. Do not show the eo-only p as a district
probability: CV precision 0.32 at 28 % alarm rate, and it flags whole seasons regardless of ENSO. Keep the current
satellite p for the drought-event narrative; add "FEWS NET IPC3+ projection within 1-3 months: NN %" as a second,
clearly labelled number. When `prices_<ISO3>.parquet` exists, rebuild rows and re-run on Kaggle (hook is in place).
