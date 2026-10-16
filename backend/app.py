"""FastAPI app for the SMS side (spec: backend/API.md).

Run:  uvicorn backend.app:app --host 0.0.0.0 --port 8000   (from the repo root)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os

import re
import secrets
import threading
import time
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import composer, crowd, db, gateway, router

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger("app")

db.ensure_admin_token()  # generates ADMIN_TOKEN into /home/looooo/bcg/.env if missing (never printed)


# ------------------------------------------------------------------ auth
def is_admin(x_api_key: str | None) -> bool:
    tok = os.environ.get("ADMIN_TOKEN", "")
    return bool(tok and x_api_key and secrets.compare_digest(x_api_key.encode(), tok.encode()))


def require_admin(x_api_key: str | None = Header(default=None)) -> None:
    """Operator endpoints need header X-API-Key: <ADMIN_TOKEN>. Fails closed if no token is configured."""
    if not is_admin(x_api_key):
        raise HTTPException(401, "admin token required (header X-API-Key)")


SIM_PHONE = re.compile(r"^\+[1-9][0-9]{6,14}$")       # E.164
GW_PHONE = re.compile(r"^\+?[0-9]{6,15}$")            # gateway may send national format


@asynccontextmanager
async def lifespan(_app):
    """Build the Claude client and pay the cold-start cost before the first SMS (background thread)."""
    from . import llm
    threading.Thread(target=llm.warm_up, daemon=True).start()
    try:
        db.purge_old()
    except Exception as e:  # pragma: no cover
        log.warning("retention purge failed: %s", e)
    yield


app = FastAPI(title="Drought SMS backend", version="0.1", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class SimIn(BaseModel):
    from_: str | None = None
    text: str

    model_config = {"populate_by_name": True}

    @classmethod
    def parse(cls, d: dict) -> "SimIn":
        return cls(from_=d.get("from") or d.get("phone") or d.get("sender"), text=d.get("text") or d.get("message") or "")


class RunIn(BaseModel):
    iso3: str
    t: int


class ApproveIn(BaseModel):
    approved_by: str | None = None


# ------------------------------------------------------------------ inbound
def _verify_signature(raw: bytes, request: Request) -> bool:
    """capcom6 webhook HMAC-SHA256(key, body + X-Timestamp), timestamp within +-5 min. No key -> False."""
    key = os.environ.get("ANDROID_GW_SIGNING_KEY")
    if not key:
        return False
    ts, sig = request.headers.get("X-Timestamp", ""), request.headers.get("X-Signature", "")
    try:
        if abs(time.time() - int(ts)) > 300:
            return False
    except ValueError:
        return False
    exp = hmac.new(key.encode(), raw + ts.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(exp, sig)


def _android_items(body: dict) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Return ([(phone, text)] inbound SMS, [(gateway_id, status)] delivery updates)."""
    ev, p = body.get("event"), body.get("payload") or {}
    if ev == "sms:received":
        return [((p.get("sender") or p.get("phoneNumber") or ""), p.get("message") or "")], []
    if ev == "sms:batch:received":
        return [((m.get("sender") or m.get("phoneNumber") or ""), m.get("message") or "")
                for m in p.get("messages", [])], []
    if ev in ("sms:sent", "sms:delivered", "sms:failed", "sms:cancelled"):
        return [], [(p.get("messageId") or "", ev.split(":")[1])]
    return [], []


@app.post("/sms/inbound")
async def sms_inbound(request: Request, background: BackgroundTasks):
    """Gateway webhook. Needs a valid gateway signature (ANDROID_GW_SIGNING_KEY) or the admin token.
    Fail closed: with no signing key configured, unsigned webhooks are rejected."""
    raw = await request.body()
    if not (_verify_signature(raw, request) or is_admin(request.headers.get("X-API-Key"))):
        raise HTTPException(401, "bad or missing webhook signature")
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "body must be JSON")
    if "event" in body:  # capcom6 Android SMS Gateway webhook
        sms, updates = _android_items(body)
        for gid, st in updates:
            if gid:
                db.ex("UPDATE messages SET status=? WHERE gateway_id=?", (st, gid))
        # reply in the background so the phone gets its 2xx within 30 s
        sms = [(p.strip(), t) for p, t in sms if p and t and GW_PHONE.match(p.strip())]
        for phone, text in sms:
            background.add_task(router.handle_inbound, phone, text)
        return {"ok": True, "queued": len(sms), "status_updates": len(updates)}
    s = SimIn.parse(body)
    if not s.from_ or not s.text:
        raise HTTPException(422, "need {from, text}")
    if not GW_PHONE.match(s.from_.strip()):
        raise HTTPException(422, "from must be a phone number")
    # Claude calls block: run them in the threadpool so /health and other SMS never wait
    return await run_in_threadpool(router.handle_inbound, s.from_, s.text)


