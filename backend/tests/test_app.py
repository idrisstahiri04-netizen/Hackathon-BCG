import json

from fastapi.testclient import TestClient

from backend import app as appmod
from backend import db
from backend.tests.conftest import AUTH, make_risk, write_risk

client = TestClient(appmod.app, headers=AUTH)
anon = TestClient(appmod.app)


def test_health():
    assert client.get("/health").json()["ok"] is True


def test_stub_refused(isolated):
    write_risk(isolated, make_risk({"Binga": {60: (2, "crop_failure")}}, model_version="STUB"))
    r = client.post("/alerts/run", json={"iso3": "ZWE", "t": 60})
    assert r.status_code == 409 and "STUB" in r.json()["detail"]
    assert db.q1("SELECT COUNT(*) n FROM events")["n"] == 0


def test_placeholder_without_data_refused(isolated):
    (isolated / "ZWE.js").write_text('// placeholder: does not set RISK_DATA["ZWE"] yet\n')
    r = client.post("/alerts/run", json={"iso3": "ZWE", "t": 10})
    assert r.status_code == 409 and "no model output" in r.json()["detail"]


def test_run_approve_send(isolated):
    write_risk(isolated, make_risk({
        "Binga": {59: (1, "crop_failure"), 60: (2, "crop_failure"), 61: (2, "crop_failure")},
        "Hwange": {60: (1, "no_grass")},
    }))
    ids = {u["name"]: u["id"] for u in db.geo_units("ZWE")}
    for phone, role, d in [("+f", "farmer", "Binga"), ("+o", "officer", "Hwange"), ("+n", "ngo", "Binga")]:
        db.upsert_user(phone, role=role, iso3="ZWE", district_id=ids[d], district_name=d, consent_at=db.now_iso())

    r = client.post("/alerts/run", json={"iso3": "ZWE", "t": 60}).json()
    assert r["created"] == 2 and r["pending_approval"] == 1  # Binga Warning pending; Hwange Watch stored, never sent
    assert r["month"] == "Jan 2024"
    alerts = client.get("/feed/alerts").json()["events"]
    binga = next(a for a in alerts if a["unit_name"] == "Binga")
    hw = next(a for a in alerts if a["unit_name"] == "Hwange")
    assert binga["status"] == "pending_approval" and hw["sent_count"] == 0 and hw["level"] == 1
    assert db.q1("SELECT COUNT(*) n FROM messages WHERE phone='+f'")["n"] == 0  # not before approval

    s = client.post(f"/events/{binga['id']}/approve", json={"approved_by": "WHH desk"}).json()
    assert s["ok"] and s["sent"] == 2 and s["event"]["status"] == "sent" and s["event"]["sent_count"] == 2
    msgs = client.get("/feed/messages?phone=%2Bf").json()["messages"]
    assert msgs[0]["text"].startswith("WARNING Binga") and msgs[0]["chars"] <= 160

    # same month again: idempotent; next month same level: no new event (not an increase)
    assert client.post("/alerts/run", json={"iso3": "ZWE", "t": 60}).json()["created"] == 0
    assert client.post("/alerts/run", json={"iso3": "ZWE", "t": 61}).json()["created"] == 0


def test_android_webhook_inbound_and_status():
    body = {"deviceId": "d", "event": "sms:received", "id": "x", "webhookId": "w",
            "payload": {"messageId": "m1", "message": "JOIN", "sender": "+212600000099",
                        "recipient": None, "simNumber": 1, "receivedAt": "2026-10-16T10:00:00.000+01:00"}}
    r = client.post("/sms/inbound", json=body)
    assert r.json()["queued"] == 1
    out = db.q("SELECT * FROM messages WHERE phone='+212600000099' ORDER BY id")
    assert [m["direction"] for m in out] == ["in", "out"] and "local officer" in out[1]["text"].lower()
    db.ex("UPDATE messages SET gateway_id='g1' WHERE id=?", (out[1]["id"],))
    client.post("/sms/inbound", json={"event": "sms:delivered", "payload": {"messageId": "g1"}})
    assert db.q1("SELECT status FROM messages WHERE gateway_id='g1'")["status"] == "delivered"


def test_legacy_phoneNumber_field_and_simple_body():
    client.post("/sms/inbound", json={"event": "sms:received", "payload": {"message": "STOP", "phoneNumber": "+212600000001"}})
    assert db.q1("SELECT intent FROM messages WHERE phone='+212600000001' AND direction='in'")["intent"] == "stop"
    r = client.post("/sim/inbound", json={"from": "+212600000002", "text": "JOIN"}).json()
    assert r["ok"] and r["intent"] == "subscribe" and r["intent_confidence"] == 1.0 and r["reply"]
    r = client.post("/sms/inbound", json={"from": "+212600000003", "text": "2"}).json()
    assert r["intent"] == "report"


def test_signature_check(monkeypatch):
    import hashlib, hmac
    monkeypatch.setenv("ANDROID_GW_SIGNING_KEY", "k")
    import time
    raw = json.dumps({"event": "system:ping", "payload": {}}).encode()
    ts = str(int(time.time()))
    assert anon.post("/sms/inbound", content=raw, headers={"X-Timestamp": ts, "X-Signature": "bad"}).status_code == 401
    sig = hmac.new(b"k", raw + ts.encode(), hashlib.sha256).hexdigest()
    assert anon.post("/sms/inbound", content=raw, headers={"X-Timestamp": ts, "X-Signature": sig}).status_code == 200


def test_seed_idempotent():
    from backend import seed_demo
    seed_demo.seed(); seed_demo.seed()
    assert db.q1("SELECT COUNT(*) n FROM users")["n"] == len(seed_demo.SEED) + 1
    assert client.get("/feed/users").json()["counters"]["total"] == len(seed_demo.SEED) + 1


