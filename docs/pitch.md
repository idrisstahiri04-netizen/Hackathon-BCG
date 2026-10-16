# Pitch deck — Drought early warning by SMS (Welthungerhilfe case, northern Zimbabwe)

BCG Platinion "Fighting World Hunger" hackathon, Casablanca hub, 16–17 Oct 2026.
Nine slides. Speaker notes are simple English, under 60 words each.

## Provenance of every number (read before touching a slide)

The globe shows the **final export** `data/risk/ZWE.js`, model `sat-v1-ensemble-ZWE_KEN_MWI_ZMB`,
written **16:53 UTC**. It differs from the 16:28 export in three ways: data latency is built in
("level for month t is issued at the end of month t from data of month t-1"), the Watch/Warning
thresholds were raised with a precision floor (`p_warn` 0.50, `p_watch` 0.525, CV precision ≥ base + 0.10),
and the Emergency rule no longer fires without a declaration. The audit files were written for the
**old** export: `pipeline/audit/judge/verdict.md` (16:39) and `pipeline/audit/ground_truth.md` (16:30).
`pipeline/out/model_report.md` (16:49) is current.

So, three classes of numbers:

| Class | Allowed on a slide? | Where |
| --- | --- | --- |
| A. Counted on the final export (`data/risk/ZWE.js`, 16:53), re-derivable with the verify command in `docs/demo_script.md` | yes, labelled "final export; audit re-run pending" | slide 6 rows marked **A** |
| B. From `model_report.md` 16:49 (current model) and `data_check.md` | yes | slide 6 rows marked **B** |
| C. From `verdict.md` / `ground_truth.md` on the **old** export (46 of 91, "13 districts 13 weeks", recall 93 %, 8.7 weeks vs FEWS NET) | **no**, until `judge.py` and `compare_ipc.py` are re-run on the 16:53 file | appendix only, marked stale |

Action for the pipeline owner before slide freeze (11:00 day 2): re-run
`python pipeline/audit/judge/judge.py` and `python -I pipeline/audit/compare_ipc.py ZWE`, then replace
the class-A rows on slide 6 with the judge's numbers and move class C to wherever the re-run puts them.

Fixed facts (sources in brackets):
- Coverage: Zimbabwe 91 districts, Kenya 47 counties, Malawi 28 districts, Zambia 116 districts.
- Declarations: Zimbabwe 2024-04-03, Malawi 2024-03-23, Zambia 2024-02-29, Kenya 2021-09-08 (`pipeline/CONTRACT.md`).
- Early destocking benefit-cost ratio **390:1, modelled, Wajir, Kenya** (Cabot Venton et al. 2012, "The Economics of Early Response and Disaster Resilience", DFID). Say "modelled". No other ratio is used.

---

## Slide 1 — Title

**See the drought coming. Tell the herder in one SMS.**

Team CASA-5 · for Welthungerhilfe, northern Zimbabwe
Satellite + weather → district risk → one action per audience → any phone.

> Speaker notes (≈40 words):
> Good afternoon. In northern Zimbabwe a failed season can kill hundreds of animals in one family.
> We built a system that watches the dry season from space, and sends one clear instruction to a
> herder's basic phone, with a human in the loop and no false alarms in a wet year.

---

## Slide 2 — Problem (the case, in WHH's words)

> "In northern Zimbabwe, drought doesn't arrive without warning, it creeps in. Rivers run dry
> earlier each year. Rainy seasons grow harder to predict."
> — BCG Platinion / Welthungerhilfe case brief, Sept 2026

- "A single failed season can mean losing hundreds of animals at once."
- The signals exist: rainfall, vegetation and soil moisture are measured every few days from space.
- They sit in archives and PDF bulletins. The herder with a 2G feature phone never sees them.
- The national declaration came on **3 April 2024**, after the 2023–24 El Niño season had already failed.

> Speaker notes (≈55 words):
> The case says drought creeps in. That is good news: slow things can be watched. The data is
> already there, measured from satellites for twenty years. The problem is the last mile. The person
> who must decide whether to sell a cow has no dashboard, no data plan, often no smartphone. Only SMS reaches them.

---

## Slide 3 — Insight

**Early action is cheap. Late action is not. False alarms are the most expensive of all.**

