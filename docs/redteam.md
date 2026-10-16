# Red-team review (jury simulation)

Role: hostile BCG Platinion / Welthungerhilfe jury member. Written 2026-10-16 (16:30-17:00 UTC)
from the `zimbabwe-real-data` working tree. Inputs read: `README.md`, the spec,
`/home/looooo/bcg/docs/hackathon_case.md`, `hunger_tech_brief.pdf`, `pipeline/CONTRACT.md`,
`pipeline/audit/{data_check,methodology,ground_truth}.md`, `pipeline/out/model_report.md`
(16:25 UTC), `data/risk/ZWE.js` (`sat-v1-ensemble-ZWE_KEN_MWI_ZMB`, 16:28 UTC),
`backend/README.md`, `docs/pitch.md`, `docs/demo_script.md`, pipeline and backend code.
Numbers marked "(own calc)" were recomputed read-only from `data/risk/ZWE.js` with the
`compare_ipc.py` functions. Web checks for load-bearing claims are in section 2.

State of the evidence at the time of writing:

| Artefact | State |
|---|---|
| `pipeline/data/signals_ZWE.parquet` | real; independent EE re-pull agrees (62 checks, 0 FAIL, max rel diff 2.52 %) |
| `pipeline/out/model_report.md` | real, first run 16:25 UTC |
| `data/risk/{ZWE,MWI,ZMB,KEN}.js` | **re-exported 16:52-16:54 UTC** ("Export B": 1-month latency, `t` = issue month, new thresholds, `cant_plant` dropped). The earlier 16:28 files ("Export A") are what every audit, the pitch and the demo script quote. See section 0 for the side-by-side. |
| `pipeline/audit/ground_truth.md` | real IPC comparison for ZWE (one headline number disputed below) |
| `pipeline/audit/judge/verdict.md` | present (16:45 UTC): **"OK WITH CAVEATS - ZWE and ZMB demo-able; MWI weak; KEN thin; Watch level broken everywhere"**. Its numbers agree with the own-calc numbers below. |
| `pipeline/alert_engine.py`, `export_risk.py`, `train.py` | edited 16:33-16:34 UTC **after** the risk files were written. `train.py` was re-run at **16:40** with 1-month data latency modelled: pooled CV mean PR-AUC fell from 0.467 to **0.42** (ensemble), `no_grass` ROC at lead 1 from 0.82 to **0.68**, `cant_plant` still no skill; thresholds still 0.25 with a CV Watch alarm rate of 0.61. Superseded by the 16:49 report and the 16:52-16:54 export (Export B). `judge.py` and `compare_ipc.py` have **not** been re-run on Export B by the team; the Export-B IPC numbers in this document are my own read-only recomputation with the `compare_ipc.py` functions. |
| `pipeline/out/model_report.md` rev. **16:49** | `cant_plant` **dropped** from the model (now 2 events); thresholds re-tuned to `p_watch 0.525, p_warn 0.50, p_emerg 0.95, p_fast 0.775` with CV Watch rate **0.21** (was 0.61) and Warning rate 0.054 (F1 0.12, i.e. very conservative); pooled CV mean PR-AUC **0.55 vs persistence 0.48 vs rule 0.46** over the two remaining events (not comparable with the 0.42/0.37 three-event figure still on pitch slide 6 - update the slide after the re-export and say "two events"). Risk files still 16:28. |
| `pipeline/audit/code_review.md` | present (17:00 UTC): confirms hysteresis, NaN handling, ids, SMS lengths; flags Emergency gate (HIGH), Watch (HIGH, "fixed, verify after rerun"), 181 ZWE Warning/Emergency unit-months with **empty `drivers`** during hysteresis hold (MEDIUM) |
| `pytest pipeline/tests/audit` | 99 passed, **1 failed** (`test_labels_invariant_to_non_vci_signals`; `cant_plant` labels use SPI/soil by design, the test is stale) |

---

## 0. The numbers the jury will remember - and which export they come from

**UPDATE 17:03 UTC - a third export ("Export C") replaced B while this was being written; see the
paragraph after the table. The pitch (17:05) and demo script (17:04) now quote Export B numbers that
are no longer in the file. Freeze the export before anyone writes another number.**

**There are two very different Zimbabwe exports.** `pitch.md` rev. 17:03 has already switched to
Export B (22 Watch / 4 Warning issued end of March, 26 Warning end of April, 48 by June; old
numbers moved to a "stale" appendix), and `demo_script.md` rev. 17:04 follows it (Hwange rises at
t=63 with `no_grass`, jury joins as **herder**, "do not promise a Mbire Warning") - good. Only
`verdict.md` and `ground_truth.md` still describe Export A; re-run `judge.py` and `compare_ipc.py`
so slide 6 can cite an audit of the file that is actually on the globe.

