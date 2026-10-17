/* ============================================================================
   live.js — the live SMS pages: Alert feed, Users (manual add/delete)
   and the backend status dot. Exposes window.LIVE for the Map alert log.

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
  const TIMEOUT = { approve: 30000 };
  async function api(path, body, method) {
    const headers = {};
    if (API_KEY) headers['X-API-Key'] = API_KEY;
    const opt = body === undefined ? (method ? { method, headers } : { headers }) : {
      method: method || 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify(body),
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
    if (p === 'users') initUserForm();
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

  let mapState = { live: false };
  window.addEventListener('app:state', ev => { mapState = ev.detail || { live: false }; });

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

  // ---- Users (added by an operator; no SMS self-signup) ---------------------
  const ROLE_ORDER = ['farmer', 'herder', 'resident', 'ngo', 'officer'];
  const LANG = { en: 'English', sn: 'Shona', nd: 'Ndebele', fr: 'French' };
  const usersBody = $('#users-body');
  let userSig = null;

  function geoOf(iso3) {
    const g = (window.GEO_DATA || {})[iso3];
    return g && g.features ? g.features.map(f => f.properties).sort((a, b) => String(a.name).localeCompare(b.name)) : [];
  }
  function fillDistricts() {
    const sel = $('#u-district'), iso = $('#u-country').value;
    sel.innerHTML = '';
    geoOf(iso).forEach(p => { const o = el('option', null, p.name); o.value = p.id; sel.append(o); });
  }
  function initUserForm() {
    const cs = $('#u-country');
    if (cs.options.length) return;
    const isos = Object.keys(window.GEO_DATA || {});
    const want = (mapState.iso3 && isos.includes(mapState.iso3)) ? mapState.iso3 : (isos.includes('ZWE') ? 'ZWE' : isos[0]);
    isos.sort().forEach(i => { const o = el('option', null, ((window.REAL && REAL.COUNTRIES && REAL.COUNTRIES[i] && REAL.COUNTRIES[i].name) || i)); o.value = i; cs.append(o); });
    if (want) cs.value = want;
    fillDistricts();
  }

  function userStatus(u) { return u.opted_out_at ? 'opted out' : u.consent_at ? 'active' : 'pending'; }
  async function pollUsers() {
    const d = await api('/feed/users?limit=500');
    const rows = rowsOf(d, 'users').sort((a, b) => b.id - a.id);
    const sig = rows.map(u => `${u.id}|${u.name}|${u.district_name}|${u.role}|${u.language}|${userStatus(u)}`).join(';');
    $('#users-count').textContent = String(rows.filter(u => !u.opted_out_at).length);
    $('#users-empty').hidden = rows.length > 0;
    if (sig === userSig) return;
    userSig = sig;
    usersBody.innerHTML = '';
    for (const u of rows) {
      const tr = el('tr');
      tr.append(el('td', null, u.name || '—'), el('td', 'c-phone', maskPhone(u.phone) || u.phone_masked || ''),
        el('td', null, u.district_name || u.district_id || '—'), el('td', null, u.role || '—'),
        el('td', null, LANG[u.language] || u.language || '—'), el('td', null, userStatus(u)),
        el('td', null, String(u.created_at || '').slice(0, 10)));
      const act = el('td', 'c-act');
      const opt = el('button', 'row-btn', u.opted_out_at ? 'Restore' : 'Opt out');
      opt.type = 'button';
      opt.addEventListener('click', () => userAction(() => api(`/users/${u.id}`, { opted_out: !u.opted_out_at }, 'PATCH')));
      const del = el('button', 'row-btn danger', 'Delete');
      del.type = 'button';
      del.addEventListener('click', () => { if (confirm(`Delete ${u.name || 'this user'}?`)) userAction(() => api(`/users/${u.id}`, undefined, 'DELETE')); });
      act.append(opt, del);
      tr.append(act);
      usersBody.append(tr);
    }
  }
  async function userAction(fn) {
    try { await fn(); userSig = null; await pollUsers(); }
    catch (err) { toast(err.auth ? err.message : err.message); }
  }
  $('#user-form').addEventListener('submit', async ev => {
    ev.preventDefault();
    const f = ev.target, err = $('#u-err');
    err.textContent = '';
    try {
      await api('/users', {
        phone: $('#u-phone').value.trim(), district_id: $('#u-district').value, iso3: $('#u-country').value,
        role: $('#u-role').value, language: $('#u-lang').value, name: $('#u-name').value.trim() || null,
      });
      $('#u-phone').value = ''; $('#u-name').value = '';
      userSig = null;
      await pollUsers();
    } catch (e) {
      const m = e.message;
      err.textContent = /phone/i.test(m) ? 'Phone must look like +263771000001' : m;
    }
  });
  $('#u-country').addEventListener('change', fillDistricts);

  // Keys typed in the phone or pages must not drive the globe timeline.
  $$('.live-page').forEach(p => p.addEventListener('keydown', ev => ev.stopPropagation()));

  // ---- Map alert log hooks ------------------------------------------------
  window.LIVE = {
    get online() { return online; },
    log: iso3 => api('/alerts/log?iso3=' + encodeURIComponent(iso3)),
    approve: async id => { await api(`/events/${id}/approve`, {}); poll(); },
    toast,
  };

  // ---- Crowd signal (spec crowd_crop_status) --------------------------------
  // GET /feed/crowd?iso3=.. every CROWD_MS: per district, share of inbound
  // 1/2/3 reports saying 2 or 3 (consented users, one per user per 7 days).
  // Display-level only: the model's exported levels are untouched. A unit is
  // shown +1 (max Warning, never Emergency) ONLY if share_bad >= 0.6 with
  // >= 3 reports AND the exported row has a satellite family in alarm.
  // Same rule as backend/crowd.py apply_rule; /feed/crowd?t= returns it too.
  const CROWD_MS = 5000;
  const CROWD_RULE = { minReports: 3, minShareBad: 0.6, maxLevel: 2, sat: ['vegetation', 'rain', 'soil'] };
  let crowd = new Map();          // unit_id -> stats from the backend
  let crowdSig = '';
  let crowdBusy = false, crowdLoaded = false;
  const crowdRows = new Map();    // unit_id -> {li, sig}  (Alert feed rows)

  const crowdAlarm = s => !!s && (+s.n_reports || 0) >= CROWD_RULE.minReports &&
    s.share_bad != null && +s.share_bad >= CROWD_RULE.minShareBad;
  const satAlarm = row => !!row && CROWD_RULE.sat.some(k => row.families && row.families[k]);
  const crowdState = (unitId, row) => {
    const s = crowd.get(unitId);
    if (!s || !row || row.level == null || row.missing) return 'none';
    if (!crowdAlarm(s)) return 'below';
    if (!satAlarm(row)) return 'nosat';
    return row.level >= CROWD_RULE.maxLevel ? 'confirms' : 'raised';
  };
  function displayLevel(unitId, row) {
    const st = crowdState(unitId, row);
    return st === 'raised' ? row.level + 1 : row.level;
  }
  const sevClass = s => (s.share_bad == null ? 'sev-0' : +s.share_bad >= 0.6 ? 'sev-3' : +s.share_bad >= 0.3 ? 'sev-2' : 'sev-1');
  const crowdLine = s => {
    const n = +s.n_reports || 0, nf = +s.n_failed || 0, nb = +s.n_bad || 0;
    if (nf > 0) return `${nf} of ${n} say failed${nb > nf ? `, ${nb - nf} poor` : ''}`;
    if (nb > 0) return `${nb} of ${n} say poor`;
    return `${n} of ${n} say ok`;
  };
  const RULE_TXT = {
    raised: 'crowd-confirmed · level shown +1',
    confirms: 'crowd-confirmed · already at Warning',
    nosat: 'not used: no satellite family in alarm',
    below: `below threshold (needs ≥${CROWD_RULE.minReports} reports, ≥${Math.round(CROWD_RULE.minShareBad * 100)}% poor or failed)`,
    none: '',
  };
  // The exported row of a unit for the month on the globe (RISK_DATA is global).
  function rowAt(unitId, t) {
    const R = (window.RISK_DATA || {})[mapState.iso3];
    const u = R && R.units && R.units.find(x => x.id === unitId);
    return u && u.series ? u.series[t] || null : null;
  }

  // Unit panel section (called by app.js renderDetail through window.CROWD).
  function detailSection(unit, row) {
    const s = crowd.get(unit.id);
    const sect = el('div', 'd-sect crowd-sect');
    sect.append(el('span', 'd-lab', 'Crowd reports · SMS, last 30 days'));
    if (online === false) {
      sect.append(el('div', 'crowd-none', 'SMS backend offline — no live reports.'));
      return sect;
    }
    if (!s || !s.n_reports) {
      sect.append(el('div', 'crowd-none', 'No reports yet. Subscribers reply 1 ok · 2 poor · 3 failed.'));
      return sect;
    }
    const st = crowdState(unit.id, row);
    const line = el('div', `crowd-line ${sevClass(s)}`);
    line.append(el('span', 'crowd-ico', '💬'), el('b', null, crowdLine(s)),
      el('span', 'crowd-meta', ` · ${s.n_users || s.n_reports} people · last ${fmtTime(s.last_report_at)}`));
    if (s.n_demo > 0) line.append(el('span', 'tag demo', `${s.n_demo} demo`));
    sect.append(line);
    const rule = el('div', `crowd-rule st-${st}`);
    if (st === 'raised' || st === 'confirms') rule.append(el('span', 'crowd-mark', '✔'));
    rule.append(el('span', null, RULE_TXT[st]));
    if (st === 'raised') rule.append(el('span', 'crowd-meta', ` (model L${row.level} → shown L${row.level + 1})`));
    sect.append(rule);
    return sect;
  }

  // Globe badges: one small 💬 n marker per district with reports.
  function renderBadges() {
    const app = window.APP;
    if (!app || !app.world || typeof app.world.htmlElementsData !== 'function') return;
    if (!mapState.live || !mapState.iso3 || !crowd.size) { app.world.htmlElementsData([]); return; }
    const G = (window.GEO_DATA || {})[mapState.iso3];
    const feats = new Map(G ? G.features.map(f => [f.properties.id, f.properties]) : []);
    const data = [];
    for (const s of crowd.values()) {
      const p = feats.get(s.unit_id);
      if (!p || p.lat == null) continue;
      data.push({ ...s, lat: p.lat, lng: p.lng, state: crowdState(s.unit_id, rowAt(s.unit_id, mapState.t)) });
    }
    app.world
      .htmlLat(d => d.lat).htmlLng(d => d.lng).htmlAltitude(0.03)
      .htmlElement(d => {
        const b = el('div', `crowd-badge ${sevClass(d)}${d.state === 'raised' || d.state === 'confirms' ? ' confirmed' : ''}`);
        b.append(el('span', 'ico', '💬'), el('span', 'n', String(d.n_reports)));
        if (d.state === 'raised') b.append(el('span', 'up', '+1'));
        b.title = `${d.unit_name}: ${crowdLine(d)}${d.n_demo ? ` (${d.n_demo} demo)` : ''} — ${RULE_TXT[d.state] || 'no model level'}`;
        return b;
      })
      .htmlElementsData(data);
  }

  // Alert feed rows: "crowd report: Binga 3 of 4 say failed".
  function renderCrowdAlerts() {
    const list = $('#alerts-list');
    for (const s of crowd.values()) {
      if (!s.n_reports) continue;
      const st = mapState.live ? crowdState(s.unit_id, rowAt(s.unit_id, mapState.t)) : 'none';
      const sig = `${s.n_reports}|${s.n_bad}|${s.n_failed}|${s.last_report_at}|${st}|${s.n_demo}`;
      const old = crowdRows.get(s.unit_id);
      if (old && old.sig === sig) continue;
      const li = el('li', `al-row crowd ${sevClass(s)}`);
      li.dataset.crowd = s.unit_id;
      const top = el('div', 'al-top');
      top.append(el('span', 'al-time', fmtTime(s.last_report_at)), el('span', 'chip crowd-chip', '💬 CROWD'),
        el('span', 'al-unit', `crowd report: ${s.unit_name || s.unit_id} ${crowdLine(s)}`));
      if (s.n_demo > 0) top.append(el('span', 'tag demo', `${s.n_demo} demo`));
      top.append(el('span', 'al-month', `${s.n_users || s.n_reports} people · 30 days`));
      li.append(top);
      const foot = el('div', 'al-foot');
      foot.append(el('span', `crowd-rule st-${st}`, st === 'none'
        ? 'reports only — shown on the map, no level change'
        : RULE_TXT[st] + (st === 'raised' || st === 'confirms' ? ` at ${mapState.label}` : '')));
      li.append(foot);
      if (old) { old.li.replaceWith(li); li.classList.add('is-changed'); }
      else { if (alertsLoaded) li.classList.add('is-new'); list.prepend(li); }
      crowdRows.set(s.unit_id, { li, sig });
    }
    for (const [id, r] of crowdRows) if (!crowd.has(id)) { r.li.remove(); crowdRows.delete(id); }
    $('#alerts-count').textContent = String(alertRows.size + crowdRows.size);
    $('#alerts-empty').hidden = alertRows.size + crowdRows.size > 0;
  }

  function applyCrowd(units) {
    const next = new Map();
    for (const u of units) if (u && u.unit_id) next.set(u.unit_id, u);
    const sig = [...next.values()].map(u => `${u.unit_id}:${u.n_reports}:${u.n_bad}:${u.n_failed}:${u.last_report_at}`).sort().join(';');
    crowd = next;
    if (sig !== crowdSig) {
      crowdSig = sig;
      if (window.APP && typeof APP.repaint === 'function') APP.repaint();
    }
    renderBadges();
    renderCrowdAlerts();
  }

  async function pollCrowd() {
    if (crowdBusy) return;
    if (online === false) { if (crowd.size) applyCrowd([]); return; }
    crowdBusy = true;
    try {
      const iso3 = mapState.iso3 || 'ZWE';
      const d = await api(`/feed/crowd?iso3=${encodeURIComponent(iso3)}`);
      crowdLoaded = true;
      applyCrowd(rowsOf(d, 'units'));
    } catch (_) {
      if (crowd.size) applyCrowd([]);   // offline: crowd disappears, model levels stay
    } finally { crowdBusy = false; }
  }
  // Month or country changed on the globe: badges and feed rows re-evaluate the rule.
  window.addEventListener('app:state', () => { renderBadges(); renderCrowdAlerts(); });
  window.CROWD = { displayLevel, detailSection, state: crowdState, stats: id => crowd.get(id) || null };

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
        if (page === 'users') jobs.push(pollUsers());
        if (!crowdLoaded) jobs.push(pollCrowd());   // first load right away, then every CROWD_MS
        await Promise.all(jobs);
      } else if (crowd.size) applyCrowd([]);
    } catch (_) {
      setOnline(false);
    } finally {
      busy = false;
    }
  }
  setInterval(() => { if (online) pollCrowd(); }, CROWD_MS);

  const start = new URLSearchParams(location.search).get('page');
  if (start && ['alerts', 'users'].includes(start)) show(start);
  else poll();
  setInterval(() => poll(true), POLL_MS);
})();
