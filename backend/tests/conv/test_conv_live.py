"""Live conversation suite as pytest (real Claude via a RUNNING backend; skips if none at CONV_API_BASE).

  DB_PATH=/tmp/conv_test/conv.db GATEWAY=sim uvicorn backend.app:app --port 8501 &
  /home/looooo/bcg/.venv/bin/python -m pytest -c backend/pytest.ini backend/tests/conv -m live -s
Each run uses fresh numbers (random CONV_SALT), so it is repeatable on the same DB.
"""
from __future__ import annotations

import pytest

from . import client, run_flow, run_load, run_suite

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def backend():
    h = client.health()
    if not h:
        pytest.skip(f"no backend at {client.BASE}")
    if not h.get("llm"):
        pytest.skip("backend has no Claude key (router would be keyword-only)")
    return h


def test_intent_accuracy(backend):
    s = run_suite.run(verbose=True)
    assert s["gsm7_all"], "a reply used non-GSM-7 characters"
    assert not s["over_160"], f"replies over 160 chars: {s['over_160']}"
    assert s["accuracy_ok"] >= 0.90, f"intent accuracy {s['accuracy_ok']:.0%} < 90%: {[m['id'] for m in s['misses']]}"


def test_multi_turn_flow(backend):
    res = run_flow.run()
    failed = [s["step"] for s in res["steps"] if not s["ok"]]
    assert not failed, failed


def test_load_and_rate_limit(backend):
    res = run_load.run()
    assert res["load"]["http_errors"] == 0
    assert res["rate_limit"]["stop_under_limit_ok"], "STOP must work while rate-limited"
    assert res["rate_limit"]["limited_from"] == 11, "11th message in a minute should be rate-limited"
