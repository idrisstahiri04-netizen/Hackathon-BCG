# Pitch deck — Drought early warning by SMS (Welthungerhilfe case, northern Zimbabwe)

BCG Platinion "Fighting World Hunger" hackathon, Casablanca hub, 16–17 Oct 2026.
Nine slides. Speaker notes are simple English, under 60 words each.
Every number marked `[NUMBER PENDING]` is filled only from `pipeline/out/model_report.md`,
`pipeline/audit/judge/verdict.md` or `pipeline/audit/ground_truth.md`. Nothing else goes on a slide.

Numbers already fixed (sources in brackets):
- Coverage: Zimbabwe 91 districts, Kenya 47 counties, Malawi 28 districts, Zambia 116 districts.
- Declarations: Zimbabwe 2024-04-03, Malawi 2024-03-23, Zambia 2024-02-29, Kenya 2021-09-08 (`pipeline/CONTRACT.md`).
- Early destocking benefit-cost ratio 390:1 (Cabot Venton et al. 2012, "The Economics of Early Response and Disaster Resilience", Kenya case). Do not use any other ratio.

---

## Slide 1 — Title

**See the drought coming. Tell the herder in one SMS.**

Team CASA-5 · for Welthungerhilfe, northern Zimbabwe
Satellite + weather → district risk → one action per audience → any phone.

> Speaker notes (≈40 words):
> Good afternoon. In northern Zimbabwe a failed season can kill hundreds of animals in one family.
> We built a system that sees the dry season early from space, and sends one clear instruction to a
> herder's basic phone, weeks before the government declares a disaster.

---

## Slide 2 — Problem (the case, in WHH's words)

> "In northern Zimbabwe, drought doesn't arrive without warning, it creeps in. Rivers run dry
> earlier each year. Rainy seasons grow harder to predict."
> — BCG Platinion / Welthungerhilfe case brief, Sept 2026

- "A single failed season can mean losing hundreds of animals at once."
- The signals exist: rainfall, vegetation and soil moisture are measured every few days from space.
- They sit in archives and PDF bulletins. The herder with a 2G feature phone never sees them.
- National declaration came on **3 April 2024**, after the 2023–24 El Niño season had already failed.

> Speaker notes (≈55 words):
> The case says drought creeps in. That is good news: slow things can be seen early. The data is
> already there, measured from satellites for twenty years. The problem is the last mile. The person
> who must decide whether to sell a cow has no dashboard, no data plan, often no smartphone. Only SMS reaches them.

---

## Slide 3 — Insight

**Early action is cheap. Late action is not.**

- Selling animals early, while they are still healthy and prices are normal, returns about
  **390 dollars for every dollar spent** (Cabot Venton et al. 2012, Kenya).
- Waiting means the animal dies or sells for almost nothing.
- So the product is not a forecast. It is **a timely instruction**: "sell weak animals now", "keep two months of grain".
- Farmers and herders get an action, never a probability. Probabilities go to NGOs and officers.

> Speaker notes (≈55 words):
> The key insight: the value is not in predicting. It is in the few weeks between "the satellite can
> see it" and "everyone can see it". In that window, selling early pays back 390 to one. So our SMS
> says what to do, not how likely it is. Numbers go to the professionals.

---

## Slide 4 — Solution (flow)

