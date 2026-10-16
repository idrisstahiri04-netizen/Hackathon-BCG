# Ground truth: our alerts vs FEWS NET IPC (Zimbabwe)

Validator run 2026-10-16 (UTC) on `data/risk/ZWE.js`, model_version `sat-v1-ensemble-ZWE_KEN_MWI_ZMB`
(generated 16:28 UTC). Re-run: `python -I pipeline/audit/fetch_ipc.py ZWE MWI ZMB KEN`, then
`python -I pipeline/audit/compare_ipc.py ZWE`. Full numbers: `pipeline/audit/out/metrics_ZWE.json`,
per unit/season: `pipeline/audit/out/units_ZWE.csv`.

## Truth data
- Source: FEWS NET Data Warehouse, `https://fdw.fews.net/api/ipcphase/?country_code=ZW&format=csv`
  (anonymous, data_usage_policy=Public). Paged JSON gets HTTP 403 after ~2 pages, so we take the bulk CSV.
  Raw copy + sha256: `pipeline/cache/ipc_raw/<ISO3>/`.
- Kept scenarios CS (current), ML1 (near-term), ML2 (medium-term), projection_start 2016-2024:
  `pipeline/data/ipc_ZWE.parquet` 32,454 rows; MWI 15,111; KEN 115,458; ZMB 1,572.
- **ZMB has no FEWS NET IPC after 2017-10** -> no ground truth for Zambia 2023/24.
  MWI has data, but `data/risk/MWI.js` was still STUB at run time -> not scored.
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
- Match: **84 of 91** our units; 84 of 84 FEWS districts. Unmatched (no truth, left missing):
  Harare Rural, Hwange Urban, Kariba Urban, Marondera Urban, Mvurwi, Plumtree, Redcliff.

## Definitions
- Season y = planted Oct-Dec y. Impact window = CS Feb, Jun, Oct of y+1. Alert window = Oct y .. Jun y+1.
- Transition = district below IPC3 at the Oct-y snapshot and IPC3+ in the impact window.
  Districts already IPC3+ in Oct y count as negatives (so precision is conservative).
- Warning+ = level >= 2 in the alert window. Lead = first IPC3+ snapshot month minus first Warning month.
- Persistence baseline = "IPC3+ this season iff IPC3+ last season".
- FEWS NET benchmark = first monthly report (ML1/ML2, by reporting_date) projecting IPC3+ for the district.

## Results, 2023/24 (replay season)
- 57 of 84 districts moved into IPC3+ (15 at Feb 2024, 3 at Jun 2024, 39 at Oct 2024).
  By Oct 2024 **every** matched district was IPC3+, so this season cannot measure false alarms on
  calm districts; it measures timing and coverage.
- Warning+ vs transitions: **precision 0.716, recall 0.930** (TP 53, FP 21, FN 4, TN 6).
  All 21 "FP" are districts already IPC3+ in Oct 2023 (27 such districts; we warned 21).
  Persistence: precision 0.426, recall 0.351.
- Missed (Watch only): Uzumba Maramba Pfungwe, Beitbridge (both IPC3+ from Feb 2024), Chipinge Urban,
  Kwekwe Urban.
- First Warning month (transition districts): Dec-23 4, Feb-24 3, Mar-24 24, Apr-24 18, May-24 3, Jun-24 1.
  72 of 80 warned districts got Warning before the 2024-04-03 declaration (median 4.7 weeks before).
- Lead to first IPC3+ snapshot: median 26.1 weeks (range -13 to 43.5), but inflated by the 4-month
  bins and by 39 districts whose first IPC3+ map is Oct 2024. **Conservative lead** (onset assumed just
  after the previous snapshot): median **8.7 weeks**, positive for 70% of hits.
- vs FEWS NET's own projections: our first Warning came a median **8.7 weeks earlier**, earlier for
  72% of the 53 hits (FEWS projected IPC3+ for 15 districts in Oct 2023, then 7 in May and 35 in Jun 2024).
- Watch is not informative: it fires in all 84 districts in Oct-Dec 2023 (and in every district in
  every season 2019-2024, all-season Watch precision 0.336 = base rate).

## Results, all seasons 2019/20 - 2023/24 (420 district-seasons)
| target | ours (Warning+) P / R / F1 | persistence P / R / F1 |
|---|---|---|
| IPC3+ transition (141 events) | 0.466 / 0.539 / 0.500 | 0.238 / 0.440 / 0.308 |
| IPC3+ anywhere in window (285 positives) | 0.816 / 0.467 / 0.594 | 0.789 / 0.723 / 0.755 |

- By season (transition F1): 2019/20 0.424, 2020/21 no events and no warnings, 2021/22 0.175
  (47 transitions, only 10 warnings), 2022/23 2 transitions, 0 hits, 29 warned districts with no transition.
- Persistence wins on "is the district in crisis at all": much of Zimbabwe IPC3+ is chronic or
  economic (prices, currency), which a satellite + weather model cannot see.

## Honest caveats
1. One drought season decides the headline; base rate ~100% IPC3+ by Oct 2024.
2. CS truth is 3 maps a year; lead times are in 4-month bins.
3. Data latency is not modelled (methodology.md B2): satellite month r is available ~4-6 weeks later.
   Subtracting that, the conservative lead and the edge over FEWS NET projections shrink from 8.7 to
   roughly 3-5 weeks (8.7 minus 4-6; arithmetic, not re-scored with an issue date yet).
4. FEWS NET `reporting_date` is used as the projection issue date; real publication can be a few weeks later.
5. District = max over LHZ pieces (no area weighting); 7 small/urban units have no truth.
6. IPC3+ is food insecurity from any cause; our model only sees drought.

## Pitch takeaway
In the 2023/24 drought our satellite+weather Warning caught 53 of the 57 Zimbabwe districts that later
went into IPC Phase 3+ (recall 93% vs 35% for persistence), mostly before the national declaration,
but it says nothing about non-drought crises, and with data latency counted the lead time is weeks, not months.
