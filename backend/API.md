# Backend API contract (SMS side)

FastAPI app `backend/app.py`, SQLite `backend/demo.db`. Runs on http://localhost:8000 (CORS open for the globe at :8777).

## Tables
- users(id, phone, name, district_id, district_name, iso3, role [farmer|herder|ngo|officer|resident], language, consent_at, opted_out_at, created_at, raw_signup_text)
- events(id, created_at, iso3, unit_id, unit_name, t, month_label, level, event, p, drivers_json, status [pending_approval|approved|sent|cancelled], approved_by)   ← the "broker"
- messages(id, created_at, direction [in|out], phone, user_id, event_id, text, intent, intent_confidence, parsed_json, status, gateway_id)
- help_requests(id, created_at, user_id, text, status)

## Endpoints
- POST /sms/inbound            gateway webhook (Android SMS Gateway format + simple {from, text}); runs the router
- POST /sim/inbound            same body {from, text} — on-screen phone simulator
- POST /alerts/run {iso3, t}   reads data/risk/<iso3>.js for month t, creates events for units whose level changed up to >=1 (Warning+ → pending_approval; Watch → approved, NGO/officer only)
- POST /events/{id}/approve    human approval → composer matches users and sends
- GET  /feed/alerts?since=id   latest events + "sent to N users"
- GET  /feed/users?since=id    latest users + counters by role
- GET  /feed/messages?since=id latest in/out messages with intent shown
- GET  /feed/crowd?iso3=ZWE[&t=63][&days=30]  crowd signal (spec `crowd_crop_status`): per unit n_reports, n_bad (2 or 3),
                               n_failed (3), share_bad, share_failed, last_report_at, n_users, n_demo. Last 30 days,
                               only users with consent and not opted out, one report per user per 7 days (anti-gaming).
                               Aggregated counts only (no phones/names) → no auth. With `t`: model_level, display_level,
                               crowd_confirmed, reason from backend/crowd.py apply_rule (see below)
- GET  /health

## Crowd rule (display level only — exported model levels are never changed)
A unit is shown +1 (max Warning, never Emergency; Normal→Watch, Watch→Warning) ONLY if `share_bad >= 0.6` with
`n_reports >= 3` AND the unit's exported row for that month has at least one satellite family in alarm
(vegetation, rain or soil; heat alone never counts). Otherwise reports are shown but change nothing.
Same rule in `js/live.js` (window.CROWD) for the globe badge (💬 n, colour by share_bad, ring + ✔ when
crowd-confirmed), the unit panel row "Crowd reports" and the Alert feed rows ("crowd report: Binga 3 of 4 say failed").
Demo helper: `python -m backend.seed_crowd` (4 demo-marked reports in Hurungwe, share_bad 0.50; one live "3" tips it).

## Router (Claude Haiku `claude-haiku-5-5`, key from /home/looooo/bcg/.env ANTHROPIC_API_KEY)
Intents are a registry list (name, description, examples, handler): subscribe, report (1/2/3), ask_advice, ask_help, stop, change_info, unknown. STOP/1/2/3/JOIN keyword fast-path without LLM. Low confidence → clarify question. District must match a known unit name (fuzzy, from data/geo/<iso3>.js); ambiguous → ask back. Confirm sign-up ("Reply YES"). Response text blocks only (Haiku may return thinking blocks first).
Advice answers ONLY from backend/advice.yaml (approved, short, per event+role); Claude (default claude-haiku-5-5 for speed, `ADVICE_MODEL=claude-sonnet-5-5` optional; only when local topic ranking is unclear) may only pick one entry, never invent. ask_help → help_requests row + "An officer will contact you".

## Gateway
`GATEWAY=android|sim|log` env. Android = capcom6 "SMS Gateway for Android" REST API (local or cloud mode; ANDROID_GW_URL, ANDROID_GW_USER, ANDROID_GW_PASS in .env). sim/log = no real SMS, stored in messages for the on-screen phone. Max 160 GSM-7 chars per SMS; per-user monthly cap.
