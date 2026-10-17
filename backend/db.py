"""SQLite schema + helpers for the SMS backend (see backend/API.md).

Also holds small shared helpers: config paths, .env loading, reading the
pipeline's data/geo and data/risk JS files.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
REPO_DIR = BACKEND_DIR.parent


def load_env() -> None:
    """Load ANTHROPIC_API_KEY etc. without ever copying secrets into the repo.

    Order: $ENV_FILE, <repo>/.env, <repo>/../.env (the team's /home/looooo/bcg/.env).
    Existing environment variables are never overridden.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover
        return
    for p in [os.environ.get("ENV_FILE"), REPO_DIR / ".env", REPO_DIR.parent / ".env"]:
        if p and Path(p).is_file():
            load_dotenv(p, override=False)


load_env()


def ensure_admin_token() -> None:
    """Make sure ADMIN_TOKEN exists. If missing, generate one and append it to the team .env
    (/home/looooo/bcg/.env, outside the repo). The value is never printed or logged."""
    if os.environ.get("ADMIN_TOKEN"):
        return
    import secrets
    tok = secrets.token_urlsafe(24)
    env = Path(os.environ.get("ENV_FILE") or REPO_DIR.parent / ".env")
    try:
        if env.is_file() and "ADMIN_TOKEN=" not in env.read_text():
            with env.open("a") as f:
                f.write(f"\n# operator token for the SMS backend (header X-API-Key)\nADMIN_TOKEN={tok}\n")
    except OSError:
        pass  # still works for this process
    os.environ["ADMIN_TOKEN"] = tok


def risk_dir() -> Path:
    return Path(os.environ.get("RISK_DIR", REPO_DIR / "data" / "risk"))


def geo_dir() -> Path:
    return Path(os.environ.get("GEO_DIR", REPO_DIR / "data" / "geo"))


def db_path() -> str:
    return os.environ.get("DB_PATH", str(BACKEND_DIR / "demo.db"))


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------- JS data files
def parse_js_assignment(text: str, var: str) -> dict | None:
    """Return the JSON object assigned in `VAR["ISO3"] = {...};`, or None."""
    import re
    m = re.search(rf'^\s*{var}\["[A-Z]{{3}}"\]\s*=', text, re.M)
    if not m:
        return None
    body = text[m.end():].strip()
    if body.endswith(";"):
        body = body[:-1]
    return json.loads(body)


_geo_cache: dict[str, list[dict]] = {}


def geo_units(iso3: str) -> list[dict]:
    """[{id, name, lat, lng}] for a country, from data/geo/<ISO3>.js."""
    iso3 = iso3.upper()
    if iso3 not in _geo_cache:
        f = geo_dir() / f"{iso3}.js"
        units: list[dict] = []
        if f.is_file():
            data = parse_js_assignment(f.read_text(encoding="utf-8"), "GEO_DATA") or {}
            for feat in data.get("features", []):
                p = feat.get("properties", {})
                units.append({"id": p.get("id"), "name": p.get("name"),
                              "lat": p.get("lat"), "lng": p.get("lng")})
        _geo_cache[iso3] = units
    return _geo_cache[iso3]


class RiskFileError(Exception):
    pass


def load_risk(iso3: str) -> dict:
    """Parse data/risk/<ISO3>.js. Raises RiskFileError for missing or STUB data."""
    iso3 = iso3.upper()
    f = risk_dir() / f"{iso3}.js"
    if not f.is_file():
        raise RiskFileError(f"No risk file for {iso3} ({f}).")
    data = parse_js_assignment(f.read_text(encoding="utf-8"), "RISK_DATA")
    if data is None:
        raise RiskFileError(f"{f.name} has no model output yet (RISK_DATA['{iso3}'] not set).")
    mv = str(data.get("meta", {}).get("model_version", ""))
    if mv.upper() == "STUB":
        raise RiskFileError(
            f"{f.name} is a STUB (placeholder numbers, model_version=STUB). "
            "Refusing to create alerts from fake data. Run the risk model first.")
    return data


def month_label(t: int, start_year: int = 2019) -> str:
    y, m = divmod(int(t), 12)
    return datetime(start_year + y, m + 1, 1).strftime("%b %Y")


# ---------------------------------------------------------------- SQLite
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  phone TEXT UNIQUE NOT NULL,
  name TEXT,
  district_id TEXT,
  district_name TEXT,
  iso3 TEXT,
  role TEXT CHECK (role IN ('farmer','herder','ngo','officer','resident')),
  language TEXT DEFAULT 'en',
  consent_at TEXT,
  opted_out_at TEXT,
  created_at TEXT NOT NULL,
  raw_signup_text TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  iso3 TEXT NOT NULL,
  unit_id TEXT NOT NULL,
  unit_name TEXT,
  t INTEGER NOT NULL,
  month_label TEXT,
  level INTEGER NOT NULL,
  event TEXT,
  p REAL,
  drivers_json TEXT,
  status TEXT NOT NULL CHECK (status IN ('pending_approval','approved','sent','cancelled')),
  approved_by TEXT,
  horizon INTEGER,
  confidence TEXT,
  agreeing INTEGER,
  model_version TEXT,
  UNIQUE (iso3, unit_id, t, level)
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  direction TEXT NOT NULL CHECK (direction IN ('in','out')),
  phone TEXT NOT NULL,
  user_id INTEGER,
  event_id INTEGER,
  text TEXT NOT NULL,
  intent TEXT,
  intent_confidence REAL,
  parsed_json TEXT,
  status TEXT,
  gateway_id TEXT
);
CREATE INDEX IF NOT EXISTS ix_messages_phone ON messages(phone);
CREATE INDEX IF NOT EXISTS ix_messages_gw ON messages(gateway_id);
-- one live alert SMS per (user, event); failed rows do not block a retry
CREATE UNIQUE INDEX IF NOT EXISTS ux_alert_once ON messages(user_id, event_id)
  WHERE direction='out' AND event_id IS NOT NULL AND status NOT LIKE 'failed%';
