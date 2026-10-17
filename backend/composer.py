"""Match an event to users and compose one-segment SMS (GSM-7, <=160 chars).

Audience rules (API.md / spec): only Warning (orange) and Emergency (red) are notified.
  Watch (1)      -> nobody (shown in the UI and the alert log only)
  Warning (2)    -> ngo, officer + farmer (crop events: cant_plant, crop_failure, none) or herder (no_grass)
  Emergency (3)  -> everyone subscribed in the district: ngo, officer, farmer, herder, resident
Farmer/herder SMS carry the top recommended action of backend/recommend.py when it fits one segment.
Farmers, herders and residents get an action, never a probability. NGO gets p + drivers.
Skips opted-out users, users without consent, duplicates, and users over the monthly cap.
"""
from __future__ import annotations

import json
import os
import sqlite3
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import db, gateway, recommend

GSM7 = set("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡"
           "ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà")
GSM7_EXT = set("^{}\\[~]|€")  # count as 2 chars
LEVELS = {0: "NORMAL", 1: "WATCH", 2: "WARNING", 3: "EMERGENCY"}
LEVELS_FR = {0: "NORMAL", 1: "VIGILANCE", 2: "ALERTE", 3: "URGENCE"}
LEVELS_SW = {0: "KAWAIDA", 1: "TAHADHARI", 2: "ONYO", 3: "DHARURA"}  # needs native review
EVENT_LABEL = {"cant_plant": "Can't plant", "crop_failure": "Crop failure", "no_grass": "No grass",
               "none": "Drought risk"}
CROP_EVENTS = {"cant_plant", "crop_failure", "none", None}
MAX_LEN = 160


def gsm_safe(s: str) -> str:
    """Map text to the GSM-7 alphabet (curly quotes, dashes, unsupported accents)."""
    s = (str(s).replace("‘", "'").replace("’", "'").replace("“", '"')
         .replace("”", '"').replace("–", "-").replace("—", "-").replace("…", "..."))
    out = []
    for ch in s:
        if ch in GSM7 or ch in GSM7_EXT:
            out.append(ch)
        else:
            base = unicodedata.normalize("NFD", ch)[0]
            out.append(base if base in GSM7 else "")
    return "".join(out)


def gsm_len(s: str) -> int:
    return sum(2 if c in GSM7_EXT else 1 for c in s)


def is_gsm7(s: str) -> bool:
    return all(c in GSM7 or c in GSM7_EXT for c in s)


def fit(s: str, limit: int = MAX_LEN) -> str:
    s = gsm_safe(s)
    if gsm_len(s) <= limit:
        return s
    return s[: limit - 3].rstrip() + "..."


# ------------------------------------------------------------------ templates
def audiences(level: int, event: str | None) -> list[str]:
    out = []
    if level >= 2:
        out += ["ngo", "officer"]
    if level >= 3:  # Emergency: everyone subscribed in the district (spec)
        return out + ["farmer", "herder", "resident"]
    if level >= 2:  # Warning: event-specific
        out.append("herder" if event == "no_grass" else "farmer")
    return out


