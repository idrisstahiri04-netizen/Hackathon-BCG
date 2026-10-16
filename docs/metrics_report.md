# Model metrics report — drought early warning (satellite + weather)

Date: 2026-10-16 · Model: `sat-v1-ensemble-ZWE_KEN_MWI_ZMB` · Branch: `zimbabwe-real-data`
Sources: `pipeline/out/model_report.md`, `pipeline/out/thresholds_ZWE_KEN_MWI_ZMB.json`, `pipeline/audit/ground_truth.md`, `pipeline/audit/judge/verdict.md`, `pipeline/out/timesfm_report.md`, `pipeline/audit/data_check.md`.

> Status: final export with realistic data latency (signals of month t-1 used at month t) the one-step-per-month rule and NO fast entry (spec: 2 months to go up). Sections 5–6 re-run on this final export.


## 0. Latest — v1.1 "spec mode" (supersedes sections 4–6 and 9 for alert results)

Levels from the spec family rule + hysteresis (2 up / 3 down, no probability gate, no fast entry, `held` flag); Emergency only = Warning + official declaration in force; soil gated to rainy season; vegetation tightened (fires in 15.5% of normal growing-season months); labels = 2 of 3 core months VCI < 35. Probability shown to NGOs only.

| Country (declaration) | Warning before decl. (median lead) | Watch before decl. (median lead) |
|---|---|---|
| Zimbabwe (2024-04-03) | **7/91 (4.7 wk)** | **53/91 (8.9 wk)** |
| Zambia (2024-02-29) | 7/116 (4.0 wk) | 52/116 (4.0 wk) |
| Malawi (2024-03-23) | 3/28 (3.1 wk) | 20/28 (3.1 wk) |
| Kenya (2021-09-08) | 6/47 (7.6 wk) | 23/47 (18.6 wk) |

| vs FEWS NET IPC3+ | Warning precision / recall | Persistence |
|---|---|---|
| Zimbabwe 2023/24 | **0.78 / 0.61** (35 hits, 10 FA, 22 misses) | 0.43 / 0.35 |
| Zimbabwe all seasons 2019/20–2023/24 | 0.71 / 0.28 | 0.24 / 0.44 |
| Malawi all seasons | 0.07 / 0.08 (no skill) | 0.07 / 0.12 |

False Warnings: Zimbabwe wet 2020/21 = 0 (Watch 3% of districts); 2019/20 = 12 and 2021/22 = 6 unit-months. Probability model (stricter labels) CV mean PR-AUC: ensemble 0.338 vs persistence 0.267 (base rates 0.20 crop / 0.29 grass).

## 1. What is predicted

| Item | Value |
|---|---|
| Countries | Zimbabwe (91 districts), Kenya (47), Malawi (28), Zambia (116) |
| Inputs | CHIRPS v3 rain (SPI 1/3/6), MODIS NDVI/EVI/VCI on crop + grass land, ERA5-Land soil moisture + temperature, lags/trends, season phase |
| Targets (satellite-only) | **crop_failure**: min cropland VCI < 35 in the growing core · **no_grass**: min grassland VCI < 35 after the rains · (cant_plant dropped: no skill) |
| Lead | 1–3 months ahead |
| Training | 2001–2022, 4 countries pooled, 80,648 rows |
| Validation | Leave-one-agricultural-year-out (22 folds) |
| Hidden test | 2023/24 season (+ Kenya 2020–22), 7,708 rows, scored once |
| Models compared | persistence, rules, logistic regression, LightGBM, ensemble (winner by CV PR-AUC) |

How to read: **ROC-AUC** 0.5 = chance, 1 = perfect · **PR-AUC** compare to base rate · **Brier** lower is better.

## 2. Cross-validation (2001–2022, pooled, leads 1–3)

| Model | crop_failure ROC / PR / Brier | no_grass ROC / PR / Brier | mean PR-AUC |
|---|---|---|---|
| Persistence | 0.562 / 0.514 / 0.249 | 0.547 / 0.440 / 0.246 | 0.477 |
| Rules | 0.514 / 0.492 / 0.252 | 0.536 / 0.436 / 0.248 | 0.464 |
| Logistic regression | 0.574 / 0.558 / 0.249 | 0.608 / 0.526 / 0.240 | 0.542 |
| LightGBM | 0.554 / 0.518 / 0.252 | 0.615 / 0.550 / 0.237 | 0.534 |
| **Ensemble (chosen)** | **0.571 / 0.546 / 0.250** | **0.620 / 0.553 / 0.237** | **0.550** |
| Base rate | 0.478 | 0.414 | |

### By lead (ensemble)

| Lead | crop_failure ROC / PR | no_grass ROC / PR |
|---|---|---|
| 1 month | 0.580 / 0.561 | **0.677 / 0.607** |
| 2 months | 0.577 / 0.539 | 0.626 / 0.554 |
| 3 months | 0.557 / 0.539 | 0.551 / 0.495 |

### Kenya by its own seasons (ensemble)

| Season | crop_failure ROC / PR (base) | no_grass ROC / PR (base) |
|---|---|---|
| MAM long rains | 0.523 / 0.488 (0.488) | 0.634 / 0.630 (0.483) |
| OND short rains | 0.491 / 0.524 (0.532) | 0.623 / 0.778 (0.683) |

**Reading:** small but real gain over baselines; best for herders (no_grass) at 1 month; crop_failure weak.

## 3. Hidden test — 2023/24 (scored once)

