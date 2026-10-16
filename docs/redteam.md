# Red-team review (jury simulation)

Role: hostile BCG Platinion / Welthungerhilfe jury member. Written 2026-10-16 from the
`zimbabwe-real-data` working tree (uncommitted). Inputs read: `README.md`, the spec,
`/home/looooo/bcg/docs/hackathon_case.md`, `hunger_tech_brief.pdf`, `pipeline/CONTRACT.md`,
`pipeline/audit/{data_check,methodology}.md`, `pipeline/out/model_report.md` (16:25 UTC),
`pipeline/audit/out/metrics_*.json`, `docs/pitch.md`, `docs/demo_script.md`, the pipeline and
backend code. Web checks were done for the load-bearing claims (section 2).

Status of the evidence at the time of writing:

| Artefact | State |
|---|---|
| `pipeline/data/signals_ZWE.parquet` | real, independently verified (62 checks, 0 FAIL) |
| `pipeline/out/model_report.md` | real, first run 16:25 UTC (numbers below) |
| `data/risk/ZWE.js`, `MWI.js`, `ZMB.js` | **still `STUB`** - the globe shows every country as DATA IN PROGRESS |
| `pipeline/audit/out/metrics_ZWE.json` (IPC comparison) | computed on the **STUB** file - every lead-time / precision number in it is synthetic and must not be quoted |
| `pipeline/audit/judge/verdict.md`, `backend/README.md` | not present yet |
| `pytest pipeline/tests/audit` | 99 passed, **1 failed** (`test_labels_invariant_to_non_vci_signals`; `cant_plant` labels use SPI/soil by design, test is stale) |

`[PENDING]` below = fill from the real export + IPC comparison once `data/risk/ZWE.js` is not STUB.

---

## 1. The 15 hardest jury questions, with the strongest honest answer

Format: question / honest answer with our numbers / the slide or demo moment that proves it.

### Q1. "Isn't this just WFP HungerMap LIVE (or FEWS NET) with an SMS bolted on?"
**Answer.** Three real differences, and one honest overlap. (a) Unit: we score 91 ADM2 units in
Zimbabwe every month from 2001; HungerMap's public layer is national / ADM1 nowcasting of current
food insecurity (relaunched 16 Apr 2026, 50+ countries, forecasts for 16 hotspots). (b) Direction:
HungerMap says how bad it is now; we say "no grass in this district in 1-3 months" with the
drivers. (c) Last mile: a 160-char GSM-7 action to a feature phone, two-way, with human approval.
The overlap: FEWS NET's own ML1/ML2 projections already flagged **all 57** Zimbabwean districts that
went IPC3+ in 2023/24, a median **17.4 weeks** before the IPC snapshot (our audit, FEWS NET FDW
data). So we must *not* claim to out-forecast FEWS NET at district level; we claim to turn the
same satellite evidence into a per-district, per-audience instruction weeks earlier than the
national declaration and deliver it. Say: "FEWS NET is an input we plan to add; we are the
fusion-plus-last-mile layer."
**Proof moment.** Slide 7 table (fix the "National / first-level admin" cell - unverified, say
"coarser than ADM2 for most countries"). Demo: click a district, show drivers + the herder SMS.

### Q2. "How do you know the warnings were right?"
**Answer.** Two independent checks. (1) Labels are satellite-only (VCI < 35, SPI < -1 and soil
z < -1), scored leave-one-agricultural-year-out 2001-2022, 22 folds, 80,648 rows, with the 2023/24
season locked away and scored once. (2) An audit script compares the exported Warning series to
FEWS NET IPC-compatible phases (84 of 91 districts matched; 27 snapshots 2016-2024) with a
persistence baseline. Honest numbers today: pooled CV mean PR-AUC **0.467** (ensemble) vs **0.373**
persistence vs **0.404** plain rule; `no_grass` is the only strong event (ROC-AUC 0.71, **0.82 at
lead 1**); `crop_failure` ROC 0.61; `cant_plant` has **no skill** (ROC 0.49, PR-AUC 0.168 =
base rate). Hold-out ZWE 2023/24: ensemble ROC 0.53-0.58, which only ranks districts within a year
where 76-88 % of units were positive. IPC lead time and precision: **[PENDING - real export]**.
**Proof moment.** Slide 6; say the `cant_plant` weakness before they find it.