| | Export A (16:28 UTC) - `verdict.md`, `ground_truth.md` | **Export B (16:52-16:54 UTC) - `data/risk/*.js` now, pitch.md 17:03, demo_script.md 17:04** |
|---|---|---|
| Rules | no latency; `t` = data month; `p_watch = p_warn = 0.25`; 3 events incl. `cant_plant` | 1-month data latency (`t` = issue month, describes month t-1); `p_watch 0.525, p_warn 0.50, p_emerg 0.95, p_fast 0.775`; `cant_plant` dropped |
| Watch share of all unit-months 2019-24 | 69 % (100 % of districts every Jan-May) | **15-20 %** (fixed) |
| Districts ever at Warning+, Oct 2023-Jun 2024 | 80 of 91 | **48 of 91** |
| First-Warning cohorts | Dec-23 13, Jan 1, Feb 4, Mar 28, Apr 26, May 7, Jun 1 (data months) | **Mar-24 4, Apr 22, May 17, Jun 5** (issue months) |
| Warning before the 3 Apr 2024 declaration | 46 (data month) / 14 (with latency), median 8.3 wk | **4 of 91**; 22 more in the April issue month, i.e. **the same month as the declaration** |
| Emergency unit-months with no declaration behind them | 41 districts May-Jul 2020, 16-19 in 2023 | 4 units Jan-Mar 2019 only; 2024: 4-8 units Apr-Jul |
| IPC 2023/24: transitions caught (of 57) | 53, recall 0.93, precision 0.72 | **31, recall 0.54, precision 0.71** |
| IPC all seasons, transition P / R / F1 | 0.47 / 0.54 / 0.50 (persistence 0.24 / 0.44 / 0.31) | **0.53 / 0.28 / 0.37** (persistence unchanged) |
| False-alarm season 2022/23 | 29 Warning districts, 0 transitions | **3 Warning districts** |
| Our Warning vs FEWS NET's own IPC3+ projection | median 8.7 wk earlier (72 % of hits) | **median 4.3 wk earlier, 68 % of 31 hits** - and FEWS NET flagged all 57 |
| Demo district Hwange | Warning at t=59 (Dec 2023 data), `crop_failure` | **Warning at t=63 (Apr 2024 issue)**, `no_grass`; Binga never above Watch; Mbire never above Watch |
| Wet 2020/21 season | 0 Warnings | 0 Warnings |

Read across: Export A over-alerts (Watch everywhere, Emergency in 2020) but shows a 13-week lead in
13 Matabeleland districts; Export B is clean (quiet Watch, no phantom Emergencies, 3 false-alarm
districts in 2022/23) but **has essentially no lead over the national declaration** - 4 districts
before it, 22 in the same month - and catches only half the IPC transitions. Neither export supports
the slide-6 line "46 of 91 before the declaration, 13 districts 13 weeks early" as it stands, because
that line is from A and the globe now shows B. The team has to choose one story and regenerate
slide 6, the demo script (Hwange t=59 -> t=63; `crop_failure` -> `no_grass`, so the jury member must
join as **herder**, not farmer) and the judge/ground-truth audits from the same file. My
recommendation as a juror: show B, and sell "we stay quiet when it rains and we are honest about
lead time" rather than weeks of foresight the data does not support.

Still real in both: the 10 driest districts by SPI-3 were all warned (A); zero Warnings in the wet
2020/21 season; Zimbabwe's south-east (Masvingo, Chiredzi, Chivi, Mwenezi, Zaka, Beitbridge) never
reaches Warning in either export because the vegetation family never fires there.

**Export C (ZWE 17:03, MWI/KEN 17:03, same thresholds, declaration gate removed from the Emergency
rule - methodology B1 "partly fixed", M8 "over-corrected"):** Warning+ in Oct 2023-Jun 2024 falls to
**33 of 91**, first Warnings **Apr 9 / May 17 / Jun 7**, **none before the declaration**. At t=62
(end of March): 22 Watch, **0 Warning**; at t=63 (end of April): 60 Watch, **9 Warning** - Bindura
Urban, Chiredzi Urban, Chitungwiza, Epworth, Harare, Harare Rural, Marondera, Mudzi, Ruwa, i.e.
mostly Harare-periphery urban units with event `no_grass`. **Hwange never leaves Watch**, so the
17:04 demo script ("JOIN Hwange herder, run alerts at t=63") produces no event; Mbire, Binga,
Tsholotsho, Bulilima and Plumtree are all Watch-only too. Emergency: one unit-month May-Jul 2024,
none elsewhere (gate fixed). IPC 2023/24: 23 of 57 transitions, precision 0.74, recall 0.40; all
seasons F1 0.30 vs persistence 0.31 - **the model no longer beats "same as last year" on IPC
transitions**. Watch share of unit-months 15-32 %. Half of the remaining Warning months (70 of 146)
are hysteresis holds showing "1/3 sources agree".

