# SMS Shortage Early Warning — prototype

A clickable MVP: a searchable globe of Kenya at **sub-county resolution**, every
area coloured by its **real FEWS NET IPC classification**, an alert feed that
says who to tell and what to do, and a timeline that steps through real FEWS NET
releases.

Countries: **Zimbabwe** (91 districts, main replay: 2023–24 El Niño drought,
disaster declared 3 Apr 2024), **Malawi** (28 districts, 23 Mar 2024),
**Zambia** (116 districts, 29 Feb 2024) and **Kenya** (47 counties, 8 Sep 2021).
**Only real data is shown.** There is no simulated fallback: a country is
`LIVE` only when the risk model has published real output for it; until then
it is listed as `DATA IN PROGRESS` and nothing is drawn.

### Data flow

```
pipeline/prep_geo.py --iso3 ZWE   -> data/geo/ZWE.js   (GEO_DATA["ZWE"], CONTRACT.md §2)
risk model (pipeline)             -> data/risk/ZWE.js  (RISK_DATA["ZWE"], CONTRACT.md §3)
pipeline/make_stub_risk.py        -> data/risk/*.js    placeholder (model_version "STUB") until the model runs
```

`index.html` loads `data/geo/<ISO3>.js` and `data/risk/<ISO3>.js` for ZWE, KEN,
MWI, ZMB, then starts `js/app.js`. A country is `LIVE` when its geometry loaded
**and** `RISK_DATA[iso3].meta.model_version` is not `STUB`. Stub files
(`make_stub_risk.py`, for pipeline/dev work only) are never displayed; the
country shows `DATA IN PROGRESS`. All four countries now have real output
(`pipeline/export_risk.py`). Live countries show
"Real satellite + weather data (CHIRPS, MODIS, ERA5). Risk levels from our model."

```bash
python3 pipeline/prep_geo.py --iso3 ZWE KEN MWI ZMB   # geometry
python3 pipeline/make_stub_risk.py --iso3 ZWE KEN      # dev stubs (never shown)
```

`make_stub_risk.py` never overwrites a risk file whose `model_version` is not
`STUB`, so re-running it after the model has written real output is safe.

## Run it

```bash
python3 serve.py
```

Then open <http://localhost:8777>. Use `serve.py`, not `python3 -m http.server` —
it also proxies the FEWS NET live feed.

## What you get

| | |
|---|---|
| **Resolution** | 290 sub-counties (288 with FEWS NET data), or 47 counties |
| **Timeline** | 18 real FEWS NET releases, Feb 2019 → Oct 2024 |
| **Observations** | 5,184 published IPC classifications |
| **Projections** | 19,584 of FEWS NET's own near-term forecasts |
| **Events** | 500 real reclassifications |
| **Live mode** | Current FEWS NET situation, re-pullable on demand |

## Observed vs forecast — what the colours mean

**The default view is the observed current situation, not a prediction.** That
was previously ambiguous, so the UI now says so explicitly and lets you switch.

The `Showing` control in the timeline footer selects what the map colours:

| View | Scenario | Horizon | Source |
|---|---|---|---|
| **Now** | `CS` Current Situation | observed, 0–1 months | FEWS NET |
| **+1.5 mo** | `ML1` Near-Term Projection | median **1.5** months ahead (0–4) | FEWS NET |
| **+5 mo** | `ML2` Medium-Term Projection | median **5.0** months ahead (1–8) | FEWS NET |

Those horizons are **measured from the data**, not assumed — each record's
`projection_start`/`projection_end` against its `reporting_date`. All three
scenarios exist for all 290 sub-counties.

Every forecast on screen is **FEWS NET's own**. We do not predict anything.

### How the difference is visible

- **The headline contrast is always on screen.** Even on the observed view the
  HUD reads e.g. *"16 units at Crisis+ now · 46 forecast at Crisis+ +1.5 mo"*.
  That gap is the product.
- **A trajectory strip** — `P2 ▲ P3 → P3` with Now / +1.5 mo / +5 mo labelled —
  appears in the marker hover card and the detail panel. The active horizon is
  highlighted, and arrows carry the direction of change.
- **Areas forecast to deteriorate get a second, dashed rotating ring** on their
  marker, and sort to the top of the marker list. Those are the areas early
  warning exists for.
