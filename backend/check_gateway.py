"""Check the Android SMS gateway (capcom6 SMS Gateway for Android) from .env settings.

    python backend/check_gateway.py                       # auth + device status
    python backend/check_gateway.py +212600000001         # ... and send one test SMS
    python backend/check_gateway.py --register-webhook https://<public-host>/sms/inbound
    python backend/check_gateway.py --list-webhooks

Reads ANDROID_GW_URL / ANDROID_GW_USER / ANDROID_GW_PASS from the environment or
/home/looooo/bcg/.env. Works for both modes:
  local  ANDROID_GW_URL=http://<phone-ip>:8080           (device /health, /webhooks, /message)
  cloud  ANDROID_GW_URL=https://api.sms-gate.app/3rdparty/v1   (/devices, /webhooks, /messages)
Never prints the password.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from backend import db, gateway  # noqa: E402,F401  (db loads .env)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("phone", nargs="?", help="send one test SMS to this number (E.164, e.g. +2126...)")
    ap.add_argument("--text", default="Test from drought alert demo. Reply STOP to quit.")
    ap.add_argument("--register-webhook", metavar="URL", help="register URL for sms:received + delivery events")
    ap.add_argument("--list-webhooks", action="store_true")
    a = ap.parse_args()

    base = os.environ.get("ANDROID_GW_URL", "").rstrip("/")
    user, pw = os.environ.get("ANDROID_GW_USER", ""), os.environ.get("ANDROID_GW_PASS", "")
    cloud = "3rdparty" in base
    print(f"GATEWAY={gateway.mode()}  (backend uses this; set GATEWAY=android in .env to go live)")
    print(f"ANDROID_GW_URL={base or '(not set)'}  mode={'cloud/private' if cloud else 'local'}  "
          f"user={user or '(not set)'}  pass={'set' if pw else '(not set)'}")
    if not base or not user or not pw:
        print("FAIL: set ANDROID_GW_URL, ANDROID_GW_USER, ANDROID_GW_PASS in /home/looooo/bcg/.env")
        return 2
    verify = os.environ.get("ANDROID_GW_VERIFY_TLS", "1") != "0"
    c = httpx.Client(auth=(user, pw), timeout=15, verify=verify)
    ok = True

    # 1. auth: list webhooks (needs Basic auth in every mode)
    try:
        r = c.get(f"{base}/webhooks")
        if r.status_code == 401:
            print("FAIL auth: 401 - wrong username/password (see app Home tab, local vs cloud credentials differ)")
            return 1
        r.raise_for_status()
        hooks = r.json()
        print(f"OK   auth ({len(hooks)} webhook(s) registered)")
        if a.list_webhooks or not hooks:
            for h in hooks:
                print(f"     - {h.get('event'):14} {h.get('url')}  id={h.get('id')}")
            if not hooks:
                print("WARN no webhooks: inbound SMS will not reach the backend (use --register-webhook)")
    except httpx.HTTPError as e:
        print(f"FAIL cannot reach {base}: {e}")
        return 1

    # 2. device status
    try:
        if cloud:
            r = c.get(f"{base}/devices")
            r.raise_for_status()
            devs = r.json()
            print(f"OK   {len(devs)} device(s): " + ", ".join(
                f"{d.get('name') or d.get('id')} last_seen={d.get('lastSeen')}" for d in devs))
            if not devs:
                ok = False
                print("FAIL no device linked to this cloud account (open the app, enable Cloud server)")
        else:
            r = c.get(f"{base}/health")
            r.raise_for_status()
            h = r.json()
            checks = h.get("checks", {})
            val = lambda k: (checks.get(k) or {}).get("observedValue")
            print(f"OK   device status={h.get('status')} app={h.get('version')} battery={val('battery:level')}% "
                  f"internet={val('connection:status')} failed_last_hour={val('messages:failed')}")
            ok = ok and h.get("status") != "fail"
    except httpx.HTTPError as e:
        print(f"WARN device status not available: {e}")

    # 3. optional webhook registration
    if a.register_webhook:
        for ev in ("sms:received", "sms:sent", "sms:delivered", "sms:failed"):
            r = c.post(f"{base}/webhooks", json={"url": a.register_webhook, "event": ev})
            print(f"{'OK  ' if r.is_success else 'FAIL'} webhook {ev} -> {a.register_webhook} ({r.status_code})")
            ok = ok and r.is_success

    # 4. optional test SMS (uses the same code path as the backend)
    if a.phone:
        os.environ["GATEWAY"] = "android"
        status, gid = gateway.send(a.phone, a.text)
        print(f"{'OK  ' if status == 'queued' else 'FAIL'} test SMS to {a.phone}: {status} id={gid}")
        ok = ok and status == "queued"
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