CREATE TABLE IF NOT EXISTS processed_runs (
  iso3 TEXT NOT NULL,
  t INTEGER NOT NULL,
  processed_at TEXT NOT NULL,
  created INTEGER,
  PRIMARY KEY (iso3, t)
);
CREATE TABLE IF NOT EXISTS help_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  user_id INTEGER,
  text TEXT,
  status TEXT DEFAULT 'open'
);
-- conversation state for multi-step sign-up / clarification (not in API.md tables list)
CREATE TABLE IF NOT EXISTS sessions (
  phone TEXT PRIMARY KEY,
  state_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""

_lock = threading.RLock()
_conns: dict[str, sqlite3.Connection] = {}


def connect(path: str | None = None) -> sqlite3.Connection:
    path = path or db_path()
    with _lock:
        if path not in _conns:
            c = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL") if path != ":memory:" else None
            c.executescript(SCHEMA)
            _conns[path] = c
        return _conns[path]


def reset_connections() -> None:
    with _lock:
        for c in _conns.values():
            c.close()
        _conns.clear()


def q(sql: str, args: tuple = (), db: sqlite3.Connection | None = None) -> list[dict]:
    db = db or connect()
    with _lock:
        return [dict(r) for r in db.execute(sql, args).fetchall()]


def q1(sql: str, args: tuple = (), db: sqlite3.Connection | None = None) -> dict | None:
    rows = q(sql, args, db)
    return rows[0] if rows else None


def ex(sql: str, args: tuple = (), db: sqlite3.Connection | None = None) -> int:
    """Execute; return lastrowid."""
    db = db or connect()
    with _lock:
        return db.execute(sql, args).lastrowid


# ---- retention (spec: limited retention; demo default 90 days)
def purge_old(days: int | None = None) -> dict:
    """Delete old messages, stale sessions (7 d) and closed help requests. RETENTION_DAYS env."""
    days = int(days if days is not None else os.environ.get("RETENTION_DAYS", "90"))
    cut = f"-{days} day"
    out = {}
    with _lock:
        c = connect()
        out["messages"] = c.execute("DELETE FROM messages WHERE created_at < strftime('%Y-%m-%dT%H:%M:%S', 'now', ?)",
                                    (cut,)).rowcount
        out["sessions"] = c.execute("DELETE FROM sessions WHERE updated_at < strftime('%Y-%m-%dT%H:%M:%S', 'now', '-7 day')").rowcount
        out["help_requests"] = c.execute("DELETE FROM help_requests WHERE status!='open' AND "
                                         "created_at < strftime('%Y-%m-%dT%H:%M:%S', 'now', ?)", (cut,)).rowcount
    return out


# ---- users
def get_user(phone: str) -> dict | None:
    return q1("SELECT * FROM users WHERE phone=?", (phone,))


def upsert_user(phone: str, **f) -> int:
    u = get_user(phone)
    if u:
        if f:
            cols = ", ".join(f"{k}=?" for k in f)
            ex(f"UPDATE users SET {cols} WHERE id=?", (*f.values(), u["id"]))
        return u["id"]
    f.setdefault("created_at", now_iso())
    cols = ", ".join(["phone", *f.keys()])
    marks = ", ".join("?" * (len(f) + 1))
    return ex(f"INSERT INTO users ({cols}) VALUES ({marks})", (phone, *f.values()))


# ---- messages
def log_message(direction: str, phone: str, text: str, **f) -> int:
    f.setdefault("created_at", now_iso())
    if "parsed_json" in f and not isinstance(f["parsed_json"], (str, type(None))):
        f["parsed_json"] = json.dumps(f["parsed_json"], ensure_ascii=False)
    cols = ", ".join(["direction", "phone", "text", *f.keys()])
    marks = ", ".join("?" * (len(f) + 3))
    return ex(f"INSERT INTO messages ({cols}) VALUES ({marks})", (direction, phone, text, *f.values()))


# ---- sessions
def get_session(phone: str) -> dict:
    r = q1("SELECT state_json FROM sessions WHERE phone=?", (phone,))
    return json.loads(r["state_json"]) if r else {}


def set_session(phone: str, state: dict | None) -> None:
    if not state:
        ex("DELETE FROM sessions WHERE phone=?", (phone,))
    else:
        ex("INSERT INTO sessions (phone, state_json, updated_at) VALUES (?,?,?) "
           "ON CONFLICT(phone) DO UPDATE SET state_json=excluded.state_json, updated_at=excluded.updated_at",
           (phone, json.dumps(state, ensure_ascii=False), now_iso()))