Juror's reading: A over-alerts, C under-alerts to the point of having no demo district and no lead,
B is the only one with a coherent story ("called in the declaration month, quiet in wet years,
4 districts ahead"). Whatever is chosen, **freeze `data/risk/*.js` now**, re-run `judge.py` and
`compare_ipc.py` on that exact file, and regenerate slide 6 and the demo script from those outputs.
Every "[verified]" below refers to the export named in the row; numbers from different exports must
never appear on the same slide.

---

## 1. The 15 hardest jury questions, with the strongest honest answer

Format: question / honest answer with our numbers / the slide or demo moment that proves it.

### Q1. "Isn't this just WFP HungerMap LIVE (or FEWS NET) with an SMS bolted on?"
**Answer.** Three real differences and one honest overlap. (a) Unit and history: 91 ADM2 units,
monthly, 2001-2024, scored out-of-sample; HungerMap (relaunched 16 Apr 2026, 50+ countries, forecasts
for 16 hotspots) is a current-situation nowcast at national/sub-national level - its admin level for
Zimbabwe is unverified, so do not put "ADM1" on the slide. (b) Output: an event type ("no grass" in
248 of 367 Warning unit-months in 2023/24), drivers and a 1-3 month horizon, not a hunger map.
(c) Last mile: one GSM-7 segment to a feature phone, two-way, human-approved. The overlap: FEWS NET's
own ML1/ML2 projections flagged **all 57** transitioning districts; our Warning came a median 8.7 weeks
earlier (72 % of hits) *before* latency, i.e. roughly 3-5 weeks after it. So the claim is "same evidence,
per district, per audience, weeks earlier than the declaration, delivered" - not "we beat FEWS NET".
**Proof moment.** Slide 7 (soften the HungerMap cells); detail panel with event + drivers + herder SMS.

### Q2. "How do you know the warnings were right?"
**Answer.** Two independent checks. (1) Satellite labels (VCI < 35; SPI < -1 and soil z < -1),
leave-one-agricultural-year-out 2001-2022, 22 folds, 80,648 rows; 2023/24 locked away and scored
once. Latest report (16:49, latency modelled, two events): pooled CV mean PR-AUC **0.55** (ensemble)
vs **0.48** persistence vs **0.46** plain rule; `no_grass` ROC 0.62 (0.68 at lead 1), `crop_failure`
ROC 0.57; `cant_plant` was dropped because it had no skill (ROC 0.47). (2) Against FEWS NET IPC
(84 of 91 districts matched, 27 snapshots), current export: 2023/24 transition precision **0.71 /
recall 0.54** vs persistence 0.43 / 0.35; all five seasons F1 **0.37 vs 0.31**; only 7 of 76
district-season Warnings 2019-24 were not followed by IPC3+ (precision 0.91). And the bad news, said
first: recall is low (31 of 57 transitions in 2023/24; 1 of 47 in the economic crisis of 2021/22),
and on "is the district in crisis at all" the persistence baseline beats us (F1 0.755 vs 0.38)
because much of Zimbabwe's IPC3+ is chronic. Two more things the judge and methodology audit will say if we do
not: the hold-out "PR-AUC 0.80" is a base-rate artefact (ZWE hold-out ROC 0.53-0.58), and skill at
leads 2-3 months is near chance (ZWE-only CV ROC 0.54-0.67; methodology M7) - the honest pitch is
"rule fusion + calibrated probability, ML as challenger", not "predicts three months ahead". Note
the 16:40 latency-aware retrain is weaker still (pooled mean PR-AUC 0.42, `no_grass` lead-1 ROC
0.68): once you stop peeking one month ahead, the lead-1 skill was mostly persistence of the last
observed month.
**Proof moment.** Slide 6 with those exact rows; `ground_truth.md` and `verdict.md` on a backup tab.

### Q3. "What if the forecast is wrong and a herder sells cattle for nothing?"
**Answer.** The herder message is gated four times: vegetation **and** (rain or soil) must agree,
calibrated p over threshold, two consecutive runs, and a human approves every Warning; nobody is
messaged at Watch. The action is low-regret: "sell weak and old animals early, keep breeding females"
is LEGS destocking guidance; a false alarm costs a few culls sold early, a miss costs the herd. The
economics we quote - Cabot Venton et al. 2012 (DFID), Kenya bottom-up, Wajir Grasslands: "for every $1
spent on commercial destocking, $390 of benefits (avoided aid and animal losses)" - is a **modelled HEA
estimate for one livelihood zone**, so say "modelled". Our own false-alarm record: 30 of 163
district-season Warnings 2019-2024 (**18 %**) were not followed by IPC3+ in Export A; in Export B it
is **7 of 76 (9 %)** and 2022/23 has 3 Warning districts instead of 29. The counter-fact to show:
**zero Warnings in the wet 2020/21 season** in both exports - the system stays quiet when it rains.
So the honest pilot design is institutions first, farmer tier when precision is proven.
**Proof moment.** Alert feed "pending approval"; slide 3 with the "modelled" caveat visible.

### Q4. "Who pays?"
**Answer.** Farmers and herders never pay. WHH itself has run forecast-based action in Zimbabwe since
2020 and **activated it in Mbire, Mount Darwin and Rushinga in July/August 2024 with EUR 500,000**
(welthungerhilfe.org; anticipation-hub.org). Our offer is the district trigger + two-way SMS layer
inside that budget line; other payers are WFP country offices, the Civil Protection Unit and index
insurers. Running cost is small: free satellite inputs (Earth Engine, non-commercial), one model run a
month, SMS at cost. The Zimbabwe per-SMS price is **unsourced** (third-party guides range US$0.003 to
US$0.29); say "gateway quote pending", never a number.
**Proof moment.** Slide 8; add the WHH 2024 activation as the anchor-customer story.

### Q5. "Why SMS in 2026?"
**Answer.** POTRAZ Q3 2025: 16.4 M active subscriptions, 104.8 % subscription penetration, but only
about half of adults own a smartphone (World Bank 2024, via secondary source). The case brief's users
are "communities whose lives depend on their land and livestock". SMS reaches every phone with no data
plan; our templates are GSM-7, one segment (**max 158 chars** with the longest district name, "Uzumba
Maramba Pfungwe"). USSD and IVR are the scale-up for literacy; smartphones for field staff.
**Proof moment.** Live SMS to a jury phone; the character counter on screen.

### Q6. "Does it work in Zimbabwe when your gateway is a Moroccan Android phone?"
**Answer.** The capcom6 Android gateway with a local SIM is the demo path; it proves the two-way loop,
not the deployment. Africa's Talking does **not** cover Zimbabwe (11 countries listed, May 2025;
Zambia and Malawi are covered). Zimbabwe needs a local aggregator or Infobip/Twilio with a registered
sender ID (weeks) - hence slide 9. Consent and data protection under the Cyber and Data Protection Act
(Act 5 of 2021, POTRAZ) are built in: explicit YES, STOP always wins, monthly cap of 6 alerts,
opt-out and consent timestamps in the `users` table. Honest gap (security audit P2/P3/P6): phone
numbers are stored in clear, there is no retention purge and `consent_source` is not recorded - say
"demo database; the pilot schema has `phone_enc` + `phone_hash` and a retention limit".
**Proof moment.** Slide 9; `backend/README.md` switch "sim -> Android" is config-only.

### Q7. "The case says northern Zimbabwe. Wasn't the drought worst in the south - and did you catch the south?"
**Answer.** Food-security impact was worst in Matabeleland South and Masvingo (FEWS NET Sep/Oct 2024:
3,500+ cattle deaths in Mat South), but the climate shock also hit the north: FEWS NET's October 2024
outlook says parts of Mashonaland Central, Mashonaland West and Midlands had "the driest mid-January
through March period on record", and WHH's own trigger fired in Mbire, Mt Darwin and Rushinga. Our
model is national. Honest weakness: the 11 districts that **never** reached Warning in 2023/24 are
mostly southern (Masvingo, Chiredzi, Chivi, Mwenezi, Zaka, Beitbridge, Chimanimani). Reason: the
vegetation family never fired there (January 2024 greenness was above normal in the south; NDVI z
+0.4 in Beitbridge) so the two-family rule held the level at Watch - the rule that stops false alarms
also costs recall. Beitbridge and Uzumba Maramba Pfungwe were IPC3+ from Feb 2024 and we missed both;
in Export B the never-Warning list grows to 43 districts and includes **Mbire, Mount Darwin, Rushinga,
Binga, Kariba and Gokwe** - i.e. WHH's own anticipatory-action districts stay at Watch all season.
The same failure explains Malawi (8 of 28 warned vs 23 declared) - the judge's fix 3 (an early
Warning path when rain **and** soil are both strong in Dec-Feb) needs a spec change because rain and
soil are not independent families; say so if asked.
**Proof moment.** Be the first to show the miss map (`judge_ZWE.png`); then the northern demo district (see Q10).

