# Results judge: verdict

Judge run 2026-10-16 ~17:10 UTC on the **latency-aware export**: `data/risk/{ZWE,MWI,ZMB,KEN}.js`, model
`sat-v1-ensemble-ZWE_KEN_MWI_ZMB`, `generated_at` 17:03:01 (ZWE), 17:03:27 (KEN), 17:03:39 (MWI), 17:04:17 (ZMB) UTC.
Model/thresholds: `pipeline/out/thresholds_ZWE_KEN_MWI_ZMB.json` (16:49 UTC, p_watch 0.525 / p_warn 0.50 / p_emerg 0.95 /
p_fast 0.775; the same values are embedded in all four risk files). Not retrained.
Re-run: `PYTHONPATH=/tmp/judge_libs python pipeline/audit/judge/judge.py` (matplotlib lives in `/tmp/judge_libs`).
Numbers: `judge_<ISO3>.json`, per unit: `units_<ISO3>.csv`, plots: `judge_<ISO3>.png`.

What changed in this export vs the one judged at 16:45 (see section 7): data latency of 1 month is built in
(`meta.issue_convention`: "level/p for month t are issued at the end of month t from data of month t-1"), so the
judge's **`next_month_1st` convention is the realistic one** and its `+5wk latency` convention double-counts (it is
reported in the JSON but not used below). Hysteresis is now one step per month (2 runs up, 3 down, fast entry at
p >= 0.775), rows kept only by hysteresis carry `held=True`, Watch is `p >= 0.525` or strong rain+soil dryness, and the
Emergency rule no longer uses the declaration date.

**Note:** `pipeline/out/model_report.md` section "Replay check on exported files" (written 16:58) still quotes the
16:53 export (ZWE 4/91 Warning before declaration, IPC recall 0.544). Those are superseded by the numbers below.

## Verdict: WEAK AS AN EARLY WARNING FOR THE ZIMBABWE DECLARATION. Honest, no longer hindsight-tuned, Watch is now selective, but Warning arrives after the government in ZWE/ZMB/MWI.

## 1. Skill (from model_report.md, unchanged since 16:49; climatology Brier = base*(1-base))

CV pooled (leave-one-agricultural-year-out 2001-2022, latency modelled), cells ROC / PR-AUC / Brier:

| target (base rate) | persistence | rule | ensemble (chosen) | climatology Brier |
|---|---|---|---|---|
| crop_failure (0.478) | 0.562 / 0.514 / 0.2488 | 0.514 / 0.492 / 0.2521 | 0.571 / 0.546 / 0.2503 | 0.2495 |
| no_grass (0.414) | 0.547 / 0.440 / 0.2458 | 0.536 / 0.436 / 0.2480 | 0.620 / 0.553 / 0.2365 | 0.2426 |

- Mean PR-AUC: ensemble 0.550 > logreg 0.542 > lgbm 0.534 > persistence 0.477 > rule 0.464. Small skill; clearest on no_grass.
- crop_failure Brier (0.2503) is *not* better than climatology (0.2495). The model adds ranking, not calibration, there.
- cant_plant model dropped (no CV skill); it is a rule-based Watch reason only.
- Hold-out 2023/24 (ZWE 273 rows, base 0.76-0.88): ensemble mean PR-AUC 0.841 vs persistence 0.830, ROC 0.55. Same
  reading as before: near-random ranking inside the drought year. Do not quote hold-out PR-AUC as "accuracy".
- Thresholds now carry CV precision: Watch precision 0.558 at rate 0.211 (base 0.446), Warning 0.555 at rate 0.054.

## 2. Story check (crisis window Oct-Jun; KEN Oct 2020-Dec 2021), realistic issue convention

A month's level is issued at the end of that month (data of the previous month). Lead = declaration minus issue date.

| | units | ever Warning in window | Warning issued before decl. | median lead | Watch before decl. | Watch median lead |
|---|---|---|---|---|---|---|
| ZWE (decl 2024-04-03) | 91 | 33 (36.3%) | **0 (0%)** | n/a | 26 (28.6%) | 15.4 wk |
| ZMB (decl 2024-02-29) | 116 | 42 (36.2%) | **5 (4.3%)** | 4.0 wk | 71 (61.2%) | 17.1 wk |
| MWI (decl 2024-03-23) | 28 | 4 (14.3%) | **2 (7.1%)** | 3.1 wk | 19 (67.9%) | 16.1 wk |
| KEN (decl 2021-09-08) | 47 | 15 (31.9%) | **11 (23.4%)** | 14.1 wk (IQR 7.6-14.1) | 41 (87.2%) | 44.4 wk |

- First Warning month, ZWE: Apr-24 9, May-24 17, Jun-24 7. Nothing before April data, which is issued 30 April, four
  weeks **after** the 3 April declaration. Even the optimistic "1st of the same month" convention gives only 9/91.
  Monthly share of ZWE units at Warning+: 0% through Mar-24, 9.9% Apr, 28.6% May, 36.3% Jun.
