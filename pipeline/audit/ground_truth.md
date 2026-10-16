# Ground truth: our alerts vs FEWS NET IPC (Zimbabwe, Malawi)

Validator run 2026-10-16 ~17:10 UTC on the **latency-aware export**: `data/risk/ZWE.js` (`generated_at`
2026-10-16T17:03:01Z) and `data/risk/MWI.js` (17:03:39Z), model_version `sat-v1-ensemble-ZWE_KEN_MWI_ZMB`,
thresholds p_watch 0.525 / p_warn 0.50 / p_emerg 0.95 / p_fast 0.775. Levels for month t are issued at the end of
month t from data of month t-1 (`meta.issue_convention`), so **data latency is now inside the numbers below**; the
"subtract 4-6 weeks" caveat of the earlier run no longer applies.
Re-run: `python -I pipeline/audit/fetch_ipc.py ZWE MWI ZMB KEN`, then `python -I pipeline/audit/compare_ipc.py ZWE MWI`.
Full numbers: `pipeline/audit/out/metrics_{ZWE,MWI}.json`, per unit/season: `pipeline/audit/out/units_{ZWE,MWI}.csv`.

## Truth data
- Source: FEWS NET Data Warehouse, `https://fdw.fews.net/api/ipcphase/?country_code=ZW&format=csv`
  (anonymous, data_usage_policy=Public). Paged JSON gets HTTP 403 after ~2 pages, so we take the bulk CSV.
  Raw copy + sha256: `pipeline/cache/ipc_raw/<ISO3>/`.
- Kept scenarios CS (current), ML1 (near-term), ML2 (medium-term), projection_start 2016-2024:
  `pipeline/data/ipc_ZWE.parquet` 32,454 rows; MWI 15,111; KEN 115,458; ZMB 1,572.
- **ZMB has no FEWS NET IPC after 2017-10** -> no ground truth for Zambia 2023/24.
- Zimbabwe CS maps exist only 3x per year (Feb, Jun, Oct). 2023/24 snapshots: 2023-10, 2024-02,
  2024-06, 2024-10. So "first IPC3+" is known only to a 4-month bin.

## Unit mapping (method + match rate)
- FEWS NET units are `fsc_admin_lhz` = livelihood zone x district pieces, nested inside one district.
  Full name is "<LHZ>, <District>, <Province>, Zimbabwe" -> we take the district element and match it to
  our geoBoundaries ADM2 name (exact; else drop "Rural/Urban" suffix; 3 aliases: Centenary ->
  Centenary/ Muzarabani, Shurugwi Urban -> Shurugwi Town, Harare Urban -> Harare).
- No area overlay: geopandas/shapely are not in the venv and the pieces are nested in districts anyway.
  District phase = **max over its LHZ pieces** ("any part of the district in IPC3+"). This is generous to
  IPC3+ (no area weighting).
- ZWE match: **84 of 91** our units; 84 of 84 FEWS districts. Unmatched (no truth, left missing):
  Harare Rural, Hwange Urban, Kariba Urban, Marondera Urban, Mvurwi, Plumtree, Redcliff.
- MWI match: 28 of 28 our units; 28 of 32 FEWS units (the 4 city units Blantyre/Lilongwe/Mzuzu/Zomba City have no ADM2 match).

## Definitions
- Season y = planted Oct-Dec y. Impact window = CS Feb, Jun, Oct of y+1. Alert window = Oct y .. Jun y+1.
- Transition = district below IPC3 at the Oct-y snapshot and IPC3+ in the impact window.
  Districts already IPC3+ in Oct y count as negatives (so precision is conservative).
- Warning+ = level >= 2 in the alert window. Lead = first IPC3+ snapshot month minus first Warning month.
- Persistence baseline = "IPC3+ this season iff IPC3+ last season".
- FEWS NET benchmark = first monthly report (ML1/ML2, by reporting_date) projecting IPC3+ for the district.

## Results, Zimbabwe 2023/24 (replay season)
- 57 of 84 districts moved into IPC3+ (42 districts first IPC3+ at Feb 2024 incl. 27 already IPC3+ in Oct 2023;
  of the 57 transitions: 15 at Feb 2024, 3 at Jun 2024, 39 at Oct 2024). By Oct 2024 **every** matched district
  was IPC3+, so this season cannot measure false alarms on calm districts; it measures timing and coverage.
- Warning+ vs transitions: **precision 0.742, recall 0.404** (TP 23, FP 8, FN 34, TN 19).
  All 8 "FP" are districts already IPC3+ in Oct 2023 (27 such districts; we warned 8).
  Persistence: precision 0.426, recall 0.351. FEWS NET's own projections: precision 0.679, recall 1.0
  (they projected IPC3+ for every district, 27 of them already in Jun 2023).
- 33 districts reached Warning by June 2024. First Warning month among the 23 hits: Apr-24 8, May-24 12, Jun-24 3.
  **None before the 2024-04-03 declaration** (April data is issued end of April).
