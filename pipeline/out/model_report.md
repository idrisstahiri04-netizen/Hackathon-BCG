# Model report (ZWE_KEN_MWI_ZMB)

Generated 2026-10-16T16:25:48+00:00. Countries pooled: ZWE, KEN, MWI, ZMB.
CV: leave-one-agricultural-year-out 2001-2022 (22 folds, 80648 rows incl. lead 0). Hold-out: 7708 rows (agyear>=2023, KEN 2020-22), scored once with final models.
Labels are satellite-only (VCI / SPI / soil moisture), not food-security outcomes.
Metrics: leads 1-3 months. Cells = ROC-AUC / PR-AUC / Brier (base rate). AUCs on raw scores, Brier on cross-fitted isotonic-calibrated probabilities.

## Cross-validation (pooled)

| model | cant_plant | crop_failure | no_grass | mean PR-AUC |
|---|---|---|---|---|
| persistence | 0.471 / 0.164 / 0.1417 (base 0.168) | 0.562 / 0.514 / 0.2488 (base 0.478) | 0.547 / 0.44 / 0.2458 (base 0.414) | 0.373 |
| rule | 0.518 / 0.173 / 0.1441 (base 0.168) | 0.545 / 0.529 / 0.2501 (base 0.478) | 0.619 / 0.51 / 0.2363 (base 0.414) | 0.404 |
| logreg | 0.493 / 0.168 / 0.1448 (base 0.168) | 0.593 / 0.586 / 0.2459 (base 0.478) | 0.697 / 0.611 / 0.221 (base 0.414) | 0.455 |
| lgbm | 0.455 / 0.162 / 0.146 (base 0.168) | 0.609 / 0.581 / 0.2437 (base 0.478) | 0.708 / 0.64 / 0.2141 (base 0.414) | 0.461 |
| ensemble | 0.485 / 0.168 / 0.1458 (base 0.168) | 0.609 / 0.593 / 0.2444 (base 0.478) | 0.712 / 0.64 / 0.2145 (base 0.414) | 0.467 |

**Winner (CV PR-AUC): ensemble**

### Winner by lead (CV)

| lead | cant_plant | crop_failure | no_grass |
|---|---|---|---|
| 1 | 0.488 / 0.172 / 0.1434 | 0.647 / 0.644 / 0.2347 | 0.818 / 0.76 / 0.1741 |
| 2 | 0.479 / 0.162 / 0.1468 | 0.596 / 0.575 / 0.2481 | 0.681 / 0.599 / 0.2257 |
| 3 | 0.491 / 0.176 / 0.1471 | 0.583 / 0.553 / 0.2505 | 0.62 / 0.546 / 0.2436 |

## Alert thresholds (tuned on CV out-of-fold predictions only)

```
{
 "p_warn": 0.25,
 "p_watch": 0.25,
 "p_emerg": 0.75,
 "cv_f1_warn": 0.252,
 "cv_f1_watch": 0.587,
 "cv_f1_warn_default": 0.223
}
```

## Hold-out (evaluated once)

### all

| model | cant_plant | crop_failure | no_grass | mean PR-AUC |
|---|---|---|---|---|
| persistence | 0.563 / 0.416 / 0.2768 (base 0.374) | 0.629 / 0.644 / 0.2428 (base 0.563) | 0.666 / 0.699 / 0.258 (base 0.597) | 0.586 |
| rule | 0.445 / 0.346 / 0.2888 (base 0.374) | 0.638 / 0.693 / 0.2328 (base 0.563) | 0.752 / 0.799 / 0.2031 (base 0.597) | 0.613 |
| logreg | 0.614 / 0.484 / 0.2639 (base 0.374) | 0.602 / 0.659 / 0.2471 (base 0.563) | 0.744 / 0.814 / 0.228 (base 0.597) | 0.652 |
| lgbm | 0.648 / 0.491 / 0.2799 (base 0.374) | 0.575 / 0.653 / 0.2667 (base 0.563) | 0.789 / 0.841 / 0.1881 (base 0.597) | 0.662 |
| ensemble | 0.63 / 0.493 / 0.2729 (base 0.374) | 0.598 / 0.664 / 0.2543 (base 0.563) | 0.781 / 0.834 / 0.2012 (base 0.597) | 0.664 |

### ZWE

