# Methodology audit (drought science + ML)

Auditor: methodology helper, 2026-10-16 (UTC). Read-only audit; no pipeline file was edited.
Files: `pipeline/{extract_signals,common,labels,features,train,alert_engine,export_risk}.py`,
`pipeline/CONTRACT.md`, `js/real.js`, spec. Numbers measured on `pipeline/data/signals_ZWE.parquet`
(91 ADM2 units, 2001-01..2024-12) with `/home/looooo/bcg/.venv`. Line numbers = state at 16:30 UTC.

Severity: **BLOCKER** = breaks a spec rule or makes a headline number wrong; **MAJOR** = biases
results or the pitch claim, fix before freeze; **MINOR** = document or fix if time.

## Summary table

| # | Sev | Where | Issue | Fix |
|---|---|---|---|---|
| B1 | BLOCKER | export_risk.py:116, alert_engine.py:76-77 | Emergency (level 3) is reachable without an official declaration: `after` = "calendar month >= April" **in every year** (2019, 2020, ... all get a fake declaration), plus a satellite-only `extreme` path (VCI<20 & SPI-3<=-2). Spec: Emergency = Warning + official declaration or price spike; "public Emergency messages only after an official declaration". The farmer SMS at level 3 says "harvest failed". | `after_decl = month >= actual declaration date` from a per-year declaration list (only 2024-04-03 for ZWE; nothing for other years). Drop the `extreme` path or cap it at level 2 with a flag `severe=True` for institutions. |
| B2 | BLOCKER | export_risk.py:91-138 (t = data month) | **Data latency ignored.** A row at month r uses month-r CHIRPS, MOD13Q1 and ERA5-Land; these are complete only ~2-6 weeks after month end (CHIRPS final ~3rd week of next month; MOD13Q1 composites that start late in r end mid r+1, +~1 week processing; ERA5-Land ~5 days). Frontend `t` = r, so "first Warning vs 2024-04-03" overstates weeks gained by ~4-6 weeks. extract_signals.py:95 also assigns a 16-day composite to its start month, so month r already contains up to 15 days of r+1. | Add `issue_date = r + 1 month + 15 days` (or per-source latency) and compute lead time vs declaration from issue_date. Show the timeline at issue month, or label it "data month". |
| M1 | MAJOR | labels.py:25,37,40,52 | `crop_failure`/`no_grass` = **min** monthly VCI over 3 months < 35. VCI<35 occurs in 32% of baseline unit-months; the min over 3 months gives 40% prevalence for "crop failure" (2001-2024). That is "below-normal greenness", not failure. Kogan's 35 threshold is for a single-week/month VCI, and FAO ASI applies it to a season-averaged index per pixel, then to the share of cropland affected. | Use **>= 2 of 3 months VCI < 35** (measured, crop window Jan-Mar, share of units): overall 17% (vs 40% now); 2014/15 0.10 (now 0.52), 2015/16 0.58, 2016/17 0.01, 2017/18 0.11 (now 0.57), 2023/24 0.40. Window-mean < 35 gives 13% but only 0.32 in 2023/24 (Jan-2024 greenness was normal). ASI-style area share is the longer-term option. Rename UI event "poor crop condition" unless validated against IPC/yields. |
| M2 | MAJOR | export_risk.py:44-54, train.py:51 | Export scores **ongoing windows** (W0 - r from -2..0, lead clipped to 0). Inside the window, the label inputs (VCI in W0..W0+2, SPI/soil in planting months) are partly observed: this is a nowcast, yet `horizon` is set to >=2 weeks (line 138) and the model was only trained with lead 0 = r==W0 (rows with r>W0 are out of distribution). | Mark rows with d<=0 as `nowcast` (horizon 0) and never count them as "lead time"; either train leads -2..3 or score only d>=0. |
| M3 | MAJOR | export_risk.py:96-99 vs alert_engine.py:140-170 | Thresholds tuned per row (one event) but export uses **max p over 2-5 candidate events**; max of several calibrated probabilities is biased upward, so live Watch/Warning rates exceed the tuned F1/F2 operating point. | Tune thresholds on the same max-over-candidates OOF construct, or pick the event by season phase (one candidate per month) and keep per-event thresholds. |
| M4 | MAJOR | spec §KPIs vs train.py:339-363 | Targets are satellite-only (correctly no circularity with announcements/prices), but the spec KPI is precision/recall of Warning+ **vs FEWS NET/IPC Phase 3+ transitions**. Nothing reports that; slides must not call VCI hits "shortages". | Score the exported Warning series against FEWS NET IPC (pipeline/audit/fetch_ipc.py + compare_ipc.py already exist): per-district first Warning vs first IPC3+ (CS or ML1), precision/recall, n events, persistence baseline. |
| M5 | MAJOR | alert_engine.py:59-60 | Vegetation family = min(crop, grass) of (z<=-1 **or** VCI<35): fires in **30.5%** of in-season baseline months (2001-2020); Warning family condition holds in 16.7% of normal in-season months, so false-alarm control rests entirely on `p`. Soil family is not season-gated: sm1_z on tiny dry-season soil water reaches -7.4/+9.5, |z|>3 in 2-4% of Jun-Sep months. | Vegetation: require crop (or grass for pastoral units), not the min of both, and AND/2-month persistence; Soil: gate to rainy season like rain, or use percentile (empirical CDF -> normal) instead of a Gaussian z. |
| M6 | MAJOR | extract_signals.py:39,184 | SPI baseline 2001-2020 = 20 years; WMO SPI guide requires >= 30 years for the gamma fit. Tails (SPI<-2, which drive Emergency/extremes) are unstable; values clipped at -3 (Feb 2024 hits the clip). CHIRPS is available from 1981 at no extra cost. | Fit SPI on 1991-2020 (pull CHIRPS 1990-2000; 11 more cached years). Keep NDVI baseline 2001-2020 (MODIS limit) and say so. |
| m1 | MINOR | extract_signals.py:192-213 | No minimum precip threshold: district-mean CHIRPS is never exactly 0 (0 zeros in 2001-2020, even Jul mean 2 mm), so the zero-mass branch never triggers and dry-season SPI is a gamma fit on noise. Now gated in alert_engine (rain family) but still a model feature. | Treat monthly totals < 1 mm as zero; set SPI NaN for calendar months with climatological mean < 10 mm (May-Sep in ZWE). |
| m2 | MINOR | extract_signals.py:56-60,100, SCALE 47 | Crop mask: 10 m WorldCover reduced at 500 m uses the pyramid (sample/mode) of the class map, so a MODIS pixel counts as crop only if crop dominates; smallholder maize is under-sampled (3 units have no crop NDVI at all, now replaced by grass in train.py:71). WorldCover 2021 mask applied to 2001-2024. MOD13Q1 native 250 m reduced at 500 m. `SummaryQA<=1` keeps "marginal" (acceptable; snow/cloud flagged in DetailedQA not used). | `crop.reduceResolution(mean).reproject(MODIS proj)` -> crop fraction per 250 m pixel; mask >= 0.3 or weight by fraction; scale 250. |
| m3 | MINOR | extract_signals.py:219-241, common.py:68 | Climatology 2001-2020 includes every CV fold year, so CV features/labels are standardised with the held-out year inside the baseline (VCI min/max is set by the record year itself: 4.8% of baseline months are VCI=0). Hold-out 2023/24 is clean. | Disclose (CV is mildly optimistic) or recompute z/VCI per fold excluding the fold year. |
| m4 | MINOR | train.py:51 | Training includes lead-0 rows where features overlap the label window (vci at W0, spi_1m/sm1_z at W0 for cant_plant). Not leakage for the lead 1-3 metrics, but in the linear model it inflates the weight of current-month signals for all leads. | Train separate models for lead 0 (nowcast) and leads 1-3, or add lead x signal interactions. |
| m5 | MINOR | train.py:128-133 | Persistence baseline = previous season's label (weak). Spec asks to beat persistence; the honest baseline is *anomaly persistence* (current VCI<35 / SPI-3<-1 at r). | Add "anomaly persistence" model to MODELS. |
| m6 | MINOR | export_risk.py:118,135 | Missing p is written as 0.0 (`nan_to_num`) - violates "missing is missing". | Write `null`; level from families only. |
| m7 | MINOR | js/real.js:87-89,96 | Cooperative SMS carries "shortage risk NN%" and asks to "share with all members" -> probability reaches farmers; extension SMS says "N/3 sources agree" though rain+soil are one weather family. | Coops get action only; say "N/2 independent families (satellite + weather)". |
| m8 | MINOR | CONTRACT.md:18-26 vs CLAUDE.md | Signal names (`spi_6m, ndvi_z_crop, vci_crop, sm1_z, t2m_z, precip_mm`) are outside the controlled vocabulary; needs the spec change the rules require. | Add them to the spec vocabulary (or map: sm1_z->soil_moist_z, ndvi_z_crop->ndvi_z). |

