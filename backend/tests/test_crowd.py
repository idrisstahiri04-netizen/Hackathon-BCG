"""Crowd signal: /feed/crowd aggregation, anti-gaming, consent filter and the display-level rule."""
import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend import app as appmod
from backend import crowd, db, seed_crowd
from backend.tests.conftest import ZWE_IDS, make_risk, write_risk

anon = TestClient(appmod.app)  # aggregated counts need no admin key


def _iso(dt):
    return dt.replace(microsecond=0).isoformat()


def _user(phone, district="Binga", consent=True, opted_out=False, iso3="ZWE"):
    return db.upsert_user(phone, role="farmer", iso3=iso3, district_id=ZWE_IDS[district], district_name=district,
                          consent_at=db.now_iso() if consent else None,
                          opted_out_at=db.now_iso() if opted_out else None)


def _report(uid, phone, value, when=None, intent="report", **extra):
    when = when or datetime.now(timezone.utc)
    parsed = {"intent": intent, "report_value": value, "confidence": 1.0, **extra}
    return db.log_message("in", phone, str(value), user_id=uid, intent=intent, parsed_json=json.dumps(parsed),
                          status="received", created_at=_iso(when))


def test_shares_and_filters():
    a = _user("+a"); b = _user("+b"); c = _user("+c")
    _report(a, "+a", 3); _report(b, "+b", 2); _report(c, "+c", 1)
    # ignored: no consent, opted out, anonymous (no user), other intent, other district window
    nc = _user("+nc", consent=False); _report(nc, "+nc", 3)
    oo = _user("+oo", opted_out=True); _report(oo, "+oo", 3)
    db.log_message("in", "+anon", "3", user_id=None, intent="report", parsed_json=json.dumps({"report_value": 3}),
                   status="received")
    _report(a, "+a", 3, intent="ask_advice")
    _report(a, "+a", 3, when=datetime.now(timezone.utc) - timedelta(days=40))  # outside 30 d window

    r = anon.get("/feed/crowd?iso3=ZWE").json()
    assert r["iso3"] == "ZWE" and r["window_days"] == 30
    assert len(r["units"]) == 1
    u = r["units"][0]
    assert u["unit_name"] == "Binga" and u["n_reports"] == 3 and u["n_users"] == 3
    assert u["n_bad"] == 2 and u["n_failed"] == 1
    assert u["share_bad"] == 0.667 and u["share_failed"] == 0.333
    assert u["last_report_at"]
    # privacy: no phone numbers or names anywhere in the response
    body = json.dumps(r)
    assert "+a" not in body.replace("+ab", "") and "phone" not in body and "name\"" not in body.replace("unit_name", "")


def test_anti_gaming_one_report_per_user_per_7_days():
    a = _user("+a")
    now = datetime.now(timezone.utc)
    for d in (0, 1, 2, 3):           # 4 reports in 4 days: only the newest counts
        _report(a, "+a", 3, when=now - timedelta(days=d))
    _report(a, "+a", 1, when=now - timedelta(days=8))   # >= 7 d older than the kept one: counts
    _report(a, "+a", 1, when=now - timedelta(days=10))  # within 7 d of the day-8 one: dropped
    u = anon.get("/feed/crowd?iso3=ZWE").json()["units"][0]
    assert u["n_reports"] == 2 and u["n_users"] == 1 and u["n_bad"] == 1 and u["share_bad"] == 0.5


