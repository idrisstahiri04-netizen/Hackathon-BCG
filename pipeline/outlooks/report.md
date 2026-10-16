# Official-outlook signal (FEWS NET text) — build report

Built 2026-10-16 on branch `zimbabwe-real-data`. Nothing committed. Files:

| file | what |
|---|---|
| `pipeline/outlooks/fetch.py` | downloads FEWS NET Outlook / Outlook Update / Key Message Update pages by URL pattern, keeps raw HTML + cleaned text + `_meta.json` (url, sha256, fetched_at, **publication_date from the page's dataLayer**), manifest CSV incl. 404s |
| `pipeline/outlooks/extract.py` | Claude extraction (strict JSON schema), evidence-span verification, gazetteer match, writes `pipeline/data/outlook_<ISO3>.parquet` |
| `pipeline/outlooks/value_test.py` | lead-time / false-alarm test vs `data/risk/ZWE.js` and the 2024-04-03 declaration -> `value_test_ZWE.json` |
| `pipeline/outlooks/spot_check.py` | prints a seeded 10 % sample with document context for human review |
| `pipeline/data/raw_outlooks/` (gitignored, 37 MB) | raw pages, `manifest.csv`, `extractions/<doc>.json` (raw LLM output + token usage) |

## 1. Corpus fetched

URL pattern `https://fews.net/<region>/<country>/<report-type>/<month>-<year>`, 2015-06..2024-06, 4 report types, 4 countries = 1,744 URLs tried. FEWS NET returns a real 404 for missing months (the dataLayer `entityBundle` is checked as a soft-404 guard anyway). robots.txt allows these paths; 4 workers, 0.3 s pause; 8 URLs stayed 403 after retry (1 ZWE: KMU 2018-01).

| country | pages | outlooks | updates | key-message updates | notes |
|---|---|---|---|---|---|
| ZWE | **115** | 32 | 31 | 52 | 105 distinct publish months; gaps only 2018-01 (403), 2018-11, 2020-08, 2024-02*, 2024-06 |
| MWI | 114 | 29 | 29 | 56 | |
| KEN | 110 | | | | fetched, not extracted |
| ZMB | 31 (+2 remote-monitoring) | 7 | 9 | 13 | pages exist only 2015-2017; **none in the 2023/24 window** |

\* the "February 2024" outlook carries publication date **2024-03-01**, so under the leakage rule it is a March signal. This matters: it is the document that first projects Crisis continuing *after* the 2024 harvest.

Publication dates are month-end (e.g. 2023-10-31), so a publish-month-r document is usable only by the end-of-month run of r.

## 2. Extraction

Model `claude-sonnet-5-5`, `output_config.format` JSON schema, effort medium. A document fails if JSON is invalid or >50 % of its evidence spans are not found verbatim (whitespace/quote-normalised) in the page text; two failures would escalate to `claude-opus-5-5`. **No document failed; Opus was never used.** Spans that fail verification are dropped individually: 0 of 709 (ZWE).

ZWE: 114 docs -> **709 statements** (531 projections, 178 current). Phase given in 690 (IPC 2: 317, IPC 3: 235, IPC 1: 105, IPC 4: 33). Rain outlook stated in 358 (below 210, above 88, normal 43, mixed 17). Mean self-reported confidence 0.74.

**Area granularity is the real limitation.** FEWS NET Zimbabwe text names areas as: descriptor 596 (84 %) - "typical deficit-producing areas in the south, west and extreme north", "communal parts of the surplus-producing areas", "urban areas"; national 40; **district 31 (19 distinct districts, mostly 2019 and 2022)**; province 29; livelihood zone 13 (the "areas of concern").

Gazetteer (`units_ZWE.geojson` names + aliases; province->districts and livelihood-zone->districts derived from FEWS NET's own FDW unit names in `ipc_ZWE.parquet`): district/province/LZ matches -> 1,745 rows; national -> 9,009 rows (all 91 units, flagged, excluded from the test); **descriptor_map** -> 51,152 rows. `descriptor_map` is a static, reviewed mapping of the three recurring descriptors to livelihood zones (natural regions IV-V = "deficit", highveld = "surplus", "Urban"). It is coarse: because LZ x district intersections touch many districts, "deficit" expands to 59 of 91 units and "surplus" to 48. 318 statements stay unmatched (`outlook_ZWE_unmatched.csv`). Free text is never fuzzy-matched to a district.

Spot check (seed 7, 71 statements = 10 %, `spot_check.py`): 71/71 quotes verbatim; 0 phase errors where a phase is stated; **7 attribution/granularity problems**: 3 statements labelled `national` where the text says "parts of the country"; 1 list of four provinces collapsed to one province match; 1 list of 7 named districts ("Mutare, Buhera, Bikita, Mudzi, Mangwe, Umzingwane, Hwange") labelled `descriptor` and therefore unmatched; 1 "Stressed and Crisis" recorded as phase 2; 1 severity 2 inferred for Chipinge from "hardest hit" (Cyclone Idai) with no phase. About 9 further quotes do not contain the area name (attribution relies on surrounding sentences; confidence 0.6-0.75). Fix list: split multi-area lists into one statement per area; forbid `national` unless the text says country-wide.

## 3. Value test, Zimbabwe (`value_test_ZWE.json`)

Alert definitions per unit and publish month: *text Crisis* = projected_severity >= 2 projection for a target month in the season (Oct-Jun); *below-rain* = rain_outlook "below"; *post-harvest Crisis* = Crisis projected for Apr-Jun. Model = `data/risk/ZWE.js` levels (Watch >= 1, Warning >= 2). Urban statements excluded.

### 2023/24 (declaration 2024-04-03)
Model: first Watch in 88/91 units, but 42 of them only in 2024-04 and 14 in 2024-05; 31 units before April; Warning in 34 units, 32 of them Apr-Jun 2024. Median model lead vs declaration: **0 months**.

| variant | units | first text-Crisis | lead vs model Watch (median, same units) | lead vs declaration |
|---|---|---|---|---|
| gazetteer only (LZ/province/district) | 29 | 2023-06: 1 (Bulilima), **2023-10: 20**, 2024-03: 8 | +6 months (text earlier in 69 %) | median 6, range 1-10 |
| + descriptor_map | 59 | **2023-06: 59** | +10 months (earlier in 91 %) | 10 |

The 20 units flagged in Oct 2023 come from two livelihood-zone "areas of concern" (Kariba Valley Kariangwe-Jambezi: Binga, Hwange, Kariba; Masvingo-Manicaland Middleveld Smallholder: Bikita, Buhera, Chimanimani, Chirumhanzu, Chivi, Gutu, Masvingo, Mutare, Shurugwi, Zaka, Zvishavane...), quoting e.g. *"From February to May 2024, the peak of the lean season will occur between February and March, with food gaps expected to increase, driving Crisis (IPC Phase 3) outcomes."* Our model put 16 of those 20 units on Watch only in Apr-Jun 2024.

National rain outlook extracted by publish month: Jun-23 mixed, **Jul-23 below**, Aug below, Sep below, Oct below, Dec below, Mar-24 below. So the El Nino below-normal signal was in the text from **July 2023**, nine months before the declaration.

### Non-drought years (false alarms)
| season | model Watch units | text Crisis units (gaz / +desc) | below-rain units (gaz / +desc) | post-harvest Crisis (gaz / +desc) |
|---|---|---|---|---|
| 2020/21 good rains | 57 | 18 / 60 | **0 / 0** | **0 / 0** |
| 2021/22 mixed, late start | 58 | 9 / 60 | 0 / 76 (Dec-21) | 0 / 0 |
| 2022/23 good rains | 25 | 18 / 59 | 0 / 76 (Sep-22, Jan-23) | 0 / 0 |
| 2018/19 drought | 52 | 13 / 67 | 13 / 80 | 13 / 13 |
| 2015/16 El Nino drought | 0 (model has no Watch) | 23 / 23 | 30 / 71 | 15 / 15 |

Honest reading:
1. **"Crisis projected" alone is not a drought signal in Zimbabwe.** FEWS NET projects Crisis for the chronic deficit zones every lean season, drought or not (18-60 units in each good year). Used as a Watch trigger it would fire every year.
2. **Rain outlook "below" via the gazetteer is drought-specific** (0 units in all three non-drought seasons; 29-30 units in 2015/16 and 2023/24) and arrives 6 months before the declaration - but covers only the ~30 districts FEWS NET names via livelihood zones. The descriptor-map version reaches 59-76 units and arrives in June 2023, but false-alarms in 2021/22 and 2022/23 (SARCOF/MSD "normal-to-below" seasons that turned out fine).
3. **Post-harvest Crisis** (Crisis still expected Apr-Jun) is the cleanest discriminator (0 false alarms, present in all three drought years), but it appears only in the February outlook, published 2024-03-01 - one month before the declaration and *after* 20 of the model's first Watches. Our model is not slower than this signal; it is slower than the rainfall-outlook signal.
4. The spec rule "text alone can raise at most Watch" is right here: text gives early, low-resolution Watch; satellite confirms per district.

Recommendation for fusion: use `rain_outlook == below` (gazetteer rows, plus descriptor_map at reduced weight) as an official_text family signal for Watch from the July-October issue months; use post-harvest Crisis as a Warning confirmer; ignore lean-season Crisis projections unless they are *earlier than usual* (e.g. Crisis emerging Aug/Sep instead of Oct - the May and July 2023 KMUs say exactly this).

Cross-check available for free: `pipeline/data/ipc_ZWE.parquet` (FEWS NET FDW ipcphase) already holds these same projections numerically per admin2 x LZ with projection windows since 2015 - the structured version of what the LLM reads. The LLM route adds the rainfall outlook, drivers and evidence quotes, and works for sources without a data warehouse (MSD/SARCOF forecasts, government statements).

Malawi (13 docs, 2023-06..2024-06): 130 statements, 0 bad spans, 129/130 matched (Malawi text names districts and provinces: province 2,102 rows, district 302, LZ 209, national 140). Not yet tested against the MWI model. Zambia: no pages in window.

## 4. Cost

| run | docs | input tok | output tok | USD (Sonnet $2/$10 per M) |
|---|---|---|---|---|
| ZWE 2015-06..2024-06 | 114 | 626,151 | 142,310 | **$2.68** (about $0.024/doc; 5.5k in / 1.2k out per doc) |
| MWI 2023-06..2024-06 | 13 | 81,584 | 27,862 | $0.44 |
| failed schema test run (schema used `minimum`/`maximum`, rejected 400) | 9 calls | 0 | 0 | $0 |

Total spent about $3.1. Full MWI+KEN back to 2015 would be about $5.5 more. Fetching is free (HTTP only, ~7 min for 1,744 URLs). Wall time: ZWE extraction with 4 workers about 4 min.

## 5. Known gaps
- 8 pages 403 (1 ZWE); the `report-search` listing is bot-challenged so months with unusual slugs could be missed (all 2023-06..2024-06 ZWE months are present except the Feb->Mar date shift).
- KEN fetched but not extracted; KEN gazetteer is ADM1 while FDW names old districts - needs a district->county map before use.
- `descriptor_map` is my mapping (listed in `extract.py`), not FEWS NET's; review before using in the demo.
- `pipeline/data/outlook_ZWE.parquet` has 61,906 rows because national and descriptor_map rows are expanded to every unit x target month; filter on `match_type` before joining to `signal_observation`.
