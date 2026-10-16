/* ============================================================================
   live.js — the live SMS pages: Alert feed, Users joining, Phone simulator,
   the "Run alerts for this month" button and the backend status dot.

   Talks only to the SMS backend (backend/API.md), default http://localhost:8000,
   override with ?api=http://host:port. If the backend is down the globe keeps
   working and these pages say "backend offline". Nothing here is simulated:
   every row comes from the backend.
   ============================================================================ */

(() => {
  'use strict';

  // Base URL: ?api=... beats window.SMS_API_BASE (js/config.local.js, made by
  // backend/make_ui_config.py, gitignored) beats the default.
  const API = (new URLSearchParams(location.search).get('api') || window.SMS_API_BASE ||
    'http://localhost:8000').replace(/\/$/, '');
  // Operator key for /sim/inbound, /alerts/run, approve, cancel. Feeds work
  // without it but come back with masked phone numbers.
  const API_KEY = window.SMS_API_KEY || null;
  const KEY_MSG = 'Admin key missing — run python backend/make_ui_config.py';
  const POLL_MS = 2000;
  const LEVELS = (typeof REAL !== 'undefined' && REAL.LEVELS) || [
    { n: 0, label: 'Normal', color: '#0ca30c', glyph: '●' },
    { n: 1, label: 'Watch', color: '#ffd43b', glyph: '▲' },
    { n: 2, label: 'Warning', color: '#ec833a', glyph: '▲' },
    { n: 3, label: 'Emergency', color: '#d03b3b', glyph: '■' },
  ];
  const EVENTS = (typeof REAL !== 'undefined' && REAL.EVENTS) || {};

  const $ = s => document.querySelector(s);
  const $$ = s => [...document.querySelectorAll(s)];
  const el = (tag, cls, txt) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt != null) n.textContent = txt;
    return n;
  };

  // ---- HTTP -----------------------------------------------------------------
  // Feeds are quick; the router may call Claude (cold start, advice answers)
  // and approve may send many SMS, so those get a long timeout.
  const TIMEOUT = { '/sim/inbound': 20000, '/alerts/run': 30000, approve: 30000 };
  async function api(path, body) {
    const headers = {};
    if (API_KEY) headers['X-API-Key'] = API_KEY;
    const opt = body === undefined ? { headers } : {
      method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    };
    const ctl = new AbortController();
    const ms = TIMEOUT[path] || (path.endsWith('/approve') ? TIMEOUT.approve : 5000);
    const to = setTimeout(() => ctl.abort(), ms);
    try {
      let r;
      try { r = await fetch(API + path, { ...opt, signal: ctl.signal }); }
      catch (err) {
        if (err.name === 'AbortError') { const e = new Error(`no answer after ${ms / 1000} s`); e.timeout = true; throw e; }
        throw err;
      }
      const data = await r.json().catch(() => ({}));
      if (r.status === 401 || r.status === 403) {
        const e = new Error(API_KEY ? 'Admin key rejected — run python backend/make_ui_config.py and reload' : KEY_MSG);
        e.auth = true;
        throw e;
      }
      if (!r.ok) throw new Error(data.detail || data.error || `HTTP ${r.status}`);
      return data;
    } finally { clearTimeout(to); }
  }

  // Accept a bare array or {events|alerts|users|messages|items: [...]}.
  const rowsOf = (d, ...keys) => {
    if (Array.isArray(d)) return d;
    for (const k of [...keys, 'items', 'rows', 'data']) if (d && Array.isArray(d[k])) return d[k];
    return [];
  };

  // ---- Formatting -----------------------------------------------------------
  const pad = n => String(n).padStart(2, '0');
  function fmtTime(iso) {
    if (!iso) return '';
    const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + 'Z');
    if (Number.isNaN(+d)) return String(iso);
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }
  const maskPhone = p => (p && /\*/.test(p) ? String(p) : p ? String(p).replace(/^(\+?\d{3,5})\d*(\d{3})$/, '$1 ••• $2') : '');
  function driversOf(e) {
    if (Array.isArray(e.drivers)) return e.drivers;
    if (e.drivers_json) {
      try { const v = typeof e.drivers_json === 'string' ? JSON.parse(e.drivers_json) : e.drivers_json; return Array.isArray(v) ? v : []; }
      catch (_) { return []; }
    }
    return [];
  }
  // Outgoing SMS status from the gateway: sim / logged / queued / sent /
  // delivered / failed[:reason] / cancelled.
  const isFailed = st => /^(failed|error|cancel)/i.test(String(st || ''));
  function deliveryLabel(st) {
    const s = String(st || '').toLowerCase();
    if (isFailed(s)) return { cls: 'failed', txt: 'failed' + (s.includes(':') ? ` (${s.split(':').slice(1).join(':')})` : '') };
    if (s === 'delivered') return { cls: 'ok', txt: 'delivered' };
    if (s === 'sent') return { cls: 'ok', txt: 'sent' };
    if (s === 'sim') return { cls: 'ok', txt: 'sent (simulator)' };
    if (s === 'logged') return { cls: 'ok', txt: 'logged, no SMS' };
    if (s === 'queued' || s === 'pending' || s === 'processed') return { cls: 'wait', txt: 'sending…' };
    return { cls: '', txt: s };
  }
  // Failed SMS per event, counted from /feed/messages (backend may also send
  // failed_count / sent_ok on the event itself; those win).
  const failedByEvent = new Map();
  const sentOf = e => e.sent_count ?? e.sent_to ?? e.n_sent ?? e.recipients ?? e.sent ?? 0;
  const STATUS = {
    pending_approval: 'Waiting for approval',
    approved: 'Approved',
    sent: 'Sent',
    cancelled: 'Cancelled',
  };

  function levelChip(n) {
    const L = LEVELS[Math.max(0, Math.min(3, +n || 0))];
    const c = el('span', 'chip', `${L.glyph} L${L.n} ${L.label.toUpperCase()}`);
    c.style.background = L.color;
    return c;
  }

  // ---- Backend status -------------------------------------------------------
  let online = null;   // null = unknown yet
  function setOnline(ok, info) {
    if (ok === online) return;
    online = ok;
    const s = $('#be-status');
    s.classList.toggle('up', ok);
    s.classList.toggle('down', !ok);
    s.querySelector('.be-lab').textContent = ok
      ? `backend online${info && info.mock ? ' (mock)' : ''}${API_KEY ? '' : ' · no admin key'}` : 'backend offline';
    s.title = ok && !API_KEY ? KEY_MSG : `SMS backend ${API} — ${ok ? 'online' : 'not reachable'}`;
    $$('.lp-offline').forEach(n => { n.hidden = ok; });
    updateRunButton();
  }
  async function checkHealth() {
    try { const h = await api('/health'); setOnline(true, h); }
    catch (_) { setOnline(false); }
  }

  // ---- Tabs -----------------------------------------------------------------
  let page = 'map';
  function show(p) {
    page = p;
    $$('#tabs [role=tab]').forEach(b => {
      const on = b.dataset.page === p;
      b.classList.toggle('on', on);
      b.setAttribute('aria-selected', String(on));
    });
    $$('.live-page').forEach(s => { s.hidden = s.id !== `page-${p}`; });
    document.body.classList.toggle('on-live', p !== 'map');
    if (p === 'alerts') { seenAlerts = maxAlertId; updateBadge(); }
    if (history.replaceState) {
      const q = new URLSearchParams(location.search);
      if (p === 'map') q.delete('page'); else q.set('page', p);
      const qs = q.toString();
      history.replaceState(null, '', location.pathname + (qs ? `?${qs}` : ''));
    }
    poll();
  }
  $('#tabs').addEventListener('click', ev => {
    const b = ev.target.closest('[role=tab]');
    if (b) show(b.dataset.page);
  });

  // ---- Globe link: Run alerts for this month --------------------------------
  let mapState = { live: false };
  window.addEventListener('app:state', ev => { mapState = ev.detail || { live: false }; updateRunButton(); });
  const runBtn = $('#run-alerts');
  function updateRunButton() {
    runBtn.hidden = !mapState.live;
    runBtn.disabled = !online || runBtn.classList.contains('busy');
    runBtn.title = online
      ? `Create SMS alert events for ${mapState.country || ''} ${mapState.label || ''}`
      : 'SMS backend offline';
  }
  runBtn.addEventListener('click', async () => {
    if (!mapState.live) return;
    runBtn.classList.add('busy');
    updateRunButton();
    const label = runBtn.textContent;
    try {
      const r = await api('/alerts/run', { iso3: mapState.iso3, t: mapState.t });
      const n = r.created ?? rowsOf(r, 'events').length;
      toast(n ? `${n} alert event${n > 1 ? 's' : ''} for ${mapState.label}. See Alert feed.` : `No district changed level in ${mapState.label}.`,
        n ? () => show('alerts') : null);
      poll();
    } catch (err) {
      toast(err.auth ? err.message : `Run alerts failed: ${err.message}`);
    } finally {
      runBtn.classList.remove('busy');
      runBtn.textContent = label;
      updateRunButton();
    }
  });

  let toastTimer = null;
  function toast(msg, onClick) {
    let t = $('#live-toast');
    if (!t) { t = el('div'); t.id = 'live-toast'; t.setAttribute('role', 'status'); document.body.append(t); }
    t.textContent = msg;
    t.onclick = onClick ? () => { onClick(); t.hidden = true; } : null;
    t.classList.toggle('clickable', !!onClick);
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, 5000);
  }

  // ---- Alert feed -----------------------------------------------------------
  const alertRows = new Map();   // id -> {li, sig}
  let maxAlertId = 0, seenAlerts = 0, alertsLoaded = false;

  function updateBadge() {
    const n = [...alertRows.values()].filter(r => r.status === 'pending_approval').length;
    const b = $('#badge-alerts');
    b.textContent = String(n);
    b.hidden = n === 0;
  }

  function buildAlert(e) {
    const lvl = +e.level || 0;
    const li = el('li', 'al-row');
    li.style.setProperty('--lvl', LEVELS[Math.max(0, Math.min(3, lvl))].color);
    li.dataset.id = e.id;

    const top = el('div', 'al-top');
    top.append(el('span', 'al-time', fmtTime(e.created_at)), levelChip(lvl),
      el('span', 'al-unit', e.unit_name || e.unit_id || '—'));
    const evName = EVENTS[e.event] || (e.event && e.event !== 'none' ? e.event : null);
    if (evName) top.append(el('span', 'evt', evName));
    if (e.month_label || e.t != null) top.append(el('span', 'al-month', e.month_label || `month ${e.t}`));
    li.append(top);

    const dr = driversOf(e);
    if (dr.length) {
      const ul = el('ul', 'n-drivers');
      dr.slice(0, 3).forEach(d => ul.append(el('li', null, d)));
      li.append(ul);
    }

    const foot = el('div', 'al-foot');
    const st = el('span', `al-status st-${e.status}`, STATUS[e.status] || e.status || '');
    foot.append(st);
    // Backend gives sent_count (delivered OK) and failed_count separately.
    // Without failed_count, sent_count counts every outgoing SMS, so subtract
    // the failures seen in /feed/messages.
    const total = +sentOf(e) || 0;
    const beFailed = e.failed_count ?? e.n_failed;
    const failed = +(beFailed ?? failedByEvent.get(e.id) ?? 0) || 0;
    const ok = e.sent_ok != null ? +e.sent_ok : beFailed != null ? total : Math.max(0, total - failed);
    foot.append(el('span', 'al-sent', e.status === 'pending_approval' ? 'not sent yet'
      : `sent to ${ok} user${ok === 1 ? '' : 's'}`));
    if (failed > 0 && e.status !== 'pending_approval') foot.append(el('span', 'al-failed', `${failed} failed`));
    if (e.approved_by && e.status !== 'pending_approval') foot.append(el('span', 'al-by', `by ${e.approved_by}`));
    if (e.status === 'pending_approval') {
      const b = el('button', 'approve', 'Approve & send');
      b.type = 'button';
      b.addEventListener('click', () => approve(e.id, b));
      foot.append(b);
    }
    li.append(foot);
    return li;
  }

  async function approve(id, btn) {
    btn.disabled = true;
    btn.textContent = 'Sending…';
    try {
      await api(`/events/${id}/approve`, {});
      await pollAlerts();
    } catch (err) {
      btn.disabled = false;
      btn.textContent = 'Approve & send';
      toast(err.auth ? err.message : `Approve failed: ${err.message}`);
    }
  }

  async function pollAlerts() {
    const [d, dm] = await Promise.all([api('/feed/alerts'), page === 'alerts' ? api('/feed/messages?limit=500') : null]);
    if (dm) {
      failedByEvent.clear();
      for (const m of rowsOf(dm, 'messages')) {
        if (m.direction === 'out' && m.event_id != null && isFailed(m.status)) {
          failedByEvent.set(m.event_id, (failedByEvent.get(m.event_id) || 0) + 1);
        }
      }
    }
    const rows = rowsOf(d, 'events', 'alerts').slice().sort((a, b) => b.id - a.id);
    const list = $('#alerts-list');
    // Insert/replace in id order, newest on top.
    for (const e of rows.slice().reverse()) {
      const sig = `${e.status}|${sentOf(e)}|${e.approved_by || ''}|${e.failed_count ?? failedByEvent.get(e.id) ?? 0}`;
      const old = alertRows.get(e.id);
      if (old && old.sig === sig) continue;
      const li = buildAlert(e);
      if (old) {
        old.li.replaceWith(li);
        li.classList.add('is-changed');
      } else {
        if (alertsLoaded) li.classList.add('is-new');
        list.prepend(li);
      }
      alertRows.set(e.id, { li, sig, status: e.status });
      maxAlertId = Math.max(maxAlertId, e.id);
    }
    alertsLoaded = true;
    if (page === 'alerts') seenAlerts = maxAlertId;
    $('#alerts-count').textContent = String(alertRows.size);
    $('#alerts-empty').hidden = alertRows.size > 0;
    updateBadge();
  }

  // ---- Users joining --------------------------------------------------------
  const ROLE_ORDER = ['farmer', 'herder', 'resident', 'ngo', 'officer'];
  const ROLE_LABEL = { farmer: 'Farmers', herder: 'Herders', resident: 'Residents', ngo: 'NGOs', officer: 'Officers' };
  const LANG = { en: 'English', sn: 'Shona', nd: 'Ndebele', ny: 'Chichewa', bem: 'Bemba', fr: 'French', ar: 'Arabic' };
  let users = new Map();       // id -> user
  let usersByPhone = new Map();
  let messages = new Map();    // id -> message
  let joinLoaded = false;

  function bump(node, val) {
    const v = String(val);
    if (node.textContent !== v) {
      node.textContent = v;
      node.classList.remove('bump');
      void node.offsetWidth;
      node.classList.add('bump');
    }
  }

  async function pollUsers() {
    const [du, dm] = await Promise.all([api('/feed/users'), api('/feed/messages')]);
    rowsOf(du, 'users').forEach(u => { users.set(u.id, u); if (u.phone) usersByPhone.set(u.phone, u); });
    rowsOf(dm, 'messages').forEach(m => messages.set(m.id, m));
    if (page === 'phone' && phNum.value.trim()) {
      const dp = await api('/feed/messages?phone=' + encodeURIComponent(phNum.value.trim()));
      rowsOf(dp, 'messages').forEach(m => messages.set(m.id, m));
    }

    const c = (du && du.counters) || {};
    const active = [...users.values()].filter(u => !u.opted_out_at);
    const byRole = c.by_role || active.reduce((a, u) => ((a[u.role] = (a[u.role] || 0) + 1), a), {});
    bump($('#ctr-total'), c.total ?? active.length);
    const today = new Date().toISOString().slice(0, 10);
    bump($('#ctr-today'), c.today ?? active.filter(u => String(u.created_at).startsWith(today)).length);
    const roles = $('#ctr-roles');
    const keys = [...ROLE_ORDER, ...Object.keys(byRole).filter(k => !ROLE_ORDER.includes(k))];
    keys.forEach(k => {
      let box = roles.querySelector(`[data-role="${k}"]`);
      if (!box) {
        box = el('div', 'ctr role');
        box.dataset.role = k;
        box.append(el('span', 'ctr-val', '0'), el('span', 'ctr-lab', ROLE_LABEL[k] || k));
        roles.append(box);
      }
      bump(box.querySelector('.ctr-val'), byRole[k] || 0);
    });

    renderJoinTable();
    if (page === 'phone') renderPhone();
  }

  function renderJoinTable() {
    const body = $('#join-body');
    const inbound = [...messages.values()].filter(m => m.direction === 'in').sort((a, b) => a.id - b.id);
    for (const m of inbound) {
      const u = (m.user_id != null && users.get(m.user_id)) || null;
      const key = `${m.id}|${u ? u.id : ''}|${m.intent || ''}`;
      const prev = body.querySelector(`tr[data-id="${m.id}"]`);
      if (prev && prev.dataset.key === key) continue;
      const tr = el('tr');
      tr.dataset.id = m.id;
      tr.dataset.key = key;

      const tdT = el('td', 'c-time');
      tdT.append(el('span', null, fmtTime(m.created_at)), el('span', 'c-phone', maskPhone(m.phone)));
      const tdS = el('td', 'c-sms');
      tdS.append(el('span', 'bubble', m.text || ''));
      const tdI = el('td', 'c-intent');
      if (m.intent) {
        const conf = m.intent_confidence == null ? null : Math.round(+m.intent_confidence * 100);
        const it = el('span', `intent i-${m.intent}`, m.intent.replace(/_/g, ' '));
        tdI.append(it);
        if (conf != null) {
          const bar = el('span', 'conf');
          const fill = el('i');
          fill.style.width = `${Math.max(0, Math.min(100, conf))}%`;
          bar.append(fill);
          tdI.append(bar, el('span', 'conf-n', `${conf}%`));
        }
      } else tdI.append(el('span', 'muted', '…'));
      const tdU = el('td', 'c-saved');
      if (u && (m.intent === 'subscribe' || m.intent === 'change_info' || !m.intent)) {
        tdU.append(el('b', null, u.district_name || u.district_id || '?'),
          el('span', null, ` · ${u.role || '?'} · ${LANG[u.language] || u.language || '?'}`));
      } else if (m.intent === 'subscribe') {
        tdU.append(el('span', 'muted', 'not saved yet (asked to confirm)'));
      } else tdU.append(el('span', 'muted', '—'));
      tr.append(tdT, tdS, tdI, tdU);

      if (prev) prev.replaceWith(tr);
      else {
        if (joinLoaded) tr.classList.add('is-new');
        body.prepend(tr);
      }
    }
    while (body.children.length > 200) body.lastChild.remove();
    joinLoaded = true;
    $('#users-empty').hidden = inbound.length > 0;
  }

  // ---- Phone simulator ------------------------------------------------------
  const phNum = $('#ph-number'), phText = $('#ph-text'), phThread = $('#ph-thread');
  const pending = [];  // optimistic outgoing bubbles not yet seen in the feed
  let phoneSig = '';
  let thinking = 0;    // requests waiting for the router (Claude)
  let lastFrom = '';

  function renderPhone() {
    const me = phNum.value.trim();
    // Without the key the backend masks numbers (+263****001), so match that.
    const meMasked = me.length > 7 ? me.slice(0, 4) + '****' + me.slice(-3) : '****';
    const mine = [...messages.values()]
      .filter(m => m.phone === me || (!API_KEY && m.phone === meMasked))
      .sort((a, b) => a.id - b.id);
    const left = pending.filter(p => p.phone === me &&
      !mine.some(m => m.direction === 'in' && m.text === p.text && m.id > p.after));
    const sig = me + '|' + mine.map(m => `${m.id}:${m.status}`).join(',') + '|' +
      left.map(p => p.state).join(',') + '|' + thinking;
    if (sig === phoneSig) return;
    phoneSig = sig;
    phThread.innerHTML = '';
    if (!mine.length && !left.length) {
      phThread.append(el('div', 'ph-hint', 'Try: JOIN Mbire farmer · 2 · STOP'));
    }
    for (const m of mine) {
      const b = el('div', `ph-msg ${m.direction === 'in' ? 'me' : 'them'}`);
      b.append(el('span', 'ph-txt', m.text || ''));
      const meta = el('span', 'ph-meta', fmtTime(m.created_at) + (m.direction === 'in' && m.intent ? ` · ${m.intent}` : ''));
      if (m.direction === 'out' && m.status) {
        const d = deliveryLabel(m.status);
        meta.append(' · ', el('span', `dl ${d.cls}`, d.txt));
        if (d.cls === 'failed') b.classList.add('failed');
      }
      b.append(meta);
      phThread.append(b);
    }
    for (const p of left) {
      const b = el('div', `ph-msg me ${p.state === 'failed' ? 'failed' : 'sending'}`);
      const meta = el('span', 'ph-meta');
      meta.append(p.state === 'failed' ? el('span', 'dl failed', `not delivered: ${p.err}`) : 'sending…');
      b.append(el('span', 'ph-txt', p.text), meta);
      phThread.append(b);
    }
    if (thinking > 0 && me === lastFrom) {
      const b = el('div', 'ph-msg them thinking');
      b.append(el('span', 'ph-txt', 'Claude is thinking…'));
      phThread.append(b);
    }
    phThread.scrollTop = phThread.scrollHeight;
  }

  async function sendSms(text) {
    text = text.trim();
    const from = phNum.value.trim();
    if (!text || !from) return;
    const after = Math.max(0, ...messages.keys());
    const p = { phone: from, text, after, state: 'sending' };
    pending.push(p);
    lastFrom = from;
    thinking++;
    renderPhone();
    let ok = true;
    try {
      await api('/sim/inbound', { from, text });
    } catch (err) {
      // A timeout is not a failure: the router may still answer, and the
      // reply will appear through polling. Only a real error marks it failed.
      if (!err.timeout) { ok = false; p.state = 'failed'; p.err = err.message; if (err.auth) toast(err.message); }
      else toast('Still waiting for the reply. It will appear here when ready.');
    } finally {
      thinking--;
    }
    try { await pollUsers(); } catch (_) {}
    if (ok) pending.splice(pending.indexOf(p), 1);
    phoneSig = '';
    renderPhone();
  }

  $('#ph-form').addEventListener('submit', ev => {
    ev.preventDefault();
    const t = phText.value;
    phText.value = '';
    phLen();
    sendSms(t);
  });
  $('#ph-quick').addEventListener('click', ev => {
    const b = ev.target.closest('button');
    if (b) sendSms(b.textContent);
  });
  $('#ph-new').addEventListener('click', () => {
    phNum.value = '+26377' + String(Math.floor(1e6 + Math.random() * 9e6));
    phoneSig = '';
    renderPhone();
  });
  phNum.addEventListener('input', () => { phoneSig = ''; renderPhone(); });
  function phLen() {
    const n = phText.value.length;
    $('#ph-len').textContent = `${n}/160`;
  }
  phText.addEventListener('input', phLen);
  // Keys typed in the phone or pages must not drive the globe timeline.
  $$('.live-page').forEach(p => p.addEventListener('keydown', ev => ev.stopPropagation()));

  // ---- Polling loop ---------------------------------------------------------
  // While offline, retry /health every 10 s instead of every 2 s: Chrome logs
  // each refused connection as a console error and that cannot be silenced.
  let busy = false, tick = 0;
  async function poll(fromTimer) {
    if (busy) return;
    if (fromTimer === true && online === false && (++tick % 5)) return;
    busy = true;
    try {
      await checkHealth();
      if (online) {
        // Alerts are always polled so the tab badge counts pending approvals.
        const jobs = [pollAlerts()];
        if (page === 'users' || page === 'phone') jobs.push(pollUsers());
        await Promise.all(jobs);
      }
    } catch (_) {
      setOnline(false);
    } finally {
      busy = false;
    }
  }

  const start = new URLSearchParams(location.search).get('page');
  if (start && ['alerts', 'users', 'phone'].includes(start)) show(start);
  else poll();
  setInterval(() => poll(true), POLL_MS);
})();
