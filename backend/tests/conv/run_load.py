"""Load: 20 numbers x 5 messages concurrently (one worker per number, messages in order).
Then the per-number rate limit (10/min): burst 14 messages, check which get no reply, and that STOP still works.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from . import client

# mix: 3 keyword fast-path (no Claude) + 2 Claude-routed per number
SCRIPT = [
    "JOIN Binga farmer",                                   # keyword
    "YES",                                                 # session
    "what should I plant now, the rains are late?",        # Claude -> advice
    "2",                                                   # keyword report
    "we have no food left please help us",                 # Claude -> help
]


def worker(phone: str) -> list[dict]:
    out = []
    for text in SCRIPT:
        try:
            r = client.send(phone, text)
            out.append({"phone": phone, "text": text, "http": r["status"], "intent": r["intent"],
                        "source": r["source"], "latency_s": r["latency_s"], "reply": r["reply"]})
        except Exception as e:  # network-level failure
            out.append({"phone": phone, "text": text, "http": 0, "error": str(e)[:200], "latency_s": None})
    return out


def run(n_numbers: int = 20) -> dict:
    salt = os.environ.get("CONV_SALT") or f"{random.randint(0, 99):02d}"
    phones = [f"+26379{salt}{i:05d}" for i in range(1, n_numbers + 1)]
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=n_numbers) as ex:
        rows = [r for rs in ex.map(worker, phones) for r in rs]
    wall = time.perf_counter() - t0
    lat = [r["latency_s"] for r in rows if r["latency_s"] is not None]
    llm = [r["latency_s"] for r in rows if r.get("source") == "llm"]
    kw = [r["latency_s"] for r in rows if r.get("source") in ("keyword", "session")]
    errors = [r for r in rows if r["http"] != 200]
    fell_back = [r for r in rows if r.get("source") == "keywords"]  # Claude timed out -> keyword fallback
    unexpected = [r for r in rows if r["http"] == 200 and r["text"] == SCRIPT[2] and r["intent"] != "ask_advice"]
    unexpected += [r for r in rows if r["http"] == 200 and r["text"] == SCRIPT[4] and r["intent"] != "ask_help"]
    load = {"numbers": n_numbers, "messages": len(rows), "wall_s": round(wall, 2),
            "throughput_msg_s": round(len(rows) / wall, 2),
            "p50_s": client.pct(lat, 50), "p95_s": client.pct(lat, 95), "max_s": max(lat, default=0),
            "llm_p50_s": client.pct(llm, 50), "llm_p95_s": client.pct(llm, 95), "llm_n": len(llm),
            "kw_p50_s": client.pct(kw, 50), "kw_p95_s": client.pct(kw, 95),
            "http_errors": len(errors), "claude_fallbacks": len(fell_back), "wrong_intents": len(unexpected),
            "wrong_intent_rows": [{k: r[k] for k in ("text", "intent", "source", "confidence") if k in r} for r in unexpected]}
    print(json.dumps(load, indent=1))

    # ---- rate limit: 14 fast messages from one number, then STOP
    p = f"+26379{salt}99999"
    burst = []
    for i in range(14):
        r = client.send(p, "hi" if i % 2 else "1")  # alternate keyword and Claude-routed
        burst.append({"i": i + 1, "intent": r["intent"], "reply": r["reply"], "latency_s": r["latency_s"]})
    limited = [b["i"] for b in burst if b["intent"] == "rate_limited"]
    r = client.send(p, "STOP")
    stop_ok = r["intent"] == "stop" and r["reply"] is not None
    r2 = client.send(p, "hello again")
    rate = {"burst": 14, "limited_from": limited[0] if limited else None, "limited_n": len(limited),
            "replies_before_limit": sum(1 for b in burst if b["reply"]),
            "stop_under_limit_ok": stop_ok, "stop_reply": r["reply"],
            "after_stop_still_limited": r2["intent"] == "rate_limited",
            "limited_latency_p50": client.pct([b["latency_s"] for b in burst if b["intent"] == "rate_limited"], 50)}
    print(json.dumps(rate, indent=1))
    res = {"load": load, "rate_limit": rate, "rows": rows, "burst": burst}
    os.makedirs(client.OUT_DIR, exist_ok=True)
    with open(os.path.join(client.OUT_DIR, "load.json"), "w") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    return res


if __name__ == "__main__":
    if not client.health():
        sys.exit(f"backend not reachable at {client.BASE}")
    run()