### Q8. "How did you avoid overfitting with so few droughts?"
**Answer.** We never learned "the drought year": labels are per district-season satellite indices
(~1,000 labelled district-seasons per country). Leave-one-agricultural-year-out holds out every
district of a year together; LightGBM is small (15 leaves, depth 5, L2 = 5, inner-year early stopping);
isotonic calibration is cross-fitted; thresholds tuned on CV out-of-fold only; 2023/24 and Kenya
2020-22 scored once at the end. The visible cost is honest, modest skill (CV ROC 0.49-0.71 by event).
Disclosed optimism: the 2001-2020 climatology includes the CV years (methodology m3). If asked
"why not a foundation model?": we ran TimesFM 2.5 zero-shot on VCI as a challenger
(`timesfm_report.md`) - 6-15 % lower MAE than persistence but fewer VCI<35 events detected, so it
is not in the product.
**Proof moment.** Slide 6 "rules the judges can hold us to"; `model_report.md`.

### Q9. "Your 'three independent families' are all weather. Where are prices and official text?"
**Answer.** Correct: rain (CHIRPS v3) and soil (ERA5-Land, a model product) are both weather; only
vegetation (MODIS) is an independent observation. The Warning rule already encodes that: vegetation
**and** (rain or soil), never rain + soil alone. Prices (WFP/HDX) and ReliefWeb/FEWS NET text are in
the schema and spec but **not built** (`data/sources.yaml` is empty). Stop saying "three independent
families" (slide 4, extension SMS "N/3 sources agree"); say "satellite + weather, 3 signals, 2
independent families". And be ready for the follow-up "then why does this Warning district say 1/3
sources agree?": because the level is being *held* by the 3-run stand-down rule after the raw
signal eased - half of all Warning months in the export are holds (see weakness 4b).
**Proof moment.** CONTRACT.md rule; slide 9 item 1.