| model | cant_plant | crop_failure | no_grass | mean PR-AUC |
|---|---|---|---|---|
| persistence | 0.278 / 0.538 / 0.4266 (base 0.6) | 0.543 / 0.779 / 0.2898 (base 0.758) | 0.507 / 0.881 / 0.3032 (base 0.879) | 0.733 |
| rule | 0.546 / 0.636 / 0.4434 (base 0.6) | 0.576 / 0.818 / 0.2373 (base 0.758) | 0.51 / 0.882 / 0.222 (base 0.879) | 0.779 |
| logreg | 0.478 / 0.647 / 0.4007 (base 0.6) | 0.591 / 0.822 / 0.3001 (base 0.758) | 0.541 / 0.91 / 0.3134 (base 0.879) | 0.793 |
| lgbm | 0.6 / 0.705 / 0.4301 (base 0.6) | 0.54 / 0.796 / 0.3947 (base 0.758) | 0.534 / 0.905 / 0.2247 (base 0.879) | 0.802 |
| ensemble | 0.526 / 0.675 / 0.4132 (base 0.6) | 0.576 / 0.813 / 0.3523 (base 0.758) | 0.538 / 0.911 / 0.2658 (base 0.879) | 0.8 |

### KEN

| model | cant_plant | crop_failure | no_grass | mean PR-AUC |
|---|---|---|---|---|
| persistence | 0.535 / 0.089 / 0.0813 (base 0.08) | 0.693 / 0.538 / 0.2247 (base 0.39) | 0.673 / 0.567 / 0.2337 (base 0.445) | 0.398 |
| rule | 0.535 / 0.09 / 0.0862 (base 0.08) | 0.619 / 0.5 / 0.229 (base 0.39) | 0.707 / 0.636 / 0.212 (base 0.445) | 0.409 |
| logreg | 0.49 / 0.074 / 0.0829 (base 0.08) | 0.683 / 0.562 / 0.2248 (base 0.39) | 0.844 / 0.825 / 0.1626 (base 0.445) | 0.487 |
| lgbm | 0.524 / 0.082 / 0.079 (base 0.08) | 0.732 / 0.622 / 0.2105 (base 0.39) | 0.825 / 0.792 / 0.172 (base 0.445) | 0.499 |
| ensemble | 0.494 / 0.075 / 0.0806 (base 0.08) | 0.731 / 0.619 / 0.2126 (base 0.39) | 0.842 / 0.819 / 0.1631 (base 0.445) | 0.504 |

### MWI

| model | cant_plant | crop_failure | no_grass | mean PR-AUC |
|---|---|---|---|---|
| persistence | 0.615 / 0.553 / 0.3066 (base 0.419) | 0.562 / 0.873 / 0.2771 (base 0.857) | 0.613 / 0.771 / 0.2942 (base 0.714) | 0.732 |
| rule | 0.35 / 0.378 / 0.3182 (base 0.419) | 0.559 / 0.882 / 0.2667 (base 0.857) | 0.697 / 0.808 / 0.199 (base 0.714) | 0.689 |
| logreg | 0.3 / 0.316 / 0.3117 (base 0.419) | 0.602 / 0.902 / 0.2575 (base 0.857) | 0.628 / 0.815 / 0.3171 (base 0.714) | 0.678 |
| lgbm | 0.473 / 0.426 / 0.3114 (base 0.419) | 0.499 / 0.856 / 0.2739 (base 0.857) | 0.672 / 0.841 / 0.2634 (base 0.714) | 0.708 |
| ensemble | 0.353 / 0.343 / 0.3137 (base 0.419) | 0.552 / 0.875 / 0.2619 (base 0.857) | 0.672 / 0.827 / 0.2871 (base 0.714) | 0.682 |

### ZMB

| model | cant_plant | crop_failure | no_grass | mean PR-AUC |
|---|---|---|---|---|
| persistence | 0.655 / 0.768 / 0.4708 (base 0.667) | 0.461 / 0.826 / 0.2496 (base 0.836) | 0.712 / 0.862 / 0.2824 (base 0.776) | 0.819 |
| rule | 0.444 / 0.675 / 0.4905 (base 0.667) | 0.65 / 0.903 / 0.2319 (base 0.836) | 0.798 / 0.923 / 0.1643 (base 0.776) | 0.834 |
| logreg | 0.504 / 0.675 / 0.4422 (base 0.667) | 0.474 / 0.836 / 0.2671 (base 0.836) | 0.615 / 0.863 / 0.3246 (base 0.776) | 0.791 |
| lgbm | 0.631 / 0.75 / 0.4824 (base 0.667) | 0.381 / 0.806 / 0.326 (base 0.836) | 0.742 / 0.915 / 0.1867 (base 0.776) | 0.824 |
| ensemble | 0.54 / 0.696 / 0.468 (base 0.667) | 0.422 / 0.817 / 0.2954 (base 0.836) | 0.716 / 0.895 / 0.2377 (base 0.776) | 0.803 |

Caveat: the ZWE/MWI/ZMB hold-out is a single season in which most units were in drought; AUC there only measures which units the model ranks worst, not whether it sees the year coming.
