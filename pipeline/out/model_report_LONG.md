# Model report (LONG)

Generated 2026-10-16T20:36:53+00:00. Countries pooled: ZWE, KEN, MWI, ZMB.
CV: leave-one-agricultural-year-out 2001-2022 (22 folds, 60486 rows incl. lead 0). Hold-out: 10743 rows (agyear>=2023, KEN 2020-22), scored once with final models.
Labels are satellite-only (VCI / SPI / soil moisture), not food-security outcomes.
Data latency modelled: {'chirps': 1, 'modis': 1, 'era5': 1} months. A value issued at month r uses only signals of month r-1 (CHIRPS final ~3 wk, MODIS 16-day ~1-2 wk, ERA5-Land via ERA5T/CDS ~5 days after month end). Lead L = months from issue to window start.
Metrics: leads 1-3 months. Cells = ROC-AUC / PR-AUC / Brier (base rate). AUCs on raw scores, Brier on cross-fitted isotonic-calibrated probabilities.

## Cross-validation (pooled)

| model | crop_failure | no_grass | mean PR-AUC |
|---|---|---|---|
| persistence | 0.552 / 0.228 / 0.1617 (base 0.204) | 0.537 / 0.305 / 0.2076 (base 0.287) | 0.267 |
| rule | 0.501 / 0.206 / 0.1633 (base 0.204) | 0.535 / 0.306 / 0.2069 (base 0.287) | 0.256 |
| logreg | 0.639 / 0.307 / 0.1574 (base 0.204) | 0.615 / 0.393 / 0.2012 (base 0.287) | 0.35 |
| lgbm | 0.643 / 0.305 / 0.1573 (base 0.204) | 0.551 / 0.37 / 0.2019 (base 0.287) | 0.338 |
| ensemble | 0.652 / 0.318 / 0.156 (base 0.204) | 0.605 / 0.398 / 0.2014 (base 0.287) | 0.358 |

**Winner (CV PR-AUC): ensemble**

### Winner by lead (CV)

| lead | crop_failure | no_grass |
|---|---|---|
| 4 | 0.68 / 0.331 / 0.1537 | 0.582 / 0.391 / 0.2027 |
| 5 | 0.655 / 0.323 / 0.1557 | 0.601 / 0.391 / 0.2015 |
| 6 | 0.621 / 0.301 / 0.1587 | 0.63 / 0.417 / 0.2 |

cant_plant: model dropped (no CV skill: pre-latency ROC 0.485, PR-AUC 0.168 = base rate 0.168, Brier worse than climatology). It is now only a rule-based Watch reason (strong rain+soil dryness).

### KEN CV by its own rainy seasons (winner ensemble)

| season | crop_failure | no_grass |
|---|---|---|
| MAM long rains | 0.66 / 0.376 / 0.1694 (base 0.233) | 0.69 / 0.529 / 0.2006 (base 0.33) |
| OND short rains | 0.547 / 0.326 / 0.2003 (base 0.268) | 0.646 / 0.595 / 0.2517 (base 0.48) |


## Spec alert rule vs satellite label on CV rows (informational; levels do not use p)

```
{
 "cv_base_rate": 0.245,
 "watch": {
  "rate": 0.148,
  "precision": 0.297,
  "recall": 0.179,
  "f1": 0.224
 },
 "warn": {
  "rate": 0.035,
  "precision": 0.333,
  "recall": 0.047,
  "f1": 0.083
 },
 "note": "levels come from the spec family rule; p is information only (v1.1, audit B3)"
}
```

## Hold-out (evaluated once)

### all

| model | crop_failure | no_grass | mean PR-AUC |
|---|---|---|---|
| persistence | 0.605 / 0.275 / 0.1637 (base 0.216) | 0.596 / 0.303 / 0.1847 (base 0.25) | 0.289 |
| rule | 0.553 / 0.258 / 0.1683 (base 0.216) | 0.614 / 0.331 / 0.1839 (base 0.25) | 0.294 |
| logreg | 0.645 / 0.353 / 0.1618 (base 0.216) | 0.751 / 0.477 / 0.1673 (base 0.25) | 0.415 |
| lgbm | 0.679 / 0.377 / 0.1576 (base 0.216) | 0.74 / 0.48 / 0.1744 (base 0.25) | 0.428 |
| ensemble | 0.665 / 0.377 / 0.1599 (base 0.216) | 0.764 / 0.512 / 0.1657 (base 0.25) | 0.445 |

