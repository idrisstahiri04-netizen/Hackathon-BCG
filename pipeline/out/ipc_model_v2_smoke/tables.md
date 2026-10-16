# IPC-target model v2: auto tables (train_ipc_v2.py)

Cells: ROC-AUC / PR-AUC (raw score) / Brier (calibrated p). 'transition rows' = state at issue < IPC3.

Label base rates per country (rows with known state):

```
{
 "MWI": {
  "y_h13": 0.177,
  "transition_h13": 0.106,
  "rows_known_state": 2966
 }
}
```

### Cross-validation (pooled MWI, leave-one-season-out) — h13

| model | all rows | transition rows (state < 3) |
|---|---|---|
| persistence | 0.797 / 0.373 / 0.1022 (n 2458, base 0.126) | 0.745 / 0.256 / 0.0873 (n 2266, base 0.094) |
| fews | 0.896 / 0.502 / 0.0745 (n 2430, base 0.123) | 0.886 / 0.415 / 0.0629 (n 2238, base 0.089) |
| eo:logreg | 0.279 / 0.081 / 0.1147 (n 2458, base 0.126) | 0.257 / 0.058 / 0.0893 (n 2266, base 0.094) |
| eo:lgbm | 0.214 / 0.076 / 0.1147 (n 2458, base 0.126) | 0.223 / 0.056 / 0.0893 (n 2266, base 0.094) |
| eo_p:logreg | 0.431 / 0.112 / 0.1150 (n 2458, base 0.126) | 0.390 / 0.071 / 0.0906 (n 2266, base 0.094) |
| eo_p:lgbm | 0.317 / 0.090 / 0.1203 (n 2458, base 0.126) | 0.315 / 0.065 / 0.0929 (n 2266, base 0.094) |
| eo_fews:logreg | 0.540 / 0.174 / 0.1178 (n 2458, base 0.126) | 0.496 / 0.117 / 0.0942 (n 2266, base 0.094) |
| eo_fews:lgbm | 0.662 / 0.242 / 0.1124 (n 2458, base 0.126) | 0.696 / 0.188 / 0.0896 (n 2266, base 0.094) |
| eo_fews_p:logreg | 0.617 / 0.206 / 0.1175 (n 2458, base 0.126) | 0.589 / 0.141 / 0.0955 (n 2266, base 0.094) |
| eo_fews_p:lgbm | 0.658 / 0.248 / 0.1143 (n 2458, base 0.126) | 0.685 / 0.196 / 0.0927 (n 2266, base 0.094) |
| full:logreg | 0.625 / 0.204 / 0.1358 (n 2458, base 0.126) | 0.579 / 0.132 / 0.1102 (n 2266, base 0.094) |
| full:lgbm | 0.674 / 0.251 / 0.1115 (n 2458, base 0.126) | 0.683 / 0.182 / 0.0897 (n 2266, base 0.094) |
| eo:ensemble | 0.238 / 0.090 / 0.1146 (n 2458, base 0.126) | 0.252 / 0.068 / 0.0892 (n 2266, base 0.094) |
| eo_p:ensemble | 0.250 / 0.091 / 0.1172 (n 2458, base 0.126) | 0.232 / 0.065 / 0.0914 (n 2266, base 0.094) |
| eo_fews:ensemble | 0.521 / 0.172 / 0.1135 (n 2458, base 0.126) | 0.511 / 0.122 / 0.0903 (n 2266, base 0.094) |
| eo_fews_p:ensemble | 0.528 / 0.192 / 0.1143 (n 2458, base 0.126) | 0.512 / 0.125 / 0.0926 (n 2266, base 0.094) |
| full:ensemble | 0.545 / 0.181 / 0.1197 (n 2458, base 0.126) | 0.510 / 0.121 / 0.0969 (n 2266, base 0.094) |

### CV by country — h13 (transition rows)

| group | persistence | fews | eo:lgbm | eo_p:lgbm | eo_fews:lgbm | eo_fews_p:lgbm | full:lgbm |
|---|---|---|---|---|---|---|---|
| MWI | 0.745 / 0.256 / 0.0873 (n 2266, base 0.094) | 0.886 / 0.415 / 0.0629 (n 2238, base 0.089) | 0.223 / 0.056 / 0.0893 (n 2266, base 0.094) | 0.315 / 0.065 / 0.0929 (n 2266, base 0.094) | 0.696 / 0.188 / 0.0896 (n 2266, base 0.094) | 0.685 / 0.196 / 0.0927 (n 2266, base 0.094) | 0.683 / 0.182 / 0.0897 (n 2266, base 0.094) |