### Q3. "What if the forecast is wrong and a herder sells cattle for nothing?"
**Answer.** The farmer/herder message is gated three times: Warning needs vegetation **and**
(rain or soil) to agree, plus a calibrated probability over threshold, plus two consecutive runs;
a human approves every Warning; nobody below Watch is messaged. The action itself is low-regret:
"sell weak animals early while prices hold, keep breeding stock" is standard LEGS destocking
guidance, and the cost of acting on a false alarm (selling a few culls early) is small next to the
cost of a miss. Cabot Venton et al. 2012 (DFID) models **$390 of avoided aid and animal losses per
$1 spent on commercial destocking** in Wajir, Kenya - a modelled figure, not an observed one, so
quote it as "modelled". Our CV false-alarm control is weak today: the tuned Warning threshold is
**p >= 0.25** with CV F1 **0.25** - so answer "we would start with institutions only for one season
and open the farmer tier when precision on the IPC audit is above X".
**Proof moment.** Detail panel: "2/3 families agree, conf medium, pending approval" in the Alert
feed. Slide 3 (make the "modelled" caveat visible).

### Q4. "Who pays?"
**Answer.** Farmers and herders never pay. Payers are those who already fund early warning and
anticipatory action: WHH itself runs a forecast-based action pilot in Zimbabwe since 2020 and
activated it in **Mbire, Mount Darwin and Rushinga in July/August 2024 with EUR 500,000**
(welthungerhilfe.org, anticipation-hub.org). Our offer to WHH: a district trigger feed + SMS
dissemination that plugs into that EUR 500k budget. Satellite inputs are free (Earth Engine,
non-commercial), one model run a month, SMS at cost. The per-SMS price in Zimbabwe is **not
sourced** (third-party guides range US$0.003 to US$0.29 per message) - say "gateway quote
pending", never a number.
**Proof moment.** Slide 8; add the WHH 2024 activation as the anchor customer story.

### Q5. "Why SMS in 2026?"
**Answer.** POTRAZ Q3 2025: 16.4 M active mobile subscriptions, 104.8 % subscription penetration,
but only ~50 % of adults own a smartphone (World Bank 2024, via secondary source). The case brief
says the target is "communities whose lives depend on their land and livestock" with 2G feature
phones. SMS is the only channel that reaches every phone with no data plan; our templates are
GSM-7 and one segment (**max 158 chars** for the longest district name, "Uzumba Maramba
Pfungwe"). Scale-up adds USSD and IVR; WhatsApp is listed as a later channel for extension staff.
**Proof moment.** Live SMS to a jury phone (Casablanca SIM), character count on screen.

### Q6. "Does it work in Zimbabwe when your gateway is a Moroccan Android phone?"
**Answer.** Today's gateway is a demo path (capcom6 Android SMS Gateway, local SIM). It proves
the loop, not the deployment. Africa's Talking does **not** cover Zimbabwe (11 countries listed,
2025; Zambia and Malawi are covered). For Zimbabwe we need a local aggregator or Infobip/Twilio
with a registered sender ID, which takes weeks - hence the ask on slide 9. Consent and data
protection under Zimbabwe's Cyber and Data Protection Act (Act 5 of 2021, POTRAZ as regulator) are
built in: opt-in, STOP, phone number hashing, monthly cap of 6 alerts.
**Proof moment.** Slide 9 next steps; show the `users` table fields (consent_at, opted_out_at).