## 1. Science

- **SPI** (extract_signals.py:175-216). Gamma MLE (`floc=0`) per unit x calendar month, mixed
  distribution H = q + (1-q)G, zeros at q/2 (Stagge et al. 2015 "centre of mass") - correct
  choice. Issues: 20-year baseline (M6), no zero threshold (m1), 3-/6-month sums need the
  previous year (handled: CHIRPS from start-1, line 285). Sign check vs anomalies is 99.4% (data_check.md).
- **NDVI/VCI**. Scale 0.0001, QA SummaryQA<=1, mask to WorldCover 40 / 20+30, monthly mean of
  16-day composites by start date (B2, m2). VCI per unit x calendar month min/max over 20 years
  (fine; Kogan uses the record), clipped 0-100. Note data_check.md: Jan-2024 NDVI anomalies were
  positive in sample units - the 2023/24 vegetation signal shows mainly from Feb 2024, so lead time
  will come from rain/soil, not vegetation.
- **ERA5-Land z** (219-229). Gaussian z per calendar month on volumetric soil water; skewed and
  bounded -> extreme z in dry months (M5). Use empirical-percentile z or gate to season.
- **Monthly aggregation**. CHIRPS pentads summed by calendar month (pentads align with months -
  correct). MOD13Q1 by composite start date (B2). ERA5 monthly aggregate `.first()` - correct.
