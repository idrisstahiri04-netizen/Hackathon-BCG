# SMS Shortage Early Warning — prototype

A clickable MVP: a searchable globe of Kenya at **sub-county resolution**, every
area coloured by its **real FEWS NET IPC classification**, an alert feed that
says who to tell and what to do, and a timeline that steps through real FEWS NET
releases.

**No data is simulated.** Every phase on screen is a published FEWS NET
classification from the FEWS NET Data Warehouse. The recommendations and the
SMS wording are ours; the classifications are not.

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
?country=Kenya&role=ngo&t=11&tip=1       # Oct 2022 peak, NGO view, card open
?country=Kenya&role=gov&t=11&tip=1       # same moment, government view
?country=Kenya&res=county&t=11           # county resolution instead
?country=Kenya&live=1                    # straight into the live FEWS NET feed
```

`t` is an index into the 18 real FEWS NET releases (0 = Feb 2019, 17 = Oct 2024).
`tip=1` opens the hover card on the worst-affected area without needing a mouse —
stage insurance. `tip=<Sub-county>` opens a specific one.

## What is real and what is not

| Part | Status |
|---|---|
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
