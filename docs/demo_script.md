# Live demo script: 3 minutes (Kenya)

Goes with `docs/pitch.md` (slide 5). Two people: **Speaker** (talks, never touches the laptop) and **Driver** (laptop; Tab 1 demo, Tab 2 deep links, Tab 3 backup video).

**SMS gateway: to be set up later.** The Android phone, the reply loop and live Claude replies are pending (API key pending). Until then show the message preview and the Alert log. Do not promise a phone buzz.

Data: `data/risk/KEN.js` (`sat-v1-ensemble-ZWE_KEN_MWI_ZMB`), **290 sub-counties**. The app calls them "counties" in some labels.
Month index: t=0 is Jan 2019. t=30 Jul 2021 · **t=32 Sep 2021 (declaration 8 Sep 2021, red dashed line)** · t=56 Sep 2023 · **t=92 Sep 2026 (today)**.
Every month is an issue month: issued at the end of month t.
Keys: arrows one month, `0` Now, `1` +1, `3` +3, `6` +6, `F` Now / forecast, `L` layer (our model / FEWS NET / both), `esc` closes the panel.
Tabs: **Map** and **Users**. The right panel is the **Alert log**.

## Facts the lines use (counted on the KEN.js above)

| Moment | On screen |
| --- | --- |
| Jul 2021 (t=30), Now | 7 sub-counties at Warning (1.3 M people), 109 at Watch or worse. Warning: Dadaab, Fafi (Garissa), Garsen (Tana River), Isiolo North, Isiolo South, Lamu West, Turkana North |
| Jul 2021, FEWS layer | +3 (Oct 2021): 34 sub-counties at Phase 3+, 8.4 M people. Main: Garissa, Mandera, Wajir, Turkana (6 each). Phase 4+: none |
| Banissa (Mandera), Jul 2021, +3 | Our level Watch. FEWS Phase 3 (published Jul 2021). Government bullets: "Based on: FEWS NET Phase 3" |
| Sep 2021 (t=32), Now | 7 at Warning (1.3 M people), 123 at Watch or worse. Warning: Dadaab, Fafi, Garsen, Ijara, Isiolo North, Isiolo South, Lamu West |
| Sep 2023 (t=56), Now | 2 at Warning (0.4 M people): Kacheliba (West Pokot) and one in Baringo |
| Kacheliba (West Pokot), Sep 2023 | Watch in Aug, **Warning in Sep**. Event: no grass. 3 of 3 families agree, confidence high. Drivers: cropland greenness 0/100, grazing land greenness 13/100, topsoil moisture -2.3 SD. Population 230 k. FEWS Phase 2 |
| Today (t=92), Now | 1 at Warning (West Pokot, 0.2 M people), 121 at Watch or worse |
| Today, FEWS layer, +1 and +3 | Oct and Dec 2026: 29 sub-counties at Phase 3+, 7.7 M people. Garissa, Mandera, Wajir, Turkana (6 each), Tana River (3), Lamu (2). Phase 4+: none |

Dropped (cannot count on the current data): any "chance of Crisis >= 57 %" headline. The model chance is per event, not stable across leads. Say it only if a juror asks.

Herder SMS (137 characters, all GSM-7, one segment, no probability):
`WARNING Kacheliba: grazing drying fast. Sell weak animals early while prices hold, plan herd moves. Reply 1 ok 2 poor 3 bad. STOP to quit`
(The Swahili text is not offered: the Users page has English, Shona, Ndebele, French only.)

Role bullets follow the FEWS phase: Phase 3 = "prepare", Phase 4-5 = "respond", no FEWS = our level. The line "Based on: FEWS NET Phase N" or "Based on: our model" shows it. Only Warning (orange) and Emergency (red) are notified.

Kenya has two rainy seasons (long rains Mar-May, short rains Oct-Dec). Forecast labels may read "OND 2021 season": say "short-rains season".

---

## Minute by minute

### 0:00-0:10 Landing and role
Open `http://localhost:8777/`. The Mapema logo types in. Click **Government** (or NGO / Food bank). Search "Kenya".
Say: "Mapema. Early warning for food shortage. Kenya, 290 sub-counties, real satellite data."

