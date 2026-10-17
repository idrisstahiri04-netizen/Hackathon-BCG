import re

import pytest

from backend import recommend

EVENTS = ["no_grass", "crop_failure", "cant_plant", "none"]
VERBS = re.compile(r"^[A-Z][a-z-]+$")
ALERT = {"county": "Turkana", "pop": 926976, "p_crisis": 0.62, "fews_phase": 3, "n_hit": 6, "n_units": 47,
         "unit_word": "counties", "drivers": ["3-month rainfall index -2.1", "vegetation greenness low"]}


@pytest.mark.parametrize("event", EVENTS)
@pytest.mark.parametrize("level", [2, 3])
@pytest.mark.parametrize("role", recommend.ROLES)
def test_role_has_complete_actions(event, level, role):
    recs = recommend.role_recommend({**ALERT, "level": level, "event": event}, role)
    assert len(recs) >= 2
    for r in recs:
        assert VERBS.match(r["verb"]) and r["action"].startswith(r["verb"])
        assert r["who"] and r["when"] and r["source"] and "NDMA/WHH" in r["note"]
        assert "Turkana" in r["evidence"] and "62%" in r["evidence"] and "IPC 3" in r["evidence"]
        assert "{" not in r["action"] + (r["quantity"] or "")


def test_below_warning_and_missing_data():
    assert recommend.role_recommend({**ALERT, "level": 1, "fews_phase": None}, "gov") == []
    r = recommend.role_recommend({"county": "X", "level": 2, "event": "none"}, "gov")
    assert r and all(x["quantity"] is None or "None" not in x["quantity"] for x in r)


def test_roles_differ_and_herder_generic_gap():
    g = {x["id"] for x in recommend.role_recommend({**ALERT, "level": 2}, "gov")}
    n = {x["id"] for x in recommend.role_recommend({**ALERT, "level": 2}, "ngo")}
    assert not g & n
    h = recommend.recommend({"level": 2, "event": "none"})
    assert any(x["audience"] == "herder" and "herd_generic" in x["id"] for x in h)


def test_fews_phase_drives_role_actions():
    a = {**ALERT, "level": 2, "event": "none"}
    p3 = recommend.role_recommend({**a, "fews_phase": 3}, "gov")
    p4 = recommend.role_recommend({**a, "fews_phase": 4}, "gov")
    assert {x["phase"] for x in p3} == {"prepare"} and p3[0]["basis"] == "Based on: FEWS NET Phase 3"
    assert {x["phase"] for x in p4} == {"respond"} and p4[0]["basis"] == "Based on: FEWS NET Phase 4"
    # FEWS missing: our alert level decides and says so
    m = recommend.role_recommend({**a, "fews_phase": None, "level": 3}, "ngo")
    assert {x["phase"] for x in m} == {"respond"} and m[0]["basis"] == "Based on: our model"
    # FEWS Phase 1-2 with no alert from us: nothing
    assert recommend.role_recommend({**a, "fews_phase": 2, "level": 1}, "ngo") == []