- ZMB: first Warnings Jan-24 5 (Manyinga, Kasempa, Ngabwe, Lukulu, Lumezi), Feb-24 16, Mar-24 17, Apr-24 3, May-24 1.
- MWI: Mchinji and Ntcheu in Feb-24, Dowa Mar-24, Machinga May-24. Government declared 23 of 28 districts; the model warned 4.
- KEN is the only country with a real Warning lead: Mandera Jan-21, then Kilifi, Laikipia, Isiolo, Marsabit, Turkana,
  Samburu in May-21, Garissa Jun-21, Mombasa, Kwale, Tana River Jul-21 (11 ASAL/coastal counties before 8 Sep 2021).
- Emergency: ZWE 3 unit-months (1.1% of units in window), ZMB 105 (14.7%), KEN 46 (6.4%), MWI none. No longer gated on
  the declaration date, so the red is model output.
- Hysteresis holds: 60% of ZWE Warning unit-months, 61% ZMB, 64% MWI, 54% KEN are `held=True` (raw level below the shown
  level). Most of the time a unit is shown at Warning, the current month's data alone would not put it there.

**Watch selectivity** (share of all unit-months 2019-2024 at Watch; was 69% in ZWE before): ZWE 17.2%, MWI 22.8%,
ZMB 42.8%, KEN 44.6%. Share of units ever at Watch in Nov-Apr: ZWE normal 2019/20 8.8%, wet 2020/21 9.9%, normal 2021/22
51.6%, normal 2022/23 23.1%, dry 2023/24 78.0%, 2024/25 0%. Watch is now selective in Zimbabwe and Malawi (MWI wet
2022/23 is the exception: 82% of districts), still broad in Zambia (54-77% of districts in normal seasons) and Kenya
(79% in wet 2019/20; a Nov-Mar season class fits Kenya badly).

**False alarms** (Warning+ unit-months, Nov-Apr; season class = country-mean Nov-Mar SPI-1, wet > +0.3, dry < -0.3):
- ZWE: wet 2020/21 **0**. Normal 2019/20 0, 2021/22 4 (1 unit), 2022/23 0, 2024/25 0. Dry 2023/24 9 (9 units), dry 2018/19 6.
- ZMB: no wet season in range. Normal 2019/20 6 (1.7% of units), 2020/21 36 (11.2%), 2022/23 14 (5.2%). Dry 2021/22 167 (41%), 2023/24 105 (35%).
- MWI: wet 2018/19 0, wet 2022/23 0. Normal 2019/20 0, 2020/21 0, 2021/22 21 (25% of districts). Dry 2023/24 8 (10.7%).
- KEN: wet 2019/20 0, wet 2023/24 4, wet 2024/25 4. Normal 2020/21 3, 2021/22 61 (34%), 2022/23 128 (55%); 2021-23 were real drought years.

## 3. Plausibility (where do Warnings fall)

- **ZWE now misses the west and the south-east.** The 10 driest units by season SPI-3 (Tsholotsho, Hwange, Bulilima,
  Victoria Falls, Binga, Lupane, Sanyati, Ruwa, Goromonzi, Makoni) include only 2 at Warning (was 7 of 10 at 16:45;
  Lupane never even reaches Watch despite crop NDVI-z -2.1). Never at Warning: Beitbridge, Binga, Bubi, Bulilima,
  Chiredzi, Chivi, Hwange, Lupane, Mangwe, Masvingo, Mwenezi, Nkayi, Plumtree, Tsholotsho, Zaka. First Warnings are
  Harare-area and Mashonaland East units (Bindura Urban, Harare, Ruwa, Epworth, Chitungwiza, Marondera, Mudzi) in April.
  Spearman of Warning months vs season-mean SPI-3 is -0.11 (was -0.63), vs crop NDVI-z -0.03 (was -0.73). Lat bands:
  south 39%, middle 50%, north 20% warned; lon: west 19%, centre 40%, east 50%. The spatial pattern is no longer a
  drought map. Likely cause: the 1-month latency plus one-step hysteresis means the dry west is still climbing
  Normal->Watch->Warning when the window closes, and the `p >= 0.50` gate drops units whose vegetation signal came late.
- **ZMB plausible but weaker.** Spearman vs crop NDVI-z -0.52 (was -0.76), SPI-3 -0.38. Middle band 71%, south 26%,
  north 13%; west 46%, east 41%. Driest-10 units: 6 warned. Western and Eastern Province districts come first (Jan-Feb).
- **MWI still wrong in the south.** Nsanje, Chikwawa, Thyolo, Mulanje, Chiradzulu, Phalombe, Blantyre, Mwanza, Neno,
  Zomba, Balaka never reach Warning despite SPI-3 -0.9 to -1.4 and sm1_z -1.0 to -1.5; their crop NDVI-z is -0.07 to
  -0.95, so the vegetation family never fires. Warnings are central (Mchinji, Ntcheu, Dowa, Machinga). Driest-10: 1 warned.
