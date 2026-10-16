import json
import os

import pytest

from backend import db, llm

TEST_TOKEN = "test-admin-token"
AUTH = {"X-API-Key": TEST_TOKEN}
ZWE_IDS = {u["name"]: u["id"] for u in db.geo_units("ZWE")}


def _row(t, level, event="crop_failure", p=0.5):
    return {"t": t, "level": level, "p": p, "confidence": "medium", "agreeing": 2,
            "families": {"rain": True, "vegetation": True, "soil": False, "heat": False},
            "event": event, "horizon": 8, "drivers": ["3-month rain index -1.4 (very dry)"], "signals": {}}


def make_risk(levels: dict, model_version="test-fixture", n=72):
    """levels: {name: {t: (level, event)}} -> risk dict (TEST FIXTURE, not model output)."""
    units = []
    for name, by_t in levels.items():
        series = [_row(t, *by_t.get(t, (0, "none"))) for t in range(n)]
        units.append({"id": ZWE_IDS[name], "name": name, "series": series})
    return {"meta": {"iso3": "ZWE", "country": "Zimbabwe", "start_year": 2019, "n_months": n,
                     "model_version": model_version}, "units": units}


def write_risk(dirpath, data, iso3="ZWE"):
    (dirpath / f"{iso3}.js").write_text(
        "// test fixture\nwindow.RISK_DATA = window.RISK_DATA || {};\n"
        f'RISK_DATA["{iso3}"] = {json.dumps(data)};\n')


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch, request):
    if "/conv/" in str(request.node.fspath):  # live suite talks HTTP to a running backend: real .env token
        yield tmp_path
        return
    db.reset_connections()
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("GATEWAY", "sim")
    monkeypatch.setenv("RISK_DIR", str(tmp_path))
    monkeypatch.setenv("ADMIN_TOKEN", TEST_TOKEN)
    monkeypatch.delenv("ANDROID_GW_SIGNING_KEY", raising=False)
    if "live" not in request.keywords:
        monkeypatch.setattr(llm, "call_json", lambda *a, **k: None)  # no network in unit tests
    yield tmp_path
    db.reset_connections()


@pytest.fixture
def fake_llm(monkeypatch):
    """Install a scripted Claude: fake_llm.set(fn(model, system, user, schema) -> dict)."""
    class F:
        calls = []

        def set(self, fn):
            def call(model, system, user, schema, max_tokens=1024):
                self.calls.append((model, user))
                return fn(model, system, user, schema)
            monkeypatch.setattr(llm, "call_json", call)
    return F()