| Country | Ensemble crop ROC / PR (base) | Ensemble grass ROC / PR (base) | Best model on hold-out |
|---|---|---|---|
| All | 0.459 / 0.560 (0.563) | 0.657 / 0.744 (0.597) | rules / LightGBM |
| Zimbabwe | 0.543 / 0.779 (0.758) | 0.551 / 0.903 (0.879) | logistic (≈ all equal) |
| Kenya | 0.597 / 0.472 (0.390) | **0.794 / 0.779 (0.445)** | LightGBM / ensemble |
| Malawi | 0.321 / 0.780 (0.857) | 0.526 / 0.752 (0.714) | rules |
| Zambia | 0.280 / 0.764 (0.836) | 0.575 / 0.835 (0.776) | rules |

Caveat: in ZWE/MWI/ZMB almost every district was in drought in 2023/24, so AUC only measures ranking within a drought year. Kenya grass is the clear win.

## 4. Alert levels (CV, thresholds tuned on out-of-fold predictions only)

| Level | Threshold p | Precision | Recall | Share of unit-months |
|---|---|---|---|---|
| Watch | 0.525 (or strong rain + soil dryness) | 0.558 | 0.264 | 21.1% |
| Warning (vegetation + rain/soil) | 0.50 | 0.555 | 0.067 | 5.4% |
| Emergency | 0.95 + severe signal | 0.611 | 0.008 | 0.6% |
| Fast entry (1-month rise) | disabled (spec) | – | – | – |

Base rate 0.446. Levels move one step per month; up needs 2 months, down needs 3 (rows kept only by this rule are flagged `held`).

## 5. Against real crises — FEWS NET IPC Phase 3+, Zimbabwe

| Check | Our Warning | Persistence |
|---|---|---|
| 2023/24 transitions: precision / recall | **0.74 / 0.40** (23 hits, 8 false alarms, 34 misses) | 0.426 / 0.351 |
| All seasons 2019/20–2023/24: precision / recall | 0.71 / 0.18 | 0.238 / 0.440 |

Without data latency recall was 0.93 — most of that came from March/April data not available before the 3 April 2024 declaration. Not used in the pitch.

## 6. Replay — warnings before the official declaration

| Country (declaration) | Warning before declaration | Median lead | Watch before declaration | Wet/normal-season Warning unit-months |
|---|---|---|---|---|
| Zimbabwe (2024-04-03) | **0/91 (0%)** | n/a (first Warnings from April data) | 26/91 (median 15.4 wk ahead) | 2020/21 wet: 0 |
| Zambia (2024-02-29) | 3/116 (2.6%) | 4 wk | 71/116 | normal seasons: 6 / 36 / 14 |
| Malawi (2024-03-23) | 2/28 (7.1%) | 3.1 wk | 19/28 | 2018/19 wet: 0, 2022/23 wet: 0 |
| Kenya (2021-09-08) | **6/47 (12.8%)** | **8 wk** | 41/47 | 2019/20 wet: 0, 2023/24 wet: 4 |

Watch selectivity: Zimbabwe Watch is 17.2% of unit-months (was 69% in v1); 9–10% of districts in normal 2019/20 and wet 2020/21. Still broad in Zambia (43%) and Kenya (45%).

## 7. Challenger: TimesFM (Google, zero-shot), Zimbabwe vci_crop

| Lead | MAE TimesFM / persistence / climatology | Hit rate VCI<35 TimesFM / persistence |
|---|---|---|
| 1 (2015–22) | 15.4 / 16.3 / 23.8 | 0.69 / 0.72 |
| 3 (2015–22) | 22.2 / 26.0 / 23.9 | 0.41 / 0.53 |
| 1 (2023/24) | 21.0 / 22.0 / – | 0.48 / 0.52 |

Lowest error but shrinks toward normal → misses more droughts. Decision: extra input only, not an alarm.

## 8. Data quality (independent audit)

62 checks, 0 FAIL, 4 WARN. Independent Earth Engine recompute matches the pipeline within 2.5% (rain, NDVI). Drought years (2015/16, 2023/24) and wet year (2016/17) show the right signs. No missing values stored as zero.

## 9. Verdict

| | |
|---|---|
| ✅ Honest | No future data, no declaration-date shortcut, hold-out untouched |
| ✅ Beats baselines | CV PR-AUC 0.55 vs 0.48 (persistence); FEWS NET precision 0.74 vs 0.43 |
| ✅ Few false alarms in Zimbabwe wet years | 0 Warnings in 2020/21 |
| ❌ Weak overall skill | ROC 0.57–0.62; crop_failure near baseline |
| ❌ Too late for Zimbabwe 2023/24 with real latency | 0 of 91 districts at Warning before 3 April (Watch in 26, ~15 wk ahead) |
| ✅ Some real lead in Kenya | 6/47 counties warned a median 8 weeks before the 2021 declaration |
| ❌ Watch not selective outside Zimbabwe | 43–45% of units in Zambia / Kenya |

**Honest pitch line:** "No hindsight: when our satellite + weather Warning fires, it matches FEWS NET crisis districts 74% of the time vs 43% for the baseline; zero Warnings in Zimbabwe's wet 2020/21 season; in Kenya it warned 6 counties a median 8 weeks before the 2021 declaration."

## 10. Next steps (in progress)

1. Seasonal rainfall forecasts (issued before the season) as inputs — for proactive Watch months ahead.
2. ENSO / El Niño index, stricter labels, season-cumulative rain, TimesFM features.
3. Freeze numbers for slides (sections 5–6 are final for this model version).
