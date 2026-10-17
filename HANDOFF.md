# HANDOFF — read this first (state as of 2026-10-17)

Drought early-warning demo for the BCG Platinion / Welthungerhilfe hackathon (case: livestock-dependent communities, northern Zimbabwe). Satellite + weather + forecasts + FEWS NET → district risk levels and 1–8-month forecasts on a 3D globe → one-segment SMS per person, two-way via Claude.

Branch: **`zimbabwe-real-data`** (pushed to `idrisstahiri04-netizen/Hackathon-BCG`). Never commit to `main`. Commit messages must **not** contain any Claude co-author line.

## 1. Run the demo
```bash
cd Hackathon-BCG
scripts/start_demo.sh --fresh          # backend :8000 + static site :8777 + demo users
python backend/seed_crowd.py            # crowd-signal demo (Hurungwe); --clear to remove
# open http://localhost:8777   (deep link: ?country=Zimbabwe&t=63)
scripts/stop_demo.sh
```
Python venv expected at `../.venv` (repo parent). Install: `pip install -r pipeline/requirements.txt -r backend/requirements.txt`.
Demo script: `docs/demo_script.md` · Pitch: `docs/pitch.md` · Jury Q&A: `docs/redteam.md`.

## 2. Secrets needed on the new machine (never commit, never paste in chat)
File `../.env` (repo parent, gitignored):
- `ANTHROPIC_API_KEY=` — **current key is INVALID (401). Put a new one.** Router = `claude-haiku-5-5`, advice picker = Haiku.
- `ADMIN_TOKEN=` — any random string; then `python backend/make_ui_config.py` writes `js/config.local.js` (gitignored).
- `GATEWAY=sim` (default) or `android` + `ANDROID_GW_URL/USER/PASS`, `ANDROID_GW_SIGNING_KEY` (capcom6 "SMS Gateway for Android"; test with `python backend/check_gateway.py <number>`). Morocco has no Twilio two-way SMS → Android phone + Moroccan SIM.
- Kaggle (all training runs there, not on the laptop): token in `~/.kaggle/access_token`, `export KAGGLE_API_TOKEN=$(cat ~/.kaggle/access_token)`. Private datasets `omarserghini/drought-signals`, `drought-code`. Runner: `scripts/kaggle/run.sh "<cmd>" [--gpu]` (see `scripts/kaggle/README.md`).
- Earth Engine: GCP project `drought-warning-zw-1016`; run `earthengine authenticate`.

## 3. What exists (key files)
| Area | Files |
|---|---|
| Data contract (source of truth) | `pipeline/CONTRACT.md` (signals, geo, risk JSON, forecast leads 1–8, `held`, `urban`, `watch_reason`, `p_crisis`) |
| Signals 2001→2026 (14 countries) | `pipeline/extract_signals.py`, `pipeline/data/signals_<ISO3>.parquet` (+ dryspell, seasonal_fc, prices, ipc, outlook) ; live extension `pipeline/live/` |
| Models | Model A "bad season" `pipeline/train.py` (ensemble logreg+LightGBM, v2: NMME + ONI + 14-country pool + dry spells, leads 1–6) ; Model B "chance of Crisis" `pipeline/ipc_model/` (IPC3+, FEWS-proxy fallback when FEWS NET missing) |
| Alert engine (FROZEN) | `pipeline/alert_engine.py`, `pipeline/export_risk.py` → `data/risk/<ISO3>.js` |
| Frontend | `index.html`, `js/app.js`, `js/real.js`, `js/live.js`, `css/` ; geo `data/geo/<ISO3>.js` |
| SMS backend | `backend/` (FastAPI, SQLite, Claude router with intent registry, composer, gateway, crowd signal, advice.yaml) ; API `backend/API.md` |
| Docs | `docs/models_explained.md`, `docs/metrics_report.md`, `docs/experts/*.md`, `pipeline/audit/*.md` |

## 4. Alert logic (frozen, spec "Ready / Set / Go")
- Watch (Ready): any one family (rain, vegetation, soil) **or** climate readiness (ONI≥1 or ONI≥0.5 & NMME dry, NGO only) **or** p_crisis≥0.57 where known IPC<3, Oct–Apr only. `watch_reason` says which.
- Warning (Set/Go): vegetation + (rain or soil). Hysteresis 2 up / 3 down (`held`), no fast entry.
- Emergency: Warning + official declaration in force (capped to that season).
- Urban units: visible but no farmer/herder SMS. Data latency: month t uses t−1 data.

## 5. Honest results (cite only these)
- Model A v2: CV mean PR-AUC 0.39 (persistence 0.27); hold-out ROC ≈ 0.76.
- Model B (with FEWS NET): hold-out 2023/24 transition ROC/PR 0.94/0.92; without FEWS → proxy ≈ 0.89.
- ZWE vs FEWS NET IPC3+ 2023/24: Warning precision 0.78 / recall 0.61 (persistence 0.43/0.35); 0 Warnings in wet 2020/21.
- Oct 2023 forecast: FEWS Phase 3 for Feb–May 2024; 40 districts ≥57%. Feb 2024 +2: 33 districts. Declaration 2024-04-03.
- Limits: Malawi = monitoring only (price-led crisis); Zambia no p_crisis (no IPC after 2017); +7/+8 = FEWS only; live 2026 forecast uses the FEWS-proxy (no FEWS outlook in 2026).

## 6. Test commands
`pytest backend -q` (5 live tests need a valid Claude key) · `pytest pipeline/tests -q` · `python scripts/robustness_tests.py` · Node Playwright e2e in `tests/e2e/` (`demo_flow.js`, `forecast_view.js`, `final_ui.js`, `sms_audit.js`; `npm i` in tests/e2e, channel chrome).

## 7. Open items / next steps
1. **New Claude API key** in `../.env`, then re-run the 5 live backend tests.
2. Switch to the Android gateway when the phone server is ready (`GATEWAY=android`, run `check_gateway.py`, register webhook via ngrok/Azure).
3. Optional: open a PR `zimbabwe-real-data` → `main`; record a backup demo video.
4. Minor UI: district panel slightly overlaps the bottom of the legend at 1440 px.
5. Ideas not done (from `docs/experts/`): 10-day dry-spell alerts (≈6 weeks earlier), SPEI and FLDAS soil moisture; phone-number encryption before any pilot.

## 8. Working rules for the next agent
- Simple English, short replies; user is token-limited → cheap models, few agents.
- Model per task: haiku (mechanical), sonnet (research/routine code/tests), opus (model design/pitch).
- Real data only on screen — never simulated numbers. Keep the forecast visible (user's top priority).
- Don't change frozen alert rules without the user's OK; never tune on the 2023/24 hold-out.
