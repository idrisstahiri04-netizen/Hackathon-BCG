# Humanitarian early-warning / anticipatory-action review

Role: senior anticipatory-action adviser (WFP / OCHA / IFRC / FAO practice). Written 2026-10-16 for the Welthungerhilfe case (livestock-dependent communities, northern Zimbabwe), branch `zimbabwe-real-data`.
Read: `docs/models_explained.md`, `docs/metrics_report.md`, `/home/looooo/bcg/docs/hackathon_case.md`, `docs/pitch.md`, `docs/redteam.md`, `pipeline/out/model_report.md`. Web content below is treated as data; every number has a URL.

Problems I was asked about: (1) satellite-only skill is weak (ROC 0.57–0.62); (2) farmer Warnings late (7/91 ZWE districts before 2024-04-03); (3) NGO Watch ~9 weeks early but broad (53–61/91); (4) Malawi no skill; (5) the strong crisis model (Model B) leans on FEWS NET.

Short verdict: the team has built a good **observation-stage** engine and is judging it against a **forecast-stage** expectation. Real anticipatory-action (AA) systems never ask one indicator to be both early and precise. They split the job: a forecast-based *readiness* trigger that is allowed to be wrong, and an observation-based *activation* trigger that must be precise. Our Watch/Warning pair is already that shape; it needs to be named, calibrated and sold that way.

---

## REPORT — top 5 recommendations (impact × feasibility before the demo)

1. **Rename and re-plumb the two levels as a Ready / Set / Go trigger.** Readiness (NGO/officer, Aug–Dec) = forecast family: ENSO + seasonal forecast + FEWS NET "below-normal rainfall expected" (we already have it: fired July 2023, 0 false alarms 2020–23). Activation (farmer/herder) = observed two-family rule. This is exactly how WFP-MSD Zimbabwe ("Ready, Set & Go", ECMWF-based readiness and activation thresholds, Chiredzi activated 15 Aug 2024) and Zimbabwe Red Cross (El Niño 1-in-6-yr first trigger, Sept 2023; observed/IPC second trigger) work. Sources: https://docs.wfp.org/api/documents/WFP-0000163573/download/ , https://go-api.ifrc.org/api/DownloadFile/85190/MDRZW020%20DREF%20EAP%20Activation%20Report
2. **Add a dekadal dry-spell detector from CHIRPS-prelim (2-day latency) for Jan–Mar.** The 2023/24 loss was a 30-day February dry spell (WFP) in central and northern Zimbabwe (FEWS NET). Malawi's OCHA framework activates on an observed 14-day dry spell in January. This is the cheapest fix for "late". Needs a spec change (new `signal_type`). https://earlywarning.usgs.gov/fews/product/190 , https://m.reliefweb.int/report/3785000/malawi/anticipatory-action-framework-malawi-dry-spells-2021-2022
3. **Reframe "late" as "earlier than the money, and targeted."** ARC paid 4 July 2024 (3 months after the declaration); WFP's ARC-advance distributions started September; the flash appeal came in May. Our Watch (53/91, ~9 weeks before declaration) and Warning precision 0.78 beat every funding clock. https://www.arc.int/news/arc-group-makes-total-us32-million-climate-insurance-payouts-assist-people-affected-drought
4. **Show skill as a contingency table with operational benchmarks.** WFP Mozambique's live drought trigger: hit rate 74%, false-alarm ratio 59%. ML in the Horn catches 20–50% of crisis onsets at 3 months. FEWS NET itself scores 78–84% overall but drops in severe crises. Our 0.78/0.61 is in the operational range. https://www.sciencedirect.com/science/article/pii/S2405880723000055 , https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2023EF004211 , https://arxiv.org/html/2410.09384v1
5. **Drop Malawi Warning claims; call it "monitoring only" and say why** (kwacha −44%, maize +160%, patchy dry spells, Cyclone Freddy carry-over): a price-driven crisis that vegetation cannot see. https://humanitarianaction.info/plan/1206/article/malawi-fa-2024

---

## 1. How real anticipatory-action systems set triggers

### 1.1 The pattern: two stages, two different error budgets