### CV ZWE by season — h13 (transition rows)

| group | persistence | fews | eo:lgbm | eo_fews:lgbm | full:lgbm |
|---|---|---|---|---|---|

### Hold-out (evaluated once; agyear >= 2023 all countries, KEN 2020-24) — h13

| model | all rows | transition rows (state < 3) |
|---|---|---|
| eo:logreg | 0.580 / 0.500 / 0.3460 (n 504, base 0.444) | 0.576 / 0.235 / 0.1607 (n 328, base 0.195) |
| eo:lgbm | 0.579 / 0.485 / 0.3482 (n 504, base 0.444) | 0.503 / 0.197 / 0.1618 (n 328, base 0.195) |
| eo_p:logreg | 0.581 / 0.526 / 0.3424 (n 504, base 0.444) | 0.585 / 0.257 / 0.1600 (n 328, base 0.195) |
| eo_p:lgbm | 0.644 / 0.597 / 0.3482 (n 504, base 0.444) | 0.607 / 0.283 / 0.1618 (n 328, base 0.195) |
| eo_fews:logreg | 0.929 / 0.864 / 0.2445 (n 504, base 0.444) | 0.934 / 0.743 / 0.1259 (n 328, base 0.195) |
| eo_fews:lgbm | 0.901 / 0.848 / 0.2471 (n 504, base 0.444) | 0.865 / 0.593 / 0.1332 (n 328, base 0.195) |
| eo_fews_p:logreg | 0.902 / 0.834 / 0.2368 (n 504, base 0.444) | 0.883 / 0.641 / 0.1271 (n 328, base 0.195) |
| eo_fews_p:lgbm | 0.901 / 0.854 / 0.2302 (n 504, base 0.444) | 0.857 / 0.563 / 0.1349 (n 328, base 0.195) |
| full:logreg | 0.893 / 0.825 / 0.2579 (n 504, base 0.444) | 0.838 / 0.626 / 0.1360 (n 328, base 0.195) |
| full:lgbm | 0.879 / 0.818 / 0.2442 (n 504, base 0.444) | 0.831 / 0.501 / 0.1399 (n 328, base 0.195) |
| persistence | 0.931 / 0.846 / 0.1550 (n 504, base 0.444) | 0.920 / 0.567 / 0.1193 (n 328, base 0.195) |
| fews | 0.932 / 0.862 / 0.1721 (n 504, base 0.444) | 0.930 / 0.696 / 0.1033 (n 328, base 0.195) |
| eo:ensemble | 0.529 / 0.459 / 0.3470 (n 504, base 0.444) | 0.530 / 0.205 / 0.1611 (n 328, base 0.195) |
| eo_p:ensemble | 0.550 / 0.470 / 0.3452 (n 504, base 0.444) | 0.531 / 0.204 / 0.1607 (n 328, base 0.195) |
| eo_fews:ensemble | 0.929 / 0.888 / 0.2440 (n 504, base 0.444) | 0.894 / 0.671 / 0.1283 (n 328, base 0.195) |
| eo_fews_p:ensemble | 0.910 / 0.861 / 0.2311 (n 504, base 0.444) | 0.873 / 0.593 / 0.1284 (n 328, base 0.195) |
| full:ensemble | 0.894 / 0.855 / 0.2487 (n 504, base 0.444) | 0.834 / 0.576 / 0.1360 (n 328, base 0.195) |

### Hold-out by country — h13 (transition rows)

| group | persistence | fews | eo:lgbm | eo_p:lgbm | eo_fews:lgbm | eo_fews_p:lgbm | full:lgbm |
|---|---|---|---|---|---|---|---|
| MWI | 0.920 / 0.567 / 0.1193 (n 328, base 0.195) | 0.930 / 0.696 / 0.1033 (n 328, base 0.195) | 0.503 / 0.197 / 0.1618 (n 328, base 0.195) | 0.607 / 0.283 / 0.1618 (n 328, base 0.195) | 0.865 / 0.593 / 0.1332 (n 328, base 0.195) | 0.857 / 0.563 / 0.1349 (n 328, base 0.195) | 0.831 / 0.501 / 0.1399 (n 328, base 0.195) |