- **KEN plausible.** East 56%, centre 40%, west 0% warned; Spearman vs sm1_z -0.53, SPI-3 -0.45, lon +0.56 (drier east).
  Driest-10: 7 warned. Fits the ASAL north/east drought.

## 4. Plots
`judge_ZWE.png`, `judge_ZMB.png`, `judge_MWI.png`, `judge_KEN.png` (regenerated 17:0x UTC): monthly maps Nov-Apr plus a
unit x month heatmap, south at the top, dashed line at the declaration. Visual reading: the pre-crisis map is now mostly
grey (Watch fixed); in ZWE the orange appears only to the right of the declaration line; ZMB shows orange from Jan-24
and red (Emergency) from Feb-24 (1 unit), 16-17 units in Mar-May 24, in the middle/west without any declaration gate.

## 5. Pitch numbers (honest; use these)
- Zimbabwe 2023/24: "**26 of 91 districts (29%) were at Watch before the 3 April 2024 declaration, median 15 weeks
  ahead.** Watch fired in only 9-10% of districts in the normal 2019/20 and wet 2020/21 seasons." Do not claim a
  Warning lead in Zimbabwe: **0 of 91 districts** were at Warning before the declaration with realistic data latency;
  the first Warnings (9 districts) came from April data, issued end of April.
- "Zero Warnings in Zimbabwe's wet 2020/21 season; 4 Warning unit-months across all four calm seasons 2019-2023."
- Kenya 2021: "11 of 47 counties (23%) at Warning before the 8 Sep 2021 declaration, median 14 weeks ahead."
- Zambia: "5 of 116 districts at Warning 4 weeks before the 29 Feb 2024 declaration; 42 (36%) by June."
- ZWE vs IPC (ground_truth.md): "Our Warning caught 23 of the 57 districts that moved into IPC3+ in 2023/24 (recall
  40%, precision 74%); persistence manages 35% / 43%." Say also that by Oct 2024 every matched district was IPC3+.
- Do NOT pitch: Malawi, hold-out PR-AUC 0.80-0.84, the superseded 46/91 or 53-of-57 figures (section 7), or any
  "weeks before the declaration" for Zimbabwe Warnings.

## 6. Fixes, ranked by impact
1. **Warning is too slow for a one-season drought.** Vegetation lags rain by 1-2 months, then latency adds one, then the
   2-run step from Watch adds another: a December rain failure cannot show as Warning before March data (issued end of
   March). Options: allow Normal->Warning in one step when two families and p agree (keep 2 runs only for Watch), or
   add an early Warning path when rain AND soil are both strong in Dec-Feb (spec change: rain+soil as independent
   families). Re-check the ZWE west/south-east miss list above after any change.
2. The `held` share (54-64% of Warning months) says the display is mostly hysteresis. Show `held` in the UI ("holding")
   and consider 2 runs down instead of 3 for Warning.
3. **Zimbabwe's driest units are not warned** (driest-10 share 0.20). Inspect Tsholotsho, Hwange, Bulilima, Binga,
   Lupane month by month (`units_ZWE.csv`, risk JS `families`/`p`) to see whether vegetation, p or hysteresis blocks them.
4. Watch still fires in 54-77% of Zambian districts and 79% of Kenyan counties in normal/wet seasons; tune p_watch per
   country or require a family in alarm alongside p for Watch.
5. Score KEN by OND/MAM seasons, not Nov-Mar (judge.py `seasons_climate`).
6. Update `model_report.md` section "Replay check" with the numbers above (it still shows the 16:53 export).

## 7. Superseded numbers (earlier exports, kept for the record)

Judge run 16:45 UTC on the 16:28-16:31 export (no latency, Watch = any family or p >= 0.25, Emergency gated on the
declaration date). These numbers are **no longer valid** and must not be quoted:
- ZWE Warning before declaration: 72/91 (79%) optimistic, 46/91 (51%) next-month-1st, 14/91 (15%) with +5 wk latency.
  ZMB 57 / 45 / 29 of 116; MWI 8 / 6 / 5 of 28; KEN 8 / 8 / 8 of 47.
- Watch fired in 100% of units in every season; 69% of all ZWE unit-months.
- ZWE Spearman Warning months vs NDVI-z -0.73, vs SPI-3 -0.63; driest-10 all warned.
- ZWE vs IPC: 53 of 57 transitions warned (recall 0.93, precision 0.72).
- Old verdict "OK WITH CAVEATS (ZWE and ZMB demo-able)" relied on March/April data being available before 3 April.

Intermediate 16:53 export (latency built in, old hysteresis), as quoted in `model_report.md` 16:58: ZWE 4/91 (4%) Warning
before declaration, median 0.3 wk; ZMB 6/116, 4.0 wk; MWI 2/28, 3.1 wk; KEN 12/47, 14.1 wk; ZWE IPC transition precision
0.705 / recall 0.544. Superseded by the 17:03 export judged above.
