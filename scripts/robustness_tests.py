#!/usr/bin/env python3
"""Failure-mode + latency tests for the demo backend (backend/app.py).

Each test boots its OWN uvicorn on a spare port with a temp SQLite db and a
non-STUB copy of data/risk/ZWE.js (RISK_DIR), so the team's running demo on
:8000 is never touched. Results -> pipeline/audit/out/robustness_results.json.

    ../.venv/bin/python scripts/robustness_tests.py            # all tests
    ../.venv/bin/python scripts/robustness_tests.py claude_down burst
    ../.venv/bin/python scripts/robustness_tests.py --list

Tests: claude_badkey claude_refused claude_blackhole gateway_down backend_down
       double_approve burst latency reload health_during_llm
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
PY = sys.executable
OUT_DIR = REPO / "pipeline" / "audit" / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)
RESULTS: dict[str, dict] = {}
_prev = OUT_DIR / "robustness_results.json"
if _prev.is_file():
    try:
        RESULTS.update(json.loads(_prev.read_text()))
    except ValueError:
        pass
SITE_PORT = int(os.environ.get("SITE_PORT", "8777"))


# ----------------------------------------------------------------------- utils
def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def pct(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1)))))
    return xs[k]


class Backend:
    """Context manager: uvicorn backend.app:app on a free port with custom env."""

    def __init__(self, name: str, env: dict | None = None, risk_stub_ok: bool = True):
        self.name = name
        self.port = free_port()
        self.tmp = Path(tempfile.mkdtemp(prefix=f"rb_{name}_"))
        self.env = {**os.environ, **(env or {})}
        self.env.setdefault("GATEWAY", "sim")
        self.env.setdefault("DB_PATH", str(self.tmp / "demo.db"))
        if env and "DB_PATH" in env:
            self.env["DB_PATH"] = env["DB_PATH"]
        self.env["PYTHONUNBUFFERED"] = "1"
        if risk_stub_ok:
            # Copy data/risk, un-STUB ZWE so /alerts/run works even before the real model lands.
            rd = self.tmp / "risk"
            rd.mkdir()
            for f in (REPO / "data" / "risk").glob("*.js"):
                txt = f.read_text(encoding="utf-8")
                txt = re.sub(r'"model_version":\s*"STUB"', '"model_version":"TEST-UNSTUBBED"', txt)
                (rd / f.name).write_text(txt, encoding="utf-8")
            self.env["RISK_DIR"] = str(rd)
        self.log = open(self.tmp / "backend.log", "w")
        self.proc: subprocess.Popen | None = None
        self.base = f"http://127.0.0.1:{self.port}"

    def __enter__(self):
        self.proc = subprocess.Popen(
            [PY, "-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", str(self.port),
             "--log-level", "warning"],
            cwd=REPO, env=self.env, stdout=self.log, stderr=subprocess.STDOUT)
        for _ in range(80):
            try:
                if httpx.get(self.base + "/health", timeout=1).status_code == 200:
                    return self
            except httpx.HTTPError:
                pass
            if self.proc.poll() is not None:
                break
            time.sleep(0.25)
        self.log.flush()
        raise RuntimeError(f"backend {self.name} did not start:\n" + (self.tmp / "backend.log").read_text()[-2000:])

    def __exit__(self, *a):
        self.stop()

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.log.flush()

    def alive(self) -> bool:
        try:
            return self.proc.poll() is None and httpx.get(self.base + "/health", timeout=3).status_code == 200
        except httpx.HTTPError:
            return False

    def logtail(self, n=30) -> str:
        self.log.flush()
        return "\n".join((self.tmp / "backend.log").read_text(errors="replace").splitlines()[-n:])

    # helpers
    def post(self, path, body, timeout=90):
        t0 = time.perf_counter()
        r = httpx.post(self.base + path, json=body, timeout=timeout, headers=_auth())
        return r, time.perf_counter() - t0

    def get(self, path, timeout=10):
        return httpx.get(self.base + path, timeout=timeout, headers=_auth())

    def rows(self, path, key):
        d = self.get(path).json()
        if isinstance(d, list):
            return d
        for k in (key, "items", "rows", "data"):
            if isinstance(d.get(k), list):
                return d[k]
        return []


def _auth() -> dict:
    """Operator header (ADMIN_TOKEN from the team .env; never printed)."""
    tok = os.environ.get("ADMIN_TOKEN")
    return {"X-API-Key": tok} if tok else {}


def record(name: str, ok: bool, **kw):
    RESULTS[name] = {"pass": ok, **kw}
    flag = "PASS" if ok else "FAIL"
    print(f"\n[{flag}] {name}")
    for k, v in kw.items():
        s = json.dumps(v, default=str) if not isinstance(v, str) else v
        print(f"   {k}: {s[:600]}")


def sign_up_free_text(be: Backend, phone: str, text: str):
    r, dt = be.post("/sim/inbound", {"from": phone, "text": text})
    return r, dt


def make_pending_event(be: Backend, iso3="ZWE") -> dict | None:
    """Run alerts over months until a pending_approval event exists; return it."""
    for t in range(1, 72):
        r = be.post("/alerts/run", {"iso3": iso3, "t": t}, timeout=120)[0]
        if r.status_code != 200:
            print("   /alerts/run", r.status_code, r.text[:200])
            return None
        evs = be.rows("/feed/alerts?since=0", "events")
        pend = [e for e in evs if e.get("status") == "pending_approval"]
        if pend:
            return pend[0]
    return None


def role_for(ev: dict) -> str:
    return "herder" if ev.get("event") == "no_grass" else "farmer"


def subscribe_users_in(be: Backend, unit_name: str, n: int, role="farmer", prefix="+26377100"):
    """Keyword-only sign-up (no Claude): JOIN -> district -> role -> YES, answering a
    'Which district? 1 X, 2 Y' disambiguation with the number of the exact name."""
    phones = []
    for i in range(n):
        ph = f"{prefix}{i:04d}"
        reply = ""
        for step in ("JOIN", unit_name, role, "YES"):
            if reply.startswith("Which district?"):
                opts = re.findall(r"(\d+) ([^,.]+)", reply.split("?", 1)[1])
                pick = next((num for num, nm in opts if nm.strip().lower() == unit_name.lower()), opts[0][0] if opts else "1")
                r, _ = be.post("/sim/inbound", {"from": ph, "text": pick})
                reply = r.json().get("reply", "") if r.status_code == 200 else ""
                if step == role and "farmer, herder" not in reply:
                    continue  # role already known? fall through to next step
            r, _ = be.post("/sim/inbound", {"from": ph, "text": step})
            reply = r.json().get("reply", "") if r.status_code == 200 else ""
            if "registered" in reply.lower():
                break
        phones.append(ph)
    users = {u.get("phone") for u in be.rows("/feed/users?since=0", "users")}
    missing = [p for p in phones if p not in users]
    if missing:
        print(f"   warning: {len(missing)} sign-ups did not complete for {unit_name!r}: last reply {reply[:90]!r}")
    return phones


# ----------------------------------------------------------------------- tests
FREE_TEXT = [
    "Hello I am a farmer in Mbire and want the drought alerts please",
    "Ndiri murimi ku Binga",
    "can you add me, I keep cattle near Gwanda",
    "what should I plant this season?",
    "we have no food in our village, need help",
    "my crops are poor this month",
]


def test_claude_badkey():
    """Claude API unreachable/invalid (bad key) -> keyword fallback, no crash."""
    with Backend("badkey", {"ANTHROPIC_API_KEY": "sk-ant-invalid-key-for-test"}) as be:
        res = []
        for i, txt in enumerate(FREE_TEXT + ["JOIN Mbire farmer", "2", "STOP"]):
            r, dt = sign_up_free_text(be, f"+2637701000{i:02d}", txt)
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            res.append({"text": txt, "status": r.status_code, "ms": round(dt * 1000),
                        "intent": body.get("intent"), "source": (body.get("parsed") or {}).get("source"),
                        "reply": str(body.get("reply", ""))[:80]})
        ok = all(x["status"] == 200 and x["reply"] for x in res) and be.alive()
        ok = ok and not any(x["source"] == "llm" for x in res)
        joined = [x for x in res if x["text"] == "JOIN Mbire farmer"]
        ok = ok and bool(joined) and joined[0]["intent"] in ("subscribe", "confirm", "join", "signup")
        record("claude_badkey", ok, results=res, alive=be.alive(),
               max_ms=max(x["ms"] for x in res), log=be.logtail(8))


def test_claude_refused():
    """Claude host refuses connections (Wi-Fi down with instant failure)."""
    with Backend("refused", {"ANTHROPIC_BASE_URL": f"http://127.0.0.1:{free_port()}"}) as be:
        res = []
        for i, txt in enumerate(FREE_TEXT[:3] + ["JOIN Gwanda herder"]):
            r, dt = sign_up_free_text(be, f"+2637702000{i:02d}", txt)
            body = r.json() if r.status_code == 200 else {}
            res.append({"text": txt, "status": r.status_code, "ms": round(dt * 1000),
                        "intent": body.get("intent"), "reply": str(body.get("reply", ""))[:80]})
        ok = all(x["status"] == 200 and x["reply"] for x in res) and be.alive()
        record("claude_refused", ok, results=res, max_ms=max(x["ms"] for x in res), log=be.logtail(6))


def test_claude_blackhole():
    """Claude host black-holed (packets dropped, e.g. captive portal) -> how long until fallback?"""
    # 10.255.255.1 is unroutable from most LANs -> connect timeout (not refusal).
    with Backend("blackhole", {"ANTHROPIC_BASE_URL": "http://10.255.255.1:9/"}) as be:
        r, dt = sign_up_free_text(be, "+263770300001", FREE_TEXT[0])
        body = r.json() if r.status_code == 200 else {}
        r2, dt2 = sign_up_free_text(be, "+263770300002", "JOIN Mbire farmer")
        ok = r.status_code == 200 and bool(body.get("reply")) and be.alive()
        record("claude_blackhole", ok, free_text_ms=round(dt * 1000), keyword_ms=round(dt2 * 1000),
               intent=body.get("intent"), reply=str(body.get("reply", ""))[:80], alive=be.alive(),
               note="UI fetch timeout is 4000 ms (js/live.js api()); anything above shows 'Send failed' on stage",
               log=be.logtail(6))


def test_gateway_down():
    """Android gateway unreachable -> out messages marked failed, feed shows it, sim still works."""
    with Backend("gwdown", {"GATEWAY": "android", "ANDROID_GW_URL": f"http://127.0.0.1:{free_port()}",
                            "ANDROID_GW_USER": "x", "ANDROID_GW_PASS": "y"}) as be:
        ev = make_pending_event(be)
        if not ev:
            record("gateway_down", False, reason="no pending_approval event could be created", log=be.logtail(20))
            return
        subscribe_users_in(be, ev["unit_name"], 3, role=role_for(ev))
        r, dt = be.post(f"/events/{ev['id']}/approve", {})
        msgs = [m for m in be.rows("/feed/messages?since=0", "messages") if m.get("event_id") == ev["id"]]
        statuses = sorted({m.get("status") for m in msgs})
        r2, _ = be.post("/sim/inbound", {"from": "+263770400099", "text": "JOIN Mbire farmer"})
        ev_after = next((e for e in be.rows("/feed/alerts?since=0", "events") if e["id"] == ev["id"]), {})
        ok = (r.status_code == 200 and msgs and all(str(m.get("status", "")).startswith("failed") for m in msgs)
              and r2.status_code == 200 and be.alive())
        record("gateway_down", ok, approve_status=r.status_code, approve_ms=round(dt * 1000),
               out_messages=len(msgs), statuses=statuses, event_status_after=ev_after.get("status"),
               sim_still_works=r2.status_code == 200, approve_body=r.text[:200],
               note="event is marked 'sent' even when every gateway send failed" if ev_after.get("status") == "sent" else "")


def test_backend_down():
    """Backend down: static site still serves globe + data, live.js degrades."""
    port = free_port()  # nothing listening
    try:
        httpx.get(f"http://127.0.0.1:{port}/health", timeout=2)
        down = False
    except httpx.HTTPError:
        down = True
    site = f"http://127.0.0.1:{SITE_PORT}"
    got = {}
    try:
        for p in ["/index.html", "/js/app.js", "/js/live.js", "/js/real.js", "/vendor/globe.gl.min.js",
                  "/data/geo/ZWE.js", "/data/risk/ZWE.js", "/css/app.css", "/css/live.css"]:
            got[p] = httpx.get(site + p, timeout=10).status_code
    except httpx.HTTPError as e:
        record("backend_down", False, reason=f"static server {site} not reachable: {e}")
        return
    html = httpx.get(site + "/index.html", timeout=10).text
    cdn = re.findall(r'https?://[^"\' ]+\.(?:js|css|png|jpg)', html)
    ok = down and all(v == 200 for v in got.values()) and not cdn
    record("backend_down", ok, static=got, external_assets_in_index=cdn,
           note="live.js: api() catches fetch errors -> 'backend offline', globe untouched (code review)")


def test_double_approve():
    """Two approve clicks at once -> each user gets exactly one SMS."""
    with Backend("dbl") as be:
        ev = make_pending_event(be)
        if not ev:
            record("double_approve", False, reason="no pending_approval event", log=be.logtail(20))
            return
        phones = subscribe_users_in(be, ev["unit_name"], 5, role=role_for(ev), prefix="+26377500")
        codes = []

        def hit():
            codes.append(be.post(f"/events/{ev['id']}/approve", {})[0].status_code)

        ts = [threading.Thread(target=hit) for _ in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        time.sleep(0.5)
        be.post(f"/events/{ev['id']}/approve", {})  # a late third click
        msgs = [m for m in be.rows("/feed/messages?since=0", "messages")
                if m.get("event_id") == ev["id"] and m.get("direction") == "out"]
        per_phone = {}
        for m in msgs:
            per_phone[m["phone"]] = per_phone.get(m["phone"], 0) + 1
        dup = {p: n for p, n in per_phone.items() if n > 1}
        ok = not dup and len(per_phone) >= 1 and be.alive()
        record("double_approve", ok, approve_codes=codes, users_subscribed=len(phones),
               recipients=len(per_phone), duplicates=dup, total_out=len(msgs))


def test_burst(n=50):
    """50 inbound SMS at once (mix of keyword + free text through real Claude)."""
    with Backend("burst") as be:
        texts = [(f"+2637706{i:05d}", (FREE_TEXT + ["JOIN Mbire farmer", "2", "STOP", "JOIN Binga herder"])[i % 10])
                 for i in range(n)]
        lat, codes, errs = [], [], []
        t0 = time.perf_counter()

        def one(pt):
            try:
                r, dt = be.post("/sim/inbound", {"from": pt[0], "text": pt[1]}, timeout=120)
                lat.append(dt)
                codes.append(r.status_code)
            except Exception as e:  # noqa: BLE001
                errs.append(repr(e)[:100])

        with ThreadPoolExecutor(max_workers=n) as ex:
            list(ex.map(one, texts))
        wall = time.perf_counter() - t0
        alive = be.alive()
        h_t0 = time.perf_counter()
        be.get("/health")
        health_ms = (time.perf_counter() - h_t0) * 1000
        ok = alive and not errs and all(c == 200 for c in codes)
        record("burst", ok, n=n, wall_s=round(wall, 2), p50_s=round(pct(lat, 50), 2), p95_s=round(pct(lat, 95), 2),
               max_s=round(max(lat), 2) if lat else None, non200=[c for c in codes if c != 200], errors=errs[:5],
               alive=alive, health_ms_after=round(health_ms), log=be.logtail(5))


def test_latency(n=15):
    """Inbound free-text SMS -> reply ready, sequential, real Claude Haiku router."""
    with Backend("lat") as be:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            record("latency", False, reason="ANTHROPIC_API_KEY not in env (load ../.env)")
            return
        free, kw = [], []
        samples = []
        for i in range(n):
            txt = FREE_TEXT[i % len(FREE_TEXT)]
            r, dt = be.post("/sim/inbound", {"from": f"+2637707{i:05d}", "text": txt})
            b = r.json() if r.status_code == 200 else {}
            free.append(dt)
            samples.append({"text": txt[:40], "ms": round(dt * 1000), "intent": b.get("intent"),
                            "conf": b.get("confidence", b.get("intent_confidence")),
                            "source": (b.get("parsed") or {}).get("source"), "reply": str(b.get("reply", ""))[:70]})
        for i in range(5):  # bare JOIN / 2 / STOP are the only keyword fast-paths (no Claude)
            r, dt = be.post("/sim/inbound", {"from": f"+2637708{i:05d}", "text": ["JOIN", "2", "STOP", "JOIN", "HELP"][i]})
            kw.append(dt)
        ms = lambda xs, p: round(pct(xs, p) * 1000)  # noqa: E731
        llm_used = any(s["source"] == "llm" for s in samples)
        fallbacks = sum(1 for s in samples if s["source"] == "keywords")
        record("latency", llm_used and all(s["intent"] for s in samples),
               free_text_p50_ms=ms(free, 50), free_text_p95_ms=ms(free, 95), free_text_max_ms=ms(free, 100),
               keyword_p50_ms=ms(kw, 50), keyword_p95_ms=ms(kw, 95), n=n, llm_used=llm_used, keyword_fallbacks=fallbacks,
               over_ui_4s_timeout=sum(1 for x in free if x > 4.0), samples=samples, log=be.logtail(5))


def test_health_during_llm():
    """Does /health still answer while one free-text SMS is inside the Claude call? (UI polls it every 2 s, 4 s timeout)."""
    with Backend("hdl") as be:
        be.post("/sim/inbound", {"from": "+263770950000", "text": FREE_TEXT[0]})  # warm the anthropic client
        health_ms: list[float] = []
        done = threading.Event()

        def probe():
            while not done.is_set():
                t0 = time.perf_counter()
                try:
                    be.get("/health", timeout=10)
                except httpx.HTTPError:
                    pass
                health_ms.append((time.perf_counter() - t0) * 1000)
                time.sleep(0.1)

        th = threading.Thread(target=probe)
        th.start()
        r, dt = be.post("/sim/inbound", {"from": "+263770950001", "text": FREE_TEXT[2]})
        done.set()
        th.join()
        worst = max(health_ms) if health_ms else None
        ok = r.status_code == 200 and worst is not None and worst < 1000
        record("health_during_llm", ok, sms_ms=round(dt * 1000), health_probes=len(health_ms),
               health_worst_ms=round(worst) if worst else None,
               note="/sim/inbound is `async def` but calls the blocking Claude SDK -> event loop stalls; "
                    "the UI health poll (4 s timeout) flips to 'backend offline' if a call runs long" if not ok else "")


def test_reload():
    """State lives in SQLite + URL (?page=, ?country&t); a reload re-polls everything."""
    with Backend("reload") as be:
        be.post("/sim/inbound", {"from": "+263770900001", "text": "JOIN Mbire farmer"})
        ev = make_pending_event(be)
        n_users = len(be.rows("/feed/users?since=0", "users"))
        n_msgs = len(be.rows("/feed/messages?since=0", "messages"))
        n_ev = len(be.rows("/feed/alerts?since=0", "events"))
        # simulate "browser reload" = fresh client polling from since=0
        again = (len(be.rows("/feed/users?since=0", "users")), len(be.rows("/feed/messages?since=0", "messages")),
                 len(be.rows("/feed/alerts?since=0", "events")))
        # and a backend restart on the same db (uvicorn crash + start_demo.sh)
        be.stop()
        with Backend("reload2", {"DB_PATH": be.env["DB_PATH"], "RISK_DIR": be.env["RISK_DIR"]}, risk_stub_ok=False) as be2:
            after = (len(be2.rows("/feed/users?since=0", "users")), len(be2.rows("/feed/messages?since=0", "messages")),
                     len(be2.rows("/feed/alerts?since=0", "events")))
        ok = again == (n_users, n_msgs, n_ev) == after and n_msgs >= 1 and n_ev >= 1
        record("reload", ok, before=(n_users, n_msgs, n_ev), fresh_client=again, after_backend_restart=after,
               note="browser-side: live.js keeps nothing in memory that is not re-fetched; ?page= and ?country&t survive reload")


TESTS = {
    "claude_badkey": test_claude_badkey,
    "claude_refused": test_claude_refused,
    "claude_blackhole": test_claude_blackhole,
    "gateway_down": test_gateway_down,
    "backend_down": test_backend_down,
    "double_approve": test_double_approve,
    "burst": test_burst,
    "latency": test_latency,
    "reload": test_reload,
    "health_during_llm": test_health_during_llm,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tests", nargs="*")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        print("\n".join(TESTS))
        return 0
    # load the team .env for the real-Claude tests (never printed)
    try:
        from dotenv import load_dotenv
        for p in [REPO / ".env", REPO.parent / ".env"]:
            if p.is_file():
                load_dotenv(p, override=False)
    except ImportError:
        pass
    names = a.tests or list(TESTS)
    for n in names:
        try:
            TESTS[n]()
        except Exception as e:  # noqa: BLE001
            record(n, False, exception=repr(e)[:800])
    out = OUT_DIR / "robustness_results.json"
    out.write_text(json.dumps(RESULTS, indent=2, default=str))
    print(f"\nwrote {out}")
    print("summary:", {k: ("PASS" if v["pass"] else "FAIL") for k, v in RESULTS.items()})
    return 0 if all(v["pass"] for v in RESULTS.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