### Cross-validation (pooled MWI, leave-one-season-out) — h46

| model | all rows | transition rows (state < 3) |
|---|---|---|
| persistence | 0.689 / 0.229 / 0.1217 (n 2459, base 0.135) | 0.696 / 0.269 / 0.1127 (n 2267, base 0.127) |
| fews | 0.857 / 0.466 / 0.1022 (n 1564, base 0.147) | 0.883 / 0.540 / 0.0846 (n 1439, base 0.137) |
| eo:logreg | 0.317 / 0.104 / 0.1233 (n 2459, base 0.135) | 0.303 / 0.099 / 0.1171 (n 2267, base 0.127) |
| eo:lgbm | 0.279 / 0.089 / 0.1218 (n 2459, base 0.135) | 0.286 / 0.084 / 0.1157 (n 2267, base 0.127) |
| eo_p:logreg | 0.339 / 0.097 / 0.1249 (n 2459, base 0.135) | 0.340 / 0.092 / 0.1182 (n 2267, base 0.127) |
| eo_p:lgbm | 0.271 / 0.087 / 0.1288 (n 2459, base 0.135) | 0.284 / 0.083 / 0.1215 (n 2267, base 0.127) |
| eo_fews:logreg | 0.550 / 0.193 / 0.1226 (n 2459, base 0.135) | 0.569 / 0.204 / 0.1142 (n 2267, base 0.127) |
| eo_fews:lgbm | 0.633 / 0.268 / 0.1143 (n 2459, base 0.135) | 0.659 / 0.299 / 0.1052 (n 2267, base 0.127) |
| eo_fews_p:logreg | 0.544 / 0.167 / 0.1275 (n 2459, base 0.135) | 0.569 / 0.187 / 0.1187 (n 2267, base 0.127) |
| eo_fews_p:lgbm | 0.614 / 0.228 / 0.1213 (n 2459, base 0.135) | 0.644 / 0.260 / 0.1118 (n 2267, base 0.127) |
| full:logreg | 0.553 / 0.175 / 0.1357 (n 2459, base 0.135) | 0.590 / 0.189 / 0.1277 (n 2267, base 0.127) |
| full:lgbm | 0.573 / 0.191 / 0.1253 (n 2459, base 0.135) | 0.610 / 0.219 / 0.1167 (n 2267, base 0.127) |
| eo:ensemble | 0.212 / 0.090 / 0.1225 (n 2459, base 0.135) | 0.217 / 0.085 / 0.1163 (n 2267, base 0.127) |
| eo_p:ensemble | 0.201 / 0.087 / 0.1267 (n 2459, base 0.135) | 0.208 / 0.083 / 0.1197 (n 2267, base 0.127) |
| eo_fews:ensemble | 0.526 / 0.203 / 0.1161 (n 2459, base 0.135) | 0.545 / 0.235 / 0.1075 (n 2267, base 0.127) |
| eo_fews_p:ensemble | 0.475 / 0.163 / 0.1217 (n 2459, base 0.135) | 0.509 / 0.191 / 0.1126 (n 2267, base 0.127) |
| full:ensemble | 0.462 / 0.135 / 0.1280 (n 2459, base 0.135) | 0.505 / 0.146 / 0.1196 (n 2267, base 0.127) |

### CV by country — h46 (transition rows)

| group | persistence | fews | eo:lgbm | eo_p:lgbm | eo_fews:lgbm | eo_fews_p:lgbm | full:lgbm |
|---|---|---|---|---|---|---|---|
| MWI | 0.696 / 0.269 / 0.1127 (n 2267, base 0.127) | 0.883 / 0.540 / 0.0846 (n 1439, base 0.137) | 0.286 / 0.084 / 0.1157 (n 2267, base 0.127) | 0.284 / 0.083 / 0.1215 (n 2267, base 0.127) | 0.659 / 0.299 / 0.1052 (n 2267, base 0.127) | 0.644 / 0.260 / 0.1118 (n 2267, base 0.127) | 0.610 / 0.219 / 0.1167 (n 2267, base 0.127) |

