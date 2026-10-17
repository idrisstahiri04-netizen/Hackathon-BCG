import re

import pytest

from backend import composer, db

LONG = "Uzumba Maramba Pfungwe"


def ev(level, event, name=LONG):
    return {"unit_name": name, "level": level, "event": event, "p": 0.68, "horizon": 8, "agreeing": 2,
            "confidence": "medium", "drivers": ["3-month rain index -1.4 (very dry)"]}


def test_watch_not_sent():
    _user("+n1", "ngo", "Binga")
    _user("+o1", "officer", "Binga")
    r = composer.send_event(_event(1, "no_grass"))
    assert r["sent"] == 0 and r["audiences"] == []
    assert not db.q("SELECT 1 FROM messages WHERE direction='out'")


def test_sms_uses_top_recommendation():
    from backend import recommend
    e = ev(3, "no_grass", "Binga")
    e["recommendations"] = recommend.recommend({"level": 3, "event": "no_grass", "drivers": []})
    for lang in ("en", "sw"):
        t = composer.compose("herder", e, lang)
        assert composer.is_gsm7(t) and composer.gsm_len(t) <= 160, t
    assert "breeding" in composer.compose("herder", e, "en") or "water" in composer.compose("herder", e, "en")


def test_audiences():
    assert composer.audiences(0, "crop_failure") == []
    assert composer.audiences(1, "crop_failure") == []  # Watch is never sent
    assert composer.audiences(1, "no_grass") == []
    assert composer.audiences(2, "crop_failure") == ["ngo", "officer", "farmer"]
    assert composer.audiences(2, "cant_plant") == ["ngo", "officer", "farmer"]
    assert composer.audiences(2, "no_grass") == ["ngo", "officer", "herder"]
    everyone = ["ngo", "officer", "farmer", "herder", "resident"]
    assert composer.audiences(3, "no_grass") == everyone
    assert composer.audiences(3, "crop_failure") == everyone


@pytest.mark.parametrize("role", ["farmer", "herder", "resident", "ngo", "officer"])
@pytest.mark.parametrize("level", [1, 2, 3])
@pytest.mark.parametrize("event", ["cant_plant", "crop_failure", "no_grass", "none"])
@pytest.mark.parametrize("lang", ["en", "fr"])
def test_one_segment_gsm7(role, level, event, lang):
    t = composer.compose(role, ev(level, event), lang)
    assert composer.is_gsm7(t), t
    assert composer.gsm_len(t) <= 160, (len(t), t)


@pytest.mark.parametrize("role", ["farmer", "herder", "resident"])
def test_no_probability_for_communities(role):
    for lvl in (2, 3):
        for e in ("cant_plant", "crop_failure", "no_grass"):
            t = composer.compose(role, ev(lvl, e, "Binga"))
            assert "%" not in t and "0.68" not in t and not re.search(r"P\(", t)
            assert "STOP" in t


def test_ngo_gets_p_and_driver():
    t = composer.compose("ngo", ev(2, "crop_failure", "Binga"))
    assert "0.68" in t and "rain index" in t


def _user(phone, role, district, **kw):
    ids = {u["name"]: u["id"] for u in db.geo_units("ZWE")}
    return db.upsert_user(phone, role=role, iso3="ZWE", district_id=ids.get(district) if district else None,
                          district_name=district, consent_at=db.now_iso(), **kw)


_T = iter(range(100, 10_000))


def _event(level, event="crop_failure", district="Binga"):
    ids = {u["name"]: u["id"] for u in db.geo_units("ZWE")}
    return db.ex("INSERT INTO events (created_at, iso3, unit_id, unit_name, t, level, event, p, drivers_json, status) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?)",
                 (db.now_iso(), "ZWE", ids[district], district, next(_T), level, event, 0.6, '["dry"]', "approved"))


def test_matching_rules():
    _user("+f", "farmer", "Binga")
    _user("+h", "herder", "Binga")
    _user("+n", "ngo", "Binga")
    _user("+N", "ngo", None)            # national NGO
    _user("+r", "resident", "Binga")
    _user("+x", "farmer", "Hwange")     # other district
    _user("+o", "farmer", "Binga", opted_out_at=db.now_iso())
    r = composer.send_event(_event(2, "crop_failure"))
    phones = {m["phone"] for m in db.q("SELECT phone FROM messages WHERE direction='out'")}
    assert phones == {"+f", "+n", "+N"}
    assert r["skipped"]["opted_out"] == 1
    # no_grass Warning -> herder, not farmer
    composer.send_event(_event(2, "no_grass"))
    assert {m["phone"] for m in db.q("SELECT phone FROM messages WHERE event_id=2")} == {"+h", "+n", "+N"}
    # Emergency -> everyone subscribed in the district (farmer too, even for no_grass)
    composer.send_event(_event(3, "no_grass"))
    msgs = {m["phone"]: m["text"] for m in db.q("SELECT phone, text FROM messages WHERE event_id=3")}
    assert set(msgs) == {"+f", "+h", "+n", "+N", "+r"}
    assert "grain" in msgs["+f"] and "%" not in msgs["+f"]


