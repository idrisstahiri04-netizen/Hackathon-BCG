# SMS backend (two-way SMS, alert broker)

Spec: `backend/API.md`. Response shapes match `tests/mock_backend.py` (what `js/live.js` reads).

```
backend/app.py          FastAPI endpoints
backend/db.py           SQLite schema + helpers, .env loading, data/geo + data/risk readers
backend/router.py       intent registry, keyword fast-path, Claude Haiku classification, sign-up flow
backend/composer.py     event -> users (audience rules, opt-out, monthly cap) + one-segment GSM-7 templates
backend/gateway.py      GATEWAY=android|sim|log
backend/llm.py          Claude wrapper (strict JSON via structured outputs; reads text blocks only)
backend/advice.yaml     approved advice library (DEMO CONTENT, to be validated by WHH/extension)
backend/seed_demo.py    fake demo subscribers (+2126000000xx) in northern Zimbabwe
backend/check_gateway.py  test the Android gateway connection / send one test SMS / register webhooks
```

## Run

```bash
cd /home/looooo/bcg/Hackathon-BCG
/home/looooo/bcg/.venv/bin/pip install -r backend/requirements.txt
/home/looooo/bcg/.venv/bin/python -m backend.seed_demo          # optional, idempotent
/home/looooo/bcg/.venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

Globe: `python3 -m http.server 8777`, then open `http://localhost:8777/?api=http://localhost:8000`.

Quick check:
```bash
curl localhost:8000/health
curl -XPOST localhost:8000/sim/inbound -H 'content-type: application/json' -d '{"from":"+212600000050","text":"JOIN"}'
curl -XPOST localhost:8000/alerts/run  -H 'content-type: application/json' -d '{"iso3":"ZWE","t":63}'
curl -XPOST localhost:8000/events/1/approve -H 'content-type: application/json' -d '{"approved_by":"WHH desk"}'
```

`/alerts/run` refuses (HTTP 409) when `data/risk/<ISO3>.js` is a STUB or has no model output. No fake data.
Watch (level 1) events are auto-approved and sent to NGO/officer only. Warning/Emergency wait for
`/events/{id}/approve` (human in the loop). `/events/{id}/cancel` drops one.

## Environment (`/home/looooo/bcg/.env`, never commit it)

| Var | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | - | Claude key. Without it the router falls back to keywords |
| `GATEWAY` | `sim` | `sim` (on-screen phone), `log` (log only), `android` (real SMS) |
| `ANDROID_GW_URL` | - | local: `http://<phone-ip>:8080` / cloud: `https://api.sms-gate.app/3rdparty/v1` |
| `ANDROID_GW_USER`, `ANDROID_GW_PASS` | - | Basic auth from the app's Home tab (local and cloud credentials differ) |
| `ANDROID_GW_SIGNING_KEY` | - | optional: verify webhook HMAC (`X-Signature`), app Settings > Webhooks > Signing Key |
| `ANDROID_GW_VERIFY_TLS` | `1` | set `0` only for self-signed local certs |
| `ROUTER_MODEL` / `ADVICE_MODEL` | `claude-haiku-5-5` / `claude-sonnet-5-5` | |
| `ROUTER_CONF_MIN` | `0.6` | below this the router asks a clarifying question |
| `MONTHLY_CAP` | `6` | max alert SMS per user per calendar month |
| `DB_PATH` | `backend/demo.db` | SQLite file (gitignored). Delete it to reset the demo |
| `COUNTRIES` | `ZWE,MWI,ZMB` | gazetteers used for district matching |

Load order: real environment, then `Hackathon-BCG/.env`, then `/home/looooo/bcg/.env` (no override).

## Switch sim -> Android phone (config only, no code change)

The app is capcom6 "SMS Gateway for Android" (github.com/capcom6/android-sms-gateway, docs.sms-gate.app).

1. Install the app on the Android phone (APK from the GitHub releases page), insert the SIM, grant SMS permissions.
   Turn off battery optimisation for the app, keep the phone charging.
2. Pick a mode in the app:
   - **Local server** (phone and laptop on the same Wi-Fi/hotspot; no internet needed for sending):
     enable "Local Server", note the IP, port (8080), username and password on the Home tab.
     `ANDROID_GW_URL=http://<phone-ip>:8080`
   - **Cloud server** (phone only needs mobile data; laptop anywhere): enable "Cloud Server",
     note the cloud username/password. `ANDROID_GW_URL=https://api.sms-gate.app/3rdparty/v1`
3. Edit `/home/looooo/bcg/.env`:
   ```
   GATEWAY=android
   ANDROID_GW_URL=...
   ANDROID_GW_USER=...
   ANDROID_GW_PASS=...
   ```
4. Test: `python backend/check_gateway.py` (auth + device status), then
   `python backend/check_gateway.py +2126XXXXXXXX` sends one test SMS through the same code path.
5. Inbound SMS: the phone (local mode) or the cloud (cloud mode) POSTs a webhook to our
   `POST /sms/inbound`. Webhooks need **HTTPS** (only `http://127.0.0.1` is allowed in clear text). Options:
   - **ngrok / Cloudflare tunnel** (easiest at the venue): `ngrok http 8000` -> `https://<id>.ngrok-free.app`
   - **Azure** (our subscription): deploy the app (App Service / Container Apps) -> `https://<app>.azurewebsites.net`
   - **USB, no internet, local mode only**: `adb reverse tcp:8000 tcp:8000`, webhook URL `http://127.0.0.1:8000/sms/inbound`
   Register it (sms:received + sent/delivered/failed for delivery status):
   ```bash
   python backend/check_gateway.py --register-webhook https://<public-host>/sms/inbound
   python backend/check_gateway.py --list-webhooks
   ```
   Local and cloud keep separate webhook lists; register in the mode you use. The phone shows a
   notification when an `sms:received` webhook is added. Payload handled: `{"event":"sms:received",
   "payload":{"message","sender" (older apps: "phoneNumber"), ...}}`; we reply in a background task
   so the gateway gets its 2xx within 30 s.
6. Restart uvicorn. `GET /health` shows `"gateway": "android"`.

Back to sim: set `GATEWAY=sim` and restart. The on-screen phone (`POST /sim/inbound`, `GET
/feed/messages?phone=...`) works in every mode.

## Router behaviour

- `STOP` (also ARRET, UNSUBSCRIBE) always wins, no LLM. `1/2/3` = crop report, `JOIN`, `HELP`/`AIDE`: keywords.
- Everything else: Claude Haiku picks one intent from the registry (`subscribe, report, ask_advice,
  ask_help, stop, change_info, unknown`) and extracts district/role/name/language as strict JSON.
- District accepted only after a fuzzy gazetteer match on `data/geo/<ISO3>.js`; ambiguous ("Gokwe")
  -> numbered choice; unknown -> ask again. Sign-up needs `YES`/`OUI` (consent recorded).
- `ask_advice`: Claude Sonnet may only pick an entry id from `advice.yaml` for the user's role and current event.
- English and French replies; Shona/Ndebele are understood by Claude but replies are English (needs native review).

## Tests

```bash
/home/looooo/bcg/.venv/bin/python -m pytest -c backend/pytest.ini backend/tests -m "not live" -q   # mocked Claude
/home/looooo/bcg/.venv/bin/python -m pytest -c backend/pytest.ini backend/tests -m live -s          # 1 real Haiku call set
```
