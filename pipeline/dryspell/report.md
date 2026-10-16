# Dry-spell / season-timing features — report

Branch `zimbabwe-real-data`, nothing committed. Code in `pipeline/dryspell/`; no main model file edited.
Additive edits outside this folder: `scripts/kaggle/push_data.sh` (stages `dryspell_*.parquet`) and
`scripts/kaggle/push_code.sh` (bundles `pipeline/dryspell/*.py|*.sh`).
Kaggle run: kernel `omarserghini/drought-dry`, 2026-10-16 18:49-19:04 UTC, 870 s, exit 0
(local copy of outputs: `pipeline/dryspell/kaggle_results/`; full download `pipeline/out/kaggle/20261016T184911Z/`).

## 1. Data: `pipeline/data/dryspell_<ISO3>.parquet` (14 countries)

Source `UCSB-CHC/CHIRPS/V3/PENTAD` (the product `precip_mm` is summed from; pentad monthly sums reproduce the
`signals` `precip_mm` to 0.1 mm). Earth Engine stacks the 72 pentads of a year as bands (`toBands`) and one
`reduceRegions(mean, scale 5566 m)` per (country, year) returns all units; raw results cached in
`pipeline/cache/dryspell/<ISO3>/pentad_<year>.json` (gitignored). Years 2000-2024 fetched (2000 only so the
2000/01 season is complete). Whole run for 14 countries ~2 min wall; the rest is pandas (`extract_dryspell.py`).

Contract long format (`unit_id, unit_name, iso3, month, signal_type, value`), 2001-01..2024-12, 288 months x 4
signals per unit, unit count == `units_<ISO3>.geojson`, no duplicates, NaN = missing (never 0). Unit ids =
geoBoundaries `shapeID` (ADM level picked by matching the geojson ids: KEN ADM1, others ADM2).

Seasons = the ones the model already uses (`common.detect_seasons` per unit; bimodal units get two). A month
belongs to the season whose search start is the most recent. The value for month m is the state at the end of the
last pentad of m, so it is "month m data" and takes the normal CHIRPS latency (issue month r uses month r-1).

| signal_type | definition | defined when |
|---|---|---|
| `dry_spell_max` | longest run of consecutive pentads < 5 mm since the season's onset, up to end of m (frozen after the last rainy month) | after onset .. last rainy month + 1 |
| `days_since_rain` | pentads since the last pentad with >= 10 mm (0 = last pentad of m was wet), cap 36 | always |
| `onset_anom` | onset pentad minus the 2001-2020 median onset of that unit+season, in pentads (+ = late). Onset = first pentad p from the search start (first pentad of the month before the first rainy month) with rain(p..p+2) >= 25 mm. Before onset: censored = pentads elapsed - median (smallest anomaly still possible) | search start .. last rainy month + 1 |
| `season_rain_pct` | rain from the first pentad of the first rainy month to end of m (clipped at season end) as % of the 2001-2020 mean of the same partial sum (100 = normal) | first rainy month .. last rainy month + 1 |

Non-NaN share per country: `days_since_rain` 99.9-100 %, `onset_anom` 53-78 %, `dry_spell_max` /
`season_rain_pct` 44-64 % (rest = dry season, missing by design). On CV rows (leads 1-3) of the 4 core
countries: no_grass 93-100 % present; crop_failure only 30 % for `dry_spell_max`/`season_rain_pct` and 63 % for
`onset_anom` (the crop window opens one month after the core starts, so at leads 2-3 the season has not begun).

### What the data say for ZWE 2023/24 (medians over 91 districts; data only, no model)

| month | dry_spell_max | days_since_rain | onset_anom | season_rain_pct |
|---|---|---|---|---|
| 2023-11 | 4 | 4 | -3.5 | 22.7 |
| 2023-12 | 3 | 0 | -3.5 | 77.7 |
| 2024-01 | 3 | 2 | -3.5 | 69.2 |
| 2024-02 | 7 | 8 | -3.5 | 56.3 |
| 2024-03 | 7 | 3 | -3.5 | 52.6 |

Same months 2022/23: dry_spell_max 1-5, days_since_rain 0-6, season_rain_pct 90-109. 2015/16 El Nino:
season_rain_pct 53-72, onset_anom +3. March `season_rain_pct` (unit mean) 2001-2023 ranges 67-139; 2024 = 54, the lowest.

Caveat: the plain 25 mm / 3 pentads onset rule accepts the October 2023 false start (onset_anom -3.5 while
November rain was 23 % of normal); the false start therefore shows in `dry_spell_max` and `season_rain_pct`, not in
`onset_anom`. A stricter rule ("no dry run >= 7 pentads in the 30 days after onset") would move it; not done.