def test_no_double_send_and_monthly_cap(monkeypatch):
    _user("+f", "farmer", "Binga")
    e = _event(2)
    composer.send_event(e)
    r = composer.send_event(e)
    assert r["sent"] == 0 and r["skipped"]["already_sent"] == 1
    monkeypatch.setenv("MONTHLY_CAP", "1")
    r = composer.send_event(_event(3))
    assert r["sent"] == 0 and r["skipped"]["monthly_cap"] == 1


def test_failed_sends_not_marked_sent(monkeypatch):
    from backend import gateway
    _user("+f", "farmer", "Binga")
    _user("+n", "ngo", "Binga")
    monkeypatch.setattr(gateway, "send", lambda phone, text: ("failed:ConnectError", None) if phone == "+f" else ("queued", "g"))
    e = _event(2)
    r = composer.send_event(e)
    assert r["sent"] == 1 and r["failed"] == 1 and r["status"] == "approved"
    assert db.q1("SELECT status FROM events WHERE id=?", (e,))["status"] == "approved"
    assert composer.event_counts(e) == {"sent_count": 1, "failed_count": 1, "sent_to_label": "sent to 1 users, failed 1"}
    assert db.q1("SELECT status FROM messages WHERE phone='+f'")["status"] == "failed:ConnectError"
    # retry after the gateway is back: only the failed user is re-sent
    monkeypatch.setattr(gateway, "send", lambda phone, text: ("queued", "g2"))
    r = composer.send_event(e)
    assert r["sent"] == 1 and r["status"] == "sent"
    assert composer.event_counts(e)["failed_count"] == 0


def test_unique_index_blocks_double_send():
    import sqlite3
    uid = _user("+f", "farmer", "Binga")
    e = _event(2)
    db.log_message("out", "+f", "x", user_id=uid, event_id=e, status="sending")
    with pytest.raises(sqlite3.IntegrityError):
        db.log_message("out", "+f", "x", user_id=uid, event_id=e, status="sending")


# ---- forecast alerts
def test_forecast_sms_one_segment_all_roles():
    ev = {"unit_name": "Turkana Central", "level": 2, "event": "no_grass", "lead": 3,
          "target_label": "Dec 2026", "basis": "FEWS NET phase 3", "p": 0.5, "unit_id": "x"}
    for lvl in (2, 3):
        for name in ("Turkana Central", "Mandera South", "A very long sub-county name that goes on and on"):
            for role in ("herder", "farmer", "officer", "ngo", "resident"):
                t = composer.compose(role, {**ev, "level": lvl, "unit_name": name})
                assert composer.is_gsm7(t) and composer.gsm_len(t) <= 160, (role, t)
                assert "Dec 2026" in t and "%" not in t and "0.5" not in t
    assert composer.compose("herder", ev).startswith("ALERT Turkana Central: food crisis likely by Dec 2026. Sell weak")


def test_forecast_events_stored_idempotent_and_not_sent(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTO_SEND", "0")
    from backend import app as appmod
    from backend.tests.conftest import make_risk, write_risk
    risk = make_risk({"Binga": {}, "Hwange": {}, "Kariba": {}})
    for u, f in zip(risk["units"], ({"p_crisis": 0.7, "fews_phase": 1}, {"p": 0.1, "fews_phase": 3},
                                    {"p": 0.2, "fews_phase": 2})):
        u["series"][60]["forecast"] = {"3": f}
    monkeypatch.setenv("RISK_DIR", str(tmp_path))
    write_risk(tmp_path, risk)
    r1 = appmod.run_forecast_alerts("ZWE", 60, 3)
    assert r1["created"] == 2 and r1["target_month"] == db.month_label(63, 2019)  # model 0.7>=0.57; FEWS phase 3
    assert appmod.run_forecast_alerts("ZWE", 60, 3)["created"] == 0
    rows = db.q("SELECT * FROM events ORDER BY id")
    assert {r["basis"] for r in rows} == {"our model", "FEWS NET phase 3"}
    assert all(r["status"] == "pending_approval" and r["lead"] == 3 and r["issue_t"] == 60 and r["t"] == 63 for r in rows)
    assert not db.q("SELECT 1 FROM messages WHERE direction='out'")


def test_forecast_auto_send_sim(tmp_path, monkeypatch):
    from backend import app as appmod
    from backend.tests.conftest import make_risk, write_risk
    risk = make_risk({"Binga": {}})
    risk["units"][0]["series"][60]["forecast"] = {"3": {"p": 0.1, "fews_phase": 3}}
    monkeypatch.setenv("RISK_DIR", str(tmp_path))
    monkeypatch.setenv("GATEWAY", "sim")
    write_risk(tmp_path, risk)
    _user("+n9", "ngo", "Binga")
    r = appmod.run_forecast_alerts("ZWE", 60, 3)
    assert r["sms_sent"] == 1
    assert db.q1("SELECT status, approved_by FROM events") == {"status": "sent", "approved_by": "auto"}
    assert "by " in db.q1("SELECT text FROM messages WHERE direction='out'")["text"]