| Programme | Stage 1 (readiness / "Ready") | Stage 2 (activation / "Set-Go") | How false alarms are handled | Source |
|---|---|---|---|---|
| **WFP + Met Services Dept Zimbabwe, "Ready, Set & Go"** (Mudzi 2021; four districts 2023/24; Chiredzi Oct 2024; WHH/AAH plans 2026 use the same model) | ECMWF seasonal forecast turned into 2- and 3-month SPI anomalies; pre-agreed readiness threshold; district level | Activation threshold on later forecast issues; 2026 plans required thresholds crossed **two consecutive months** | Trigger probabilities set from historical frequency per region, so the system fires at a chosen return period | https://docs.wfp.org/api/documents/WFP-0000163573/download/ ; https://www.wfp.org/anticipatory-actions ; https://www.anticipation-hub.org/news/partners-act-to-anticipate-the-impacts-of-drought-across-zimbabwe |
| **WFP Mozambique (same system, published verification)** | SEAS5 forecasts of SPI-2/3 for OND/NDJ/DJF, mild/moderate/severe thresholds by return period | Later-lead forecasts; staged release of actions by severity | Accepted skill: mean hit rate 74%, false-alarm ratio 59%; AUROC classed "moderate" at 0.6–0.8; lead time changes mean AUROC by only 0.02; only 12% of forecast SPIs had CI lower bound above 0.5 | https://www.sciencedirect.com/science/article/pii/S2405880723000055 |
| **Zimbabwe Red Cross drought EAP (Binga)** | Forecast of El Niño with impact "corresponding to once-in-six-year event" → low-investment actions (early-warning messages, drought-tolerant seed, livestock dosing). Activated 24 Aug / Sept 2023, seed distributed last week of Oct 2023 | Forecast of IPC 4 in FEWS NET reports in March and June → cash, livestock support, school feeding. In practice fired after the 3 Apr 2024 declaration | Lesson in the report: "need to include triggers that were not informed by Government declaration such as state of disaster before activation" | https://go-api.ifrc.org/api/DownloadFile/85190/MDRZW020%20DREF%20EAP%20Activation%20Report ; https://www.anticipation-hub.org/news/zimbabwe-acts-in-anticipation-of-an-impending-drought |
| **IRI / WFP Ethiopia (Oromia, Somali, South Ethiopia)** | Frequency-first: working group picks how often to act (moderate = 1-in-3, ~30–35% of years; severe = 1-in-5, 20–25%); forecast-probability threshold is the percentile that reproduces that frequency; −5 pp if previous season SPI was below average | Monitoring of observed SPI through the season | Explicit: with a low-skill forecast a 1-in-5 trigger "would only be at least 25% more confident than guessing; however, the overall frequency of trigger actions remains constant" | https://fist.iri.columbia.edu/publications/docs/wfp_ethiopia_aa_documentation_oromia_ond ; https://docs.wfp.org/api/documents/WFP-0000157417/download |
| **OCHA Malawi dry-spell framework (Balaka, Chikwawa, Nsanje)** | Stage I predictive, mid-Nov / mid-Dec | **Stage II observational, January: a dry spell (14 consecutive days with 0–2 mm) observed in ≥3 districts** | Observation stage cannot be a false alarm; only the pre-positioning is at risk | https://m.reliefweb.int/report/3785000/malawi/anticipatory-action-framework-malawi-dry-spells-2021-2022 ; https://www.disasterprotection.org/publications-centre/malawi-anticipatory-action-process-learning-on-trigger-development |
| **OCHA Somalia 2020 (first drought AA pilot)** | Trigger on *projected* food insecurity (IPC projections), fired June 2020 | — | Learning report; trigger used projections not observations | https://www.disasterprotection.org/publications-centre/un-ocha-anticipatory-action-lessons-from-the-2020-somalia-pilot |
| **CERF Ethiopia Sept 2024** | $10 M released "to get ahead of a projected drought" | — | — | https://centre.humdata.org/how-ochas-anticipatory-approach-to-predictable-shocks-is-speeding-up-post-disaster-response/ |
| **ARC / Africa RiskView (Zimbabwe, Malawi)** | — (ARC classic pays after season end on modelled rainfall/WRSI: Zimbabwe payout US$32 M on 4 July 2024, 4.7 M people affected per ARV; Gov $16.8 M, WFP $6.1 M, Start Network $8.9 M) | **ARC "anticipatory insurance" pilot (Malawi, Zambia 2023/24–2024/25)** pays by mid-January on failed sowing plus forecast end-of-season impact | Basis risk accepted by contract; early minimum-payout confirmation let WFP start distributions in early Sept 2024 (Buhera, Mwenezi, Mangwe) | https://www.arc.int/news/arc-group-makes-total-us32-million-climate-insurance-payouts-assist-people-affected-drought ; https://www.undrr.org/quick/104935 ; https://docs.wfp.org/api/documents/WFP-0000163208/download ; https://startnetwork.org/what-we-do/arc-replica |
| **Anticipation Hub 2024 overview** | — | — | Reports a 2024 case where readiness and activation triggers were both reached and the event did not occur: a "false alarm" accepted as a cost of the system | https://www.anticipation-hub.org/Documents/Reports/Overview-report-2024/Overview_Report_2024_Online_FINAL_lowres.pdf |