@app.post("/sim/inbound", dependencies=[Depends(require_admin)])
def sim_inbound(body: dict):
    """Sync handler -> FastAPI runs it in the threadpool (never blocks the event loop)."""
    s = SimIn.parse(body)
    if not s.from_ or not s.text:
        raise HTTPException(422, "need {from, text}")
    if not SIM_PHONE.match(s.from_.strip()):
        raise HTTPException(422, "from must be an E.164 number, e.g. +212600000001")
    return router.handle_inbound(s.from_, s.text)


# ------------------------------------------------------------------ alerts broker
@app.post("/alerts/run", dependencies=[Depends(require_admin)])
def alerts_run(body: RunIn):
    try:
        risk = db.load_risk(body.iso3)
    except db.RiskFileError as e:
        raise HTTPException(409, str(e))
    meta = risk.get("meta", {})
    n = int(meta.get("n_months") or 0)
    if not 0 <= body.t < max(n, 1):
        raise HTTPException(422, f"t must be 0..{n - 1}")
    start = int(meta.get("start_year") or 2019)
    created, auto_sent = [], []
    for u in risk.get("units", []):
        series = {r["t"]: r for r in u.get("series", [])}
        cur, prev = series.get(body.t), series.get(body.t - 1)
        if not cur or cur.get("level") is None:
            continue  # missing is missing
        lvl, plvl = int(cur["level"]), int((prev or {}).get("level") or 0)
        if lvl < 1 or lvl <= plvl:
            continue
        if db.q1("SELECT 1 FROM events WHERE iso3=? AND unit_id=? AND t=? AND level=?",
                 (body.iso3.upper(), u["id"], body.t, lvl)):
            continue
        status = "approved" if lvl == 1 else "pending_approval"
        eid = db.ex(
            "INSERT INTO events (created_at, iso3, unit_id, unit_name, t, month_label, level, event, p, "
            "drivers_json, status, approved_by, horizon, confidence, agreeing, model_version) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (db.now_iso(), body.iso3.upper(), u["id"], u.get("name"), body.t, db.month_label(body.t, start),
             lvl, cur.get("event"), cur.get("p"), json.dumps(cur.get("drivers") or []), status,
             "auto (Watch)" if lvl == 1 else None, cur.get("horizon"), cur.get("confidence"),
             cur.get("agreeing"), meta.get("model_version")))
        created.append(eid)
        if lvl == 1:  # Watch: NGO/officer only, no human gate
            auto_sent.append(composer.send_event(eid, "auto (Watch)"))
    events = []
    for eid in created:
        e = db.q1("SELECT * FROM events WHERE id=?", (eid,))
        e["drivers"] = json.loads(e.pop("drivers_json") or "[]")
        e.update(composer.event_counts(eid))
        events.append(e)
    return {"created": len(created), "events": events, "iso3": body.iso3.upper(), "t": body.t, "month": db.month_label(body.t, start),
            "model_version": meta.get("model_version"),
            "event_ids": created, "watch_sent": auto_sent,
            "pending_approval": len(created) - len(auto_sent)}


@app.post("/events/{event_id}/approve", dependencies=[Depends(require_admin)])
def approve(event_id: int, body: ApproveIn | None = None):
    row = db.q1("SELECT status FROM events WHERE id=?", (event_id,))
    if not row:
        raise HTTPException(404, "no such event")
    if row["status"] == "cancelled":
        raise HTTPException(409, "event was cancelled")
    by = (body.approved_by if body else None) or "operator"
    db.ex("UPDATE events SET status='approved', approved_by=? WHERE id=?", (by, event_id))
    res = composer.send_event(event_id, by)
    e = db.q1("SELECT * FROM events WHERE id=?", (event_id,))
    e["drivers"] = json.loads(e.pop("drivers_json") or "[]")
    e.update(composer.event_counts(event_id))
    return {"ok": True, "event": e, **res}


@app.post("/events/{event_id}/cancel", dependencies=[Depends(require_admin)])
def cancel(event_id: int, body: ApproveIn | None = None):
    if not db.q1("SELECT 1 FROM events WHERE id=?", (event_id,)):
        raise HTTPException(404, "no such event")
    db.ex("UPDATE events SET status='cancelled', approved_by=? WHERE id=? AND status!='sent'",
          ((body.approved_by if body else None) or "operator", event_id))
    return db.q1("SELECT * FROM events WHERE id=?", (event_id,))


# ------------------------------------------------------------------ feeds (polled by the globe)
@app.get("/feed/alerts")
def feed_alerts(since: int = 0, limit: int = 100):
    rows = db.q("SELECT e.* "
                "FROM events e WHERE e.id>? ORDER BY e.id DESC LIMIT ?", (since, limit))
    for r in rows:
        r["drivers"] = json.loads(r.pop("drivers_json") or "[]")
        r.update(composer.event_counts(r["id"]))
        r["sent_to"] = r["sent_count"]
        r["audiences"] = composer.audiences(r["level"], r["event"])
    return {"events": rows, "last_id": max([r["id"] for r in rows], default=since)}


