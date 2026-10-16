"""5. export_risk output matches CONTRACT.md section 3 exactly (synthetic run + the real data/risk file)."""
import json
import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from conftest import PIPE, make_long

ROOT = PIPE.parent
META_KEYS = {"iso3", "country", "start_year", "n_months", "live_t", "declaration", "model_version", "metrics", "generated_at"}
DECL_KEYS = {"t", "date", "label"}
UNIT_KEYS = {"id", "name", "urban", "series"}
ROW_KEYS = {"t", "level", "held", "watch_reason", "p", "p_crisis", "confidence", "agreeing", "families", "event", "horizon", "drivers", "signals", "forecast"}
FAM_KEYS = {"rain", "vegetation", "soil", "heat"}
SIG_KEYS = {"spi_1m", "spi_3m", "ndvi_z_crop", "ndvi_z_grass", "vci_crop", "vci_grass", "sm1_z", "t2m_z"}
EVENTS = {"none", "cant_plant", "crop_failure", "no_grass"}
DECL = {"ZWE": "2024-04-03", "KEN": "2021-09-08", "MWI": "2024-03-23", "ZMB": "2024-02-29"}


def isint(x):
    return isinstance(x, int) and not isinstance(x, bool)


def isnum(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and np.isfinite(x)


def validate(doc, iso3):
    errs = []
    E = errs.append
    if set(doc) != {"meta", "units"}:
        E(f"top-level keys {sorted(doc)}")
    m = doc["meta"]
    if set(m) != META_KEYS:
        E(f"meta keys: extra {sorted(set(m) - META_KEYS)} missing {sorted(META_KEYS - set(m))}")
    if m.get("iso3") != iso3: E("meta.iso3")
    if m.get("start_year") != 2019: E("meta.start_year != 2019")
    if not (isint(m.get("n_months")) and m["n_months"] >= 72): E("meta.n_months < 72")
    if not (m.get("live_t") is None or (isint(m["live_t"]) and 0 <= m["live_t"] < m["n_months"])): E(f"meta.live_t {m.get('live_t')}")
    d = m.get("declaration", {})
    if set(d) != DECL_KEYS: E(f"declaration keys {sorted(d)}")
    if d.get("date") != DECL[iso3]: E(f"declaration.date {d.get('date')}")
    dt = pd.Timestamp(DECL[iso3])
    if d.get("t") != (dt.year - 2019) * 12 + dt.month - 1: E(f"declaration.t {d.get('t')}")
    if not isinstance(m.get("metrics"), dict): E("meta.metrics not object")
    if not isinstance(m.get("model_version"), str): E("model_version not str")
    try:
        pd.Timestamp(m.get("generated_at"))
    except Exception:
        E("generated_at not ISO")
    n = m.get("n_months", 72)
    # declaration in force: declaration month .. end of that agricultural year (June)
    d_t = (dt.year - 2019) * 12 + dt.month - 1
    ag_end_t = ((dt.year if dt.month <= 6 else dt.year + 1) - 2019) * 12 + 5
    ids = [u.get("id") for u in doc["units"]]
    if len(ids) != len(set(ids)): E("duplicate unit ids")
    for u in doc["units"]:
        if set(u) != UNIT_KEYS: E(f"unit {u.get('id')} keys {sorted(u)}"); continue
        if not isinstance(u["urban"], bool): E(f"unit {u['id']} urban not bool")
        if not isinstance(u["name"], str): E(f"unit {u['id']} name")
        s = u["series"]
        if len(s) != n: E(f"unit {u['id']} series length {len(s)}"); continue
        prev = None
        for i, r in enumerate(s):
            tag = f"unit {u['id']} t={i}"
            if set(r) != ROW_KEYS:
                E(f"{tag} keys extra {sorted(set(r) - ROW_KEYS)} missing {sorted(ROW_KEYS - set(r))}"); break
            if r["t"] != i: E(f"{tag} t={r['t']}")
            if not (isint(r["level"]) and 0 <= r["level"] <= 3): E(f"{tag} level {r['level']}")
            if not isinstance(r["held"], bool): E(f"{tag} held {r['held']!r} not bool")
            if r["held"] and r["level"] == 0: E(f"{tag} held at level 0")
            if (r["watch_reason"] is None) != (r["level"] == 0): E(f"{tag} watch_reason {r['watch_reason']!r} at level {r['level']}")
            if r["level"] >= 2 and r["watch_reason"] != "district_evidence": E(f"{tag} Warning+ not district_evidence")
            for pk in ("p", "p_crisis"):      # contract: 0-1 or null (missing is missing)
                if not (r[pk] is None or (isnum(r[pk]) and 0 <= r[pk] <= 1)): E(f"{tag} {pk} {r[pk]}")
            if r["confidence"] not in ("low", "medium", "high"): E(f"{tag} confidence {r['confidence']}")
            f = r["families"]
            if set(f) != FAM_KEYS or not all(isinstance(v, bool) for v in f.values()):
                E(f"{tag} families {f}"); break
            core = f["rain"] + f["vegetation"] + f["soil"]
            if not isint(r["agreeing"]) or r["agreeing"] != core:
                E(f"{tag} agreeing {r['agreeing']} != core families {core}")
            if r["event"] not in EVENTS: E(f"{tag} event {r['event']}")
            if r["level"] > 0 and r["event"] == "none": E(f"{tag} level>0 but event none")
            if not (isint(r["horizon"]) and r["horizon"] >= 0): E(f"{tag} horizon {r['horizon']}")
            dr = r["drivers"]
            if not (isinstance(dr, list) and len(dr) <= 3 and all(isinstance(x, str) for x in dr)):
                E(f"{tag} drivers {dr}")
            sg = r["signals"]
            if set(sg) != SIG_KEYS: E(f"{tag} signal keys {sorted(sg)}")
            elif not all(v is None or isnum(v) for v in sg.values()): E(f"{tag} signal values {sg}")
            fc = r["forecast"]                 # CONTRACT section 4
            if not ({"1", "2", "3"} <= set(fc) <= {str(x) for x in range(1, 9)}): E(f"{tag} forecast keys {sorted(fc)}")
            else:
                for L, v in fc.items():
                    if not ({"p", "p_crisis", "target_label"} <= set(v) <= {"p", "p_crisis", "target_label", "fews_phase",
                            "fews_scenario", "fews_published", "source"}) or not isinstance(v["target_label"], str):
                        E(f"{tag} forecast[{L}] {v}"); break
                    for pk in ("p", "p_crisis"):
                        if not (v[pk] is None or (isnum(v[pk]) and 0 <= v[pk] <= 1)): E(f"{tag} forecast[{L}].{pk} {v[pk]}")
            if r["level"] == 3 and not (d_t <= i <= ag_end_t):
                E(f"{tag} Emergency outside declaration season (t {d_t}..{ag_end_t}), held={r['held']}")
            # a rise to Warning+ needs this month's raw level >= 2, so the 2-family rule must hold now
            if prev is not None and r["level"] >= 2 and r["level"] > prev["level"]:
                if not (f["vegetation"] and (f["rain"] or f["soil"])):
                    E(f"{tag} rose to level {r['level']} without vegetation+(rain|soil): {f}")
            prev = r
        if len(errs) > 50:
            break
    return errs


def load_js(path: Path, iso3: str):
    txt = path.read_text()
    mm = re.search(r'RISK_DATA\["%s"\]\s*=\s*(\{.*\})\s*;?\s*$' % iso3, txt, re.S)
    assert mm, "RISK_DATA assignment not found"
    assert "window.RISK_DATA = window.RISK_DATA || {};" in txt
    return json.loads(mm.group(1), parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))