- Selling weak animals early, while they are still healthy and prices are normal, returns about
  **390 dollars for every dollar spent** (modelled estimate, Wajir, Kenya; Cabot Venton et al. 2012).
- Waiting means the animal dies or sells for almost nothing.
- But two wrong warnings and nobody listens again. So the system is tuned for **precision first**, and
  every Warning passes a human.
- The product is not a forecast. It is **a timely, trusted instruction**: "sell weak animals now". Farmers and herders get an action, never a probability.

> Speaker notes (≈55 words):
> The value is in the weeks between "the satellite can see it" and "everyone can see it". Selling early
> pays back, in the modelled Kenya case, 390 to one. But trust is the real asset: after two false alarms
> a herder stops reading. So we tuned for precision, and a person approves every Warning.

---

## Slide 4 — Solution (flow)

```
 SATELLITE + WEATHER (free, global, 2001 → today)
   CHIRPS v3 rain  ·  MODIS NDVI (crop / grass, WorldCover mask)  ·  ERA5-Land soil moisture + heat
            │  monthly, per district (ZWE 91 · KEN 47 · MWI 28 · ZMB 116); 1-month data latency built in
            ▼
 THREE SIGNAL FAMILIES       vegetation (satellite)  |  rain (weather)  |  soil (weather)      heat = supporting only
            │  anomaly vs 2001–2020 baseline; missing stays missing, never zero
            ▼
 RISK MODEL  (LightGBM + logistic ensemble, calibrated; tested against persistence and a plain rule)
   → per district, per month: level 0–3, probability, confidence, drivers, event type
     event = crop failure · no grass
            │  Warning only if vegetation AND (rain or soil) agree and p ≥ 0.5 · hysteresis 2 up / 3 down · human approval
            ▼
 ALERT ENGINE → one message per audience, one GSM-7 segment (160 chars)
   herder: "sell weak animals now"   farmer: "keep 2 months of grain"   NGO/officer: level, p, drivers
            │
            ▼
 TWO-WAY SMS GATEWAY (Android phone + local SIM; here a Moroccan SIM)
   Claude Haiku reads replies: JOIN · ask advice · ask help · report 1/2/3 · STOP
   advice only from an approved list · "we can't manage" → escalated to a human officer
```

Next in the same table, no model change: prices (WFP/HDX) and official text (ReliefWeb, FEWS NET) as families 4 and 5.

> Speaker notes (≈55 words):
> Left to right. Free satellite data, every month, every district, real data delays built in.
> Three signal families: plants from satellite, rain and soil from weather. A Warning needs the plants
> plus one weather family, probability above a half, and a human to approve. Then one short SMS per
> audience, and the phone talks back. The AI only reads replies.

---

## Slide 5 — Live demo (3 minutes, see `docs/demo_script.md`)

1. Globe → Zimbabwe, Oct 2023: 91 districts, 13 at Watch in the south-east, none at Warning.
2. Press play. **End of March 2024: 22 districts at Watch**, including Mbire, Karoi and Rushinga in the north, all three families agreeing, days before the red line on 3 April.
3. Step onto the red line: **26 districts tip to Warning**, Hwange, Tsholotsho, Bulilima, Plumtree, Victoria Falls among them.
4. Click Hwange: event *no grass*, all three families agree, confidence high, the herder's SMS, 1 segment.
5. A jury member texts **JOIN Hwange herder** to the number on screen. They appear in "Users joining".
6. Run alerts for that month → approve → their phone buzzes with the real herder Warning. They reply "we can't manage" → help request opens.

> Speaker notes (≈45 words):
> Now the real thing. Everything you see is real satellite data and real model output; nothing is
> simulated. We will replay the 2023–24 season month by month. Then one of you will join as a herder
> in Hwange and receive the alert on your own phone, here, in Casablanca.

---

## Slide 6 — Proof: honest back-test, 2023–24 season, final export