### Q7. "The case says northern Zimbabwe. Wasn't the 2023/24 drought worst in the south?"
**Answer.** Yes for food security: FEWS NET (Sep/Oct 2024) names Matabeleland South as the worst
affected province (3,500+ cattle deaths). But the climate shock also hit the north: FEWS NET's
October 2024 outlook says parts of Mashonaland Central, Mashonaland West and Midlands had "the
driest mid-January through March period on record", and WHH's own anticipatory action triggered in
Mbire, Mt Darwin and Rushinga. Our model is national (91 districts) so the north is covered, and
the demo district should be a northern one that WHH works in (Mbire). In our verified sample Mbire
shows SPI-1 **-1.3** and soil z **-1.5** in Nov 2023, then SPI-1 **-2.2** and soil z **-4.1** in Feb
2024.
**Proof moment.** Demo on Mbire; have Binga/Hwange (north-west) as second click.

### Q8. "How did you avoid overfitting with so few droughts?"
**Answer.** We did not learn "the drought year": labels are satellite indices per district per
season, giving ~1,000 labelled district-seasons per country, not one event. Leave-one-year-out CV
holds out every district of a year together; LightGBM is small (15 leaves, depth 5, L2 = 5, early
stopping on inner years); calibration is cross-fitted; thresholds tuned on CV out-of-fold only;
the 2023/24 season and Kenya 2020-22 were never touched until one final scoring. The honest cost:
skill is modest (CV ROC 0.49-0.71 by event) and the baseline climatology (2001-2020) includes the
CV years (mild optimism, disclosed in `methodology.md` m3).
**Proof moment.** Slide 6 "rules the judges can hold us to"; `model_report.md` on screen if asked.

### Q9. "Your 'three independent families' are all weather. Where are prices and official text?"
**Answer.** Correct. Rain (CHIRPS v3) and soil (ERA5-Land) are both weather-derived and
ERA5-Land soil moisture is model output; only vegetation (MODIS) is an independent observation.
Our Warning rule already reflects that: it requires vegetation **and** (rain or soil), never
rain + soil alone. Prices (WFP/HDX) and ReliefWeb/FEWS NET text are in the schema and the spec but
**not in the build** - say "families 4 and 5, next 90 days", and stop saying "three independent
families" on slide 4 (say "satellite plus weather").
**Proof moment.** CONTRACT.md rule; slide 9 item 1.

### Q10. "Lead time: weeks before the declaration, measured how? Did you account for data latency?"
**Answer.** Our timeline `t` is the *data month*. CHIRPS final, MOD13Q1 and ERA5-Land are complete
2-6 weeks after month end, so a Warning at "Feb 2024" is really issuable mid/late March 2024. Say
the lead time as "data-month lead minus ~4-6 weeks" or show it at issue date. Also: the hard
signal in 2023/24 came late - Nov 2023 was dry in all 5 verified sample districts (SPI-1 down to
-3.0 in Beitbridge/Mwenezi), **Jan 2024 vegetation was above normal** (rains recovered), and the
collapse is Feb 2024 (national SPI-1 mean **-2.11**, 100 % of districts dry). A Feb-2024 Warning
issued mid-March beats the 3 April declaration by about 2-3 weeks, not months. **[PENDING: first
Warning month per district from the real export.]**
**Proof moment.** Timeline scrub Nov 2023 -> Feb 2024; be the first to say "latency".

### Q11. "FEWS NET and IPC - you use them as truth. Aren't they themselves late and now unreliable?"
**Answer.** FEWS NET was paused by the US aid freeze in early 2025, relaunched 24 June 2025, and
in Aug 2026 still had coverage gaps (NPR). That is exactly why a free, open-data district trigger
with local ownership matters (brief, section 9). We use FEWS NET only as *evaluation* truth, and
only its Current Situation snapshots (3 per year), which makes our IPC lead times coarse (about
4-month resolution). The model does not depend on FEWS NET at run time.
**Proof moment.** Slide 7 note; `fetch_ipc.py` provenance (`_meta.json` with sha256).

