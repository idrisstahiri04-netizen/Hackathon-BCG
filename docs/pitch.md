# Pitch deck: drought early warning by SMS (Welthungerhilfe case, northern Zimbabwe)

BCG Platinion "Fighting World Hunger" hackathon, 16–17 Oct 2026. Nine slides. Speaker notes are simple English, 60 words or fewer.
Live demo: `docs/demo_script.md`.

## Where every number comes from (read before you touch a slide)

All numbers below were counted on the **final export** of 16 Oct 2026, files `data/risk/<ISO3>.js`
(model `sat-v1-ensemble-ZWE_KEN_MWI_ZMB`). ZWE was written 20:07 UTC, KEN 20:13, MWI 20:15, ZMB 20:23, and the other seven countries 20:34–20:44.
The ZWE/KEN/MWI/ZMB files run to **Sep 2026** (`live_t` 92, Sep 2026 = "today"). MOZ, TZA, ETH, SOM, NAM, BWA and ZAF stop at Dec 2024.
The globe loads 14 ISO3 codes (`index.html`). MDG, AGO and UGA have no risk file, so they show "data in progress".

| Tag | Source | How to check it again |
| --- | --- | --- |
| **E** | Counted on `data/risk/ZWE.js` (20:07) | the verify command in `docs/demo_script.md` |
| **I** | `pipeline/audit/compare_ipc.py ZWE MWI`, re-run on the 20:07 file (written to a scratch folder; the repo copy `pipeline/audit/out/` is from 19:46). The numbers did not change. | same script |
| **M** | `pipeline/out/model_report.md` (19:41). The same numbers are in `meta.metrics` of the export | the file |
| **P** | `pipeline/ipc_model/report.md` (chance-of-Crisis model). The same numbers are in `meta.metrics.forecast_skill` | the file |
| **X** | `docs/experts/ml.md` (FEWS-outage fallback), `pipeline/experiments/report.md` (v2 experiments) | the files |
| **H** | `docs/experts/humanitarian.md`, which gives a URL for each item | the URLs |

Month convention: the level for month t is **issued at the end of month t** from data of month t-1. The one-month delay is already applied, so never add it again.
Index: t=57 is Oct 2023, t=61 Feb 2024, t=62 Mar 2024, t=63 Apr 2024 (the declaration on 3 Apr), t=92 Sep 2026.

---

## Slide 1: Title

**See the drought coming. Get ready early. Tell the herder in one SMS.**

For Welthungerhilfe, northern Zimbabwe.
Forecast → district risk → Ready / Set / Go → one action per person → any phone.

> Speaker notes (40 words):
> In northern Zimbabwe one failed season can kill a family's whole herd. We built a system that
> sees the drought months ahead, gets aid groups ready, and only then tells the herder what to do,
> in one SMS, on any phone.

---

## Slide 2: The problem is not data. It is time.

> "In northern Zimbabwe, drought doesn't arrive without warning, it creeps in." (case brief, BCG Platinion / WHH)

**2023–24 El Niño: when the money moved** (H)

| When | What happened |
| --- | --- |
| Aug–Sep 2023 | El Niño is clear. ONI +1.0 (Jun–Aug), public by end of Sep. The Red Cross EAP in Binga fires on its first trigger. |
| **3 Apr 2024** | National state of disaster declared |
| May 2024 | Flash appeal |
| **4 Jul 2024** | ARC drought insurance pays out US$32 M (Government, WFP and Start Network policies) |
| **Sep 2024** | WFP's ARC-funded food distributions start |

The signal was public **six months** before the declaration. The money arrived **three to five months after it**.

> Speaker notes (52 words):
> Everyone knew El Niño was coming by September 2023. The declaration came in April 2024. The
> insurance paid in July and food arrived in September. That is a year from "we know" to "we help".
> Herders cannot wait a year. Their animals die in February and March.

---

## Slide 3: Ready / Set / Go, the way real anticipatory action works

| Stage | Our level | Trigger | Who hears | Allowed to be wrong? |
| --- | --- | --- | --- | --- |
| **Ready** | Watch | Forecasts: El Niño + seasonal rain forecast, FEWS NET outlook, our chance of Crisis ≥ 57 % | NGOs and extension officers only | **Yes.** Low-regret actions: register herders, line up buyers, dose animals |
| **Set / Go** | Warning | **Observed**: plants (satellite) + rain or soil (weather), two families agree, held 2 months (3 to step down) | Farmers and herders: one action, never a probability | Rarely. Precision 0.78 in 2023/24 (I) |
| **Response** | Emergency | Warning + official declaration in force | Everyone | n/a |

Text or forecasts alone can never raise a district above Watch. A person approves every Warning.
WFP Zimbabwe ("Ready, Set & Go") and the Zimbabwe Red Cross drought plan use the same two stages (H).

> Speaker notes (55 words):
> Real early-action systems split the job in two. "Ready" uses forecasts. It may be wrong, so it
> only talks to aid workers. "Go" needs proof you can see from space: dry plants plus dry rain or
> soil. Only then does a herder get a message. Forecasts prepare. Observations act.