### CV ZWE by season — h46 (transition rows)

| group | persistence | fews | eo:lgbm | eo_fews:lgbm | full:lgbm |
|---|---|---|---|---|---|

### Hold-out (evaluated once; agyear >= 2023 all countries, KEN 2020-24) — h46

| model | all rows | transition rows (state < 3) |
|---|---|---|
| eo:logreg | 0.442 / 0.453 / 0.3742 (n 448, base 0.489) | 0.506 / 0.285 / 0.2145 (n 289, base 0.27) |
| eo:lgbm | 0.566 / 0.590 / 0.3754 (n 448, base 0.489) | 0.645 / 0.435 / 0.2154 (n 289, base 0.27) |
| eo_p:logreg | 0.480 / 0.490 / 0.3746 (n 448, base 0.489) | 0.558 / 0.316 / 0.2151 (n 289, base 0.27) |
| eo_p:lgbm | 0.565 / 0.581 / 0.3753 (n 448, base 0.489) | 0.665 / 0.459 / 0.2153 (n 289, base 0.27) |
| eo_fews:logreg | 0.791 / 0.743 / 0.2898 (n 448, base 0.489) | 0.844 / 0.603 / 0.1757 (n 289, base 0.27) |
| eo_fews:lgbm | 0.732 / 0.703 / 0.3122 (n 448, base 0.489) | 0.809 / 0.551 / 0.1734 (n 289, base 0.27) |
| eo_fews_p:logreg | 0.789 / 0.746 / 0.3060 (n 448, base 0.489) | 0.840 / 0.604 / 0.1817 (n 289, base 0.27) |
| eo_fews_p:lgbm | 0.688 / 0.657 / 0.3182 (n 448, base 0.489) | 0.775 / 0.523 / 0.1773 (n 289, base 0.27) |
| full:logreg | 0.751 / 0.711 / 0.3217 (n 448, base 0.489) | 0.794 / 0.574 / 0.1907 (n 289, base 0.27) |
| full:lgbm | 0.735 / 0.695 / 0.3384 (n 448, base 0.489) | 0.829 / 0.580 / 0.1874 (n 289, base 0.27) |
| persistence | 0.900 / 0.833 / 0.2635 (n 448, base 0.489) | 0.883 / 0.669 / 0.1595 (n 289, base 0.27) |
| fews | 0.890 / 0.816 / 0.1684 (n 336, base 0.467) | 0.878 / 0.706 / 0.1251 (n 225, base 0.267) |
| eo:ensemble | 0.494 / 0.493 / 0.3747 (n 448, base 0.489) | 0.503 / 0.281 / 0.2149 (n 289, base 0.27) |
| eo_p:ensemble | 0.500 / 0.489 / 0.3750 (n 448, base 0.489) | 0.500 / 0.270 / 0.2152 (n 289, base 0.27) |
| eo_fews:ensemble | 0.805 / 0.764 / 0.2928 (n 448, base 0.489) | 0.865 / 0.669 / 0.1691 (n 289, base 0.27) |
| eo_fews_p:ensemble | 0.767 / 0.723 / 0.3095 (n 448, base 0.489) | 0.842 / 0.624 / 0.1772 (n 289, base 0.27) |
| full:ensemble | 0.780 / 0.726 / 0.3290 (n 448, base 0.489) | 0.844 / 0.599 / 0.1882 (n 289, base 0.27) |

### Hold-out by country — h46 (transition rows)

| group | persistence | fews | eo:lgbm | eo_p:lgbm | eo_fews:lgbm | eo_fews_p:lgbm | full:lgbm |
|---|---|---|---|---|---|---|---|
| MWI | 0.883 / 0.669 / 0.1595 (n 289, base 0.27) | 0.878 / 0.706 / 0.1251 (n 225, base 0.267) | 0.645 / 0.435 / 0.2154 (n 289, base 0.27) | 0.665 / 0.459 / 0.2153 (n 289, base 0.27) | 0.809 / 0.551 / 0.1734 (n 289, base 0.27) | 0.775 / 0.523 / 0.1773 (n 289, base 0.27) | 0.829 / 0.580 / 0.1874 (n 289, base 0.27) |

## Thresholds (CV OOF transition rows)

