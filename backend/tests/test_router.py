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
        assert model == "claude-sonnet-5-5"
        return {"id": "crop_store_safely"}
    fake_llm.set(fn)
    db.upsert_user("+8", role="farmer", consent_at=db.now_iso())
    r = router.handle_inbound("+8", "how do I keep my maize from weevils?")
    assert r["reply"] == entries["crop_store_safely"]


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
