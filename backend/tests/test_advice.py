from backend import composer, router

ROLES = {"farmer", "herder", "ngo", "officer", "resident"}


def test_advice_library_valid():
    entries = router.load_advice()
    assert 12 <= len(entries) <= 15
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids))
    for e in entries:
        assert e["event"] in {"cant_plant", "crop_failure", "no_grass", "any"}
        assert set(e["roles"]) <= ROLES
        assert e["source"]
        assert composer.is_gsm7(e["text"]) and composer.gsm_len(e["text"]) <= 160, e["id"]
        assert "%" not in e["text"]


def test_every_role_has_advice():
    entries = router.load_advice()
    for role in ROLES:
        assert any(role in e["roles"] for e in entries), role
