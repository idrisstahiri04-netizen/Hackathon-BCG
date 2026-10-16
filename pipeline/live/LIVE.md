# LIVE extension — status as of 2026-10-16

`pipeline/live/extend_live.py` extends `signals_<ISO3>.parquet`, `dryspell_<ISO3>.parquet` and
`seasonal_fc_<ISO3>.parquet` for **ZWE, KEN, MWI, ZMB** from the frozen history (signals/dryspell to
2024-12, NMME issues to 2024-06) up to the latest complete month. It wraps the existing extractors
(same per-year caches in `pipeline/cache/`), so only 2025-2026 hit Earth Engine / IRI. Baselines
(2001-2020) and all history values are untouched: every month <= 2024-12 (NMME <= 2024-06) was
compared row by row before and after (0 of 1,056,372 signal rows, 324,864 dryspell rows and
636,192 x 3 forecast values differ; copies of the pre-extension files are in `pipeline/live/backup/`).
Machine-readable detail: `pipeline/live/live_status.json`.

Rerun (idempotent, ~8 min total):
```
/home/looooo/bcg/.venv/bin/python pipeline/live/extend_live.py --step all --iso3 ZWE KEN MWI ZMB --end 2026 --last-s 2026-10
```

## 1. Last complete month per source (checked on Earth Engine / IRI, 2026-10-16)

| source | EE / IRI collection | last image | last **complete** month | completeness rule |
|---|---|---|---|---|
| CHIRPS v3 pentad | `UCSB-CHC/CHIRPS/V3/PENTAD` | 2026-09-11 | **2026-08** | 6 pentads in the month (Sep 2026 has 1 of 6; all 2025-01..2026-08 months have 6) |
| MODIS NDVI | `MODIS/061/MOD13Q1` | 2026-09-14 | **2026-08** | the 16-day composite covering month end exists (Sep 2026 has 1 of 2) |
| ERA5-Land monthly | `ECMWF/ERA5_LAND/MONTHLY_AGGR` | 2026-09-01 | **2026-09** | monthly image exists |
| NMME GFDL-SPEAR | IRI DL `.GFDL-SPEAR/.FORECAST` | S = 2026-10 | 2026-10 | see gaps below |
| NMME NASA-GEOSS2S | IRI DL `.NASA-GEOSS2S/.FORECAST` | S = 2026-10 | 2026-10 | complete 2024-07..2026-10 |
| NMME CanSIPS-IC3 | IRI DL `.CanSIPS-IC3/.FORECAST` | S = 2024-06 | 2024-06 | model retired on IRI; **nothing after 2024-06** |

ERA5-Land note: the plan assumed the Earth Engine monthly collection lags 2-3 months. On 2026-10-16 it
was only ~1 month behind (the 2026-09 monthly image is present and has values for all units). This can
vary; `extend_live.py` reads the real last image each run, so rerunning later is safe. `common.LATENCY`
(1 month for every source) is unchanged.

## 2. Resulting "today" issue month

- Issue month t uses month t-1 data (`common.LATENCY`). The last month with **all three** satellite /
  reanalysis sources complete is **2026-08**, so the latest fully informed issue month is
  **2026-09 (Sep 2026)**.
- **live_t = 92** (t = 0 is Jan 2019: (2026-2019)*12 + 8). **n_months = 93** (Jan 2019 .. Sep 2026).
- An Oct 2026 issue (t = 93) would have only ERA5-Land features for Sep 2026 (rain and vegetation
  missing), so it is not issued. The signal tables therefore stop at month 2026-09.

## 3. Which fields are null in the new months

Signals (`signals_<ISO3>.parquet`, months 2025-01 .. 2026-09):
- 2025-01 .. 2026-08: all 13 dynamic signals present (same per-unit NaN pattern as history, e.g.
  units without cropland have no `ndvi_crop`/`vci_crop`).
- **2026-09**: `precip_mm, spi_1m, spi_3m, spi_6m, ndvi_crop, ndvi_grass, ndvi_z_crop, ndvi_z_grass,
  vci_crop, vci_grass` = NaN (partial month masked, never 0). `sm1_z, sm2_z, t2m_z` present.
- Static `crop_frac`, `grass_frac` unchanged (month 2001-01).

Dry-spell (`dryspell_<ISO3>.parquet`, months 2025-01 .. 2026-09):
- Sep 2026 pentads were dropped before the maths (1 of 6 present), so **2026-09 is NaN for all four**
  signals (`dry_spell_max, days_since_rain, onset_anom, season_rain_pct`).
- Jul-Aug 2026: `days_since_rain` present everywhere; the season-timing signals are NaN outside the
  rainy season by design (southern Africa dry season; Kenya units in their long-rains tail still have values).

