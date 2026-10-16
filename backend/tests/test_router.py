from backend import db, router


def llm_result(**kw):
    base = {"intent": "unknown", "confidence": 0.9, "language": "en", "district": None,
            "role": None, "name": None, "report_value": None}
    base.update(kw)
    return base


def test_stop_fast_path_no_llm(fake_llm):
    fake_llm.set(lambda *a: (_ for _ in ()).throw(AssertionError("LLM must not be called")))
    db.upsert_user("+1", role="farmer", consent_at=db.now_iso())
    r = router.handle_inbound("+1", "STOP")
    assert r["intent"] == "stop"
    assert db.get_user("+1")["opted_out_at"]


def test_report_fast_path(fake_llm):
    fake_llm.set(lambda *a: (_ for _ in ()).throw(AssertionError("LLM must not be called")))
    db.upsert_user("+1", role="farmer", district_name="Binga", consent_at=db.now_iso())
    r = router.handle_inbound("+1", "3")
    assert r["intent"] == "report" and r["parsed"]["report_value"] == 3
    assert "failed" in r["reply"]
    m = db.q1("SELECT * FROM messages WHERE direction='in'")
    assert m["intent"] == "report"


def test_signup_full_flow_with_llm(fake_llm):
    fake_llm.set(lambda *a: llm_result(intent="subscribe", district="binga", role="farmer", name="Tendai"))
    r = router.handle_inbound("+2", "Hi I am Tendai, I grow maize in binga, want alerts")
    assert "Binga" in r["reply"] and "YES" in r["reply"]
    assert db.get_user("+2") is None  # no consent yet
    r = router.handle_inbound("+2", "yes")
    u = db.get_user("+2")
    assert u["district_name"] == "Binga" and u["role"] == "farmer" and u["consent_at"] and u["name"] == "Tendai"
    assert u["district_id"] == db.geo_units("ZWE")[[x["name"] for x in db.geo_units("ZWE")].index("Binga")]["id"]


def test_join_keyword_asks_district_then_role_then_confirm():
    r = router.handle_inbound("+3", "JOIN")
    assert "district" in r["reply"].lower()
    r = router.handle_inbound("+3", "Hwange")
    assert "farmer" in r["reply"].lower()  # asks role
    r = router.handle_inbound("+3", "herder")
    assert "YES" in r["reply"]
    router.handle_inbound("+3", "YES")
    assert db.get_user("+3")["role"] == "herder"


def test_ambiguous_district_asks_back():
    router.handle_inbound("+4", "JOIN")
    r = router.handle_inbound("+4", "Gokwe")
    assert "Gokwe North" in r["reply"] and "Gokwe South" in r["reply"]
    r = router.handle_inbound("+4", "1")  # pick option 1, NOT a crop report
    assert r["intent"] == "subscribe"
    assert "Are you" in r["reply"]


def test_unknown_district_not_free_text(fake_llm):
    fake_llm.set(lambda *a: llm_result(intent="subscribe", district="Atlantis", role="farmer"))
    r = router.handle_inbound("+5", "join me, farmer in Atlantis")
    assert "do not know" in r["reply"]
    assert db.get_user("+5") is None


def test_low_confidence_clarifies(fake_llm):
    fake_llm.set(lambda *a: llm_result(intent="ask_advice", confidence=0.3))
    r = router.handle_inbound("+6", "mmm the thing")
    assert r["parsed"]["clarify"] is True
    assert "did not understand" in r["reply"]


def test_help_creates_request(fake_llm):
    fake_llm.set(lambda *a: llm_result(intent="ask_help", confidence=0.95))
    r = router.handle_inbound("+7", "we have no food left for the children")
    assert "officer will contact" in r["reply"]
    assert db.q1("SELECT COUNT(*) n FROM help_requests")["n"] == 1


def test_advice_only_from_yaml(fake_llm):
    entries = {e["id"]: e["text"] for e in router.load_advice()}

    def fn(model, system, user, schema):
        if "intent" in schema["properties"]:
            return llm_result(intent="ask_advice", confidence=0.9)
        picked["id"] = schema["properties"]["id"]["enum"][-1]
        return {"id": picked["id"]}
    picked = {}
    fake_llm.set(fn)
    db.upsert_user("+8", role="farmer", consent_at=db.now_iso())
    r = router.handle_inbound("+8", "what do you advise?")
    assert r["reply"] == entries[picked["id"]]


def test_advice_invalid_pick_falls_back_to_library(fake_llm):
    def fn(model, system, user, schema):
        if "intent" in schema["properties"]:
            return llm_result(intent="ask_advice", confidence=0.9)
        return {"id": "invented_advice"}
    fake_llm.set(fn)
    r = router.handle_inbound("+9", "what now?")
    assert r["reply"] in {e["text"] for e in router.load_advice()}


