# Model-improvement experiments — results and recommendation

All numbers come from Kaggle runs of the scripts in this directory (`results/results_all.jsonl`, `results/log_*`,
`results/*.csv|json`); nothing is estimated. Pre-latency / old-label runs are archived in `prelatency/` and are not used below.

## Set-up (identical to the main model unless stated)
* Rows are built by calling the main code (`train.prepare_country` → `labels.build_targets` v1.1, `features.make_xy`,
  `common.apply_latency`, `train.add_families` with `crop_dominant`). **Latency is applied exactly as in train.py**
  (issue month r uses month r-1 satellite/reanalysis data). Hold-out rows (agyear ≥ 2023, KEN 2020-22) are flagged and never
  used for fitting, calibration, selection or metrics; the hold-out table below was produced **once**, for the single
  configuration chosen on CV.
* CV = leave-one-agricultural-year-out 2001-2022, countries pooled, training leads 0-3, metrics on leads 1-3, cross-fitted
  isotonic calibration — re-implemented in `harness.py`, reproducing the main report's baseline to the third decimal.
* Events: crop_failure and no_grass (cant_plant was dropped from the main model). "mean PR-AUC" = mean over the two.
  Ensemble = 0.5 logreg + 0.5 LightGBM raw scores (main `train.py` classes, same seeds, same early stopping).
* New inputs and their time alignment (no value is used before it was public at the end of month r):
  * **ONI** (NOAA, `data/oni/_meta.json`): trimester **ending at r-1** (NOAA publishes a trimester in the first ~10 days of the
    next month). `oni_x_south` = ONI × (+1 if centroid lat < −8°, else −1): El Niño is dry in southern Africa, wet in East Africa.
  * **Niño3.4 monthly, DMI** (`data/nino34`, `data/dmi`): month r-1.
  * **NMME seasonal rainfall forecast** (`pipeline/data/seasonal_fc_<ISO3>.parquet`, MME3 product): issued in month r
    (published ~day 8-10 of r). Features `sfc_z_m13, sfc_pbn_m13, sfc_z_m46, sfc_pbn_m46` = anomaly z and P(below normal) for
    months r+1..r+3 and r+4..r+6. Caveat: before ~2011 these are hindcasts, not real-time forecasts.
  * **Pooled countries**: MOZ TZA ETH SOM NAM BWA ZAF MDG AGO UGA (1,125 units, 657k training rows) enter only the training
    side of each fold; their agyear ≥ 2023 rows are dropped entirely (same regional drought as the hold-out season).

