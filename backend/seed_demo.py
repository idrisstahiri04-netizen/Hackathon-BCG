"""Seed a few demo subscribers so the feed is not empty (default ZWE; --iso3 KEN = Kenya demo, West Pokot).

Numbers +2126000000xx are FAKE placeholders (Moroccan mobile format, team test range).
Replace with real team test phones only in a local .env-driven run, never commit them.
Idempotent: re-running updates the same rows (keyed on phone).

    python -m backend.seed_demo [--iso3 KEN]
"""
from __future__ import annotations

import argparse

from . import db

# (phone, name, district, role, language)
SEED_ZWE = [
    ("+212600000001", "Demo Farmer Binga", "Binga", "farmer", "en"),
    ("+212600000002", "Demo Herder Hwange", "Hwange", "herder", "en"),
    ("+212600000003", "Demo Farmer Mbire", "Mbire", "farmer", "fr"),
    ("+212600000004", "Demo Officer Gokwe N", "Gokwe North", "officer", "en"),
    ("+212600000005", "Demo NGO Kariba", "Kariba", "ngo", "en"),
    ("+212600000006", "Demo Resident Muzarabani", "Centenary/ Muzarabani", "resident", "en"),
    ("+212600000007", "Demo Farmer Hurungwe", "Hurungwe", "farmer", "en"),
    ("+212600000008", "Demo Herder Binga", "Binga", "herder", "en"),
]

# Kenya demo: West Pokot herder Warning (no_grass) in Sep 2026 (t=92). Swahili texts need native review.
SEED_KEN = [
    ("+212600000001", "Demo Herder West Pokot", "West Pokot", "herder", "sw"),
    ("+212600000002", "Demo Farmer West Pokot", "West Pokot", "farmer", "en"),
    ("+212600000003", "Demo Herder Turkana", "Turkana", "herder", "sw"),
    ("+212600000004", "Demo Officer West Pokot", "West Pokot", "officer", "en"),
    ("+212600000005", "Demo NGO Marsabit", "Marsabit", "ngo", "en"),
    ("+212600000006", "Demo Resident Kilifi", "Kilifi", "resident", "sw"),
    ("+212600000007", "Demo Farmer Kilifi", "Kilifi", "farmer", "sw"),
    ("+212600000008", "Demo Herder Wajir", "Wajir", "herder", "en"),
]
SEEDS = {"ZWE": SEED_ZWE, "KEN": SEED_KEN}
SEED = SEED_ZWE  # default country (kept for tests)


def seed(iso3: str = "ZWE") -> int:
    units = {u["name"]: u for u in db.geo_units(iso3)}
    n = 0
    for phone, name, district, role, lang in SEEDS[iso3]:
        u = units.get(district)
        if not u:
            raise SystemExit(f"district {district!r} not in data/geo/{iso3}.js")
        existing = db.get_user(phone)
        db.upsert_user(phone, name=name, district_id=u["id"], district_name=u["name"], iso3=iso3,
                       role=role, language=lang,
                       consent_at=(existing or {}).get("consent_at") or db.now_iso(),
                       raw_signup_text="SEED demo placeholder (fake number)")
        n += 1
    # one national NGO subscriber (no district = all districts)
    db.upsert_user("+212600000009", name="Demo NGO national", district_id=None, district_name=None,
                   iso3=iso3, role="ngo", language="en",
                   consent_at=(db.get_user("+212600000009") or {}).get("consent_at") or db.now_iso(),
                   raw_signup_text="SEED demo placeholder (fake number)")
    return n + 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso3", default="ZWE", choices=sorted(SEEDS))
    a = ap.parse_args()
    print(f"seeded {seed(a.iso3)} demo users ({a.iso3}) into {db.db_path()}")
