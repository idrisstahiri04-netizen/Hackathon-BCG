# Live demo script — 3 minutes

Companion to `docs/pitch.md` (slide 5). Three people:

| Role | Who | Has |
| --- | --- | --- |
| **Speaker** | talks, never touches the laptop | printed copy of this page |
| **Driver** | laptop, browser, clicks | second tab with deep links, third tab with the backup video |
| **Phone** | holds the gateway Android phone, watches the jury phone | gateway app open, charger |

Everything shown is real: real satellite data, real model output, real SMS. Say so once, early.

Built against the **final export** `data/risk/ZWE.js`, `sat-v1-ensemble-ZWE_KEN_MWI_ZMB`, **16:53 UTC**.
Month index `t`: 0 = Jan 2019 · 57 = Oct 2023 · 62 = Mar 2024 · 63 = Apr 2024 (declaration 3 Apr) · 66 = Jul 2024.
Months are **issue months**: the level at t is issued at the end of month t from data of month t-1
(latency already applied; never add it again, never call them data months).

## The one rule that decides the live SMS

`/alerts/run` creates an event for a district **only in the month its level rises** (`backend/app.py`,
`lvl <= plvl: continue`). The event's type fixes the audience (`backend/composer.py`): Warning with
event `no_grass` → **herders**; any other Warning event → **farmers**; Emergency → everyone. So the
jury member's role must match the event type **of the rise month**. A herder in a district whose rise
month says *crop failure* receives nothing (red-team finding, `docs/redteam.md` §2).

**Live choice: `JOIN Hwange herder`, alerts run at t = 63.** In the final export Hwange rises 0 → 2 at
t=63 with event `no_grass`, all three families, confidence high, p 0.69, drivers "cropland greenness
9/100", "grazing land greenness 15/100", "topsoil moisture -1.9 SD". Same month, same role, same event
for Tsholotsho, Bulilima, Plumtree, Umguza, Victoria Falls (fallback districts, all herder/no_grass at t=63).

### Verify on the day (Driver, after any re-export)

```bash
cd /home/looooo/bcg/Hackathon-BCG && python3 -I - <<'EOF'
import json
s = open('data/risk/ZWE.js').read()
j = json.loads(s[s.index('= {') + 2:].rstrip().rstrip(';'))
print(j['meta']['model_version'], j['meta']['generated_at'])
print('HERDER-eligible rises (level rises to 2 with event no_grass, or to 3), Oct 2023..Jun 2024:')
for u in j['units']:
    ser = u['series']
    for t in range(57, 66):
        c, p = ser[t], ser[t - 1]
        if c['level'] >= 2 and c['level'] > p['level'] and (c['event'] == 'no_grass' or c['level'] == 3):
            print(f"  t={t}  {u['name']:<24} L{c['level']} {c['event']:<12} agree={c['agreeing']} {c['confidence']:<6} p={c['p']:.2f} drivers={len(c['drivers'])}")
print('Watch+ count t57..66:', [sum(1 for u in j['units'] if u['series'][t]['level'] >= 1) for t in range(57, 67)])
print('Warning+ count t57..66:', [sum(1 for u in j['units'] if u['series'][t]['level'] >= 2) for t in range(57, 67)])
EOF
```

Expected with the 16:53 file: `Hwange` at `t=63 L2 no_grass agree=3 high p=0.69 drivers=3`;
Watch+ `[13, 13, 12, 3, 4, 22, 69, 84, 83, 51]`; Warning+ `[0, 0, 0, 0, 0, 4, 26, 43, 48, 33]`.
If any of this differs, the file changed again: pick the earliest northern herder-eligible row, update
the district and `t` below and on slide 5, and tell the pipeline owner to re-run the judge.