### 1.2 What to copy, concretely

1. **Name the stages.** Watch = *Readiness* (forecast-driven, NGO/officer audience, pre-positioning and registration). Warning = *Activation* (observed, farmer/herder audience, one action). Emergency = *Response* (declaration). This is already what the engine does; the pitch just does not call it that.
2. **Readiness is allowed to be wrong, by design.** Set it frequency-first, like IRI/WFP: choose the return period you want to act at (1-in-3 for messages and seed, 1-in-5 for cash) and derive the threshold from the historical forecast distribution per district. Then "fires in 30% of years" is a feature, not a false-alarm rate. We already hold the inputs: ONI, NMME, FEWS NET "below-normal rainfall expected" (fired July 2023, zero false alarms 2020–23 per `docs/models_explained.md`), SARCOF-27 / MSD "normal to below-normal" for OND 2023 (https://docs.wfp.org/api/documents/WFP-0000153348/download/ ; https://newsday.co.zw/local/article/200016886/drought-looms-in-southern-zim). Under the spec, text-family signals can raise a district to Watch at most, which is exactly the readiness level.
3. **Activation must be observed, not modelled.** Keep the two-family rule, but feed it a faster observation (section 2, dry-spell detector). Zimbabwe Red Cross' second trigger ended up being the state-of-disaster declaration, which their own report lists as a failure to fix. We can be the fix.
4. **Tie each stage to a cost ladder, like the Red Cross EAP:** stage 1 = low-regret (early-warning SMS, drought-tolerant seed, livestock dosing/dipping, register herders with buyers); stage 2 = high-regret (destocking, cash). "Sell weak animals now" is a stage-2 action and should only ride on observed evidence, which is what the spec already enforces.
5. **Two consecutive issues before activation** (WHH/AAH 2026 plans) = our 2-run hysteresis. Say so.
6. **Publish the "act in vain" budget.** Every framework above states one. Ours: readiness in ~30% of district-seasons; activation false-alarm ratio 22% (precision 0.78) on 2023/24.

---

## 2. Complementary data to reduce FEWS NET dependence and catch late droughts

Ranked by what it would do for the stated problems. "Family" refers to the spec's independent source families.

| Source | Open? | Latency | District level? | What it fixes | Plugs into | URL |
|---|---|---|---|---|---|---|
| **CHIRPS-prelim pentads (dry-spell days, onset date)** | Yes, public | ~2 days (final product ~3 weeks) | Yes (we already aggregate CHIRPS) | **Problem 2.** Feb 2024 was a 30-day dry spell (WFP) "across central and northern Zimbabwe" (FEWS NET). A 14–21-day dry-spell count would fire in late Feb, before 3 Apr, with no model | Rain family; needs a new `signal_type` (e.g. `dry_spell_days`) → spec change | https://earlywarning.usgs.gov/fews/product/190 ; https://reliefweb.int/report/zimbabwe/wfp-zimbabwe-el-nino-response ; https://fews.net/southern-africa/zimbabwe/food-security-outlook/february-2024 |
| **JRC ASAP warnings** | Yes; "reuse is authorised, provided the source is acknowledged" | 10-day | GAUL 1 everywhere, GAUL 2 for selected countries; warnings CSV back to May 2001; WFS/WMS | Independent vegetation/rangeland warning to cross-check MODIS; an external "second opinion" for the jury | Vegetation family (same satellite, so not independent for the two-family rule; use as confirmer) | https://agricultural-production-hotspots.ec.europa.eu/download.php |
| **GEOGLAM Crop Monitor for Early Warning** | Bulletin PDF only, copyright; ~3-day latency | Monthly | Sub-national narrative, not district table | Text family input for the extractor (same pipeline as FEWS NET); FEWS NET itself uses it (Busker et al.) | Announcement family | https://www.cropmonitor.org/crop-monitor-for-early-warning |
| **SARCOF / MSD seasonal outlook** | Public statements, Aug–Sept | Once per season (+ Jan update) | Zones (3 for Zimbabwe) | Readiness trigger that is not FEWS NET | Announcement family (Watch only) | https://sardc.net/en/wp-content/uploads/STATEMENT-FROM-SARCOF-29.pdf |
| **ZimLAC / ZimVAC Rural Livelihoods Assessment** | PDF, Food and Nutrition Council | Annual (fieldwork May–June, report ~July) | Yes, district: food-insecurity %, livestock deaths by district (2024: Mat South 30% households, Chirumhanzu, Zaka, Bulilima highest) | Ground truth that is not FEWS NET; livestock-loss labels for the herder model | Label/validation; `ipc_phase`-like severity | https://www.fnc.org.zw/documents/ ; https://www.unicef.org/zimbabwe/media/11516/file/2024%20ZimLAC%20Rural%20Livelihoods%20Assessment%20Report.pdf.pdf |
| **Ministry Crop, Livestock and Fisheries Assessment (1st round ~Feb/Mar, 2nd round ~Apr/May)** | PDF via ministry/news | Seasonal | Yes, district livestock condition and deaths (9,941 cattle lost early 2023/24; Tsholotsho, Binga, Mangwe, Bulilima worst) | Livestock ground truth; the Red Cross used it as a stage-2 input | Announcement family + labels | https://cite.org.zw/drought-matabeleland-provinces-suffer-most-cattle-deaths/ ; https://fews.net/southern-africa/zimbabwe/food-security-outlook-update/december-2023 |
| **FAO DIEM household monitoring (Zimbabwe rounds 5–7)** | Microdata on FAO/World Bank catalogues (registration) | Rounds ~6–12 months apart; R7 Mar–Apr 2023, 1,686 CATI records | **ADM1 only** | Validation of food-consumption outcomes independent of FEWS NET | Validation only | https://microdata.fao.org/index.php/catalog/2663 |
| **WFP HungerMap LIVE / real-time monitoring** | Dashboard; no public API or licence found on the site; data by request to WFP | Near-real-time (rural Zimbabwe: 36% insufficient food consumption Nov 2024, 31% Dec 2024) | Published as national/rural aggregates for Zimbabwe | Nowcast cross-check; not usable for district triggers without WFP partnership | Validation | https://hungermap.wfp.org/ ; https://docs.wfp.org/api/documents/WFP-0000164114/download |
| **ACLED** | Free for non-commercial use after registration; API key | Weekly | Yes, event-level | Low value for Zimbabwe drought; useful if the product goes to conflict-affected countries | New family (not in spec) | https://developer.acleddata.com/rehd/cms/views/acled_api/documents/ACLED_AccessGuide_2022.pdf |
| **Market prices (WFP VAM / HDX)** | Yes | Monthly | Market towns → district | **Problem 4 (Malawi)** and price-driven crises; Lentz et al. show prices + rainfall identify 83–99% of Malawi's worst clusters | `price_anom` family (already in spec) | https://lbj.utexas.edu/data-driven-approach-improves-food-insecurity-crisis-prediction |
| **Our SMS crowd signal (1/2/3 replies)** | Ours | Real-time | Yes | Confirmer, never trigger (spec). Add a herder-specific question: "animals dying? water trips > X km?" Livestock body condition is what WHH's communities feel first | `crowd_crop_status` | — |
| Mobile-money / remittance proxies | Not open in Zimbabwe | — | — | Skip for the demo | — | — |

Priority for the next build: dry-spell detector (hours), JRC ASAP warnings as external confirmer (hours), prices as family 4 (already planned), ZimLAC livestock-death table as herder label (a day).

---

## 3. Presenting honest skill to a jury

**Benchmarks the jury can check:**
- WFP's operational Mozambique drought trigger (same "Ready, Set & Go" family used in Zimbabwe): hit rate 74%, false-alarm ratio 59%; AUROC 0.6–0.8 called "moderate" and accepted for activation. https://www.sciencedirect.com/science/article/pii/S2405880723000055
- Machine learning on 20+ datasets in the Horn of Africa (Busker et al. 2024): predicts 20% of crisis onsets in pastoral and 20–50% in agro-pastoral regions at 3 months lead, with false-alarm rates under 10%; "similar to FEWS NET" in pastoral areas, worse in crop areas. https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2023EF004211
- FEWS NET itself: 84% accuracy 2009–2020 across 25 countries but accuracy "drops sharply" in severe crises, biased to over-projection (Backer & Billing 2021); 78% overall in an independent 2024 evaluation, 57% in Somalia. https://arxiv.org/html/2410.09384v1
- News-based ML (Balashankar et al. 2023) is the only published system claiming large gains, and it is at district level with IPC labels. https://pmc.ncbi.nlm.nih.gov/articles/PMC9984173/

**How to show ours:**
1. One contingency table per stage (hits / misses / false alarms / correct rejections), per lead time, next to persistence and FEWS NET. Humanitarians read hit rate and false-alarm ratio, not ROC. Our activation stage: 35 hits, 10 false alarms, 22 misses on 2023/24 IPC3+ transitions (precision 0.78, recall 0.61 vs 0.43/0.35 persistence). Our readiness stage: 53/91 at median 8.9 weeks before the declaration; 2021/22 Watch caught all 47 districts that entered IPC3+ with 13 false.
2. Say plainly: "ROC 0.6 for a satellite-only district forecast is where published systems sit. We did not beat physics; we removed the lag." The 2023/24 hold-out ROC is low partly because almost every district was in drought, so ranking is all that is measured (`model_report.md` caveat).
3. **Reframe "late":** (a) *earlier than the money* — declaration 3 Apr, flash appeal May, ARC payout 4 July, WFP ARC-advance distributions September 2024; (b) *targeting, not timing* — the ARC payout went to 27 districts and FEWS NET maps livelihood zones; a district ranking with precision 0.78 tells WHH which districts first; (c) *the right action at the right stage* — readiness SMS to officers in Dec–Jan (register herders, line up buyers, dosing), activation SMS to herders in Feb–Mar ("sell weak animals now") while prices still hold.
4. Never show the no-latency 0.93 recall; the red team already flagged it.

---

## 4. Malawi: why no skill, and what practitioners do

Evidence on the 2023/24 crisis drivers:
- State of disaster 23 of 28 districts, March 2024; dry spells hit 749,113 ha (44.3% of maize area), so damage was patchy within districts. https://humanitarianaction.info/plan/1206/article/malawi-fa-2024
- Kwacha lost 44% from November 2023; maize prices 160% above the five-year average by April 2024; inflation 32%. GIEWS: deterioration "driven by a combination of weather and economic factors". https://reliefweb.int/report/malawi/giews-country-brief-malawi-10-january-2025
- The 2022/23 season carried Cyclone Freddy damage into 2023/24 stocks and prices.

Why our engine cannot see it: (1) district-mean VCI dilutes a 44%-of-area dry spell; (2) the shock to food access was price and currency, which vegetation never shows (Model B has no `price_anom` yet); (3) 28 large, heterogeneous districts (lakeshore, estates, urban) vs 91 in Zimbabwe; (4) southern Malawi is in IPC 3 almost every lean season, so "transitions" are few and labels are noisy (our all-seasons precision 0.07 vs base 0.07). Check the 2021/22 "calm season" with 30 Warning unit-months: January 2022 had Tropical Storm Ana and dry spells, so some of those may be hits mislabelled by the judge.

What practitioners do there: the OCHA framework triggers on *observed* 14-day dry spells in January in three southern districts, not on vegetation (https://m.reliefweb.int/report/3785000/malawi/anticipatory-action-framework-malawi-dry-spells-2021-2022); Lentz et al. built the Malawi crisis predictor on market prices, rainfall and demographics, not NDVI (https://lbj.utexas.edu/data-driven-approach-improves-food-insecurity-crisis-prediction); ARC's anticipatory policy pays on failed sowing by mid-January (https://www.undrr.org/quick/104935). For the demo: show Malawi as "monitoring, no Warnings", say the crisis was price-led, and point to prices as family 4.

---

## Risks and things not to claim

- Do not present readiness Watch as a prediction of crisis; it is a pre-positioning signal with an accepted ~30% act-in-vain rate.
- Do not call JRC ASAP an "independent family"; it is the same satellite.
- HungerMap LIVE access terms and admin level for Zimbabwe are unverified; say "by partnership".
- The dry-spell detector needs a spec vocabulary change before it enters `signal_observation`.
- WFP Zimbabwe's four 2023/24 AA districts were not found by name; cite only Chiredzi and Mudzi.
