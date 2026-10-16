# ML-expert experiment A: satellite-only FEWS NET proxy (IPC3+ within 1-3 months)

Generated 2026-10-16T19:26:39Z; countries ['ZWE', 'KEN', 'MWI']; rows 17928; CV seasons [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022]; LightGBM trees 400. Cells: ROC / PR-AUC (raw) / Brier (calibrated).

Proxy skill: {"vs_fews_target_all": {"roc": 0.835, "n": 12437, "base": 0.353}, "vs_fews_target_transition": {"roc": 0.842, "n": 8754, "base": 0.184}, "proxy_vs_ipc_truth_transition": {"n": 8878, "pos": 1396, "base": 0.157, "roc": 0.796, "pr": 0.381}}

### Cross-validation (leave-one-season-out, purged) — h13

| model | all rows | transition rows (state < 3) |
|---|---|---|
| persistence | 0.847 / 0.670 / 0.1363 (n 12282, base 0.331) | 0.709 / 0.255 / 0.1226 (n 8878, base 0.157) |
| fews | 0.903 / 0.757 / 0.0965 (n 12123, base 0.329) | 0.863 / 0.525 / 0.0886 (n 8752, base 0.155) |
| eo:logreg | 0.761 / 0.577 / 0.1876 (n 12282, base 0.331) | 0.735 / 0.317 / 0.1496 (n 8878, base 0.157) |
| eo:lgbm | 0.797 / 0.637 / 0.1753 (n 12282, base 0.331) | 0.768 / 0.353 / 0.1421 (n 8878, base 0.157) |
| eo_proxy:logreg | 0.771 / 0.604 / 0.1843 (n 12282, base 0.331) | 0.746 / 0.336 / 0.1464 (n 8878, base 0.157) |
| eo_proxy:lgbm | 0.792 / 0.629 / 0.1774 (n 12282, base 0.331) | 0.776 / 0.357 / 0.1402 (n 8878, base 0.157) |
| eo_fews:logreg | 0.894 / 0.791 / 0.1239 (n 12282, base 0.331) | 0.833 / 0.483 / 0.1132 (n 8878, base 0.157) |
| eo_fews:lgbm | 0.917 / 0.843 / 0.1058 (n 12282, base 0.331) | 0.872 / 0.598 / 0.0939 (n 8878, base 0.157) |
| eo_fews_masked:logreg | 0.623 / 0.467 / 0.2284 (n 12282, base 0.331) | 0.585 / 0.228 / 0.1677 (n 8878, base 0.157) |
| eo_fews_masked:lgbm | 0.610 / 0.459 / 0.2294 (n 12282, base 0.331) | 0.594 / 0.238 / 0.1669 (n 8878, base 0.157) |
| eo:ensemble | 0.775 / 0.607 / 0.1764 (n 12282, base 0.331) | 0.742 / 0.329 / 0.1413 (n 8878, base 0.157) |
| eo_proxy:ensemble | 0.772 / 0.614 / 0.1765 (n 12282, base 0.331) | 0.750 / 0.345 / 0.1394 (n 8878, base 0.157) |
| eo_fews:ensemble | 0.905 / 0.823 / 0.1081 (n 12282, base 0.331) | 0.842 / 0.531 / 0.0977 (n 8878, base 0.157) |
| eo_fews_masked:ensemble | 0.581 / 0.437 / 0.2269 (n 12282, base 0.331) | 0.551 / 0.213 / 0.1657 (n 8878, base 0.157) |

### CV by country — h13 (transition rows)