---

## Slide 4: The forecast (centrepiece, shown live)

**Issued end of Oct 2023, using only data public at that time** (E):

| | +1 to +3 (Nov 2023–Jan 2024) | +4 to +7 (Feb–May 2024) |
| --- | --- | --- |
| FEWS NET outlook layer, districts at Phase 3+ | 26 of 91 | **38 of 91** |
| Our chance of Crisis ≥ 57 % | 8 districts | **40 districts, 5.7 M people** (+4 to +6 only; +7 is FEWS NET alone) |
| **Mbire** (north) | FEWS Phase 2 · our chance **15 %** | FEWS Phase 3 · our chance **57 %** |

**Issued end of Feb 2024, five weeks before the declaration** (E): for Apr–May 2024 (+2/+3), **33 districts, 4.8 M people**, are at ≥ 57 % chance of Crisis.
FEWS NET maps later showed 31 of the 33 in Crisis that season (I). Every matched district reached Crisis in 2023/24, so this checks timing, not ranking.

**Ready went out** (E): Watch in all 91 districts from the end of Nov 2023, about 18 weeks before the declaration. Driver: "climate readiness (El Niño + dry forecast)". In the three seasons 2020/21–2022/23 it fired in **0 districts**.

**Today** (E): issue Sep 2026. Zimbabwe is in the dry season: 87 of 91 districts Normal, 4 urban units on Watch (held by the 3-month step-down rule). The export has **no** Zimbabwe forecast for Sep 2026. The model only forecasts in the season months, and the FEWS feed in our data ends in 2024. Kenya, at the start of its short rains, does have a live +1 to +5 forecast.

> Speaker notes (58 words):
> October 2023. FEWS NET says "stressed" for the next three months, then "crisis" from February.
> Our model turns that into a district number: Mbire goes from 15 to 57 percent. By February,
> five weeks before the declaration, 33 districts and almost five million people are flagged.
> The forecast was there. It had to reach someone.

---

## Slide 5: Live demo (3 minutes)

1. Forecast view, issued Oct 2023: FEWS layer steps from Phase 2 to Phase 3. Click Mbire: 15 % → 57 %.
2. Feb 2024, +2: 33 districts flagged before the red line (3 Apr).
3. Now view, Mar → Apr 2024: Ready (Watch) everywhere since Nov. Warning in 7 districts in March, then 22 in April.
4. Hwange, Apr 2024: *no grass*, 3 of 3 families, high confidence. A jury member texts **JOIN Hwange herder**, we press **Approve**, and the phone gets the Warning.
5. "How do I save my cattle?" gets approved advice. Reply "3" is counted as a crowd report. "We need help" sends the case to a person.
6. **Go to today**: Sep 2026.

> Speaker notes (45 words):
> Everything you will see is real satellite data and real model output. Nothing is simulated. First
> the forecast, then the warning, then one of you joins as a herder in Hwange and gets the real SMS on
> your own phone. Probabilities are model estimates. We will say how good.

---

## Slide 6: Honest skill

**Warning vs FEWS NET Crisis maps (IPC 3+), Zimbabwe** (I)

| | Hit | False alarm | Missed | Precision / recall | "Same as last year" |
| --- | --- | --- | --- | --- | --- |
| 2023/24 | 35 | 10 | 22 | **0.78 / 0.61** | 0.43 / 0.35 |
| All seasons 2019/20–2023/24 | 39 | 16 | 102 | 0.71 / 0.28 | 0.24 / 0.44 |
| Wet 2020/21 | 0 Warnings | | | | |

**Benchmarks** (H): WFP's live drought trigger in Mozambique has a hit rate of 74 % and a false-alarm ratio of 59 %. FEWS NET is about 78–84 % accurate overall, less in severe crises. ML in the Horn of Africa catches 20–50 % of crisis onsets 3 months ahead.

**Models, tested on years they never saw**
- Chance of Crisis (FEWS outlook + satellite + forecasts), districts not yet in Crisis (P). In cross-validation: ROC 0.87, PR-AUC 0.60, against 0.71 / 0.26 for "same as last year" and 0.86 / 0.53 for FEWS NET's own projection. On the 2023/24 hold-out for Zimbabwe: 0.94 / 0.92. FEWS NET alone scores 0.98 there.
- At +4 to +6 months the chance of Crisis drops to ROC 0.81 (P). That is season-level risk, and district detail is less sure.
- Bad-season model (satellite + weather + El Niño + seasonal forecast, v2 features) (M). In cross-validation the mean PR-AUC is 0.391, against 0.267 for "same as last year". On the 2023/24 Zimbabwe hold-out the ROC is 0.71 for crop failure and 0.82 for no grass, against 0.49 / 0.53.

> Speaker notes (58 words):
> We score ourselves like humanitarians do: hits, false alarms, misses. In 2023/24 about four in
> five Warnings were right, with no Warnings in the wet year before. WFP's live trigger in
> Mozambique accepts more false alarms than that. Our crisis model mostly repeats FEWS NET's
> judgement. Our added value is that it is monthly, per district, and reaches the last mile.