### Q10. "Weeks before the declaration - measured how, and what about data latency?"
**Answer.** The timeline `t` is the *data month*; CHIRPS final, MOD13Q1 and ERA5-Land are complete
2-6 weeks after month end (methodology B2). `ground_truth.md` says "72 of 80 warned districts before
the 2024-04-03 declaration (median 4.7 weeks)" - **do not use that line**: it counts the 26 districts
whose first Warning is the *April 2024* data month, which cannot precede 3 April. The judge
(`verdict.md`) says the same: for Export A, 46 of 91 by "available on the 1st of the next month",
**14 of 91 (median 8.3 weeks) with latency**. But the file on the globe now is **Export B**, which
already builds the latency in: there, **4 districts** are at Warning before the declaration and
**22 reach it in the April issue month**, the month of the declaration; Hwange rises at t=63 (April),
Binga and Mbire never leave Watch. So the truthful sentence for Export B is: "the system called
Warning in 26 districts in the same month the government declared, with 4 ahead of it; its value in
2023/24 was coverage and the per-district action, not weeks of lead". If the team wants a lead-time
story it must go back to Export A's thresholds and then own the 69 % Watch rate and the 2020
Emergencies. Pick one; do not mix numbers from both.
**Proof moment.** Scrub Feb -> Apr 2024 on Hwange (B); say "latency is already in these dates".

### Q11. "FEWS NET and IPC are your truth. Aren't they late, coarse and now politically fragile?"
**Answer.** FEWS NET was paused by the US aid freeze in early 2025, relaunched 24 June 2025, and still
had coverage gaps in Aug 2026 (NPR). That is the argument for an open-data district trigger with
local ownership (brief section 9). We use FEWS NET only to *evaluate*: Current Situation maps exist 3
times a year, so our IPC lead times sit in 4-month bins (median 26 weeks raw, **8.7 weeks
conservative**, ~3-5 weeks after latency). Zambia has no FEWS NET IPC after 2017, so the Zambia
fallback cannot be scored.
**Proof moment.** `fetch_ipc.py` provenance (`_meta.json` with URL + sha256).