Seasonal forecast (`seasonal_fc_<ISO3>.parquet`, issue months 2001-01 .. 2026-10):
- `NMME/CanSIPS-IC3`: no rows after 2024-06.
- `NMME/GFDL-SPEAR`: rows exist to 2026-10 but **11 issue months are empty on the IRI server**
  (verified with single-month requests): 2025-06, 2025-08, 2025-10, 2025-11, 2025-12, 2026-02,
  2026-03, 2026-05, 2026-06, 2026-08, 2026-09 -> `anom_z`/`p_below_normal` NaN, `n_members` 0.
  2026-07 and 2026-10 are present.
- `NMME/MME3` after 2024-06 is the mean of GFDL-SPEAR + NASA-GEOSS2S (n_members 40); in the 11 gap
  months it is NASA-GEOSS2S alone (n_members 10). So the forecast attached to the live issue month
  (S = 2026-09) is single-model; S = 2026-10 has both models.

## 4. Rows added

| table | ZWE | KEN | MWI | ZMB |
|---|---|---|---|---|
| signals (months to 2026-09) | 340,886 -> 365,729 (+24,843) | 176,062 -> 188,893 (+12,831) | 104,888 -> 112,532 (+7,644) | 434,536 -> 466,204 (+31,668) |
| dryspell (months to 2026-09) | 104,832 -> 112,476 (+7,644) | 54,144 -> 58,092 (+3,948) | 32,256 -> 34,608 (+2,352) | 133,632 -> 143,376 (+9,744) |
| seasonal_fc (issues to 2026-10) | 205,296 -> 220,584 (+15,288) | 106,032 -> 113,928 (+7,896) | 63,168 -> 67,872 (+4,704) | 261,696 -> 281,184 (+19,488) |

21 new months x units x 13 dynamic signals (signals); 21 x units x 4 (dryspell); 28 new issue months x
units x 2 windows x 3 products (seasonal_fc).

## 5. Note for the model helper

- Data pushed to the Kaggle dataset `omarserghini/drought-signals` with `scripts/kaggle/push_data.sh`
  (see the push note at the end of this file). The other 10 countries' files are unchanged.
- Please export with `meta.n_months = 93` and `meta.live_t = 92` (CONTRACT section 4). Months
  2025-01 .. 2026-09 are hold-out/live: use the final model, never a CV fold.
- Series rows for t = 92 (Sep 2026) get their features from month 2026-08 after the latency shift
  (all sources present). If you also export t = 93 (Oct 2026), its rain/vegetation/dry-spell features
  are NaN by construction; prefer stopping at live_t.
- Forecast view for live_t: NMME S = 2026-09 is NASA-GEOSS2S only (GFDL-SPEAR empty on IRI), S = 2026-10
  has both models; CanSIPS-IC3 is absent from every live month.
- No model file (`train.py`, `alert_engine.py`, `export_risk.py`) was touched; `extract_signals.py`,
  `dryspell/extract_dryspell.py`, `seasonal_forecast.py` are unchanged too (the wrapper overrides their
  end year / `LAST_S` at run time).

## 6. Kaggle push

`scripts/kaggle/push_data.sh` run 2026-10-16 19:38 UTC: 86 files (77 MB) staged, new version of
`omarserghini/drought-signals` created, tree hash `8cd4054b46dd061c`, status `ready`.

## 7. Kenya live soil moisture (sm1_z down to about -6 SD): checked 2026-10-16, real, kept

Pitch review flagged KEN `sm1_z` near -6 in the live months. Checked against the raw cache
(`pipeline/cache/KEN/era5_<year>.json`, ERA5-Land `volumetric_soil_water_layer_1`, m3/m3) and Earth Engine:
- **No unit or version change.** The 2025-2026 raw values are in the same m3/m3 range as 2001-2024 (e.g. Busia
  0.25-0.39, Turkana 0.02-0.12). The 2026-05..09 `MONTHLY_AGGR` images are full months (time_end = month end,
  normal asset size). The z-scores use the same 2001-2020 per-unit, per-calendar-month baseline as history
  (Busia Sep 2026: (0.256 - 0.353) / 0.021 = -4.6, as stored).
- **The large |z| comes from a tiny baseline SD.** Western Kenya topsoil sits near field capacity in Jun-Sep
  (Kakamega Aug SD 0.018 m3/m3), so a real drop to 0.29 gives z of about -6. History has the same effect (2021: -7.4).
- **Other sources agree it is dry.** Busia / Kakamega / Bungoma Jun-Aug 2026: CHIRPS SPI-3 -1.6 to -2.8,
  ERA5 t2m +3.7 to +5.4 SD. So the values are not masked (masking real data would be fabricating "normal").
- Effect on alerts: none beyond the sign. The soil family is a threshold (`sm1_z <= -1`, rainy season +1 month
  only); magnitude does not change levels. UI text should show such values as "far below normal" rather than
  as a precise SD.
