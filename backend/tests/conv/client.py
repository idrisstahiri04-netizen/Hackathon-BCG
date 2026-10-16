"""HTTP client for the conversation tests. Admin key is read from the team .env (never printed)."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from backend import composer, db, router  # db import loads .env (ADMIN_TOKEN, ANTHROPIC_API_KEY)

BASE = os.environ.get("CONV_API_BASE", "http://127.0.0.1:8501").rstrip("/")
OUT_DIR = os.path.join(os.path.dirname(__file__), "out")
CLARIFY = {composer.fit(router.R["en"]["clarify"]), composer.fit(router.R["fr"]["clarify"])}


def _key() -> str:
    tok = os.environ.get("ADMIN_TOKEN", "")
    if not tok:
        raise SystemExit("ADMIN_TOKEN not found in environment / .env")
    return tok


def call(method: str, path: str, body: dict | None = None, timeout: float = 60) -> tuple[int, dict | None, float]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"X-API-Key": _key(), "content-type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read().decode() or "null")
            return r.status, out, time.perf_counter() - t0
    except urllib.error.HTTPError as e:
        try:
            out = json.loads(e.read().decode() or "null")
        except ValueError:
            out = None
        return e.code, out, time.perf_counter() - t0


def send(phone: str, text: str) -> dict:
    """POST /sim/inbound -> {status, reply, intent, effective, parsed, latency_s, gsm7, len}."""
    status, out, dt = call("POST", "/sim/inbound", {"from": phone, "text": text})
    out = out or {}
    reply = out.get("reply")
    parsed = out.get("parsed") or {}
    intent = out.get("intent")
    effective = intent
    if parsed.get("clarify") or (reply in CLARIFY and intent not in ("unknown", None)):
        effective = "unknown"  # low confidence or value-less report -> user saw the clarify text
    return {
        "status": status, "reply": reply, "intent": intent, "effective": effective,
        "source": parsed.get("source"), "confidence": parsed.get("confidence"),
        "language": parsed.get("language"), "district": parsed.get("district"), "role": parsed.get("role"),
        "name": parsed.get("name"), "report_value": parsed.get("report_value"),
        "latency_s": round(dt, 3),
        "gsm7": composer.is_gsm7(reply) if reply else None,
        "len": composer.gsm_len(reply) if reply else 0,
        "raw": out,
    }


def messages_for(phone: str) -> list[dict]:
    from urllib.parse import quote
    _, out, _ = call("GET", f"/feed/messages?phone={quote(phone)}&limit=200")
    return (out or {}).get("messages", []) if isinstance(out, dict) else []


def health() -> dict | None:
    try:
        _, out, _ = call("GET", "/health")
        return out
    except Exception:
        return None


def pct(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    k = max(0, min(len(s) - 1, round((p / 100) * (len(s) - 1))))
    return s[k]
