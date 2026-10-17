# Live demo script: 3 minutes (Kenya)

Goes with `docs/pitch.md` (slide 5). Three people: **Speaker** (talks, never touches the laptop), **Driver** (laptop; Tab 1 demo, Tab 2 deep links, Tab 3 backup video), **Phone** (gateway Android phone + the jury member's phone).

Data: `data/risk/KEN.js` (`sat-v1-ensemble-ZWE_KEN_MWI_ZMB`, generated 2026-10-17 01:30 UTC), 47 counties.
Month index: t=0 is Jan 2019. t=26 Mar 2021 · **30 Jul 2021** · **32 Sep 2021 (declaration 8 Sep 2021)** · **92 Sep 2026 (today)**.
Every month is an issue month: issued at the end of month t from data of month t-1.
Keys: `space` play/pause, arrows one month, `0` Now, `1`..`8` lead, `L` layer (model / FEWS NET / both), `esc` closes the panel. Play at 1x only.

## Facts the lines use (counted on the KEN.js above)

| Moment | On screen |
| --- | --- |
| Jul 2021 (t=30), Now | 22 counties Watch, 5 Warning (Garissa, Isiolo, Kilifi, Lamu, Turkana, all no_grass) |
| Jul 2021, forecast +1..+3 | FEWS NET Phase 3+: 13 counties. Our chance of Crisis >= 57 %: 12 counties, 8.9 M people (+1 to +3) |
| Isiolo, t=30 | FEWS Phase 3, our chance 87 %. Marsabit 69 %. Top: Wajir 87 %, Isiolo 87 % |
| Sep 2021 (t=32) | 26 Watch, 4 Warning (Garissa, Isiolo, Kilifi, Lamu). 10 counties >= 57 % (6.1 M people) |
| Lead | Of the 4 Warnings at declaration, the run had lasted a median 11 weeks. Watch ran a median 35 weeks in 26 counties. Watch is noisy (on in 31 counties in Mar 2021 and also in non-drought months) |
| Demo month (t=56, Sep 2023), sub-county data | Kacheliba: Warning, no_grass, 3 of 3 families, high (county-level counts above are from the 47-county run) |
| Today forecast +1..+3 (Oct-Dec 2026) | 8 counties >= 57 % chance of Crisis, 4.9 M people: Garissa, Isiolo, Mandera, Marsabit, Samburu, Tana River, Turkana, Wajir. FEWS Phase 3+: Garissa, Lamu, Mandera, Tana River, Turkana, Wajir |
| Kacheliba (West Pokot), t=56 | Rises Watch (Aug) to Warning (Sep). Drivers: topsoil moisture -3.3 SD, temperature +4.2 SD, cropland greenness 3/100. Population 0.62 M |

Herder SMS (138 septets, GSM-7, one segment, no probability):
`WARNING Kacheliba: grazing drying fast. Sell weak animals early while prices hold, plan herd moves. Reply 1 ok 2 poor 3 bad. STOP to quit`
Swahili (146 septets, **needs native review**):
`ONYO Kacheliba: malisho yanakauka haraka. Uza mifugo dhaifu mapema bei ikiwa nzuri, panga kuhamisha. Jibu 1 sawa 2 hafifu 3 mbaya. ACHA kujiondoa`

Kenya has two rainy seasons (long rains Mar-May, short rains Oct-Dec). Forecast labels for model leads can read "Nov 2021 season" instead of a month: say "short-rains season".

---

## Minute by minute

### 0:00-0:15 The line to beat
Tab 1 on `?country=Kenya&t=30`. Point at the red dashed line (8 Sep 2021).
Say: "Kenya, July 2021. Forty-seven counties. The red line is 8 September 2021, when the drought became a national disaster. All real data, nothing simulated."

### 0:15-1:00 The forecast (centrepiece)
Press `2`, then `L` to FEWS NET outlook: 13 counties at Phase 3. Press `L` to both. Click **Isiolo**: FEWS Phase 3, our chance 87 %.
Say: "This is what was public in July 2021. FEWS NET already says Crisis in the north. Our model puts a number on every county: twelve counties, almost nine million people, above our line, two months before the declaration."
Link: `?country=Kenya&t=30&view=f2&layer=both&county=Isiolo`

### 1:00-1:20 Ready, then Go
Press `0`. Step to Sep 2021 (t=32): 4 orange (Garissa, Isiolo, Kilifi, Lamu).
Say: "Observed levels. Warning needs proof from space, two months in a row. Four counties on the day of the declaration. It is honest: Warning is not early here, the forecast is."

### 1:20-2:30 Live SMS loop (jury member), today
Go to Sep 2023 (t=56), click **Kacheliba**: No grass, 3/3, high, Herders tab.
| Who | Does |
| --- | --- |
| Jury member | Texts "JOIN Kacheliba herder" (or the operator adds them on Users). Replies YES |
| Driver | Alert log: Kacheliba "Waiting for approval". **Approve & send** on Kacheliba only. Say: "A person approves every Warning." |
| Jury member | Phone buzzes with the Warning (English, or Swahili if the user language is sw). Reads it out |
| Jury member | Texts "how do I save my goats?" (advice from the approved list), then "3" (crowd report: 3 of 5 say bad), then "We need help" (goes to a person) |
15-second rule: no buzz 15 s after Approve, switch to Fallback A silently.

### 2:30-3:00 Today's forecast
Press `1`..`3`, layer both: 8 counties >= 57 % for Oct-Dec 2026 (Turkana, Wajir, Mandera, Garissa, Tana River, Marsabit, Isiolo, Samburu).
Say: "The short rains are starting. Eight pastoral counties are at high risk of Crisis. Forecasts to get ready, satellites to act, one SMS to the person who decides."
Never say "weeks early" about the SMS. If asked: "The forecast was early. The Warning confirms; it came with the declaration."

---

## Deep links (Tab 2)
```
http://localhost:8777/?country=Kenya&t=30                                     Jul 2021: 22 Watch, 5 Warning
http://localhost:8777/?country=Kenya&t=30&view=f2&layer=fews                  FEWS Phase 3+ in 13 counties
http://localhost:8777/?country=Kenya&t=30&view=f2&layer=both&county=Isiolo    Isiolo FEWS 3, our 87 %
http://localhost:8777/?country=Kenya&t=32                                     Sep 2021: 4 Warning
http://localhost:8777/?country=Kenya&t=56&county=Kacheliba                 Today: Kacheliba Warning, no grass
http://localhost:8777/?country=Kenya&t=92&view=f2&layer=both                  Today: 8 counties >= 57 %
```
Add `&api=http://localhost:8000` if the backend is on another host.

## Fallbacks
- **A. On-screen simulator** (`GATEWAY=sim`): add the herder on the Users tab, approve in the alert log. "Same code path, no radio."
- **B. Pre-seeded herder:** `python -m backend.seed_demo --iso3 KEN` creates "Demo Herder Kacheliba" (language sw). Re-point to a team phone in the local `.env` only.
- **C. Backend down:** the map works alone; play the video for the SMS loop.
- **D. Backup video** (Tab 3).

## T-30 checklist
```bash
cd /home/looooo/bcg/Hackathon-BCG && python3 -I - <<'EOF'
import json
s = open('data/risk/KEN.js').read(); k = 'RISK_DATA["KEN"] ='
j, _ = json.JSONDecoder().raw_decode(s[s.index(k) + len(k):].lstrip())
print(j['meta']['generated_at'], j['meta']['live_t'])
for t in (30, 32, 92):
    print(t, [sum(u['series'][t]['level'] >= i for u in j['units']) for i in (1, 2)])
print('t30 +2 >=0.57', sum((u['series'][30]['forecast']['2']['p_crisis'] or 0) >= 0.57 for u in j['units']))
print('t92 +1 >=0.57', sum((u['series'][92]['forecast']['1']['p_crisis'] or 0) >= 0.57 for u in j['units']))
EOF
```
Expected: `2026-10-17T01:30:10+00:00 92`, `30 [22, 5]`, `32 [26, 4]`, `92 [19, 2]` (Watch or above, Warning or above), `12`, `8`. If different, the file changed: update this page and slides 4-6.

- [ ] `scripts/start_demo.sh --fresh` (seeds Kenya users), then `python -m backend.seed_crowd --iso3 KEN` (Kacheliba, 4 reports, share 0.50).
- [ ] Backend dot green. Dry run: add a Kacheliba herder, approve at t=56, then `--fresh` again and re-seed.
- [ ] Real SMS: `GATEWAY=android`, phone charged, SIM credit. Else `GATEWAY=sim` and Fallback A.
- [ ] Chrome, one window, zoom 125 %, speed 1x. Nobody says a number not on this page or a slide.
