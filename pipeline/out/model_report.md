# Model report (ZWE_KEN_MWI_ZMB)

Generated 2026-10-16T19:41:57+00:00. Countries pooled: ZWE, KEN, MWI, ZMB.
CV: leave-one-agricultural-year-out 2001-2022 (22 folds, 80648 rows incl. lead 0). Hold-out: 11316 rows (agyear>=2023, KEN 2020-22), scored once with final models.
Labels are satellite-only (VCI / SPI / soil moisture), not food-security outcomes.
Data latency modelled: {'chirps': 1, 'modis': 1, 'era5': 1} months. A value issued at month r uses only signals of month r-1 (CHIRPS final ~3 wk, MODIS 16-day ~1-2 wk, ERA5-Land via ERA5T/CDS ~5 days after month end). Lead L = months from issue to window start.
Metrics: leads 1-3 months. Cells = ROC-AUC / PR-AUC / Brier (base rate). AUCs on raw scores, Brier on cross-fitted isotonic-calibrated probabilities.

## Cross-validation (pooled)

| model | crop_failure | no_grass | mean PR-AUC |
|---|---|---|---|
| persistence | 0.552 / 0.228 / 0.1617 (base 0.204) | 0.537 / 0.305 / 0.2076 (base 0.287) | 0.267 |
| rule | 0.529 / 0.22 / 0.163 (base 0.204) | 0.547 / 0.31 / 0.2086 (base 0.287) | 0.265 |
| logreg | 0.651 / 0.329 / 0.1558 (base 0.204) | 0.626 / 0.406 / 0.2006 (base 0.287) | 0.368 |
| lgbm | 0.653 / 0.324 / 0.1563 (base 0.204) | 0.648 / 0.451 / 0.1951 (base 0.287) | 0.388 |
| ensemble | 0.663 / 0.339 / 0.1543 (base 0.204) | 0.643 / 0.443 / 0.1962 (base 0.287) | 0.391 |

**Winner (CV PR-AUC): ensemble**

### Winner by lead (CV)

| lead | crop_failure | no_grass |
|---|---|---|
| 1 | 0.678 / 0.356 / 0.1527 | 0.714 / 0.507 / 0.1838 |
| 2 | 0.67 / 0.338 / 0.154 | 0.639 / 0.446 / 0.1964 |
| 3 | 0.64 / 0.325 / 0.1562 | 0.573 / 0.375 / 0.2084 |

cant_plant: model dropped (no CV skill: pre-latency ROC 0.485, PR-AUC 0.168 = base rate 0.168, Brier worse than climatology). It is now only a rule-based Watch reason (strong rain+soil dryness).

### KEN CV by its own rainy seasons (winner ensemble)

| season | crop_failure | no_grass |
|---|---|---|
| MAM long rains | 0.694 / 0.385 / 0.1677 (base 0.233) | 0.722 / 0.607 / 0.1876 (base 0.33) |
| OND short rains | 0.689 / 0.431 / 0.1837 (base 0.268) | 0.725 / 0.688 / 0.2269 (base 0.48) |


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
| persistence | 0.607 / 0.3 / 0.1708 (base 0.229) | 0.61 / 0.39 / 0.212 (base 0.319) | 0.345 |
| rule | 0.601 / 0.295 / 0.1746 (base 0.229) | 0.715 / 0.532 / 0.1921 (base 0.319) | 0.413 |
| logreg | 0.75 / 0.508 / 0.1497 (base 0.229) | 0.832 / 0.667 / 0.171 (base 0.319) | 0.588 |
| lgbm | 0.751 / 0.449 / 0.1536 (base 0.229) | 0.785 / 0.631 / 0.1756 (base 0.319) | 0.54 |
| ensemble | 0.756 / 0.493 / 0.1496 (base 0.229) | 0.832 / 0.674 / 0.1679 (base 0.319) | 0.584 |

### ZWE

| model | crop_failure | no_grass | mean PR-AUC |
|---|---|---|---|
| persistence | 0.486 / 0.161 / 0.1412 (base 0.165) | 0.525 / 0.278 / 0.1965 (base 0.267) | 0.22 |
| rule | 0.641 / 0.298 / 0.1335 (base 0.165) | 0.66 / 0.388 / 0.1815 (base 0.267) | 0.343 |
| logreg | 0.702 / 0.329 / 0.1311 (base 0.165) | 0.837 / 0.579 / 0.1579 (base 0.267) | 0.454 |
| lgbm | 0.699 / 0.328 / 0.1309 (base 0.165) | 0.727 / 0.474 / 0.1753 (base 0.267) | 0.401 |
| ensemble | 0.709 / 0.35 / 0.1296 (base 0.165) | 0.818 / 0.57 / 0.1612 (base 0.267) | 0.46 |

### KEN

| model | crop_failure | no_grass | mean PR-AUC |
|---|---|---|---|
| persistence | 0.653 / 0.272 / 0.1302 (base 0.163) | 0.667 / 0.384 / 0.1828 (base 0.256) | 0.328 |
| rule | 0.549 / 0.192 / 0.1374 (base 0.163) | 0.667 / 0.426 / 0.1739 (base 0.256) | 0.309 |
| logreg | 0.726 / 0.416 / 0.1214 (base 0.163) | 0.846 / 0.67 / 0.1434 (base 0.256) | 0.543 |
| lgbm | 0.752 / 0.385 / 0.1269 (base 0.163) | 0.848 / 0.687 / 0.1371 (base 0.256) | 0.536 |
| ensemble | 0.743 / 0.417 / 0.1232 (base 0.163) | 0.86 / 0.693 / 0.1346 (base 0.256) | 0.555 |

### MWI

| model | crop_failure | no_grass | mean PR-AUC |
|---|---|---|---|
| persistence | 0.556 / 0.397 / 0.2315 (base 0.321) | 0.607 / 0.586 / 0.2915 (base 0.5) | 0.491 |
| rule | 0.531 / 0.342 / 0.236 (base 0.321) | 0.63 / 0.582 / 0.2559 (base 0.5) | 0.462 |
| logreg | 0.437 / 0.346 / 0.2445 (base 0.321) | 0.488 / 0.514 / 0.2798 (base 0.5) | 0.43 |
| lgbm | 0.478 / 0.395 / 0.232 (base 0.321) | 0.641 / 0.632 / 0.2614 (base 0.5) | 0.514 |
| ensemble | 0.437 / 0.378 / 0.2415 (base 0.321) | 0.538 / 0.558 / 0.2642 (base 0.5) | 0.468 |

### ZMB

| model | crop_failure | no_grass | mean PR-AUC |
|---|---|---|---|
| persistence | 0.544 / 0.66 / 0.3983 (base 0.638) | 0.636 / 0.734 / 0.3509 (base 0.655) | 0.697 |
| rule | 0.6 / 0.708 / 0.4146 (base 0.638) | 0.751 / 0.819 / 0.2772 (base 0.655) | 0.763 |
| logreg | 0.617 / 0.732 / 0.2908 (base 0.638) | 0.767 / 0.846 / 0.2904 (base 0.655) | 0.789 |
| lgbm | 0.58 / 0.683 / 0.3009 (base 0.638) | 0.664 / 0.802 / 0.3161 (base 0.655) | 0.743 |
| ensemble | 0.599 / 0.705 / 0.2862 (base 0.638) | 0.754 / 0.837 / 0.2995 (base 0.655) | 0.771 |

Caveat: the ZWE/MWI/ZMB hold-out is a single season in which most units were in drought; AUC there only measures which units the model ranks worst, not whether it sees the year coming.
