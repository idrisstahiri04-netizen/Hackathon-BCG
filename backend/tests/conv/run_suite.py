"""Run the realistic conversation suite (real Claude calls) and write out/suite.json + out/suite.md."""
from __future__ import annotations

import json
import os
import random
import sys
import time

from . import client
from .cases import C

SETUP = {
    "farmer_hwange": [("JOIN Hwange farmer", None), ("YES", "registered")],
    "herder_binga": [("JOIN Binga herder", None), ("YES", "registered")],
    "signup_district": [("JOIN", "which district")],
}


def phone_for(slot: str, salt: str, table: dict) -> str:
    if slot not in table:
        table[slot] = f"+26377{salt}{len(table) + 1:05d}"
    return table[slot]


def run(verbose: bool = True) -> dict:
    salt = os.environ.get("CONV_SALT") or f"{random.randint(0, 99):02d}"
    phones: dict[str, str] = {}
    results = []
    for c in C:
        slot_new = c["phone"] not in phones
        phone = phone_for(c["phone"], salt, phones)
        setup_ok = True
        if c["setup"] and slot_new:  # fresh slot -> build state with keyword-only steps
            for text, need in SETUP[c["setup"]]:
                r = client.send(phone, text)
                if need and need not in (r["reply"] or "").lower():
                    setup_ok = False
        r = client.send(phone, c["text"])
        got = r["effective"]
        strict = got == c["expect"][0]
        ok = got in c["expect"]
        reply_ok = True if not c["reply_has"] else c["reply_has"] in (r["reply"] or "").lower()
        row = {**{k: c[k] for k in ("id", "group", "text", "expect", "setup", "note", "reply_has")},
               "phone": phone, "setup_ok": setup_ok, "got": got, "raw_intent": r["intent"], "source": r["source"],
               "confidence": r["confidence"], "language": r["language"], "district": r["district"],
               "role": r["role"], "report_value": r["report_value"], "reply": r["reply"], "gsm7": r["gsm7"],
               "len": r["len"], "latency_s": r["latency_s"], "http": r["status"],
               "strict": strict, "ok": ok, "reply_ok": reply_ok}
        results.append(row)
        if verbose:
            flag = "OK " if ok and reply_ok else "MISS"
            print(f"{flag} {c['id']:18} want={'/'.join(c['expect']):22} got={got:12} src={r['source'] or '-':8} "
                  f"conf={r['confidence']} {r['latency_s']:.2f}s len={r['len']} gsm7={r['gsm7']} | {c['text'][:50]!r}")
            if not reply_ok:
                print(f"      reply missing {c['reply_has']!r}: {r['reply']!r}")
    llm_lat = [x["latency_s"] for x in results if x["source"] == "llm"]
    kw_lat = [x["latency_s"] for x in results if x["source"] != "llm"]
    summary = {
        "n": len(results), "ok": sum(x["ok"] for x in results), "strict": sum(x["strict"] for x in results),
        "reply_ok": sum(x["reply_ok"] for x in results),
        "accuracy_ok": round(sum(x["ok"] for x in results) / len(results), 3),
        "accuracy_strict": round(sum(x["strict"] for x in results) / len(results), 3),
        "gsm7_all": all(x["gsm7"] for x in results if x["reply"]),
        "max_len": max(x["len"] for x in results), "over_160": [x["id"] for x in results if x["len"] > 160],
        "llm_calls": len(llm_lat),
        "latency_llm_p50": client.pct(llm_lat, 50), "latency_llm_p95": client.pct(llm_lat, 95),
        "latency_llm_max": max(llm_lat, default=0),
        "latency_kw_p50": client.pct(kw_lat, 50), "latency_kw_p95": client.pct(kw_lat, 95),
        "misses": [{k: x[k] for k in ("id", "group", "text", "expect", "got", "raw_intent", "confidence", "source",
                                       "reply", "reply_ok")} for x in results if not (x["ok"] and x["reply_ok"])],
        "salt": salt, "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    os.makedirs(client.OUT_DIR, exist_ok=True)
    with open(os.path.join(client.OUT_DIR, "suite.json"), "w") as f:
        json.dump({"summary": summary, "results": results}, f, indent=1, ensure_ascii=False)
    if verbose:
        print(json.dumps({k: v for k, v in summary.items() if k != "misses"}, indent=1))
        print(f"MISSES ({len(summary['misses'])}):")
        for m in summary["misses"]:
            print(f"  {m['id']:18} want={'/'.join(m['expect'])} got={m['got']} (raw {m['raw_intent']} "
                  f"conf={m['confidence']} src={m['source']}) reply_ok={m['reply_ok']} | {m['text'][:70]!r}")
    return summary


if __name__ == "__main__":
    if not client.health():
        sys.exit(f"backend not reachable at {client.BASE}")
    run()
