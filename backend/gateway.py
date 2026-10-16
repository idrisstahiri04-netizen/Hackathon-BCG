"""Outbound SMS gateway: GATEWAY=android|sim|log.

android = capcom6 "SMS Gateway for Android" (github.com/capcom6/android-sms-gateway,
docs.sms-gate.app). Send API (checked 2026-10-16):
  local mode : POST http://<phone-ip>:8080/message                  (Basic auth from app Home tab)
  cloud mode : POST https://api.sms-gate.app/3rdparty/v1/messages   (Basic auth, cloud credentials)
  body       : {"textMessage": {"text": "..."}, "phoneNumbers": ["+2126..."]}
  response   : JSON with "id" (used to match sms:sent / sms:delivered / sms:failed webhooks)
sim / log  = no real SMS; the row in `messages` is what the on-screen phone shows.
"""
from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger("gateway")


def mode() -> str:
    return os.environ.get("GATEWAY", "sim").lower()


def _android_send(phone: str, text: str) -> tuple[str, str | None]:
    base = os.environ.get("ANDROID_GW_URL", "").rstrip("/")
    if not base:
        return "failed:no ANDROID_GW_URL", None
    path = "/messages" if "3rdparty" in base else "/message"
    body: dict = {"phoneNumbers": [phone]}
    if os.environ.get("ANDROID_GW_LEGACY") == "1":  # very old app versions
        body["message"] = text
    else:
        body["textMessage"] = {"text": text}
    auth = (os.environ.get("ANDROID_GW_USER", ""), os.environ.get("ANDROID_GW_PASS", ""))
    try:
        r = httpx.post(base + path, json=body, auth=auth, timeout=15,
                       verify=os.environ.get("ANDROID_GW_VERIFY_TLS", "1") != "0")
        r.raise_for_status()
        gid = None
        try:
            gid = r.json().get("id")
        except ValueError:
            pass
        return "queued", gid
    except httpx.HTTPError as e:  # network down, 401, ...
        log.warning("android gateway send failed: %s", e)
        return f"failed:{type(e).__name__}", None


def _daily_sent() -> int:
    from . import db
    r = db.q1("SELECT COUNT(*) n FROM messages WHERE direction='out' AND status IN ('queued','sent','delivered') "
              "AND created_at >= strftime('%Y-%m-%dT%H:%M:%S', 'now', '-1 day')")
    return r["n"] if r else 0


def send(phone: str, text: str) -> tuple[str, str | None]:
    """Send one SMS. Returns (status, gateway_id). Never raises."""
    m = mode()
    if m == "android":
        if _daily_sent() >= int(os.environ.get("DAILY_SEND_CAP", "500")):  # protects the SIM / budget
            log.warning("daily send cap reached; not sending")
            return "failed:daily_cap", None
        return _android_send(phone, text)
    if m == "log":
        log.info("SMS to %s****%s (%d chars)", phone[:4], phone[-3:], len(text))
        return "logged", None
    return "sim", None
