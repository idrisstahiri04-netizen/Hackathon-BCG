"""ONE live smoke test: real Claude Haiku call on 6 sample SMS. Run: pytest -m live -s"""
import pytest

from backend import llm, router

SAMPLES = [
    ("Hi, my name is Rudo, I grow maize in Binga and want the drought alerts", "subscribe"),
    ("3", "report"),  # fast-path, no LLM
    ("our maize has completely dried up, nothing to harvest", "report"),
    ("should I sell my goats now or wait?", "ask_advice"),
    ("please stop sending me messages", "stop"),
    ("Bonjour, je suis eleveur a Hwange, je veux recevoir les alertes", "subscribe"),
]


@pytest.mark.live
def test_live_haiku_intents():
    if not llm.available():
        pytest.skip("no ANTHROPIC_API_KEY")
    hits = 0
    for text, want in SAMPLES:
        if text.strip() in {"1", "2", "3"}:
            got = {"intent": "report", "confidence": 1.0, "source": "keyword"}
        else:
            got = router.classify(text)
        print(f"\n{got.get('source'):8} {got['intent']:12} conf={got.get('confidence')} "
              f"district={got.get('district')} role={got.get('role')} lang={got.get('language')} "
              f"report={got.get('report_value')} | {text}")
        assert got.get("source") in ("llm", "keyword"), "Claude call failed, fell back to keywords"
        hits += got["intent"] == want
    assert hits >= 5


@pytest.mark.live
def test_live_sonnet_advice_goats():
    if not llm.available():
        pytest.skip("no ANTHROPIC_API_KEY")
    from backend import db
    db.upsert_user("+30", role="farmer", consent_at=db.now_iso())
    txt = router.pick_advice(db.get_user("+30"), "should I sell my goats now or wait?")
    print("\nAdvice (farmer, goats):", txt)
    livestock = {e["text"] for e in router.load_advice() if e["id"].startswith("grass_")}
    assert txt in livestock


@pytest.mark.live
def test_live_help_unsure_phrasing():
    """Rehearsal regression: free-text distress that is NOT in the keyword list still reaches a human."""
    if not llm.available():
        pytest.skip("no ANTHROPIC_API_KEY")
    from backend import db
    for i, text in enumerate(["We can't manage", "things are really bad, the children are weak",
                              "Zvinhu zvakaoma, hatichakwanisi"]):
        r = router.handle_inbound(f"+2637790000{i:02d}", text)
        print(f"\n{r['parsed'].get('source'):8} {r['intent']:10} conf={r['confidence']} | {text} -> {r['reply'][:50]}")
        assert r["intent"] == "ask_help", (text, r["parsed"])
    assert db.q1("SELECT COUNT(*) n FROM help_requests")["n"] == 3