- **A forecast view looks different**: violet tint on the scrim and legend, and
  the legend title changes to "forecast +1.5 mo".
- **Missing projections are marked, not filled.** If FEWS NET published no
  projection for a unit, the trajectory shows `–` rather than silently
  repeating the observed value.

A good demo moment is **Jun 2021** (`t=28`): 16 sub-counties observed at
Crisis, 46 forecast at Crisis within six weeks, 30 of them forecast to
deteriorate.

Live mode carries only `CS` and `ML1`, so **+5 mo is disabled there** rather
than falling back to a shorter forecast dressed up as a longer one.

## Sign in as a role

The app opens on a role picker — **Food bank / NGO** or **Government entity**.
This is not authentication; it decides which decision you are being helped with,
and the recommendations are genuinely different, not relabelled:

| | Food bank / NGO | Government entity |
|---|---|---|
| Framing | "Buy and pre-position for Mwingi West this month, before the price peak." | "Mwingi West has crossed the reserve-release threshold." |
| Levers | procurement timing, branch stock, cash vs food, distribution | NCPB reserve release, duty waivers, declarations, extension deployment |
| At Emergency | "needs relief distribution now, not procurement" | "a declaration decision is live" |

Switch role any time from the badge in the feed header.

## The pulsing markers

Areas at IPC Phase 3+ get a pulsing marker — red and blinking at Phase 4+.
Hover one and a card appears above it with:

- what crops or livestock are at risk, from that area's real FEWS NET
  livelihood zones
- the next steps **for your role**
- which real body can act (NDMA, NCPB, KALRO, HSNP, Kenya Red Cross, WFP)
- where help does **not** reach — e.g. counties outside the 8 HSNP counties are
  told so explicitly rather than offered a service they cannot get

Markers cap at 22 so the map stays legible; the overflow count is shown rather
than silently dropped.

## Demo script

1. **Open on the spinning globe.** Search box is focused, the country list is
   already open. Countries with real model output are `LIVE`, the others in
   the pipeline say `DATA IN PROGRESS`, everything else `NO COVERAGE`.
2. **Type Zimbabwe, hit enter.** Districts appear in their Jan 2019 levels
   (not all green: some districts already start at Watch or above). The red
   dashed line on the timeline is the national disaster declaration
   (3 Apr 2024) — the point to beat. The OFFICIAL note stays pinned in the feed.
3. **Press play** (or `space`) and watch which districts turn yellow, then
   orange, before the declaration. That lead time is the product.
4. **Click a red district.** Event type (can't plant / crop failure / no
   grass), drivers, which of the 3 families (rain, vegetation, soil) agree, and
   the SMS each audience would receive, with its GSM-7 septet count (`[`, `]`
   etc. cost 2) and segment count. A level kept only by hysteresis shows
   "held (needs 3 calm months to stand down)" instead of an agreement count.
5. **Click the Farmers or Herders tab.** One GSM-7 segment, an action not a
   probability. Herders get the message when the event is "no grass".
6. **Scrub past the crisis.** Levels stand down slowly (hysteresis: 3 runs).

### Forecast view (the predictions, not just today's level)

The horizon switch under the HUD — **Now | +1 … +8** — turns the map from the
alert levels into a forecast for the month `now + N`, issued at the end of the
month on the slider. The **layer** switch picks what is drawn:

- **Our model** — choropleth of the predicted chance of Crisis (`p_crisis`,
  IPC 3+; falls back to `p` when `p_crisis` is null). Single-hue, light→dark,
  five % bins with the country's Watch threshold as a bin edge. The HUD counts
  districts at or above the threshold and the population in them.
- **FEWS NET outlook** — the projected IPC phase (`fews_phase`, standard IPC
  colours 1–5 with number and name) from the latest outlook published on or
  before the issue month. The HUD counts districts projected at Phase 3+.
- **Both** — our chance as the fill, the FEWS phase on the outline and sides.

The legend is titled *"Forecast issued end of Feb 2024 for May 2024 — using only
data available then"* and lists the bins/phases with counts. `L` cycles the layer.