| Class | What we measured | Result |
| --- | --- | --- |
| A | Districts at **Watch** issued end of March 2024 (days before the 3 Apr declaration) | **22 of 91**, incl. Mbire, Karoi, Rushinga, Uzumba Maramba Pfungwe in the north |
| A | Districts at **Warning** issued end of March 2024 | **4 of 91** (Harare periphery) |
| A | Districts at Warning issued end of April 2024 / reached Warning by June 2024 | **26 of 91** / **48 of 91** |
| A | Districts never reaching Warning in 2023/24 | 43, including Masvingo, Chivi, Zaka, Mwenezi, Chiredzi, Beitbridge (the south-east) |
| A | False alarms: Warning unit-months in the wet 2020/21 season; Emergency in 2020 without a declaration | **0** and **0** |
| A | Watch in Oct 2023 before the fix / after the fix | 91 of 91 / **13 of 91** |
| B | Model skill, cross-validation 2001–2022, 4 countries, leave-one-year-out (mean PR-AUC) | ensemble **0.55** vs persistence 0.48 vs plain rule 0.46; *no grass* 0.55 vs 0.44 (base 0.41) |
| B | Thresholds tuned on CV out-of-fold only, precision floor base + 0.10 | Warning precision 0.56 at a 5 % alarm rate |
| B | Signals checked against a second, independent Earth Engine pull | max difference 2.5 % over 30 district-months |

Class A = counted on the final `data/risk/ZWE.js` (16:53 UTC); independent judge re-run pending.
Class B = `model_report.md` (16:49 UTC), `data_check.md`.

Rules the judges can hold us to: the 2023/24 season was a hold-out never used for tuning; labels come
from satellite only; missing data is missing, not zero; months on the globe are **issue months**, data
latency already subtracted. We did not beat the declaration with a Warning except in four districts;
we reached Watch in 22 districts first, and we accepted that cost to keep a wet year silent.

> Speaker notes (≈55 words):
> Honest numbers. With real data delays, most Warnings were issued at the end of April, four weeks
> after the declaration. What came first was the Watch: twenty-two districts, the north included, at the
> end of March. The wet year before: zero warnings. We chose a quiet wet year over an impressive lead.
> The model beats "same as last year" in cross-validation.

---

## Slide 7 — Why us, not just HungerMap LIVE

| | WFP HungerMap LIVE | This system |
| --- | --- | --- |
| Who it is for | Humanitarian analysts and country offices | The herder, the extension officer, the WHH field team |
| Unit | Country and sub-national nowcast (its admin level for Zimbabwe not verified by us) | District (ADM2), 91 in Zimbabwe, monthly since 2001 |
| Output | Current food-insecurity map, plus forecasts for a set of hotspots | Level 0–3 with a 1–3 month horizon, event type (no grass / crop failure), drivers |
| Last mile | Dashboard, needs a browser | One-segment SMS to a 2G feature phone, two-way |
| Action | None prescribed | One approved action per audience; "sell weak animals now" |
| Governance | Published | Two-family rule, precision-floored thresholds, hysteresis, human approval, STOP keyword |

We are not a competitor. HungerMap and FEWS NET are inputs we plan to add. We are the fusion and
last-mile layer that WHH's existing early-warning work plugs into ("move faster, earlier, further").

> Speaker notes (≈55 words):
> Good dashboards already exist. HungerMap LIVE is excellent, for analysts. It does not tell a herder
> in Hwange what to do this week, and it does not listen back. We sit under those tools: district
> level, an action per person, on any phone, with the field officer in the loop. WHH keeps the lead.

---

## Slide 8 — Business model

- **Farmers and herders never pay.**
- **Who pays:** NGOs and anticipatory-action funds (WHH, WFP country offices), government early-warning
  units, index insurers. Annual licence per country for the risk feed, dashboard and API. SMS billed at cost.
- **Cost driver:** SMS segments. One segment per alert per person; the backend caps alerts at 6 per person per month.
  SMS cost per season = subscribers × alerts × segments × price per segment
  (Zimbabwe per-segment price: not yet quoted; get a gateway quote before putting a figure on this line).
- **Why it is cheap to run:** satellite inputs are free, the model runs monthly, a country is one config file.
- **Value proof for funders:** every alert logs lead time, delivery, reply and opt-out, so impact is reportable.

> Speaker notes (≈55 words):
> Free for the person in the field. Paid by the organisations that already fund early warning, because
> it makes their money go further: in the modelled Kenya case, 390 to one for early destocking. Running
> cost is tiny: free satellite data, one model run a month, SMS at cost. Adding a country is a config change.