```
 SATELLITE + WEATHER (free, global, 2001 → today)
   CHIRPS v3 rain  ·  MODIS NDVI (crop / grass, WorldCover mask)  ·  ERA5-Land soil moisture + heat
            │  monthly, per district (ZWE 91 · KEN 47 · MWI 28 · ZMB 116)
            ▼
 THREE INDEPENDENT FAMILIES       rain  |  vegetation  |  soil        (heat = supporting only)
            │  anomaly vs 2001–2020 baseline; missing stays missing, never zero
            ▼
 RISK MODEL  (LightGBM + logistic, calibrated; tested against persistence and a plain rule)
   → per district, per month: level 0–3, probability, confidence, drivers, event type
     event = can't plant · crop failure · no grass
            │  Warning only if ≥2 families agree · hysteresis 2 up / 3 down · human approval
            ▼
 ALERT ENGINE → one message per audience, one GSM-7 segment (160 chars)
   herder: "sell weak animals now"   farmer: "keep 2 months of grain"   NGO/officer: level, p, drivers
            │
            ▼
 TWO-WAY SMS GATEWAY (Android phone + local SIM; here a Moroccan SIM)
   Claude Haiku reads replies: JOIN · ask advice · ask help · report 1/2/3 · STOP
   advice only from an approved list · "we can't manage" → escalated to a human officer
```

> Speaker notes (≈60 words):
> Left to right. Free satellite data, every month, for every district. Three independent families:
> rain, plants, soil. A model turns them into a level from zero to three. A Warning needs two families
> to agree and a human to approve. Then one short SMS per audience, and the phone can talk back.
> The AI only reads replies; it never invents advice.

---

## Slide 5 — Live demo (3 minutes, see `docs/demo_script.md`)

1. Globe → Zimbabwe, Oct 2023: all 91 districts green.
2. Press play. Districts turn yellow, then orange, **before** the red line on 3 April 2024.
3. Click the first Warning district: drivers, families that agree, the herder's SMS, 1 segment.
4. A jury member texts **JOIN <district> herder** to the number on screen. They appear in "Users joining".
5. Run alerts → approve → their phone buzzes with the real Warning. They reply "we can't manage" → help request opens.

> Speaker notes (≈45 words):
> Now the real thing. Everything you see is real satellite data and real model output; nothing is
> simulated. We will replay the 2023–24 season month by month. Then one of you will join as a herder
> and receive the alert on your own phone, here, in Casablanca.

---

## Slide 6 — Proof: honest back-test on the 2023–24 season

| What we measured | Result | How |
| --- | --- | --- |
| Lead time: first Warning vs national declaration (Zimbabwe, 3 Apr 2024) | **[NUMBER PENDING] weeks** median across districts that reached Warning | `model_report.md` |
| Districts at Warning+ before the declaration | **[NUMBER PENDING] of 91** | `model_report.md` |
| Model skill vs persistence baseline (PR-AUC, leads 1–3 months) | model **[NUMBER PENDING]** vs persistence **[NUMBER PENDING]** vs plain rule **[NUMBER PENDING]** | leave-one-year-out CV 2001–2022, four countries pooled |
| Hold-out season never touched during training | 2023/24 (ZWE, MWI, ZMB) + Kenya 2020–22: PR-AUC **[NUMBER PENDING]** | `model_report.md` |
| False alarms: Warning+ not followed by a failed season | **[NUMBER PENDING] %** | `model_report.md` |
| Independent audit vs IPC / FEWS NET ground truth | **[NUMBER PENDING]** (verdict: [PENDING]) | `audit/judge/verdict.md`, `audit/ground_truth.md` |
| Signal check against a second, independent Earth Engine pull | max difference 2.5 %, 30 district-months | `audit/data_check.md` |

Rules the judges can hold us to: hold-out never used for tuning; labels come from satellite only
(no leakage of the official story); missing data is missing, not zero.

> Speaker notes (≈60 words):
> We did not grade our own homework. The 2023–24 season was locked away before training. The model is
> compared to the simplest possible baseline: "same as last year". [NUMBER PENDING] of 91 districts
> reached Warning [NUMBER PENDING] weeks before the declaration. An independent audit checked our
> numbers against IPC and FEWS NET; the verdict is on the slide.

---

## Slide 7 — Why us, not just HungerMap LIVE