| group | persistence | fews | eo:lgbm | eo:ensemble | eo_proxy:lgbm | eo_proxy:ensemble | eo_fews:lgbm | eo_fews_masked:lgbm |
|---|---|---|---|---|---|---|---|---|
| KEN | 0.877 / 0.204 / 0.0504 (n 2146, base 0.06) | 0.930 / 0.489 / 0.0343 (n 2100, base 0.061) | 0.924 / 0.489 / 0.0501 (n 2146, base 0.06) | 0.899 / 0.408 / 0.0511 (n 2146, base 0.06) | 0.902 / 0.456 / 0.0514 (n 2146, base 0.06) | 0.887 / 0.430 / 0.0510 (n 2146, base 0.06) | 0.962 / 0.623 / 0.0329 (n 2146, base 0.06) | 0.618 / 0.142 / 0.1114 (n 2146, base 0.06) |
| MWI | 0.723 / 0.232 / 0.0974 (n 2190, base 0.121) | 0.890 / 0.449 / 0.0825 (n 2162, base 0.116) | 0.625 / 0.173 / 0.1212 (n 2190, base 0.121) | 0.592 / 0.179 / 0.1249 (n 2190, base 0.121) | 0.635 / 0.160 / 0.1211 (n 2190, base 0.121) | 0.594 / 0.166 / 0.1243 (n 2190, base 0.121) | 0.896 / 0.427 / 0.0883 (n 2190, base 0.121) | 0.585 / 0.203 / 0.1490 (n 2190, base 0.121) |
| ZWE | 0.627 / 0.279 / 0.1688 (n 4542, base 0.221) | 0.826 / 0.559 / 0.1169 (n 4490, base 0.217) | 0.714 / 0.370 / 0.1956 (n 4542, base 0.221) | 0.681 / 0.351 / 0.1918 (n 4542, base 0.221) | 0.729 / 0.377 / 0.1914 (n 4542, base 0.221) | 0.701 / 0.373 / 0.1884 (n 4542, base 0.221) | 0.827 / 0.641 / 0.1255 (n 4542, base 0.221) | 0.549 / 0.278 / 0.2018 (n 4542, base 0.221) |

### CV ZWE by season — h13 (transition rows)

| group | persistence | fews | eo:lgbm | eo_proxy:lgbm | eo_fews:lgbm | eo_fews_masked:lgbm |
|---|---|---|---|---|---|---|
| 2015/16 | 0.829 / 0.552 / 0.1763 (n 216, base 0.296) | 0.950 / 0.823 / 0.0653 (n 216, base 0.296) | 0.980 / 0.960 / 0.2044 (n 216, base 0.296) | 0.945 / 0.875 / 0.1681 (n 216, base 0.296) | 0.970 / 0.906 / 0.0979 (n 216, base 0.296) | 0.815 / 0.625 / 0.2807 (n 216, base 0.296) |
| 2016/17 | 0.796 / 0.052 / 0.0473 (n 552, base 0.022) | 0.926 / 0.143 / 0.0925 (n 552, base 0.022) | 0.807 / 0.157 / 0.1404 (n 552, base 0.022) | 0.812 / 0.115 / 0.1530 (n 552, base 0.022) | 0.957 / 0.230 / 0.0848 (n 552, base 0.022) | 0.767 / 0.059 / 0.1417 (n 552, base 0.022) |
| 2017/18 | 0.658 / 0.288 / 0.1512 (n 860, base 0.195) | 0.940 / 0.769 / 0.0594 (n 860, base 0.195) | 0.763 / 0.385 / 0.1881 (n 860, base 0.195) | 0.752 / 0.343 / 0.1923 (n 860, base 0.195) | 0.914 / 0.665 / 0.0930 (n 860, base 0.195) | 0.608 / 0.270 / 0.1736 (n 860, base 0.195) |
| 2018/19 | 0.911 / 0.710 / 0.1794 (n 502, base 0.303) | 0.897 / 0.649 / 0.1340 (n 450, base 0.276) | 0.767 / 0.627 / 0.1750 (n 502, base 0.303) | 0.759 / 0.630 / 0.1715 (n 502, base 0.303) | 0.837 / 0.624 / 0.1656 (n 502, base 0.303) | 0.617 / 0.433 / 0.2725 (n 502, base 0.303) |
| 2019/20 | 0.463 / 0.442 / 0.3561 (n 436, base 0.459) | 0.515 / 0.496 / 0.3630 (n 436, base 0.459) | 0.427 / 0.423 / 0.3296 (n 436, base 0.459) | 0.434 / 0.431 / 0.3196 (n 436, base 0.459) | 0.530 / 0.563 / 0.3449 (n 436, base 0.459) | 0.432 / 0.423 / 0.2727 (n 436, base 0.459) |
| 2020/21 | 0.540 / 0.103 / 0.1234 (n 500, base 0.096) | 0.960 / 0.571 / 0.0604 (n 500, base 0.096) | 0.649 / 0.121 / 0.1757 (n 500, base 0.096) | 0.722 / 0.147 / 0.1616 (n 500, base 0.096) | 0.936 / 0.423 / 0.0817 (n 500, base 0.096) | 0.284 / 0.064 / 0.1829 (n 500, base 0.096) |
| 2021/22 | 0.584 / 0.238 / 0.1596 (n 836, base 0.206) | 0.868 / 0.505 / 0.1522 (n 836, base 0.206) | 0.773 / 0.346 / 0.2283 (n 836, base 0.206) | 0.796 / 0.404 / 0.2245 (n 836, base 0.206) | 0.881 / 0.678 / 0.1409 (n 836, base 0.206) | 0.573 / 0.281 / 0.1849 (n 836, base 0.206) |
| 2022/23 | 0.527 / 0.305 / 0.2062 (n 640, base 0.294) | 0.945 / 0.892 / 0.0508 (n 640, base 0.294) | 0.924 / 0.827 / 0.1480 (n 640, base 0.294) | 0.925 / 0.827 / 0.1395 (n 640, base 0.294) | 0.973 / 0.955 / 0.0465 (n 640, base 0.294) | 0.746 / 0.491 / 0.1977 (n 640, base 0.294) |

