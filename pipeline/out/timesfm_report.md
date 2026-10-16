# TimesFM zero-shot VCI forecast report (ZWE)

Model: `google/timesfm-2.5-200m-pytorch` (zero-shot, CPU). Input: `pipeline/data/signals_ZWE.parquet`. Units: 91. Origins 2015-01..2024-06. Leads [1, 2, 3]. max_context=256 months, flip_invariance=False, batch=512. Forecast wall time: 3028s.

Baselines: persistence = last observed value at origin; climatology = mean of same calendar month using only months <= origin. Event = VCI < 35 (hit rate = hits/events; false-alarm ratio = false alarms/(hits+false alarms)). Rows with missing obs or baseline are dropped.

Caveat: VCI is scaled with 2001-2020 min/max, so the input itself carries mild look-ahead for 2015-2020 origins (same for all methods).


## Back-test: origins 2015-01 .. 2022-12

| signal | lead | method | n | MAE | events | hits | false alarms | hit rate | false-alarm ratio |
|---|---|---|---|---|---|---|---|---|---|
| vci_crop | 1 | timesfm | 8441 | 15.38 | 2878 | 1981 | 679 | 0.69 | 0.26 |
| vci_crop | 1 | persist | 8441 | 16.33 | 2878 | 2084 | 807 | 0.72 | 0.28 |
| vci_crop | 1 | clim | 8441 | 23.82 | 2878 | 260 | 155 | 0.09 | 0.37 |
| vci_crop | 2 | timesfm | 8441 | 20.18 | 2873 | 1492 | 766 | 0.52 | 0.34 |
| vci_crop | 2 | persist | 8441 | 22.46 | 2873 | 1722 | 1170 | 0.60 | 0.40 |
| vci_crop | 2 | clim | 8441 | 23.94 | 2873 | 261 | 156 | 0.09 | 0.37 |
| vci_crop | 3 | timesfm | 8441 | 22.18 | 2842 | 1155 | 733 | 0.41 | 0.39 |
| vci_crop | 3 | persist | 8441 | 26.03 | 2842 | 1504 | 1387 | 0.53 | 0.48 |
| vci_crop | 3 | clim | 8441 | 23.87 | 2842 | 261 | 156 | 0.09 | 0.37 |
| vci_grass | 1 | timesfm | 8734 | 15.60 | 2443 | 1517 | 614 | 0.62 | 0.29 |
| vci_grass | 1 | persist | 8734 | 16.33 | 2443 | 1670 | 783 | 0.68 | 0.32 |
| vci_grass | 1 | clim | 8734 | 24.41 | 2443 | 241 | 219 | 0.10 | 0.48 |
| vci_grass | 2 | timesfm | 8734 | 20.35 | 2443 | 1028 | 618 | 0.42 | 0.38 |
| vci_grass | 2 | persist | 8734 | 22.21 | 2443 | 1335 | 1118 | 0.55 | 0.46 |
| vci_grass | 2 | clim | 8734 | 24.52 | 2443 | 241 | 219 | 0.10 | 0.48 |
| vci_grass | 3 | timesfm | 8734 | 22.34 | 2418 | 731 | 588 | 0.30 | 0.45 |
| vci_grass | 3 | persist | 8734 | 25.41 | 2418 | 1128 | 1325 | 0.47 | 0.54 |
| vci_grass | 3 | clim | 8734 | 24.48 | 2418 | 241 | 219 | 0.10 | 0.48 |


## Crisis: targets 2023-10 .. 2024-04

| signal | lead | method | n | MAE | events | hits | false alarms | hit rate | false-alarm ratio |
|---|---|---|---|---|---|---|---|---|---|
| vci_crop | 1 | timesfm | 616 | 20.97 | 256 | 123 | 43 | 0.48 | 0.26 |
| vci_crop | 1 | persist | 616 | 22.01 | 256 | 132 | 67 | 0.52 | 0.34 |
| vci_crop | 1 | clim | 616 | 26.34 | 256 | 11 | 18 | 0.04 | 0.62 |
| vci_crop | 2 | timesfm | 616 | 24.53 | 256 | 66 | 44 | 0.26 | 0.40 |
| vci_crop | 2 | persist | 616 | 26.35 | 256 | 92 | 84 | 0.36 | 0.48 |
| vci_crop | 2 | clim | 616 | 26.34 | 256 | 11 | 18 | 0.04 | 0.62 |
| vci_crop | 3 | timesfm | 616 | 25.30 | 256 | 44 | 42 | 0.17 | 0.49 |
| vci_crop | 3 | persist | 616 | 27.87 | 256 | 94 | 87 | 0.37 | 0.48 |
| vci_crop | 3 | clim | 616 | 26.34 | 256 | 11 | 18 | 0.04 | 0.62 |
| vci_grass | 1 | timesfm | 637 | 21.00 | 183 | 69 | 30 | 0.38 | 0.30 |
| vci_grass | 1 | persist | 637 | 22.55 | 183 | 84 | 51 | 0.46 | 0.38 |
| vci_grass | 1 | clim | 637 | 23.99 | 183 | 7 | 21 | 0.04 | 0.75 |
| vci_grass | 2 | timesfm | 637 | 23.34 | 183 | 33 | 31 | 0.18 | 0.48 |
| vci_grass | 2 | persist | 637 | 26.64 | 183 | 51 | 69 | 0.28 | 0.57 |
| vci_grass | 2 | clim | 637 | 23.99 | 183 | 7 | 21 | 0.04 | 0.75 |
| vci_grass | 3 | timesfm | 637 | 23.73 | 183 | 22 | 39 | 0.12 | 0.64 |
| vci_grass | 3 | persist | 637 | 28.42 | 183 | 51 | 85 | 0.28 | 0.62 |
| vci_grass | 3 | clim | 637 | 23.99 | 183 | 7 | 21 | 0.04 | 0.75 |
