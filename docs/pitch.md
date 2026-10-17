# Pitch deck: drought early warning by SMS (Welthungerhilfe case, pastoral Kenya)

BCG Platinion "Fighting World Hunger" hackathon, 16-17 Oct 2026. Nine slides. Speaker notes in simple English, 60 words or fewer.
Live demo: `docs/demo_script.md`. Demo country: **Kenya** (47 counties). Zimbabwe, Zambia and Malawi stay in the app as other countries.

## Where every number comes from

All Kenya numbers are counted on `data/risk/KEN.js` (generated 2026-10-17 01:30 UTC, model `sat-v1-ensemble-ZWE_KEN_MWI_ZMB`, `live_t` 92 = Sep 2026). The verify command is in `docs/demo_script.md`. Population: county figures in `data/geo/KEN.js` (47.8 M total), the same as on screen. Month rule: the level for month t is issued at the end of month t. Index: t=30 Jul 2021, t=32 Sep 2021 (declaration 8 Sep 2021), t=92 Sep 2026.
Model and skill numbers (tags M, P, X) are pooled over ZWE, KEN, MWI, ZMB: `pipeline/out/model_report.md`, `pipeline/ipc_model/report.md`. Cite the URL for anything else (`docs/experts/humanitarian.md`).

## Slide 1: Title
**See the drought coming. Get ready early. Tell the herder in one SMS.**
For Welthungerhilfe, pastoral northern Kenya. Forecast, county risk, Ready / Set / Go, one action per person, any phone.
> Notes: In northern Kenya one failed rainy season can kill a family's herd. We built a system that sees the drought months ahead, gets aid groups ready, and only then tells the herder what to do, in one SMS, on any phone.

## Slide 2: The problem is not data. It is time.
Kenya declared the 2020-22 drought a **national disaster on 8 Sep 2021**. FEWS NET already showed Phase 3 (Crisis) in 13 northern counties in July 2021 (E). Kenya has two rainy seasons (March-May, October-December), so one missed season leaves only months to act.
> Notes: FEWS NET saw Crisis in July. The declaration came in September. Money and food come after that. Herders lose animals in the dry months in between. The gap is the problem.

## Slide 3: Ready / Set / Go
| Stage | Our level | Trigger | Who hears |
| --- | --- | --- | --- |
| Ready | Watch | Forecasts: FEWS NET outlook, our chance of Crisis >= 57 % | NGOs and officers only. May be wrong |
| Set / Go | Warning | Observed: plants plus rain or soil, two families agree, held 2 months | Farmers and herders: one action, never a probability |
| Response | Emergency | Warning plus official declaration | Everyone |
Text or forecasts alone never raise a county above Watch. A person approves every Warning.

## Slide 4: The forecast (centrepiece, live)
**Issued end of Jul 2021, only data public then** (E):
| | +1, +2 (Aug-Sep 2021) | +3 to +6 |
| --- | --- | --- |
| FEWS NET outlook, counties at Phase 3+ | 13 of 47 | 9 of 47 |
| Our chance of Crisis >= 57 % | **12 counties, 8.9 M people** (+1 to +3) | 10 counties (+4 to +6) |
| Isiolo | FEWS Phase 3, our chance **87 %** | |
**Sep 2021 (declaration month):** 10 counties >= 57 % (6.1 M people); Warning in 4 counties (Garissa, Isiolo, Kilifi, Lamu). The 4 Warnings had been on a median 11 weeks. Watch had been on a median 35 weeks in 26 counties, but Watch is noisy (31 counties in Mar 2021, and on in non-drought months too).
**Today, Sep 2026** (E): 8 counties >= 57 % chance of Crisis for Oct-Dec 2026: Garissa, Isiolo, Mandera, Marsabit, Samburu, Tana River, Turkana, Wajir (4.9 M people). FEWS NET Phase 3+: Garissa, Lamu, Mandera, Tana River, Turkana, Wajir. Warning: West Pokot (no grass, 3 of 3 families) and Kilifi.
> Notes: July 2021. FEWS NET says crisis for the north. Our model gives each county a number: twelve counties, nearly nine million people, above our line, two months before the declaration. Today the same view shows eight counties at risk.