### Hold-out (scored once; ZWE/MWI 2023/24+, KEN 2020-24) — h13

| model | all rows | transition rows (state < 3) |
|---|---|---|
| eo:logreg | 0.860 / 0.737 / 0.1539 (n 4554, base 0.373) | 0.855 / 0.414 / 0.1110 (n 3284, base 0.15) |
| eo:lgbm | 0.903 / 0.836 / 0.1337 (n 4554, base 0.373) | 0.893 / 0.525 / 0.0954 (n 3284, base 0.15) |
| eo_proxy:logreg | 0.871 / 0.764 / 0.1478 (n 4554, base 0.373) | 0.867 / 0.450 / 0.1065 (n 3284, base 0.15) |
| eo_proxy:lgbm | 0.899 / 0.834 / 0.1383 (n 4554, base 0.373) | 0.890 / 0.530 / 0.0942 (n 3284, base 0.15) |
| eo_fews:logreg | 0.951 / 0.916 / 0.0888 (n 4554, base 0.373) | 0.933 / 0.744 / 0.0935 (n 3284, base 0.15) |
| eo_fews:lgbm | 0.963 / 0.940 / 0.0768 (n 4554, base 0.373) | 0.936 / 0.722 / 0.0737 (n 3284, base 0.15) |
| eo_fews_masked:logreg | 0.775 / 0.602 / 0.2017 (n 4554, base 0.373) | 0.796 / 0.323 / 0.1560 (n 3284, base 0.15) |
| eo_fews_masked:lgbm | 0.754 / 0.637 / 0.2031 (n 4554, base 0.373) | 0.747 / 0.314 / 0.1532 (n 3284, base 0.15) |
| persistence | 0.925 / 0.847 / 0.0989 (n 4554, base 0.373) | 0.781 / 0.288 / 0.1082 (n 3284, base 0.15) |
| fews | 0.957 / 0.900 / 0.0619 (n 4554, base 0.373) | 0.938 / 0.735 / 0.0467 (n 3284, base 0.15) |
| eo:ensemble | 0.894 / 0.804 / 0.1391 (n 4554, base 0.373) | 0.884 / 0.476 / 0.0995 (n 3284, base 0.15) |
| eo_proxy:ensemble | 0.893 / 0.809 / 0.1392 (n 4554, base 0.373) | 0.885 / 0.493 / 0.0972 (n 3284, base 0.15) |
| eo_fews:ensemble | 0.964 / 0.942 / 0.0760 (n 4554, base 0.373) | 0.945 / 0.770 / 0.0757 (n 3284, base 0.15) |
| eo_fews_masked:ensemble | 0.792 / 0.669 / 0.1984 (n 4554, base 0.373) | 0.807 / 0.363 / 0.1509 (n 3284, base 0.15) |

### Hold-out by country — h13 (transition rows)