### Q12. "Emergency level - you say it needs an official declaration, but your code fires it from a calendar month."
**Answer.** True as of 16:06 UTC (`methodology.md` B1): `after_decl` is "agricultural month >=
April" in every year, plus a satellite-only extreme path (VCI < 20 and SPI-3 <= -2). That breaks
the spec rule "public Emergency only after an official declaration". Fix before freeze: gate level
3 on the actual declaration list (only 2024-04-03 for ZWE) and cap the extreme path at Warning
with a `severe` flag. If not fixed, say "Emergency in the demo is 'severe' not 'declared'".
**Proof moment.** Only if fixed; otherwise avoid the Emergency tab on stage.

### Q13. "A farmer and a herder in the same district get opposite advice: 'do not sell animals cheap' vs 'sell weak animals now'."
**Answer.** They are different decisions: the farmer line is about not panic-selling at collapsed
prices; the herder line is about early destocking of culls while prices still hold. But read
together on stage they sound contradictory, and the cooperative message leaks a probability
("shortage risk 68 %") to a farmer-facing audience. Reword before the demo: farmer "do not sell
grain or animals below market price", herder "sell weak and old animals early, keep breeding
females", coop message action-only.
**Proof moment.** Audience tabs in the detail panel (after the reword).

### Q14. "What does the AI do, and what happens when it is wrong?"
**Answer.** Claude Haiku only classifies inbound SMS into a fixed intent list (JOIN, 1/2/3 report,
advice, help, STOP) with keyword fast-paths that bypass the LLM; advice is picked from
`backend/advice.yaml` (12 approved entries, marked "demo content to be validated by WHH/AGRITEX"),
never generated; "we can't manage" opens a help request for a human. No LLM touches the risk
level. Weakness: the advice library is unvalidated and the Shona/Ndebele versions do not exist yet
(only EN/FR). Say so.
**Proof moment.** Jury member texts free text, sees intent label + human hand-off in the feed.

### Q15. "Everything on the globe is grey - where is the real output?"
**Answer (if still true at demo time).** The signals are real and verified; the model report is
real; the export to the globe is the last step. Have the fallback ready: the recorded video and the
`model_report.md` table. If `data/risk/ZWE.js` is real by then, open with "every colour you see is
model output scored out-of-sample, nothing is simulated" - and be able to show the file header
`sat-v1-ensemble-...`.
**Proof moment.** The country list showing LIVE for Zimbabwe (pre-demo checklist item 1).

---

## 2. Fact check of README.md, the spec and pitch.md

Legend: VERIFIED / PARTLY / UNVERIFIED / WRONG. Sources are URLs or repo files.

### README.md

| Claim | Verdict | Evidence |
|---|---|---|
| Zimbabwe 91 districts | PARTLY | 91 = geoBoundaries gbOpen ADM2 units incl. urban units (Hwange Urban, Kariba Urban...). Zimbabwe has ~63 rural districts; call them "91 admin-2 units". |
| Disaster declared 3 Apr 2024 | VERIFIED | Reuters / New Humanitarian 2024-04-03, Mnangagwa, >US$2 bn appeal. |
| Malawi 28 districts, 23 Mar 2024 | VERIFIED | AP 2024-03-24: state of disaster in 23 of 28 districts; OCHA. |
| Zambia 116 districts, 29 Feb 2024 | VERIFIED | Cabinet Office statement; Al Jazeera 2024-02-29 (84 of 116 districts). |
| Kenya 47 counties, 8 Sep 2021 | VERIFIED | State House Kenya, 8 Sept 2021 (47 counties: constitutional, not re-checked). |
| "Only real data is shown... STUB never displayed" | VERIFIED in code (`app.js`, `real.js`), but today **all three risk files are STUB**, so nothing is shown. |
| "Live countries show 'Real satellite + weather data (CHIRPS, MODIS, ERA5)'" | VERIFIED (`real.js` disclaimer). |
| Boundaries from geoBoundaries gbOpen | VERIFIED | `extract_signals.py` uses `WM/geoLab/geoBoundaries/600/ADM2`. |
| Kenya populations / crop share from 2019 census | UNVERIFIED | `prep_data.py` not audited; cite KNBS 2019 if kept. |
| Risk levels, SPI, NDVI, soil = real model output | PARTLY | Signals real (data_check.md); risk output pending export. |
| Hysteresis 2 up / 3 down | VERIFIED | `alert_engine.hysteresis`. |
| Two-family rule for level 2+ | VERIFIED | `alert_engine.raw_levels` (vegetation and (rain or soil)). |
| "Announcements can never exceed level 1 alone" | PARTLY | Vacuous: no announcement source is ingested. |
| "Six NGO-audience messages run to 2 segments" | WRONG (stale) | Measured: every template <= 158 chars for the longest ZWE name; NGO max 136. |
| Deep links `?country=Kenya&t=26` etc. | WRONG today | `data/risk/KEN.js` is an empty placeholder; Kenya is DATA IN PROGRESS. |
| 841 KB raw -> 46 KB | VERIFIED | `ken_raw.geojson` = 861,584 bytes. |
| three-globe wants clockwise rings | UNVERIFIED | plausible; not checked. |
| Colour ramp contrast >= 3:1 on `#1a1a19` | UNVERIFIED | not re-computed. |