Other facts the lines below rely on (16:53 file):
- t=57 (Oct 2023): 13 districts at Watch (south-east and Harare), none at Warning.
- t=62 (issued end of March 2024): **22 at Watch**, including **Mbire, Karoi, Rushinga** (all three families, confidence high) and Uzumba Maramba Pfungwe; **4 at Warning** (Chitungwiza, Epworth, Harare Rural, Ruwa; crop failure).
- t=63 (issued end of April, the red line): **26 at Warning**: Hwange, Hwange Urban, Tsholotsho, Bulilima, Plumtree, Victoria Falls, Bulawayo, Umguza, Umzingwane, Insiza, Bubi, Bindura, Marondera, Goromonzi, Seke, Mudzi, Kadoma Urban and the Harare units. 4 at Emergency (Harare-area units).
- 48 of 91 reach Warning by June; Hwange is back to Normal at t=66 (Jul 2024).
- Wet 2020/21: zero Warnings; 2020: zero Emergency. Safe to scrub anywhere, but the 3 minutes stay in Oct 2023 – Jul 2024.
- Mbire never reaches Warning in the final export (Watch from t=61). Do not promise a Mbire Warning.
- Do not point at t=62 Hwange: all three families agree, p 0.69, but level 0 (hysteresis: first run). If asked: "The signals are there in March; the level waits for a second run. That is the rule that keeps wet years quiet."

---

## Minute by minute

### 0:00 – 0:25 · The globe, the country, the line to beat

| Driver | Speaker says |
| --- | --- |
| Tab 1 is already on `http://localhost:8777/?country=Zimbabwe&t=57`. Globe shows Zimbabwe, 91 districts, timeline at Oct 2023. Thirteen yellow in the south-east, nothing orange. | "This is Zimbabwe, October 2023, start of the rainy season. Ninety-one districts, none at Warning; a few on Watch in the south-east from the last dry year. Every colour you will see is real satellite data and real model output; nothing is simulated." |
| Points cursor at the red dashed line on the timeline. | "The red line is 3 April 2024, the day the government declared a national disaster." |

Stage insurance: if the page did not load, reload the same URL. If the globe is black, see Fallbacks.

### 0:25 – 1:05 · Play the season

| Driver | Speaker says |
| --- | --- |
| Press **space** at 2× speed. Nov, Dec, Jan, Feb pass; the map goes quiet (3–4 yellow). | "Rains came late. The system stays quiet while it is unsure; that is on purpose." |
| At **Mar 2024 (t=62)** press **space** to pause. 22 yellow, 4 orange around Harare. | "End of March, days before the declaration. Twenty-two districts on Watch, Mbire, Karoi and Rushinga in the north among them, all three families agreeing: rain, plants, soil. Watch goes to NGOs and extension officers, not to farmers." |
| Step once with **→** onto t=63, the red line. 26 orange. | "End of April: twenty-six districts tip to Warning. Hwange, Tsholotsho, Bulilima, Victoria Falls. Four weeks after the declaration, not before. We will show you why we accept that in a minute." |

Stage insurance: `?country=Zimbabwe&t=62` (22 Watch, 4 Warning), `?country=Zimbabwe&t=63` (26 Warning). Both bookmarked in Tab 2.

### 1:05 – 1:40 · One district, one message

| Driver | Speaker says |
| --- | --- |
| Still at t=63. Click **Hwange** on the map. Detail panel opens. | "Hwange, north-west, cattle country. Event: *no grass*. All three families agree. Confidence high. Drivers in plain words: grazing land greenness fifteen out of a hundred, cropland nine, topsoil moisture far below normal." |
| Click the **Herders** tab in the panel. Point at the character count. | "The herder gets one SMS, one segment, 160 characters, one action: sell weak animals early while prices hold. No probability. The NGO tab is the one with the number." |

Stage insurance: `?country=Zimbabwe&t=63&county=Hwange` opens straight on the panel.

### 1:40 – 2:35 · The live SMS moment (jury member)

Before the demo the Phone person has asked one jury member to keep their phone out. The Moroccan
gateway number is on a card and on slide 5.