## A. Experiment table (CV, latency, v1.1 labels)
| experiment | what changes | ens. mean PR-AUC (Δ) | ens. mean Brier (Δ) | logreg Δ | lgbm Δ | crop_failure ROC / PR | no_grass ROC / PR |
|---|---|---|---|---|---|---|---|
| baseline (main model, v1.1 labels, latency) | — | 0.3375 | 0.1819 | — | — | 0.589 / 0.272 | 0.603 / 0.403 |
| oni_south_only | ONI×south (signed) → both members | 0.3505 (+0.0130) | 0.1815 (-0.0004) | +0.0155 | +0.0050 | 0.646 / 0.32 | 0.588 / 0.381 |
| oni_lr_only | ONI, ΔONI, ONI×south, lat → logreg only | 0.3485 (+0.0110) | 0.1813 (-0.0006) | +0.0110 | +0.0000 | 0.633 / 0.302 | 0.591 / 0.395 |
| oni_both | same 4 → both members | 0.3450 (+0.0075) | 0.1824 (+0.0005) | +0.0110 | -0.0005 | 0.644 / 0.315 | 0.577 / 0.375 |
| nino34_lr_only | monthly Niño3.4 (+3-mo mean, ×south), lat → logreg | 0.3500 (+0.0125) | 0.1809 (-0.0010) | +0.0120 | +0.0000 | 0.636 / 0.304 | 0.592 / 0.396 |
| oni_dmi_lr_only | ONI set + IOD/DMI → logreg | 0.3430 (+0.0055) | 0.1822 (+0.0003) | +0.0015 | +0.0000 | 0.627 / 0.3 | 0.575 / 0.386 |
| sfc_both | NMME MME3 P(below) & anomaly, m1-3 & m4-6 → both | 0.3720 (+0.0345) | 0.1779 (-0.0040) | +0.0340 | +0.0275 | 0.662 / 0.322 | 0.62 / 0.422 |
| combo_oni_sfc | NMME + ONI×south → both | 0.3625 (+0.0250) | 0.1797 (-0.0022) | +0.0295 | +0.0135 | 0.664 / 0.336 | 0.592 / 0.389 |
| combo_oni_sfc_cum | NMME + ONI×south + season-to-date rain % | 0.3660 (+0.0285) | 0.1793 (-0.0026) | +0.0300 | +0.0200 | 0.667 / 0.338 | 0.596 / 0.394 |
| combo_oni_lr_cum | ONI(logreg) + season-to-date rain % | 0.3530 (+0.0155) | 0.1807 (-0.0012) | +0.0120 | +0.0070 | 0.64 / 0.307 | 0.594 / 0.399 |
| cum_rain | season-to-date rain % of normal | 0.3455 (+0.0080) | 0.1812 (-0.0007) | +0.0055 | +0.0070 | 0.602 / 0.283 | 0.605 / 0.408 |
| cum_dry_gated | + dry-spell months + SPI gated to rainy season | 0.3450 (+0.0075) | 0.1816 (-0.0003) | +0.0060 | +0.0055 | 0.601 / 0.284 | 0.602 / 0.406 |
| mono | LightGBM monotone constraints (drier → riskier) | 0.3435 (+0.0060) | 0.1819 (+0.0000) | +0.0000 | +0.0025 | 0.591 / 0.282 | 0.597 / 0.405 |
| ens_w_lr70 | ensemble weight 0.7 logreg / 0.3 lgbm | 0.3380 (+0.0005) | 0.1819 (+0.0000) | +0.0000 | +0.0000 | 0.59 / 0.278 | 0.6 / 0.398 |
| pool_base | +10 countries in training (eval on 4) | 0.3540 (+0.0165) | 0.1792 (-0.0027) | +0.0120 | +0.0235 | 0.596 / 0.29 | 0.617 / 0.418 |
| pool_oni_lr_only | pooled + ONI(logreg) | 0.3615 (+0.0240) | 0.1787 (-0.0032) | +0.0185 | +0.0235 | 0.625 / 0.308 | 0.616 / 0.415 |
| pool_oni_sfc | pooled + NMME + ONI×south | 0.3800 (+0.0425) | 0.1771 (-0.0048) | +0.0320 | +0.0450 | 0.665 / 0.341 | 0.626 / 0.419 |
| v2_sfc_oni | per-event: crop NMME+ONI×south, grass NMME | 0.3795 (+0.0420) | 0.1774 (-0.0045) | +0.0370 | +0.0350 | 0.666 / 0.337 | 0.62 / 0.422 |
| v2_sfc_oni_lr | per-event: crop NMME+ONI×south, grass NMME+ONI(logreg) | 0.3735 (+0.0360) | 0.1784 (-0.0035) | +0.0295 | +0.0345 | 0.666 / 0.337 | 0.603 / 0.41 |
| v2_sfc_pool | **v2**: per-event as above + pooled 14 countries | 0.3870 (+0.0495) | 0.1757 (-0.0062) | +0.0380 | +0.0520 | 0.664 / 0.34 | 0.629 / 0.434 |

Not adopted / negative: **TimesFM** VCI forecasts as features: −0.054 PR-AUC on the ZWE 2015-22 subset and worse as an ensemble
member (`prelatency/timesfm_feat_result.json`; TimesFM shrinks toward normal and misses VCI<35 events at leads 2-3, see
`pipeline/out/timesfm_report.md`). **DMI/IOD**: no gain. **Monotone constraints, ensemble weights, dry-spell/SPI gating,
NDVI slope, phase interactions**: ≤ +0.008. **Calibration**: isotonic vs Platt/beta/by-lead differ by ≤ 0.001 Brier
(`results/calibration_ensemble.csv`) — keep isotonic.

Why ONI must not go raw into the trees: ONI is a year-level constant (22 distinct values in leave-one-year-out CV), so LightGBM
memorises years (`oni_both`: lgbm −0.0005, no_grass 0.403 → 0.375). The signed interaction alone, or ONI only in the linear
member, avoids this. NMME varies per unit and month and helps both members.