```
{
 "h13": {
  "eo": {
   "winner": "eo:ensemble",
   "cv_transition_pr": {
    "logreg": 0.058,
    "lgbm": 0.056,
    "ensemble": 0.068
   },
   "f1": {
    "thr": 0.07,
    "tp": 211,
    "fp": 2008,
    "fn": 1,
    "precision": 0.095,
    "recall": 0.995,
    "f1": 0.174,
    "alarm_rate": 0.979
   },
   "p60": null,
   "n_rows": 2266,
   "base": 0.094
  },
  "eo_p": {
   "winner": "eo_p:logreg",
   "cv_transition_pr": {
    "logreg": 0.071,
    "lgbm": 0.065,
    "ensemble": 0.065
   },
   "f1": {
    "thr": 0.06,
    "tp": 210,
    "fp": 1956,
    "fn": 2,
    "precision": 0.097,
    "recall": 0.991,
    "f1": 0.177,
    "alarm_rate": 0.956
   },
   "p60": null,
   "n_rows": 2266,
   "base": 0.094
  },
  "eo_fews": {
   "winner": "eo_fews:lgbm",
   "cv_transition_pr": {
    "logreg": 0.117,
    "lgbm": 0.188,
    "ensemble": 0.122
   },
   "f1": {
    "thr": 0.21,
    "tp": 79,
    "fp": 256,
    "fn": 133,
    "precision": 0.236,
    "recall": 0.373,
    "f1": 0.289,
    "alarm_rate": 0.148
   },
   "p60": null,
   "n_rows": 2266,
   "base": 0.094
  },
  "eo_fews_p": {
   "winner": "eo_fews_p:lgbm",
   "cv_transition_pr": {
    "logreg": 0.141,
    "lgbm": 0.196,
    "ensemble": 0.125
   },
   "f1": {
    "thr": 0.16,
    "tp": 88,
    "fp": 393,
    "fn": 124,
    "precision": 0.183,
    "recall": 0.415,
    "f1": 0.254,
    "alarm_rate": 0.212
   },
   "p60": null,
   "n_rows": 2266,
   "base": 0.094
  },
  "full": {
   "winner": "full:lgbm",
   "cv_transition_pr": {
    "logreg": 0.132,
    "lgbm": 0.182,
    "ensemble": 0.121
   },
   "f1": {
    "thr": 0.18,
    "tp": 70,
    "fp": 164,
    "fn": 142,
    "precision": 0.299,
    "recall": 0.33,
    "f1": 0.314,
    "alarm_rate": 0.103
   },
   "p60": null,
   "n_rows": 2266,
   "base": 0.094
  }
 },
 "h46": {
  "eo": {
   "winner": "eo:logreg",
   "cv_transition_pr": {
    "logreg": 0.099,
    "lgbm": 0.084,
    "ensemble": 0.085
   },
   "f1": {
    "thr": 0.05,
    "tp": 273,
    "fp": 1949,
    "fn": 15,
    "precision": 0.123,
    "recall": 0.948,
    "f1": 0.218,
    "alarm_rate": 0.98
   },
   "p60": null,
   "n_rows": 2267,
   "base": 0.127
  },
  "eo_p": {
   "winner": "eo_p:logreg",
   "cv_transition_pr": {
    "logreg": 0.092,
    "lgbm": 0.083,
    "ensemble": 0.083
   },
   "f1": {
    "thr": 0.05,
    "tp": 258,
    "fp": 1919,
    "fn": 30,
    "precision": 0.119,
    "recall": 0.896,
    "f1": 0.209,
    "alarm_rate": 0.96
   },
   "p60": null,
   "n_rows": 2267,
   "base": 0.127
  },
  "eo_fews": {
   "winner": "eo_fews:lgbm",
   "cv_transition_pr": {
    "logreg": 0.204,
    "lgbm": 0.299,
    "ensemble": 0.235
   },
   "f1": {
    "thr": 0.19,
    "tp": 133,
    "fp": 171,
    "fn": 155,
    "precision": 0.438,
    "recall": 0.462,
    "f1": 0.449,
    "alarm_rate": 0.134
   },
   "p60": null,
   "n_rows": 2267,
   "base": 0.127
  },
  "eo_fews_p": {
   "winner": "eo_fews_p:lgbm",
   "cv_transition_pr": {
    "logreg": 0.187,
    "lgbm": 0.26,
    "ensemble": 0.191
   },
   "f1": {
    "thr": 0.26,
    "tp": 118,
    "fp": 268,
    "fn": 170,
    "precision": 0.306,
    "recall": 0.41,
    "f1": 0.35,
    "alarm_rate": 0.17
   },
   "p60": null,
   "n_rows": 2267,
   "base": 0.127
  },
  "full": {
   "winner": "full:lgbm",
   "cv_transition_pr": {
    "logreg": 0.189,
    "lgbm": 0.219,
    "ensemble": 0.146
   },
   "f1": {
    "thr": 0.12,
    "tp": 170,
    "fp": 655,
    "fn": 118,
    "precision": 0.206,
    "recall": 0.59,
    "f1": 0.305,
    "alarm_rate": 0.364
   },
   "p60": null,
   "n_rows": 2267,
   "base": 0.127
  }
 }
}
```