| group | persistence | fews | eo:lgbm | eo:ensemble | eo_proxy:lgbm | eo_proxy:ensemble | eo_fews:lgbm | eo_fews_masked:lgbm |
|---|---|---|---|---|---|---|---|---|
| KEN | 0.842 / 0.122 / 0.0470 (n 2096, base 0.042) | 0.895 / 0.252 / 0.0413 (n 2096, base 0.042) | 0.908 / 0.238 / 0.0443 (n 2096, base 0.042) | 0.899 / 0.208 / 0.0477 (n 2096, base 0.042) | 0.904 / 0.262 / 0.0445 (n 2096, base 0.042) | 0.896 / 0.244 / 0.0478 (n 2096, base 0.042) | 0.915 / 0.289 / 0.0508 (n 2096, base 0.042) | 0.746 / 0.148 / 0.1188 (n 2096, base 0.042) |
| MWI | 0.880 / 0.582 / 0.1361 (n 300, base 0.227) | 0.897 / 0.670 / 0.1212 (n 300, base 0.227) | 0.770 / 0.475 / 0.1492 (n 300, base 0.227) | 0.769 / 0.408 / 0.1597 (n 300, base 0.227) | 0.727 / 0.357 / 0.1616 (n 300, base 0.227) | 0.747 / 0.384 / 0.1604 (n 300, base 0.227) | 0.903 / 0.715 / 0.0992 (n 300, base 0.227) | 0.673 / 0.366 / 0.1797 (n 300, base 0.227) |
| ZWE | 0.525 / 0.391 / 0.2433 (n 888, base 0.378) | 0.981 / 0.967 / 0.0343 (n 888, base 0.378) | 0.759 / 0.601 / 0.1978 (n 888, base 0.378) | 0.753 / 0.602 / 0.2014 (n 888, base 0.378) | 0.773 / 0.626 / 0.1885 (n 888, base 0.378) | 0.772 / 0.618 / 0.1926 (n 888, base 0.378) | 0.938 / 0.915 / 0.1189 (n 888, base 0.378) | 0.629 / 0.495 / 0.2254 (n 888, base 0.378) |

## CV thresholds (transition rows, max F1)

```
{
 "eo": [
  "eo:lgbm",
  {
   "thr": 0.44,
   "tp": 694,
   "fp": 1259,
   "fn": 702,
   "precision": 0.355,
   "recall": 0.497,
   "f1": 0.414,
   "alarm_rate": 0.22
  }
 ],
 "eo_proxy": [
  "eo_proxy:lgbm",
  {
   "thr": 0.46,
   "tp": 704,
   "fp": 1238,
   "fn": 692,
   "precision": 0.363,
   "recall": 0.504,
   "f1": 0.422,
   "alarm_rate": 0.219
  }
 ],
 "eo_fews": [
  "eo_fews:lgbm",
  {
   "thr": 0.32,
   "tp": 971,
   "fp": 723,
   "fn": 425,
   "precision": 0.573,
   "recall": 0.696,
   "f1": 0.628,
   "alarm_rate": 0.191
  }
 ],
 "eo_fews_masked": [
  "eo_fews_masked:lgbm",
  {
   "thr": 0.31,
   "tp": 649,
   "fp": 2373,
   "fn": 747,
   "precision": 0.215,
   "recall": 0.465,
   "f1": 0.294,
   "alarm_rate": 0.34
  }
 ]
}
```

## Replay ZWE 2023/24 (and MWI), CV thresholds

