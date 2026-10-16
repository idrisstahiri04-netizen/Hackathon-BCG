"""Seed a few demo subscribers in northern Zimbabwe so the feed is not empty.

Numbers +2126000000xx are FAKE placeholders (Moroccan mobile format, team test range).
Replace with real team test phones only in a local .env-driven run, never commit them.
Idempotent: re-running updates the same rows (keyed on phone).

    python -m backend.seed_demo
"""
from __future__ import annotations

from . import db

# (phone, name, district, role, language)
SEED = [
    ("+212600000001", "Demo Farmer Binga", "Binga", "farmer", "en"),
    ("+212600000002", "Demo Herder Hwange", "Hwange", "herder", "en"),
    ("+212600000003", "Demo Farmer Mbire", "Mbire", "farmer", "fr"),
    ("+212600000004", "Demo Officer Gokwe N", "Gokwe North", "officer", "en"),
    ("+212600000005", "Demo NGO Kariba", "Kariba", "ngo", "en"),
    ("+212600000006", "Demo Resident Muzarabani", "Centenary/ Muzarabani", "resident", "en"),
    ("+212600000007", "Demo Farmer Hurungwe", "Hurungwe", "farmer", "en"),
    ("+212600000008", "Demo Herder Binga", "Binga", "herder", "en"),
]


def seed() -> int:
    units = {u["name"]: u for u in db.geo_units("ZWE")}
    n = 0
    for phone, name, district, role, lang in SEED:
        u = units.get(district)
        if not u:
            raise SystemExit(f"district {district!r} not in data/geo/ZWE.js")
        existing = db.get_user(phone)
        db.upsert_user(phone, name=name, district_id=u["id"], district_name=u["name"], iso3="ZWE",
                       role=role, language=lang,
                       consent_at=(existing or {}).get("consent_at") or db.now_iso(),
                       raw_signup_text="SEED demo placeholder (fake number)")
        n += 1
    # one national NGO subscriber (no district = all ZWE districts)
    db.upsert_user("+212600000009", name="Demo NGO national", district_id=None, district_name=None,
                   iso3="ZWE", role="ngo", language="en",
                   consent_at=(db.get_user("+212600000009") or {}).get("consent_at") or db.now_iso(),
                   raw_signup_text="SEED demo placeholder (fake number)")
    return n + 1


if __name__ == "__main__":
    print(f"seeded {seed()} demo users into {db.db_path()}")