## Season bootstrap (transition rows, h13)

```
{
 "persistence": {
  "pr_5_95": [
   0.098,
   0.473
  ],
  "roc_5_95": [
   0.574,
   0.875
  ]
 },
 "fews": {
  "pr_5_95": [
   0.245,
   0.549
  ],
  "roc_5_95": [
   0.813,
   0.937
  ]
 },
 "eo:logreg": {
  "pr_5_95": [
   0.03,
   0.106
  ],
  "roc_5_95": [
   0.165,
   0.366
  ]
 },
 "eo:lgbm": {
  "pr_5_95": [
   0.027,
   0.099
  ],
  "roc_5_95": [
   0.102,
   0.349
  ]
 },
 "eo_p:logreg": {
  "pr_5_95": [
   0.033,
   0.118
  ],
  "roc_5_95": [
   0.285,
   0.483
  ]
 },
 "eo_p:lgbm": {
  "pr_5_95": [
   0.032,
   0.11
  ],
  "roc_5_95": [
   0.194,
   0.448
  ]
 },
 "eo_fews:logreg": {
  "pr_5_95": [
   0.05,
   0.297
  ],
  "roc_5_95": [
   0.326,
   0.685
  ]
 },
 "eo_fews:lgbm": {
  "pr_5_95": [
   0.101,
   0.359
  ],
  "roc_5_95": [
   0.615,
   0.83
  ]
 },
 "eo_fews_p:logreg": {
  "pr_5_95": [
   0.07,
   0.274
  ],
  "roc_5_95": [
   0.417,
   0.779
  ]
 },
 "eo_fews_p:lgbm": {
  "pr_5_95": [
   0.13,
   0.352
  ],
  "roc_5_95": [
   0.597,
   0.833
  ]
 },
 "full:logreg": {
  "pr_5_95": [
   0.055,
   0.266
  ],
  "roc_5_95": [
   0.398,
   0.748
  ]
 },
 "full:lgbm": {
  "pr_5_95": [
   0.092,
   0.396
  ],
  "roc_5_95": [
   0.589,
   0.835
  ]
 },
 "eo:ensemble": {
  "pr_5_95": [
   0.033,
   0.119
  ],
  "roc_5_95": [
   0.141,
   0.403
  ]
 },
 "eo_p:ensemble": {
  "pr_5_95": [
   0.032,
   0.114
  ],
  "roc_5_95": [
   0.142,
   0.359
  ]
 },
 "eo_fews:ensemble": {
  "pr_5_95": [
   0.069,
   0.257
  ],
  "roc_5_95": [
   0.423,
   0.67
  ]
 },
 "eo_fews_p:ensemble": {
  "pr_5_95": [
   0.077,
   0.247
  ],
  "roc_5_95": [
   0.379,
   0.75
  ]
 },
 "full:ensemble": {
  "pr_5_95": [
   0.062,
   0.279
  ],
  "roc_5_95": [
   0.359,
   0.674
  ]
 }
}
```

## Replay ZWE 2023/24

```
{
 "eo:f1": {
  "note": "no ZWE rows"
 },
 "eo_p:f1": {
  "note": "no ZWE rows"
 },
 "eo_fews:f1": {
  "note": "no ZWE rows"
 },
 "eo_fews_p:f1": {
  "note": "no ZWE rows"
 },
 "full:f1": {
  "note": "no ZWE rows"
 }
}
```

