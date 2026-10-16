"""Seed DEMO crowd reports in one district so the crowd signal can be shown on stage.

Creates 4 fake users (+2126000001xx, FAKE Moroccan-format placeholders, name "Demo crowd ...",
raw_signup_text "SEED crowd demo") in one district and one inbound report each, 2 x "1" (ok) and
2 x "3" (failed). That is share_bad = 0.50, just under the 0.60 threshold, so the live jury reply
"3" from a real subscriber in the same district tips the district over (3 of 5 = 0.60).

Every seeded message carries parsed_json {"demo": true, "source": "seed_crowd"} so the UI can
label them as demo. Idempotent: re-running refreshes the same 4 reports (no duplicates).

    python -m backend.seed_crowd                 # default district (Hurungwe: Watch + satellite alarm Apr 2024)
    python -m backend.seed_crowd --district Kariba
    python -m backend.seed_crowd --clear         # remove the demo reports and users
"""
from __future__ import annotations

import argparse
import json

from . import db

DEFAULT_DISTRICT = "Hurungwe"
SEED_TAG = "seed_crowd"
# (phone, name, role, report value)
SEED = [
    ("+212600000101", "Demo crowd farmer 1", "farmer", 1),
    ("+212600000102", "Demo crowd farmer 2", "farmer", 3),
    ("+212600000103", "Demo crowd herder 1", "herder", 1),
    ("+212600000104", "Demo crowd farmer 3", "farmer", 3),
]
LABEL = {1: "ok", 2: "poor", 3: "failed"}


def clear() -> int:
    n = 0
    for phone, *_ in SEED:
        u = db.get_user(phone)
        if not u:
            continue
        n += db.connect().execute("DELETE FROM messages WHERE user_id=? AND json_extract(parsed_json,'$.source')=?",
                                  (u["id"], SEED_TAG)).rowcount
        db.ex("DELETE FROM users WHERE id=?", (u["id"],))
    return n


def seed(district: str = DEFAULT_DISTRICT, iso3: str = "ZWE") -> dict:
    units = {u["name"].lower(): u for u in db.geo_units(iso3)}
    unit = units.get(district.lower())
    if not unit:
        raise SystemExit(f"district {district!r} not in data/geo/{iso3}.js")
    now = db.now_iso()
    n = 0
    for phone, name, role, value in SEED:
        existing = db.get_user(phone)
        uid = db.upsert_user(phone, name=name, district_id=unit["id"], district_name=unit["name"], iso3=iso3,
                             role=role, language="en",
                             consent_at=(existing or {}).get("consent_at") or now,
                             raw_signup_text="SEED crowd demo (fake number, demo report)")
        # refresh: one demo report per user, never duplicated
        db.connect().execute("DELETE FROM messages WHERE user_id=? AND json_extract(parsed_json,'$.source')=?",
                             (uid, SEED_TAG))
        parsed = {"intent": "report", "report_value": value, "confidence": 1.0,
                  "source": SEED_TAG, "demo": True, "label": f"DEMO {LABEL[value]}"}
        db.log_message("in", phone, str(value), user_id=uid, intent="report", intent_confidence=1.0,
                       parsed_json=json.dumps(parsed), status="received", created_at=now)
        n += 1
    return {"district": unit["name"], "unit_id": unit["id"], "reports": n,
            "share_bad": sum(v >= 2 for *_, v in SEED) / len(SEED)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--district", default=DEFAULT_DISTRICT)
    ap.add_argument("--iso3", default="ZWE")
    ap.add_argument("--clear", action="store_true")
    a = ap.parse_args()
    if a.clear:
        print(f"removed {clear()} demo crowd reports from {db.db_path()}")
    else:
        r = seed(a.district, a.iso3)
        print(f"seeded {r['reports']} DEMO crowd reports in {r['district']} (share_bad {r['share_bad']:.2f}, "
              f"one more '3' tips it to >= 0.60) into {db.db_path()}")