def test_french_reply(fake_llm):
    fake_llm.set(lambda *a: llm_result(intent="ask_help", language="fr", confidence=0.9))
    r = router.handle_inbound("+10", "j'ai besoin d'aide svp")
    assert "agent" in r["reply"]


def test_change_info(fake_llm):
    db.upsert_user("+11", role="farmer", district_name="Binga", iso3="ZWE", consent_at=db.now_iso())
    fake_llm.set(lambda *a: llm_result(intent="change_info", district="Hwange", role="herder"))
    r = router.handle_inbound("+11", "I moved to Hwange and now keep cattle")
    u = db.get_user("+11")
    assert u["district_name"] == "Hwange" and u["role"] == "herder"


def test_llm_down_keyword_fallback():
    r = router.handle_inbound("+12", "please help")
    assert r["intent"] == "ask_help"


def test_registry_complete():
    assert router.registry_names() == ["subscribe", "report", "ask_advice", "ask_help", "stop", "change_info", "unknown"]


def test_all_replies_one_segment():
    from backend import composer
    for lang in router.R:
        for key in router.R[lang]:
            txt = router.say(lang, key, district="Uzumba Maramba Pfungwe", role="resident",
                             name="Uzumba Maramba Pfungwe", options="1 Gokwe North, 2 Gokwe South, 3 Gokwe South Urban",
                             label="failed")
            assert composer.is_gsm7(txt) and composer.gsm_len(txt) <= 160, (lang, key, txt)


def test_goats_question_gets_livestock_advice_without_llm():
    db.upsert_user("+20", role="farmer", consent_at=db.now_iso())
    r = router.handle_inbound("+20", "should I sell my goats?")
    assert r["reply"] == next(e["text"] for e in router.load_advice() if e["id"] == "grass_destock_early")


def test_livestock_candidates_offered_to_sonnet(fake_llm):
    seen = {}

    def fn(model, system, user, schema):
        if "intent" in schema["properties"]:
            return llm_result(intent="ask_advice", confidence=0.9)
        seen["ids"] = schema["properties"]["id"]["enum"]
        seen["system"] = system
        return {"id": seen["ids"][0]}
    fake_llm.set(fn)
    db.upsert_user("+21", role="farmer", consent_at=db.now_iso())
    router.handle_inbound("+21", "should I sell my goats?")
    # clear topic match -> answered locally, no second LLM call
    assert "ids" not in seen
    router.handle_inbound("+21", "what should I do now?")  # vague -> LLM picks among top entries
    assert "User role: farmer" in seen["system"]
    assert not {"ngo_trigger_check", "officer_prioritise"} & set(seen["ids"])


def test_grain_question_gets_crop_advice_without_llm():
    db.upsert_user("+22", role="herder", consent_at=db.now_iso())
    r = router.handle_inbound("+22", "how do I store my maize grain?")
    assert r["reply"] == next(e["text"] for e in router.load_advice() if e["id"] == "crop_store_safely")


def test_join_district_role_fast_path(fake_llm):
    fake_llm.set(lambda *a: (_ for _ in ()).throw(AssertionError("LLM must not be called")))
    r = router.handle_inbound("+23", "JOIN Mbire farmer")
    assert r["parsed"]["source"] == "keyword" and "Mbire" in r["reply"] and "YES" in r["reply"]
    router.handle_inbound("+23", "YES")
    assert db.get_user("+23")["role"] == "farmer"


import pytest  # noqa: E402


@pytest.mark.parametrize("role,report_word,join_word", [
    ("farmer", "Crop", "crops"), ("herder", "Grazing", "grazing"), ("resident", "Food and water", "food and water")])
def test_role_aware_report_and_join(role, report_word, join_word):
    router.handle_inbound("+30", f"JOIN Binga {role}")
    r = router.handle_inbound("+30", "YES")
    assert join_word in r["reply"], r["reply"]
    if role != "farmer":
        assert "crops" not in r["reply"]
    r = router.handle_inbound("+30", "3")
    assert r["reply"].startswith(f"Thank you. {report_word}"), r["reply"]
    if role == "herder":
        assert "'bad'" in r["reply"] and "Crop" not in r["reply"]


def test_role_aware_french_herder():
    db.upsert_user("+31", role="herder", district_name="Hwange", language="fr", consent_at=db.now_iso())
    r = router.handle_inbound("+31", "2")
    assert "paturages" in r["reply"] and "cultures" not in r["reply"]


def test_role_variants_one_segment():
    from backend import composer
    for lang in router.R:
        for role in router.ROLES:
            for key in ("joined", "report_thanks"):
                txt = router.say_role(lang, key, role, district="Uzumba Maramba Pfungwe", label="short")
                assert composer.is_gsm7(txt) and composer.gsm_len(txt) <= 160 and not txt.endswith("..."), (lang, role, key, len(txt), txt)
