import re

import pytest

from backend import composer, db

LONG = "Uzumba Maramba Pfungwe"


def ev(level, event, name=LONG):
    return {"unit_name": name, "level": level, "event": event, "p": 0.68, "horizon": 8, "agreeing": 2,
            "confidence": "medium", "drivers": ["3-month rain index -1.4 (very dry)"]}


def test_audiences():
    assert composer.audiences(0, "crop_failure") == []
    assert composer.audiences(1, "crop_failure") == ["ngo", "officer"]
    assert composer.audiences(2, "crop_failure") == ["ngo", "officer", "farmer"]
    assert composer.audiences(2, "cant_plant") == ["ngo", "officer", "farmer"]
    assert composer.audiences(2, "no_grass") == ["ngo", "officer", "herder"]
    assert composer.audiences(3, "no_grass") == ["ngo", "officer", "herder", "resident"]


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


def _event(level, event="crop_failure", district="Binga"):
    ids = {u["name"]: u["id"] for u in db.geo_units("ZWE")}
    return db.ex("INSERT INTO events (created_at, iso3, unit_id, unit_name, t, level, event, p, drivers_json, status) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?)",
                 (db.now_iso(), "ZWE", ids[district], district, 60, level, event, 0.6, '["dry"]', "approved"))


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
    # no_grass emergency -> herder + resident, not farmer
    composer.send_event(_event(3, "no_grass"))
    last = {m["phone"] for m in db.q("SELECT phone FROM messages WHERE event_id=2")}
    assert last == {"+h", "+n", "+N", "+r"}


def test_no_double_send_and_monthly_cap(monkeypatch):
    _user("+f", "farmer", "Binga")
    e = _event(2)
    composer.send_event(e)
    r = composer.send_event(e)
    assert r["sent"] == 0 and r["skipped"]["already_sent"] == 1
    monkeypatch.setenv("MONTHLY_CAP", "1")
    r = composer.send_event(_event(3))
    assert r["sent"] == 0 and r["skipped"]["monthly_cap"] == 1