# ------------------------------------------------------------------ synthetic export
@pytest.fixture(scope="module")
def synthetic_doc(tmp_path_factory):
    import train as T
    import export_risk as X
    d = tmp_path_factory.mktemp("exp")
    (d / "data").mkdir()
    make_long(n_units=3, seed=2).to_parquet(d / "data" / "signals_ZWE.parquet")
    T.run(["ZWE"], d / "data", d / "out", "T")
    bundle = joblib.load(d / "out" / "model_T.joblib")
    doc = X.build("ZWE", bundle, d / "data", d / "out" / "metrics_ZWE.json")
    # round-trip through the same serialisation main() uses
    return json.loads(json.dumps(doc, separators=(",", ":"), allow_nan=False))


def test_synthetic_export_matches_contract(synthetic_doc):
    errs = validate(synthetic_doc, "ZWE")
    assert not errs, "\n".join(errs[:20])
    assert synthetic_doc["meta"]["model_version"] != "STUB"


# ------------------------------------------------------------------ real file
REAL = ROOT / "data" / "risk" / "ZWE.js"


def test_real_zwe_risk_file():
    if not REAL.exists():
        pytest.skip("data/risk/ZWE.js missing")
    doc = load_js(REAL, "ZWE")
    if doc["meta"].get("model_version") == "STUB":
        pytest.skip("data/risk/ZWE.js is still the STUB")
    errs = validate(doc, "ZWE")
    assert not errs, "\n".join(errs[:20])
    assert doc["meta"]["metrics"].get("fast_entry") in (False, None), "real export built with fast entry"
