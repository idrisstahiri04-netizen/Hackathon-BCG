"""Token usage / cost per 1,000 inbound SMS.

The backend's llm.call_json does not return usage, so we replay the router's exact prompt
(router._router_system() + schema, same model/effort) on a few SMS and read response.usage.
Prices: claude-haiku-5-5 $0.10 / M input, $0.50 / M output (claude-api skill table, 2026-10).
"""
from __future__ import annotations

import json
import os
import sys

import anthropic

from backend import llm, router
from . import client

IN_PRICE, OUT_PRICE = 0.10 / 1e6, 0.50 / 1e6
SAMPLES = [
    "hi",
    "I want drought alerts for Binga, I am a farmer",
    "Ndinoda kujoina. Ndiri murimi kuMbire",
    "what should i plant now that the rains are late?",
    ("Good morning sir/madam, I hope this message finds you well. My name is Mrs Moyo from Tsholotsho, we have had "
     "very little rain since December and the maize is wilting, I heard on the radio there is a service that sends "
     "warnings by SMS and I would like to be included in that, I have 4 hectares and also some goats."),
]


def run(share_llm: float | None = None) -> dict:
    if not llm.available():
        sys.exit("no ANTHROPIC_API_KEY")
    c = anthropic.Anthropic(max_retries=1)
    rows = []
    for s in SAMPLES:
        resp = c.messages.create(model=llm.ROUTER_MODEL, max_tokens=1024, system=router._router_system(),
                                 messages=[{"role": "user", "content": f"<sms>{s[:640]}</sms>"}],
                                 output_config={"effort": "low", "format": {"type": "json_schema",
                                                                            "schema": router._router_schema()}})
        u = resp.usage
        rows.append({"sms": s[:40], "input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                     "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
                     "cost_usd": u.input_tokens * IN_PRICE + u.output_tokens * OUT_PRICE})
    avg_in = sum(r["input_tokens"] for r in rows) / len(rows)
    avg_out = sum(r["output_tokens"] for r in rows) / len(rows)
    per_call = avg_in * IN_PRICE + avg_out * OUT_PRICE
    # share of inbound that reaches Claude: measured by the suite if available, else 0.7
    if share_llm is None:
        try:
            with open(os.path.join(client.OUT_DIR, "suite.json")) as f:
                s = json.load(f)["summary"]
            share_llm = s["llm_calls"] / s["n"]
        except (OSError, KeyError, ZeroDivisionError):
            share_llm = 0.7
    advice_share = 0.10  # ask_advice with unclear local ranking -> a second Haiku pick (~600 in / 20 out)
    advice_call = 600 * IN_PRICE + 20 * OUT_PRICE
    est = {"model": llm.ROUTER_MODEL, "avg_input_tokens": round(avg_in), "avg_output_tokens": round(avg_out),
           "usd_per_router_call": round(per_call, 6), "share_inbound_reaching_claude": round(share_llm, 2),
           "usd_per_1000_inbound_router_only": round(1000 * share_llm * per_call, 3),
           "usd_per_1000_inbound_with_advice_picks": round(1000 * (share_llm * per_call + advice_share * advice_call), 3),
           "usd_per_1000_inbound_worst_case_all_llm": round(1000 * (per_call + advice_share * advice_call), 3),
           "samples": rows}
    print(json.dumps(est, indent=1))
    os.makedirs(client.OUT_DIR, exist_ok=True)
    with open(os.path.join(client.OUT_DIR, "cost.json"), "w") as f:
        json.dump(est, f, indent=1)
    return est


if __name__ == "__main__":
    run()
