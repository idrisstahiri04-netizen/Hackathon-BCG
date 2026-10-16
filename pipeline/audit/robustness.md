# Demo robustness audit (2026-10-16, branch `zimbabwe-real-data`)

Scope: globe (static :8777) + FastAPI SMS backend (:8000) + Claude router + Android gateway.
Harness: `scripts/robustness_tests.py` (each test boots its own uvicorn on a spare port with a temp
SQLite db and an un-stubbed copy of `data/risk`, so the running demo is never touched).
Raw numbers: `pipeline/audit/out/robustness_results.json`. Browser checks done with Playwright
against `index.html` on :8777 (`?api=` pointed at a test backend); screenshots in `pipeline/audit/out/ui_*.png`.
Code tested: `backend/*` as of 16:34, `js/live.js` as of 16:24, real model output in `data/risk/*.js` (16:28).

Run everything again with
`../.venv/bin/python scripts/robustness_tests.py` (about 5 min, ~70 Claude Haiku calls).

## 1. Start / stop

| Script | What it does | Checked |
|---|---|---|
| `scripts/start_demo.sh` | venv + modules, `ANTHROPIC_API_KEY` present (length only, never printed), ports, risk file not STUB; starts uvicorn :8000 and `http.server` :8777 (pid files in `scripts/.run/`); waits for `/health`; **warms up the Claude client**; seeds users via `backend/seed_demo.py`; prints URLs. `--fresh` wipes `backend/demo.db`, `--no-seed`, `--check`. | Run twice on spare ports: second run adopts the running processes, re-seed is a no-op (keyed on phone). |
| `scripts/stop_demo.sh` | Kills pid-file processes, then anything of ours still on the ports (`backend.app` / `http.server` only); `--fresh` deletes the db. | Run twice: second run is a clean no-op, ports free. |

Note: `scripts/.run/site.pid` got committed by someone's `git add -A`; add `scripts/.run/` to `.gitignore`.

## 2. Failure-mode results

