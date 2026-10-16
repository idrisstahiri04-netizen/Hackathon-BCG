# Model report (ZWE_KEN_MWI_ZMB)

Generated 2026-10-16T17:49:19+00:00. Countries pooled: ZWE, KEN, MWI, ZMB.
CV: leave-one-agricultural-year-out 2001-2022 (22 folds, 80648 rows incl. lead 0). Hold-out: 7708 rows (agyear>=2023, KEN 2020-22), scored once with final models.
Labels are satellite-only (VCI / SPI / soil moisture), not food-security outcomes.
Data latency modelled: {'chirps': 1, 'modis': 1, 'era5': 1} months. A value issued at month r uses only signals of month r-1 (CHIRPS final ~3 wk, MODIS 16-day ~1-2 wk, ERA5-Land via ERA5T/CDS ~5 days after month end). Lead L = months from issue to window start.
Metrics: leads 1-3 months. Cells = ROC-AUC / PR-AUC / Brier (base rate). AUCs on raw scores, Brier on cross-fitted isotonic-calibrated probabilities.

## Cross-validation (pooled)

| model | crop_failure | no_grass | mean PR-AUC |
|---|---|---|---|
| persistence | 0.552 / 0.228 / 0.1617 (base 0.204) | 0.537 / 0.305 / 0.2076 (base 0.287) | 0.267 |
| rule | 0.529 / 0.22 / 0.163 (base 0.204) | 0.547 / 0.31 / 0.2086 (base 0.287) | 0.265 |
| logreg | 0.59 / 0.278 / 0.1607 (base 0.204) | 0.593 / 0.379 / 0.2051 (base 0.287) | 0.329 |
| lgbm | 0.568 / 0.252 / 0.1628 (base 0.204) | 0.601 / 0.4 / 0.2038 (base 0.287) | 0.326 |
| ensemble | 0.589 / 0.272 / 0.161 (base 0.204) | 0.603 / 0.403 / 0.2028 (base 0.287) | 0.338 |

**Winner (CV PR-AUC): ensemble**

### Winner by lead (CV)

| lead | crop_failure | no_grass |
|---|---|---|
| 1 | 0.594 / 0.286 / 0.1602 | 0.657 / 0.459 / 0.1938 |
| 2 | 0.601 / 0.276 / 0.1605 | 0.603 / 0.405 / 0.2026 |
| 3 | 0.57 / 0.26 / 0.1623 | 0.545 / 0.35 / 0.2119 |

cant_plant: model dropped (no CV skill: pre-latency ROC 0.485, PR-AUC 0.168 = base rate 0.168, Brier worse than climatology). It is now only a rule-based Watch reason (strong rain+soil dryness).

### KEN CV by its own rainy seasons (winner ensemble)

| season | crop_failure | no_grass |
|---|---|---|
| MAM long rains | 0.598 / 0.287 / 0.1784 (base 0.233) | 0.674 / 0.528 / 0.2016 (base 0.33) |
| OND short rains | 0.52 / 0.311 / 0.1996 (base 0.268) | 0.637 / 0.626 / 0.2419 (base 0.48) |


## Spec alert rule vs satellite label on CV rows (informational; levels do not use p)

```
{
 "cv_base_rate": 0.245,
 "watch": {
  "rate": 0.25,
  "precision": 0.319,
  "recall": 0.324,
  "f1": 0.321
 },
 "warn": {
  "rate": 0.069,
  "precision": 0.343,
  "recall": 0.097,
  "f1": 0.151
 },
 "note": "levels come from the spec family rule; p is information only (v1.1, audit B3)"
}
```

## Hold-out (evaluated once)

### all

