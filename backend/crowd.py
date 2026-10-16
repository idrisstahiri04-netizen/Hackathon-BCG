"""Crowd signal: aggregate inbound 1/2/3 reports per district (spec signal_type crowd_crop_status).

Spec: "share of inbound reports in a unit saying 2 or 3"; "inbound reports weighted, checked
against satellite signal, never the sole trigger".

Rules implemented here (display-level only; the exported model levels are never changed):
- window: last WINDOW_DAYS days (default 30)
- only users with consent_at set and opted_out_at NULL, with a known district
- anti-gaming: one report per user per DEDUP_DAYS (7) counts; the newest in each window wins
- no phone numbers or names leave this module: output is per unit only
- crowd rule (apply_rule): displayed level may go up by +1 (max Warning, never Emergency) ONLY if
  share_bad >= MIN_SHARE_BAD with n_reports >= MIN_REPORTS AND the unit's exported row already has
  at least one satellite family in alarm (vegetation, rain or soil). Heat alone does not count.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from . import db

WINDOW_DAYS = 30
DEDUP_DAYS = 7
MIN_REPORTS = 3
MIN_SHARE_BAD = 0.6
SAT_FAMILIES = ("vegetation", "rain", "soil")
MAX_DISPLAY_LEVEL = 2  # Warning; crowd never makes an Emergency


def _parse_ts(s: str) -> datetime:
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _report_value(parsed_json: str | None) -> int | None:
    try:
        v = (json.loads(parsed_json or "{}") or {}).get("report_value")
        v = int(v)
    except (TypeError, ValueError):
        return None
    return v if v in (1, 2, 3) else None


def _is_demo(parsed_json: str | None) -> bool:
    try:
        return bool((json.loads(parsed_json or "{}") or {}).get("demo"))
    except ValueError:
        return False


def raw_reports(iso3: str, days: int = WINDOW_DAYS, now: datetime | None = None) -> list[dict]:
    """Consented, not-opted-out users' inbound reports in the window. One row per message."""
    now = now or datetime.now(timezone.utc)
    cut = (now - timedelta(days=days)).replace(microsecond=0).isoformat()
    rows = db.q(
        "SELECT m.id, m.created_at, m.user_id, m.parsed_json, u.district_id, u.district_name "
        "FROM messages m JOIN users u ON u.id = m.user_id "
        "WHERE m.direction='in' AND m.intent='report' AND m.created_at >= ? "
        "AND u.consent_at IS NOT NULL AND u.opted_out_at IS NULL "
        "AND u.district_id IS NOT NULL AND upper(u.iso3) = ? "
        "ORDER BY m.user_id, m.created_at DESC, m.id DESC",
        (cut, iso3.upper()))
    out = []
    for r in rows:
        v = _report_value(r["parsed_json"])
        if v is None:
            continue
        r["value"] = v
        r["demo"] = _is_demo(r["parsed_json"])
        out.append(r)
    return out


def dedup(reports: list[dict], dedup_days: int = DEDUP_DAYS) -> list[dict]:
    """Anti-gaming: per user keep the newest report, then only reports >= dedup_days older than
    the last kept one. Input must be sorted by user, newest first."""
    kept: list[dict] = []
    last_by_user: dict[int, datetime] = {}
    for r in reports:
        ts = _parse_ts(r["created_at"])
        prev = last_by_user.get(r["user_id"])
        if prev is not None and (prev - ts) < timedelta(days=dedup_days):
            continue
        last_by_user[r["user_id"]] = ts
        kept.append(r)
    return kept


def aggregate(iso3: str, days: int = WINDOW_DAYS, now: datetime | None = None) -> list[dict]:
    """Per unit: n_reports, n_bad (2 or 3), n_failed (3), share_bad, share_failed, last_report_at,
    n_demo, n_users. No phones, no names."""
    per: dict[str, dict] = {}
    for r in dedup(raw_reports(iso3, days, now)):
        u = per.setdefault(r["district_id"], {
            "unit_id": r["district_id"], "unit_name": r["district_name"],
            "n_reports": 0, "n_bad": 0, "n_failed": 0, "n_demo": 0,
            "last_report_at": None, "_users": set()})
        u["n_reports"] += 1
        u["n_bad"] += r["value"] >= 2
        u["n_failed"] += r["value"] == 3
        u["n_demo"] += bool(r["demo"])
        u["_users"].add(r["user_id"])
        if u["last_report_at"] is None or r["created_at"] > u["last_report_at"]:
            u["last_report_at"] = r["created_at"]
    out = []
    for u in per.values():
        n = u["n_reports"]
        u["n_users"] = len(u.pop("_users"))
        u["share_bad"] = round(u["n_bad"] / n, 3) if n else None
        u["share_failed"] = round(u["n_failed"] / n, 3) if n else None
        out.append(u)
    out.sort(key=lambda x: (-(x["share_bad"] or 0), -x["n_reports"], x["unit_name"] or ""))
    return out


def crowd_alarm(stats: dict) -> bool:
    """True when the crowd itself is in alarm (enough reports, enough of them bad)."""
    n = int(stats.get("n_reports") or 0)
    s = stats.get("share_bad")
    return n >= MIN_REPORTS and s is not None and float(s) >= MIN_SHARE_BAD


def apply_rule(level: int | None, families: dict | None, stats: dict) -> dict:
    """Display-level rule. Returns {display_level, crowd_confirmed, crowd_alarm, sat_alarm, reason}.
    Missing level (None) stays missing: crowd never invents a level."""
    fam = families or {}
    sat = any(bool(fam.get(k)) for k in SAT_FAMILIES)
    alarm = crowd_alarm(stats)
    if level is None:
        return {"display_level": None, "crowd_confirmed": False, "crowd_alarm": alarm, "sat_alarm": sat,
                "reason": "no model level"}
    lvl = int(level)
    if not alarm:
        return {"display_level": lvl, "crowd_confirmed": False, "crowd_alarm": False, "sat_alarm": sat,
                "reason": f"crowd below threshold (need >= {MIN_REPORTS} reports and share_bad >= {MIN_SHARE_BAD})"}
    if not sat:
        return {"display_level": lvl, "crowd_confirmed": False, "crowd_alarm": True, "sat_alarm": False,
                "reason": "no satellite family in alarm: crowd is never the sole trigger"}
    if lvl >= MAX_DISPLAY_LEVEL:
        return {"display_level": lvl, "crowd_confirmed": True, "crowd_alarm": True, "sat_alarm": True,
                "reason": "already at Warning or above: crowd confirms, no raise"}
    return {"display_level": lvl + 1, "crowd_confirmed": True, "crowd_alarm": True, "sat_alarm": True,
            "reason": "crowd + satellite agree: displayed level +1"}


def with_rule(units: list[dict], iso3: str, t: int) -> list[dict]:
    """Annotate aggregated units with the rule result for month t of data/risk/<ISO3>.js.
    If the risk file is missing or a STUB, units get model_level=None and no raise."""
    try:
        risk = db.load_risk(iso3)
    except db.RiskFileError:
        risk = {"units": []}
    rows = {u["id"]: {r["t"]: r for r in u.get("series", [])} for u in risk.get("units", [])}
    for u in units:
        row = rows.get(u["unit_id"], {}).get(t) or {}
        lvl = row.get("level")
        res = apply_rule(lvl, row.get("families"), u)
        u.update(model_level=lvl, t=t, **res)
    return units
