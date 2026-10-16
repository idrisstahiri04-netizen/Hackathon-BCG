# SMS Shortage Early Warning — prototype

A clickable MVP of the dashboard half of the pitch: a globe you search, counties
that change colour as a drought develops, an alert feed that says who to tell,
and a timeline you can scrub across six years.

The country is **Kenya** (47 counties). The replay is scripted to the real
**2020–2023 Horn of Africa drought** — five consecutive failed rainy seasons and
the national drought disaster declaration of 8 September 2021.

## Run it

```bash
python3 serve.py
```

Then open <http://localhost:8777>.

Use `serve.py`, not `python3 -m http.server` — it also proxies the FEWS NET
live feed (see below). It must be served over HTTP, not opened as a `file://`
path, or the browser blocks the data loads.

**The replay works with no network.** `globe.gl`, both earth textures and all
FEWS NET data are vendored or cached locally. Only the Live toggle needs the
internet, and it degrades to the cached snapshot if offline.

## Two modes

**Replay** (default) — the six-year scripted drought, driven by the timeline.

**Live** — press the `Live` button top-left. The globe switches to FEWS NET's
*current* published IPC classification for all 47 counties, with their own
near-term projection alongside. The timeline greys out because it no longer
drives anything.

As of the last pull, 8 counties sit at IPC Phase 3 Crisis: Turkana, Marsabit,
Mandera, Wajir, Garissa, Isiolo, Samburu and Tana River — which are exactly the
eight HSNP counties, so every one of them gets a cash-transfer recommendation
it is actually eligible for.

## Demo script

1. **Open on the spinning globe.** Search box is focused, the country list is
   already open. Kenya is marked `LIVE`; everything else says `NO COVERAGE`.
2. **Type Kenya, hit enter.** Camera flies in, 47 counties appear, all green.
   "Every county is normal. This is October 2019."
3. **Press play** (or `space`). Watch 2020 stay calm, then the arid north and
   east turn yellow in early 2021 as the short rains fail.
4. **Let it run to late 2021.** Counties jump to red. In the feed you can see
   `FEWS NET: IPC Phase 3 Crisis` appear as a *driver* — the official source
   confirming what the satellite and price signals already showed months
   earlier. That gap is the product.
5. **Pause at the peak (Nov 2022).** 23 Warning + 24 Emergency, 47.8M people.
6. **Read a notification properly.** Not just the risk level: what crops or
   livestock are at risk in that specific county, what to do this week, and
   which real programme pays for it. A pastoral county is told to destock; a
   highland county is told to hold the surplus. Different advice, same engine.
7. **Click a red county, then the Farmers tab.** One GSM-7 segment, an action
   not a probability, matched to that county's livelihood. Turkana gets "Water
   and feed breeding stock only"; Kitui gets "Plant green gram or cowpea".
8. **Scrub to 2024.** Everything green again. The system stands down.
9. **Press `Live`.** The globe drops the replay and shows FEWS NET's current
   published classification for all 47 counties, with their own near-term
   projection. Eight counties are in Crisis today, and all eight are HSNP
   counties, so each gets a cash transfer it is genuinely eligible for.

### Controls

| Input | Action |
|---|---|
| `space` | play / pause |
| `←` `→` | step one month |
| `esc` | close the county panel |
| click a county | open its detail panel |
| click a notification | jump to that month and fly to that county |

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
?country=Kenya&t=26                      # Mar 2021, drought spreading
?country=Kenya&t=33&county=Marsabit      # Oct 2021, just after the declaration
?country=Kenya&t=48&county=Turkana       # Jan 2023, peak crisis
?country=Kenya&live=1                    # straight into the live FEWS NET feed
```

`t` is a month index, 0 = Jan 2019, 71 = Dec 2024.

## What is real and what is not

| Part | Status |
|---|---|
| County boundaries | **Real.** geoBoundaries gbOpen KEN ADM1 (RCMRD / Africa GeoPortal), public domain, simplified for the browser |
| County populations | **Real**, 2019 census, rounded |
| Aridity / cropland split | **Real-ish.** Follows Kenya's standard ASAL vs high-potential classification |
| Sequence of failed rainy seasons | **Real.** The 2019–2024 season-by-season record |
| Sept 2021 disaster declaration | **Real event**, real date |
| FEWS NET IPC phases (official source family) | **Real.** 846 county-month observations, 2019-2024, from fdw.fews.net |
| Livelihood zones per county | **Real.** FEWS NET classification, 24 zones across 47 counties |
| HSNP county eligibility | **Real.** The published 8-county list |
| Rainfall, NDVI, prices, the risk score | **Simulated.** Generated in `js/sim.js` |
| Crop lists and action text | **Ours.** Grounded in the real zone, but written by us |
| SMS text | Generated from the templates in the spec |

The disclaimer is on screen at all times. Do not let anyone leave the room
thinking the probabilities are measured.

## Layout of the code

```
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

Everything else talks to it through one shape: a risk assessment per
`(county, month)` carrying `level`, `p`, `confidence`, `agreeing`, `drivers`
and the raw signals. When the real pipeline lands — Earth Engine SPI/NDVI, WFP
prices, ReliefWeb extraction — it replaces this file and nothing in `app.js`
needs to change.

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
python3 prep_data.py      # ken_raw.geojson -> data/kenya-counties.js
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

- One country. Adding another needs its admin boundaries, a crop mask and a
  season of price data.
- Counties are coloured whole. Sub-county cropland patches would look better and
  are the obvious next visual step.
- The SMS is previewed, not sent. Wiring Africa's Talking (which covers Kenya)
  is Role C's job.
- Six NGO-audience messages run to 2 segments on the longest county names. The
  UI shows the real count rather than hiding it.