| model | crop_failure | no_grass | mean PR-AUC |
|---|---|---|---|
| persistence | 0.621 / 0.42 / 0.2239 (base 0.324) | 0.651 / 0.566 / 0.2638 (base 0.451) | 0.493 |
| rule | 0.598 / 0.405 / 0.23 (base 0.324) | 0.699 / 0.633 / 0.239 (base 0.451) | 0.519 |
| logreg | 0.464 / 0.342 / 0.2342 (base 0.324) | 0.644 / 0.612 / 0.2587 (base 0.451) | 0.477 |
| lgbm | 0.492 / 0.366 / 0.2335 (base 0.324) | 0.696 / 0.658 / 0.2351 (base 0.451) | 0.512 |
| ensemble | 0.472 / 0.362 / 0.2325 (base 0.324) | 0.679 / 0.641 / 0.2467 (base 0.451) | 0.502 |

### ZWE

| model | crop_failure | no_grass | mean PR-AUC |
|---|---|---|---|
| persistence | 0.527 / 0.439 / 0.2877 (base 0.407) | 0.552 / 0.748 / 0.3821 (base 0.725) | 0.594 |
| rule | 0.551 / 0.472 / 0.2739 (base 0.407) | 0.464 / 0.705 / 0.362 (base 0.725) | 0.589 |
| logreg | 0.454 / 0.372 / 0.2977 (base 0.407) | 0.555 / 0.755 / 0.412 (base 0.725) | 0.564 |
| lgbm | 0.463 / 0.39 / 0.2996 (base 0.407) | 0.561 / 0.759 / 0.3626 (base 0.725) | 0.575 |
| ensemble | 0.453 / 0.374 / 0.2989 (base 0.407) | 0.556 / 0.775 / 0.3954 (base 0.725) | 0.575 |

### KEN

| model | crop_failure | no_grass | mean PR-AUC |
|---|---|---|---|
| persistence | 0.683 / 0.337 / 0.1451 (base 0.192) | 0.706 / 0.47 / 0.1978 (base 0.299) | 0.403 |
| rule | 0.588 / 0.254 / 0.1531 (base 0.192) | 0.673 / 0.466 / 0.1899 (base 0.299) | 0.36 |
| logreg | 0.638 / 0.31 / 0.1502 (base 0.192) | 0.818 / 0.699 / 0.1588 (base 0.299) | 0.504 |
| lgbm | 0.722 / 0.393 / 0.1452 (base 0.192) | 0.82 / 0.68 / 0.1608 (base 0.299) | 0.536 |
| ensemble | 0.687 / 0.38 / 0.1449 (base 0.192) | 0.826 / 0.704 / 0.1529 (base 0.299) | 0.542 |

### MWI

| model | crop_failure | no_grass | mean PR-AUC |
|---|---|---|---|
| persistence | 0.556 / 0.397 / 0.2315 (base 0.321) | 0.607 / 0.586 / 0.2915 (base 0.5) | 0.491 |
| rule | 0.531 / 0.342 / 0.236 (base 0.321) | 0.63 / 0.582 / 0.2559 (base 0.5) | 0.462 |
| logreg | 0.434 / 0.306 / 0.2409 (base 0.321) | 0.379 / 0.474 / 0.3233 (base 0.5) | 0.39 |
| lgbm | 0.673 / 0.511 / 0.2276 (base 0.321) | 0.57 / 0.53 / 0.3028 (base 0.5) | 0.52 |
| ensemble | 0.479 / 0.365 / 0.2369 (base 0.321) | 0.417 / 0.469 / 0.3156 (base 0.5) | 0.417 |

### ZMB

| model | crop_failure | no_grass | mean PR-AUC |
|---|---|---|---|
| persistence | 0.544 / 0.66 / 0.3983 (base 0.638) | 0.636 / 0.734 / 0.3509 (base 0.655) | 0.697 |
| rule | 0.6 / 0.708 / 0.4146 (base 0.638) | 0.751 / 0.819 / 0.2772 (base 0.655) | 0.763 |
| logreg | 0.372 / 0.588 / 0.4241 (base 0.638) | 0.569 / 0.709 / 0.4053 (base 0.655) | 0.648 |
| lgbm | 0.38 / 0.587 / 0.4367 (base 0.638) | 0.613 / 0.776 / 0.3289 (base 0.655) | 0.681 |
| ensemble | 0.367 / 0.583 / 0.4305 (base 0.638) | 0.618 / 0.761 / 0.3785 (base 0.655) | 0.672 |

