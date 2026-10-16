# Agro-climatology / drought-monitoring review

Date 2026-10-16 · Branch `zimbabwe-real-data` · Scope: physical indicators and methods that are open, in Earth Engine or
downloadable, and usable within ~1 day. Tests: `pipeline/experts/agroclimate/` (extract + analyse), results in
`pipeline/experts/agroclimate/results_{ZWE,MWI}.md`, data in `pipeline/data/agroclimate_{ZWE,MWI}.parquet` (contract long format,
16 new `signal_type`s, baseline 2001-2020, low = dry). Nothing in the existing pipeline was edited.

## 0. The main finding first (what the tests say)

1. **The 2023/24 Zimbabwe season had no land-surface signal that was both early and persistent.** Data month Nov 2023 was dry
   (SPI-1 ≤ -1.5 in 84 % of districts, ERA5 topsoil 93 %, FLDAS evapotranspiration 60 %), **Dec-Jan rains recovered everything**
   (Jan 2024: VCI < 35 in 4 %, SPI-3 ≤ -1 in 27 %, soil 0 %), then the **Feb 2024 dry spell** collapsed the crop (Feb: SPI-3 84 %,
   soil 97 %, TCI 70 %, VCI 33 %). Every indicator we tested, new or old, shows the same dry / wet / dry shape (table T1). So
   extra lead time cannot come from a better anomaly index of the same months; it has to come from (a) issuing faster than
   monthly, (b) treating the late onset as its own event, (c) forecasts.
2. **Within a season, no satellite indicator ranks which districts enter IPC 3+.** Pooled ROC-AUC vs FEWS NET post-harvest Crisis
   (districts not yet in crisis) looks good for the water-balance indices (0.80-0.83 at Jan vs 0.73 for SPI-3), **but the per-season
   AUC is 0.3-0.6** (2023/24: 0.25-0.36, i.e. inverted). The pooled skill is between-season skill: indicators tell drought years
   from normal years, FEWS NET / vulnerability decides which districts tip. That is why problem (5) exists and will not be solved
   by satellite data; it is the correct division of labour and should be pitched as such.
3. **Latency is the biggest lever.** From the cached CHIRPS pentads: by **16 Feb 2024** 53 % of Zimbabwe districts had ≥ 15
   consecutive dry days (49 % ≥ 20 days) in the flowering window; quiet seasons 2016/17 and 2020/21 had 0-1 % on that date
   (2015/16: 22 %). A dekadal issue on ~17 Feb would have been ~6.5 weeks before the 3 April declaration, versus the current
   monthly product that sees Feb data only at the end of March (0.4 weeks). MODIS LST 8-day and MOD13Q1 16-day composites
   covering the first half of Feb were available by ~25 Feb (TCI < 35 in 70 % of districts for Feb) — enough for a two-family
   Warning about 5 weeks ahead for roughly half the districts. **Not yet replayed end-to-end; the numbers above are the inputs
   that existed on those dates, not a validated alert count.**

## 1. Ranked proposals

