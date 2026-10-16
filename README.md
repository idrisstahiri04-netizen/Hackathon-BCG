# SMS Shortage Early Warning — prototype

A clickable MVP of the dashboard half of the pitch: a globe you search, counties
that change colour as a drought develops, an alert feed that says who to tell,
and a timeline you can scrub across six years.

The country is **Kenya** (47 counties). The replay is scripted to the real
**2020–2023 Horn of Africa drought** — five consecutive failed rainy seasons and
the national drought disaster declaration of 8 September 2021.

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
   already open. Kenya is marked `LIVE`; everything else says `NO COVERAGE`.
2. **Type Kenya, hit enter.** Camera flies in, 47 counties appear, all green.
   "Every county is normal. This is October 2019."
3. **Press play** (or `space`). Watch 2020 stay calm, then the arid north and
   east turn yellow in early 2021 as the short rains fail.
4. **Let it run to Sept 2021.** Counties jump to red — that is the government
   declaring a national disaster, and you can see it arrive in the feed as a
   driver. Point out that the satellite and price signals turned *months*
   earlier. That gap is the product.
5. **Pause at the peak (Jan 2023).** 24 Warning + 23 Emergency, 47.8M people.
6. **Click a red county.** Drivers, which of the 5 source families agree, and
   the SMS each audience would actually receive, with its character count and
   segment count.
7. **Click the Farmers tab.** One GSM-7 segment, an action not a probability.
   That is the whole thesis: it fits on a feature phone and tells one person
   one thing to do.
8. **Scrub to 2024.** Everything green again. The system stands down.

### Controls

| Input | Action |
|---|---|
| `space` | play / pause |
| `←` `→` | step one month |
| `esc` | close the county panel |
| click a county | open its detail panel |
| click a notification | jump to that month and fly to that county |

### Deep links (stage insurance)

If dragging the slider in front of an audience goes wrong, reload straight into
a moment:

```
?country=Kenya&t=26                      # Mar 2021, drought spreading
?country=Kenya&t=33&county=Marsabit      # Oct 2021, just after the declaration
?country=Kenya&t=48&county=Turkana       # Jan 2023, peak crisis
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
| Every risk number, price, NDVI, SPI | **Simulated.** Generated in `js/sim.js` |
| SMS text | Generated from the templates in the spec |

The disclaimer is on screen at all times. Do not let anyone leave the room
thinking the probabilities are measured.

## Layout of the code

```
index.html              markup for the three regions
css/app.css             all styling; design tokens at the top
js/sim.js               the risk engine — replace this with the real pipeline
js/app.js               globe, search, timeline, feed, detail panel
data/kenya-counties.js  generated; do not hand-edit
prep_data.py            regenerates the above from ken_raw.geojson
vendor/                 globe.gl + earth textures, vendored for offline use
```

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