---

## Slide 7: Limits we tell you up front

- **We depend on FEWS NET.** If the FEWS feed stops (it paused for about 6 months in 2025), a satellite-only fallback takes over. On hold-out its ROC is 0.89, against 0.94 with FEWS (X). The district panel says which model is running. The live months after 2024 show no chance-of-Crisis number until FEWS data is added.
- **+3 months and beyond show season-level risk.** Bad-season skill falls from ROC 0.68 at +1 to 0.64 at +3 for crops, and from 0.71 to 0.57 for grass (M). From +7 there is only the FEWS outlook.
- **Malawi is monitoring only.** All seasons: precision 0.07, recall 0.08 (I). Its 2024 crisis was led by prices: the kwacha lost 44 % and maize cost 160 % above normal (H). Prices are our next family.
- **Warnings come late for crops.** Only 7 districts reached Warning before 3 Apr (E). The fix is a dry-spell check every 10 days. By 16 Feb 2024, 53 % of districts already had 15 or more dry days in a row (agroclimate review). It has not been replayed end to end yet.
- **Towns get Warnings.** 15 of the 22 April Warnings are towns (Harare, Bulawayo, Epworth, Victoria Falls…) (E). Those units have little cropland or grazing. We will mask them before any farmer or herder SMS goes out.

> Speaker notes (55 words):
> Four honest limits. Our crisis model leans on FEWS NET, so we built a fallback. Beyond three
> months we show the shape of the season, not a district promise. Malawi's crisis was about prices,
> which satellites cannot see, so we only monitor it there. And Warnings for crops come late. A
> faster dry-spell check is next.

---

## Slide 8: Why this, and who pays

| | FEWS NET / HungerMap | This system |
| --- | --- | --- |
| Unit | Livelihood zones, provinces | **District**, monthly, 91 in Zimbabwe |
| Updates | Outlook about 3 times a year | Every month, between FEWS releases |
| Last mile | Reports and dashboards | **One-segment SMS** to any phone, two-way |
| Action | Analysis | One approved action per audience, a person approves every Warning |

- We do not compete with FEWS NET. We carry its outlook, plus satellites, to the person who must decide.
- **Farmers and herders never pay.** Anticipatory-action funds, NGOs (WHH, WFP), government early-warning units and index insurers pay a licence per country. SMS is billed at cost and capped at 6 per person per month.
- Running cost is close to zero: free satellite data, one model run a month, and one config file per country.
- Early sale of weak animals paid back about **390:1** in a *modelled* study (Wajir, Kenya; Cabot Venton et al. 2012, DFID).

> Speaker notes (50 words):
> FEWS NET does the expert analysis. We do the last mile: every district, every month, one SMS a
> herder can act on, and a reply channel back. The herder pays nothing. Aid funds pay, because
> acting months before the money arrives is far cheaper than acting after.

---

## Slide 9: Ask

**One season pilot with WHH in northern Zimbabwe, 2026/27:** Mbire and Hwange, about 500 opted-in herders and farmers through extension officers, and a local sender ID.

Next 90 days:
1. Add a dry-spell check every 10 days (CHIRPS-prelim) so Warnings come earlier. This needs a spec change for a new signal type.
2. Add market prices as the fourth family, which fixes the Malawi-type crises.
3. Bring live FEWS NET data into the forecast, so "Go to today" shows the chance of Crisis for 2026/27.
4. Translate messages into Shona, Ndebele and Tonga with AGRITEX. Use a Zimbabwean SMS aggregator.

> Speaker notes (45 words):
> We ask for one pilot season with WHH's field teams in Mbire and Hwange. The system works end to
> end today, on real data and real phones. What it needs now is local trust: a known sender name,
> local languages, and officers who approve each warning. Thank you.

---

### Appendix: answers if asked

- **"Is it real?"** Yes. CHIRPS v3, MODIS, ERA5-Land, NMME, NOAA ONI, FEWS NET and geoBoundaries data. Population is from WorldPop 2020. Each month uses only the data that was public at the time.
- **"Readiness fired everywhere in 2023/24."** Yes, and by design: it is a country-wide El Niño signal sent to aid workers only. It was silent in 2020/21, 2021/22 and 2022/23.
- **"Did you beat the declaration?"** Ready did: Watch went out in Nov 2023, and 33 districts had a chance of Crisis ≥ 57 % in Feb 2024. Warning reached 7 districts in March and 22 in April. Warnings need observed proof on purpose.
- **"What does the AI do?"** Claude Haiku reads incoming SMS (join, advice, help, report, STOP). Advice comes only from an approved list. Distress words skip the AI and go straight to a person.
- **"Kenya today?"** At Sep 2026 the model shows West Pokot at 43 % and Baringo at 37 % for Oct–Nov (bad-season chance). Live inputs are partly missing. Check the soil and heat values before you quote them.