### 0:10-0:25 The line to beat
Go to Jul 2021 (t=30). Point at the red dashed line (8 Sep 2021).
Say: "July 2021. The red line is 8 September, when the drought became a national disaster. Seven sub-counties are at Warning. Nothing is simulated."

### 0:25-1:05 The forecast (centrepiece)
Press `3`, then `L` to FEWS NET: 34 sub-counties at Phase 3 for Oct 2021, 8.4 M people. Press `L` to both. Click **Banissa**: FEWS Phase 3, our level Watch. Show the Government bullets and "Based on: FEWS NET Phase 3". Switch role to NGO / Food bank: bullets change.
Say: "Three months ahead. The outline is FEWS NET, the fill is our model. Thirty-four sub-counties head for Crisis. Each audience gets its own actions."
Link: `?country=Kenya&t=30&view=f3&layer=both&county=Banissa&role=gov`

### 1:05-1:25 Ready, then Go
Press `0`. Step to Sep 2021 (t=32): 7 orange.
Say: "Observed levels. Warning needs proof from space in three families, two months in a row. Seven on the day of the declaration. The forecast is early. Warning confirms."

### 1:25-2:20 The alert (Sep 2023)
Go to Sep 2023 (t=56), click **Kacheliba**: Warning, no grass, 3 of 3, high, drivers. Look at the Alert log: Kacheliba went Watch to Warning.
Open the **Users** tab: add a herder by hand (name, phone, district Kacheliba, role herder). Go back to Map.
In the Alert log click **Approve & send** on Kacheliba only (needs the backend).
Say: "A person approves every Warning. Users are added by hand for now. The farmer gets one action, never a probability."
Show the herder SMS above in the detail panel (message preview).
**SMS gateway: to be set up later.** No phone buzz in this version.

### 2:20-3:00 Today (Sep 2026)
Go to today (t=92), press `1` or `3`, layer FEWS: 29 sub-counties at Phase 3+, 7.7 M people (Garissa, Mandera, Wajir, Turkana, Tana River, Lamu).
Say: "The short rains start. Twenty-nine sub-counties are projected in Crisis, mostly in the north-east and north-west. Forecast to get ready, satellites to act, one SMS to the person who decides."
Never say "weeks early" about the SMS. If asked: "The forecast was early. The Warning confirms."

---

## Deep links (Tab 2)
The `role` param is needed to skip the landing page (`gov` or `ngo`). Params: `country`, `t`, `view` (now, f1, f3, f6), `layer` (model, fews, both), `county` (sub-county name), `role`.
```
http://localhost:8777/?country=Kenya&t=30&role=gov                                    Jul 2021: 7 Warning
http://localhost:8777/?country=Kenya&t=30&view=f3&layer=fews&role=gov                 FEWS Phase 3+: 34 sub-counties
http://localhost:8777/?country=Kenya&t=30&view=f3&layer=both&county=Banissa&role=gov  Banissa: FEWS 3, Government bullets
http://localhost:8777/?country=Kenya&t=32&role=gov                                    Sep 2021: 7 Warning
http://localhost:8777/?country=Kenya&t=56&county=Kacheliba&role=gov                   Sep 2023: Kacheliba Warning
http://localhost:8777/?country=Kenya&t=92&view=f3&layer=fews&role=gov                 Today: 29 at Phase 3+
```
Add `&api=http://localhost:8000` if the backend is on another host. `view=f1` also works.

## Fallbacks
- **A. No SMS gateway (now):** show the message preview in the detail panel and the Alert log row. "Same code path, no radio yet."
- **B. Backend down:** the map, forecast and role bullets work alone. The Alert log lists events but "Approve & send" is missing; say "sending needs the backend" and move on. Users page shows "Backend offline".
- **C. Backup video** (Tab 3).

## T-30 checklist
```bash
cd /home/looooo/bcg/Hackathon-BCG && grep -c "" data/risk/KEN.js && python3 -m http.server 8777
```
- [ ] Open the six deep links: each loads, no red errors in the console.
- [ ] Counts above match the screen (stat card top left: 7, 34 / 8.4M, 7, 29 / 7.7M).
- [ ] If `data/risk/KEN.js` is regenerated: recount, update this page and slides 4-6.
- [ ] Backend (optional): Alert log shows "Approve & send" on Kacheliba at t=56.
- [ ] Chrome, one window, zoom 125 %. Nobody says a number not on this page or a slide.