### Long leads (train leads 0-6, metrics per lead; ensemble ROC / PR-AUC)
| lead | base crop ROC/PR | +ONI crop | +ONI+NMME crop | base grass ROC/PR | +ONI grass | +ONI+NMME grass |
|---|---|---|---|---|---|---|
| 1 | 0.593 / 0.282 | 0.654 / 0.324 | 0.665 / 0.339 | 0.639 / 0.45 | 0.602 / 0.401 | 0.612 / 0.417 |
| 2 | 0.584 / 0.258 | 0.643 / 0.31 | 0.659 / 0.327 | 0.583 / 0.401 | 0.571 / 0.376 | 0.578 / 0.388 |
| 3 | 0.584 / 0.263 | 0.644 / 0.308 | 0.665 / 0.329 | 0.544 / 0.362 | 0.534 / 0.339 | 0.55 / 0.351 |
| 4 | 0.602 / 0.287 | 0.652 / 0.309 | 0.683 / 0.337 | 0.529 / 0.355 | 0.536 / 0.341 | 0.535 / 0.341 |
| 5 | 0.6 / 0.29 | 0.647 / 0.309 | 0.666 / 0.332 | 0.546 / 0.368 | 0.536 / 0.354 | 0.534 / 0.362 |
| 6 | 0.597 / 0.285 | 0.621 / 0.293 | 0.625 / 0.303 | 0.57 / 0.379 | 0.534 / 0.355 | 0.552 / 0.374 |
With ONI + NMME, crop_failure skill is flat from lead 1 to lead 5 (ROC 0.66-0.68) — the climate drivers carry real skill
4-5 months before the window; no_grass gains nothing beyond lead 3.

### Alternative labels (same features; PR-AUC must be read against its own base rate)
| label | base crop / grass | ens ROC crop / grass | ens PR crop / grass | persistence PR crop / grass | lift over persistence |
|---|---|---|---|---|---|
| current v1.1 (≥2 of 3 months VCI<35) | 0.204 / 0.287 | 0.589 / 0.603 | 0.272 / 0.403 | 0.228 / 0.305 | ×1.19 / ×1.32 |
| window-mean VCI < 35 | 0.174 / 0.277 | 0.617 / 0.596 | 0.259 / 0.376 | 0.207 / 0.295 | ×1.25 / ×1.27 |
| window-mean VCI < 35, + ONI(logreg) | 0.174 / 0.277 | 0.65 / 0.584 | 0.283 / 0.369 | 0.207 / 0.295 | ×1.37 / ×1.25 |
| min VCI below unit 20th pct (2001-20) | 0.211 / 0.202 | 0.554 / 0.56 | 0.259 / 0.244 | 0.22 / 0.202 | ×1.18 / ×1.21 |
| same + ONI(logreg) | 0.211 / 0.202 | 0.598 / 0.554 | 0.289 / 0.241 | 0.22 / 0.202 | ×1.31 / ×1.19 |
`window-mean VCI < 35` is the cleanest target (highest ROC, best lift over persistence); per-unit quantile labels are
memoryless (P(1|prev=1) 0.22 vs 0.20) and no more predictable. Recommendation: keep v1.1 for the product (base rate 0.20/0.29
is already "failure", not "below normal"), consider `mean VCI<35` as the headline evaluation label.