| | WFP HungerMap LIVE | This system |
| --- | --- | --- |
| Who it is for | Analysts in Rome and country offices | The herder, the extension officer, the WHH field team |
| Unit | National / first-level admin | District (ADM2), 91 in Zimbabwe |
| Output | Map of current food insecurity (nowcast) | Level 0–3 with lead of 1–3 months, event type, drivers |
| Last mile | Dashboard, needs a browser | One-segment SMS to a 2G feature phone, two-way |
| Action | None prescribed | One approved action per audience; "sell weak animals now" |
| Governance | Published | Two-family rule, hysteresis, human approval, STOP keyword |

We are not a competitor. HungerMap and FEWS NET are inputs we plan to add. We are the fusion and
last-mile layer that WHH's existing early-warning work plugs into ("move faster, earlier, further").

> Speaker notes (≈55 words):
> Good dashboards already exist. HungerMap LIVE is excellent, for analysts. It does not tell a herder
> in Mbire what to do this week, and it does not listen back. We sit under those tools: district
> level, an action per person, on any phone, with the field officer in the loop. WHH keeps the lead.

---

## Slide 8 — Business model

- **Farmers and herders never pay.**
- **Who pays:** NGOs and anticipatory-action funds (WHH, WFP country offices), government early-warning
  units, index insurers. Annual licence per country for the risk feed, dashboard and API. SMS billed at cost.
- **Cost driver:** SMS segments. One segment per alert per person; Warning alerts go out a few times per season.
  SMS cost per season = subscribers × alerts × segments × price per segment
  (Zimbabwe per-segment price: [NUMBER PENDING — gateway quote]).
- **Why it is cheap to run:** satellite inputs are free, the model runs monthly, a country is one config file.
- **Value proof for funders:** every alert logs lead time, delivery, reply and opt-out, so impact is reportable.

> Speaker notes (≈55 words):
> Free for the person in the field. Paid by the organisations that already fund early warning, because
> it makes their money go further: 390 to one for early destocking. Running cost is tiny: free satellite
> data, one model run a month, and SMS at cost. Adding a country is a config change, not a project.

---

## Slide 9 — Ask and next steps

**Ask:** a WHH field partner in northern Zimbabwe for one season pilot: 2–3 districts, ~500 opted-in
herders and farmers via extension officers, a registered local sender ID.

Next 90 days:
1. Add prices (WFP/HDX) and official text (ReliefWeb, FEWS NET) as families 4 and 5 — the schema already has the slots.
2. Translate templates to Shona and Ndebele with native speakers; add IVR for low literacy.
3. Swap the demo phone for a Zimbabwean aggregator; register the sender ID now (takes weeks).
4. Season-end review with WHH: did the alert arrive before the loss? Publish the back-test.

> Speaker notes (≈50 words):
> We ask for one thing: a pilot district with WHH's field team this coming season. The code works
> end to end today, on real data, with real phones. What we need next is local trust: a known sender
> name, local languages, and field officers who approve each warning. Thank you.

---

### Appendix — things to say if asked

- "Is the data real?" Yes. CHIRPS v3, MODIS MOD13Q1, ERA5-Land, ESA WorldCover, geoBoundaries. Monthly, 2001–2024, four countries. Verified against an independent pull (max 2.5 % difference).
- "Why satellite only?" It is free, global, and twenty years deep, so we can back-test honestly. Prices and text are confirmers, planned next; the schema already treats every source as rows in one table.
- "What stops false alarms?" Two independent families must agree; a level must hold two runs to go up and three to go down; a human approves every Warning; farmers are not messaged at Watch.
- "What does the AI do?" Only reads incoming SMS and picks an answer from an approved list. It never writes advice. "We can't manage" goes to a person.
- "Why an Android phone as gateway?" Twilio has no two-way SMS in Morocco. A phone with a local SIM gives real two-way SMS today; in Zimbabwe we would use a local aggregator.
- "Is 390:1 real?" Cabot Venton et al. 2012, DFID-commissioned, Kenya early destocking case. We use no other ratio.