- Missed (34 FN, 32 of them Watch only): including Beitbridge, Mbire, Mutoko, Uzumba Maramba Pfungwe, Rushinga,
  Mount Darwin, Centenary/Muzarabani, Mutasa, Umguza (all IPC3+ from Feb 2024).
- Watch vs transitions: precision 0.688, recall 0.965 (TP 55, FP 25, FN 2). Precision equals the season base rate
  (57/84 = 0.679), so Watch adds nothing *within* this season; across seasons it does (below).
- Lead to first IPC3+ snapshot (23 hits): median 21.7 weeks (range -17.4 to 26.1), inflated by the 4-month
  bins and by 17 of the 23 hits whose first IPC3+ map is Oct 2024. **Conservative lead** (onset assumed just
  after the previous snapshot, i.e. minus 17.4 wk): median **4.3 weeks**, positive for 65% of hits.
- vs FEWS NET's own projections: our first Warning came a median **4.3 weeks earlier**, earlier for 52% of the 23
  hits (FEWS projected IPC3+ for 27 districts in Jun 2023, 15 in Oct 2023, then 7 in May and 35 in Jun 2024).

## Results, Zimbabwe, all seasons 2019/20 - 2023/24 (420 district-seasons)
| target | ours (Warning+) P / R / F1 | ours (Watch+) P / R / F1 | persistence P / R / F1 |
|---|---|---|---|
| IPC3+ transition (141 events) | 0.711 / 0.191 / 0.302 | 0.479 / 0.738 / 0.581 | 0.238 / 0.440 / 0.308 |
| IPC3+ anywhere in window (285 positives) | 0.947 / 0.126 / 0.223 | n/a | 0.789 / 0.723 / 0.755 |

- By season (transition F1, Warning+): 2019/20 0.150 (35 transitions, 5 warned), 2020/21 no events and no
  warnings, 2021/22 0.042 (47 transitions, 1 warned), 2022/23 2 transitions, 0 hits, 2 warned districts, 2023/24 0.523.
- Warning is now **precise but rare**: 41 district-seasons warned in five seasons, 27 of them true transitions.
  Watch base rate across seasons is 0.336; Watch precision 0.479 is above it (it was equal to it in the earlier export).
- Persistence wins on "is the district in crisis at all": much of Zimbabwe IPC3+ is chronic or
  economic (prices, currency), which a satellite + weather model cannot see.

## Results, Malawi (28 districts, 140 district-seasons)
- 2023/24: 4 transitions, 4 warned districts; Warning+ precision 0.5, recall 0.5 (TP 2 Mchinji, Ntcheu); persistence
  0.158 / 0.75. Lead to first IPC3+ (2 hits): 17.4 and 34.8 weeks (4-month bins). 18 of 28 districts were IPC3+ in the
  window; Warning recall on that target 0.167 vs persistence 0.944.
- All seasons: Warning+ transition P/R 0.10 / 0.08 (2 of 25 transitions hit, 18 false alarms, mostly 2019/20 and
  2021/22); persistence 0.07 / 0.12. Malawi is not scorable in our favour on any target.

## Honest caveats
1. One drought season decides the Zimbabwe headline; base rate ~100% IPC3+ by Oct 2024.
2. CS truth is 3 maps a year; lead times are in 4-month bins.
3. Data latency (1 month: CHIRPS, MODIS, ERA5-Land) is now modelled in the export; no further subtraction is needed.
   The cost is visible: recall on 2023/24 transitions fell from 0.93 (no latency, earlier export) to 0.40 because
   most of the earlier skill came from March/April data that is not available before early April.
4. FEWS NET `reporting_date` is used as the projection issue date; real publication can be a few weeks later.
5. District = max over LHZ pieces (no area weighting); 7 small/urban ZWE units have no truth.
6. IPC3+ is food insecurity from any cause; our model only sees drought.

## Pitch takeaway
In the 2023/24 drought our satellite+weather Warning, issued with realistic one-month data latency, caught 23 of the
57 Zimbabwe districts that later went into IPC Phase 3+ (recall 40%, precision 74%; persistence 35% / 43%), but none
of them before the national declaration of 3 April 2024. Watch covered 55 of 57 (97%) and was raised in 26 districts
a median 15 weeks before the declaration (judge/verdict.md). Say "Watch early, Warning confirms", not "Warning early".

## Superseded (earlier run, 16:28 export without data latency; do not quote)
- 2023/24 Warning+ vs transitions: precision 0.716, recall 0.930 (TP 53, FP 21, FN 4); 72 of 80 warned districts
  before the declaration, median 4.7 weeks; conservative lead 8.7 weeks; 8.7 weeks earlier than FEWS NET projections.
- All seasons Warning+ transition P/R/F1 0.466 / 0.539 / 0.500; IPC3+ anywhere 0.816 / 0.467 / 0.594.
- Watch fired in all 84 districts in every season (precision = base rate 0.336).
- `model_report.md` (16:58) quotes an intermediate 16:53 export: precision 0.705, recall 0.544 (TP 31, FP 13, FN 26),
  all-seasons 0.526 / 0.284. Also superseded by the 17:03 export above.
