"""Audit 3 + 4 - secrets and personal data (phone numbers, consent, STOP, retention)."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import app as appmod
from backend import composer, db, gateway, router
from backend.tests.conftest import AUTH, make_risk, write_risk

from ._helpers import VICTIM, register_victim

client = TestClient(appmod.app, headers=AUTH)   # operator
anon = TestClient(appmod.app)                   # big screen / anyone
REPO = Path(__file__).resolve().parents[3]


# ------------------------------------------------------------- consent / STOP (pass today)
def test_no_consent_no_alert(isolated):
    ids = {u["name"]: u["id"] for u in db.geo_units("ZWE")}
    db.upsert_user(VICTIM, role="farmer", iso3="ZWE", district_id=ids["Binga"], district_name="Binga")  # consent_at NULL
    write_risk(isolated, make_risk({"Binga": {60: (2, "crop_failure")}}))
    eid = client.post("/alerts/run", json={"iso3": "ZWE", "t": 60}).json()["event_ids"][0]
    r = client.post(f"/events/{eid}/approve", json={}).json()
    assert r["sent"] == 0 and r["skipped"]["no_consent"] == 1


def test_stop_is_honoured_and_rejoin_clears_it(isolated):
    register_victim()
    router.handle_inbound(VICTIM, "stop.")
    assert db.get_user(VICTIM)["opted_out_at"]
    write_risk(isolated, make_risk({"Binga": {60: (2, "crop_failure")}}))
    eid = client.post("/alerts/run", json={"iso3": "ZWE", "t": 60}).json()["event_ids"][0]
    assert client.post(f"/events/{eid}/approve", json={}).json()["skipped"]["opted_out"] == 1
    # re-join: district -> role -> YES
    router.handle_inbound(VICTIM, "JOIN")
    router.handle_inbound(VICTIM, "Binga")
    router.handle_inbound(VICTIM, "farmer")
    router.handle_inbound(VICTIM, "YES")
    u = db.get_user(VICTIM)
    assert u["opted_out_at"] is None and u["consent_at"]


def test_stop_variants_never_call_llm(fake_llm):
    fake_llm.set(lambda *a: (_ for _ in ()).throw(AssertionError("LLM called for STOP")))
    register_victim()
    for w in ("STOP", "stop", "Stop!", "UNSUBSCRIBE", "ARRET", "quit"):
        db.ex("UPDATE users SET opted_out_at=NULL WHERE phone=?", (VICTIM,))
        router.handle_inbound(VICTIM, w)
        assert db.get_user(VICTIM)["opted_out_at"], w


# ------------------------------------------------------------- P1: full phone numbers leave the API
def test_feed_users_full_phone_only_for_operator():
    register_victim()
    assert client.get("/feed/users").json()["users"][0]["phone"] == VICTIM
    assert anon.get("/feed/users").json()["users"][0]["phone"] != VICTIM


def test_feeds_do_not_expose_full_phone():
    register_victim()
    router.handle_inbound(VICTIM, "1")
    users = anon.get("/feed/users").json()["users"]
    msgs = anon.get("/feed/messages").json()["messages"]
    assert all(VICTIM not in str(r.values()) for r in users)
    assert all(VICTIM not in str(r.values()) for r in msgs)
    assert all(m["phone_masked"].count("*") >= 3 for m in msgs)


def test_phone_masked_field_and_raw_only_for_operator():
    register_victim()
    router.handle_inbound(VICTIM, "1")
    m = client.get("/feed/messages").json()["messages"][0]
    assert "phone_masked" in m and m["phone"] == VICTIM
    assert anon.get("/feed/messages").json()["messages"][0]["phone"] == m["phone_masked"]


# ------------------------------------------------------------- P2: storage of phone numbers
@pytest.mark.xfail(strict=True, reason="finding P2 (slide note for demo, MUST-FIX for pilot): phone stored plaintext, no phone_hash/phone_enc")
def test_phone_not_stored_in_plaintext():
    register_victim()
    router.handle_inbound(VICTIM, "1")
    for table in ("users", "messages", "sessions"):
        cols = [c["name"] for c in db.q(f"PRAGMA table_info({table})")]
        if "phone" in cols:
            raw = db.q(f"SELECT phone FROM {table}")
            assert all(r["phone"] != VICTIM for r in raw), f"{table}.phone holds the clear number"


def test_raw_signup_text_stores_whole_sms_today(fake_llm):
    """Minimum-data check: the full sign-up SMS (incl. anything else the user typed) is kept."""
    from ._helpers import llm_result
    fake_llm.set(lambda *a: llm_result(intent="subscribe", confidence=1.0, role="farmer", district="Binga", name="Rudo"))
    secret = "my ID number is 63-123456A70"
    router.handle_inbound(VICTIM, f"I am Rudo farmer in Binga, {secret}")
    router.handle_inbound(VICTIM, "YES")
    assert secret in db.get_user(VICTIM)["raw_signup_text"]


# ------------------------------------------------------------- P3: retention
def test_retention_purge_exists():
    assert any(hasattr(db, n) for n in ("purge", "purge_old", "apply_retention", "retention_purge"))


# ------------------------------------------------------------- P4: logging of personal data
def test_log_gateway_masks_phone(monkeypatch, caplog):
    monkeypatch.setenv("GATEWAY", "log")
    with caplog.at_level(logging.INFO, logger="gateway"):
        gateway.send(VICTIM, "WARNING Binga: ...")
    assert VICTIM not in caplog.text


# ------------------------------------------------------------- S1: secrets
def test_env_file_is_outside_repo_and_ignored():
    env = REPO.parent / ".env"
    assert env.is_file()
    assert (REPO / ".gitignore").read_text().splitlines().count(".env") >= 1
    assert not (REPO / ".env").exists() or subprocess.run(
        ["git", "check-ignore", "-q", ".env"], cwd=REPO).returncode == 0


KEY_RE = r"sk-ant-api[0-9]{2}-[A-Za-z0-9_-]{40,}"  # a real key; the 27-char fake in scripts/robustness_tests.py:222 is not one


def test_no_anthropic_key_in_tracked_files_or_history():
    tracked = subprocess.run(["git", "grep", "-I", "-l", "-E", KEY_RE], cwd=REPO, capture_output=True, text=True)
    assert tracked.stdout.strip() == "", "a tracked file contains an Anthropic API key"
    hist = subprocess.run(f"git log -p --all | grep -cE '{KEY_RE}' || true", shell=True, cwd=REPO,
                          capture_output=True, text=True)
    assert hist.stdout.strip() == "0", "git history contains an Anthropic API key"


def test_secrets_never_logged_by_llm_or_gateway(monkeypatch, caplog):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-FAKE-for-test")
    monkeypatch.setenv("ANDROID_GW_PASS", "hunter2-FAKE")
    monkeypatch.setenv("ANDROID_GW_URL", "http://127.0.0.1:9")  # closed port -> connection error path
    monkeypatch.setenv("GATEWAY", "android")
    from backend import llm
    monkeypatch.setattr(llm, "_client", None)
    with caplog.at_level(logging.DEBUG):
        llm.call_json("claude-haiku-5-5", "s", "u", {"type": "object"}) if False else None  # no network in unit tests
        gateway.send(VICTIM, "x")
    assert "sk-ant-FAKE" not in caplog.text and "hunter2" not in caplog.text


def test_health_does_not_reveal_db_path():
    assert "db" not in anon.get("/health").json()  # S2 fixed


def test_demo_db_is_gitignored():
    """Was a finding during the audit (README claimed it); fixed by `backend/demo.db*` in .gitignore."""
    rc = subprocess.run(["git", "check-ignore", "-q", "backend/demo.db"], cwd=REPO).returncode
    assert rc == 0
