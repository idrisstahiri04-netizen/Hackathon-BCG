# How our models work — and how FEWS NET fits in

Date: 2026-10-16 · Branch: `zimbabwe-real-data`
Simple-English overview for the team and the jury. Numbers come from `pipeline/out/model_report.md`, `pipeline/ipc_model/report.md`, `pipeline/outlooks/report.md` and `docs/metrics_report.md`.

---

## The big picture

```
                 EARLY (months ahead)                          LATE but PRECISE (weeks ahead)
 FEWS NET outlooks + El Niño + seasonal forecasts      Satellite + weather per district
                    │                                               │
          Model B: "Chance of Crisis"                    Model A: "Bad season" probability
          (IPC model, NGO only)                          + Alert rules (spec family rule)
                    │                                               │
                    └───────────────► ALERT LEVEL per district ◄────┘
                                      (Normal / Watch / Warning / Emergency)
                                                  │
                                    Crowd replies (1/2/3) can confirm, never trigger
                                                  │
                                       SMS to the right people
```

**Rule of thumb:** FEWS NET and forecasts give *early* signals for NGOs. Satellite evidence decides *Warnings* for farmers and herders. Our system turns both into one SMS per person, per district, every month.

---

## 1. FEWS NET — what it is and what we take from it

**Who:** Famine Early Warning Systems Network (USAID-funded expert analysts).

**What it publishes:**

| Product | How often | What it says |
|---|---|---|
| Food Security Outlook | 3 times a year (≈ Feb, Jun, Oct) | Projected food-security phase for the next ~8 months: near term (ML1, ~4 months) and medium term (ML2, next ~4 months) |
| Outlook Update / Key Messages | Monthly in between | Adjusts the projections |
| IPC-compatible maps | ~3 per year | Current situation (CS): which areas are in Phase 1–5 now |

**How we use it (2 ways):**

1. **As the "answer" (ground truth):** the IPC phase maps tell us which districts *really* fell into crisis (Phase 3+). We use them to train Model B and to check all our alerts.
2. **As an input (early signal):** Claude (Sonnet) read 370 FEWS NET reports and extracted each forecast with an exact quote (71/71 quotes verified word-for-word, cost ≈ $3).

**What we learned:**

| FEWS NET signal | Zimbabwe 2023/24 | Usable? |
|---|---|---|
| "Below-normal rainfall expected" | from **July 2023** | ✅ yes — 0 false alarms in normal years 2020–2023 |
| "Crisis projected" | 20 districts in **Oct 2023** | ⚠️ appears every year (chronic crisis areas) → not an alarm by itself |
| Post-harvest Crisis | March 2024 | ✅ reliable, but late → confirmation only |

**Limits:** talks about areas (livelihood zones, provinces), not districts; full outlook only 3×/year; paused ~6 months in 2025; not every country (Zambia only until 2017). It is expert judgement, not an SMS alert system.

**Spec rule:** text/official sources alone can raise a district to **Watch at most**, never Warning.

---

## 2. Model A — "Bad season" model (satellite + weather) — *our own*

**Question it answers:** *"Will plants in this district be very weak in the coming 1–3 months?"*
Two events: **crop_failure** (cropland) and **no_grass** (grazing land, for herders). Label = 2 of 3 core months with VCI < 35 (satellite-measured plant condition).

**Inputs (per district, per month, using only data available at the time — 1-month delay built in):**

| Family | Data | Source |
|---|---|---|
| Rain | SPI 1/3/6 months | CHIRPS v3 |
| Vegetation | NDVI score + VCI, cropland and grassland separately | MODIS + ESA WorldCover |
| Soil | soil moisture, 2 layers | ERA5-Land |
| Heat | temperature anomaly | ERA5-Land |
| Context | lags 1–3 months, trends, month of year, season phase, crop/grass share | derived |

**How it learns:** supervised classification on 2001–2022 history (4 countries pooled, 80,648 examples). Compares 5 approaches and keeps the best on honest tests:
persistence ("nothing changes"), fixed rules, logistic regression, LightGBM (small boosted trees), ensemble (average). Probabilities are calibrated (isotonic) so "70%" means ~70%.

**Honest testing:** leave-one-year-out (22 folds); 2023/24 kept hidden and tested once.

**How good:** small but real gain over baselines (CV PR-AUC 0.338 vs persistence 0.267 with the stricter labels). Best for herders (no_grass) 1 month ahead. Weak for crop failure.

**Where it is used:** the "chance" number for NGOs in the panel. **It does not set the colour by itself** (see section 4).