## B. Hold-out, evaluated once (v2 = `v2_sfc_pool`, chosen on CV before looking)
| hold-out set | event | base rate | v1 baseline ROC / PR / Brier | **v2** ROC / PR / Brier |
|---|---|---|---|---|
| all | crop_failure | 0.324 | 0.478 / 0.368 / 0.2322 | 0.735 / 0.56 / 0.1929 |
| all | no_grass | 0.451 | 0.677 / 0.637 / 0.2518 | 0.795 / 0.733 / 0.2238 |
| ZWE | crop_failure | 0.407 | 0.449 / 0.372 / 0.3008 | 0.571 / 0.507 / 0.2559 |
| ZWE | no_grass | 0.725 | 0.549 / 0.771 / 0.3968 | 0.563 / 0.769 / 0.3614 |
| KEN | crop_failure | 0.192 | 0.702 / 0.398 / 0.1449 | 0.779 / 0.504 / 0.131 |
| KEN | no_grass | 0.299 | 0.826 / 0.703 / 0.1631 | 0.881 / 0.761 / 0.1446 |
| MWI | crop_failure | 0.321 | 0.459 / 0.341 / 0.237 | 0.426 / 0.368 / 0.2467 |
| MWI | no_grass | 0.5 | 0.402 / 0.461 / 0.307 | 0.529 / 0.545 / 0.2764 |
| ZMB | crop_failure | 0.638 | 0.371 / 0.583 / 0.4281 | 0.579 / 0.688 / 0.308 |
| ZMB | no_grass | 0.655 | 0.621 / 0.759 / 0.3755 | 0.712 / 0.805 / 0.3272 |
v1 baseline = same harness, main features. v2 improves ROC, PR-AUC and Brier on every set except MWI crop_failure (ROC 0.43 vs
0.46, 28 units, single season). Zimbabwe 2023/24 crop_failure: ROC 0.449 → 0.571, PR 0.372 → 0.507, Brier 0.301 → 0.256.
Caveat (as in the main report): ZWE/MWI/ZMB hold-out is one season in which most units were in drought, so AUC there ranks
units, it does not measure "seeing the year coming". The long-lead and season-level results in C do.

## C. Spec-mode alert logic: what can raise an earlier Watch (no model, CV years only)
Spec mode = Warning needs vegetation & (rain | soil) families, p informational. Instance = one (unit, crop_failure window) in
CV years, v1.1 label, families with `crop_dominant` (v1.1). Hit rate = share of real events where the input fires at that
lead; FPR = share of non-events that fire (`results/watch_inputs.csv`, `watch_inputs.py`):

| input (at issue month, lead L months before the crop window) | L | hit rate | FPR | FAR |
|---|---|---|---|---|
| CONTRACT Warning condition (veg & (rain or soil)) | 2 / 3 | 0.024 / 0.031 | 0.012 / 0.013 | 0.66 / 0.61 |
| Watch: any core family | 2 / 3 | 0.113 / 0.107 | 0.065 / 0.055 | 0.69 / 0.67 |
| ENSO: signed ONI ≥ 0.5 | 3 / 4 | 0.304 / 0.230 | 0.168 / 0.128 | 0.68 / 0.69 |
| ENSO: signed ONI ≥ 1.0 | 3 / 4 | 0.111 / 0.108 | 0.040 / 0.037 | 0.58 / 0.57 |
| NMME P(below) m1-3 ≥ 0.5 | 2 / 3 | 0.129 / 0.122 | 0.063 / 0.052 | 0.66 / 0.62 |
| ONI ≥ 1.0 or (ONI ≥ 0.5 and NMME P(below) ≥ 0.5), **Zimbabwe** | 3 / 4 | 0.228 / 0.165 | 0.037 / 0.023 | 0.45 / 0.41 |
| ENSO: signed ONI ≥ 0.5, **Zimbabwe** | 3 / 4 | 0.411 / 0.345 | 0.136 / 0.095 | 0.62 / 0.58 |

Reading: the Warning condition almost never fires before a window (that is the 4/91 pre-declaration result); the family Watch
catches 11 % at 6 % FPR 2-3 months out. A climate Watch on ONI ≥ 1.0 has the same recall at **half the FPR, 1-2 months earlier**;
ONI ≥ 0.5 doubles the recall at 13 % FPR four months out. Season level (Spearman, share of a country's units in crop failure
vs ONI known at origin; sign flipped for KEN): ZWE +0.64/+0.66/+0.69/+0.65 at leads 2/3/4/5; MWI +0.36..+0.42; ZMB +0.13..+0.26;
KEN +0.63/+0.65 at leads 2/3. Southern Africa, ONI 4 months before the window: El Niño seasons 73 % of units in crop failure,
neutral 46 %, La Niña 31 %. Fact from the input data: ONI trimester ending Aug-2023 = +1.0, Oct-2023 = +1.5 — public by
end-September 2023, six months before the 2024-04-03 declaration.

FEWS NET outlook text (ZWE 2015+, `watch_inputs.csv`): `rain_outlook == below` with gazetteer match fires rarely (11-40 of 728
unit-seasons) with FAR 0.18-0.5; the descriptor-map version fires on 26-29 % of non-events. Use gazetteer rows only, Watch only.