## ZWE monthly

Empty DataFrame
Columns: []
Index: []

## LightGBM gain, hold-out models

```
{
 "eo": {
  "month_sin": 750.2,
  "oni": 420.5,
  "oni_d3": 385.2,
  "sm2_z_l3": 376.3,
  "spi_3m_l1": 179.7,
  "ndvi_z_crop_l1": 160.6,
  "t2m_z_l1": 158.6,
  "grass_frac": 153.6,
  "spi_3m_tr3": 148.1,
  "vci_crop_l1": 144.0,
  "sm2_z_tr3": 141.9,
  "spi_3m_l2": 120.6,
  "sfc_z46": 120.6,
  "sfc_z13_l1": 100.4,
  "month_cos": 89.8,
  "ndvi_z_crop_l3": 80.2,
  "ndvi_z_crop": 79.8,
  "spi_1m": 78.3,
  "vci_crop": 78.2,
  "sm1_z_tr3": 77.2
 },
 "eo_p": {
  "price_price_anom": 1152.1,
  "oni": 499.9,
  "oni_d3": 472.3,
  "spi_3m_l2": 390.7,
  "month_sin": 330.2,
  "spi_6m_tr3": 248.7,
  "sm2_z_l3": 246.0,
  "grass_frac": 196.5,
  "oni_x_south": 166.7,
  "t2m_z_l1": 126.1,
  "vci_crop_l3": 125.7,
  "sfc_z46": 111.5,
  "sm1_z_l3": 99.2,
  "spi_3m_l1": 94.9,
  "ndvi_z_crop_l1": 89.2,
  "spi_3m_tr3": 69.4,
  "sfc_p46": 67.8,
  "sfc_z13": 64.7,
  "sm1_z_tr3": 64.4,
  "vci_crop_l1": 53.9
 },
 "eo_fews": {
  "fdw_ml2": 4578.1,
  "fdw_ml1": 703.9,
  "fdw_ml1_share3": 432.6,
  "month_sin": 412.9,
  "oni_d3": 356.7,
  "oni": 307.1,
  "fdw_age": 156.7,
  "sm2_z_tr3": 116.9,
  "grass_frac": 105.7,
  "sfc_p46": 90.2,
  "spi_3m_l2": 76.4,
  "ndvi_z_crop_l1": 61.9,
  "vci_crop_tr3": 51.6,
  "sm2_z_l3": 45.4,
  "sfc_z13_l1": 44.3,
  "oni_x_south": 39.5,
  "spi_3m_tr3": 38.3,
  "ndvi_z_crop_tr3": 37.6,
  "sfc_z13": 35.8,
  "t2m_z_l1": 31.0
 },
 "eo_fews_p": {
  "fdw_ml2": 4151.8,
  "fdw_ml1": 759.3,
  "fdw_ml1_share3": 612.6,
  "price_price_anom": 416.9,
  "month_sin": 375.0,
  "oni_d3": 316.3,
  "oni": 250.6,
  "fdw_age": 234.6,
  "spi_3m_l2": 177.3,
  "oni_x_south": 177.2,
  "sfc_z46": 87.5,
  "sm2_z_tr3": 77.6,
  "grass_frac": 66.9,
  "sfc_p46": 64.8,
  "spi_6m_l2": 46.5,
  "crop_frac": 33.4,
  "sm2_z_l3": 31.8,
  "spi_6m_l1": 27.1,
  "t2m_z": 26.2,
  "spi_3m": 24.0
 },
 "full": {
  "fdw_ml2": 2755.3,
  "fdw_ml1": 1125.1,
  "month_sin": 752.9,
  "st_phase": 678.4,
  "fdw_ml1_share3": 613.3,
  "oni": 491.4,
  "oni_d3": 414.2,
  "price_price_anom": 375.7,
  "fdw_age": 217.3,
  "spi_6m_tr3": 88.7,
  "st_delta4": 76.1,
  "st_share3": 70.6,
  "grass_frac": 58.1,
  "sfc_p46": 55.9,
  "oni_x_south": 55.2,
  "t2m_z": 54.0,
  "spi_3m_l2": 50.6,
  "spi_3m_l1": 44.7,
  "spi_6m_l2": 44.0,
  "sfc_p13": 42.7
 }
}
```
