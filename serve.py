#!/usr/bin/env python3
"""
Dev server for the prototype: static files + a live FEWS NET feed.

Run this instead of `python3 -m http.server`:

    python3 serve.py            # http://localhost:8777

Why a custom server rather than a plain static one:

  1. fdw.fews.net sends no Access-Control-Allow-Origin header, so the browser
     cannot call it directly. This proxies it.
  2. The only FEWS NET endpoint that carries reporting dates returns the full
     235 MB Kenya history - there is no server-side date filter (confirmed:
     reporting_date_after is ignored, and `fields=` projection silently drops
     reporting_date). So we fetch once in the background, reduce to the latest
     period, and cache.

Endpoints:
    GET /api/live             -> cached current situation, instantly
    GET /api/live?refresh=1   -> force a re-pull from FEWS NET

The response always carries `fetched_at`, `stale` and `source`, so the UI can
be honest about how fresh the number on screen is. If FEWS NET is unreachable
the committed snapshot is served with stale=true - the demo never hard-fails
on a network call.
"""

import collections
import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", 8777))
ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(ROOT, "data", "fews-live.json")
FALLBACK = os.path.join(ROOT, "data", "fews-ipc-kenya.json")

FEWS_URL = ("https://fdw.fews.net/api/ipcphase/?format=json&country_code=KE")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0 Safari/537.36")
PHASE = {"Minimal": 1, "Stressed": 2, "Crisis": 3, "Emergency": 4, "Famine": 5}
TTL = 60 * 60 * 6          # re-pull at most every 6 hours

_lock = threading.Lock()
_state = {"data": None, "fetching": False}


def _county(full):
    parts = [p.strip() for p in full.split(",")]
    return parts[-2] if len(parts) >= 3 else None


def _reduce(raw):
    """Full history -> the latest Current-Situation classification per county,
    plus FEWS NET's own near-term projection (ML1) where one exists."""
    cur, proj = collections.defaultdict(dict), collections.defaultdict(dict)
    for r in raw:
        if r.get("unit_type") != "fsc_admin_lhz":
            continue
        d, c, v = r.get("reporting_date"), _county(r.get("geographic_unit_full_name", "")), PHASE.get(r.get("description"))
        if not (d and c and v):
            continue
        bucket = cur if r.get("scenario") == "CS" else (proj if r.get("scenario") == "ML1" else None)
        if bucket is None:
            continue
        m = d[:7]
        # keep the worst zone within the county, for the latest month seen
        if m not in bucket[c]:
            bucket[c][m] = v
        else:
            bucket[c][m] = max(bucket[c][m], v)

    def latest(b):
        out = {}
        for c, months in b.items():
            if not months:
                continue
            m = max(months)
            out[c] = {"phase": months[m], "as_of": m}
        return out

    current = latest(cur)
    projection = latest(proj)
    asof = sorted({v["as_of"] for v in current.values()})
    return {
        "source": "FEWS NET Data Warehouse (fdw.fews.net), IPC phase",
        "scale": {1: "Minimal", 2: "Stressed", 3: "Crisis", 4: "Emergency", 5: "Famine"},
        "reporting_period": asof[-1] if asof else None,
        "current": current,
        "projection_ml1": projection,
        "n_counties": len(current),
    }


def _load_fallback():
    """Committed snapshot, used when FEWS NET cannot be reached."""
    try:
        with open(FALLBACK) as fh:
            d = json.load(fh)
        latest = {}
        for c, months in d["phases"].items():
            if months:
                m = max(months)
                latest[c] = {"phase": months[m], "as_of": m}
        return {
            "source": "cached snapshot (data/fews-ipc-kenya.json)",
            "scale": d["meta"]["scale"],
            "reporting_period": max((v["as_of"] for v in latest.values()), default=None),
            "current": latest, "projection_ml1": {}, "n_counties": len(latest),
        }
    except Exception:
        return {"source": "unavailable", "current": {}, "projection_ml1": {},
                "reporting_period": None, "n_counties": 0}


def _ssl_context():
    """A framework Python on macOS often ships without a usable CA bundle, so
    urllib fails on HTTPS where curl succeeds. Prefer certifi when it is
    installed; otherwise fall back to the system default."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _fetch():
    """Pull and reduce. Slow (~30-45s) and only ever runs off the request path."""
    req = urllib.request.Request(FEWS_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300, context=_ssl_context()) as r:
        raw = json.loads(r.read())
    out = _reduce(raw)
    out["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out["stale"] = False
    return out


def _refresh(force=False):
    with _lock:
        cur = _state["data"]
        fresh_enough = (
            cur and not cur.get("stale")
            and time.time() - cur.get("_t", 0) < TTL
        )
        if (fresh_enough and not force) or _state["fetching"]:
            return
        _state["fetching"] = True

    def worker():
        try:
            print("[live] pulling FEWS NET...", flush=True)
            d = _fetch()
            d["_t"] = time.time()
            with _lock:
                _state["data"] = d
            os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
            with open(CACHE_FILE, "w") as fh:
                json.dump(d, fh, separators=(",", ":"))
            print(f"[live] ok - {d['n_counties']} counties, period {d['reporting_period']}", flush=True)
        except Exception as e:   # network, TLS, or malformed payload - all non-fatal
            print(f"[live] FAILED ({type(e).__name__}: {e}) - serving cached snapshot", flush=True)
            with _lock:
                if not _state["data"]:
                    d = _load_fallback()
                    d["stale"] = True
                    d["fetched_at"] = None
                    d["_t"] = time.time()
                    _state["data"] = d
        finally:
            with _lock:
                _state["fetching"] = False

    threading.Thread(target=worker, daemon=True).start()


def _current_payload():
    with _lock:
        d = _state["data"]
        fetching = _state["fetching"]
    if d is None:
        d = _load_fallback()
        d["stale"] = True
        d["fetched_at"] = None
    out = {k: v for k, v in d.items() if k != "_t"}
    out["refreshing"] = fetching
    return out


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def do_GET(self):
        if self.path.startswith("/api/live"):
            if "refresh=1" in self.path:
                _refresh(force=True)
            else:
                _refresh(force=False)
            body = json.dumps(_current_payload()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):
        # Quiet the static-file noise, keep the API calls. args[0] is not
        # always a string (send_response passes an HTTPStatus), so coerce.
        first = str(args[0]) if args else ""
        if "/api/" in first:
            super().log_message(fmt, *args)


if __name__ == "__main__":
    # Warm the cache at startup so the Live toggle is instant by demo time.
    _refresh(force=False)
    srv = ThreadingHTTPServer(("", PORT), Handler)
    print(f"\n  SMS Shortage Early Warning — prototype")
    print(f"  http://localhost:{PORT}\n")
    print(f"  live feed: /api/live  (warming in background, ~40s)\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