| Who | Does | Speaker says |
| --- | --- | --- |
| Jury member | Texts **JOIN Hwange herder** to the gateway number. | "Please send *JOIN Hwange herder* to the number on the card." |
| Driver | Clicks the **Users joining** tab. Within ~5 s the new subscriber appears; Claude Haiku has read the text and matched the district. | "There you are. The AI read your message, matched Hwange to our district list, and signed you up as a herder. It asks you to confirm." |
| Jury member | Replies **YES**. | |
| Driver | Back to **Map**, confirm the clock says **Apr 2024 (t=63)**, click **Run alerts for this month**. Then the **Alert feed** tab: the Hwange Warning event sits at *pending approval* among the others created for that month. | "April 2024, the month Hwange's grazing signal tipped it into Warning. A Warning never goes out by itself. A human approves it." |
| Driver | Clicks **Approve & send** on the **Hwange** event only. | "Approved. Sent." |
| Jury member | Phone buzzes: the real herder Warning for Hwange, one segment. | "Read it out, please." (pause for the message) |
| Jury member | Replies **We can't manage** (or anything in that spirit). | "Now tell us you need help." |
| Driver | **Alert feed / messages**: intent *ask_help*, reply "An officer will contact you", a help request is open. | "The AI did not try to be a hero. It opened a help request and a person takes over. That is the whole loop: watch, tell one person, listen back." |

Timing guard: if the jury's phone has not buzzed within 15 seconds of Approve, go to Fallback A without comment.

Never say "weeks early" about this message. If a judge asks about lead time, answer: "With real data
delays, Warning came four weeks after the declaration; Watch came days before, in twenty-two districts.
An earlier, looser model warned forty-six districts before the declaration but also lit up every district
every year. We kept the strict one. Zero warnings in the wet year before."

### 2:35 – 3:00 · Close

| Driver | Speaker says |
| --- | --- |
| Scrub to **Jul 2024 (t=66)**; Hwange and many others have stepped down. Then back to the pitch deck, slide 6. | "After the crisis, levels stand down slowly, three runs, so nobody gets a false all-clear. Everything you saw runs on free data, one model run a month, and a phone with a SIM card. The honest numbers are on the next slide." |

---

## Deep links (Tab 2, in this order)

```
http://localhost:8777/?country=Zimbabwe&t=57                     Oct 2023, 13 Watch, no Warnings
http://localhost:8777/?country=Zimbabwe&t=62                     end Mar 2024: 22 Watch (north incl.), 4 Warning
http://localhost:8777/?country=Zimbabwe&t=63                     end Apr 2024, red line: 26 Warning
http://localhost:8777/?country=Zimbabwe&t=63&county=Hwange       Hwange panel: no grass, 3 families, herder SMS
http://localhost:8777/?country=Zimbabwe&t=62&county=Mbire        Mbire at Watch, 3 families (for the "north" question)
http://localhost:8777/?country=Zimbabwe&t=66                     Jul 2024, standing down
```

Append `&api=http://localhost:8000` if the backend runs on another host or port.

Only use Zimbabwe on stage. Zambia and Malawi files (`data/risk/ZMB.js`, `MWI.js`) are still the
**16:29–16:31 exports** with the old thresholds and no latency; do not open them until re-exported.
Kenya (16:52) only if someone has checked it.

## Fallbacks, in order

**A. Phone tab (on-screen simulator).** Same router, same backend, no radio.
Driver clicks **Phone** tab, types `JOIN Hwange herder`, then `YES`, then runs/approves the t=63 alert exactly
as above; the Warning appears in the on-screen thread; type `We need food help`. Speaker: "The venue radio is
slow, so here is the same conversation on screen; the code path is identical."

**B. Pre-seeded subscriber.** `backend/seed_demo.py` already holds "Demo Herder Hwange" on a placeholder
number; before the session re-point it to a real team phone (local `.env`-driven run only, never committed).
If the jury member's JOIN never arrives, approve the Hwange event; the team phone buzzes; hand it to the jury
member to read and reply.

