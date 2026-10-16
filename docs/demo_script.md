# Live demo script — 3 minutes

Companion to `docs/pitch.md` (slide 5). Three people:

| Role | Who | Has |
| --- | --- | --- |
| **Speaker** | talks, never touches the laptop | printed copy of this page |
| **Driver** | laptop, browser, clicks | second tab with deep links, third tab with the backup video |
| **Phone** | holds the gateway Android phone, watches the jury phone | gateway app open, charger |

Demo district: **[DISTRICT PENDING]** — the northern district that reaches Warning earliest in
`pipeline/out/model_report.md`. Default if nothing better: **Mbire** (Zambezi valley, already in the
Phone-tab quick messages). Month index `t`: 0 = Jan 2019, 57 = Oct 2023, 63 = Apr 2024 (declaration).
First-Warning month for the demo district: **t = [NUMBER PENDING]** ([MONTH PENDING]).

Everything shown is real: real satellite data, real model output, real SMS. Say so once, early.

---

## Minute by minute

### 0:00 – 0:25 · The globe, the country, the line to beat

| Driver | Speaker says |
| --- | --- |
| Tab 1 is already on `http://localhost:8777/?country=Zimbabwe&t=57`. Globe shows Zimbabwe, all 91 districts green, timeline at Oct 2023. | "This is Zimbabwe, October 2023, start of the rainy season. Ninety-one districts, all green. Every colour you will see comes from real satellite data and our model; nothing is simulated." |
| Points cursor at the red dashed line on the timeline. | "The red line is 3 April 2024, the day the government declared a national disaster. That is the line to beat." |

Stage insurance: if the page did not load, reload the same URL. If the globe is black, see Fallbacks.

### 0:25 – 1:05 · Play the season

| Driver | Speaker says |
| --- | --- |
| Press **space** (or the play button) at 2× speed. Watch Nov, Dec, Jan. | "Watch the north. Rain family first, then the plants, then the soil." |
| When the first district turns **orange (Warning)** at t = [NUMBER PENDING], press **space** to pause. | "[MONTH PENDING]. [DISTRICT PENDING] is at Warning. That is [NUMBER PENDING] weeks before the declaration. Two independent families agree, and the level has held for two runs; one cloudy month cannot do this." |
| Let it run to t = 63, pause on the red line. | "By the declaration day, [NUMBER PENDING] of 91 districts are already orange or red. The system saw it first." |

Stage insurance: `?country=Zimbabwe&t=[NUMBER PENDING]` (first Warning) and `?country=Zimbabwe&t=63` (declaration day). Both bookmarked in Tab 2.

### 1:05 – 1:40 · One district, one message

| Driver | Speaker says |
| --- | --- |
| Click **[DISTRICT PENDING]** on the map. Detail panel opens: event type, drivers, families, SMS per audience. | "Click a district. Event: *no grass*. Drivers in plain words. Which of the three families agree. And the message each audience gets." |
| Click the **Herders** tab in the panel. Point at the character count. | "The herder gets one SMS, one segment, 160 characters, with one action: sell weak animals now. No probability. The NGO tab is the one with the number." |

Stage insurance: `?country=Zimbabwe&t=63&county=[DISTRICT PENDING]` opens straight on the panel.

### 1:40 – 2:35 · The live SMS moment (jury member)

Before the demo, the Phone person has asked one jury member to keep their phone out. The Moroccan
gateway number is on a card and on the slide.

| Who | Does | Speaker says |
| --- | --- | --- |
| Jury member | Texts **JOIN [DISTRICT PENDING] herder** to the gateway number. | "Please send *JOIN [DISTRICT PENDING] herder* to the number on the card." |
| Driver | Clicks the **Users joining** tab. Within ~5 s the new subscriber appears; Claude Haiku has read the text and matched the district. | "There you are. The AI read your message, matched the district to our list, and signed you up as a herder. It asked you to confirm with YES." |
| Jury member | Replies **YES**. | |
| Driver | Back to **Map**, scrub to t = [NUMBER PENDING] (first Warning for that district), click **Run alerts for this month**. Then **Alert feed** tab: the Warning event sits at *pending approval*. | "A Warning never goes out by itself. A human approves it." |
| Driver | Clicks **Approve & send**. | "Approved. Sent." |
| Jury member | Phone buzzes: the real herder Warning, one segment. | "Read it out, please." (pause for the message) |
| Jury member | Replies **We can't manage** (or anything in that spirit). | "Now tell us you need help." |
| Driver | **Alert feed / messages**: intent *ask_help*, reply "An officer will contact you", a help request is open. | "The AI did not try to be a hero. It opened a help request and a person takes over. That is the whole loop: see early, tell one person, listen back." |

Timing guard: if the jury's phone has not buzzed within 15 seconds of Approve, go to Fallback A without comment.

### 2:35 – 3:00 · Close

