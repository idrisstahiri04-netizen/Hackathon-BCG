import re

import pytest

from backend import composer, recommend

EVENTS = ["no_grass", "crop_failure", "cant_plant", "none"]


@pytest.mark.parametrize("event", EVENTS)
@pytest.mark.parametrize("level", [2, 3])
def test_every_audience_has_action(event, level):
    recs = recommend.recommend({"level": level, "event": event, "drivers": ["3-month rainfall index -2.5"]})
    for a in recommend.AUDIENCES:
        assert any(r["audience"] == a for r in recs), (event, level, a)
    for r in recs:
        assert r["id"] and r["detail"] and r["source"] and r["priority"] >= 1
        if r["audience"] in ("farmer", "herder"):
            for txt in (r["action"], r.get("action_sw") or r["action"]):
                assert composer.is_gsm7(txt) and len(txt) <= 95, txt
                assert "%" not in txt and not re.search(r"\bp\s*=|probab", txt, re.I)


def test_no_recs_below_warning_and_phase():
    assert recommend.recommend({"level": 1, "event": "no_grass"}) == []
    w = recommend.recommend({"level": 2, "event": "no_grass"})
    e = recommend.recommend({"level": 3, "event": "no_grass"})
    assert all(r["phase"] == "prepare" for r in w) and all(r["phase"] == "respond" for r in e)
    assert w[0]["audience"] in recommend.AUDIENCES


def test_event_decides_livestock_vs_crop():
    herder = recommend.top_action(recommend.recommend({"level": 2, "event": "no_grass"}), "herder")
    assert "Sell" in herder
    farmer = recommend.top_action(recommend.recommend({"level": 2, "event": "cant_plant"}), "farmer")
    assert "rain" in farmer.lower()