## 2. Experiment (`pipeline/dryspell/exp_dryspell.py`, Kaggle)

Same harness as the earlier experiments (`pipeline/experiments/harness.py` = train.py's leave-one-agyear-out CV
2001-2022, logreg + LightGBM + ensemble, cross-fitted isotonic calibration, metrics on leads 1-3, v1.1 labels 2-of-3
months VCI < 35, latency 1 month). Hold-out (agyear >= 2023, KEN 2020-22) never enters `cv()`; it is scored exactly
once at the end for the ZWE replay with models fitted on CV rows, nothing is selected on it. Features joined at
(unit_id, r - 1). Four CV runs: {core 4, all 14} x {base 58 columns, base + 4 dry}. Pooled-14 training rows for the
10 extra countries from `experiments/expand.py` (agyear < 2023 only). Full tables: `kaggle_results/summary.md`.

### Delta (dry - base), ensemble, CV, leads 1-3 (ROC-AUC / PR-AUC / Brier)

| rows | event | base | dry | delta |
|---|---|---|---|---|
| core 4 (n 20184) | crop_failure | 0.589 / 0.272 / 0.1610 | 0.598 / 0.282 / 0.1605 | +0.009 / +0.010 / -0.0005 |
| core 4 | no_grass | 0.603 / 0.403 / 0.2030 | 0.616 / 0.412 / 0.2017 | +0.013 / +0.009 / -0.0013 |
| all 14 (n 110742) | crop_failure | 0.660 / 0.393 / 0.1730 | 0.665 / 0.400 / 0.1721 | +0.005 / +0.007 / -0.0009 |
| all 14 | no_grass | 0.665 / 0.512 / 0.2010 | 0.671 / 0.515 / 0.2001 | +0.006 / +0.003 / -0.0009 |
| trained 14, eval core 4 | crop_failure | 0.596 / 0.290 / 0.1610 | 0.601 / 0.290 / 0.1612 | +0.005 / +0.000 / +0.0002 |
| trained 14, eval core 4 | no_grass | 0.617 / 0.418 / 0.1970 | 0.627 / 0.428 / 0.1958 | +0.010 / +0.010 / -0.0012 |

By lead (core 4, ensemble, PR-AUC delta): crop_failure L1 +0.002, L2 +0.009, L3 +0.017; no_grass L1 +0.006,
L2 +0.013, L3 +0.016. All-14: crop_failure +0.005 / +0.008 / +0.007; no_grass +0.009 / +0.002 / +0.004.
Every ensemble delta in PR-AUC and ROC is >= 0 at every lead in both pools; Brier improves or is flat.
The tree member gains most: LightGBM alone, core 4, no_grass 0.400 -> 0.428 PR-AUC (+0.028), ROC +0.027, Brier -0.0044.

Per country (core-4 model, ensemble, leads 1-3, PR-AUC base -> dry): ZWE crop 0.159 -> 0.167, no_grass 0.308 -> 0.332;
KEN 0.297 -> 0.308, 0.585 -> 0.588; ZMB 0.336 -> 0.349, 0.284 -> 0.285; MWI 0.181 -> 0.188, 0.177 -> 0.175 (MWI no_grass
lead 1 is the one clear loss: 0.213 -> 0.194).

Feature importance (final core-4 dry models): no_grass LightGBM gain share `days_since_rain` 15.2 %,
`season_rain_pct` 7.0 %, `onset_anom` 0.5 %, `dry_spell_max` 0 %; crop_failure `season_rain_pct` 5.4 % (logreg
standardised coef -0.28, the largest of the four), `onset_anom` 2.0 %, `days_since_rain` 1.8 %.

### ZWE 2023/24 replay (hold-out, scored once; ensemble, calibrated p; 91 districts)

| event | lead | issue r (data of r-1) | mean p base -> dry | share p >= 0.5 base -> dry | features seen (medians) |
|---|---|---|---|---|---|
| no_grass | 0 | 2024-04 (Mar) | 0.399 -> 0.478 | 0.16 -> 0.56 | dry 7, since 3, rain% 53 |
| no_grass | 1 | 2024-03 (Feb) | 0.346 -> 0.389 | 0.01 -> 0.25 | dry 7, since 8, rain% 56 |
| no_grass | 2 | 2024-02 (Jan) | 0.265 -> 0.307 | 0.00 -> 0.00 | dry 3, since 2, rain% 69 |
| no_grass | 3 | 2024-01 (Dec) | 0.240 -> 0.233 | 0.00 -> 0.00 | dry 3, since 0, rain% 78 |
| crop_failure | 1 | 2023-12 (Nov) | 0.165 -> 0.184 | 0.00 -> 0.00 | dry 4, since 4, rain% 23 |
| crop_failure | 2-3 | 2023-11 / 2023-10 | 0.155 -> 0.154, 0.204 -> 0.200 | 0 -> 0 | pre-season (NaN) |

