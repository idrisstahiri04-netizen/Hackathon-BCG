# Signal extraction — expansion countries

Extra countries for pooled training (existing: ZWE, KEN, MWI, ZMB).
Run with `python pipeline/extract_signals.py --iso3 <ISO3> --adm 2 --start 2001 --end 2024`
(per-year cache in `pipeline/cache/<ISO3>/`). ADM2 for all: every country has <= 200
geoBoundaries ADM2 units (threshold for falling back to ADM1 was > 200).

Checks per parquet: units == geoBoundaries count and == units_<ISO3>.geojson ids; no duplicate
(unit_id, month, signal_type); coverage 2001-01..2024-12 (288 months) for all time series;
missing stays NaN (never 0); rows == units * 288 * 13 signals + units * 2 statics.

geoBoundaries unit counts (ADM1 / ADM2), queried from Earth Engine `WM/geoLab/geoBoundaries/600` 2026-10-16:
MOZ 10/156, TZA 30/170, ETH 11/74, SOM 18/118, NAM 13/103, BWA 10/25, ZAF 9/52, MDG 22/119, AGO 18/157, UGA 4/151.

| iso3 | adm | units | rows | NaN % | runtime | status | issues |
|---|---|---|---|---|---|---|---|
| MOZ | 2 | 156 | 584,376 | 0.1 | 120s | ready | all checks pass, attempt 1; NaN only in ndvi_crop/ndvi_z_crop/vci_crop (0.6%, units without WorldCover cropland) |
| TZA | 2 | 170 | 636,820 | 0.5 | 142s | ready | all checks pass, attempt 1; NaN in ndvi_crop family 1.8%, ndvi_grass family 0.2% |
| ETH | 2 | 74 | 277,204 | 0.9 | 91s | ready | all checks pass, attempt 1; ADM2 = zones (74); NaN in ndvi_crop family 4.1% |
| SOM | 2 | 118 | 442,028 | 13.8 | 86s | ready (sparse crop NDVI) | all structural checks pass, attempt 1. ndvi_crop family 47.5% NaN: 56 of 118 units have no WorldCover cropland at all (23 with crop_frac = 0, 84 with < 0.5%). ERA5 (sm1_z/sm2_z/t2m_z) and ndvi_grass ~6% NaN: 7 Mogadishu city districts (Abdul Aziz, Bondere, Hamar Jabjab, Hamar Weyn, Shangani, Shibis, Waberi) are smaller than one 11 km ERA5-Land pixel -> null. spi_1m 0.1% NaN (Jan, usually-dry month, SPI undefined by design). All genuine missingness, not zero. |
| NAM | 2 | 103 | 385,838 | 6.7 | 94s | ready | all checks pass, attempt 1. ndvi_crop family 27.2% NaN (13 units crop_frac = 0, arid). ERA5 1.0% NaN = Hakahana (Windhoek suburb, sub-pixel); ndvi_grass 1.0% = Opuwo unit. |
| BWA | 2 | 25 | 93,650 | 0.1 | 64s | ready | all checks pass, attempt 1 |
| ZAF | 2 | 52 | 194,792 | 0.0 | 86s | ready | all checks pass, attempt 1; ADM2 = district + metropolitan municipalities |
| MDG | 2 | 119 | 445,774 | 1.6 | 83s | ready | all checks pass, attempt 1; NaN in ndvi_crop family 4.2%, ndvi_grass family 2.5% |
| AGO | 2 | 157 | 588,122 | 3.9 | 102s | ready | all checks pass, attempt 1. ndvi_crop family 16.9% NaN: 24 municipalities (mostly forested north: Ambriz, Ambuila, Banga, Belize, Bembe, Buco Zau ...) have no QA-passing cropland NDVI, 79 units have crop_frac < 0.5%. ndvi_grass 0.1%. |
| UGA | 2 | 151 | 565,646 | 0.7 | 63s | ready | all checks pass, attempt 1; ADM1 is only 4 regions so ADM2 (districts) used. ndvi_crop family 2.7%, sm1_z/sm2_z 0.7% (sub-pixel units). |

## Summary (2026-10-16)
- 10 / 10 countries ready, all ADM2, all on first attempt, 0 Earth Engine retry warnings in any log.
- New rows: 4,214,250 across 10 parquets (pipeline/data/signals_<ISO3>.parquet); units_<ISO3>.geojson written for each
  (feature count == parquet unit count == geoBoundaries count; all features have geometry).
- Wall time ~6 min with 3 countries in parallel (each run 63-142 s).
- All NaN is genuine missingness: units with no WorldCover cropland (ndvi_crop family), urban units smaller than an
  ERA5-Land pixel (sm/t2m), and SPI undefined in nearly-always-dry calendar months. Exact-zero share of time-series
  values is 0.6-1.0% in every country (dry-month precip_mm, VCI floor), same as ZWE (0.7%).
- Caveat for pooled training: SOM/NAM/AGO have many units with almost no cropland, so the vegetation family there
  rests on ndvi_grass/vci_grass; treat ndvi_crop coverage as a per-unit feature, not as a data error.
- Not committed. Nothing in train.py or other model files touched. Raw EE cache in pipeline/cache/<ISO3>/ (gitignored).
