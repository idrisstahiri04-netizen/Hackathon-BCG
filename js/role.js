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
  // Same rule as backend role_tier: FEWS NET phase drives it (3 prepare, 4-5 respond);
  // without FEWS, our alert level (L2 prepare, L3 respond). Returns {phase, basis} or null.
  function tier(a) {
    var lvl = +a.level || 0, fp = a.fews_phase ? Math.round(+a.fews_phase) : 0;
    if (fp) {
      var b = 'Based on: FEWS NET Phase ' + fp;
      if (fp >= 4) return { phase: 'respond', basis: b };
      if (fp === 3 || lvl >= 2) return { phase: 'prepare', basis: b };
      return null;
    }
    if (lvl >= 3) return { phase: 'respond', basis: 'Based on: our model' };
    if (lvl === 2) return { phase: 'prepare', basis: 'Based on: our model' };
    return null;
  }
  function recommend(a, r) {
    var lib = window.RECS, lvl = +a.level || 0, t = tier(a);
    if (!lib || !lib.role_actions || !t || !LABEL[r]) return [];
    var phase = t.phase;
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
      return { id: it.id, role: r, phase: phase, basis: t.basis, verb: it.verb, action: fill(it.action, c), who: it.who, when: it.when,
        quantity: it.quantity ? fill(it.quantity, c) : null, evidence: evid, source: lib.sources[it.source] || it.source, note: lib.role_note };
    }).filter(function (x) { return x.action; }).slice(0, 4);
  }
  function block(recs) {
    var box = document.createElement('div'); box.className = 'a-recs role-recs';
    var ul = document.createElement('ul');
    recs.forEach(function (x) { var li = document.createElement('li'); li.textContent = x.action; ul.append(li); });
    box.append(ul);
    if (recs[0] && recs[0].basis) { var bs = document.createElement('small'); bs.className = 'a-demo role-basis'; bs.textContent = recs[0].basis; box.append(bs); }
    var src = recs.map(function (x) { return x.source; }).filter(function (v, i, a) { return v && a.indexOf(v) === i; }).join('\n');
    if (src) { var n = document.createElement('small'); n.className = 'a-demo'; n.textContent = 'sources'; n.title = src; box.append(n); }
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
