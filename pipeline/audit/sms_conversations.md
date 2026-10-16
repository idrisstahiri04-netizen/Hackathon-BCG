# SMS conversation audit (live Claude Haiku router)

Date: 2026-10-16. Backend: own instance on :8501, `DB_PATH=/tmp/conv_test/conv.db`, `GATEWAY=sim`,
`ROUTER_MODEL=ADVICE_MODEL=claude-haiku-5-5`, effort low, structured outputs. No backend source edited.
Harness: `backend/tests/conv/` (cases.py, run_suite.py, run_flow.py, run_load.py, cost_estimate.py,
test_conv_live.py). Raw results: `backend/tests/conv/out/{suite,flow,load,cost,repeat}.json`.

Re-run: start a disposable backend, then
`/home/looooo/bcg/.venv/bin/python -m pytest -c backend/pytest.ini backend/tests/conv -m live -s`
(or the `run_*` modules directly; `CONV_API_BASE` picks the backend, default http://127.0.0.1:8501).

## 1. Intent accuracy (75 inbound SMS, 55 reached Claude, 20 keyword/session fast-path)

| metric | value |
|---|---|
| accepted intent (primary or listed alternative) | **74 / 75 = 98.7 %** |
| strict (primary intent) | 70 / 75 = 93.3 % |
| reply-content checks (`reply_has`) | 75 / 75 |
| GSM-7 / <= 160 chars | all replies; longest 126 chars (alerts 133-136) |
| prompt-injection (3 cases) | all -> `unknown`, template reply only, no state change |
| stability (10 borderline cases x 3 repeats) | identical intent + confidence every run |

Coverage: English, French, Shona, Ndebele, Swahili/Shona-English mixes, typos, ALL CAPS, emojis,
"hi"/"?", 300-char rambling sign-up, digits only, unknown district (Timbuktu), fuzzy district (Bingaa),
ambiguous district (Gokwe -> numbered choice), role change, move, STOP/stop/Stop please/Quit/Unsubscribe/
ARRET, HELP variants, food aid, prices, weather, abuse, injection, sign-up YES and NO, 1/2/3 before and
after sign-up, duplicate report, free-text reports.

### Misses and weak spots (all deterministic)

| id | SMS | got | cause |
|---|---|---|---|
| sn_stop (**miss**) | "Mira kutumira" (Shona: stop sending) | unknown 0.4 | no Shona/Ndebele stop example or keyword; Ndebele "Yekela..." worked (0.92) |
| sub_123 | "123" | report, value **1**, conf 0.6-0.8 | digits-only text that is not 1/2/3 is read as a report; for a registered user a bogus "ok" report would be saved |
| adv_weather | "will it rain next week in Binga?" | ask_advice 0.6 -> planting advice | off-scope question; conf exactly 0.6 passes `< CONF_MIN` and an unrelated advice entry is sent |
| adv_drought_end | "is the drought going to end soon" | ask_advice 0.6 -> boil-water advice | same |
| adv_price2 | "how much is a 50kg bag of maize meal now" | ask_advice 0.6 -> grain-storage advice | same (prices are not in the advice library) |
| adv_price | "what is the price of maize in Harare" | unknown 0.6 -> clarify | OK but inconsistent with adv_price2 |
| sub_bare_district | "Binga" (no session) | unknown 0.4, district=Binga extracted | a bare district name from an unregistered number could start sign-up |
| rep_text_good | "crops are looking good this year" | report 1 (0.7) | fine, but a chatty remark becomes a crowd data point |
| sn_report | "Chibage changu chaoma chese" | report 3 (0.6), language=**bem** | right intent, Shona tagged as Bemba (language field unreliable for sn/nd) |
| rep_3_dup | second "3" within 7 days | same thank-you text | crowd dedups silently; user is not told the report was already counted |

Haiku outputs 0.6 for "unsure" very often; `CONF_MIN=0.6` with a strict `<` lets every one of them through.

## 2. Multi-turn flow (16/16 steps pass, `out/flow.json`)

Free-text sign-up as herder near Bulawayo -> "yes" -> `/alerts/run t=63` (Bulawayo Warning, no_grass,
pending approval) -> approve -> herder gets the 136-char GSM-7 Warning -> "What should I do with my
animals now?" -> livestock advice from advice.yaml -> help request logged -> STOP -> `/alerts/run t=64`
Emergency approved -> **no SMS to the opted-out number** -> "hello?" still gets the clarify reply ->
JOIN re-activates. Note: Binga never reaches level 3 in the real risk file, so it cannot be used for
the Emergency step (first draft of the flow failed on that fixture, not on the backend).

## 3. Latency and load

| scenario | p50 | p95 | max |
|---|---|---|---|
| suite, Claude-routed (n=55, serial) | 1.39 s | 3.22 s | 5.57 s |
| suite, keyword/session (n=20) | 9 ms | 15 ms | |
| load 20 numbers x 5 msgs concurrent (100 msgs in 8.6 s, 11.6 msg/s) all | 0.70 s | 4.17 s | 6.12 s |
| load, Claude-routed (n=40) | 1.92 s | 4.59 s | |
| load, keyword/session (n=60) | 0.43 s | 0.77 s | |

0 HTTP errors, 0 Claude timeouts/keyword fallbacks, 0 wrong intents under load. Keyword replies slow
from 9 ms to ~430 ms under 20-way concurrency (SQLite + threadpool), still fine. Max LLM latency 5.6-6.1 s
is right at `LLM_TIMEOUT_S=6`: expect occasional keyword fallbacks at busy times.

Rate limit (14-message burst from one number): messages 1-10 answered, 11-14 `rate_limited` (no Claude
call, no reply, ~30 ms). STOP sent while limited: processed and answered. Next message after STOP still
limited (window not reset) - correct.

## 4. Cost (Haiku 5.5: $0.10 / M input, $0.50 / M output)

Router call replayed with the production prompt + schema: ~1,200 input tokens (system prompt + JSON
schema ~1,150, SMS 10-120) and ~53 output tokens -> **$0.000146 per Claude call**. In the suite 73 % of
inbound reached Claude (the rest were STOP/JOIN/1-2-3/session steps).

| per 1,000 inbound SMS | USD |
|---|---|
| router only, 73 % reaching Claude | 0.11 |
| + advice picks (~10 % of inbound, ~600 in / 20 out) | 0.11-0.12 |
| worst case, every SMS to Claude | 0.15 |

No cache hits (`cache_read_input_tokens=0`); the prefix is below Haiku's minimum cacheable size and the
spend is negligible anyway. Cost is dominated by the SMS gateway, not Claude.

## 5. Concrete fixes (router prompt / examples), file:line in `backend/router.py`

1. **Shona/Ndebele STOP** - add keywords to `STOP_WORDS` (line 31): `"MIRA", "MIRA KUTUMIRA", "REGA", "YEKELA"`;
   and add examples to the `stop` intent (line 264): `"Mira kutumira"`, `"Yekela ukungithumela imilayezo"`,
   `"ndinoda kurega"`. Also add `"Hatina chikafu, tibatsireiwo"` / `"Asilakudla, sicela uncedo"` to
   `ask_help` (line 257) and `"Ndinoda kujoina, ndiri murimi kuMbire"` to `subscribe` (line 215) so the
   language mix is represented (today every example is en/fr).
2. **Digits-only text** - at line 539 (`if up in {"1","2","3"}`) add `elif up.isdigit(): parsed = unknown`
   (no Claude call), so "123", "0772123456" never become a report. Also tell the model in
   `_router_system()` (line 336): "report_value only when the SMS clearly states crop/pasture condition;
   a bare number other than 1/2/3 is unknown".
3. **Off-scope questions (weather, prices, forecasts)** - add to the `unknown` intent examples (line 299):
   `"will it rain next week?"`, `"what is the maize price?"`, `"when will the drought end?"` and extend
   its description with "questions we cannot answer: weather forecasts, market prices, dates". Pair this
   with a dedicated reply: reuse `no_advice` (line 68) for `ask_advice` when `rank_advice` top score is 0
   (`pick_advice`, line 410-417: today `top >= 3` only decides whether to ask Claude; a `top == 0` branch
   should return `no_advice` instead of the best-of-nothing entry).
4. **Confidence threshold** - Haiku emits 0.6 for "unsure"; change line 556 to `<= CONF_MIN` or set
   `ROUTER_CONF_MIN=0.65`. With fix 3 this routes the three unrelated-advice cases to clarify/no_advice.
5. **Bare district from an unregistered number** - after `classify()` (line 551): if `intent == "unknown"`,
   `parsed["district"]` matches the gazetteer (`match_district`) and `ctx.user is None`, treat as
   `subscribe` (asks role next). Cheap and makes "Binga" start a sign-up.
6. **Language field** - the `language` enum (line 314) misfires for Shona (`bem`, `other`). It is only used
   to pick en/fr replies, so either drop `sn/nd/ny/bem` from the enum or add "southern Africa: sn=Shona,
   nd=Ndebele" to the system prompt (line 337).
7. **Duplicate report UX** - `h_report` (line 247): if `crowd` reports the 7-day dedup, say "already
   counted this week" instead of the normal thank-you (needs a small return value from crowd).

Non-router notes: free-text reports ("crops are looking good") feed the crowd signal at conf 0.7; consider
requiring conf >= 0.8 for `report` from free text, or confirming ("Reply 1 to confirm 'ok'").
