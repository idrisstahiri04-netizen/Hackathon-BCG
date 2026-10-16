# Live demo script: 3 minutes

Goes with `docs/pitch.md` (slide 5). Three people:

| Role | Does |
| --- | --- |
| **Speaker** | Talks. Never touches the laptop. Has this page printed. |
| **Driver** | Laptop and browser. Tab 1 is the demo, Tab 2 the deep links, Tab 3 the backup video. |
| **Phone** | Holds the gateway Android phone and looks after the jury member's phone. |

Written for the **final export**: `data/risk/ZWE.js` (`sat-v1-ensemble-ZWE_KEN_MWI_ZMB`, generated 2026-10-16 20:07 UTC).
Month index: t=57 is Oct 2023 · 61 Feb 2024 · 62 Mar 2024 · 63 Apr 2024 (declaration on 3 Apr) · 66 Jul 2024 · **92 Sep 2026 (today)**.
Every month is an **issue month**: issued at the end of month t from data of month t-1.
Keys: `space` play/pause · `←` `→` one month · `0` Now · `1`…`8` lead · `L` cycles the layer (our model → FEWS NET → both) · `esc` closes the panel.
**Play at 1× only** (950 ms a month). At 2× the pause sometimes lands a month late (`pipeline/audit/e2e_demo.md`, F1).

## Facts the lines below use (all counted on the 20:07 file)

| Moment | What is on screen |
| --- | --- |
| Oct 2023 (t=57), Now view | 37 districts at Watch, 0 at Warning |
| Oct 2023, forecast +1…+3 / +4…+7 | FEWS NET Phase 3+: 26 / 38 districts. Our chance of Crisis ≥ 57 %: 8 / 40 districts (40 = 5.7 M people, +4…+6; +7 is FEWS NET only; +8 is empty) |
| Mbire at t=57 | FEWS Phase 2 at +1…+3, Phase 3 at +4…+7 (Feb–May 2024). Our chance: 15 % at +1…+3, 57 % at +4…+6 |
| Feb 2024 (t=61), +2 or +3 | 33 districts ≥ 57 % (4.8 M people). Top: Plumtree 91 %, Mutare, Lupane and Gwanda 81 %, Hwange 77 % |
| Watch count, Nov 2023 → Jul 2024 | 91 of 91 (Ready, driver "climate readiness (El Niño + dry forecast)") |
| Warning count, t=60…66 | 3, 4, **7** (Mar), **22** (Apr), 50, 50, 46. Emergency 46 in May–Jun |
| Hwange, t=63 | Rises 1 → 2. Event **no_grass** (so the SMS goes to **herders**), 3 of 3 families, confidence high, p 83 %, NGO chance of Crisis 94 %. Drivers: cropland greenness 9/100, grazing land greenness 15/100, topsoil moisture -1.9 SD |
| Mbire, t=63 | Also rises 1 → 2, no_grass, 3/3, high: the "north" answer |
| Today (t=92, Sep 2026) | 87 Normal, 4 Watch (Harare, Harare Rural, Mvurwi, Norton, held). **No Zimbabwe forecast for this issue** (all leads say "no model forecast"). Kenya t=92: 6 Warning, live forecast +1…+5 |

Herder SMS (134 septets, GSM-7, 1 segment, no probability):
`WARNING Hwange: grazing drying fast. Sell weak animals early while prices hold, plan herd moves. Reply 1 ok 2 poor 3 bad. STOP to quit`

---

## Minute by minute

### 0:00–0:15 · The line to beat

| Driver | Speaker says |
| --- | --- |
| Tab 1 is already on `?country=Zimbabwe&t=57`. Point at the red dashed line. | "Zimbabwe, October 2023. Ninety-one districts. The red line is 3 April 2024, the day the drought became a national disaster. Everything here is real data, nothing is simulated." |

### 0:15–0:55 · The forecast (the centrepiece)

| Driver | Speaker says |
| --- | --- |
| Press `3` (forecast +3), then `L` until the layer is **FEWS NET outlook**. | "This is the forecast issued in October 2023, using only what was public then. FEWS NET says Phase 2, stressed, until January." |
| Press `4`, `5`, `6`, `7`: the map steps to Phase 3 (38 districts). | "From February it says Crisis. FEWS NET updates about three times a year, so it moves in steps." |
| Press `L` to get **both**, then `4`. Click **Mbire** (north). The chart shows 15 % at +1…+3 and 57 % at +4. | "Our model turns that into a number for each district, every month. Mbire, in the north: 15 percent now, 57 percent by February. Forty districts, almost six million people, are above our line." |

Insurance: `?country=Zimbabwe&t=57&view=f4&layer=both&county=Mbire`

### 0:55–1:15 · Before the declaration

