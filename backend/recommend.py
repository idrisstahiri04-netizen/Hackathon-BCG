"""Deterministic recommendation engine (no LLM). Library: backend/recommendations.yaml.

Warning (L2) -> preparatory actions, Emergency (L3) -> response actions.
Event decides livestock vs crop. Drivers refine the rank. Farmers/herders get one short action,
never a probability. DEMO CONTENT, to be validated with NDMA / WHH.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

AUDIENCES = ["herder", "farmer", "resident", "ngo", "officer", "foodbank"]
PATH = Path(__file__).with_name("recommendations.yaml")
DRIVER_WORDS = {"rain": ("rain", "spi", "precip"), "veg": ("green", "vci", "ndvi", "vegetation", "grass"),
                "heat": ("hot", "temperature", "heat"), "soil": ("soil", "moisture"),
                "fews": ("fews", "ipc", "crisis"), "price": ("price", "market")}


@lru_cache(maxsize=1)
def _lib() -> dict:
    return yaml.safe_load(PATH.read_text(encoding="utf-8"))


def livelihood_for(event: str | None, livelihood: str | None = None) -> str:
    if livelihood in ("pastoral", "agro-pastoral", "agricultural"):
        return livelihood
    return "pastoral" if event == "no_grass" else "agricultural"


def _tags(drivers: list[str] | None) -> set[str]:
    txt = " ".join(drivers or []).lower()
    return {k for k, ws in DRIVER_WORDS.items() if any(w in txt for w in ws)}


def recommend(alert: dict, per_audience: int = 3) -> list[dict]:
    """alert: iso3, county, level, event, drivers, season, p_crisis, livelihood. Returns ranked list."""
    level = int(alert.get("level") or 0)
    if level < 2:
        return []
    phase = "respond" if level >= 3 else "prepare"
    event = alert.get("event") or "none"
    ev_key = "any" if event == "none" else event
    live = livelihood_for(alert.get("event"), alert.get("livelihood"))
    tags = _tags(alert.get("drivers"))
    lib = _lib()
    out = []
    for it in lib["items"]:
        if it["phase"] not in (phase, "both"):
            continue
        evs = it["events"]
        if ev_key not in evs and "any" not in evs:
            continue
        score = it.get("priority", 5) * 10 - 3 * len(tags & set(it.get("drivers") or []))
        if ev_key in evs:
            score -= 2  # exact event match beats generic
        # livelihood: pastoral and agro-pastoral households also get the other group's top item
        if it["audience"] == "farmer" and live == "pastoral":
            score += 20
        if it["audience"] == "herder" and live == "agricultural" and ev_key != "no_grass":
            score += 20
        out.append((score, it))
    out.sort(key=lambda x: (x[0], x[1]["id"]))
    res, count = [], {}
    for rank, (score, it) in enumerate(out):
        a = it["audience"]
        if count.get(a, 0) >= per_audience:
            continue
        count[a] = count.get(a, 0) + 1
        src = lib["sources"].get(it["source"], it["source"])
        d = {"id": it["id"], "audience": a, "action": it["action"], "detail": it.get("detail") or it["action"],
             "priority": count[a], "source": src, "phase": phase}
        if it.get("action_sw"):
            d["action_sw"] = it["action_sw"]
        res.append(d)
    return res


def top_action(recs: list[dict], role: str, lang: str = "en") -> str | None:
    """Top one-line action for a role (farmer/herder), in en or sw. None if nothing."""
    for r in recs:
        if r["audience"] == role:
            return (r.get("action_sw") if (lang or "en").startswith("sw") else None) or r["action"]
    return None


# ---------------------------------------------------------------- role actions (gov / ngo)
ROLES = ["gov", "ngo"]
_TOK = __import__("re").compile(r"\{(\w+)\}")
FEWS_PHASE = {1: "Minimal", 2: "Stressed", 3: "Crisis", 4: "Emergency", 5: "Famine"}


def _fill(tpl: str, ctx: dict) -> str | None:
    """Fill {tokens}; None if any token is missing (missing is missing, not zero)."""
    if any(ctx.get(t) is None for t in _TOK.findall(tpl)):
        return None
    return _TOK.sub(lambda m: str(ctx[m.group(1)]), tpl)


def _ctx(alert: dict) -> dict:
    pop, n_hit, n_units = alert.get("pop"), alert.get("n_hit"), alert.get("n_units")
    pc = alert.get("p_crisis")
    return {
        "name": alert.get("county") or alert.get("name") or "this unit",
        "pop": f"{int(pop):,}" if pop else None,
        "ration_t": f"{round(pop * 15 / 1000):,}" if pop else None,
        "n_hit": n_hit, "n_units": n_units,
        "pct_units": round(100 * n_hit / n_units) if n_units and n_hit is not None else None,
        "unit_word": alert.get("unit_word") or "units",
        "chance": round(pc * 100) if pc is not None else None,
    }


def evidence(alert: dict) -> str:
    c = _ctx(alert)
    lvl = int(alert.get("level") or 0)
    parts = [f"{c['name']} at {'Emergency' if lvl >= 3 else 'Warning'} (L{lvl})"]
    if c["chance"] is not None:
        parts.append(f"{c['chance']}% chance of IPC 3+ in the next 3 months")
    fp = alert.get("fews_phase")
    if fp:
        parts.append(f"FEWS NET projects IPC {int(fp)} ({FEWS_PHASE.get(int(fp), '')})")
    if alert.get("drivers"):
        parts.append("drivers: " + "; ".join(alert["drivers"][:3]))
    return ". ".join(parts) + "."


def role_recommend(alert: dict, role: str, limit: int = 5) -> list[dict]:
    """Objective, actionable advice for one role (gov|ngo). [] below Warning."""
    level = int(alert.get("level") or 0)
    if level < 2 or role not in ROLES:
        return []
    phase = "respond" if level >= 3 else "prepare"
    ev = alert.get("event") or "none"
    ev_key = "any" if ev == "none" else ev
    lib = _lib()
    ctx, evid, out = _ctx(alert), evidence(alert), []
    for it in sorted(lib["role_actions"], key=lambda i: (i["priority"], i["id"])):
        if it["role"] != role or it["phase"] not in (phase, "both"):
            continue
        if ev_key not in it["events"] and "any" not in it["events"]:
            continue
        out.append({"id": it["id"], "role": role, "phase": phase, "verb": it["verb"],
                    "action": _fill(it["action"], ctx), "who": it["who"], "when": it["when"],
                    "quantity": _fill(it.get("quantity", ""), ctx) if it.get("quantity") else None,
                    "evidence": evid, "source": lib["sources"].get(it["source"], it["source"]),
                    "note": lib["role_note"]})
    return [r for r in out if r["action"]][:limit]
