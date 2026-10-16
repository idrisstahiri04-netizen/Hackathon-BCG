# ML / spatio-temporal forecasting review — drought early warning

Author: ML expert helper · 2026-10-16 · branch `zimbabwe-real-data` · read-only review + 2 Kaggle experiments.
Code: `pipeline/experts/ml/` (nothing in the pipeline was edited; nothing committed). Kaggle kernel `drought-xml`,
code dataset `drought-code-xml` (own slug, so other helpers' kernels were not replaced). Results: `pipeline/out/kaggle/<ts>/out/xml/`.

Inputs read: `docs/models_explained.md`, `docs/metrics_report.md`, `pipeline/out/model_report.md`,
`pipeline/ipc_model/report.md`, `pipeline/audit/methodology.md`, `pipeline/{features,labels,train,common}.py`,
`pipeline/experiments/{harness,harness_ext,extra_features,run_experiments3}.py`, `pipeline/ipc_model/{ipc_data,train_ipc}*.py`.

## 0. Diagnosis in one paragraph

Model A (satellite labels) is weak for a structural reason, not a tuning one: its target (2 of 3 months VCI < 35, 1–3 months
ahead) is a *vegetation nowcast* delayed by the data latency, and the features are the same vegetation/rain/soil signals one
month earlier. With a 1-month latency the gap between the last observed month and the first label month is L+1 = 2–4
months, which is about the de-correlation time of monthly SPI/VCI anomalies in southern Africa. What does carry 2–4 months is
the *climate state* (ENSO, NMME) and *spatially coherent* anomalies (a drought that already covers the region rarely vanishes).
The prior experiments confirm this: ONI × south was the only extra that moved CV PR-AUC (+0.02); TimesFM (pure own-history)
made things worse. Model B (IPC target) is strong only because FEWS NET projections encode exactly that regional/seasonal
judgement; without them it falls to ROC 0.74 and, worse, it ranks by chronic geography (grass_frac, south, ONI), not by the
season. The alert engine's lateness and broad Watch follow from the same thing: the Warning rule needs vegetation, and
vegetation is the *last* signal to move (data_check.md: Jan-2024 NDVI anomalies were still positive in ZWE).

## 1. Ranked proposals

Ranking = expected gain on the five problems × cost before the model freeze. "Measured" = run in this review (section 2);
otherwise the gain is an expectation and is marked as such.

| # | Proposal | Problems | Status / measured gain | Cost |
|---|---|---|---|---|
| 1 | **FEWS proxy (distillation)** — train an EO + NMME + ONI model whose target is "FEWS NET projects IPC3+ for t+1..t+3", use its probability as a feature of the IPC model (stacked, nested CV). Gives a crisis probability that keeps working when the FEWS feed is late/down. | 5, 2 | **Measured (2.1):** proxy alone beats the IPC-trained EO model on IPC truth, CV ROC 0.796 vs 0.768 (PR 0.381 vs 0.353); stacked into the IPC model +0.004 PR only. FEWS-off gap becomes hold-out ROC 0.94 → 0.89 instead of → 0.73; the current masked `eo_fews` collapses to 0.59 (below persistence). | done |
| 2 | **Spatial features** — contiguity-neighbour mean, country-wide mean and own-minus-neighbour difference of 9 signals at r-1. Cheap, no new data, respects latency. | 1, 3 | **Measured (2.2): no gain.** nb +0.004 CV PR, nat −0.002, nb_nat −0.005; hold-out once (nb) −0.003. Only ONI × south moves anything (ZWE +0.046, MWI +0.032). Use the graph in the alert engine instead (section 3). | done |
| 3 | **Malawi: per-country vs pooled model, country fixed effects, per-country calibration** | 4 | **Measured (2.3): none helps** — per-country model 0.211 → 0.191, one-hot ±0, per-country calibration ±0.005 Brier. Root cause is the label: VCI<35 fires in wet/flood seasons (2019/20 no_grass 0.75, 2021/22 crop 0.61). | done |
| 4 | **Target engineering: season-level severity instead of monthly windows.** Predict one label per (unit, season): season-mean VCI of the core window < 35 *and* area share (FAO ASI style) — one row per season per lead-from-planting (Oct, Nov, Dec, Jan). Removes the lead-0/lead-3 mixing (audit m4) and the 2-of-3 noise; the alert engine then reads a *season* probability that is stable month to month, which is what hysteresis wants. Prior `lab_mean35` (mean VCI<35) ran at PR 0.3175 vs 0.338 — on monthly rows it is harder; the gain is in stability, not AUC. | 1, 2, 3 | not measured; expected: fewer flip-flops, same AUC | 0.5 day |
| 5 | **Continuous VCI forecast + threshold (quantile LightGBM)** — regress end-of-core-window VCI (q10/q50/q90 with `objective=quantile`), derive P(VCI<35) from the quantile spread. Gives a *calibrated early trigger*: Watch when q50 < 35, Warning when q90 < 35 confirmed by observed vegetation. Honest uncertainty for NGOs without showing farmers a probability. | 2, 3 | not measured; expected: better Watch precision (the q90 rule is stricter than any-single-family) | 0.5 day |
| 6 | **Hazard / time-to-crisis model** (discrete-time survival: for each unit-month not yet in IPC3+, P(enter within h) with h as a feature, censored at the last map). Equivalent to the current h13/h46 but one model, consistent across horizons, and it gives a *median time to crisis* (SMS: "pre-position within ~2 months"). | 2 | not measured; same data as Model B, ~1 day | 1 day |
| 7 | **Monotone constraints** on the IPC/Model-A LightGBM (p non-increasing in SPI, VCI, soil moisture, NMME anomaly; non-decreasing in P(below normal), ONI × south). Removes the "chronic geography" ranking of the eo model (gain led by grass_frac/crop_frac) by forcing the season signals to act in the right direction. `run_experiments3 mono` exists (not in results.jsonl yet). | 1, 5 | not measured here; expected small AUC change, large interpretability gain for the jury | 1 h |
| 8 | **Transfer from the 14-country pool with domain adaptation** — pooled rows exist (`expand.py`, 10 extra countries). Honest way: train pooled, *evaluate per target country*, add country-level random-effect proxies (country one-hot + per-country isotonic) rather than naive pooling; the v2 IPC ablation ("does pooling help?") is the right template. Caution: SOM/NAM/AGO have no cropland → vegetation family rests on grass. | 1, 4 | pooled runs are being done by another helper (`drought-exp-v2`); do not duplicate | — |
| 9 | **Climatology / ENSO-analogue ensemble** — for each (unit, season) a prior = label rate in the k most similar past seasons by (ONI at issue, NMME anomaly). Average with the model (or feed as a feature). The `oni_south_only` experiment (+0.02 PR) is the linear version; analogue years give the same signal non-parametrically and a jury-friendly "this looks like 2015/16" message. | 1, 2 | not measured; expected ≈ ONI gain, better story | 0.5 day |
| 10 | **Per-livelihood-zone thresholds** — VCI 35 is a cropland stress threshold; for pastoral units the no_grass label should use the grass VCI percentile (e.g. unit-specific 20th percentile) and for high-potential units a stricter one. `lab_q20` (20th-percentile labels) scored PR 0.2515 vs base 0.168 (= +50 % relative over its base, more than the fixed-35 label's +65 %?) — inconclusive; needs base-rate-normalised comparison. | 1, 3 | not measured | 0.5 day |
| 11 | **Class-imbalance handling** — labels are 20–29 % positive; `class_weight="balanced"` is already in logreg, LightGBM uses none. Focal loss / `scale_pos_weight` move the operating point, not the ranking; with isotonic calibration afterwards the gain is nil. **Do not spend time here.** | 1 | not needed | — |
| 12 | **Conformal prediction** for the NGO probability (split-conformal on the OOF scores per season → "the 90 % band for P(crisis) is 0.3–0.7"). Honest, cheap, cosmetic for a hackathon. | 3 | not measured | 2 h |
| 13 | **Temporal-CV pitfalls to fix in reporting** — (a) leave-one-year-out without purge: Model A trains on *later* years (acceptable, disclosed); Model B purges — good. (b) The 2001–2020 VCI/SPI climatology includes every CV fold year (audit m3): a season that sets the VCI min for its unit gets VCI = 0 by construction → optimistic CV for extreme years; hold-out is clean. (c) Season bootstrap CIs (Model B has them, Model A does not: 22 folds → report 5–95 % by season). | credibility | report fix only | 1 h |

Not recommended now: multi-task crop+grass+IPC joint model (the labels live on different row grids; a shared trunk brings little over the stacked proxy), deep sequence models (22 seasons × 282 units is too little signal per season; TimesFM already showed the shrink-to-climatology failure).

## 2. Experiments run on Kaggle (honest protocol)

Protocol for all: same folds, calibration and purge as the production code; hold-out (agyear ≥ 2023 + KEN 2020–22) scored once
with a configuration declared in the script before any result was seen; latency 1 month everywhere; numbers copied from
`xml_proxy_metrics.json` / `xml_spatial_results.json` — none invented.

### 2.1 Experiment A — satellite-only FEWS NET proxy (IPC model, h13)

`pipeline/experts/ml/xml_fews_proxy.py` → `pipeline/out/kaggle/20261016T192327Z/out/xml/xml_proxy_{tables.md,metrics.json}` (170 s on Kaggle).
Rows = `ipc_data.build_country` for ZWE+KEN+MWI (17,928 issue-months, same as `ipc_model/report.md`). Proxy = logreg+LightGBM on
the **eo** features (signals, NMME, ONI, statics) with target *FEWS NET projects IPC3+ for t+1..t+3* (`fews_h13 ≥ 3`; 94 % of CV rows
have a projection, rate 0.35). Nested: fold-k test rows get a proxy fitted without k; fold-k training rows get proxies fitted without
{k, own fold} (36 proxy fits). CV = leave-one-season-out 2015/16–2022/23 with purge; hold-out scored once.

CV, transition rows (known state < IPC3; base 0.157), ROC / PR-AUC / Brier:

| model | pooled | ZWE (base 0.221) | MWI (base 0.121) | KEN (base 0.06) |
|---|---|---|---|---|
| persistence | 0.709 / 0.255 / 0.123 | 0.627 / 0.279 | 0.723 / 0.232 | 0.877 / 0.204 |
| FEWS NET own projection | 0.863 / 0.525 / 0.089 | 0.826 / 0.559 | 0.890 / 0.449 | 0.930 / 0.489 |
| eo:lgbm (current no-FEWS model) | 0.768 / 0.353 / 0.142 | 0.714 / 0.370 | 0.625 / 0.173 | 0.924 / 0.489 |
| **proxy alone** (EO → FEWS target, scored vs IPC truth) | **0.796 / 0.381** | **0.754 / 0.410** | **0.679 / 0.204** | 0.926 / 0.527 |
| eo_proxy:lgbm (eo + proxy) | 0.776 / 0.357 / 0.140 | 0.729 / 0.377 | 0.635 / 0.160 | 0.902 / 0.456 |
| eo_fews:lgbm (current FEWS-dependent model) | 0.872 / 0.598 / 0.094 | 0.827 / 0.641 | 0.896 / 0.427 | 0.962 / 0.623 |
| **eo_fews with FEWS columns masked (feed down)** | **0.594 / 0.238 / 0.167** | 0.549 / 0.278 | 0.585 / 0.203 | 0.618 / 0.142 |

Hold-out once (transition rows): pooled eo 0.893/0.525, eo_proxy 0.890/0.530, eo_fews 0.936/0.722, eo_fews_masked 0.747/0.314,
FEWS 0.938/0.735. ZWE 2023/24 (base 0.378): eo 0.759/0.601, **eo_proxy 0.773/0.626**, eo_fews 0.938/0.915, masked 0.629/0.495.
Proxy vs its own target: ROC 0.84 (transition rows).

Replay ZWE 2023/24 at CV max-F1 thresholds (57 transitions, 0 calm districts → timing only): eo 48 warned, 30 before 2024-04-03
(28 with 2 runs); eo_proxy 48 / 27 (19); eo_fews 57 / 36 (22); FEWS projection itself 56 / 15. Masked eo_fews: 54 "before the
declaration" — **not foresight: with its FEWS columns NaN the model drifts high everywhere** (CV ROC 0.59, worse than persistence).

Reading:
1. Distillation works as a *target*, not as a *feature*: an EO model trained on FEWS projections ranks IPC transitions better than
   the same EO model trained on IPC truth (+0.03 ROC, +0.03 PR pooled; +0.04 ROC ZWE, +0.05 ROC MWI). FEWS projections are a
   denser (monthly-usable), less noisy label than 3 CS maps/year, so the EO model learns the seasonal pattern instead of the map
   timing. Stacking it back into the IPC model adds almost nothing (the IPC model already has the same inputs).
2. The current production fallback is wrong: if the FEWS feed is down, `eo_fews` must **not** be served with missing columns — it
   over-alerts (54/57 districts) and loses all ranking. Serve the **proxy (or eo)** instead; the panel should state which model is
   on. Gap FEWS-on vs FEWS-off is ROC 0.87 → 0.80 (CV) / 0.94 → 0.89 (hold-out), not 0.94 → 0.73 as before.
3. Not fixed by any of this: ZWE 2019/20 (nobody above 0.53) and MWI in general (proxy 0.68; FEWS 0.89 — Malawi's crises are
   price/macro-driven, see 2.3).

### 2.2 Experiment B — spatial / neighbour features (Model A, satellite labels)

`pipeline/experts/ml/xml_spatial.py` (+ `build_neighbours.py`, queen contiguity from the unit polygons; mean degree 4.3–5.2).
Features at r-1: `nb_<s>` neighbour mean, `nat_<s>` country mean, `dif_<s>` own − neighbour, for 9 signals. Harness CV
(22 folds, pooled ZWE/KEN/MWI/ZMB, leads 1–3). Two Kaggle runs: run 1 (`20261016T192327Z`, all variants; crashed after the CV
step so the hold-out was not scored) and run 2 (`20261016T194348Z`, nb/nat/nb_nat/percountry + hold-out once). **The shared
signals dataset was re-versioned by another helper between the two runs, so the base differs (0.345 vs 0.371); compare within a run only.**

CV ensemble mean PR-AUC over the two events (base rates 0.20 crop / 0.29 grass):

| variant | run | pooled | ZWE | KEN | MWI | ZMB | lead 1 / 2 / 3 |
|---|---|---|---|---|---|---|---|
| base | 1 | 0.345 | 0.248 | 0.445 | 0.182 | 0.318 | 0.374 / 0.350 / 0.319 |
| nb (neighbour means) | 1 | 0.349 (+0.004) | 0.253 | 0.450 | 0.182 | 0.318 | 0.379 / 0.355 / 0.322 |
| nat (country means) | 1 | 0.343 (−0.002) | 0.253 | 0.451 | 0.172 | 0.305 | |
| nb_nat (+ differences) | 1 | 0.340 (−0.005) | 0.252 | 0.445 | 0.176 | 0.308 | |
| nb_nat + ONI × south | 1 | 0.350 (+0.005) | **0.294 (+0.046)** | 0.446 | **0.214 (+0.032)** | 0.309 | 0.380 / 0.350 / 0.330 |
| nb_nat + neighbours' previous-season label | 1 | 0.340 | 0.250 | 0.450 | 0.171 | 0.307 | |
| country one-hot (fixed effects) | 1 | 0.344 | 0.245 | 0.443 | 0.176 | 0.310 | |
| base | 2 | 0.371 | | | 0.211 | | |
| nb | 2 | 0.372 (+0.001) | | | 0.214 | | |
| one model per country | 2 | 0.377 (+0.006) | 0.297 (−0.002) | 0.516 (+0.032) | **0.191 (−0.020)** | 0.332 (+0.012) | |

Hold-out once (run 2; pick declared = best CV among nb/nat/nb_nat → `nb`): pooled ensemble mean PR 0.364/0.554 → 0.363/0.549
(−0.003); LightGBM +0.013; KEN −0.02, MWI +0.02 (n small), ZMB −0.016. Per-country isotonic calibration vs pooled: Brier within
±0.005 everywhere.

Reading: spatial smoothing of the *inputs* adds nothing — the neighbour mean correlates 0.95 with the unit's own SPI-3, so the
model already sees it; the spatial coherence that matters is *seasonal and regional* and is carried by ONI/NMME, not by
neighbours. Spatial features are **not** worth a slot in the frozen model. Use the neighbour graph for the *alert engine* instead
(proposal 3 in section 3): a Warning that is isolated (no neighbour at Watch or above) is far more likely a VCI/fire artefact than
a drought.

### 2.3 Malawi — why "no skill" (diagnostics from both experiments)

- Per-country model is *worse* for Malawi (CV 0.211 → 0.191); country fixed effects do nothing; per-country calibration does
  nothing. The problem is not pooling.
- The **labels are wrong for Malawi**. Prevalence of the satellite label by season (lead 1, CV years): `no_grass` = 0.96 in 2004/05,
  **0.75 in 2019/20 (a wet season)**, 0.46 in 2015/16; `crop_failure` = **0.61 in 2021/22 (Tropical Storm Ana, floods)**, 0.57 in 2004/05,
  only 0.39 in 2015/16 (the real El Niño drought) and 0.04 in 2016/17. VCI < 35 in Malawi marks cloud/flood/burn months of a small,
  wet, densely cropped country as often as drought. No model can learn drought from that target.
- In the IPC experiment Malawi is the one country where FEWS NET (CV ROC 0.89) is far above every EO model (proxy 0.68): its
  crises are price- and macro-driven (2021/22, 2023/24 maize price spikes, kwacha devaluation), which `prices_MWI.parquet`
  (81 % of rows have a value) should capture — the prices hook ran with the FDW/WFP series for the first time only in the v2 IPC rows.
- Recommendation: for Malawi (and for the alert engine generally) require the vegetation family to be confirmed by the rain
  family in the *same* unit-season (drought ⇒ SPI-3 < −1 at some point in the season); drop VCI-only positives from the training
  labels (label = VCI rule **and** season SPI-3 min < −0.5). This is a one-line change in `labels.py` and should be re-run before
  the freeze; expected effect: Malawi prevalence drops to the drought years, CV skill becomes measurable.

## 3. What I would change before the model freeze (priority order)

1. **Fix the FEWS-outage path (1 h, measured).** Never score `eo_fews` with missing FEWS columns. Fallback order: `eo_fews` →
   proxy (`xml_fews_proxy.Proxy`, EO features, FEWS-projection target) → `eo`. Show "model: FEWS-informed / satellite-only" in the
   NGO panel. Pitch line becomes "0.94 with FEWS NET, 0.89 without" (hold-out ROC, transition rows) instead of 0.94 → 0.73.
2. **Train the EO crisis model on the FEWS-projection target (distillation), 2 h, measured.** Proxy alone beats the IPC-trained
   EO model on IPC truth (CV ROC 0.80 vs 0.77; ZWE 0.75 vs 0.71; MWI 0.68 vs 0.63). Use it as the satellite-only "chance of crisis".
3. **Use the neighbour graph in the alert engine, not in the model (2 h, not measured).** Suppress a Warning whose unit has no
   neighbour at ≥ Watch in the same run (isolated VCI/fire artefact), and let a Watch become Warning one run earlier when ≥ 2
   neighbours are already at Warning (spatial confirmation = the spec's "independent evidence" in the spatial dimension).
   Replay it with `judge.py`/`compare_ipc.py` exactly as v1.1 — this attacks problems 2 and 3 directly, which no feature did.
4. **Clean the satellite label (1 h, diagnosed in 2.3).** VCI rule AND season SPI-3 min < −0.5. Re-run `train.py` on Kaggle, re-read
   Malawi. Rename the UI event to "poor crop condition" if Malawi still shows no skill.
5. **Season-level target + quantile/hazard output (½–1 day each, proposals 4–6)** only if time remains after the freeze candidates
   above; they change what the engine consumes, so they are day-2-morning work at the latest.
6. Reporting fixes (proposal 13): season-bootstrap CIs for Model A; disclose the climatology-fold overlap; state in every table
   which data version the base was computed on (the two spatial runs differ by 0.026 PR-AUC on the *same code* because the
   input dataset changed underneath — freeze `drought-signals` before the model freeze).

Things I checked and would *not* do: class re-weighting (calibration already handles it), per-country models (hurt Malawi),
country fixed effects (no effect), neighbour-mean features (no effect), TimesFM (already shown to shrink to climatology).