**C. Backend down.** The map still works without the backend (Phone/Users/Alert tabs show "Backend
offline"). Finish the map part, then play the recorded video for the SMS loop.

**D. Recorded video (Tab 3, local file, muted).** Full 3-minute run recorded the night before.
Driver presses play; Speaker narrates over it with the same lines. Never apologise for more than one sentence.

---

## Pre-demo checklist (T-30 min)

Backend and data
- [ ] `head -1 data/risk/ZWE.js` says `Real model output - pipeline/export_risk.py (sat-v1-…)`, not `STUB`. Zimbabwe shows `LIVE` in the country list.
- [ ] Run the **Verify on the day** command; output matches the expected lines (Hwange t=63 herder; Warning+ `[0,0,0,0,0,4,26,43,48,33]`). If not, update this page and slide 5, and tell the pipeline owner to re-run `judge.py` / `compare_ipc.py`.
- [ ] `python3 -m http.server 8777` running from the repo root (not `file://`). Open `http://localhost:8777` once; globe renders, textures load (vendored, no network needed).
- [ ] Backend: `/home/looooo/bcg/.venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port 8000`; `curl -s localhost:8000/health` returns ok; the `backend …` dot in the top bar is green.
- [ ] `.env` has `ANTHROPIC_API_KEY`; from the Phone tab send `JOIN Mbire farmer` and get the confirmation question back (proves the Haiku router works, not just the keyword fast-path).
- [ ] `backend/demo.db` deleted (clean reset), then `python -m backend.seed_demo`, then the Fallback-B team phone set as herder in Hwange.
- [ ] **Dry run of the exact live path:** Phone tab `JOIN Hwange herder` → `YES`; `POST /alerts/run {"iso3":"ZWE","t":63}`; approve the Hwange event; the simulated phone shows the **herder** text (sell weak animals). If it shows a farmer text or nothing, the role/event do not match: re-run the verify command and pick another row. Then delete `demo.db` and re-seed so the live run creates a fresh event (the run de-duplicates on unit + month + level).
- [ ] `MONTHLY_CAP` default 6 is fine; the jury member receives at most one alert.

Android gateway
- [ ] Gateway phone charged > 60 %, charger plugged in, screen-lock off, battery optimisation off for the gateway app.
- [ ] `GATEWAY=android` in `.env`, `ANDROID_GW_URL/USER/PASS` set; `python backend/check_gateway.py` passes; `python backend/check_gateway.py +2126XXXXXXXX` arrives on a team phone within 10 s.
- [ ] Inbound webhook works (HTTPS tunnel up if cloud mode): text `STOP` from a team phone, see it in **Alert feed / messages**, then re-subscribe the team phone.
- [ ] Moroccan SIM has credit for at least 50 SMS; the number is printed on cards and on slide 5.
- [ ] Phone person has the jury member's consent; one test SMS to them before the session if possible.

Browser
- [ ] Chrome, one window, three tabs: (1) demo at `?country=Zimbabwe&t=57`, (2) deep links, (3) backup video. All other tabs and notifications closed.
- [ ] Zoom 125 % for the projector; check the detail panel and the SMS character count are readable from the back of the room.
- [ ] Playback speed 2× selected; `space`, `←`, `→` tested; `esc` closes the panel.
- [ ] Projector resolution checked; the feed column and timeline are both visible (no cut-off at the bottom).
- [ ] Wifi may be off entirely: the globe is offline-safe. Only the backend's Claude calls and the gateway (cloud mode) need internet; if venue wifi is down, use the phone's hotspot for the laptop.

People
- [ ] Speaker has this page printed; the numbers 22 / 4 / 26 / 48 / zero-in-2020-21 match slide 6.
- [ ] Driver has rehearsed the click path three times, including Fallback A.
- [ ] Phone person knows the 15-second rule and the hand-off for Fallback B.
- [ ] Nobody says a number that is not on a slide. Nobody says "weeks early" about the Hwange message. Nobody opens Malawi or Zambia.