---

## Slide 9 — Ask and next steps

**Ask:** a WHH field partner in northern Zimbabwe for a one-season pilot: 2–3 districts (Mbire, Karoi,
Hwange: where the final model flagged first in the north), ~500 opted-in herders and farmers via
extension officers, a registered local sender ID.

Next 90 days:
1. Win back lead time without losing precision: an early rain+soil path for December–February (needs a spec change, both are weather), and a Watch message to extension officers so the north's end-of-March Watch becomes a field visit.
2. Add prices (WFP/HDX) and official text (ReliefWeb, FEWS NET) as families 4 and 5; the schema already has the slots.
3. Translate templates to Shona, Ndebele and Tonga with native speakers and AGRITEX; add IVR for low literacy.
4. Swap the demo phone for a Zimbabwean aggregator; register the sender ID now (it takes weeks).
5. Season-end review with WHH: did the alert arrive before the loss? Publish the back-test.

> Speaker notes (≈50 words):
> We ask for one thing: a pilot district with WHH's field team this coming season. The code works
> end to end today, on real data, with real phones. What we need next is local trust: a known sender
> name, local languages, and field officers who approve each warning. Thank you.

---

### Appendix — things to say if asked

- "Is the data real?" Yes. CHIRPS v3, MODIS MOD13Q1, ERA5-Land, ESA WorldCover, geoBoundaries. Monthly, 2001–2024, four countries. Verified against an independent pull (max 2.5 % difference).
- "You did not beat the declaration." Correct for Warning: four districts before, twenty-six at the end of April. Watch reached twenty-two districts at the end of March, with all three families agreeing in Mbire, Karoi and Rushinga. An earlier, looser version of the model warned forty-six districts before the declaration but also lit up every district every year; the independent judge called that Watch level "broken". We kept the strict one.
- "Why satellite only?" It is free, global and twenty years deep, so we can back-test honestly. Prices and text are confirmers, planned next; the schema already treats every source as rows in one table.
- "Three independent families? Two are weather." Correct: vegetation is satellite, rain and soil are both weather. That is why the Warning rule requires vegetation plus one weather family, never rain plus soil alone.
- "What stops false alarms?" Two families must agree; p ≥ 0.5 with a precision floor tuned on cross-validation; a level must hold two runs to go up and three to go down; a human approves every Warning; farmers are not messaged at Watch. Zero Warnings in the wet 2020/21 season, zero Emergency in 2020.
- "Why did it not catch the south?" Vegetation stayed near normal there in January 2024, so the two-family rule held those districts at Watch or Normal. The rule that stops false alarms also costs recall. The north was hit too; the model is national.
- "Your farmer and herder messages contradict." "Do not sell at collapsed prices" (farmer) and "sell weak animals early while prices hold" (herder) are two different decisions at two different times; we will reword so they read as one policy. All advice is marked "to be validated by WHH / AGRITEX".
- "What about Malawi?" The government declared 23 of 28 districts; the earlier export warned 8. Southern Malawi was missed for the same vegetation-lag reason. We show Zimbabwe; Malawi is work in progress.
- "What does the AI do?" Only reads incoming SMS and picks an answer from an approved list. It never writes advice. "We can't manage" goes to a person.
- "Why an Android phone as gateway?" We could not get two-way SMS through Twilio for a Moroccan number for this demo, so a phone with a local SIM gives real two-way SMS today; in Zimbabwe we would use a local aggregator. (Do not state a general claim about Twilio's coverage; it is unverified.)
- "Is 390:1 real?" Cabot Venton et al. 2012, DFID-commissioned; a modelled household-economy estimate for commercial destocking in Wajir, Kenya. The observed Ethiopian case (Abebe et al. 2008) is 41:1. We use no other ratio.

### Stale numbers (class C) — do not show until the audit is re-run on the 16:53 export

From `verdict.md` / `ground_truth.md` on the 16:28 export: 46 of 91 at Warning before the declaration;
13 districts from December data, ~13 weeks early; 14 of 91 with latency, median 8 weeks; IPC 3+ recall
93 % (53 of 57) vs 35 % persistence; median 8.7 weeks earlier than FEWS NET projections. These describe
a model with `p_warn = 0.25` and no latency, which is not the one on the globe.