def compose(role: str, ev: dict, language: str = "en") -> str:
    """ev: dict with unit_name, level, event, p, drivers (list), horizon, agreeing, confidence."""
    level = int(ev["level"])
    fr = (language or "en").startswith("fr") and role in ("farmer", "herder", "resident")
    sw = (language or "en").startswith("sw") and role in ("farmer", "herder", "resident")
    L = (LEVELS_SW if sw else LEVELS_FR if fr else LEVELS)[level]
    em = level >= 3
    event = ev.get("event") or "none"
    drivers = ev.get("drivers") or []

    def build(name: str) -> str:
        if sw:  # Swahili, needs native review before real use. GSM-7 only, one segment.
            tail = "Jibu 1 sawa 2 hafifu 3 {x}. ACHA kujiondoa"
            if role == "farmer":
                if event == "cant_plant" and not em:
                    return f"{L} {name}: mvua ni hafifu. Subiri mvua nzuri 2 kabla ya kupanda, tumia mbegu za muda mfupi. " + tail.format(x="imeharibika")
                return (f"{L} {name}: mazao yameharibika. Weka nafaka yako, usiuze mifugo kwa bei ndogo. " + tail.format(x="imeharibika") if em else
                        f"{L} {name}: mazao yanakauka. Weka nafaka ya miezi 2, usiuze kwa bei ndogo. " + tail.format(x="imeharibika"))
            if role == "herder":
                return (f"{L} {name}: malisho yameisha. Uza mifugo dhaifu sasa, weka wazazi, peleka mifugo penye maji. " + tail.format(x="mbaya") if em else
                        f"{L} {name}: malisho yanakauka haraka. Uza mifugo dhaifu mapema bei ikiwa nzuri, panga kuhamisha. " + tail.format(x="mbaya"))
            return f"{L} {name}: ukame, chakula kinaweza kupungua. Weka maji safi, jisajili kwa kamati ya chakula. Jibu MSAADA. ACHA kujiondoa"
        if role == "farmer":
            if fr:
                if event == "cant_plant" and not em:
                    return f"{L} {name}: pluies faibles. Attendez 2 bonnes pluies avant de semer, semence a cycle court. Repondez 1 ok 2 moyen 3 perdu. STOP pour arreter"
                if em and event == "no_grass":
                    return f"{L} {name}: grave secheresse. Gardez vos grains pour la famille, ne bradez pas vos animaux. Repondez 1 ok 2 moyen 3 perdu. STOP pour arreter"
                return (f"{L} {name}: recolte perdue. Gardez vos grains, ne vendez pas les animaux a bas prix. Repondez 1 ok 2 moyen 3 perdu. STOP pour arreter" if em else
                        f"{L} {name}: cultures seches. Gardez 2 mois de grains, ne vendez pas a bas prix. Repondez 1 ok 2 moyen 3 perdu. STOP pour arreter")
            if event == "cant_plant" and not em:
                return f"{L} {name}: rains late and poor. Wait for 2 good rains before planting, use short-season seed. Reply 1 ok 2 poor 3 failed. STOP to quit"
            if em and event == "no_grass":
                return f"{L} {name}: severe drought, grazing gone. Keep your grain for the family, do not sell animals cheap. Reply 1 ok 2 poor 3 failed. STOP to quit"
            return (f"{L} {name}: harvest failed. Keep your grain, do not sell animals cheap. Ask chief about relief. Reply 1 ok 2 poor 3 failed. STOP to quit" if em else
                    f"{L} {name}: crops drying, poor harvest likely. Keep 2 months of grain, do not sell cheap. Reply 1 ok 2 poor 3 failed. STOP to quit")
        if role == "herder":
            if em and event != "no_grass" and not fr:
                return f"{L} {name}: severe drought, crops failed. Sell weak animals early, keep breeding stock, save water for the herd. Reply 1 ok 2 poor 3 bad. STOP to quit"
            if em and event != "no_grass" and fr:
                return f"{L} {name}: grave secheresse. Vendez tot les betes faibles, gardez les reproductrices, gardez l'eau. Repondez 1 ok 2 moyen 3 grave. STOP pour arreter"
            if fr:
                return (f"{L} {name}: plus d'herbe. Vendez les betes faibles, gardez les reproductrices, allez vers l'eau. Repondez 1 ok 2 moyen 3 grave. STOP pour arreter" if em else
                        f"{L} {name}: paturages secs. Vendez tot les betes faibles, prevoyez les deplacements. Repondez 1 ok 2 moyen 3 grave. STOP pour arreter")
            return (f"{L} {name}: no grass left. Sell weak animals now, keep breeding stock, move herds to water. Reply 1 ok 2 poor 3 bad. STOP to quit" if em else
                    f"{L} {name}: grazing drying fast. Sell weak animals early while prices hold, plan herd moves. Reply 1 ok 2 poor 3 bad. STOP to quit")
        if role == "resident":
            if fr:
                return f"{L} {name}: secheresse, manque de nourriture probable. Gardez l'eau propre, inscrivez-vous au comite local. Repondez HELP. STOP pour arreter"
            return f"{L} {name}: drought, food shortage likely. Keep water clean, register with ward food committee. Reply HELP for an officer. STOP to quit"
        if role == "ngo":
            p = ev.get("p")
            ptxt = f"P(shortage,{ev.get('horizon') or '?'}wk)={p:.2f}" if p is not None else "P n/a"
            drv = gsm_safe(drivers[0])[:45] if drivers else "dry conditions"
            return f"{L} {name}: {ptxt}. {drv}. {ev.get('agreeing', '?')}/3 sources agree, conf {ev.get('confidence') or '?'}."
        if role == "officer":
            lab = EVENT_LABEL.get(event, "Drought risk")
            return f"{L} {name}: {lab}. Prioritise visits to worst-hit wards, push drought-tolerant seed. {ev.get('agreeing', '?')}/3 sources agree."
        raise ValueError(f"unknown role {role}")

    name = gsm_safe(ev.get("unit_name") or "your area")
    act = None
    if role in ("farmer", "herder") and ev.get("recommendations") and (language or "en")[:2] in ("en", "sw"):
        act = recommend.top_action(ev["recommendations"], role, language or "en")
    if act:  # top recommended action, same reply tail as the template; fall back if it does not fit
        tail = ("Jibu 1 sawa 2 hafifu 3 mbaya. ACHA kujiondoa" if sw else "Reply 1 ok 2 poor 3 bad. STOP to quit")
        cand = gsm_safe(f"{L} {name}: {act} {tail}")
        if gsm_len(cand) <= MAX_LEN:
            return cand
    text = build(name)
    while gsm_len(text) > MAX_LEN and len(name) > 6:  # shorten long district names first
        name = name[:-2]
        text = build(name.rstrip() + ".")
    return fit(text)