Hold-out metrics ZWE 2023/24, leads 1-3 (273 rows each): no_grass ROC 0.549 -> 0.566, PR 0.771 -> 0.773,
Brier 0.3942 -> 0.3696; crop_failure ROC 0.449 -> 0.406, PR 0.372 -> 0.343, Brier 0.3022 -> 0.3044 (worse).
Label rates 0.73 / 0.41 (most districts in drought; AUC here only ranks districts).

Answer to "is the Feb 2024 dry spell flagged earlier?": not earlier in calendar time, but much more strongly in the
same month. With the 1-month latency the February dry spell (median 8 pentads since >= 10 mm, 35-day dry run, season
rain 56 % of normal) is first visible at the end-of-March issue; there the share of districts with p(no_grass) >= 0.5
rises from 1 % to 25 % (mean p 0.346 -> 0.389), and at the April nowcast from 16 % to 56 %. For crop_failure the window
(Jan-Mar) has already opened when the dry spell happens, so at leads >= 1 the model only sees pre-season months and the
features cannot help; the November rain deficit (23 % of normal at the December issue) moved p only 0.165 -> 0.184.

## 3. Recommendation

Adopt the four signals: a modest but consistent gain (ensemble +0.009/+0.010 PR-AUC, +0.009/+0.013 ROC on core 4;
no negative pooled delta at any lead), largest for no_grass in the LightGBM member and in ZWE/KEN; MWI no_grass is the
only per-country loss. The replay effect is real for the herder (no_grass) audience. Do not expect the features to move
crop_failure at leads 2-3 (season not started). Deltas are within what a single extra fold could move; re-check once
after adoption with `train.py` (same folds) before the model freeze.

## 4. Code to adopt

Extraction (re-runnable, cached), add to `pipeline/run_all.sh` after `extract_signals.py`:

```bash
python pipeline/dryspell/extract_dryspell.py            # all 14 countries -> pipeline/data/dryspell_<ISO3>.parquet
```

`pipeline/common.py` — register the four names as CHIRPS-sourced dynamic signals so `apply_latency` shifts them by 1:

```python
DRY_SIGNALS = ["dry_spell_max", "days_since_rain", "onset_anom", "season_rain_pct"]
DYNAMIC = ["precip_mm", "spi_1m", "spi_3m", "spi_6m", "ndvi_crop", "ndvi_grass",
           "ndvi_z_crop", "ndvi_z_grass", "vci_crop", "vci_grass", "sm1_z", "sm2_z", "t2m_z"] + DRY_SIGNALS
SOURCE.update({s: "chirps" for s in DRY_SIGNALS})


def load_signals(iso3: str, data_dir: Path = DATA_DIR) -> pd.DataFrame:
    df = pd.read_parquet(Path(data_dir) / f"signals_{iso3}.parquet")
    extra = Path(data_dir) / f"dryspell_{iso3}.parquet"
    if extra.exists():                      # absent file = missing features (NaN), not an error
        df = pd.concat([df, pd.read_parquet(extra)], ignore_index=True)
    df["month"] = pd.to_datetime(df["month"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df
```

`pipeline/features.py` — state variables, no lags/trends (exactly what the experiment tested):

```python
from common import BASE_END, BASE_START, DRY_SIGNALS, Country, months_between

def unit_month_features(c: Country) -> pd.DataFrame:
    ...
    for s in DRY_SIGNALS:                   # value of month r; apply_latency moves it to r-1
        out[s] = w[s]
    f = pd.DataFrame(out)
```

`pipeline/CONTRACT.md` section 1 — add the four `signal_type` rows (table in section 1 above) under
"dry-spell / season timing (CHIRPS v3 pentad), stored in `dryspell_<ISO3>.parquet`".

Kaggle re-check after adoption (data push already stages the new files):

```bash
scripts/kaggle/run.sh "python pipeline/train.py --iso3 ZWE KEN MWI ZMB"
KERNEL_SLUG=drought-dry scripts/kaggle/run.sh "bash pipeline/dryspell/kaggle_job.sh 4"   # re-run this experiment
```

Files: `pipeline/dryspell/extract_dryspell.py`, `exp_dryspell.py`, `kaggle_job.sh`, `extract_log.txt`,
`kaggle_run_log.txt`, `kaggle_results/{summary.md,results.json,replay_ZWE_2023.csv,log.txt,kaggle_run.json}`.