def mask_phone(p: str | None) -> str:
    """+263771000001 -> +263****001 (big-screen safe)."""
    p = p or ""
    return p[:4] + "****" + p[-3:] if len(p) > 7 else "****"


@app.get("/feed/users")
def feed_users(since: int = 0, limit: int = 100, x_api_key: str | None = Header(default=None)):
    """Without the admin token, phone numbers are masked and names dropped."""
    admin = is_admin(x_api_key)
    rows = db.q("SELECT id, phone, name, district_id, district_name, iso3, role, language, consent_at, opted_out_at, "
                "created_at FROM users WHERE id>? ORDER BY id DESC LIMIT ?", (since, limit))
    for r in rows:
        r["phone_masked"] = mask_phone(r["phone"])
        if not admin:
            r["phone"], r["name"] = r["phone_masked"], None
    counts = db.q("SELECT role, COUNT(*) n FROM users WHERE consent_at IS NOT NULL AND opted_out_at IS NULL GROUP BY role")
    today = db.now_iso()[:10]
    n_today = db.q1("SELECT COUNT(*) n FROM users WHERE consent_at IS NOT NULL AND opted_out_at IS NULL "
                    "AND substr(created_at,1,10)=?", (today,))["n"]
    return {"users": rows, "last_id": max([r["id"] for r in rows], default=since),
            "counters": {"total": sum(c["n"] for c in counts), "today": n_today,
                         "by_role": {c["role"]: c["n"] for c in counts}}}


@app.get("/feed/messages")
def feed_messages(since: int = 0, limit: int = 100, phone: str | None = None,
                  x_api_key: str | None = Header(default=None)):
    """Without the admin token, phone numbers are masked and the `phone` filter is ignored."""
    admin = is_admin(x_api_key)
    if not admin:
        phone = None
    if phone:
        rows = db.q("SELECT * FROM messages WHERE id>? AND phone=? ORDER BY id DESC LIMIT ?", (since, phone, limit))
    else:
        rows = db.q("SELECT * FROM messages WHERE id>? ORDER BY id DESC LIMIT ?", (since, limit))
    for r in rows:
        r["parsed"] = json.loads(r.pop("parsed_json") or "null")
        r["chars"] = composer.gsm_len(r["text"])
        r["gsm7"] = composer.is_gsm7(r["text"])
        r["phone_masked"] = mask_phone(r["phone"])
        if not admin:
            r["phone"] = r["phone_masked"]
            if isinstance(r["parsed"], dict):
                r["parsed"].pop("name", None)
    return {"messages": rows, "last_id": max([r["id"] for r in rows], default=since)}


@app.get("/feed/crowd")
def feed_crowd(iso3: str = "ZWE", t: int | None = None, days: int = crowd.WINDOW_DAYS):
    """Crowd signal (spec crowd_crop_status): per district, inbound 1/2/3 reports of consented users in
    the last `days` days, one per user per 7 days. Aggregated counts only (no phones, no names), so no
    auth. With `t`, the display-level rule is evaluated against data/risk/<ISO3>.js for that month:
    +1 (max Warning) only when share_bad >= 0.6, n_reports >= 3 and a satellite family is in alarm."""
    if not re.fullmatch(r"[A-Za-z]{3}", iso3 or ""):
        raise HTTPException(422, "iso3 must be 3 letters")
    if not 1 <= days <= 365:
        raise HTTPException(422, "days must be 1..365")
    units = crowd.aggregate(iso3, days)
    if t is not None:
        units = crowd.with_rule(units, iso3, t)
    return {"iso3": iso3.upper(), "window_days": days, "t": t, "generated_at": db.now_iso(),
            "rule": {"min_reports": crowd.MIN_REPORTS, "min_share_bad": crowd.MIN_SHARE_BAD,
                     "dedup_days": crowd.DEDUP_DAYS, "max_display_level": crowd.MAX_DISPLAY_LEVEL,
                     "needs_satellite_family": list(crowd.SAT_FAMILIES)},
            "units": units}


@app.get("/health")
def health():
    from . import llm
    return {"ok": True, "gateway": gateway.mode(), "llm": llm.available(),
            "auth": "X-API-Key" if os.environ.get("ADMIN_TOKEN") else "NOT CONFIGURED",
            "router_model": llm.ROUTER_MODEL, "advice_model": llm.ADVICE_MODEL,
            "users": db.q1("SELECT COUNT(*) n FROM users")["n"],
            "events": db.q1("SELECT COUNT(*) n FROM events")["n"]}