## Slide 5: Live demo (3 minutes)
1. Jul 2021 forecast: FEWS layer shows 13 counties at Phase 3; Isiolo 87 %.
2. Sep 2021: 4 Warnings on declaration day.
3. Go to today (Sep 2026): West Pokot Warning, no grass, 3 of 3 families.
4. A jury member texts **JOIN West Pokot herder**; we approve; the phone gets the Warning (English or Swahili). "3" is a crowd report. "We need help" goes to a person.
5. Today's forecast: 8 counties above the line.

## Slide 6: Honest skill
- **Kenya IPC check not available.** `compare_ipc.py --iso3 KEN` finds no evaluable Warning-vs-IPC pairs: FEWS reports Kenya at sub-county level (45 of 349 FEWS units match our counties; Elgeyo-Marakwet, Kisii and Meru do not). We do not quote a Kenya precision or recall.
- **Zimbabwe check (I), 2023/24:** precision 0.78, recall 0.61, before the FEWS-first gate. After the gate: 0.55 / 0.21 (HANDOFF.md).
- **Chance-of-Crisis model (P), pooled, unseen years:** ROC 0.87, PR-AUC 0.60 vs 0.71 / 0.26 for "same as last year" and 0.86 / 0.53 for FEWS NET's own projection. It mostly repeats FEWS NET's judgement; the added value is monthly, per county, and the last mile.
- In 2020-22, 19 % of Kenya county-months were at >= 57 %.
> Notes: We score ourselves like humanitarians do. For Kenya we cannot yet prove hits and misses, because FEWS NET maps are finer than our counties. We say so. In Zimbabwe about four in five early Warnings were right.

## Slide 7: Limits
- We depend on FEWS NET; if its feed stops, a satellite-only fallback runs (lower skill, X).
- Beyond +3 months only season-level risk; from +5 months Kenya shows FEWS NET only or nothing.
- Warning is not early: it came with the declaration (4 counties). The forecast is the early part.
- Kenya Swahili messages are machine-written and **need native review**; the farmer/herder texts have not been tested with users.
- Cities (Nairobi, Mombasa) get flags despite little cropland or grazing; they will be masked before any SMS.
- Prices, a key Malawi-type driver, are not yet a signal family.

## Slide 8: Why this, and who pays
| | FEWS NET / HungerMap | This system |
| --- | --- | --- |
| Unit | Livelihood zone / sub-county | County, monthly, 47 in Kenya |
| Updates | Outlook a few times a year | Monthly |
| Last mile | Reports | One-segment two-way SMS |
Farmers and herders never pay. Aid funds, NGOs and governments pay a licence per country; SMS at cost, capped at 6 per person per month. Early sale of weak animals paid back about 390:1 in a *modelled* Wajir study (Cabot Venton et al. 2012).

## Slide 9: Ask
**One season pilot with WHH in pastoral Kenya (West Pokot, Turkana, Marsabit, Wajir), about 500 opted-in herders via extension officers and a local sender ID.**
Next 90 days: dry-spell signal; prices as a fourth family; Swahili and local-language review with NDMA; Kenyan SMS aggregator.

### Appendix
- **Is it real?** CHIRPS, MODIS, ERA5-Land, NMME, NOAA ONI, FEWS NET, geoBoundaries. Each month uses only data public then.
- **Did you beat the declaration?** The forecast did (12 counties flagged in Jul 2021). Warning did not; it matched it.
- **AI?** Claude reads incoming SMS; advice comes from an approved list; distress words skip the AI and go to a person.
- **Zimbabwe, Zambia, Malawi?** Also in the app; the earlier Zimbabwe replay (declaration 3 Apr 2024) is documented in git history.