| # | Scenario | Result | Evidence |
|---|---|---|---|
| 1 | Claude API down: invalid key | **PASS** | 9/9 SMS answered HTTP 200, `parsed.source=keywords`, process alive. 401 costs 0.2-0.4 s per SMS. |
| 2 | Claude API down: connection refused | **PASS** | 4/4 answered, keyword fallback, < 0.5 s per SMS after warm-up. |
| 3 | Claude API down: host black-holed (captive portal / dropped packets) | **PASS (app) / FAIL (stage)** | Reply still comes, but after **48 s** (20 s timeout x 2 attempts) and the event loop is blocked meanwhile (see #9). UI gives up at 4 s. |
| 4 | Android gateway unreachable (`GATEWAY=android`, dead URL) | **PASS (backend) / FAIL (UI)** | Approve returns 200 in 0.2 s; 3/3 outbound rows `status=failed:ConnectError`; `/sim/inbound` keeps working. But the event is set to `sent` and the feed says "sent to 3 users"; the phone thread shows no status. Nothing on screen says the SMS failed. |
| 5 | Backend down, globe offline | **PASS** | All assets served from :8777, no CDN URL in `index.html`; `#be-status` flips to "backend offline", the three live pages show the offline banner, "Run alerts" hides, globe + deep link `?country=Zimbabwe&t=63&county=Binga` render normally (screenshot `ui_globe_backend_down.png`). Only console noise is `ERR_CONNECTION_REFUSED` on `/health`. |
| 6 | Double approve click | **PASS** | UI: button disabled synchronously on first click (3 JS clicks -> one request, "sent to 1 user"). API: 4 concurrent + 1 late `POST /events/{id}/approve` -> 5 recipients, 0 duplicates (3 runs). Guard is `composer.recipients` `already_sent` check per user; not transactional, so a true race is still possible but was not reproduced. |
| 7 | 50 inbound SMS burst (real Haiku) | **PASS (no crash) / FAIL (latency)** | 50/50 HTTP 200, process alive, `/health` 57 ms afterwards. But requests are **serialised**: wall 75.7 s, p50 46.7 s, p95 73.7 s, max 75.1 s. Cause: #9. |
| 8 | Browser reload mid-demo | **PASS** | No client-side state that is not re-fetched; phone thread, counters, feed and `?page=` / `?country&t&county` come back after reload. Backend restart on the same db keeps users/messages/events (2 msgs, 6 events before = after). |
| 9 | `/health` while a Claude call is in flight | **FAIL** | `/health` stalled 1 042 ms during a 1.26 s SMS -> the event loop is blocked by the sync Claude SDK call inside `async def sim_inbound`. With one slow call (10 s advice, 48 s black-hole) the UI health poll (2 s interval, 4 s timeout) shows **"backend offline"** and disables the Run button mid-demo. |

## 3. Latency: inbound SMS -> reply ready (real Claude Haiku router, sequential)

| Path | p50 | p95 | max | n |
|---|---|---|---|---|
| Free text, **warm** client | **1.4 s** | 9.9 s (advice) | 11.4 s | 14 |
| Free text, excluding `ask_advice` | 1.4 s | 1.9 s | 1.9 s | 10 |
| First SMS after backend start (cold `anthropic.Anthropic()`) | 12.3 s | - | - | 1 (also 12.1 s, 14.0 s, 6.0 s, 9.9 s in other runs) |
| `ask_advice` ("what should I plant?") = Haiku classify + Sonnet pick | 10-11 s in server (4.2 s measured in isolation) | | | 3 |
| Keyword fast-path (`JOIN`, `2`, `STOP`, `HELP`, session replies) | 39 ms | 121 ms | | 5 |
| Burst of 50 concurrent | 46.7 s | 73.7 s | 75.1 s | 50 |

UI budget is **4 s** (`js/live.js:39`). Warm sign-up / report / help fit; the first SMS of the day and every
advice question do not (the reply still shows up through polling 2 s later, but a red "Send failed" toast appears).
`start_demo.sh` now sends one warm-up SMS so the cold 6-14 s is paid before the audience is watching.

## 4. Must-fix list (ordered by stage impact)

1. **Event loop blocked by Claude calls** - `backend/app.py:95` (`async def sim_inbound`) and `:70/:91`
   (`sms_inbound` non-webhook path) call the synchronous `router.handle_inbound` directly. Make them plain
   `def` (FastAPI runs them in the threadpool) or `await run_in_threadpool(...)`. Fixes #7 and #9: burst becomes
   parallel and `/health` keeps answering, so the UI never says "offline" while Claude is thinking.
2. **Network timeouts too long** - `backend/llm.py:28` `anthropic.Anthropic(timeout=20.0, max_retries=1)`.
   Use `timeout=httpx.Timeout(6.0, connect=2.0), max_retries=0` so a black-holed network falls back to
   keywords in <= 6 s instead of 48 s.
3. **Cold start 6-14 s on first SMS** - `backend/llm.py:24-29` builds the client lazily. Build it at import
   (or in a FastAPI startup hook) and fire one tiny warm-up call. The start script covers this for now.
4. **Advice path exceeds 4 s every time** - `backend/router.py:397` second LLM call (Sonnet, `max_tokens=1024`)
   after the Haiku classify. Use Haiku for the pick (`ADVICE_MODEL`, `backend/llm.py:19`), `max_tokens<=64`,
   or skip the LLM when the candidate list is <= 3. The Phone tab quick button "What should I plant?" hits this.
5. **Failed gateway sends invisible** - `backend/composer.py:186` marks the event `sent` regardless of per-user
   status; `backend/app.py:178-183` counts all `out` rows as `sent_to`. Count only rows whose status is not
   `failed%`, and in `js/live.js:378` append `m.status` to the phone bubble meta when it starts with `failed`.
   With the real Android phone this is the only way to see on stage that nothing went out.
6. **UI timeout vs. approve-with-Android** - `js/live.js:39` 4 s abort; `backend/gateway.py` sends sequentially
   with a 15 s timeout per SMS. Approving an event with N real recipients can take N x 15 s on a bad link ->
   "Approve failed" toast while sends continue. Raise the abort for `/events/*/approve` and `/sim/inbound`
   to ~30 s, or send in a background task and poll.
7. **`JOIN <district> <role>` is not a keyword fast-path** - `backend/router.py:476` matches only the bare
   word (`up in JOIN_WORDS`). The Phone tab quick button "JOIN Mbire farmer" therefore goes through Claude
   (1.5 s, or 6-14 s cold). Treat a leading JOIN/START/REGISTER word as `subscribe` with the rest parsed
   locally (`parse_role` + `match_district`), Claude only for the remainder.
8. **Approve race (theoretical)** - `backend/composer.py:139-186` SELECT-then-INSERT per user without a
   transaction; two simultaneous approvals could double-send. Not reproduced in 3 runs; wrap `send_event` in
   a `BEGIN IMMEDIATE` or add `UNIQUE(user_id, event_id)` on `messages` for `direction='out'`.
9. Housekeeping: `scripts/.run/` into `.gitignore`; `start_demo.sh` leaves a `+000000000000` warm-up row in
   the message feed (filter it in the Users tab or use `--fresh` right before going on stage and accept it).

## 5. If X breaks on stage, do Y

1. **"backend offline" dot turns red** -> `scripts/start_demo.sh` (idempotent; restarts only what died). Globe keeps working meanwhile, so stay on the Map tab.
2. **Phone tab shows "Send failed"** but you only sent one SMS -> it is the 4 s UI timeout, not a failure; wait 2 s, the reply appears in the thread. Avoid "What should I plant?" and send a short free text instead.
3. **First SMS of the demo hangs** -> cold Claude client; always run `start_demo.sh` (it warms up) at least 1 min before, or text `JOIN` first (keyword path, 40 ms).
4. **Venue Wi-Fi dies / Claude unreachable** -> nothing to do: router answers from keywords in <1 s (bad key / refused) but up to 48 s if packets are silently dropped; switch the laptop to phone hotspot, or `export LLM_DISABLED=1` and restart to force instant keyword mode.
5. **Real Android phone gets nothing** -> check the alert row still says "sent to N users" (it will, even on failure); fall back: Phone tab (`GATEWAY=sim`) runs the same router. `python backend/check_gateway.py +2126...` tells you if the gateway is reachable.
6. **Approve button stuck on "Sending..."** -> the send is still running (sequential gateway sends); do not click again (no duplicates are created anyway); reload the page, the row will show `Sent`.
7. **Slider/timeline misbehaves or the page is in a weird state** -> reload with a deep link: `?country=Zimbabwe&t=63&county=Binga` (Apr 2024 declaration month). All SMS state is in SQLite, nothing is lost on reload.
8. **"Run alerts for this month" greyed out** -> backend offline (see 1) or country not LIVE (risk file is STUB). It returns "No district changed level" for months with no escalation; use t=59 (Dec 2023) or t=63.
9. **Port 8000/8777 already in use** -> `scripts/stop_demo.sh` then `start_demo.sh`; the scripts only kill `backend.app` / `http.server` processes, anything else is reported with its pid.
10. **Need a clean slate 2 min before** -> `scripts/stop_demo.sh --fresh && scripts/start_demo.sh` (wipes db, re-seeds 9 demo users, warms Claude; ~20 s).