- **District panel**: headline *"Chance of Crisis by May 2024: 82%"* (or the
  FEWS projected phase in the FEWS layer) plus a chart — past 6 issued months
  (solid), our model +1..+8 (dotted; leads without model output are shaded "no
  model forecast"), the Watch threshold line, and a stepped strip of the FEWS
  NET projected phase per lead with ML1 / ML2 brackets and the publication
  month, so the ~4-month outlook steps are visible.
- **Feed column**: *Top 10 districts most at risk, next 3 months* for the issue
  month on the slider (ranked on the highest chance over +1..+3; click a row to
  fly to the district).
- **Confidence per lead** next to every forecast (horizon buttons, caption,
  legend, panel, Top-10 note). Read from `meta.metrics.forecast_skill`
  (`{"1":{roc_auc|confidence},…}`, "tested skill per lead") when the export has
  it; otherwise the back-test defaults **+1 Medium-High · +2 Medium · +3
  Low-Medium** ("based on back-tests"); leads beyond the tested model show
  *"no model forecast — FEWS NET only"*. From +3 on the view adds *"+N-month
  forecasts show season-level risk; district detail is less certain."* Live
  months (t > 71) with partly-null forecast fields add *"live: some inputs
  missing (see data notes)"*. The FEWS layers add *"How to read: FEWS NET
  outlook updates ~3×/year, so its layer changes in steps; our model updates
  monthly."*
- **Timeline**: when `meta.live_t` is set the slider shows a blue **TODAY** tick
  and a **Go to today** button; `meta.n_months` may exceed 72.
- **Data contract**: `pipeline/CONTRACT.md` §4 / §4b (`forecast: {"1".."8"}`
  per row with `p, p_crisis, fews_phase, fews_scenario, fews_published,
  target_label, source`). Only real fields are shown; missing leads or layers
  say *"pending"*. For leads 1–3 without a `forecast` key the UI derives a
  fallback from the existing real fields only (`p_crisis`, a 1–3 month window,
  so the same number at +1/+2/+3; `p` for +1) and says so. `js/real.js`
  `forecastAt(row, lead)` is the single seam.
- Test: `node tests/e2e/forecast_view.js` (own server on :8601, own Chrome;
  screenshots `tests/e2e/screens/forecast_*.png`).

### Controls

| Input | Action |
|---|---|
| `space` | play / pause (also with the slider focused) |
| `←` `→` | step one month |
| `F` | toggle Now ↔ forecast (last used lead, default +3) |
| `0` … `8` | Now, +1 … +8 months |
| `L` | cycle the forecast layer: our model → FEWS NET outlook → both |
| `esc` | close the county panel |
| click a county | open its detail panel |
| click a notification | jump to that month and fly to that county |
| click a Top-10 row | fly to that district and open its panel |

### Recommendations — the added value

Every alert carries a response block, not just a risk number:

- **What is at risk** — the crops or livestock of that county's *actual* FEWS
  NET livelihood zones. Nyamira (Western High Potential) shows maize, beans,
  tea, sugarcane, dairy. Turkana (Northwestern Pastoral + Lake Turkana Fishing)
  shows goats, camels, cattle, tilapia, Nile perch.
- **Do now** — actions matched to that livelihood and level. You destock a
  pastoral county and re-seed a marginal one; those are different instructions
  and the system never confuses them.
- **Resources** — real Kenyan programmes with real eligibility: HSNP cash
  transfer (8 counties only), NDMA County Drought Coordinator, NCPB strategic
  grain reserve, KALRO drought-tolerant seed, county livestock offtake, Kenya
  Red Cross, WFP anticipatory action.
- **Gaps** — where help does *not* reach. A county outside HSNP is told so
  explicitly rather than being offered a service it cannot get.

The farmer SMS action is also livelihood-matched, so a Turkana herder is told
"Sell weak stock now while prices hold" and a Kitui farmer "Plant green gram or
cowpea, keep 2 months grain".

See `js/advice.js`. Livelihood zones come from `data/kenya-livelihoods.json`,
parsed out of FEWS NET's own unit names — they are not our invention. The
mapping from zone to crops, and the action text, are ours.

### Deep links (stage insurance)

If dragging the slider in front of an audience goes wrong, reload straight into
a moment:

```
?country=Zimbabwe&t=63                   # Apr 2024, Zimbabwe declaration month
?country=Zimbabwe&t=63&county=Binga      # district detail (name match, case-insensitive)
?country=Zimbabwe&t=61&view=f3           # Feb 2024, forecast for May 2024 (view = now | f1 … f8)
?country=Zimbabwe&t=57&view=f6&layer=both # Oct 2023, +6 months, our chance + FEWS NET phase outline
?country=Kenya&t=26                      # Mar 2021, drought spreading
?country=Kenya&t=33&county=Marsabit      # Oct 2021, just after the declaration
?country=Kenya&t=48&county=Turkana       # Jan 2023, peak crisis
```

`t` is an index into the 18 real FEWS NET releases (0 = Feb 2019, 17 = Oct 2024).
`tip=1` opens the hover card on the worst-affected area without needing a mouse —
stage insurance. `tip=<Sub-county>` opens a specific one.

## What is real and what is not

| Part | Status |
|---|---|
| Boundaries (ZWE/MWI/ZMB ADM2, KEN ADM1) | **Real.** geoBoundaries gbOpen, simplified for the browser |
| Kenya county populations / crop share | **Real**, 2019 census (from `prep_data.py`) |
| Declaration dates | **Real**, sources in `pipeline/CONTRACT.md` |
| Risk levels, SPI, NDVI, soil | **Real model output** from `data/risk/<ISO3>.js`. A `STUB` file is never displayed |
| SMS text | Generated from the templates in the spec |

The data note is on screen whenever a country is live. Probabilities are
model estimates, not measurements — say so on stage.

## Layout of the code

```
index.html              markup for the three regions
css/app.css             all styling; design tokens at the top
js/real.js              engine over RISK_DATA (real pipeline output), herder audience, SMS text
js/app.js               globe, search, timeline, feed, detail panel (multi-country)
data/geo/<ISO3>.js      generated by pipeline/prep_geo.py; do not hand-edit
data/risk/<ISO3>.js     written by the risk model (or make_stub_risk.py)
data/kenya-counties.js  legacy Kenya geometry (no longer loaded)
vendor/                 globe.gl + earth textures, vendored for offline use
```

### The engine is the seam

Everything else talks to it through one shape: a risk assessment per
`(county, month)` carrying `level`, `p`, `confidence`, `agreeing`, `drivers`
and the raw signals. `js/real.js` exposes the same API over `RISK_DATA`, adds
the event type (can't plant / crop failure / no grass) and a **herder**
audience (sent instead of farmers when the event is no grass). Real data
counts 3 families (rain, vegetation, soil; heat is supporting only).

The engine already implements the parts of the spec that are design decisions
rather than data:

- **Hysteresis.** A level must hold 2 consecutive runs to escalate, 3 to stand
  down, so one cloudy month cannot flip a county red and back.
- **Two-family rule.** Level 2+ requires two or more *independent* source
  families to agree.
- **Announcements can never exceed level 1 alone.** An official statement
  confirms satellite and price evidence; it cannot manufacture an alert.
- **Audience routing.** Level 1 goes to institutions only. Farmers are not
  messaged until level 2 — alert fatigue is what kills these systems.
- **Farmers get an action, never a probability.** A public forecast moves the
  market and can cause the shortage it predicts.

### Regenerating the geometry

```bash
python3 pipeline/prep_geo.py --iso3 ZWE KEN MWI ZMB   # -> data/geo/<ISO3>.js
python3 prep_data.py      # legacy: ken_raw.geojson -> data/kenya-counties.js (unused by the app)
```

841 KB of raw boundaries down to 46 KB. One non-obvious step: it reverses the
ring winding. `three-globe` triangulates polygon caps on the sphere and wants
exterior rings **clockwise** — the opposite of the GeoJSON right-hand rule that
geoBoundaries ships. Get it backwards and a single county paints the entire
globe.

## Colour

The four risk levels use the validated status ramp:

| Level | Colour | |
|---|---|---|
| 0 Normal | `#0ca30c` | green |
| 1 Watch | `#ffd43b` | yellow |
| 2 Warning | `#ec833a` | orange |
| 3 Emergency | `#d03b3b` | red |

Checked against the dark surface `#1a1a19` for colour-blind separation,
normal-vision separation and 3:1 contrast. Because colour alone is never enough,
every level also carries its number, its name and a glyph — on the map legend,
on every notification chip and in the detail panel.

## Country coverage — why only Kenya

The pipeline is country-agnostic; the *data* is not. Everything here rests on
FEWS NET publishing IPC classifications, and FEWS NET is a famine early-warning
network for sub-Saharan Africa, Central America, Central Asia, Yemen,
Afghanistan and Haiti.

Measured directly against `fdw.fews.net/api/ipcphase`:

| Country | IPC records | Addable |
|---|---|---|
| Ethiopia | 236,608 | yes |
| Kenya | 162,508 | **built** |
| Uganda | 87,846 | yes |
| Sudan | 69,361 | yes |
| Somalia | 59,092 | yes |
| Nigeria | 57,366 | yes |
| Mozambique | 55,322 | yes |
| Zimbabwe | 47,019 | yes |
| Niger | 39,664 | yes |
| Mali | 28,106 | yes |
| Malawi | 23,673 | yes |
| Chad | 22,578 | yes |
| South Sudan | 20,687 | yes |
| Burkina Faso | 13,528 | yes |
| Zambia | 7,543 | yes |
| **Morocco, Algeria, Tunisia, Egypt, Libya** | **0** | no |
| Tanzania | 0 | no |

**All of North Africa returns zero.** Morocco is not an IPC or Cadre Harmonisé
country either, so there are no published phases, no livelihood zones, no
ground-truth labels and no official projections — the four things this
prototype is built on. The app's "no coverage" state is the honest answer, and
it is deliberate.

Morocco's food problem is also different in kind: national cereal shortfall and
import dependency (3.1 Mt harvested in 2023-24 against 10 Mt+ in good years)
rather than household famine classification, so IPC phases would not apply
meaningfully even if they existed. A Morocco product would need its own data
stack — ERA5 rainfall anomalies via Open-Meteo work there and the drought
signal is strong, but nothing grades the output.

### Adding a covered country

Roughly an hour per country:

1. `python3 fetch_fews.py` with `country_code=XX`
2. Download that country's geoBoundaries ADM2 and run `prep_adm2.py`
3. Check the name join rate (Kenya reached 288/290)
4. Add the country to `COUNTRIES` in `js/app.js`
5. Add its livelihood zones to `ZONES` in `js/advice.js` — the only real work,
   since crop and livestock mappings are country-specific

Zimbabwe is the natural next one: 4,263 records across 84 admin units, periods
running to **June 2026**, and geoBoundaries ADM2 carries 91 districts sourced
from ZIMSTAT, the national statistics agency — the same official-grade
provenance as Kenya's IEBC boundaries.

## Known gaps

- Adding a country: add it to the ISO3 list in `index.html` and `COUNTRIES` in
  `app.js`, run `prep_geo.py`, then the model.
- HUD numbers are real only: units at Warning+, real population (WorldPop /
  census in `data/geo`) of those units, and model escalations this month.
  There is no "SMS sent" estimate; real send counts are in the backend pages.
- Counties are coloured whole. Sub-county cropland patches would look better and
  are the obvious next visual step.
- The SMS is previewed, not sent. Wiring Africa's Talking (which covers Kenya)
  is Role C's job.
- Every template fits one GSM-7 segment on current data (audit:
  `node tests/e2e/sms_audit.js`). The NGO driver is shortened at a word
  boundary to fit. `[link]` is a placeholder; a real URL must stay short.

## Small screens

At 720 px and below (tested at 390 px) the globe sits on top, the feed below,
the unit panel opens as a bottom sheet, and the timeline wraps so the slider
gets the full width.


## Kenya add-ons from main (announcements scraper, FEWS live proxy)

Merged from Idriss's main. Kept as-is; our page loads them only if used.

**No data is simulated.** Every phase on screen is a published FEWS NET
classification from the FEWS NET Data Warehouse. The recommendations and the
SMS wording are ours; the classifications are not.

1. **Sign in** as Food bank / NGO.
2. **Type Kenya, hit enter.** The camera flies in and 290 sub-counties appear,
   coloured by FEWS NET's February 2019 classification.
3. **Press play** (or `space`). Each step is a real FEWS NET release. Watch the
   arid north and east deteriorate through 2021 into 2022.
4. **Stop at Oct 2022** — the peak. 54 sub-counties at Crisis+, 11 at Emergency.
   Pulsing markers mark them; the red blinking ones are IPC Phase 4.
5. **Hover a marker.** A card appears above it: what is at risk there, your next
   steps, and who can act. Point out the gap line — "no HSNP coverage in this
   county" — because knowing where help does *not* reach is the useful part.
6. **Switch role to Government entity** from the badge. Same alert, same data,
   completely different decision: reserve release and declaration, not
   procurement.
7. **Flip to County resolution** and back, to show the 6x jump in granularity.
8. **Click a sub-county.** FEWS NET's published phase, their own near-term
   projection, the livelihood zones, and the SMS each audience receives —
   one GSM-7 segment.
9. **Press `Live`.** The globe drops the replay and shows FEWS NET's current
   published classification, with their projection alongside.

?country=Kenya&role=ngo&t=28&view=now    # Jun 2021 observed: 16 at Crisis
?country=Kenya&role=ngo&t=28&view=ml1&tip=1   # same moment forecast: 46 at Crisis
?country=Kenya&role=gov&t=11&tip=1       # Oct 2022 peak, government view
?country=Kenya&role=gov&t=11&tip=1       # same moment, government view
?country=Kenya&res=county&t=11           # county resolution instead
?country=Kenya&live=1                    # straight into the live FEWS NET feed

| Every IPC phase on screen | **Real.** FEWS NET Data Warehouse, Current Situation scenario |
| The projections shown beside them | **Real.** FEWS NET's own ML1 near-term forecast |
| Sub-county boundaries | **Real.** geoBoundaries gbOpen KEN ADM2 (IEBC / OCHA ROSEA), CC BY 3.0 IGO |
| County boundaries | **Real.** geoBoundaries gbOpen KEN ADM1, public domain |
| Livelihood zones | **Real.** FEWS NET classification, 24 zones |
| HSNP eligibility | **Real.** The published 8-county list |
| Crop and livestock lists per zone | **Ours.** Mapped from the real zone, written by us |
| Next steps and role framing | **Ours.** Written by us, grounded in real Kenyan programmes |
| SMS wording | **Ours.** |

Nothing is simulated, smoothed or interpolated. A unit holds its last published
classification until FEWS NET publishes the next one, and units FEWS NET does
not cover are drawn grey rather than guessed.

**Two caveats worth stating on stage.** The crop lists and action wording are
ours, written from general knowledge of Kenyan agriculture — the livelihood zone
they hang off is real, the specific crop list is our mapping. And 2 of 290
sub-counties (Kilimani, Nithi) have no FEWS NET match and show as no-data.

serve.py                   static server + /api/live FEWS NET proxy
index.html                 markup for the three regions
css/app.css                all styling; design tokens at the top
js/sim.js                  the risk engine — replace this with the real pipeline
js/advice.js               livelihood zones -> crops, actions, resources
js/app.js                  globe, search, timeline, feed, detail panel
data/kenya-counties.js     generated; do not hand-edit
data/fews-ipc-kenya.json   real IPC phases, 2019-2024
data/kenya-livelihoods.json real FEWS NET livelihood zones per county
prep_data.py               regenerates geometry from ken_raw.geojson
fetch_fews.py              regenerates both FEWS NET files
vendor/                    globe.gl + earth textures, vendored for offline use
```

### Why `serve.py` and not a static server

`fdw.fews.net` sends no `Access-Control-Allow-Origin` header, so the browser
cannot call it directly. It also has no server-side date filter — the only
endpoint carrying reporting dates returns the full 235 MB Kenya history, and
asking for a `fields=` projection silently drops `reporting_date`. So the
server pulls once in a background thread at startup, reduces it to the latest
period per county, and caches to `data/fews-live.json`. `/api/live` answers
instantly from that cache and always reports `fetched_at` and `stale`, so the
UI can be honest about freshness. If FEWS NET is unreachable the committed
snapshot is served with `stale: true` — the demo never hard-fails on a network
call.

### `js/sim.js` is the seam
