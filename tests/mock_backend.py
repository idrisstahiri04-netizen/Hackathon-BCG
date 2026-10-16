"""Tiny stand-in for backend/app.py so the live UI (js/live.js) can be built
and tested before the real backend exists. Standard library only.

    python3 tests/mock_backend.py --port 8001 [--auto]

then open http://localhost:8777/?api=http://localhost:8001

Response shapes (js/live.js also accepts plain arrays and a few aliases):
  GET  /health                 {"ok": true, "gateway": "sim", "mock": true}
  GET  /feed/alerts?since=id   {"events":   [event, ...]}   newest first
  GET  /feed/users?since=id    {"users":    [user, ...], "counters": {"total", "today", "by_role": {role: n}}}
  GET  /feed/messages?since=id {"messages": [message, ...]}
  POST /alerts/run {iso3, t}   {"created": n, "events": [...]}
  POST /events/{id}/approve    {"ok": true, "event": event, "sent": n}
  POST /sim/inbound {from,text}{"ok": true, "reply": str, "intent": str, "intent_confidence": float}
  event   = id, created_at, iso3, unit_id, unit_name, t, month_label, level, event, p,
            drivers (list), status, approved_by, sent_count
--auto adds a fake sign-up every 7 s (mock only; never used by the globe).
"""
import argparse
import json
import random
import re
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent.parent
MONTHS = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()
ROLES = ['farmer', 'herder', 'ngo', 'officer', 'resident']
LOCK = threading.Lock()
DB = {'events': [], 'users': [], 'messages': [], 'help': []}
SEQ = {'events': 0, 'users': 0, 'messages': 0}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def nid(k):
    SEQ[k] += 1
    return SEQ[k]


def load_js(kind, iso3):
    p = ROOT / 'data' / kind / f'{iso3}.js'
    if not p.exists():
        return None
    txt = p.read_text()
    m = re.search(r'\[\s*"%s"\s*\]\s*=\s*' % iso3, txt)
    if not m:
        return None
    body = txt[m.end():].strip().rstrip(';')
    return json.loads(body)


_UNITS = {}


def unit_names(iso3='ZWE'):
    if iso3 not in _UNITS:
        g = load_js('geo', iso3) or {'features': []}
        _UNITS[iso3] = [f['properties']['name'] for f in g['features']]
    return _UNITS[iso3]


def add_msg(direction, phone, text, user_id=None, event_id=None, intent=None, conf=None, status='stored'):
    m = dict(id=nid('messages'), created_at=now(), direction=direction, phone=phone, user_id=user_id,
             event_id=event_id, text=text, intent=intent, intent_confidence=conf, status=status)
    DB['messages'].append(m)
    return m


def route(phone, text):
    """Keyword router standing in for the Claude router."""
    t = text.strip()
    up = t.upper()
    user = next((u for u in DB['users'] if u['phone'] == phone and not u['opted_out_at']), None)
    if up == 'STOP':
        intent, conf, reply = 'stop', 1.0, 'You are unsubscribed. Send JOIN to start again.'
        if user:
            user['opted_out_at'] = now()
    elif up in ('1', '2', '3'):
        intent, conf = 'report', 1.0
        reply = 'Thank you. Your crop report was saved.' if user else 'Send JOIN <district> <role> first.'
    elif 'JOIN' in up or 'register' in t.lower() or 'murimi' in t.lower() or 'sign' in t.lower():
        names = unit_names('ZWE')
        dist = next((n for n in names if n.lower() in t.lower()), None)
        role = next((r for r in ROLES if r in t.lower()), 'farmer')
        lang = 'sn' if re.search(r'\b(ndi|ndiri|mhoro)\b', t.lower()) else 'en'
        if not dist:
            intent, conf, reply = 'subscribe', 0.62, 'Which district do you live in? Reply with the name.'
        else:
            intent, conf = 'subscribe', 0.94
            user = dict(id=nid('users'), created_at=now(), phone=phone, name=None, district_id=None,
                        district_name=dist, iso3='ZWE', role=role, language=lang, consent_at=now(),
                        opted_out_at=None, raw_signup_text=t)
            DB['users'].append(user)
            reply = f'Saved: {dist}, {role}. You will get drought alerts. Reply YES to confirm, STOP to quit.'
    elif 'help' in t.lower() or 'food' in t.lower():
        intent, conf, reply = 'ask_help', 0.88, 'An officer will contact you.'
        DB['help'].append(dict(user_id=user and user['id'], text=t))
    elif '?' in t:
        intent, conf, reply = 'ask_advice', 0.81, 'Plant short-season seed after 2 good rains. Keep 2 months of grain.'
    else:
        intent, conf, reply = 'unknown', 0.35, 'Sorry, we did not understand. Send JOIN <district> <role>, or STOP.'
    add_msg('in', phone, t, user and user['id'], intent=intent, conf=conf, status='received')
    add_msg('out', phone, reply, user and user['id'], intent=intent, status='sent')
    return dict(ok=True, reply=reply, intent=intent, intent_confidence=conf)