---

## 3. Model B — "Chance of Crisis" model (IPC model) — *our own, built on FEWS NET*

**Question it answers:** *"Will this district enter food crisis (IPC Phase 3+) in the next 1–3 months?"* — the outcome that really matters.

**Inputs:** Model A's satellite + weather features **plus** NMME seasonal rain forecasts, the El Niño index (ONI), FEWS NET outlooks/projections (only those published before the issue month).

**Training:** on Kaggle (≈ 3 min). Leave-one-season-out 2016–2022, 2023/24 hidden.

**How good (districts not yet in crisis — the hard, important case):**

| Model | CV ROC / PR-AUC | Hidden 2023/24 ROC / PR-AUC |
|---|---|---|
| Persistence | 0.71 / 0.26 | 0.53 / 0.39 |
| Satellite + forecasts + El Niño | 0.74 / 0.35 | 0.73 / 0.58 |
| **+ FEWS NET outlooks** | **0.87 / 0.60** | **0.94 / 0.92** |

**Zimbabwe 2023/24 replay:** flagged all 57 districts that later entered crisis; 34 before the 3 April 2024 declaration; first signals Nov–Dec 2023.

**Honest note:** most of its power comes from FEWS NET's own projections. Our added value is a calibrated, monthly, per-district probability that keeps working between FEWS NET releases.

**Where it is used:** "chance of Crisis within 3 months" in the NGO panel and NGO SMS, and an **NGO-only early Watch** (only for districts not already in crisis). Never a farmer Warning.

---

## 4. Alert engine — how the colour is decided (spec rules)

| Level | Rule |
|---|---|
| 🟢 Normal | nothing in alarm |
| 🟡 Watch | any one family in alarm (rain, vegetation, soil), or strong rain + soil dryness, or (NGO only) Model B chance ≥ threshold |
| 🟠 Warning | **vegetation + (rain or soil)** in alarm — two independent families, plants required |
| 🔴 Emergency | Warning **and** an official declaration in force |

- Heat only supports, never triggers.
- A level must hold **2 months to go up** and **3 months to go down** (rows kept only by this rule are marked **held**).
- No probability gate on Warning (the methodology audit showed it switched alerts off).

**Zimbabwe 2023/24 (v1.1):** Warning in 7/91 districts before the declaration (≈5 weeks); Watch in 53/91 (≈9 weeks). Against FEWS NET crisis maps: precision 0.78, recall 0.61 (baseline 0.43 / 0.35). Zero Warnings in the wet 2020/21 season.

---

## 5. Supporting / tested models

| Model | Role | Result |
|---|---|---|
| **TimesFM** (Google, zero-shot forecaster) | forecast plant condition 1–3 months ahead | lowest error but misses droughts; made Model A worse as a feature → **dropped** |
| **NMME seasonal forecasts** | rain outlook months ahead | saw the Feb–Apr 2024 dryness from Oct–Nov 2023 (~2–3 extra months); Sep 2023 said "not dry" |
| **El Niño (ONI)** | climate driver | El Niño seasons: 73% of ZWE districts in crop failure vs 31% in La Niña; small accuracy gain |
| **Claude Haiku (SMS router)** | understands incoming SMS (sign-up, advice, help, report, STOP) | 6/6 live test intents correct; ~1.5 s replies |
| **Claude (advice picker)** | chooses an answer **only** from the approved advice list | never invents advice |

---

## 6. Who does what — one table

| | FEWS NET | Model A (ours) | Model B (ours) | Alert engine (ours) |
|---|---|---|---|---|
| Looks ahead | ~8 months | 1–3 months | 1–3 months | — |
| Detail | areas | **district** | **district** | **district** |
| Updates | 3×/yr + monthly notes | **monthly** | **monthly** | **monthly** |
| Main input | expert analysis | satellite + weather | satellite + forecasts + FEWS NET | Model A families (+ B for NGO Watch) |
| Output | phase maps, reports | "bad season" chance | "crisis" chance | colour + who gets which SMS |
| Reaches farmers? | no | via engine | no (NGO only) | **yes, by SMS** |

---

## 7. In progress (may change the numbers)

- Food prices (WFP / FEWS NET) as a new family — catches price-driven crises.
- Model B trained on more countries + proper map overlap of FEWS NET areas.
- Dry-spell features from 5-day rain (longest dry spell, late onset).
- Live crowd signal: farmers' "3 = failed" replies can confirm (never trigger) a level.