| Driver | Speaker says |
| --- | --- |
| `→` four times to Feb 2024 (t=61). Press `2`. Point at the Top-10 list. | "February 2024, five weeks before the declaration. Thirty-three districts, nearly five million people, have a high chance of Crisis by April. This is 'Ready': it goes to aid workers, not farmers, and it is allowed to be wrong." |

Insurance: `?country=Zimbabwe&t=61&view=f2`

### 1:15–1:35 · From Ready to Go

| Driver | Speaker says |
| --- | --- |
| Press `0` (Now). `→` to Mar 2024 (t=62): everything yellow, 7 orange. `→` to Apr 2024 (t=63): 22 orange. | "Now the observed levels. Ready since November, everywhere. Warning needs proof from space, dry plants plus dry rain or soil, two months in a row. Seven districts in March, twenty-two in April." |
| Click **Hwange** (or the deep link). Panel: No grass, 3/3, high. Click the **Herders** tab. | "Hwange, cattle country. No grass. All three families agree. The herder gets one SMS, one action, no percentage." |

Insurance: `?country=Zimbabwe&t=63&county=Hwange`

### 1:35–2:35 · The live SMS loop (jury member)

| Who | Does | Speaker says |
| --- | --- | --- |
| Jury member | Texts **JOIN Hwange herder** to the number on the card. | "Please text JOIN Hwange herder." |
| Driver | **Users joining** tab: the row appears within about 5 s. | "The AI read it, matched Hwange to our district list, and asks you to confirm." |
| Jury member | Replies **YES**. | |
| Driver | **Map**, check the clock says **Apr 2024**, click **Run alerts for this month**. Then **Alert feed**: Hwange is "Waiting for approval". Click **Approve & send** on **Hwange only**. | "A Warning never goes out by itself. A person approves it." |
| Jury member | The phone buzzes with the Warning above. | "Read it out, please." |
| Jury member | Texts **how do I save my cattle?** | "Ask it something." |
| Phone | The reply is livestock advice from the approved list. | "The answer comes only from advice WHH approved. The AI does not invent it." |
| Jury member | Texts **3** | "Now report: three means bad." |
| Driver | **Map**: Hwange shows a crowd badge (✔), the panel says "crowd-confirmed · already at Warning", and the feed says "crowd report: Hwange 3 of 5 say failed". | "Your report confirms the satellite. Replies can confirm a level. They can never trigger one." |
| Jury member | Texts **We need help** | |
| Phone / Driver | Reply: "An officer will contact you soon…". A help request opens. | "Distress goes straight to a person." |

15-second rule: if the jury phone has not buzzed 15 s after Approve, switch to Fallback A without comment.

### 2:35–3:00 · Today

| Driver | Speaker says |
| --- | --- |
| Close the panel (`esc`). Click **Go to today** (Sep 2026). Press `1`. | "This is today, September 2026, the dry season. Zimbabwe is calm. The leads say 'no model forecast': we forecast the rainy season, and the first 2026/27 forecast comes with the October data." |
| (Only if 10 s are left) Tab 2: `?country=Kenya&t=92&view=f1`. | "Kenya's short rains start now. The live forecast is already running there." |
| Back to the deck, slide 6. | "Forecasts to get ready, satellites to act, one SMS to the person who decides." |

Never say "weeks early" about the Hwange SMS. If asked: "The Warning came the month of the declaration. The Ready signal came in November, and the district forecast by February."

---

## Deep links (Tab 2, checked against the 20:07 file)

```
http://localhost:8777/?country=Zimbabwe&t=57                                  Oct 2023, Now: 37 Watch, 0 Warning
http://localhost:8777/?country=Zimbabwe&t=57&view=f3&layer=fews               Oct 2023 → Jan 2024: FEWS Phase 3+ in 26 (Mbire Phase 2)
http://localhost:8777/?country=Zimbabwe&t=57&view=f4&layer=both&county=Mbire  Oct 2023 → Feb 2024: Mbire 57 %, FEWS Phase 3; 40 districts ≥ 57 %
http://localhost:8777/?country=Zimbabwe&t=61&view=f2                          Feb 2024 → Apr 2024: 33 districts ≥ 57 %
http://localhost:8777/?country=Zimbabwe&t=62                                  Mar 2024: 91 Watch, 7 Warning
http://localhost:8777/?country=Zimbabwe&t=63&county=Hwange                    Apr 2024: 22 Warning; Hwange no grass, herder SMS
http://localhost:8777/?country=Zimbabwe&t=63&county=Mbire                     Apr 2024: Mbire Warning, no grass (north)
http://localhost:8777/?country=Zimbabwe&t=92                                  Today, Sep 2026: 87 Normal, 4 Watch
http://localhost:8777/?country=Kenya&t=92&view=f1                             Kenya today, +1 (Oct 2026): West Pokot 43 %, Baringo 37 %
```
Add `&api=http://localhost:8000` if the backend runs on another host or port.

## Fallbacks, in order