def test_rule_needs_crowd_and_satellite():
    fam_rain = {"rain": True, "vegetation": False, "soil": False, "heat": False}
    fam_none = {"rain": False, "vegetation": False, "soil": False, "heat": True}  # heat alone never counts
    strong = {"n_reports": 3, "share_bad": 0.67}
    weak_n = {"n_reports": 2, "share_bad": 1.0}
    weak_s = {"n_reports": 10, "share_bad": 0.5}

    assert crowd.apply_rule(1, fam_rain, strong)["display_level"] == 2          # Watch -> Warning
    assert crowd.apply_rule(1, fam_rain, strong)["crowd_confirmed"] is True
    assert crowd.apply_rule(0, fam_rain, strong)["display_level"] == 1          # Normal -> Watch only
    assert crowd.apply_rule(2, fam_rain, strong)["display_level"] == 2          # max Warning
    assert crowd.apply_rule(2, fam_rain, strong)["crowd_confirmed"] is True
    assert crowd.apply_rule(3, fam_rain, strong)["display_level"] == 3          # never touches Emergency
    assert crowd.apply_rule(1, fam_none, strong)["display_level"] == 1          # never the sole trigger
    assert crowd.apply_rule(1, fam_none, strong)["crowd_confirmed"] is False
    assert crowd.apply_rule(1, fam_rain, weak_n)["display_level"] == 1
    assert crowd.apply_rule(1, fam_rain, weak_s)["display_level"] == 1
    assert crowd.apply_rule(1, fam_rain, {"n_reports": 0, "share_bad": None})["display_level"] == 1
    assert crowd.apply_rule(None, fam_rain, strong)["display_level"] is None    # missing stays missing
    assert crowd.apply_rule(1, None, strong)["display_level"] == 1


def test_feed_crowd_with_t_applies_rule(isolated):
    write_risk(isolated, make_risk({"Binga": {63: (1, "crop_failure")}, "Hwange": {63: (1, "no_grass")}}))
    for p in ("+a", "+b", "+c"):
        _report(_user(p), p, 3)
    for p in ("+x", "+y", "+z"):                     # Hwange: 1 of 3 bad -> below threshold
        _report(_user(p, "Hwange"), p, 1)
    _report(_user("+w", "Hwange"), "+w", 3)
    r = anon.get("/feed/crowd?iso3=ZWE&t=63").json()
    by = {u["unit_name"]: u for u in r["units"]}
    assert by["Binga"]["model_level"] == 1 and by["Binga"]["display_level"] == 2 and by["Binga"]["crowd_confirmed"]
    assert by["Hwange"]["display_level"] == 1 and not by["Hwange"]["crowd_confirmed"]
    assert r["rule"]["min_reports"] == 3 and r["rule"]["min_share_bad"] == 0.6
    # month 0 has no alarm in the fixture (level 0, families still rain+veg): Normal -> Watch at most
    r0 = anon.get("/feed/crowd?iso3=ZWE&t=0").json()
    assert {u["unit_name"]: u["display_level"] for u in r0["units"]}["Binga"] == 1


def test_feed_crowd_without_risk_file_still_counts(isolated):
    _report(_user("+a"), "+a", 3)
    r = anon.get("/feed/crowd?iso3=ZWE&t=63").json()
    assert r["units"][0]["n_reports"] == 1 and r["units"][0]["model_level"] is None
    assert r["units"][0]["display_level"] is None and not r["units"][0]["crowd_confirmed"]


def test_feed_crowd_bad_params():
    assert anon.get("/feed/crowd?iso3=Z").status_code == 422
    assert anon.get("/feed/crowd?iso3=ZWE&days=0").status_code == 422
    assert anon.get("/feed/crowd?iso3=ZWE").json()["units"] == []


def test_seed_crowd_is_demo_marked_and_idempotent():
    r = seed_crowd.seed("Hurungwe")
    seed_crowd.seed("Hurungwe")
    assert r["reports"] == 4 and r["share_bad"] == 0.5
    u = anon.get("/feed/crowd?iso3=ZWE").json()["units"][0]
    assert u["unit_name"] == "Hurungwe" and u["n_reports"] == 4 and u["n_demo"] == 4 and u["share_bad"] == 0.5
    # the live jury reply "3" from a real subscriber tips it over
    j = _user("+jury", "Hurungwe"); _report(j, "+jury", 3)
    u = anon.get("/feed/crowd?iso3=ZWE").json()["units"][0]
    assert u["n_reports"] == 5 and u["share_bad"] == 0.6 and u["n_demo"] == 4
    assert seed_crowd.clear() == 4
    assert anon.get("/feed/crowd?iso3=ZWE").json()["units"][0]["n_reports"] == 1