# ------------------------------------------------------------------ matching + send
def monthly_cap() -> int:
    return int(os.environ.get("MONTHLY_CAP", "6"))


def _alerts_this_month(user_id: int) -> int:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    r = db.q1("SELECT COUNT(*) n FROM messages WHERE user_id=? AND direction='out' "
              "AND event_id IS NOT NULL AND status NOT LIKE 'failed%' AND substr(created_at,1,7)=?",
              (user_id, month))
    return r["n"] if r else 0


def recipients(ev: dict) -> tuple[list[dict], dict]:
    roles = audiences(int(ev["level"]), ev.get("event"))
    if not roles:
        return [], {"opted_out": 0, "no_consent": 0, "monthly_cap": 0, "already_sent": 0}
    marks = ",".join("?" * len(roles))
    users = db.q(
        f"SELECT * FROM users WHERE iso3=? AND role IN ({marks}) AND "
        f"(district_id=? OR (district_id IS NULL AND role IN ('ngo','officer'))) ORDER BY id",
        (ev["iso3"], *roles, ev["unit_id"]))
    skipped = {"opted_out": 0, "no_consent": 0, "monthly_cap": 0, "already_sent": 0}
    out = []
    for u in users:
        if u["opted_out_at"]:
            skipped["opted_out"] += 1
        elif not u["consent_at"]:
            skipped["no_consent"] += 1
        elif db.q1("SELECT 1 FROM messages WHERE user_id=? AND event_id=? AND direction='out' "
                   "AND status NOT LIKE 'failed%'", (u["id"], ev["id"])):
            skipped["already_sent"] += 1
        elif _alerts_this_month(u["id"]) >= monthly_cap():
            skipped["monthly_cap"] += 1
        else:
            out.append(u)
    return out, skipped


def event_dict(row: dict) -> dict:
    ev = dict(row)
    ev["drivers"] = json.loads(row.get("drivers_json") or "[]")
    ev["recommendations"] = json.loads(row.get("recommendations_json") or "[]")
    return ev


def event_counts(event_id: int) -> dict:
    """Delivery counts for one event: failed rows are never counted as sent."""
    r = db.q1(
        "SELECT (SELECT COUNT(*) FROM messages WHERE event_id=:e AND direction='out' AND status NOT LIKE 'failed%') ok, "
        "(SELECT COUNT(DISTINCT user_id) FROM messages f WHERE f.event_id=:e AND f.direction='out' "
        " AND f.status LIKE 'failed%' AND NOT EXISTS (SELECT 1 FROM messages g WHERE g.event_id=:e "
        " AND g.user_id=f.user_id AND g.direction='out' AND g.status NOT LIKE 'failed%')) bad",
        {"e": event_id}) or {}
    ok, bad = int(r.get("ok") or 0), int(r.get("bad") or 0)
    label = f"sent to {ok} users" + (f", failed {bad}" if bad else "")
    return {"sent_count": ok, "failed_count": bad, "sent_to_label": label}


def _send_one(u: dict, ev: dict, event_id: int) -> str:
    text = compose(u["role"], ev, u.get("language") or "en")
    try:  # reserve the row first: the unique index makes a concurrent double-approve a no-op
        mid = db.log_message("out", u["phone"], text, user_id=u["id"], event_id=event_id,
                             intent=f"alert_{u['role']}", status="sending")
    except sqlite3.IntegrityError:
        return "duplicate"
    status, gid = gateway.send(u["phone"], text)
    db.ex("UPDATE messages SET status=?, gateway_id=? WHERE id=?", (status, gid, mid))
    return status


def send_event(event_id: int, approved_by: str | None = None) -> dict:
    """Send an approved event. Status becomes 'sent' only if no send failed;
    otherwise it stays 'approved' and approving again retries the failed users."""
    row = db.q1("SELECT * FROM events WHERE id=?", (event_id,))
    if not row:
        raise KeyError(event_id)
    if row["status"] == "cancelled":
        return {"event_id": event_id, "sent": 0, "failed": 0, "status": "cancelled"}
    ev = event_dict(row)
    users, skipped = recipients(ev)
    workers = max(1, min(8, len(users)))
    with ThreadPoolExecutor(max_workers=workers) as pool:  # real gateway: parallel, not N x timeout
        results = list(pool.map(lambda u: _send_one(u, ev, event_id), users))
    sent = sum(1 for r in results if not r.startswith("failed") and r != "duplicate")
    failed = sum(1 for r in results if r.startswith("failed"))
    skipped["already_sent"] += results.count("duplicate")
    counts = event_counts(event_id)
    status = "approved" if failed else "sent"
    db.ex("UPDATE events SET status=?, approved_by=COALESCE(?, approved_by) WHERE id=?",
          (status, approved_by, event_id))
    return {"event_id": event_id, "sent": sent, "failed": failed, "skipped": skipped, "status": status,
            "audiences": audiences(int(ev["level"]), ev.get("event")), **counts}