def test_android_gateway_payload(monkeypatch):
    from backend import gateway
    seen = {}

    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"id": "abc", "state": "Pending"}

    def post(url, json, auth, timeout, verify):
        seen.update(url=url, json=json, auth=auth)
        return Resp()
    monkeypatch.setattr(gateway.httpx, "post", post)
    monkeypatch.setenv("GATEWAY", "android")
    monkeypatch.setenv("ANDROID_GW_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("ANDROID_GW_USER", "sms"); monkeypatch.setenv("ANDROID_GW_PASS", "pw")
    assert gateway.send("+212600000001", "hi") == ("queued", "abc")
    assert seen["url"] == "http://127.0.0.1:8080/message"
    assert seen["json"] == {"phoneNumbers": ["+212600000001"], "textMessage": {"text": "hi"}}
    monkeypatch.setenv("ANDROID_GW_URL", "https://api.sms-gate.app/3rdparty/v1")
    gateway.send("+1", "hi")
    assert seen["url"] == "https://api.sms-gate.app/3rdparty/v1/messages"


def test_operator_endpoints_need_token():
    for path, body in [("/sim/inbound", {"from": "+212600000001", "text": "JOIN"}),
                       ("/alerts/run", {"iso3": "ZWE", "t": 1}), ("/events/1/approve", {}), ("/events/1/cancel", {})]:
        assert anon.post(path, json=body).status_code == 401, path
        assert anon.post(path, json=body, headers={"X-API-Key": "wrong"}).status_code == 401, path


def test_feeds_masked_without_token():
    db.upsert_user("+212600000001", name="Rudo", role="farmer", consent_at=db.now_iso())
    client.post("/sim/inbound", json={"from": "+212600000001", "text": "2"})
    u = anon.get("/feed/users").json()["users"][0]
    assert u["phone"] == "+212****001" and u["name"] is None
    assert all("+212600000001" not in json.dumps(m) for m in anon.get("/feed/messages").json()["messages"])
    assert client.get("/feed/users").json()["users"][0]["phone"] == "+212600000001"  # operator sees it


def test_inbound_rate_limit(monkeypatch):
    from backend import router
    monkeypatch.setattr(router, "PER_MIN", 3)
    replies = [client.post("/sim/inbound", json={"from": "+212600000005", "text": f"hello {i}"}).json()["reply"] for i in range(6)]
    assert sum(r is not None for r in replies) == 3
    assert client.post("/sim/inbound", json={"from": "+212600000005", "text": "STOP"}).json()["intent"] == "stop"


# ------------------------------------------------------------------ admin user management
def _binga():
    return next(u["id"] for u in db.geo_units("ZWE") if u["name"] == "Binga")


def test_users_crud_admin_only():
    body = {"phone": "+263771000111", "district_id": _binga(), "role": "farmer", "name": "Rudo", "language": "en"}
    anon = TestClient(appmod.app)
    assert anon.post("/users", json=body, headers={"X-API-Key": "x"}).status_code == 401
    assert anon.post("/users", json=body).status_code == 401
    r = client.post("/users", json=body, headers=AUTH)
    assert r.status_code == 201
    u = r.json()
    assert u["district_name"] == "Binga" and u["iso3"] == "ZWE" and u["consent_at"] and u["role"] == "farmer"
    assert client.post("/users", json=body, headers=AUTH).status_code == 409
    assert anon.patch(f"/users/{u['id']}", json={"role": "herder"}).status_code == 401
    p = client.patch(f"/users/{u['id']}", json={"role": "herder", "opted_out": True}, headers=AUTH).json()
    assert p["role"] == "herder" and p["opted_out_at"]
    assert client.patch(f"/users/{u['id']}", json={"opted_out": False}, headers=AUTH).json()["opted_out_at"] is None
    assert anon.delete(f"/users/{u['id']}").status_code == 401
    assert client.delete(f"/users/{u['id']}", headers=AUTH).json()["ok"]
    assert client.delete(f"/users/{u['id']}", headers=AUTH).status_code == 404
    assert db.get_user("+263771000111") is None


def test_users_validation():
    ok = {"phone": "+263771000112", "district_id": _binga(), "role": "farmer"}
    for bad in ({"phone": "0771000112"}, {"phone": "+12; DROP"}, {"district_id": "ZWE.NOPE"},
                {"role": "king"}, {"language": "xx"}):
        r = client.post("/users", json={**ok, **bad}, headers=AUTH)
        assert r.status_code == 422, (bad, r.text)
    assert client.patch("/users/999", json={"role": "ngo"}, headers=AUTH).status_code == 404
    assert client.patch("/users/999", json={"role": "king"}, headers=AUTH).status_code in (404, 422)
    assert db.q1("SELECT COUNT(*) n FROM users")["n"] == 0


def test_scheduler_stores_new_live_month_once_without_sending(isolated):
    risk = make_risk({"Binga": {59: (0, "none"), 60: (2, "crop_failure")}})
    risk["meta"]["live_t"] = 60
    write_risk(isolated, risk)
    db.upsert_user("+263771000200", role="farmer", district_id=_binga(), district_name="Binga",
                   iso3="ZWE", consent_at=db.now_iso())
    assert appmod.process_live_months() == [{"iso3": "ZWE", "t": 60, "created": 1}]
    assert appmod.process_live_months() == []  # idempotent
    ev = db.q("SELECT * FROM events")
    assert len(ev) == 1 and ev[0]["status"] == "pending_approval"
    assert db.q1("SELECT COUNT(*) n FROM messages WHERE direction='out'")["n"] == 0
    log = client.get("/alerts/log?iso3=ZWE").json()["events"]
    assert log[0]["send_status"] == "pending" and "phone" not in log[0]