- **Season detection** (common.py:147-198). Wettest 3-month window from 2001-2020 climatology;
  bimodal only if second peak >= 45% and dry dips on both sides. ZWE: 91/91 unimodal, core Dec-Feb,
  planting Nov-Dec, crop Jan-Mar, grass Apr-Jun - agrees with the FEWS NET ZWE calendar. KEN
  bimodal logic tested only on synthetic data (no real KEN parquet yet).

## 2. Labels

- Satellite-only, no announcement/price input -> no circularity with the official story. Good.
- Labels share signals with the alert families (VCI<35 in both): fine for lead >= 1 because label
  months are strictly after r; for ongoing windows (M2) the family flag and the label are the same data.
- ZWE label prevalence by agyear (`python labels.py --iso3 ZWE`): 2015/16 crop 0.99, 2016/17 0.03,
  2019/20 0.60, 2023/24 0.76 (cant_plant 0.85, no_grass 0.88). Years look right; the level is too
  high overall (M1).
- VCI<35 literature:
  - Kogan 1995, Adv. Space Res. 15(11):91-100, VCI definition and drought detection:
    https://www.sciencedirect.com/science/article/pii/027311779500079T
  - NOAA STAR Vegetation Health: drought when VCI/VHI < 40, severe below lower values:
    https://www.star.nesdis.noaa.gov/smcd/emb/vci/VH/VH-Syst_10ap30.php
  - FAO ASIS: ASI = % of arable pixels whose season-averaged VHI (crop-coefficient weighted) is below 35, "identified as a critical threshold ... by Kogan, 1995"; admin areas classed by % affected:
    https://www.fao.org/giews/earthobservation/asis/index_1.jsp?lang=en
  - UN-SPIDER recommended practice (VCI drought monitoring):
    https://un-spider.org/advisory-support/recommended-practices/recommended-practice-drought-monitoring/in-detail
  - SPI: WMO SPI User Guide (WMO-No.1090, >=30 yr):
    https://www.droughtmanagement.info/literature/WMO_standardized_precipitation_index_user_guide_en_2012.pdf ;
    Stagge et al. 2015 zero handling: https://rmets.onlinelibrary.wiley.com/doi/10.1002/joc.4267
  - Conclusion: 35 is a defensible *drought-stress* cut-off (Kogan/FAO), but FAO applies it to a
    **season-mean** and an **area share**, not to the minimum month - hence M1.

## 3. Leakage checklist

| check | status |
|---|---|
| future months in features | OK - features.py uses shift(L>=1) and value at r only; r = W0 - lead |
| data availability at r | **FAIL** - B2 (month r not available at r) |
| baseline includes hold-out years | OK - 2001-2020 excludes 2023/24 |
| baseline includes CV years | minor (m3) |
| scalers/imputers fit on all data | OK - sklearn pipeline inside each fold (train.py:149) |
| early stopping on test fold | OK - inner validation seasons from training years (train.py:162-171) |
| calibration | OK - cross-fitted isotonic, fold k calibrator never sees fold k labels |
| thresholds tuned on hold-out | OK - tune_thresholds on CV OOF leads 1-3 only (train.py:303) |
| model selection on hold-out | OK - winner by CV PR-AUC |
| CV grouped by season | OK - leave-one-agricultural-year-out, all units and events of a year held out together. No temporal purge (train on later years) - acceptable, disclose. |
| final model uses hold-out | OK - final fit on CV rows only |
| frontend in-sample | OK - CV months scored by their fold model (export_risk.py:66-69) |
| hold-out informativeness | single season, base rate ~0.8: AUC ranks districts only (report already says so) |

## 4. Alert rules vs spec

- Two independent families: Warning = vegetation AND (rain OR soil) (alert_engine.py:70) -> rain+soil
  alone cannot reach Warning. Matches spec (eo + weather). Heat supporting only. OK.
- Hysteresis 2 up / 3 down (alert_engine.py:82-92) on monthly runs. Correct; level can jump 0->2 in
  one step when both runs are >= 2 (acceptable).
- Watch on a single family or p>=p_watch - matches "Level 1 = one source anomaly".
- Emergency - B1.
- Farmers: action only, no probability (js/real.js:77-83) OK; coops leak % (m7).
- Missing never raises a family (`_le/_lt` treat NaN as False) OK; but p NaN -> 0 (m6).