| Driver | Speaker says |
| --- | --- |
| Scrub past Apr 2024 to Jul 2024; districts stand down slowly. Then back to the pitch deck, slide 6. | "After the crisis, levels stand down slowly, three runs, so nobody gets a false all-clear. Everything you saw runs on free data, one model run a month, and a phone with a SIM card. The numbers behind it are on the next slide." |

---

## Deep links (Tab 2, in this order)

```
http://localhost:8777/?country=Zimbabwe&t=57                                  Oct 2023, all green
http://localhost:8777/?country=Zimbabwe&t=[NUMBER PENDING]                    first Warning month
http://localhost:8777/?country=Zimbabwe&t=63                                  declaration day
http://localhost:8777/?country=Zimbabwe&t=63&county=[DISTRICT PENDING]        district panel open
http://localhost:8777/?country=Zimbabwe&t=66                                  Jul 2024, standing down
```

Only use Zimbabwe on stage. Malawi (`?country=Malawi&t=62`, declaration 23 Mar 2024) and Zambia
(`?country=Zambia&t=61`, 29 Feb 2024) are answers to questions, not part of the 3 minutes. Kenya
is shown only if `data/risk/KEN.js` has real model output on the day.

## Fallbacks, in order

**A. Phone tab (on-screen simulator).** Same router, same backend, no radio.
Driver clicks **Phone** tab, types `JOIN [DISTRICT PENDING] herder` (or uses the quick button), then
`YES`, then runs/approves the alert exactly as above; the Warning appears in the on-screen thread; type
`We need food help`. Speaker: "The venue radio is slow, so here is the same conversation on screen; the
code path is identical."

**B. Pre-seeded subscriber.** If the jury member's JOIN never arrives, a team phone was subscribed
before the session as a herder in the demo district. Approve the alert; the team phone buzzes; hand it
to the jury member to read and reply.

**C. Backend down.** The map still works without the backend (Phone/Users/Alert tabs show "Backend
offline"). Finish the map part, then play the recorded video for the SMS loop.

**D. Recorded video (Tab 3, local file, muted).** Full 3-minute run recorded the night before.
Driver presses play; Speaker narrates over it with the same lines. Never apologise for more than one sentence.

---

## Pre-demo checklist (T-30 min)

Backend and data
- [ ] `data/risk/ZWE.js` header says `Real model output - pipeline/export_risk.py (sat-v1-…)`, not `STUB`. Zimbabwe shows `LIVE` in the country list.
- [ ] `python3 -m http.server 8777` running from the repo root (not `file://`). Open `http://localhost:8777` once; globe renders, textures load (vendored, no network needed).
- [ ] Backend running on `http://localhost:8000`: `curl -s localhost:8000/health` returns ok; the `backend …` dot in the top bar is green.
- [ ] `.env` has `ANTHROPIC_API_KEY`; send `JOIN Mbire farmer` from the Phone tab and get the confirmation question back (proves Haiku router works).
- [ ] `backend/demo.db` reset to a clean state, then the pre-seeded team herder re-added (Fallback B).
- [ ] `POST /alerts/run` for t = [NUMBER PENDING] produces the Warning event for the demo district; cancel or clear it afterwards so the live run creates a fresh one.

Android gateway
- [ ] Gateway phone charged > 60 %, charger plugged in, screen-lock off, battery optimisation off for the gateway app.
- [ ] `GATEWAY=android` in `.env`, `ANDROID_GW_URL/USER/PASS` set; gateway app shows "online"; test send to a team phone arrives within 10 s.
- [ ] Inbound webhook works: text `STOP` from a team phone, see it in **Alert feed / messages** (then re-subscribe the team phone).
- [ ] Moroccan SIM has credit for at least 50 SMS; the number is printed on cards and on slide 5.
- [ ] Phone person has the jury member's consent and their phone is on the same network family that tested fine (one test SMS to them before the session if possible).

Browser
- [ ] Chrome, one window, three tabs: (1) demo at `?country=Zimbabwe&t=57`, (2) deep links, (3) backup video. All other tabs and notifications closed.
- [ ] Zoom 125 % for the projector; check the detail panel and the SMS character count are readable from the back of the room.
- [ ] Playback speed 2× selected; `space`, `←`, `→` tested; `esc` closes the panel.
- [ ] Projector resolution checked; the feed column and timeline are both visible (no cut-off at the bottom).
- [ ] Wifi may be off entirely: the globe is offline-safe. Only the backend's Claude calls need internet; if wifi is down, use the phone's hotspot for the laptop.

People
- [ ] Speaker has this page printed with the `[PENDING]` numbers filled in by hand if they changed overnight.
- [ ] Driver has rehearsed the click path three times, including Fallback A.
- [ ] Phone person knows the 15-second rule and the hand-off for Fallback B.
- [ ] Slide 6 numbers match `pipeline/out/model_report.md` exactly; nobody says a number that is not on a slide.