### Q12. "Your Emergency level is supposed to need an official declaration. Your file fires it in 2020 and 2023."
**Answer.** True for Export A (methodology B1, code_review #1): `after_decl` is "agricultural month
>= April" in every year plus a satellite-only extreme path, so level 3 fired in **41 districts in
May-Jul 2020** and 16-19 in May-Aug 2023 with no declaration. In Export B (p_emerg 0.95) the
phantom Emergencies shrink to 4 units in Jan-Mar 2019 and 4-8 units in Apr-Jul 2024 - but the gate
is still the real declaration month, so the red that appears in April 2024 is hindsight, not a
prediction. Say "Emergency means 'after an official declaration' in our rules" and never claim the
red as a model result. Fix: gate on the declaration list, cap the extreme path at Warning + `severe`.
**Proof moment.** Only after the fix; otherwise do not dwell on red districts.

### Q13. "A farmer and a herder in the same district get opposite advice; and why does your probability jump from 100 % to 43 % and back?"
**Answer.** Messages: farmer "do not sell animals cheap" vs herder "sell weak animals now" are
different decisions (no panic sales at collapsed prices vs early destocking of culls), but read aloud
they contradict; the cooperative SMS also leaks "shortage risk NN %" to a farmer-facing audience.
Reword before the demo. Probability: `p` is the max over candidate events; the Nov 2023 "1.0" in
Binga/Hwange/Lupane is the `cant_plant` **nowcast** (planting-window condition already observed),
the Dec "0.47" is a 1-3 month forecast of crop failure (methodology M2). Label nowcasts as such in
the panel and never count them as lead time.
**Proof moment.** Audience tabs after the reword; panel shows "nowcast" vs "forecast".

### Q14. "What does the AI do, and what happens when it is wrong?"
**Answer.** Claude Haiku only classifies inbound SMS into a fixed intent list (JOIN, 1/2/3 report,
advice, help, STOP) with keyword fast-paths that bypass the LLM; STOP always wins; advice is picked
from `backend/advice.yaml` (12 entries, "demo content to be validated by WHH/AGRITEX"), never
generated; "we can't manage" opens a help request for a human; district names must match the
gazetteer. No LLM touches a risk level. When Claude is down the router falls back to keywords
(tested: 9/9 answered with an invalid key). Weakness: replies are English/French only; Shona and
Ndebele are understood but not answered; and the sync Claude call blocks the server (robustness
#9), so a slow answer can make the dashboard say "backend offline" mid-demo.
**Proof moment.** Jury member texts free text; intent label and human hand-off appear in the feed.

### Q15. "Watch is on in every district every year. What is it for?"
**Answer.** It was (Export A: 69 % of all unit-months, 100 % of districts each Jan-May, precision =
base rate). Export B fixes it: Watch covers **15-20 %** of unit-months, 13 of 91 districts in Oct-Nov
2023, and Watch only goes to NGOs and officers. Say so, and keep the prepared line from the demo
script ("yellow is an early, low-confidence flag; orange is where the system commits"). If the team
reverts to Export A for the lead-time story, this answer collapses - another reason to choose B.
**Proof moment.** Oct 2023 map: 78 grey, 13 yellow, nothing orange.

---

## 2. Fact check of README.md, the spec, pitch.md and the brief

Legend: VERIFIED / PARTLY / UNVERIFIED / WRONG.

### README.md

| Claim | Verdict | Evidence |
|---|---|---|
| Zimbabwe 91 districts | PARTLY | 91 = geoBoundaries gbOpen ADM2 units incl. urban units (Hwange Urban, Kariba Urban, Plumtree...). Zimbabwe has ~63 rural districts; say "91 admin-2 units". |
| Disaster declared 3 Apr 2024 | VERIFIED | Reuters / The New Humanitarian 2024-04-03; Mnangagwa; >US$2 bn appeal. |
| Malawi 28 districts, 23 Mar 2024 | VERIFIED | AP 2024-03-24: state of disaster in 23 of 28 districts; OCHA. |
| Zambia 116 districts, 29 Feb 2024 | VERIFIED | Cabinet Office statement; Al Jazeera (84 of 116 districts). |
| Kenya 47 counties, 8 Sep 2021 | VERIFIED | State House Kenya, 8 Sept 2021. |
| "Only real data is shown; STUB never displayed" | VERIFIED in code; ZWE is now real, MWI/ZMB still STUB, KEN empty. |
| Live disclaimer "Real satellite + weather data (CHIRPS, MODIS, ERA5)" | VERIFIED (`js/real.js`). |
| Boundaries: geoBoundaries gbOpen | VERIFIED | `WM/geoLab/geoBoundaries/600/ADM2`. |
| Kenya populations / crop share from 2019 census | UNVERIFIED | `prep_data.py` not audited; cite KNBS 2019 if kept. |
| Hysteresis 2 up / 3 down | VERIFIED | `alert_engine.hysteresis`. |
| Two-family rule for level 2+ | VERIFIED | vegetation and (rain or soil). |
| "Announcements can never exceed level 1 alone" | PARTLY | Vacuous: no announcement source is ingested. |
| "Six NGO-audience messages run to 2 segments" | WRONG (stale) | All templates <= 158 chars for the longest ZWE name; NGO max 136. `frontend_qa.md`: 29,363 real messages, 0 over 160 septets even counting `[link]` extension characters (the UI counter under-counts those by 4). |
| README:27 "`data/risk/KEN.js` is an empty placeholder" | WRONG (stale) | Kenya has real output since 16:29. |
| Deep links `?country=Kenya&t=26`, `t=33&county=Marsabit`, `t=48&county=Turkana` | WRONG today | `data/risk/KEN.js` is an empty placeholder. |
| Demo script "all green" at Oct 2023 | WRONG | Real file: 46 green, 45 Watch in Oct 2023; 77 Watch in Nov 2023. |
| 841 KB raw -> 46 KB | VERIFIED | `ken_raw.geojson` = 861,584 bytes. |
| three-globe wants clockwise rings; colour ramp contrast >= 3:1 | UNVERIFIED | not re-checked. |

### Spec

| Claim | Verdict | Evidence |
|---|---|---|
| Zimbabwe 3 Apr 2024 (NBC); Zambia Feb, Malawi Mar 2024 | VERIFIED | as above. |
| Africa's Talking covers 10 listed countries, not Zimbabwe/Morocco | PARTLY | Help article (May 2025) lists **11** (adds Ghana); Zimbabwe and Morocco absent - correct. |
| "World Bank estimate ... USD 2.8 saved per USD 1" | WRONG attribution | USAID, Cabot Venton 2018 "Economics of Resilience to Drought" (Kenya/Ethiopia/Somalia): "early response and resilience ... $2.8 for every $1". Not World Bank. |
| FEWS NET skipped cycles in 2025 | VERIFIED | paused early 2025; relaunched 24 Jun 2025; gaps Aug 2026 (NPR). |
| Earth Engine free for non-commercial use; Twilio trial = verified numbers only; GSM-7 160 / UCS-2 70 | VERIFIED (standard terms). |
| Zimbabwe Cyber and Data Protection Act; Morocco Law 09-08 | VERIFIED | Act 5 of 2021 (zimlii); Dahir 1-09-15 of 2009. |
| MODIS over HLS for history back to 2000 | VERIFIED. |
| "Real: WFP prices from HDX"; "Real: ReliefWeb reports + LLM extraction" at the demo | WRONG today | no such code; `data/sources.yaml` has `sources: []`. |
| "Escalate only when 2+ independent source families agree" | PARTLY | implemented as vegetation + weather; both weather sub-families are not independent of each other. |
| KPI "precision/recall of Warning+ vs FEWS NET/IPC Phase 3+ transitions vs persistence" | VERIFIED delivered | `ground_truth.md`: 0.72/0.93 (2023/24), 0.47/0.54 all seasons; persistence 0.24/0.44. |

### pitch.md

| Claim | Verdict | Evidence |
|---|---|---|
| **390:1 early destocking, Cabot Venton et al. 2012, Kenya** | VERIFIED with caveats | Full DFID report, Kenya bottom-up (Wajir Grasslands): "for every $1 spent on commercial destocking, $390 of benefits (avoided aid and animal losses) are gained"; destocking cost ~$4.50/household. **Modelled** HEA estimate for one livelihood zone; Ethiopia equivalent $311; the observed Moyale 2006 case (Abebe et al. 2008) is 41:1. Say "modelled, Wajir, Kenya". |
| "CHIRPS v3 rain" | VERIFIED | EE asset `UCSB-CHC/CHIRPS/V3/PENTAD` (1981-2026). |
| "THREE INDEPENDENT FAMILIES" | PARTLY | see Q9. |
| "Verified against an independent pull (max 2.5 % difference)" | VERIFIED | `data_check.md`. |
| HungerMap LIVE "National / first-level admin", "analysts in Rome" | UNVERIFIED | relaunched 16 Apr 2026, 50+ countries; admin level not confirmed. |
| "Twilio has no two-way SMS in Morocco" | UNVERIFIED. |
| "Globe -> Zimbabwe, Oct 2023: all 91 districts green" | FIXED in `demo_script.md` rev. 16:57 ("most are yellow, nothing is orange", with a prepared answer on Watch); check pitch slide 5 step 1 says the same. |
| pitch.md rev. 16:51 UTC: 46 of 91 / 13 districts 13 wk / 14 of 91 8 wk / recall 93 % | SUPERSEDED - those were Export A numbers; rev. 17:03 marks them stale. |
| pitch.md rev. 17:03 slide 6: Watch issued end of March 2024 **22 of 91**; Warning **4 of 91**; Warning end of April **26**; by June **48**; Watch Oct 2023 13 of 91 (was 91) | VERIFIED against Export B (own calc: cohorts Mar 4 / Apr 22 / May 17 / Jun 5; Oct 2023 13 Watch). Add the IPC line for B once `compare_ipc.py` is re-run: 31 of 57 transitions, precision 0.71, recall 0.54 (own calc). |
| pitch.md 17:03 / demo_script.md 17:04: jury member texts **"JOIN Hwange herder"**, alerts run at t=63 | VERIFIED on Export B | Hwange t=63: level 2, p 0.69, event `no_grass`, agreeing 3 (own calc). `composer.audiences()` routes `no_grass` Warnings to herders. Earlier drafts ("JOIN Hwange farmer", t=59) were only valid for Export A. |
| demo_script.md 17:04: t=62 "22 at Watch incl. Mbire, Karoi, Rushinga; 4 at Warning (Harare units)"; t=63 "26 at Warning, 4 Emergency" | VERIFIED on Export B (own calc: Mar 4 / Apr 22 new Warnings; level-3 count 4 in Apr 2024). |
| `pipeline/out/timesfm_report.md` (17:04): TimesFM 2.5 zero-shot VCI forecast | Real challenger result, not in the product: beats persistence on MAE by 6-15 % (lead 1-3) but detects **fewer** VCI<35 events (hit rate 0.69 vs 0.72 at lead 1, 0.41 vs 0.53 at lead 3). Use as the answer to "why not a foundation model?": tried, marginal, not shipped. |
| "Everything you see is real ... nothing is simulated" | TRUE for all four countries since 16:31 UTC (ZWE, MWI, ZMB, KEN exported). Malawi/Zambia/Kenya have no IPC audit yet (Zambia has no FEWS NET IPC after 2017). |

### Brief (hunger_tech_brief.pdf) items we lean on

| Claim | Verdict |
|---|---|
| Kenya NDMA triggers at VCI3M < 35 | VERIFIED (Barrett et al., arXiv 1911.10339). Bands: 35-50 normal, 20-35 moderate, 10-20 severe, **< 10 extreme** - our "extreme" path (VCI < 20) is NDMA "severe". |
| "89 % hits, 4 % false alarms four weeks ahead" | research result, not NDMA operational; cite as such. |
| HungerMap LIVE "90+ countries" | OUTDATED - WFP says 50+ since the Apr 2026 relaunch. |
| Zimbabwe 2023/24 maize output forecast -72 % | not re-checked. |

---

## 3. Top weaknesses to fix before the demo (ranked; 1-5 are the model/content asks, 6 is stage operations, 7 is security)

1. **Two exports, one story: the pitch, demo script and audits quote Export A (16:28) while the
   globe shows Export B (16:52-16:54).** A: Watch on 69 % of unit-months, Emergency in 41 districts
   in 2020, but "46 of 91 before the declaration, 13 districts 13 weeks early". B: Watch 15-20 %,
   no phantom Emergencies, 3 false-alarm districts in 2022/23, but only **4 of 91** before the
   declaration, 22 in the declaration month, Hwange rising at t=63 not t=59 and WHH's own districts
   (Mbire, Mt Darwin, Rushinga) never above Watch. C (17:03, now on disk): 33 of 91, **0** before the
   declaration, 9 in the declaration month (Harare periphery), Hwange never above Watch, model no
   longer beats persistence on IPC transitions - the demo script's live moment has no event to
   approve. Decide now which file is on stage, **freeze it**, then regenerate `verdict.md`,
   `ground_truth.md`, slide 6 and `demo_script.md` from that file. Recommended: B (restore its
   thresholds/rules), with the honest line "called in the month of the declaration, quiet when it
   rains".

2. **The Emergency gate is still hindsight.** In both exports level 3 can only appear from the
   month the government actually declared (`after_decl`, code_review #1); B merely makes it rarer
   (p_emerg 0.95). Either remove the gate (season-phase gate or signal-only rule) or label red as
   "after official declaration" in the UI and never call it a prediction. Also carry drivers forward
   during hysteresis holds (181 unit-months with "WARNING, 0 drivers" in A; re-check in B).

3. **The model misses the hungriest places and is honest-but-modest everywhere else.** Zero
   Warnings in Masvingo, Chiredzi, Chivi, Mwenezi, Zaka, Beitbridge in both exports (vegetation lags
   rain; the two-family rule holds the south at Watch); the same failure gives Malawi 8 of 28
   districts (A). CV mean PR-AUC 0.55 vs 0.48 persistence (two events, latency modelled); `cant_plant`
   dropped for no skill; lead-2/3 skill near chance (methodology M7); hold-out "PR-AUC 0.80" is a
   base-rate artefact; B catches 31 of 57 IPC transitions in 2023/24, 1 of 47 in 2021/22. Lead with
   `no_grass` (the livestock event the case is about), show the miss map yourself, and frame the
   product as "rule + calibrated probability + human", not "AI predicts famine". Do not pitch Watch
   lead times or Malawi (judge section 5). The judge's fix 3 (early rain+soil path in Dec-Feb) is the
   one change that could restore lead time without re-opening the Watch flood - but it needs a spec
   change on family independence.

4. **Screen content that contradicts "nothing is simulated" or the two-family rule.**
   (a) `js/app.js:438-441` computes "SMS sent to date" as population x 0.11 x audiences/3 and
   `js/real.js:128` shows "people" = pop x (0.25 + 0.20 x level) - both invented (frontend_qa B2);
   hide them or take them from the backend. (b) In Export B, **219 of 428 Warning+ unit-months show
   "1/3 sources agree" or no vegetation family** (own calc, confirmed frontend_qa). All 219 are
   hysteresis holds (the level is kept while the raw level falls), so the rule is not violated on
   entry - but the panel does not say "holding", 58 of them have empty drivers and 10 are Emergency
   rows with <2 families. Add a "holding since <month>" line and carry drivers forward, or a juror
   will click one. (c) Levels drop two steps in one month 103 times (3-run stand-down jumps from the
   held level straight to the new one) - visible as orange -> grey; explain or smooth. (d) Jan 2019
   (t=0) opens with 31 Warning / 4 Emergency districts (2018/19 drought tail) - the feed never shows
   them (code_review #7).
   **Message content a jury will read aloud.** Farmer "do not sell animals cheap" vs herder "sell
   weak animals now"; cooperative SMS leaks a probability; extension SMS says "N/3 sources agree"
   (two are weather); frontend templates (7 audiences, `[link]`) differ from backend `composer.py`
   (5 roles, no link, name truncation); advice library and templates are EN/FR only; README still
   claims 2-segment NGO messages. Align frontend and backend text, reword, keep the "to be validated
   by WHH/AGRITEX" label visible.

5. **Claims drift from what is built.** Spec and slide 4 promise prices, ReliefWeb text, "three
   independent families" and real SMS in Zimbabwe; the build has satellite + weather only, an empty
   `sources.yaml`, a Moroccan Android gateway, an unsourced SMS price, and no IPC audit for
   Malawi, Zambia or Kenya (all four countries are exported now, but only Zimbabwe is validated).
   Correct the 2.8:1 attribution (USAID 2018, not World Bank), label 390:1 "modelled, Wajir", fix
   the Africa's Talking list (11 countries), say "families 4 and 5 next" everywhere, and re-check
   the Kenya deep links in README against the real `KEN.js` before using them.

6. **(Operational, from `pipeline/audit/robustness.md`) The live SMS moment can stall or lie on
   stage.** Sync Claude calls block the FastAPI event loop (`/health` stalls, UI shows "backend
   offline" and hides "Run alerts" while Haiku thinks); a black-holed network means 48 s before the
   keyword fallback; the first SMS after start takes 6-14 s (cold client); the advice path takes
   10 s vs a 4 s UI timeout; and when the Android gateway fails, the feed still says "sent to N
   users". Apply fixes 1, 2 and 5 of that audit (threadpool, 6 s timeout, count only non-failed
   sends) or at least run `scripts/start_demo.sh` (warm-up) and send `JOIN` first.

7. **(Security, from `pipeline/audit/security.md`) If the backend is tunnelled with ngrok as the
   README says, anyone with the URL can approve a Warning (real SMS to every subscriber), cancel
   it, STOP any subscriber, send SMS to arbitrary numbers at our cost, and read full phone numbers
   from `/feed/users`.** `/sim/inbound`, `/alerts/run`, `/events/*` and `/feed/*` have no auth, CORS
   is `*`, the webhook HMAC is optional, phones are stored in clear (spec asks for `phone_enc` +
   `phone_hash`), no retention, no rate limit on inbound (each inbound = one Claude call + one SMS).
   Good news for Q14: prompt injection via SMS is contained by design (schema-constrained intents,
   gazetteer-only districts, advice by id only; 22 mocked + 3 live injection tests passed). Before
   the demo: put a bearer token on approve/run/cancel/sim, mask phones in the feeds, and prefer the
   USB `adb reverse` or local-Wi-Fi gateway mode over a public tunnel.

Minor but visible: one failing test in `pipeline/tests/audit`; 181 ZWE unit-months at Warning or
Emergency show **no drivers** (hysteresis hold; the NGO SMS falls back to "dry conditions") - do not
click such a month on stage, or carry the last drivers forward (code_review #3); Mvurwi shows
"0.00M people" (WorldPop rounding); the 39 `p = 0.000` rows are the isotonic calibrator's floor, not
NaN-to-zero (code_review), but `export_risk.py` still writes `nan_to_num(p)` (methodology m6);
`pipeline/audit/out/metrics_MWI.json` is still a STUB artefact next to the real ZWE one; demo script
and pitch no longer carry `[NUMBER PENDING]` placeholders but their numbers are tied to the 16:28
risk file; the demo opening line was corrected to "most are yellow, nothing is orange" (16:57).