### ZWE

| model | crop_failure | no_grass | mean PR-AUC |
|---|---|---|---|
| persistence | 0.486 / 0.161 / 0.1412 (base 0.165) | 0.525 / 0.278 / 0.1965 (base 0.267) | 0.22 |
| rule | 0.516 / 0.212 / 0.139 (base 0.165) | 0.636 / 0.418 / 0.189 (base 0.267) | 0.315 |
| logreg | 0.61 / 0.207 / 0.1375 (base 0.165) | 0.706 / 0.455 / 0.184 (base 0.267) | 0.331 |
| lgbm | 0.715 / 0.293 / 0.1286 (base 0.165) | 0.653 / 0.352 / 0.1948 (base 0.267) | 0.323 |
| ensemble | 0.658 / 0.249 / 0.1333 (base 0.165) | 0.711 / 0.46 / 0.1862 (base 0.267) | 0.355 |

### KEN

| model | crop_failure | no_grass | mean PR-AUC |
|---|---|---|---|
| persistence | 0.653 / 0.272 / 0.1302 (base 0.163) | 0.667 / 0.384 / 0.1828 (base 0.256) | 0.328 |
| rule | 0.602 / 0.246 / 0.1354 (base 0.163) | 0.576 / 0.318 / 0.1861 (base 0.256) | 0.282 |
| logreg | 0.755 / 0.475 / 0.126 (base 0.163) | 0.8 / 0.54 / 0.1586 (base 0.256) | 0.508 |
| lgbm | 0.794 / 0.466 / 0.1239 (base 0.163) | 0.812 / 0.577 / 0.1595 (base 0.256) | 0.521 |
| ensemble | 0.78 / 0.504 / 0.1264 (base 0.163) | 0.819 / 0.58 / 0.152 (base 0.256) | 0.542 |

### MWI

| model | crop_failure | no_grass | mean PR-AUC |
|---|---|---|---|
| persistence | 0.529 / 0.202 / 0.1543 (base 0.19) | 0.507 / 0.193 / 0.1636 (base 0.19) | 0.198 |
| rule | 0.567 / 0.217 / 0.1543 (base 0.19) | 0.658 / 0.292 / 0.1614 (base 0.19) | 0.255 |
| logreg | 0.537 / 0.217 / 0.1624 (base 0.19) | 0.688 / 0.274 / 0.1666 (base 0.19) | 0.245 |
| lgbm | 0.609 / 0.27 / 0.1526 (base 0.19) | 0.713 / 0.373 / 0.1598 (base 0.19) | 0.322 |
| ensemble | 0.586 / 0.246 / 0.1588 (base 0.19) | 0.718 / 0.328 / 0.1593 (base 0.19) | 0.287 |

### ZMB

| model | crop_failure | no_grass | mean PR-AUC |
|---|---|---|---|
| persistence | 0.561 / 0.368 / 0.2309 (base 0.336) | 0.569 / 0.274 / 0.1832 (base 0.241) | 0.321 |
| rule | 0.561 / 0.393 / 0.2412 (base 0.336) | 0.642 / 0.343 / 0.1824 (base 0.241) | 0.368 |
| logreg | 0.558 / 0.374 / 0.2315 (base 0.336) | 0.739 / 0.486 / 0.1665 (base 0.241) | 0.43 |
| lgbm | 0.576 / 0.396 / 0.2291 (base 0.336) | 0.708 / 0.388 / 0.1825 (base 0.241) | 0.392 |
| ensemble | 0.569 / 0.389 / 0.2285 (base 0.336) | 0.75 / 0.504 / 0.1702 (base 0.241) | 0.447 |

Caveat: the ZWE/MWI/ZMB hold-out is a single season in which most units were in drought; AUC there only measures which units the model ranks worst, not whether it sees the year coming.
