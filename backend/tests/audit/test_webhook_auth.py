"""Audit 2 + 5 - webhook / endpoint authentication, spoofed senders, flooding.

All HTTP. GATEWAY=android with the real send function stubbed, so a test can prove
"this unauthenticated request would have sent a real SMS".
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from backend import app as appmod
from backend import db, gateway, llm
from backend.tests.conftest import AUTH, make_risk, write_risk

from ._helpers import ATTACKER, VICTIM, llm_result, register_victim

client = TestClient(appmod.app, headers=AUTH)   # operator (has ADMIN_TOKEN)
anon = TestClient(appmod.app)                   # anyone on the network


@pytest.fixture
def android_stub(monkeypatch):
    """GATEWAY=android, but _android_send only records what would have gone out."""
    sent: list[tuple[str, str]] = []
    monkeypatch.setenv("GATEWAY", "android")
    monkeypatch.setattr(gateway, "_android_send", lambda phone, text: (sent.append((phone, text)) or ("queued", "gw1")))
    return sent


def _sign(key: str, raw: bytes, ts: str) -> str:
    return hmac.new(key.encode(), raw + ts.encode(), hashlib.sha256).hexdigest()


# ------------------------------------------------------------- W1: /sim/inbound is an open SMS cannon
def test_sim_inbound_with_token_sends(android_stub):
    """Fixed W1: only the operator (X-API-Key) can drive the simulator."""
    r = client.post("/sim/inbound", json={"from": "+263779999999", "text": "JOIN"})
    assert r.status_code == 200
    assert android_stub == [("+263779999999", r.json()["reply"])]


def test_sim_inbound_requires_token(android_stub):
    r = anon.post("/sim/inbound", json={"from": "+263779999999", "text": "JOIN"})
    assert r.status_code in (401, 403)
    assert android_stub == []


def test_spoofed_stop_over_http_rejected(android_stub):
    register_victim()
    r = anon.post("/sim/inbound", json={"from": VICTIM, "text": "STOP"})
    assert r.status_code in (401, 403)
    assert db.get_user(VICTIM)["opted_out_at"] is None


def test_spoofed_stop_with_wrong_token_rejected(android_stub):
    register_victim()
    r = anon.post("/sim/inbound", json={"from": VICTIM, "text": "STOP"}, headers={"X-API-Key": "guess"})
    assert r.status_code == 401 and db.get_user(VICTIM)["opted_out_at"] is None


# ------------------------------------------------------------- W2: approve / run / cancel have no auth
def _pending_event(isolated) -> int:
    write_risk(isolated, make_risk({"Binga": {60: (2, "crop_failure")}}))
    r = client.post("/alerts/run", json={"iso3": "ZWE", "t": 60}).json()
    assert r["pending_approval"] == 1
    return r["event_ids"][0]


def test_approve_unauthenticated_sends_alerts_today(isolated, android_stub):
    register_victim()
    eid = _pending_event(isolated)
    r = client.post(f"/events/{eid}/approve", json={"approved_by": "anyone on the internet"})
    assert r.status_code == 200 and r.json()["sent"] == 1
    assert android_stub and android_stub[0][0] == VICTIM
    assert db.q1("SELECT approved_by FROM events WHERE id=?", (eid,))["approved_by"] == "anyone on the internet"


def test_approve_requires_token(isolated, android_stub):
    register_victim()
    eid = _pending_event(isolated)
    r = anon.post(f"/events/{eid}/approve", json={"approved_by": "x"})
    assert r.status_code in (401, 403)
    assert android_stub == []


def test_alerts_run_requires_token(isolated):
    write_risk(isolated, make_risk({"Binga": {60: (1, "crop_failure")}}))
    r = anon.post("/alerts/run", json={"iso3": "ZWE", "t": 60})
    assert r.status_code in (401, 403)


def test_cancel_requires_token(isolated):
    eid = _pending_event(isolated)
    r = anon.post(f"/events/{eid}/cancel", json={})
    assert r.status_code in (401, 403)


def test_approve_twice_does_not_double_send(isolated, android_stub):
    register_victim()
    eid = _pending_event(isolated)
    client.post(f"/events/{eid}/approve", json={})
    client.post(f"/events/{eid}/approve", json={})
    assert len(android_stub) == 1
    assert db.q1("SELECT COUNT(*) n FROM messages WHERE direction='out' AND event_id=?", (eid,))["n"] == 1


# ------------------------------------------------------------- W3: HMAC on /sms/inbound
def test_hmac_rejects_unsigned_when_key_set(monkeypatch):
    monkeypatch.setenv("ANDROID_GW_SIGNING_KEY", "k")
    body = {"event": "sms:received", "payload": {"sender": ATTACKER, "message": "JOIN"}}
    assert anon.post("/sms/inbound", json=body).status_code == 401
    raw = json.dumps(body).encode()
    r = anon.post("/sms/inbound", content=raw, headers={"X-Timestamp": "1", "X-Signature": _sign("wrong", raw, "1"),
                                                            "content-type": "application/json"})
    assert r.status_code == 401


def test_hmac_accepts_valid_signature(monkeypatch):
    monkeypatch.setenv("ANDROID_GW_SIGNING_KEY", "k")
    body = {"event": "sms:received", "payload": {"sender": ATTACKER, "message": "JOIN"}}
    raw = json.dumps(body).encode()
    ts = str(int(time.time()))
    r = anon.post("/sms/inbound", content=raw, headers={"X-Timestamp": ts, "X-Signature": _sign("k", raw, ts),
                                                            "content-type": "application/json"})
    assert r.status_code == 200 and r.json()["queued"] == 1


def test_hmac_covers_plain_from_text_body_too(monkeypatch, android_stub):
    """A {from,text} body on /sms/inbound is also behind the signature when a key is set."""
    monkeypatch.setenv("ANDROID_GW_SIGNING_KEY", "k")
    r = anon.post("/sms/inbound", json={"from": ATTACKER, "text": "JOIN"})
    assert r.status_code == 401 and android_stub == []


def test_hmac_rejects_stale_timestamp(monkeypatch):
    monkeypatch.setenv("ANDROID_GW_SIGNING_KEY", "k")
    body = {"event": "sms:received", "payload": {"sender": ATTACKER, "message": "JOIN"}}
    raw = json.dumps(body).encode()
    ts = str(int(time.time()) - 86400)
    r = anon.post("/sms/inbound", content=raw, headers={"X-Timestamp": ts, "X-Signature": _sign("k", raw, ts),
                                                            "content-type": "application/json"})
    assert r.status_code == 401


def test_android_mode_without_signing_key_fails_closed(monkeypatch, android_stub):
    monkeypatch.delenv("ANDROID_GW_SIGNING_KEY", raising=False)
    body = {"event": "sms:received", "payload": {"sender": ATTACKER, "message": "JOIN"}}
    r = anon.post("/sms/inbound", json=body)
    assert r.status_code == 401


# ------------------------------------------------------------- A1: flooding / cost
def test_inbound_flood_is_rate_limited(android_stub, fake_llm):
    fake_llm.set(lambda *a: llm_result(intent="unknown", confidence=0.9))
    for i in range(40):
        client.post("/sim/inbound", json={"from": ATTACKER, "text": f"hello {i}"})
    assert len(android_stub) <= 10, f"{len(android_stub)} replies sent to one number in a burst"


def test_inbound_flood_stops_llm_calls_too(android_stub, fake_llm):
    """Fixed A1: over the per-number limit there is no Claude call and no reply."""
    fake_llm.set(lambda *a: llm_result(intent="unknown", confidence=0.9))
    for i in range(20):
        client.post("/sim/inbound", json={"from": ATTACKER, "text": f"hello {i}"})
    assert len(android_stub) == 10 and len(fake_llm.calls) == 10


def test_monthly_alert_cap_enforced(isolated, android_stub, monkeypatch):
    monkeypatch.setenv("MONTHLY_CAP", "2")
    u = register_victim()
    write_risk(isolated, make_risk({"Binga": {60: (2, "crop_failure"), 61: (3, "crop_failure"), 62: (1, "none"), 63: (2, "none")}}))
    for t in (60, 61, 63):
        r = client.post("/alerts/run", json={"iso3": "ZWE", "t": t}).json()
        for eid in r["event_ids"]:
            client.post(f"/events/{eid}/approve", json={})
    assert len([p for p, _ in android_stub if p == VICTIM]) == 2


def test_garbage_phone_rejected(android_stub):
    r = client.post("/sim/inbound", json={"from": "not a phone; DROP", "text": "JOIN"})
    assert r.status_code == 422
    assert android_stub == []


def test_cors_is_wildcard_today():
    r = client.options("/events/1/approve", headers={"Origin": "https://evil.example",
                                                      "Access-Control-Request-Method": "POST"})
    assert r.headers.get("access-control-allow-origin") == "*"
