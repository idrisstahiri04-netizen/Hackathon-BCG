"""Multi-turn flow: sign-up -> confirm -> alert (alerts/run + approve) -> advice -> help -> STOP -> silence.

Uses the real ZWE risk file: Bulawayo rises to Warning (level 2, no_grass) at t=63 (Apr 2024) and to
Emergency (level 3) at t=64. A herder in Bulawayo gets the Warning; after STOP the Emergency must NOT reach them.
(Binga only reaches level 2 in the real data, so it cannot be used for the Emergency step.)
Idempotent on a reused DB: events already created by an earlier run are looked up in /feed/alerts.
"""
from __future__ import annotations

import json
import os
import random
import sys

from . import client

STEPS = []


def step(name, ok, detail=""):
    STEPS.append({"step": name, "ok": bool(ok), "detail": detail})
    print(f"{'OK ' if ok else 'FAIL'} {name:28} {detail}")


DISTRICT = "Bulawayo"


def alerts_for(phone: str) -> list[dict]:
    return [m for m in client.messages_for(phone) if m["direction"] == "out" and m.get("event_id")]


def event_for(t: int, level: int) -> dict | None:
    """Run the broker for month t, then find this district's event (new or from an earlier run)."""
    st, out, dt = client.call("POST", "/alerts/run", {"iso3": "ZWE", "t": t})
    step(f"alerts/run t={t}", st == 200, f"http={st} created={(out or {}).get('created')} {dt:.2f}s")
    _, feed, _ = client.call("GET", "/feed/alerts?limit=500")
    evs = feed if isinstance(feed, list) else (feed or {}).get("events", (feed or {}).get("alerts", []))
    hits = [e for e in evs if e.get("unit_name") == DISTRICT and e.get("t") == t and int(e.get("level") or 0) == level]
    step(f"{DISTRICT} level-{level} event at t={t}", bool(hits),
         json.dumps({k: hits[0].get(k) for k in ("id", "level", "event", "status")}) if hits else "none")
    return hits[0] if hits else None


def approve(ev: dict) -> None:
    st, out, dt = client.call("POST", f"/events/{ev['id']}/approve", {"approved_by": "conv test"})
    step(f"approve event {ev['id']}", st == 200, f"http={st} {out.get('sent_to_label') if out else ''} {dt:.2f}s")


def run() -> dict:
    salt = os.environ.get("CONV_SALT") or f"{random.randint(0, 99):02d}"
    phone = f"+26378{salt}00001"
    # 1. sign-up (Claude reads free text), 2. confirm
    r = client.send(phone, f"Hello, I keep goats and cattle near {DISTRICT} and want the drought warnings")
    step("signup free text", r["effective"] == "subscribe" and DISTRICT.lower() in (r["reply"] or "").lower()
         and "herder" in (r["reply"] or "").lower(), f"{r['latency_s']}s {r['reply']!r}")
    r = client.send(phone, "yes")
    step("confirm YES", "registered" in (r["reply"] or "").lower(), r["reply"])
    # 3. alert: Warning at t=63 needs human approval, then reaches the herder (no_grass -> herder audience)
    ev = event_for(63, 2)
    if ev:
        approve(ev)
    al = alerts_for(phone)
    step("herder received alert", len(al) == 1, f"n={len(al)} " + (repr(al[0]['text']) if al else ""))
    if al:
        step("alert one segment GSM-7", al[0]["gsm7"] and al[0]["chars"] <= 160, f"chars={al[0]['chars']} gsm7={al[0]['gsm7']}")
    # 4. advice after the alert
    r = client.send(phone, "What should I do with my animals now?")
    step("advice", r["effective"] == "ask_advice", f"{r['latency_s']}s {r['reply']!r}")
    # 5. help request
    r = client.send(phone, "Our cattle are dying and we have nothing to feed the children, we need help")
    step("help request", r["effective"] == "ask_help", f"{r['latency_s']}s {r['reply']!r}")
    # 6. STOP
    r = client.send(phone, "STOP")
    step("STOP", r["intent"] == "stop" and "no more" in (r["reply"] or "").lower(), r["reply"])
    # 7. Emergency at t=64 (everyone in the district) must not reach the opted-out user
    n_before = len(alerts_for(phone))
    ev3 = event_for(64, 3)
    if ev3:
        approve(ev3)
    step("no alert after STOP", len(alerts_for(phone)) == n_before, f"alerts before={n_before} after={len(alerts_for(phone))}")
    # 8. inbound after STOP still gets a (non-alert) reply; JOIN re-activates
    r = client.send(phone, "hello?")
    step("inbound after STOP answered", r["reply"] is not None, repr(r["reply"]))
    r = client.send(phone, "JOIN")
    step("JOIN after STOP", r["intent"] == "subscribe", repr(r["reply"]))
    res = {"phone": phone, "steps": STEPS, "ok": all(s["ok"] for s in STEPS)}
    os.makedirs(client.OUT_DIR, exist_ok=True)
    with open(os.path.join(client.OUT_DIR, "flow.json"), "w") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    print("FLOW", "PASS" if res["ok"] else "FAIL", f"{sum(s['ok'] for s in STEPS)}/{len(STEPS)}")
    return res


if __name__ == "__main__":
    if not client.health():
        sys.exit(f"backend not reachable at {client.BASE}")
    run()
