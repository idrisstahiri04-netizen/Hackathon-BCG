/* Role (Government | NGO / food bank): chosen on the landing page, kept in localStorage and ?role=.
   Advice is a JS port of backend/recommend.py role_recommend (same library: window.RECS.role_actions). */
window.ROLE = (function () {
  'use strict';
  var LABEL = { gov: 'Government', ngo: 'NGO / Food bank' };
  var PHASE = { 1: 'Minimal', 2: 'Stressed', 3: 'Crisis', 4: 'Emergency', 5: 'Famine' };
  var role = null;
  function read() {
    try { var q = new URLSearchParams(location.search).get('role'); if (LABEL[q]) return q; } catch (e) {}
    try { var v = localStorage.getItem('mapema_role'); if (LABEL[v]) return v; } catch (e) {}
    return null;
  }
  function set(r) {
    role = LABEL[r] ? r : null;
    try { if (role) localStorage.setItem('mapema_role', role); } catch (e) {}
    try {
      var u = new URL(location.href);
      if (role) u.searchParams.set('role', role);
      history.replaceState(null, '', u);
    } catch (e) {}
    document.body.classList.toggle('role-gov', role === 'gov');
    document.body.classList.toggle('role-ngo', role === 'ngo');
    document.querySelectorAll('#role-switch button').forEach(function (b) {
      b.classList.toggle('on', b.dataset.role === role); b.setAttribute('aria-pressed', String(b.dataset.role === role));
    });
    if (window.APP) { APP.repaint(); if (APP.feed) APP.feed(); }
  }
  function fill(t, c) {
    var miss = false;
    var out = t.replace(/\{(\w+)\}/g, function (_, k) { if (c[k] == null) { miss = true; return ''; } return c[k]; });
    return miss ? null : out;
  }
  function recommend(a, r) {
    var lib = window.RECS, lvl = +a.level || 0;
    if (!lib || !lib.role_actions || lvl < 2 || !LABEL[r]) return [];
    var phase = lvl >= 3 ? 'respond' : 'prepare';
    var ev = !a.event || a.event === 'none' ? 'any' : a.event;
    var pop = a.pop, n = a.n_hit, N = a.n_units, pc = a.p_crisis;
    var c = { name: a.county || 'this unit', pop: pop ? Math.round(pop).toLocaleString('en-US') : null,
      ration_t: pop ? Math.round(pop * 15 / 1000).toLocaleString('en-US') : null, n_hit: n, n_units: N,
      pct_units: N && n != null ? Math.round(100 * n / N) : null, unit_word: a.unit_word || 'units' };
    var parts = [c.name + ' at ' + (lvl >= 3 ? 'Emergency' : 'Warning') + ' (L' + lvl + ')'];
    if (pc != null && !isNaN(pc)) parts.push(Math.round(pc * 100) + '% chance of IPC 3+ in the next 3 months');
    if (a.fews_phase) parts.push('FEWS NET projects IPC ' + a.fews_phase + ' (' + (PHASE[a.fews_phase] || '') + ')');
    if (a.drivers && a.drivers.length) parts.push('drivers: ' + a.drivers.slice(0, 3).join('; '));
    var evid = parts.join('. ') + '.';
    return lib.role_actions.filter(function (it) {
      return it.role === r && (it.phase === phase || it.phase === 'both') && (it.events.indexOf(ev) >= 0 || it.events.indexOf('any') >= 0);
    }).sort(function (x, y) { return x.priority - y.priority || (x.id < y.id ? -1 : 1); }).map(function (it) {
      return { id: it.id, role: r, verb: it.verb, action: fill(it.action, c), who: it.who, when: it.when,
        quantity: it.quantity ? fill(it.quantity, c) : null, evidence: evid, source: lib.sources[it.source] || it.source, note: lib.role_note };
    }).filter(function (x) { return x.action; }).slice(0, 5);
  }
  function block(recs) {
    var box = document.createElement('div'); box.className = 'a-recs role-recs';
    var ol = document.createElement('ol');
    recs.forEach(function (x) {
      var li = document.createElement('li');
      var b = document.createElement('b'); b.textContent = x.action; li.append(b);
      [['Who', x.who], ['When', x.when], ['Scale', x.quantity], ['Evidence', x.evidence], ['Source', x.source]].forEach(function (p) {
        if (!p[1]) return;
        var s = document.createElement('small'); s.className = 'rr-' + p[0].toLowerCase();
        s.textContent = p[0] + ': ' + p[1]; li.append(s);
      });
      ol.append(li);
    });
    box.append(ol);
    if (recs[0]) { var n = document.createElement('small'); n.className = 'a-demo'; n.textContent = recs[0].note; box.append(n); }
    return box;
  }
  function forEvent(e, unit, ctxFn) {
    var row = unit && unit.series[e.t];
    return row ? recommend(ctxFn(unit, row, e.t, e.to), role) : [];
  }

  // ---- landing page + header switch
  var LOOP_MS = 4420 + 150;  // mapema-typing.gif total duration (12 frames, read with PIL) + margin
  function start() {
    var p = new URLSearchParams(location.search);
    var skip = p.has('role') || p.has('country') || p.has('skip');
    var land = document.getElementById('landing');
    document.querySelectorAll('#role-switch button').forEach(function (b) {
      b.addEventListener('click', function () { set(b.dataset.role); });
    });
    role = read(); set(role);
    var img = document.getElementById('land-logo');
    function go(r) {
      set(r); land.hidden = true; document.body.classList.remove('on-landing');
      var t = setInterval(function () {
        if (window.APP && APP.selectCountry) { clearInterval(t); if (!new URLSearchParams(location.search).has('country')) APP.selectCountry('Kenya'); }
      }, 100);
    }
    if (skip && role) { land.hidden = true; return; }
    document.body.classList.add('on-landing'); land.hidden = false;
    land.querySelectorAll('[data-pick]').forEach(function (b) { b.addEventListener('click', function () { go(b.dataset.pick); }); });
    img.addEventListener('load', function () { setTimeout(function () { img.src = 'assets/mapema.gif'; img.dataset.state = 'loop'; }, LOOP_MS); }, { once: true });
    img.src = 'assets/mapema-typing.gif'; img.dataset.state = 'typing';
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
  return { get: function () { return role; }, set: set, label: function (r) { return LABEL[r]; }, recommend: recommend, block: block, forEvent: forEvent };
})();