### Spec ("SMS Shortage Early Warning - Project Spec.md")

| Claim | Verdict | Evidence |
|---|---|---|
| Zimbabwe declared national disaster 3 Apr 2024 (NBC link) | VERIFIED | as above. |
| Zambia Feb 2024, Malawi Mar 2024 declared earlier | VERIFIED | 29 Feb and 23 Mar 2024. |
| Africa's Talking covers 10 listed countries, not Zimbabwe or Morocco | PARTLY | Help article (May 2025) lists **11** countries (adds Ghana); Zimbabwe and Morocco indeed absent. |
| "World Bank estimate ... USD 2.8 saved per USD 1" | WRONG attribution | Figure is USAID, Cabot Venton 2018 "Economics of Resilience to Drought" (Kenya/Ethiopia/Somalia): "early response and resilience ... $2.8 for every $1". Not World Bank; framing is early response + resilience. |
| FEWS NET skipped cycles in 2025 | VERIFIED | Paused early 2025, relaunched 24 Jun 2025; gaps persisted Aug 2026 (NPR). |
| Earth Engine free for non-commercial / research | VERIFIED | EE terms (not re-fetched). |
| Twilio trial sends only to verified numbers | VERIFIED (known). |
| GSM-7 160 / UCS-2 70 chars | VERIFIED (standard). |
| Zimbabwe Cyber and Data Protection Act; Morocco Law 09-08 | VERIFIED | Act 5 of 2021 (zimlii); Dahir 1-09-15 of 2009. |
| MODIS over HLS for history back to 2000 | VERIFIED (MOD13Q1 from 2000). |
| "Real: WFP market prices from HDX" and "Real: ReliefWeb ... LLM extraction" at the demo | WRONG today | No price or ReliefWeb code exists in the repo; `data/sources.yaml` has `sources: []`. |
| Example SMS lengths (~155 / ~115 / ~120) | VERIFIED order of magnitude. |
| Placeholder `ZWE.MSV.MBR`, p = 0.68 | correctly labelled placeholder. |

### pitch.md (slides as drafted)

| Claim | Verdict | Evidence |
|---|---|---|
| **390:1 early destocking, Cabot Venton et al. 2012, Kenya** | VERIFIED, with caveats | Full report, Kenya bottom-up, Wajir Grasslands: "for every $1 spent on commercial destocking, $390 of benefits (avoided aid and animal losses) are gained." It is a **modelled HEA estimate** for one livelihood zone, destocking cost ~$4.50/household; the Ethiopia equivalent is $311 and the observed Moyale 2006 case (Abebe et al. 2008) is 41:1. Say "modelled, Wajir". |
| "CHIRPS v3 rain" | VERIFIED | EE asset `UCSB-CHC/CHIRPS/V3/PENTAD` exists (1981-2026). |
| "THREE INDEPENDENT FAMILIES" | PARTLY | rain and soil both weather; say "satellite + weather, 3 signals". |
| "Verified against an independent pull (max 2.5 % difference)" | VERIFIED | `data_check.md`: max rel diff 2.52 %, 30 unit-months. |
| HungerMap LIVE "National / first-level admin", "analysts in Rome" | UNVERIFIED | Relaunched 16 Apr 2026, 50+ countries; admin level not confirmed. Soften. |
| "Twilio has no two-way SMS in Morocco" | UNVERIFIED | not checked. |
| "Everything you see is real ... nothing is simulated" | TRUE only once `data/risk/ZWE.js` is non-STUB. |

