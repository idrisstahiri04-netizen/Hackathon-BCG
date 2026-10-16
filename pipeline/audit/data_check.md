# Data check: pipeline/data/signals_ZWE.parquet

Generated 2026-10-16 18:54 UTC by `pipeline/audit/verify_signals.py` (independent code path, not importing extract_signals.py).

Parquet mtime 2026-10-16 15:57 UTC, 3039915 bytes, 340886 rows.

**62 checks not failed, 0 FAIL.**

Independent EE method: per-unit `reduceRegion` mean; CHIRPS v3 pentads summed per calendar month (5 km); MOD13Q1 NDVI x0.0001 masked SummaryQA in {0,1}, monthly mean of 16-day composites with start date in the month, then masked to WorldCover v200 class 40 (crop) / 20+30 (shrub+grass), 250 m; ERA5-Land monthly volumetric_soil_water_layer_1 (11 km). Climatology = 2001-2020 same calendar month.

Sample units: Mbire, Binga, Hwange, Beitbridge, Mwenezi.

| check | result | detail |
|---|---|---|
| anom sign 2023-11 (El Nino onset; sign not asserted): precip | INFO | 5 units below / 0 above 2001-20 mean; median anom -54.44 |
| anom sign 2023-11 (El Nino onset; sign not asserted): ndvi_crop | INFO | 3 units below / 2 above 2001-20 mean; median anom -0.0008538 |
| anom sign 2023-11 (El Nino onset; sign not asserted): ndvi_grass | INFO | 2 units below / 3 above 2001-20 mean; median anom +0.02691 |
| anom sign 2023-11 (El Nino onset; sign not asserted): sm1 | INFO | 5 units below / 0 above 2001-20 mean; median anom -0.03477 |
| anom sign 2024-01 El Nino drought: precip | PASS | 4 units below / 1 above 2001-20 mean; median anom -36.42 |
| anom sign 2024-01 El Nino drought: ndvi_crop | WARN | 1 units below / 4 above 2001-20 mean; median anom +0.01858 |
| anom sign 2024-01 El Nino drought: ndvi_grass | WARN | 0 units below / 5 above 2001-20 mean; median anom +0.0282 |
| anom sign 2024-01 El Nino drought: sm1 | PASS | 4 units below / 1 above 2001-20 mean; median anom -0.003926 |
| anom sign 2024-02 El Nino drought (driest Feb on record): precip | PASS | 5 units below / 0 above 2001-20 mean; median anom -132.6 |
| anom sign 2024-02 El Nino drought (driest Feb on record): ndvi_crop | PASS | 3 units below / 2 above 2001-20 mean; median anom -0.06938 |
| anom sign 2024-02 El Nino drought (driest Feb on record): ndvi_grass | PASS | 3 units below / 2 above 2001-20 mean; median anom -0.0416 |
| anom sign 2024-02 El Nino drought (driest Feb on record): sm1 | PASS | 5 units below / 0 above 2001-20 mean; median anom -0.1584 |
| anom sign 2015-01 drought: precip | PASS | 3 units below / 2 above 2001-20 mean; median anom -32.86 |
| anom sign 2015-01 drought: ndvi_crop | WARN | 1 units below / 4 above 2001-20 mean; median anom +0.04111 |
| anom sign 2015-01 drought: ndvi_grass | WARN | 0 units below / 5 above 2001-20 mean; median anom +0.0484 |
| anom sign 2015-01 drought: sm1 | PASS | 3 units below / 2 above 2001-20 mean; median anom -0.00225 |
| anom sign 2016-01 2015/16 El Nino drought peak: precip | PASS | 5 units below / 0 above 2001-20 mean; median anom -54.12 |
| anom sign 2016-01 2015/16 El Nino drought peak: ndvi_crop | PASS | 5 units below / 0 above 2001-20 mean; median anom -0.08358 |
| anom sign 2016-01 2015/16 El Nino drought peak: ndvi_grass | PASS | 5 units below / 0 above 2001-20 mean; median anom -0.08713 |
| anom sign 2016-01 2015/16 El Nino drought peak: sm1 | PASS | 5 units below / 0 above 2001-20 mean; median anom -0.0553 |
| anom sign 2017-01 wet season: precip | PASS | 0 units below / 5 above 2001-20 mean; median anom +108.7 |
| anom sign 2017-01 wet season: ndvi_crop | PASS | 0 units below / 5 above 2001-20 mean; median anom +0.08109 |
| anom sign 2017-01 wet season: ndvi_grass | PASS | 0 units below / 5 above 2001-20 mean; median anom +0.07768 |
| anom sign 2017-01 wet season: sm1 | PASS | 0 units below / 5 above 2001-20 mean; median anom +0.08891 |
| columns per contract | PASS | unit_id, unit_name, iso3, month, signal_type, value |
| value match pq_precip_mm vs independent EE (tol 5%) | PASS | max rel diff 2.52%, median 0.24% over 30 unit-months |
| value match pq_ndvi_crop vs independent EE (tol 5%) | PASS | max rel diff 2.52%, median 1.36% over 30 unit-months |
| value match pq_ndvi_grass vs independent EE (tol 5%) | PASS | max rel diff 0.28%, median 0.13% over 30 unit-months |
| sign pq_spi_1m vs EE anomaly | PASS | 29/30 same sign; disagree: Hwange 2024-01 anom=-12.9 pq_spi_1m=+0.00 |
| sign pq_sm1_z vs EE anomaly | PASS | 30/30 same sign |
| vci_crop within 0-100 | PASS | n=25333 min=0 max=100, out of range=0 |
| vci_grass within 0-100 | PASS | n=26201 min=0 max=100, out of range=0 |
| spi_1m range | INFO | min -3.00 max 3.00; clipped at -3: 52, at +3: 268 (extractor clips to [-3,3]; extreme events like Feb 2024 saturate) |
| spi_3m range | INFO | min -3.00 max 3.00; clipped at -3: 55, at +3: 146 (extractor clips to [-3,3]; extreme events like Feb 2024 saturate) |
| spi_6m range | INFO | min -3.00 max 3.00; clipped at -3: 40, at +3: 43 (extractor clips to [-3,3]; extreme events like Feb 2024 saturate) |
| no duplicate (unit_id, month, signal_type) | PASS | 0 duplicates |
| 91 units | PASS | 91 unit_ids, 91 names |
| iso3 = ZWE only | PASS | ['ZWE'] |
| all contract signal types present | PASS | missing=[] extra=[] |
| coverage precip_mm | PASS | rows 26208/26208, non-null 26208 (100.0%); months outside range 0; first 2001-01-01 last 2024-12-01 |
| coverage spi_1m | PASS | rows 26208/26208, non-null 26208 (100.0%); months outside range 0; first 2001-01-01 last 2024-12-01 |
| coverage spi_3m | PASS | rows 26208/26208, non-null 26208 (100.0%); months outside range 0; first 2001-01-01 last 2024-12-01 |
| coverage spi_6m | PASS | rows 26208/26208, non-null 26208 (100.0%); months outside range 0; first 2001-01-01 last 2024-12-01 |
| coverage ndvi_crop | PASS | rows 26208/26208, non-null 25333 (96.7%); months outside range 0; first 2001-01-01 last 2024-12-01; units all-NaN: ['Gwanda Urban', 'Kariba Urban', 'Victoria Falls']; units with partial gaps: ['Mvurwi', 'Zvishavane Urban', 'Hwange Urban', 'Bindura Urban'] |
| coverage ndvi_grass | PASS | rows 26208/26208, non-null 26201 (100.0%); months outside range 0; first 2001-01-01 last 2024-12-01; units all-NaN: []; units with partial gaps: ['Mvurwi'] |
| coverage ndvi_z_crop | PASS | rows 26208/26208, non-null 25333 (96.7%); months outside range 0; first 2001-01-01 last 2024-12-01; units all-NaN: ['Gwanda Urban', 'Kariba Urban', 'Victoria Falls']; units with partial gaps: ['Mvurwi', 'Zvishavane Urban', 'Hwange Urban', 'Bindura Urban'] |
| coverage ndvi_z_grass | PASS | rows 26208/26208, non-null 26201 (100.0%); months outside range 0; first 2001-01-01 last 2024-12-01; units all-NaN: []; units with partial gaps: ['Mvurwi'] |
| coverage vci_crop | PASS | rows 26208/26208, non-null 25333 (96.7%); months outside range 0; first 2001-01-01 last 2024-12-01; units all-NaN: ['Gwanda Urban', 'Kariba Urban', 'Victoria Falls']; units with partial gaps: ['Mvurwi', 'Zvishavane Urban', 'Hwange Urban', 'Bindura Urban'] |
| coverage vci_grass | PASS | rows 26208/26208, non-null 26201 (100.0%); months outside range 0; first 2001-01-01 last 2024-12-01; units all-NaN: []; units with partial gaps: ['Mvurwi'] |
| coverage sm1_z | PASS | rows 26208/26208, non-null 26208 (100.0%); months outside range 0; first 2001-01-01 last 2024-12-01 |
| coverage sm2_z | PASS | rows 26208/26208, non-null 26208 (100.0%); months outside range 0; first 2001-01-01 last 2024-12-01 |
| coverage t2m_z | PASS | rows 26208/26208, non-null 26208 (100.0%); months outside range 0; first 2001-01-01 last 2024-12-01 |
| static crop_frac: one row per unit at 2001-01-01, in [0,1] | PASS | rows 91, months ['2001-01-01'], range 0.000538-0.454 |
| static grass_frac: one row per unit at 2001-01-01, in [0,1] | PASS | rows 91, months ['2001-01-01'], range 0.151-0.813 |
| no zero-for-missing | PASS | precip_mm zeros=9, re-checked in EE: 9 are real 0 mm (all pentads present, CHIRPS sum 0 over unit) [Zvishavane Urban 2002-02, Zvishavane Urban 2005-10, Zvishavane Urban 2011-02, Gwanda Urban 2011-02, Beitbridge Urban 2011-02, Beitbridge Urban 2015-01, Hwange Urban 2019-03, Zvishavane Urban 2022-02, Gwanda Urban 2022-02]; vci_crop zeros=1273 (expected: VCI=0 at the baseline-minimum year; max 1 zero per unit x calendar month in 2001-20, 217 after 2020 = clipped below baseline min); vci_grass zeros=1206 (expected: VCI=0 at the baseline-minimum year; max 1 zero per unit x calendar month in 2001-20, 114 after 2020 = clipped below baseline min) / NaN kept: ndvi_crop NaN=875; ndvi_grass NaN=7; ndvi_z_crop NaN=875; ndvi_z_grass NaN=7; vci_crop NaN=875; vci_grass NaN=7 |
| precip_mm physical range [0,1500] | PASS | min 0 max 620.5 |
| ndvi_crop physical range [-0.2,1] | PASS | min 0.1848 max 0.8406 |
| ndvi_grass physical range [-0.2,1] | PASS | min 0.1917 max 0.7892 |
| spi_1m sign vs precip anomaly (all units, wet season, |anom|>10% of median) | PASS | agreement 99.4% over 9163 unit-months; median rank corr per unit/cal-month 1.000 |
| national spi_1m 2024-02 expected dry | PASS | mean -2.11; 100% of units with expected sign |
| national spi_1m 2016-01 expected dry | PASS | mean -0.78; 100% of units with expected sign |
| national spi_1m 2017-01 expected wet | PASS | mean +1.47; 100% of units with expected sign |