Caveat: the ZWE/MWI/ZMB hold-out is a single season in which most units were in drought; AUC there only measures which units the model ranks worst, not whether it sees the year coming.

## v1.1 spec mode: replay of the exported files (judge.py + compare_ipc.py, run after export)

Levels: spec family rule + hysteresis 2 up / 3 down only (no p gate, no one-step limit, no fast entry);
soil gated to rainy season; vegetation = dominant cover, VCI<35 two published months running or ndvi_z<=-1
in crop and grass (normal-season in-season firing 15.5% on CV years vs 28% before); Emergency = Warning +
declaration in force (declaration month to end of that agricultural year). p is information only, null if missing.
Issue convention: month t issued at end of t from data of t-1 (judge `next_month_1st`).

| country | Warning before decl. (median lead) | Watch before decl. (median lead) | calm-season Warning unit-months |
|---|---|---|---|
| ZWE | 7/91 (4.7 wk) | 53/91 (8.9 wk) | 2019/20 12, 2020/21 0, 2021/22 6, 2022/23 0 |
| ZMB | 7/116 (4.0 wk) | 52/116 (4.0 wk) | 2019/20 9, 2020/21 5, 2022/23 8 |
| MWI | 3/28 (3.1 wk) | 20/28 (3.1 wk) | 0 except 2021/22 30 |
| KEN | 6/47 (7.6 wk) | 23/47 (18.6 wk) | 2019/20 0, 2020/21 0 (2021/22, 2022/23 were real drought; judge's Nov-Mar class is wrong for KEN) |

ZWE vs FEWS NET IPC3+ transitions 2023/24: precision 0.778, recall 0.614 (TP 35, FP 10, FN 22); persistence
0.426 / 0.351. All seasons 2019/20-2023/24: 0.709 / 0.277 vs persistence 0.238 / 0.440.
MWI 2023/24: 0.40 / 0.50 (4 transitions); all seasons 0.07 / 0.08 (no skill, persistence 0.07 / 0.12).
Kaggle retrain attempt failed (HTTP 409 creating kernel drought-train-v11); this model was trained locally with the same code.

## p_crisis Watch trigger (final, alert logic frozen)

Per-row `p_crisis` = out-of-sample calibrated P(district enters IPC3+ within 1-3 months) from pipeline/ipc_model
(eo_fews:lgbm; CV fold predictions for CV seasons, final model for hold-out); shown to NGOs everywhere, null where
unavailable (ZMB). Watch trigger (announcement/text family, Watch only, never Warning, NGO/officer audiences):
p_crisis >= 0.57 (precision-first CV point of the IPC model; the max-F1 point 0.31 kept Watch on in ~90% of districts
in calm seasons), only where the latest published IPC phase is < 3 (as the threshold was tuned), and only in the
agricultural decision window: Oct-Apr for ZWE/MWI/ZMB (planting, growing and lean season), KEN each own rainy
season +/- 1 month. The window is an a-priori agricultural-calendar rule (when planting, input and pre-positioning
decisions can still be acted on), not tuned on replay outcomes.

ZWE replay (judge.py, compare_ipc.py): Warning before the declaration 7/91 (median 4.7 wk); Watch before 61/91
(median 8.9 wk; first Watch Dec-23 13, Jan-24 40). Share of districts ever at Watch (Nov-Apr): 2020/21 18%,
2021/22 70% (47 of 84 districts entered IPC3+ that season; Watch caught all 47, 13 false), 2022/23 3%.
Warning+ vs IPC3+ transitions unchanged: 2023/24 P 0.78 / R 0.61 (persistence 0.43 / 0.35); all seasons 0.71 / 0.28.