Lead time with the model's p (`results/leadtime_*`, main features): the family gate, not p, is binding. At FPR ≤ 0.2 a
probability-only crop_failure alert (p ≥ 0.30) catches 33 % of events with mean lead 2.3 months (55 % at lead 3), versus
14 % / 1.5 months for the gated Warning at any p.

## D. Recommendation (ranked) and exact changes for the main pipeline
1. **Adopt NMME seasonal-forecast features for both events** (+0.0345 alone; part of v2). `features.py`:
```python
# features.unit_month_features(): after the rain_pct3 block
def seasonal_fc_features(iso3, index):
    f = DATA_DIR / f"seasonal_fc_{iso3}.parquet"
    out = pd.DataFrame(index=index, columns=["sfc_z_m13", "sfc_pbn_m13", "sfc_z_m46", "sfc_pbn_m46"], dtype=float)
    if not f.exists():
        return out                                    # missing is missing
    d = pd.read_parquet(f); d["issue_month"] = pd.to_datetime(d["issue_month"])
    d = d[d["product"] == "NMME/MME3"]
    g = d.groupby(["unit_id", "issue_month", "target_window"])[["anom_z", "p_below_normal"]].mean().unstack("target_window")
    g.columns = [f"sfc_{'z' if a == 'anom_z' else 'pbn'}_{b.replace('-', '')}" for a, b in g.columns]
    g = g.reindex(index)                              # index = (unit_id, month): forecast issued in month r is known in r
    for c in out.columns:
        if c in g: out[c] = g[c].values
    return out
f = pd.concat([f, seasonal_fc_features(c.iso3, w.index)], axis=1)
```
   `common.SOURCE` has no entry for `sfc_*`, so `apply_latency` leaves them unshifted — correct (NMME is published in the
   issue month). Add `sfc_pbn_m13 >= 0.5` to the Watch reasons in `alert_engine` as a *climate* family (Watch only).
2. **Add ONI×south for crop_failure only** (both members); do **not** give raw ONI to LightGBM. `features.py`:
```python
ONI = json.loads((HERE / "experiments" / "climate_indices.json").read_text())["oni_trimester_end"]   # NOAA, public domain
oni = pd.Series({pd.Timestamp(k + "-01"): v for k, v in ONI.items()})
known = oni.reindex(mon - pd.DateOffset(months=1)).values            # trimester ending r-1
south = np.where(lat_of_unit < -8.0, 1.0, -1.0)                       # centroid latitude per unit
f["oni_x_south"] = known * south
```
   `train.py`: per-event columns: `cols_by_event = {"crop_failure": cols + SFC + ["oni_x_south"], "no_grass": cols + SFC}` and
   pass `cols_by_event[ev]` to `fit_all` (and store it in the bundle for `export_risk.score`).
3. **Pool the 10 extra countries into training** (+0.0165 alone, +0.0495 with 1-2): in `train.run`, load them with
   `prepare_country`, mark `train_only=True`, drop `agyear >= 2023`, include in each fold's training set only; exclude from
   `cv`-metrics, threshold tuning and hold-out. Expected cost: ~5× training rows (Kaggle CPU: `v2_sfc_pool` CV took 14 min).
4. **Climate Watch input (spec mode)**: new Watch-only family `climate` = `oni_x_south >= 1.0 or (oni_x_south >= 0.5 and
   sfc_pbn_m13 >= 0.5)`, active from 4 months before the unit's planting month. Never counts toward Warning (same rule as text).
   Evidence: table in C. Expected effect on the ZWE replay: Watch from Sep/Oct 2023 for the whole country (ONI known +1.0 by
   end-Sep-2023, +1.5 by end-Oct); not measured on the hold-out here (replay needs the export, main helper).
5. **FEWS NET rain outlook (gazetteer rows only)** as an `official_text` Watch input, 3-month validity; ignore "Crisis projected".
6. Not worth adopting: TimesFM, DMI, monotone constraints, alternative calibration, dry-spell/SPI gating, phase interactions.

Kaggle runtime for re-running everything: `scripts/kaggle/run.sh "bash pipeline/experiments/kaggle_job.sh 4 <groups>"`,
groups = enso sfc pooled labels longlead season model v2 calib holdout; 4-15 min per group on a 4-vCPU kernel.
