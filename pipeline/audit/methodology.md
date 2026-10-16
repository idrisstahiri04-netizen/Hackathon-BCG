# Methodology audit (drought science + ML)

Auditor: methodology helper, 2026-10-16 (UTC). Read-only audit; no pipeline file was edited.
Files: `pipeline/{extract_signals,common,labels,features,train,alert_engine,export_risk}.py`,
`pipeline/CONTRACT.md`, `js/real.js`, spec. Numbers measured on `pipeline/data/signals_ZWE.parquet`
(91 ADM2 units, 2001-01..2024-12) with `/home/looooo/bcg/.venv`. Model runs were written to
`/tmp/audit_out*` and `/tmp/audit_risk*` only (owners' `pipeline/out`, `data/risk` untouched).
Line numbers = code state at 17:25 UTC (files changed during the audit; passes at 16:06, 16:52, 17:25).

Severity: **BLOCKER** = breaks a spec rule or makes the demo/headline wrong; **MAJOR** = biases
results or the pitch claim, fix before freeze; **MINOR** = document or fix if time.

## Summary table

| # | Sev | Status 17:25 | Where | Issue | Fix |
|---|---|---|---|---|---|
| B3 | BLOCKER | NEW | alert_engine.py:72-81, 157-201; result in /tmp/audit_risk2/ZWE.js | **The p-gate switches the replay off.** After the latency fix the CV skill is ~chance (section 5b), so `tune_thresholds` (precision >= base+0.10) pushes p_watch = p_warn = 0.775 (CV recall: Watch 1.7%, Warning 0.3%). Export: 148 Watch and 5 Warning unit-months in 72 months x 91 units; in 2023/24 **1 district at Warning before the declaration**, although vegetation AND (rain or soil) held in 19 (Dec), 25 (Jan), 44 (Mar) districts. | Rule wins CV (`winner: rule`), so drive levels by the spec rule and drop `p >= P_*` from Watch/Warning (keep p for NGO/food-bank text and ranking). Measured with families + 2-up/3-down hysteresis (min of last 2 runs, as at 16:06): first Warning Jan-2024 in 13 districts (issued end-Jan = ~9 weeks before 2024-04-03), 18 by March; Warning 0% of months in 2021, 3% in 2022 (normal years), Watch 16-19%. With the 17:02 one-step-per-month hysteresis: only 3 by Jan, 8 by March (see M10). |
| B1 | BLOCKER | PARTLY FIXED | alert_engine.py:79-81 | Hindsight use of the declaration month is gone (good), but Emergency is now **satellite-only** (`extreme`: VCI<20 & SPI-3<=-2, or p>=p_emerg & severe). Spec: Emergency = Warning + official declaration **or price spike**; public Emergency only after an official declaration. Farmer SMS at level 3 says "harvest failed". | Keep the signal as `severe=True` on a level-2 row for institutions; level 3 only with a real declaration/price input (announcement family). Earlier pass: `after` = month>=April in **every** year gave Emergency in May-Aug 2020 (28 districts) - make sure that code path stays removed. |
| B2 | BLOCKER | FIXED | common.py:36-64, train.py:100-113 | Data latency: issue month t now uses data of t-1 (CHIRPS final, MOD13Q1, ERA5 via CDS). Correct. Note ERA5-Land in Earth Engine lags 2-3 months; the demo pipeline must actually use CDS/ERA5T or set `era5: 3`. | Lead-time claims: first Warning month t = issued end of month t. |
| M1 | MAJOR | OPEN | labels.py:25,37,40,52 | `crop_failure`/`no_grass` = **min** monthly VCI over 3 months < 35 -> 40% prevalence; VCI<35 in 32% of baseline unit-months. "Below-normal greenness", not failure. FAO ASI applies 35 to a season-averaged index and an area share. | **>= 2 of 3 months VCI < 35** (measured, Jan-Mar, share of units): overall 17% (now 40%); 2014/15 0.10 (now 0.52), 2015/16 0.58, 2016/17 0.01, 2017/18 0.11 (now 0.57), 2023/24 0.40. Window-mean<35: 13%, but only 0.32 in 2023/24. Rename UI event "poor crop condition" unless validated vs IPC/yields. |
| M7 | MAJOR | WORSE (honest now) | train.py, /tmp/audit_out2/model_report.md | **No forecast skill at leads 1-3** once latency is applied: CV ROC-AUC crop_failure 0.46-0.51 (all ML models), no_grass 0.50-0.55; winner = rule; cant_plant model dropped (AUC 0.485). Before latency: ensemble 0.54/0.67, i.e. most of the apparent skill was the extra month of data. | Do not pitch "predicts N months ahead". Pitch monitoring/nowcast with ~1-2 months lead from rain+soil+vegetation agreement (B3 fix). For real lead: fix M1 labels; add Nino3.4/IOD at r (known months ahead); report bootstrap-by-year CIs. |
| M4 | MAJOR | OPEN | spec KPIs vs train.py | Targets are satellite-only (no circularity with announcements/prices - good), but the spec KPI is precision/recall of Warning+ **vs FEWS NET/IPC Phase 3+ transitions** and weeks gained vs the declaration. Not reported. | Score the exported level series vs IPC (`pipeline/audit/fetch_ipc.py`, `compare_ipc.py` exist): first Warning vs first IPC3+ (CS/ML1), precision/recall, n events, persistence baseline. |
| M9 | MAJOR | OPEN (by design) | alert_engine.py:76-78; js/real.js:29,78 | **cant_plant can never reach Warning** (Warning needs vegetation; nothing is green at planting). Now an explicit Watch-only path (`strong_weather`), so the farmer "wait for 2 good rains" SMS (minLevel 2) is never sent. Nov-Dec 2023 (SPI-1 -2 to -3) gave no farmer message. | Product decision: send the low-regret planting advisory at Watch, or add a second family available at planting (crowd replies; announcements capped at level 1; EO LST/ET). |
| M2 | MAJOR | PARTLY | export_risk.py:45, 74-77 | Ongoing windows (W0 - r in -2..0, lead clipped 0) are scored and labelled with a horizon; inside the window the label is partly observed (nowcast), and training lead 0 = r==W0 only. | Flag `nowcast` (horizon 0) and exclude from lead-time stats, or train leads -2..3. |
| M3 | MAJOR | OPEN | export_risk.py:109 vs alert_engine.py:157 | Thresholds tuned per (row, event) but export takes **max p over candidate events** - biased upward vs the tuned operating point. Moot if B3 fix drops the p-gate. | Tune on the same max-over-candidates construct, or one event per month by season phase. |
| M5 | MAJOR | OPEN | alert_engine.py:59-60 | Vegetation family = min(crop, grass) of (z<=-1 **or** VCI<35): fires in 30.5% of in-season baseline months. Soil not season-gated; Gaussian z on dry-season soil water reaches -7.4/+9.5. | Vegetation: crop for crop units / grass for pastoral, not min of both; Soil: gate to rainy season or use empirical-percentile z. |
| M6 | MAJOR | OPEN | extract_signals.py:39,184 | SPI fitted on 20 years (WMO: >= 30). Tails unstable; Feb 2024 hits the -3 clip. | Fit SPI on 1991-2020 (CHIRPS from 1981). Keep NDVI 2001-2020 and say so. |
| M8 | MAJOR | FIXED (over-corrected, see B3) | alert_engine.py:79 | First pass: Watch on in 80% of unit-months 2019-2022 (p_watch 0.25 + any single family). Now Watch needs p>=0.775 or strong weather -> almost never on. | Target Watch 15-25% of months in normal years; families-only rule gives 16-19%. |
| M10 | MAJOR | NEW 17:02 | alert_engine.py:94-115 | Hysteresis now moves **one level per month**, so Normal->Warning needs >= 3 months even when two-family agreement holds for 2 runs. Spec only says a level must hold 2 runs to go up. Cost measured on the rule-only replay: districts warned before 2024-04-03 drop from 18 to 8 (Jan-2024: 13 -> 3); normal-year Warning rate is 0% either way. | Go up to the level held for the last 2 runs (`level = min(hist[-2:])`), as before; keep the one-step rule for going down if wanted. |
| m9 | MINOR | NEW | alert_engine.py:100 | Fast entry (1 run when p >= p_fast) departs from the spec hysteresis (2 up). Currently inactive (p_fast = None). | Needs a spec change, or remove. |
| m10 | MINOR | NEW | seasonal_forecast.py | NMME seasonal forecast added: good idea for lead time (issue-month convention and own-hindcast standardisation look right). Caveats: hindcasts (CV years) vs real-time runs (2023/24) differ in members/system (CanSIPS-IC3 real-time from 2021-10), so CV skill may not transfer; 1-degree grid vs ADM2; it is the **weather** family (does not add a second independent family); register in data/sources.yaml. | Report skill separately for hindcast and real-time years; count it with rain/soil. |
| m1 | MINOR | PARTLY | extract_signals.py:192-213 | District-mean CHIRPS never exactly 0 (Jul mean 2 mm) -> zero branch never used; dry-season SPI is noise. Rain family now gated to rainy season (good); still a model feature. | Totals < 1 mm = 0; SPI NaN where calendar-month mean < 10 mm. |
| m2 | MINOR | OPEN | extract_signals.py:47,56-60,100 | 10 m WorldCover mask at 500 m = sampled/mode class, under-samples smallholder crop (3 units no crop NDVI; train.py falls back to grass). 2021 mask for 2001-2024. MOD13Q1 reduced at 500 m not 250 m. 16-day composite assigned to start month. | `reduceResolution(mean)` crop fraction per 250 m pixel, mask >= 0.3; scale 250. |
| m3 | MINOR | OPEN | extract_signals.py:219-241 | 2001-2020 climatology contains every CV fold year (VCI min/max set by the year itself: 4.8% of baseline months VCI=0). Hold-out clean. | Disclose, or recompute per fold. |
| m4 | MINOR | OPEN | train.py:55 | Lead-0 rows (features overlap label window) trained together with leads 1-3. | Separate nowcast model, or lead x signal interactions. |
| m5 | MINOR | OPEN | train.py Persistence | Persistence = previous season's label (weak). | Add anomaly persistence (VCI<35 / SPI-3<-1 at r). |
| m6 | MINOR | OPEN | export_risk.py:127,150 | Missing p written as 0.0 (`nan_to_num`) - violates "missing is missing". | Write null. |
| m7 | MINOR | OPEN | js/real.js:87-89,96 | Coop SMS has "shortage risk NN%" + "share with all members" -> probability reaches farmers; extension SMS "N/3 sources agree" though rain+soil are one weather family. | Coops: action only; "satellite + weather agree". |
| m8 | MINOR | OPEN | CONTRACT.md:18-26 | Signal names outside the controlled vocabulary in CLAUDE.md. | Spec change or map names. |

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
| data availability at r | FIXED - common.apply_latency, 1-month lag (B2) |
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
- Watch: now p>=P_WATCH or strong rain+soil dryness (no longer any single family). Spec Level 1 = "one source anomaly" - the families-only variant in B3 is closer to the spec.
- Emergency - B1 (satellite-only; spec needs declaration or price spike).
- Farmers: action only, no probability (js/real.js:77-83) OK; coops leak % (m7).
- Missing never raises a family (`_le/_lt` treat NaN as False) OK; but p NaN -> 0 (m6).

## 5. Measured model skill

### 5a. First pass, before latency (ZWE, /tmp/audit_out, 16:34 UTC)

CV = leave-one-agyear-out 2001-2022, leads 1-3, cells ROC-AUC / PR-AUC (base rate):

| model | cant_plant | crop_failure | no_grass |
|---|---|---|---|
| persistence | 0.46 / 0.18 (0.18) | 0.58 / 0.44 (0.39) | 0.49 / 0.39 (0.39) |
| rule (families) | 0.54 / 0.20 | 0.55 / 0.47 | 0.62 / 0.48 |
| ensemble (winner) | 0.55 / 0.20 | 0.54 / 0.44 | 0.67 / 0.53 |

Hold-out 2023/24 (base rates 0.60 / 0.76 / 0.88): ensemble AUC 0.63 / 0.48 / 0.56; rule 0.55 / 0.58 / 0.51.
Reading: rule fusion is as good as ML; skill beyond 1 month is near chance with these labels.
Fixing M1 (labels) and adding a seasonal driver (ENSO / Nino3.4 at r, legitimately known months
ahead and the main cause of 2015/16 and 2023/24) is the cheapest route to real lead-time skill.

### 5b. Second pass, latency applied (ZWE, /tmp/audit_out2, 17:00 UTC)

CV ROC-AUC / PR-AUC (base 0.39): crop_failure persistence 0.58/0.44, rule 0.51/0.41, logreg 0.51/0.41,
lgbm 0.46/0.35, ensemble 0.49/0.38; no_grass rule 0.55/0.42, others 0.49-0.52. Winner: rule.
Thresholds: p_watch = p_warn = 0.775, p_emerg = 0.95 (CV Warning recall 0.3%).
Export level counts (6552 unit-months): 0: 6399, 1: 148, 2: 5, 3: 0.

## 6. Replay of 2023/24

### 6a. Current code (/tmp/audit_risk2)

1 district at Warning Jan-Mar 2024; 46 at Watch only from
April (after the declaration). Two-family agreement existed in 19/25/5/44 districts Dec/Jan/Feb/Mar.

### 6b. Spec rule only (families + hysteresis 2/3, no p-gate, latency applied)

With the 16:06 hysteresis (jump to level held 2 runs):
First Warning after 2023-10-01: Jan-2024 13, Feb 1, Mar 4, Apr 28, May 26, Jun 7, Jul 1, never 11.
=> 18 districts warned before 2024-04-03, best lead ~9 weeks (issued end-Jan). Normal-year rates:
2021 Watch 16% / Warning 0%; 2022 Watch 19% / Warning 3%. Drought years 2019 and 2020 Warning 6% / 17%.

With the 17:02 one-step hysteresis: Jan 3, Feb 1, Mar 4, Apr 33, May 30, Jun 7, Jul 1, never 12
(8 before the declaration). Warning 0% in 2021 and 2022, 16% in 2020.

### 6c. First pass (before latency, superseded)

Units at Warning+ per data month: Oct-Dec 2023 0/91 (all Watch), Jan 13, Feb 14, Mar 18,
Apr 46 (6 Emergency), May 72, Jun 78. With latency (B2) a Jan-2024 data month is issuable
~mid-Feb, so honest lead vs 2024-04-03 is ~6-7 weeks for 13 districts and ~0-3 weeks for the
next 5; most districts reach Warning after the declaration. Warnings in Jun-Aug 2023 (24-31 units)
come from the previous season's grazing window, not from the 2023/24 drought - exclude them from
any "first Warning" statistic (use first transition after 2023-10-01).
Emergency appears in Jan-Mar 2019, May-Aug 2020 (28 units) and Jun-Aug 2023 with no declaration
behind it (B1).
