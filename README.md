# SMS Shortage Early Warning — prototype

A clickable MVP of the dashboard half of the pitch: a globe you search, counties
that change colour as a drought develops, an alert feed that says who to tell,
and a timeline you can scrub across six years.

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
python3 -m http.server 8777
```

Then open <http://localhost:8777>.

It must be served over HTTP, not opened as a `file://` path — the browser blocks
the texture and data loads otherwise.

**No network required.** `globe.gl` and both earth textures are vendored in
`vendor/`. Nothing is fetched from a CDN at runtime, so venue wifi cannot break
the demo.

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

### Controls

| Input | Action |
|---|---|
| `space` | play / pause (also with the slider focused) |
| `←` `→` | step one month |
| `esc` | close the county panel |
| click a county | open its detail panel |
| click a notification | jump to that month and fly to that county |

### Deep links (stage insurance)

If dragging the slider in front of an audience goes wrong, reload straight into
a moment:

```
?country=Zimbabwe&t=63                   # Apr 2024, Zimbabwe declaration month
?country=Zimbabwe&t=63&county=Binga      # district detail (name match, case-insensitive)
?country=Kenya&t=26                      # Mar 2021, drought spreading
?country=Kenya&t=33&county=Marsabit      # Oct 2021, just after the declaration
?country=Kenya&t=48&county=Turkana       # Jan 2023, peak crisis
```

`t` is a month index, 0 = Jan 2019, 71 = Dec 2024.

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