- **A. On-screen phone (simulator).** Same router, same backend, no radio. In the **Phone** tab type `JOIN Hwange herder` → `YES`, then run and approve as above, then `how do I save my cattle?` → `3` → `We need help`. Say: "Venue radio is slow, so here is the same conversation on screen. The code path is identical."
- **B. Pre-seeded herder.** `backend/seed_demo.py` has "Demo Herder Hwange". Before the session, re-point it to a team phone (local `.env` only, never commit it). If the jury JOIN never arrives, approve Hwange and hand the team phone to the jury member.
- **C. Backend down.** The map works without the backend. Finish the forecast and map part, then play the video for the SMS loop.
- **D. Backup video** (Tab 3, local file, muted). The full 3 minutes, recorded the night before. The Speaker talks over it. Apologise in one sentence at most.

---

## T-30 checklist

**Data**
- [ ] Run the verify command below. The output must match the expected lines. If it does not, the file changed: update this page and slides 4–6 before going on stage.

```bash
cd /home/looooo/bcg/Hackathon-BCG && python3 -I - <<'EOF'
import json
s = open('data/risk/ZWE.js').read(); k = 'RISK_DATA["ZWE"] ='
j, _ = json.JSONDecoder().raw_decode(s[s.index(k) + len(k):].lstrip())
U = {u['name']: u for u in j['units']}; m = j['meta']
print(m['generated_at'], m['live_t'])
print('Watch+  t57-66', [sum(u['series'][t]['level'] >= 1 for u in j['units']) for t in range(57, 67)])
print('Warning t57-66', [sum(u['series'][t]['level'] >= 2 for u in j['units']) for t in range(57, 67)])
f = U['Mbire']['series'][57]['forecast']
print('Mbire t57', [(k, f[k]['p_crisis'], f[k]['fews_phase']) for k in '1234567'])
print('t61 +2 >=0.57', sum((u['series'][61]['forecast']['2']['p_crisis'] or 0) >= 0.57 for u in j['units']))
h, p = U['Hwange']['series'][63], U['Hwange']['series'][62]
print('Hwange t63', p['level'], '->', h['level'], h['event'], h['agreeing'], h['confidence'], h['p'])
EOF
```
Expected:
```
2026-10-16T20:07:34+00:00 92
Watch+  t57-66 [37, 91, 91, 91, 91, 91, 91, 91, 91, 91]
Warning t57-66 [0, 0, 0, 3, 4, 7, 22, 50, 50, 46]
Mbire t57 [('1', 0.152, 2), ('2', 0.152, 2), ('3', 0.152, 2), ('4', 0.565, 3), ('5', 0.565, 3), ('6', 0.565, 3), ('7', None, 3)]
t61 +2 >=0.57 33
Hwange t63 1 -> 2 no_grass 3 high 0.832
```

**Stack**
- [ ] `scripts/start_demo.sh --fresh`. This wipes `backend/demo.db`, starts the backend on :8000 and the site on :8777, and seeds the demo users. All checks must say `[ok]`.
- [ ] `/home/looooo/bcg/.venv/bin/python -m backend.seed_crowd --district Hwange`. `start_demo.sh` does **not** do this, and the default district is Hurungwe. It seeds 4 reports, share 0.50, so the jury's "3" tips it to 3 of 5.
- [ ] The backend dot in the top bar is green. Zimbabwe shows LIVE.
- [ ] Dry run in the **Phone** tab: `JOIN Hwange herder` → `YES` → Run alerts at Apr 2024 → Approve Hwange. The herder text appears. Then run `scripts/start_demo.sh --fresh` again and re-seed the crowd, so the live run creates a new event.
- [ ] From the Phone tab, `how do I save my cattle?` gets advice (this proves the Claude key works). `We need help` gets the officer reply.

**Gateway**
- [ ] Real SMS: `GATEWAY=android` and `ANDROID_GW_URL/USER/PASS` in `.env`. Run with `BACKEND_HOST=0.0.0.0` if the phone must reach the laptop. `python backend/check_gateway.py +2126…` reaches a team phone within 10 s.
- [ ] Gateway phone charged above 60 %, plugged in, screen lock off, battery saver off for the gateway app. The SIM has credit for 50+ SMS. The number is on the cards.
- [ ] No radio or no credit: stay on `GATEWAY=sim` and use Fallback A from the start.

**Browser and people**
- [ ] Chrome, one window. Tab 1 `?country=Zimbabwe&t=57`, Tab 2 the deep links, Tab 3 the video. Notifications off. Zoom 125 %. Speed **1×**.
- [ ] Driver has rehearsed the click path 3 times, including Fallback A. Phone knows the 15-second rule.
- [ ] Nobody opens Malawi (monitoring only) or the countries that stop in 2024. Nobody says a number that is not on this page or a slide.
- [ ] Optional regression: `node tests/e2e/demo_flow.js --runs 1` (on its own ports, about 3 min). It was last run on the 18:40 export, so if it fails, compare the failure with this page.