### Brief (hunger_tech_brief.pdf) items we lean on

| Claim | Verdict |
|---|---|
| Kenya NDMA triggers at VCI3M < 35 | VERIFIED (Barrett et al., arXiv 1911.10339). Bands: 35-50 normal, 20-35 moderate, 10-20 severe, **< 10 extreme** - our "extreme" path (VCI < 20) is NDMA "severe". |
| "89 % hits, 4 % false alarms four weeks ahead" | research result, not NDMA operational - cite as such. |
| HungerMap LIVE "90+ countries" | OUTDATED - WFP now says 50+ (Apr 2026 relaunch). |

---

## 3. Top 5 weaknesses to fix before the demo (ranked)

1. **No real risk output on the globe yet, and the only lead-time numbers in the repo are from
   the STUB.** `pipeline/audit/out/metrics_ZWE.json` (precision 0.70, median lead 34.8 wk) was
   computed on `make_stub_risk.py`'s Gaussian bump centred on the declaration date - it is
   circular. Export the real model (`export_risk.py`), rerun `compare_ipc.py` without
   `--allow-stub`, delete or clearly rename the stub metrics, and only then fill slide 6.

2. **Emergency level is wrongly gated (methodology B1) and lead time ignores data latency (B2).**
   Level 3 fires on "calendar month >= April" in every year and on a satellite-only extreme path;
   `t` is the data month, so stated weeks-before-declaration are overstated by 4-6 weeks. Fix the
   gate (declaration list), and present lead time at issue date or say "data month" on the slide.

3. **Model skill is modest and uneven; the pitch must not oversell it.** CV mean PR-AUC 0.467
   vs persistence 0.373; `cant_plant` has no skill; Warning threshold tuned down to p >= 0.25
   with CV F1 0.25; hold-out ZWE ROC ~0.55. Lead with `no_grass` (ROC 0.82 at lead 1 - the
   livestock event the case is about), say the weaknesses first, and position the model as
   "rule + calibrated probability", not "AI predicts famine".

4. **Message content inconsistencies that a jury will read aloud.** Farmer "do not sell animals
   cheap" vs herder "sell weak animals now"; cooperative SMS leaks a probability to a farmer
   audience; frontend templates (7 audiences, `[link]`) differ from backend `composer.py`
   (5 roles, no link, name truncation); advice library and all templates are EN/FR only, no
   Shona/Ndebele; README still claims 2-segment NGO messages. Align frontend and backend text,
   reword, and mark advice "to be validated by WHH/AGRITEX" on the slide.

5. **Claims drift from what is built.** Spec and slide 4 promise prices, ReliefWeb text,
   "three independent families" and real SMS in Zimbabwe; the build has satellite + weather
   only, an empty `sources.yaml`, a Moroccan Android gateway, and an unsourced SMS price. Correct
   the spec attribution (2.8:1 is USAID 2018, not World Bank), label 390:1 as "modelled, Wajir",
   fix the Africa's Talking list (11 countries), and say "families 4 and 5 next" everywhere.

Minor but visible: one failing test in `pipeline/tests/audit`; `data/risk/KEN.js` deep links in
README do nothing; `pipeline/audit/methodology.md` still says DRAFT in places; stub metrics
files sit next to real ones in `pipeline/audit/out/`.