def run_alerts(iso3, t):
    R = load_js('risk', iso3)
    if not R:
        return 404, {'error': f'no risk file for {iso3}'}
    created = []
    for u in R['units']:
        s = u['series']
        if t >= len(s) or t < 1:
            continue
        cur, prev = s[t]['level'], s[t - 1]['level']
        if cur < 1 or cur <= prev:
            continue
        st = 'pending_approval' if cur >= 2 else 'approved'
        e = dict(id=nid('events'), created_at=now(), iso3=iso3, unit_id=u['id'], unit_name=u['name'], t=t,
                 month_label=f"{MONTHS[t % 12]} {R['meta']['start_year'] + t // 12}", level=cur,
                 event=s[t].get('event'), p=s[t].get('p'), drivers=s[t].get('drivers') or [],
                 status=st, approved_by='auto (Watch)' if st == 'approved' else None,
                 sent_count=random.randint(1, 4) if st == 'approved' else 0)
        DB['events'].append(e)
        created.append(e)
    return 200, {'created': len(created), 'events': created}


def approve(eid):
    e = next((x for x in DB['events'] if x['id'] == eid), None)
    if not e:
        return 404, {'error': 'no such event'}
    if e['status'] == 'pending_approval':
        targets = [u for u in DB['users'] if u['district_name'] == e['unit_name'] and not u['opted_out_at']]
        n = len(targets) + random.randint(8, 40)
        for u in targets:
            add_msg('out', u['phone'], f"WARNING {e['unit_name']}: crops drying. Keep 2 months of grain. STOP to quit",
                    u['id'], e['id'], status='sent')
        e.update(status='sent', approved_by='demo officer', sent_count=n)
    return 200, {'ok': True, 'event': e, 'sent': e['sent_count']}


def since(rows, qs):
    try:
        s = int(qs.get('since', ['0'])[0])
    except ValueError:
        s = 0
    return [r for r in reversed(rows) if r['id'] > s][:200]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.end_headers()
        self.wfile.write(b)

    def do_OPTIONS(self):
        self.send(204, {})

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        with LOCK:
            if u.path == '/health':
                return self.send(200, {'ok': True, 'gateway': 'sim', 'mock': True})
            if u.path == '/feed/alerts':
                return self.send(200, {'events': since(DB['events'], qs)})
            if u.path == '/feed/messages':
                return self.send(200, {'messages': since(DB['messages'], qs)})
            if u.path == '/feed/users':
                today = datetime.now(timezone.utc).date().isoformat()
                live = [x for x in DB['users'] if not x['opted_out_at']]
                by = {}
                for x in live:
                    by[x['role']] = by.get(x['role'], 0) + 1
                return self.send(200, {'users': since(DB['users'], qs), 'counters': {
                    'total': len(live), 'today': sum(x['created_at'].startswith(today) for x in live),
                    'by_role': by}})
        self.send(404, {'error': 'not found'})

    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        try:
            body = json.loads(self.rfile.read(n) or b'{}')
        except json.JSONDecodeError:
            return self.send(400, {'error': 'bad json'})
        p = urlparse(self.path).path
        with LOCK:
            if p in ('/sim/inbound', '/sms/inbound'):
                frm, text = body.get('from') or body.get('phone'), body.get('text') or body.get('message')
                if not frm or not text:
                    return self.send(400, {'error': 'need from and text'})
                return self.send(200, route(str(frm), str(text)))
            if p == '/alerts/run':
                return self.send(*run_alerts(str(body.get('iso3', '')).upper(), int(body.get('t', 0))))
            m = re.fullmatch(r'/events/(\d+)/approve', p)
            if m:
                return self.send(*approve(int(m.group(1))))
        self.send(404, {'error': 'not found'})


SAMPLES = ['JOIN Mbire farmer', 'Ndiri murimi ku Binga, JOIN', 'JOIN Gwanda herder please',
           'register me Chiredzi officer', 'JOIN Hwange resident', 'I want to sign up, Mudzi farmer',
           'JOIN Beitbridge herder', 'JOIN Kariba ngo']


def auto_loop():
    i = 0
    while True:
        time.sleep(7)
        with LOCK:
            route(f'+26377{random.randint(1000000, 9999999)}', SAMPLES[i % len(SAMPLES)])
        i += 1


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8001)
    ap.add_argument('--auto', action='store_true')
    a = ap.parse_args()
    if a.auto:
        threading.Thread(target=auto_loop, daemon=True).start()
    print(f'mock backend on http://localhost:{a.port}')
    ThreadingHTTPServer(('127.0.0.1', a.port), H).serve_forever()