```
{
 "eo": {
  "model": "eo:lgbm",
  "threshold": 0.44,
  "threshold_kind": "f1",
  "n_units": 91,
  "n_oct2023_ipc3": 27,
  "n_transitions": 57,
  "n_never_ipc3_by_oct2024": 0,
  "transitions_warned": 48,
  "transitions_warned_2runs": 45,
  "precision_vs_transition": 0.64,
  "recall_transition": 0.842,
  "warned_before_decl": 30,
  "warned_before_decl_2runs": 28,
  "lead_months_median": 4.0,
  "lead_months_conservative_median": 1.0,
  "lead_months_share_pos": 1.0,
  "lead_weeks_median": 17.4,
  "lead_2runs_months_median": 3.0,
  "first_cross_by_month": {
   "2023-10": 27,
   "2023-11": 2,
   "2024-01": 1,
   "2024-04": 1,
   "2024-05": 1,
   "2024-06": 9,
   "2024-07": 3,
   "2024-08": 4
  },
  "first_cross_2runs_by_month": {
   "2023-11": 26,
   "2023-12": 2,
   "2024-06": 2,
   "2024-07": 11,
   "2024-09": 4
  },
  "first_ipc3_by_month": {
   "2024-02": 15,
   "2024-06": 3,
   "2024-10": 39
  },
  "lead_by_entry_map": {
   "2024-02": 4.0,
   "2024-06": 8.0,
   "2024-10": 4.0
  },
  "fews_proj_warned": 56,
  "fews_proj_before_decl": 15,
  "fews_proj_lead_months_median": 3.0,
  "already_ipc3_oct2023_p_nov23_ge_thr": 27,
  "false_alarms_calm_units": 0
 },
 "eo_MWI": {
  "n_transitions": 4,
  "transitions_warned": 4,
  "warned_before_decl": 0,
  "false_alarms_calm_units": 3,
  "lead_months_median": 3.5
 },
 "eo_proxy": {
  "model": "eo_proxy:lgbm",
  "threshold": 0.46,
  "threshold_kind": "f1",
  "n_units": 91,
  "n_oct2023_ipc3": 27,
  "n_transitions": 57,
  "n_never_ipc3_by_oct2024": 0,
  "transitions_warned": 48,
  "transitions_warned_2runs": 40,
  "precision_vs_transition": 0.64,
  "recall_transition": 0.842,
  "warned_before_decl": 27,
  "warned_before_decl_2runs": 19,
  "lead_months_median": 4.0,
  "lead_months_conservative_median": 1.0,
  "lead_months_share_pos": 1.0,
  "lead_weeks_median": 17.4,
  "lead_2runs_months_median": 3.0,
  "first_cross_by_month": {
   "2023-10": 26,
   "2024-03": 1,
   "2024-06": 4,
   "2024-07": 14,
   "2024-08": 2,
   "2024-09": 1
  },
  "first_cross_2runs_by_month": {
   "2023-11": 19,
   "2024-07": 5,
   "2024-08": 15,
   "2024-09": 1
  },
  "first_ipc3_by_month": {
   "2024-02": 15,
   "2024-06": 3,
   "2024-10": 39
  },
  "lead_by_entry_map": {
   "2024-02": 4.0,
   "2024-06": 8.0,
   "2024-10": 3.0
  },
  "fews_proj_warned": 56,
  "fews_proj_before_decl": 15,
  "fews_proj_lead_months_median": 3.0,
  "already_ipc3_oct2023_p_nov23_ge_thr": 19,
  "false_alarms_calm_units": 0
 },
 "eo_proxy_MWI": {
  "n_transitions": 4,
  "transitions_warned": 2,
  "warned_before_decl": 0,
  "false_alarms_calm_units": 2,
  "lead_months_median": 3.0
 },
 "eo_fews": {
  "model": "eo_fews:lgbm",
  "threshold": 0.32,
  "threshold_kind": "f1",
  "n_units": 91,
  "n_oct2023_ipc3": 27,
  "n_transitions": 57,
  "n_never_ipc3_by_oct2024": 0,
  "transitions_warned": 57,
  "transitions_warned_2runs": 56,
  "precision_vs_transition": 0.838,
  "recall_transition": 1.0,
  "warned_before_decl": 36,
  "warned_before_decl_2runs": 22,
  "lead_months_median": 5.0,
  "lead_months_conservative_median": 2.0,
  "lead_months_share_pos": 1.0,
  "lead_weeks_median": 21.7,
  "lead_2runs_months_median": 4.0,
  "first_cross_by_month": {
   "2023-10": 7,
   "2023-11": 11,
   "2023-12": 12,
   "2024-01": 1,
   "2024-03": 5,
   "2024-04": 7,
   "2024-05": 8,
   "2024-06": 4,
   "2024-07": 2
  },
  "first_cross_2runs_by_month": {
   "2023-11": 6,
   "2023-12": 11,
   "2024-01": 5,
   "2024-04": 5,
   "2024-05": 7,
   "2024-06": 10,
   "2024-07": 7,
   "2024-08": 5
  },
  "first_ipc3_by_month": {
   "2024-02": 15,
   "2024-06": 3,
   "2024-10": 39
  },
  "lead_by_entry_map": {
   "2024-02": 3.0,
   "2024-06": 6.0,
   "2024-10": 6.0
  },
  "fews_proj_warned": 56,
  "fews_proj_before_decl": 15,
  "fews_proj_lead_months_median": 3.0,
  "already_ipc3_oct2023_p_nov23_ge_thr": 27,
  "false_alarms_calm_units": 0
 },
 "eo_fews_MWI": {
  "n_transitions": 4,
  "transitions_warned": 3,
  "warned_before_decl": 0,
  "false_alarms_calm_units": 2,
  "lead_months_median": 3.0
 },
 "eo_fews_masked": {
  "model": "eo_fews_masked:lgbm",
  "threshold": 0.31,
  "threshold_kind": "f1",
  "n_units": 91,
  "n_oct2023_ipc3": 27,
  "n_transitions": 57,
  "n_never_ipc3_by_oct2024": 0,
  "transitions_warned": 57,
  "transitions_warned_2runs": 55,
  "precision_vs_transition": 0.905,
  "recall_transition": 1.0,
  "warned_before_decl": 54,
  "warned_before_decl_2runs": 30,
  "lead_months_median": 8.0,
  "lead_months_conservative_median": 5.0,
  "lead_months_share_pos": 1.0,
  "lead_weeks_median": 34.8,
  "lead_2runs_months_median": 6.0,
  "first_cross_by_month": {
   "2023-10": 16,
   "2023-11": 13,
   "2023-12": 16,
   "2024-03": 9,
   "2024-04": 2,
   "2024-05": 1
  },
  "first_cross_2runs_by_month": {
   "2023-11": 16,
   "2023-12": 13,
   "2024-01": 1,
   "2024-04": 20,
   "2024-05": 3,
   "2024-06": 1,
   "2024-08": 1
  },
  "first_ipc3_by_month": {
   "2024-02": 15,
   "2024-06": 3,
   "2024-10": 39
  },
  "lead_by_entry_map": {
   "2024-02": 4.0,
   "2024-06": 8.0,
   "2024-10": 10.0
  },
  "fews_proj_warned": 56,
  "fews_proj_before_decl": 15,
  "fews_proj_lead_months_median": 3.0,
  "already_ipc3_oct2023_p_nov23_ge_thr": 17,
  "false_alarms_calm_units": 0
 },
 "eo_fews_masked_MWI": {
  "n_transitions": 4,
  "transitions_warned": 4,
  "warned_before_decl": 0,
  "false_alarms_calm_units": 10,
  "lead_months_median": 7.0
 }
}
```