| # | Proposal | Physics | Data (verified in EE 2026-10-16) | Latency | Effort | Family | Expected effect on problems 1-5 |
|---|---|---|---|---|---|---|---|
| 1 | **Dekadal issuance + in-season dry-spell trigger** (reuse `pipeline/dryspell`: `dry_spell_max`, `days_since_rain` at pentad level; CHIRPS-prelim for the last 2 pentads) | Maize yield is set by water stress at flowering/grain-fill (Jan-Feb in ZWE). A 15-20 day dry spell then is the damage event itself; it is visible in rain 1-3 months before NDVI/IPC. | `UCSB-CHC/CHIRPS/V3/PENTAD` (final ~3 wk; prelim 2 days after the pentad, USGS WRSI doc); MOD11A2 8-day; MOD13Q1 16-day | 2-10 days | 1 day (issue loop runs 3×/month; family rule unchanged) | rain (+ vegetation via LST) | (2) biggest: +4-6 weeks for ~50 % of ZWE districts in 2023/24 per the pentad check; (3) sharper Watch; no help for (1),(4),(5) |
| 2 | **Season water balance / SPEI-like index** (CHIRPS − PET, 3-month and season-to-date; `spei3_like`, `wb_season_z` already in the parquet) | Rain minus atmospheric demand is the crop water supply; heat during El Niño adds demand that SPI ignores. | PET from `NASA/GLDAS/V021/NOAH/G025/T3H` `PotEvap_tavg` (monthly mean computed server-side) or ERA5-Land `potential_evaporation_sum`; operationally better: NOAA MERRA-2 ETos (what FEWS NET uses) | GLDAS 2.1 ~1 month; ERA5T ~5 days (CDS) | 0.5 day | rain | ZWE: Jan-24 alarm share 81 % vs 27 % for SPI-3, IPC AUC 0.80/0.83 vs 0.73 (between-season), T3 median lead 6.9 wk vs 4.9 wk (6 vs 7 districts). 2015/16: 96-100 % from Nov. Quiet seasons clean except Oct-Nov (PET-dominated months: gate to rainy season, already done by the engine). Helps (2) modestly, (3) slightly; MWI no gain |
| 3 | **FLDAS soil moisture and ET** (FEWS NET's own LDAS) instead of / beside ERA5-Land | Same physics as ERA5 soil, but forced by CHIRPS + MERRA-2, so it is consistent with our rain, and it is what FEWS NET analysts look at. 40-100 cm layer carries last season's deficit into planting. | `NASA/FLDAS/NOAH01/C/GL/M/V001` (0.1°, monthly, 1982-2026-08): `SoilMoi00_10cm/10_40cm/40_100cm_tavg`, `Evap_tavg` | final ~20th, prelim ~5th of next month (ldas.gsfc.nasa.gov/fldas/specifications); EE copy lags ~1-2 months | 0.5 day (already extracted) | soil | Zero false Warnings in all three quiet ZWE seasons (ERA5: 4); same 7 districts before the declaration. Dec IPC AUC 0.78 (0-10 cm) vs 0.75 ERA5. Cheap robustness gain; little lead-time gain |
| 4 | **MODIS LST → TCI / VHI** (Kogan) | Canopy warms when transpiration stops, days before greenness drops. | `MODIS/061/MOD11A2` LST_Day 1 km 8-day, QC ≤ 1, crop/grass masks | ~1 week | done (in parquet) | vegetation / heat | **Did not add lead at monthly resolution**: Nov 2023 TCI 12 %, Dec 24 %, Jan 0 %, Feb 70 %. 2015/16 stronger (96 % Nov) and 2016/17 clean. T3 Warnings before the declaration fell 7 → 2 (two-months-running rule breaks on the Jan recovery). Keep LST as the fast second family for proposal 1, not as a monthly replacement |
| 5 | **FEWS NET WRSI (maize, Southern Africa)** as a direct crop-stress input | Full FAO water balance (Kc, soil WHC, SOS/EOS): WRSI < 50 = crop failure; "Extended WRSI" projects end-of-season with climatology. | GeoTIFF zips, dekadal, 2001/02-present: `https://edcintl.cr.usgs.gov/downloads/sciweb1/shared/fews/web/africa/southern/dekadal/wrsi-chirps-etos/southern/downloads/dekadal/` (naming `wYYYYDDsa.zip`) | updated 2nd/7th/12th/… of each month | 1 day (download ~24 dekads × 24 seasons, zonal stats) | vegetation-proxy (crop model) — needs spec decision | Should be the best single crop indicator for (1) and the explainable "crop failure" message; not tested here (no EE copy). Note: it is a model, not an observation, so pair with NDVI/LST for the 2-family rule |
| 6 | **JRC ASAP hotspots** | Independent expert-classified warning (NDVI + rain + phenology) | HDX `asap-hotspots-monthly.csv` (Oct 2016-present, monthly, CC BY-IGO) | monthly | 2 h | announcement-type | Admin-1 only for ZWE; use as a second "official text" source to cut FEWS NET dependence (5) — cannot raise above Watch by spec |
| 7 | SMAP L4 root-zone soil moisture `NASA/SMAP/SPL4SMGP/008` | Observation-constrained root-zone water | 9 km, 3-hourly, 2015-03 onward | ~3 days | 0.5 day | soil | Fast soil family for the dekadal loop; **no 20-year baseline** (percentiles vs 2015-2025 only). Not tested |
| 8 | Not recommended: GLDAS 2.1 soil/ET anomalies (false alarms in 2020/21: 26-96 % of districts), TerraClimate and MOD16A2GF (yearly releases, not operational; MOD16 ESI had the best Dec sat-label AUC 0.69, but EE has non-GF MOD16 only from 2021), SPEIbase `CSIC/SPEI/2_10` (1°, to 2023-12, annual update) | | | | | | |

**Malawi (problem 4):** nothing tested gains skill (T2 within 0.4-0.6, T3 Warnings 3 → 0-4, quiet-season false alarms rise
8 → 11-19 unit-months). Malawi's 2023/24 shows the same dry (Dec) / wet (Jan) / dry (Feb) sequence, 28 units, and IPC
transitions in the "not yet in crisis" subset are 4 % — the crises are chronic-south, flood (Freddy 2023) and price-driven.
Recommend: pitch Malawi as monitoring + prices + FEWS NET, not satellite prediction.

## 2. Test details (ZWE, 91 districts; MWI, 28)

- **T1** share of districts in alarm per data month, seasons 2015/16, 2016/17, 2020/21, 2023/24 — full table in `results_ZWE.md`.
  Clean quiet seasons (≤ 10 % Dec-Apr) for: VCI, SPI, ERA5/FLDAS soil, TCI/VHI, SPEI-3, water balance. Dirty: GLDAS, PDSI.
- **T2** ROC-AUC at data month vs (a) the pipeline's satellite label (≥ 2 of 3 crop months VCI < 35; ~2 090 unit-seasons) and
  (b) IPC CS ≥ 3 in Apr-Sep, districts with pre-season phase < 3 (ZWE n ≈ 520, 9 seasons; MWI n = 178).
  Sat label from Nov/Dec: everything ≈ 0.5-0.65 — the Jan-Mar outcome is not in the Nov-Dec land state (physics, not a modelling
  gap; lead time there must come from NMME/ENSO). Jan: MOD16 ESI 0.85, VCI 0.82, SPI-3 0.78, SPEI-3 0.67.
  IPC pooled vs per-season: see section 0 point 2 (per-season table printed by the robustness check in this session; e.g.
  `wb_season_z` Jan pooled 0.83, seasons 2017: 0.80, 2019: 0.79, 2023: 0.28).
- **T3** alert replay with `alert_engine.families/hysteresis`, one family swapped (1-month latency, no p_crisis Watch).
  ZWE 2023/24 Warnings before 2024-04-03: current 7 (4.9 wk), VHI 2, TCI 2, FLDAS 7, SPEI-3 6 (6.9 wk), combo 2.
  2015/16 by end-Feb 2016: current 40, VHI 47, TCI 49, SPEI-3 47, combo 53 of 91. Quiet 2020/21: 0 for all variants.

## 3. Concrete 1-day plan for the team

1. Issue 3×/month: move the engine to a dekadal clock; rain family adds `dry_spell_max ≥ 3 pentads` or `days_since_rain ≥ 3`
   during each unit's `crop` months (from `common.detect_seasons`); vegetation family may use MOD11A2 TCI < 35 for the latest
   16 days when MOD13Q1 is not yet in. Keep hysteresis in runs (2 dekads up / 3 down) and re-run `judge.py`.
2. Add `spei3_like` / `wb_season_z` next to SPI-3 in the rain family (`rain = spi_3m ≤ -1 or spei3 ≤ -1`, rainy-season gated).
3. Replace ERA5 `sm1_z` by FLDAS 0-10 cm (or OR them) — fewer false Warnings, same hits.
4. If time: pull WRSI zips for 2001-2024 and compute district mean WRSI/anomaly; report it as the crop-failure message driver.
5. Pitch: "satellite tells the year, FEWS NET tells the district" — and show the Feb-2024 dekadal timeline as the lead-time story.
