"""Thin Claude wrapper: one call -> strict JSON dict (structured outputs).

Reads ANTHROPIC_API_KEY from the environment (db.load_env loads /home/looooo/bcg/.env).
Only `text` blocks are read; thinking blocks (Haiku/Sonnet may emit them) are ignored.
Returns None on any API/parse failure so callers can fall back to keywords.
Tests monkeypatch `call_json`.
"""
from __future__ import annotations

import json
import logging
import os
import threading

from . import db  # noqa: F401  (ensures .env is loaded)

log = logging.getLogger("llm")

ROUTER_MODEL = os.environ.get("ROUTER_MODEL", "claude-haiku-5-5")
# Advice pick runs only when local ranking is not clear-cut; Haiku keeps it < 4 s end to end.
# Set ADVICE_MODEL=claude-sonnet-5-5 for the slower, stronger picker.
ADVICE_MODEL = os.environ.get("ADVICE_MODEL", "claude-haiku-5-5")
TIMEOUT_S = float(os.environ.get("LLM_TIMEOUT_S", "6"))

_client = None
_client_lock = threading.Lock()


def client():
    """Short timeouts: a black-holed network falls back to keywords in ~2x connect timeout."""
    global _client
    with _client_lock:
        if _client is None:
            import anthropic
            _client = anthropic.Anthropic(timeout=anthropic.Timeout(TIMEOUT_S, connect=2.0), max_retries=1)
        return _client


def warm_up() -> None:
    """Create the client and make one tiny call so the first real SMS is not cold (6-14 s)."""
    if not available() or os.environ.get("LLM_WARMUP", "1") == "0":
        return
    try:
        client().messages.create(model=ROUTER_MODEL, max_tokens=16, output_config={"effort": "low"},
                                 messages=[{"role": "user", "content": "ok"}])
        log.info("Claude client warmed up")
    except Exception as e:  # never break startup
        log.warning("Claude warm-up failed: %s", e)


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY")) and os.environ.get("LLM_DISABLED") != "1"


def _text(resp) -> str:
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")


def call_json(model: str, system: str, user: str, schema: dict, max_tokens: int = 1024) -> dict | None:
    if not available():
        return None
    try:
        resp = client().messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        )
    except Exception as e:  # network, auth, 4xx/5xx: never crash the SMS flow
        log.warning("Claude call failed (%s): %s", model, e)
        return None
    if resp.stop_reason == "refusal":
        log.warning("Claude refused (%s)", model)
        return None
    raw = _text(resp).strip()
    try:
        return json.loads(raw)
    except ValueError:
        s, e = raw.find("{"), raw.rfind("}")
        if s >= 0 and e > s:
            try:
                return json.loads(raw[s:e + 1])
            except ValueError:
                pass
        log.warning("Claude returned non-JSON: %r", raw[:200])
        return None
