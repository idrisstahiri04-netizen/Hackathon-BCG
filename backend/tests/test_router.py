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


REG = "To register, please contact your local officer."


def test_join_from_unknown_number_gets_polite_reply(fake_llm):
    fake_llm.set(lambda *a: (_ for _ in ()).throw(AssertionError("LLM must not be called")))
    r = router.handle_inbound("+3", "JOIN")
    assert r["reply"] == REG and db.get_user("+3") is None and not db.get_session("+3")


def test_join_with_details_and_llm_subscribe_create_no_user(fake_llm):
    r = router.handle_inbound("+23", "JOIN Mbire farmer")
    assert r["reply"] == REG and db.get_user("+23") is None
    fake_llm.set(lambda *a: llm_result(intent="subscribe", district="binga", role="farmer", name="Tendai"))
    r = router.handle_inbound("+2", "Hi I am Tendai, I grow maize in binga, want alerts")
    assert r["reply"] == REG and db.get_user("+2") is None and not db.get_session("+2")


def test_bare_district_from_unknown_number_gets_polite_reply(fake_llm):
    fake_llm.set(lambda *a: (_ for _ in ()).throw(AssertionError("LLM must not be called")))
    r = router.handle_inbound("+46", "Binga")
    assert r["reply"] == REG and db.get_user("+46") is None


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
        picked["id"] = schema["properties"]["id"]["enum"][0]
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


import pytest  # noqa: E402


@pytest.mark.parametrize("role,report_word", [("farmer", "Crop"), ("herder", "Grazing"), ("resident", "Food and water")])
def test_role_aware_report(role, report_word):
    db.upsert_user("+30", role=role, district_name="Binga", consent_at=db.now_iso())
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



@pytest.mark.parametrize("w", ["Mira kutumira", "MISA", "yima", "Yekela", "rega", "Stop please"])
def test_shona_ndebele_stop_keywords(w, fake_llm):
    fake_llm.set(lambda *a: (_ for _ in ()).throw(AssertionError("LLM must not be called")))
    db.upsert_user("+40", role="farmer", consent_at=db.now_iso())
    assert router.handle_inbound("+40", w)["intent"] == "stop"
    assert db.get_user("+40")["opted_out_at"]


@pytest.mark.parametrize("t", ["123", "0772 123 456", "11"])
def test_digits_are_not_reports(t, fake_llm):
    fake_llm.set(lambda *a: (_ for _ in ()).throw(AssertionError("LLM must not be called")))
    db.upsert_user("+41", role="farmer", district_name="Binga", consent_at=db.now_iso())
    r = router.handle_inbound("+41", t)
    assert r["intent"] == "unknown" and "did not understand" in r["reply"]
    assert db.q1("SELECT COUNT(*) n FROM messages WHERE intent='report'")["n"] == 0


def test_off_scope_question_polite_reply(fake_llm):
    fake_llm.set(lambda *a: llm_result(intent="unknown", confidence=0.9))
    r = router.handle_inbound("+42", "will it rain next week in Binga?")
    assert "cannot answer weather" in r["reply"]


def test_off_scope_routed_as_advice_still_no_wrong_advice(fake_llm):
    fake_llm.set(lambda *a: llm_result(intent="ask_advice", confidence=0.8))
    r = router.handle_inbound("+43", "how much is a 50kg bag of maize meal now")
    assert r["reply"] not in {e["text"] for e in router.load_advice()}


def test_advice_picker_may_say_none(fake_llm):
    def fn(model, system, user, schema):
        if "intent" in schema["properties"]:
            return llm_result(intent="ask_advice", confidence=0.9)
        assert "none" in schema["properties"]["id"]["enum"]
        return {"id": "none"}
    fake_llm.set(fn)
    r = router.handle_inbound("+44", "what do you think?")
    assert "no advice" in r["reply"]


def test_confidence_at_threshold_is_low(fake_llm):
    fake_llm.set(lambda *a: llm_result(intent="ask_advice", confidence=router.CONF_MIN))
    r = router.handle_inbound("+45", "is the drought going to end soon")
    assert r["parsed"].get("clarify") is True


def test_bare_district_registered_user_not_resubscribed(fake_llm):
    fake_llm.set(lambda *a: llm_result(intent="unknown", confidence=0.4, district="Binga"))
    db.upsert_user("+48", role="farmer", district_name="Binga", consent_at=db.now_iso())
    assert router.handle_inbound("+48", "Binga")["intent"] == "unknown"


def test_language_enum_has_no_bemba():
    enum = router._router_schema()["properties"]["language"]["enum"]
    assert "sn" in enum and "nd" in enum and "bem" not in enum


def test_price_word_in_real_advice_question_still_answered():
    db.upsert_user("+49", role="herder", consent_at=db.now_iso())
    r = router.handle_inbound("+49", "should I sell my goats before prices drop?")
    assert r["reply"] in {e["text"] for e in router.load_advice()}


def test_question_mentioning_district_is_not_signup(fake_llm):
    fake_llm.set(lambda *a: llm_result(intent="unknown", confidence=0.9, district="Binga"))
    r = router.handle_inbound("+50", "will it rain next week in Binga?")
    assert r["intent"] == "unknown" and "cannot answer weather" in r["reply"]



@pytest.mark.parametrize("t", ["We can't manage", "we cannot cope anymore", "please help us", "We need food",
                               "Hatina chikafu", "Batsirai", "Siza", "aidez-nous svp", "sicela uncedo"])
def test_help_phrases_fast_path(t, fake_llm):
    fake_llm.set(lambda *a: (_ for _ in ()).throw(AssertionError("LLM must not be called")))
    r = router.handle_inbound("+60", t)
    assert r["intent"] == "ask_help" and ("officer will contact" in r["reply"] or "agent va" in r["reply"])
    assert db.q1("SELECT COUNT(*) n FROM help_requests")["n"] == 1


def test_help_low_confidence_still_creates_request(fake_llm):
    fake_llm.set(lambda *a: llm_result(intent="ask_help", confidence=0.5))
    r = router.handle_inbound("+61", "things are very bad here")
    assert r["intent"] == "ask_help" and "officer will contact" in r["reply"]
    assert db.q1("SELECT COUNT(*) n FROM help_requests")["n"] == 1


def test_help_very_low_confidence_clarifies(fake_llm):
    fake_llm.set(lambda *a: llm_result(intent="ask_help", confidence=0.3))
    assert router.handle_inbound("+62", "hm")["parsed"]["clarify"] is True


def test_help_beats_signup_session_and_rate_limit(monkeypatch):
    db.set_session("+63", {"step": "district", "draft": {}})  # stale sign-up state
    r = router.handle_inbound("+63", "we have no food, please help")
    assert r["intent"] == "ask_help"
    monkeypatch.setattr(router, "PER_MIN", 0)
    assert router.handle_inbound("+63", "We can't manage")["intent"] == "ask_help"


def test_help_phrase_not_triggered_by_normal_advice():
    assert not router.HELP_PHRASES.search("should I sell my goats?")
    assert not router.HELP_PHRASES.search("what should I plant this season?")
