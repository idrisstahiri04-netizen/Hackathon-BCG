"""Shared helpers for the security audit tests (pipeline/audit/security.md).

The tests in this folder never edit backend source. Tests that FAIL today because of
a documented finding are marked xfail(strict=True) with the finding id, so the suite is
green now and turns red (XPASS) the moment the fix lands, telling you to drop the marker.
"""
from __future__ import annotations

import re

from backend import composer, db, router

VICTIM = "+263771000001"
ATTACKER = "+263771000002"


def llm_result(**kw) -> dict:
    """A well-formed router JSON (what Claude Haiku returns), overridable per field."""
    base = {"intent": "unknown", "confidence": 0.95, "language": "en", "district": None,
            "role": None, "name": None, "report_value": None}
    base.update(kw)
    return base


def register_victim(role: str = "farmer", district: str = "Binga") -> dict:
    ids = {u["name"]: u["id"] for u in db.geo_units("ZWE")}
    db.upsert_user(VICTIM, name="Victim", role=role, iso3="ZWE", district_id=ids[district],
                   district_name=district, consent_at=db.now_iso())
    return db.get_user(VICTIM)


def outbound_to(phone: str) -> list[dict]:
    return db.q("SELECT * FROM messages WHERE direction='out' AND phone=? ORDER BY id", (phone,))


def outbound_not_to(phone: str) -> list[dict]:
    return db.q("SELECT * FROM messages WHERE direction='out' AND phone!=? ORDER BY id", (phone,))


def n_events() -> int:
    return db.q1("SELECT COUNT(*) n FROM events")["n"]


# ----------------------------------------------------------------- allowed reply set
def _template_regexes() -> list[re.Pattern]:
    """Every fixed reply template, with {placeholders} turned into wildcards."""
    out = []
    for lang in router.R.values():
        for tpl in lang.values():
            pat = re.escape(composer.gsm_safe(tpl))
            pat = re.sub(r"\\\{[a-z_]+\\\}", ".{0,80}", pat)
            out.append(re.compile("^" + pat + r"(\.\.\.)?$", re.S))
    return out


_TEMPLATES = _template_regexes()
_ADVICE = {composer.fit(e["text"]) for e in router.load_advice()}


def reply_is_approved(reply: str) -> bool:
    """True if the outbound text is a fixed template or an advice.yaml entry (nothing invented)."""
    if reply in _ADVICE:
        return True
    return any(p.match(reply) for p in _TEMPLATES)