## Season bootstrap (transition rows)

```
{
 "persistence": {
  "pr_5_95": [
   0.2,
   0.323
  ],
  "roc_5_95": [
   0.665,
   0.763
  ]
 },
 "fews": {
  "pr_5_95": [
   0.447,
   0.619
  ],
  "roc_5_95": [
   0.807,
   0.921
  ]
 },
 "eo:lgbm": {
  "pr_5_95": [
   0.304,
   0.447
  ],
  "roc_5_95": [
   0.739,
   0.818
  ]
 },
 "eo_proxy:lgbm": {
  "pr_5_95": [
   0.304,
   0.432
  ],
  "roc_5_95": [
   0.745,
   0.824
  ]
 },
 "eo_fews:lgbm": {
  "pr_5_95": [
   0.46,
   0.712
  ],
  "roc_5_95": [
   0.823,
   0.92
  ]
 },
 "eo_fews_masked:lgbm": {
  "pr_5_95": [
   0.171,
   0.315
  ],
  "roc_5_95": [
   0.553,
   0.655
  ]
 }
}
```

## LightGBM gain (hold-out models)

```
{
 "eo": {
  "grass_frac": 27447.2,
  "crop_frac": 19068.4,
  "price_price_anom": 9519.2,
  "south": 7110.6,
  "oni": 6382.4,
  "oni_x_south": 5576.1,
  "spi_6m_l3": 4473.5,
  "month_cos": 3258.2,
  "oni_d3": 3244.3,
  "sm2_z": 2011.9,
  "price_tot_anom": 1632.9,
  "spi_6m_l2": 1355.4,
  "onset_anom": 1300.2,
  "month_sin": 1149.0,
  "price_livestock_price_anom": 966.2
 },
 "eo_proxy": {
  "p_proxy": 40873.6,
  "crop_frac": 10604.2,
  "grass_frac": 9942.6,
  "oni": 7630.9,
  "oni_x_south": 4269.0,
  "price_price_anom": 4105.5,
  "oni_d3": 4057.7,
  "spi_6m_l3": 3476.2,
  "month_cos": 2571.3,
  "onset_anom": 1918.1,
  "spi_6m_tr3": 1484.2,
  "sm2_z": 1349.8,
  "sfc_z46": 1342.0,
  "south": 1327.3,
  "t2m_z": 1009.6
 },
 "eo_fews": {
  "fdw_ml1": 43125.3,
  "fdw_ml2": 36112.8,
  "fdw_ml1_share3": 20397.7,
  "oni_x_south": 5468.4,
  "oni_d3": 4943.3,
  "price_price_anom": 3808.2,
  "oni": 3567.9,
  "grass_frac": 2964.1,
  "phase_m": 2950.9,
  "fdw_age": 2065.6,
  "crop_frac": 2006.9,
  "ol_cur": 1943.6,
  "ol_n": 1903.5,
  "sfc_z46": 1887.7,
  "onset_anom": 1621.0
 }
}
```