## Independent EE sample vs parquet

| unit | month | precip EE | precip PQ | precip clim | ndvi_crop EE | PQ | clim | ndvi_grass EE | PQ | clim | sm1 EE | sm1 clim | spi_1m PQ | sm1_z PQ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Beitbridge | 2015-01 | 2.376 | 2.398 | 79.23 | 0.464 | 0.468 | 0.39 | 0.497 | 0.497 | 0.429 | 0.243 | 0.249 | -2.1 | -0.089 |
| Binga | 2015-01 | 196.9 | 196.8 | 172.6 | 0.539 | 0.547 | 0.552 | 0.646 | 0.645 | 0.626 | 0.347 | 0.337 | 0.47 | 0.2 |
| Hwange | 2015-01 | 129.7 | 129.9 | 162.6 | 0.556 | 0.562 | 0.515 | 0.653 | 0.654 | 0.614 | 0.298 | 0.301 | -0.28 | -0.042 |
| Mbire | 2015-01 | 313.3 | 313.8 | 197.4 | 0.651 | 0.653 | 0.579 | 0.699 | 0.7 | 0.624 | 0.396 | 0.35 | 1.2 | 0.7 |
| Mwenezi | 2015-01 | 25.45 | 25.44 | 108.4 | 0.5 | 0.507 | 0.487 | 0.589 | 0.589 | 0.54 | 0.253 | 0.255 | -1.1 | -0.033 |
| Beitbridge | 2016-01 | 27.63 | 27.63 | 79.23 | 0.306 | 0.31 | 0.39 | 0.373 | 0.373 | 0.429 | 0.203 | 0.249 | -0.62 | -0.71 |
| Binga | 2016-01 | 95.7 | 95.73 | 172.6 | 0.38 | 0.389 | 0.552 | 0.467 | 0.467 | 0.626 | 0.266 | 0.337 | -1.2 | -1.5 |
| Hwange | 2016-01 | 115.5 | 115.7 | 162.6 | 0.437 | 0.445 | 0.515 | 0.527 | 0.528 | 0.614 | 0.245 | 0.301 | -0.5 | -0.9 |
| Mbire | 2016-01 | 143.2 | 143.6 | 197.4 | 0.546 | 0.551 | 0.579 | 0.576 | 0.578 | 0.624 | 0.241 | 0.35 | -0.5 | -1.7 |
| Mwenezi | 2016-01 | 36.43 | 36.16 | 108.4 | 0.31 | 0.316 | 0.487 | 0.416 | 0.418 | 0.54 | 0.202 | 0.255 | -0.78 | -0.74 |
| Beitbridge | 2017-01 | 187.9 | 187.8 | 79.23 | 0.471 | 0.471 | 0.39 | 0.507 | 0.507 | 0.429 | 0.369 | 0.249 | 1.4 | 1.8 |
| Binga | 2017-01 | 252.6 | 252.2 | 172.6 | 0.563 | 0.571 | 0.552 | 0.669 | 0.668 | 0.626 | 0.394 | 0.337 | 1.2 | 1.2 |
| Hwange | 2017-01 | 232.1 | 232.1 | 162.6 | 0.585 | 0.587 | 0.515 | 0.682 | 0.683 | 0.614 | 0.39 | 0.301 | 0.94 | 1.4 |
| Mbire | 2017-01 | 328 | 329.5 | 197.4 | 0.695 | 0.697 | 0.579 | 0.713 | 0.713 | 0.624 | 0.413 | 0.35 | 1.3 | 0.99 |
| Mwenezi | 2017-01 | 246.3 | 245.4 | 108.4 | 0.581 | 0.585 | 0.487 | 0.663 | 0.663 | 0.54 | 0.391 | 0.255 | 1.4 | 1.9 |
| Beitbridge | 2023-11 | 4.064 | 3.967 | 58.5 | 0.306 | 0.31 | 0.278 | 0.37 | 0.371 | 0.305 | 0.189 | 0.205 | -3 | -0.47 |
| Binga | 2023-11 | 13.83 | 13.71 | 62.55 | 0.284 | 0.291 | 0.305 | 0.353 | 0.353 | 0.358 | 0.145 | 0.205 | -2.4 | -2.1 |
| Hwange | 2023-11 | 15 | 15.08 | 69.75 | 0.284 | 0.289 | 0.304 | 0.327 | 0.328 | 0.365 | 0.138 | 0.203 | -2.9 | -2.1 |
| Mbire | 2023-11 | 13.37 | 13.52 | 61.37 | 0.285 | 0.289 | 0.283 | 0.353 | 0.354 | 0.326 | 0.128 | 0.163 | -1.3 | -1.5 |
| Mwenezi | 2023-11 | 3.622 | 3.531 | 65.23 | 0.328 | 0.336 | 0.329 | 0.442 | 0.443 | 0.373 | 0.175 | 0.2 | -3 | -0.72 |
| Beitbridge | 2024-01 | 30.4 | 30.47 | 79.23 | 0.56 | 0.562 | 0.39 | 0.593 | 0.593 | 0.429 | 0.248 | 0.249 | -0.55 | -0.02 |
| Binga | 2024-01 | 178 | 178.1 | 172.6 | 0.515 | 0.523 | 0.552 | 0.644 | 0.643 | 0.626 | 0.318 | 0.337 | 0.21 | -0.4 |
| Hwange | 2024-01 | 149.7 | 150.2 | 162.6 | 0.521 | 0.532 | 0.515 | 0.617 | 0.618 | 0.614 | 0.291 | 0.301 | 0.0022 | -0.14 |
| Mbire | 2024-01 | 160.9 | 162.2 | 197.4 | 0.598 | 0.601 | 0.579 | 0.653 | 0.654 | 0.624 | 0.355 | 0.35 | -0.26 | 0.048 |
| Mwenezi | 2024-01 | 42.71 | 42.47 | 108.4 | 0.526 | 0.534 | 0.487 | 0.649 | 0.651 | 0.54 | 0.251 | 0.255 | -0.65 | -0.054 |
| Beitbridge | 2024-02 | 22.44 | 22.44 | 63.09 | 0.508 | 0.512 | 0.416 | 0.544 | 0.544 | 0.457 | 0.157 | 0.236 | -0.65 | -1.3 |
| Binga | 2024-02 | 12.28 | 12.26 | 166.3 | 0.483 | 0.492 | 0.596 | 0.6 | 0.599 | 0.658 | 0.159 | 0.344 | -3 | -5.4 |
| Hwange | 2024-02 | 4.277 | 4.249 | 136.8 | 0.493 | 0.503 | 0.562 | 0.587 | 0.588 | 0.649 | 0.142 | 0.3 | -3 | -2.8 |
| Mbire | 2024-02 | 24.33 | 24.31 | 175.1 | 0.568 | 0.571 | 0.666 | 0.646 | 0.648 | 0.688 | 0.153 | 0.356 | -2.2 | -4.1 |
| Mwenezi | 2024-02 | 38.45 | 37.82 | 95.57 | 0.536 | 0.544 | 0.533 | 0.645 | 0.647 | 0.58 | 0.155 | 0.241 | -0.56 | -1.2 |
