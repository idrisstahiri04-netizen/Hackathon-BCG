/* ============================================================================
   app.js — globe, roles, timeline, markers and the alert feed.

   State that matters:
     role        'ngo' | 'gov'        — changes every recommendation shown
     resolution  'county'|'subcounty' — 47 units or 290
     now         index into the real FEWS NET publication dates
     liveMode    replay vs current situation

   Everything on screen is a pure function of those four. No simulated values
   anywhere: the timeline steps through real FEWS NET releases.
   ============================================================================ */

(() => {
  'use strict';

  const $ = s => document.querySelector(s);
  const el = (tag, cls, txt) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt != null) n.textContent = txt;
    return n;
  };

  const COUNTRIES = [
    { name: 'Kenya',       lat:  0.53, lng: 37.86, alt: 0.38, live: true },
    { name: 'Ethiopia',    lat:  9.10, lng: 40.50, alt: 0.65 },
    { name: 'Somalia',     lat:  5.15, lng: 46.20, alt: 0.65 },
    { name: 'Uganda',      lat:  1.37, lng: 32.29, alt: 0.65 },
    { name: 'Tanzania',    lat: -6.37, lng: 34.89, alt: 0.65 },
    { name: 'Zimbabwe',    lat:-19.02, lng: 29.15, alt: 0.65 },
    { name: 'Zambia',      lat:-13.13, lng: 27.85, alt: 0.65 },
    { name: 'Malawi',      lat:-13.25, lng: 34.30, alt: 0.65 },
    { name: 'Niger',       lat: 17.61, lng:  8.08, alt: 0.65 },
    { name: 'Sudan',       lat: 15.60, lng: 30.22, alt: 0.65 },
    { name: 'South Sudan', lat:  7.86, lng: 29.69, alt: 0.65 },
    { name: 'Nigeria',     lat:  9.08, lng:  8.68, alt: 0.65 },
    { name: 'Madagascar',  lat:-18.77, lng: 46.87, alt: 0.65 },
    { name: 'Morocco',     lat: 31.79, lng: -7.09, alt: 0.65 },
  ];
  const WORLD_VIEW = { lat: 6, lng: 24, altitude: 2.3 };

  // Markers are the loud part of the UI, so they must stay legible. Past this
  // many we show the worst and say how many were held back.
  const MAX_MARKERS = 22;

  let TIMELINE = null;
  let MODEL = null;
  let LIVE = null;

  let role = null;
  let resolution = 'subcounty';
  let now = 0;
  let rendered = -1;
  let playing = false, speed = 1, timer = null;
  let active = null, selected = null, hovered = null;
  let liveMode = false;
  let smsAudience = null;

  const featuresFor = r =>
    r === 'county' ? KENYA_COUNTIES.features : KENYA_SUBCOUNTIES.features;
  const levelColor = n => ENGINE.LEVELS[n].color;

  // =========================================================================
  //  Role
  // =========================================================================
  function buildRolePicker() {
    const wrap = $('#role-picker');
    Object.values(ROLES.DEFS).forEach(r => {
      const b = el('button', 'role-opt');
      b.dataset.role = r.id;
      b.innerHTML =
        `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${r.icon}"/></svg>` +
        `<span class="ro-l">${r.label}</span>` +
        `<span class="ro-b">${r.blurb}</span>` +
        `<span class="ro-q">${r.question}</span>`;
      b.addEventListener('click', () => setRole(r.id, true));
      wrap.append(b);
    });
  }

  function setRole(id, dismiss) {
    role = id;
    const def = ROLES.DEFS[id];
    const badge = $('#role-badge');
    badge.innerHTML =
      `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${def.icon}"/></svg>` +
      `<span>${def.label}</span>`;
    badge.dataset.role = id;
    document.body.dataset.role = id;
    if (dismiss) {
      $('#login').classList.add('gone');
      setTimeout(() => { $('#login').hidden = true; }, 380);
      searchInput.focus();
    }
    // Everything downstream of role has to be rebuilt, not just restyled.
    if (MODEL && active) {
      renderFeed({ rebuild: true });
      renderMarkers();
      if (selected) renderDetail();
    }
  }

  // =========================================================================
  //  Globe
  // =========================================================================
  const globeEl = $('#globe');
  const world = Globe()(globeEl)
    .globeImageUrl('vendor/earth-blue-marble.jpg')
    .bumpImageUrl('vendor/earth-topology.png')
    .backgroundColor('rgba(0,0,0,0)')
    .showAtmosphere(true)
    .atmosphereColor('#5b8fd0')
    .atmosphereAltitude(0.17)
    .polygonGeoJsonGeometry(d => d.geometry)
    .polygonsTransitionDuration(380)
    .polygonLabel(() => '')
    .onPolygonHover(p => { hovered = p || null; globeEl.style.cursor = p ? 'pointer' : ''; paintGlobe(); })
    .onPolygonClick(p => { selected = p; smsAudience = null; paintGlobe(); renderDetail(); })
    .htmlElementsData([])
    .htmlLat(d => d.lat)
    .htmlLng(d => d.lng)
    .htmlAltitude(0.04)
    .htmlElement(markerElement);

  world.pointOfView(WORLD_VIEW, 0);
  world.controls().autoRotate = true;
  world.controls().autoRotateSpeed = 0.32;
  world.controls().enableDamping = true;

  const fit = () => world.width(globeEl.clientWidth).height(globeEl.clientHeight);
  fit();
  new ResizeObserver(fit).observe(globeEl);

  const unitAt = name => (MODEL ? MODEL.byName.get(name) : null);

  // Single source of truth for "what level is this unit showing".
  function levelAt(name) {
    if (liveMode) return liveLevel(name);
    const u = unitAt(name);
    const lv = u ? u.series[now].level : null;
    return lv == null ? 0 : lv;
  }
  function hasData(name) {
    if (liveMode) return !!(LIVE && LIVE.current && LIVE.current[liveKey(name)]);
    const u = unitAt(name);
    return !!(u && u.series[now].hasData);
  }

  function paintGlobe() {
    if (!active || !active.live || !MODEL) return;
    world
      .polygonAltitude(d => {
        const base = 0.006 + levelAt(d.properties.name) * 0.006;
        return d === selected || d === hovered ? base + 0.012 : base;
      })
      .polygonCapColor(d => {
        const n = d.properties.name;
        if (!hasData(n)) return '#55555540';            // honest "no coverage"
        const lvl = levelAt(n);
        const c = levelColor(lvl);
        return d === selected ? c : c + (lvl === 0 ? 'a8' : 'd8');
      })
      .polygonSideColor(d => levelColor(levelAt(d.properties.name)) + '55')
      .polygonStrokeColor(d =>
        d === selected ? '#ffffff' : d === hovered ? '#ffffffaa' : '#00000044');
  }

  // =========================================================================
  //  Pulsing alert markers
  // =========================================================================
  // A colour change on a map is easy to miss, especially across 290 units.
  // A pulsing marker over a deteriorating area is not.
  const markerEls = new Map();
  function markerElement(d) {
    const wrap = document.createElement('div');
    wrap.className = `mk lvl-${d.level}`;
    markerEls.set(d.name, { el: wrap, d });
    wrap.innerHTML = '<span class="mk-ring"></span><span class="mk-dot"></span>';
    wrap.addEventListener('mouseenter', () => showTip(d, wrap));
    wrap.addEventListener('mouseleave', hideTip);
    wrap.addEventListener('click', ev => {
      ev.stopPropagation();
      const f = featuresFor(resolution).find(x => x.properties.name === d.name);
      if (f) {
        selected = f;
        smsAudience = null;
        world.pointOfView({ lat: d.lat, lng: d.lng, altitude: 0.26 }, 850);
        paintGlobe();
        renderDetail();
      }
    });
    return wrap;
  }

  function renderMarkers() {
    const old = $('#marker-overflow');
    if (old) old.remove();
    if (!MODEL || !active || !active.live) { world.htmlElementsData([]); return; }
    const rows = [];
    for (const f of featuresFor(resolution)) {
      const n = f.properties.name;
      if (!hasData(n)) continue;
      const lvl = levelAt(n);
      if (lvl < 2) continue;                       // Crisis and above only
      rows.push({
        name: n,
        county: f.properties.county || n,
        lat: f.properties.lat, lng: f.properties.lng,
        level: lvl,
        zones: f.properties.zones || (unitAt(n) || {}).zones || [],
      });
    }
    rows.sort((a, b) => b.level - a.level || a.name.localeCompare(b.name));
    const shown = rows.slice(0, MAX_MARKERS);
    markerEls.clear();
    world.htmlElementsData(shown);
    if (rows.length > shown.length) {
      const n = el('div', null, `+${rows.length - shown.length} more at Crisis+ not pinned`);
      n.id = 'marker-overflow';
      $('#globe-col').append(n);
    }
  }

  // The hover card — role-specific next steps, directly over the area.
  function showTip(d, anchor) {
    const tip = $('#marker-tip');
    const rec = ADVICE.build(d.county, d.level, d.zones);
    const steps = ROLES.steps(role, rec.kinds, d.level).slice(0, 3);
    const L = ENGINE.LEVELS[d.level];
    const def = ROLES.DEFS[role];

    tip.innerHTML = '';
    tip.style.setProperty('--lvl', L.color);

    const head = el('div', 'tip-head');
    const chip = el('span', 'chip', `${L.glyph} ${L.ipc}`);
    chip.style.background = L.color;
    head.append(chip, el('span', 'tip-name', d.name));
    if (d.county && d.county !== d.name) head.append(el('span', 'tip-sub', d.county));
    tip.append(head);

    tip.append(el('div', 'tip-lead', ROLES.headline(role, d.level, d.name)));

    if (rec.crops.length) {
      const c = el('div', 'tip-crops');
      c.append(el('span', 'tip-lab', 'At risk'));
      rec.crops.slice(0, 5).forEach(x => c.append(el('span', 'crop', x)));
      tip.append(c);
    }

    const sw = el('div', 'tip-steps');
    sw.append(el('span', 'tip-lab', `Next steps · ${def.label}`));
    const ul = el('ul');
    steps.forEach(s => ul.append(el('li', null, s)));
    sw.append(ul);
    tip.append(sw);

    if (rec.resources.length) {
      const r = el('div', 'tip-res');
      r.append(el('span', 'tip-lab', 'Who can act'));
      rec.resources.slice(0, 3).forEach(x => {
        const b = el('span', 'res-pill');
        b.append(el('b', null, x.body), el('span', null, x.name));
        r.append(b);
      });
      tip.append(r);
    }
    rec.gaps.slice(0, 1).forEach(g => tip.append(el('div', 'tip-gap', g)));

    // Position above the marker, clamped inside the globe column.
    tip.hidden = false;
    const a = anchor.getBoundingClientRect();
    const col = $('#globe-col').getBoundingClientRect();
    const w = tip.offsetWidth, h = tip.offsetHeight;
    let left = a.left + a.width / 2 - w / 2 - col.left;
    let top = a.top - h - 14 - col.top;
    let below = false;
    if (top < 8) { top = a.bottom + 14 - col.top; below = true; }
    left = Math.max(8, Math.min(col.width - w - 8, left));
    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;
    tip.classList.toggle('below', below);
    tip.style.setProperty('--arrow', `${a.left + a.width / 2 - col.left - left}px`);
  }
  const hideTip = () => { $('#marker-tip').hidden = true; };

  // =========================================================================
  //  Search
  // =========================================================================
  const searchInput = $('#search');
  const resultsEl = $('#results');
  let cursor = -1;

  function openResults(q) {
    const term = q.trim().toLowerCase();
    const hits = term ? COUNTRIES.filter(c => c.name.toLowerCase().includes(term))
                      : COUNTRIES.slice(0, 6);
    resultsEl.innerHTML = '';
    if (!hits.length) {
      const li = el('li'); li.append(el('span', null, 'No match'));
      li.style.pointerEvents = 'none'; resultsEl.append(li);
    }
    hits.forEach((c, i) => {
      const li = el('li');
      li.setAttribute('role', 'option');
      li.dataset.name = c.name;
      li.append(el('span', null, c.name));
      li.append(el('span', c.live ? 'tag live' : 'tag soon', c.live ? 'Live' : 'No coverage'));
      li.addEventListener('mousedown', ev => { ev.preventDefault(); selectCountry(c.name); });
      li.addEventListener('mouseenter', () => { cursor = i; markCursor(); });
      resultsEl.append(li);
    });
    cursor = hits.length ? 0 : -1;
    markCursor();
    resultsEl.hidden = false;
  }
  const markCursor = () => [...resultsEl.children]
    .forEach((li, i) => li.setAttribute('aria-selected', String(i === cursor)));
  const closeResults = () => { resultsEl.hidden = true; cursor = -1; };

  searchInput.addEventListener('input', () => openResults(searchInput.value));
  searchInput.addEventListener('focus', () => openResults(searchInput.value));
  searchInput.addEventListener('blur', () => setTimeout(closeResults, 120));
  searchInput.addEventListener('keydown', ev => {
    const n = resultsEl.children.length;
    if (ev.key === 'ArrowDown' && n) { ev.preventDefault(); cursor = (cursor + 1) % n; markCursor(); }
    else if (ev.key === 'ArrowUp' && n) { ev.preventDefault(); cursor = (cursor - 1 + n) % n; markCursor(); }
    else if (ev.key === 'Enter') {
      const li = resultsEl.children[cursor];
      if (li && li.dataset.name) { ev.preventDefault(); selectCountry(li.dataset.name); }
    } else if (ev.key === 'Escape') { closeResults(); searchInput.blur(); }
  });
  $('#empty-hint').addEventListener('click', ev => {
    if (ev.target.dataset.demo) selectCountry(ev.target.dataset.demo);
  });

  function selectCountry(name) {
    const c = COUNTRIES.find(x => x.name === name);
    if (!c) return;
    active = c;
    searchInput.value = c.name;
    searchInput.blur();
    closeResults();
    world.controls().autoRotate = false;
    world.pointOfView({ lat: c.lat, lng: c.lng, altitude: c.alt }, 1500);
    selected = null; hovered = null; hideTip();
    $('#detail').hidden = true;
    $('#empty-hint').hidden = true;
    $('#hud').hidden = false;
    $('#hud-name').textContent = c.name;

    if (c.live) {
      applyResolution(resolution);
      $('#legend').hidden = false;
      $('#res').hidden = false;
      $('#spark').style.opacity = '1';
      setTime(0, { rebuild: true });
    } else {
      world.polygonsData([]); world.htmlElementsData([]);
      $('#legend').hidden = true; $('#res').hidden = true;
      $('#spark').style.opacity = '.18';
      $('#hud-sub').textContent = 'not yet modelled';
      $('#feed-sub').textContent = `${c.name} · no coverage`;
      $('#feed').innerHTML = '';
      $('#feed-empty').hidden = false;
      $('#feed-empty').innerHTML =
        `<p>No FEWS NET coverage wired up for ${c.name} yet.</p>` +
        `<p class="muted">Adding a country needs its admin boundaries and the ` +
        `matching FEWS NET livelihood units. The data exists; the join does not.</p>`;
      ['#stat-units', '#stat-alerts', '#stat-sms'].forEach(s => $(s).textContent = '—');
      pause();
    }
  }

  // =========================================================================
  //  Resolution
  // =========================================================================
  $('#res').addEventListener('click', ev => {
    const b = ev.target.closest('button');
    if (!b || b.dataset.res === resolution) return;
    applyResolution(b.dataset.res);
    setTime(now, { rebuild: true });
  });

  function applyResolution(r) {
    resolution = r;
    [...$('#res').children].forEach(b => b.classList.toggle('on', b.dataset.res === r));
    const feats = featuresFor(r);
    MODEL = ENGINE.build(feats, TIMELINE, r);
    selected = null; hovered = null; hideTip();
    $('#detail').hidden = true;
    world.polygonsData(feats);
    const covered = MODEL.units.filter(u => u.covered).length;
    const noun = r === 'county' ? 'counties' : 'sub-counties';
    $('#hud-sub').textContent = `${feats.length} ${noun} · ${covered} with FEWS NET data`;
    $('#feed-sub').textContent = `Kenya · ${covered} ${noun}`;
    buildSpark();
  }

  // =========================================================================
  //  Timeline — each step is a real FEWS NET release
  // =========================================================================
  const scrub = $('#scrub');
  scrub.addEventListener('input', () => setTime(+scrub.value));
  $('#play').addEventListener('click', () => (playing ? pause() : play()));
  $('#speeds').addEventListener('click', ev => {
    const b = ev.target.closest('button');
    if (!b) return;
    speed = +b.dataset.speed;
    [...$('#speeds').children].forEach(x => x.classList.toggle('on', x === b));
    if (playing) { pause(); play(); }
  });
  document.addEventListener('keydown', ev => {
    if (ev.target.tagName === 'INPUT' || !$('#login').hidden) return;
    if (ev.code === 'Space') { ev.preventDefault(); playing ? pause() : play(); }
    else if (ev.key === 'ArrowRight') setTime(now + 1);
    else if (ev.key === 'ArrowLeft') setTime(now - 1);
    else if (ev.key === 'Escape') { closeDetail(); hideTip(); }
  });

  function play() {
    if (!active || !active.live || liveMode) return;
    if (now >= ENGINE.N_PERIODS() - 1) setTime(0, { rebuild: true });
    playing = true;
    $('.ic-play').hidden = true; $('.ic-pause').hidden = false;
    timer = setInterval(() => {
      if (now >= ENGINE.N_PERIODS() - 1) { pause(); return; }
      setTime(now + 1);
    }, 1500 / speed);
  }
  function pause() {
    playing = false; clearInterval(timer);
    $('.ic-play').hidden = false; $('.ic-pause').hidden = true;
  }

  function setTime(t, { rebuild = false } = {}) {
    const N = ENGINE.N_PERIODS() || 1;
    t = Math.max(0, Math.min(N - 1, t));
    const back = t < now;
    now = t;
    scrub.max = String(N - 1);
    scrub.value = String(t);
    const d = ENGINE.dateAt(t);
    $('#clock-date').textContent = d.label;
    $('#clock-sub').textContent = `release ${t + 1} of ${N}`;
    if (!active || !active.live || !MODEL) return;
    paintGlobe();
    renderMarkers();
    updateStats();
    updateLegend();
    renderFeed({ rebuild: rebuild || back });
    if (selected) renderDetail();
  }

  function buildTicks() {
    const wrap = $('#track-marks');
    wrap.innerHTML = '';
    const periods = ENGINE.periods;
    let lastYear = null;
    periods.forEach((p, i) => {
      const y = p.slice(0, 4);
      if (y === lastYear) return;
      lastYear = y;
      const m = el('span', 'yr', y);
      m.style.left = `${(i / Math.max(1, periods.length - 1)) * 100}%`;
      wrap.append(m);
    });
  }

  // Share of units at Crisis+ across the whole window. One measure, one hue.
  function buildSpark() {
    buildTicks();
    const svg = $('#spark');
    const W = 1000, H = 30;
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.innerHTML =
      `<defs><linearGradient id="sg" x1="0" y1="0" x2="0" y2="1">
         <stop offset="0%" stop-color="#ec833a" stop-opacity=".40"/>
         <stop offset="100%" stop-color="#ec833a" stop-opacity=".03"/>
       </linearGradient></defs>`;
    const n = MODEL.national.length;
    const pts = MODEL.national.map((v, i) => [
      (i / Math.max(1, n - 1)) * W, H - v * (H - 2) - 1,
    ]);
    const line = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' L');
    const mk = (d, fill, stroke) => {
      const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      p.setAttribute('d', d);
      p.setAttribute('fill', fill);
      if (stroke) {
        p.setAttribute('stroke', stroke);
        p.setAttribute('stroke-width', '1.5');
        p.setAttribute('vector-effect', 'non-scaling-stroke');
      }
      return p;
    };
    svg.append(mk(`M0,${H} L${line} L${W},${H} Z`, 'url(#sg)'),
               mk(`M${line}`, 'none', '#ec833a'));
  }

  // =========================================================================
  //  Readout + legend
  // =========================================================================
  function updateStats() {
    if (!MODEL) return;
    const live = MODEL.units.filter(u => hasData(u.name));
    const crisis = live.filter(u => levelAt(u.name) >= 2);
    $('#stat-units').textContent = `${crisis.length}`;
    $('#stat-units').style.color = crisis.length === 0 ? 'var(--lvl-0)'
      : crisis.length > live.length * 0.25 ? 'var(--lvl-3)' : 'var(--lvl-2)';

    const alerts = liveMode ? crisis.length
      : MODEL.events.filter(e => e.t === now && e.escalation).length;
    $('#stat-alerts').textContent = String(alerts);

    // One message per subscriber reached in each alerted unit. Rough, but it
    // is the number that drives the cost model.
    const reach = live
      .filter(u => levelAt(u.name) >= 1)
      .reduce((s, u) => s + 11000 * ENGINE.audiencesFor(levelAt(u.name)).length / 3, 0);
    $('#stat-sms').textContent = fmt(Math.round(reach));
  }
  const fmt = n => n >= 1e6 ? `${(n / 1e6).toFixed(1)}M`
                 : n >= 1e3 ? `${(n / 1e3).toFixed(0)}k` : String(n);

  function buildLegend() {
    const ul = $('#legend-items');
    ul.innerHTML = '';
    ENGINE.LEVELS.forEach(L => {
      const li = el('li');
      li.dataset.level = L.n;
      const sw = el('span', 'sw', L.glyph);
      sw.style.background = L.color;
      const code = L.ipc.split(' ')[1];                    // "1", "2", "4+"
      li.append(sw, el('span', 'n', `P${code}`),
                el('span', null, L.ipc.split(' ').slice(2).join(' ')),
                el('span', 'ct', '0'));
      ul.append(li);
    });
  }
  function updateLegend() {
    if (!MODEL) return;
    const c = [0, 0, 0, 0];
    MODEL.units.forEach(u => { if (hasData(u.name)) c[levelAt(u.name)]++; });
    [...$('#legend-items').children].forEach(li => {
      li.querySelector('.ct').textContent = String(c[+li.dataset.level]);
    });
  }

  // =========================================================================
  //  Feed
  // =========================================================================
  const feedEl = $('#feed');

  function renderFeed({ rebuild }) {
    if (liveMode) return renderLiveFeed();
    if (rebuild) { feedEl.innerHTML = ''; rendered = -1; }
    const due = MODEL.events.filter(e => e.t > rendered && e.t <= now);
    for (const e of due) feedEl.prepend(buildNote(e, !rebuild));
    rendered = now;
    const total = MODEL.events.filter(e => e.t <= now).length;
    $('#feed-empty').hidden = total > 0;
    if (!total) {
      $('#feed-empty').innerHTML =
        '<p>No reclassifications yet.</p><p class="muted">Press play, or drag the timeline.</p>';
    }
    while (feedEl.children.length > 150) feedEl.lastChild.remove();
    if (!rebuild) feedEl.scrollTop = 0;
  }

  function buildNote(e, animate) {
    const L = ENGINE.LEVELS[e.to];
    const li = el('li', 'note' + (animate ? ' is-new' : '') + (e.escalation ? '' : ' deesc'));
    li.style.setProperty('--lvl', L.color);

    const top = el('div', 'n-top');
    const chip = el('span', 'chip', `${L.glyph} ${L.ipc}`);
    top.append(chip, el('span', 'n-county', e.unit));
    top.append(el('span', 'n-date', ENGINE.dateAt(e.t).label));
    li.append(top);

    if (e.county && e.county !== e.unit) {
      li.append(el('div', 'n-move', `${e.county} County`));
    }
    li.append(el('div', 'n-move',
      e.escalation
        ? `FEWS NET raised this area from Phase ${e.fromPhase} to Phase ${e.toPhase}`
        : `FEWS NET lowered this area from Phase ${e.fromPhase} to Phase ${e.toPhase}`));

    if (e.escalation) {
      const ul = el('ul', 'n-drivers');
      e.drivers.forEach(d => ul.append(el('li', null, d)));
      li.append(ul);

      li.append(buildAdvice(ADVICE.build(e.county, e.to, e.zones), e.to, e.unit));

      const nf = el('div', 'n-notify');
      nf.append(el('span', 'lab', 'Notify'));
      e.audiences.forEach(a => nf.append(el('span', 'aud', ENGINE.AUDIENCES[a].label)));
      li.append(nf);
    } else {
      li.append(el('div', 'n-line', 'Conditions improved. No new alerts sent.'));
    }

    li.addEventListener('click', () => {
      if (!liveMode) setTime(e.t);
      const f = featuresFor(resolution).find(x => x.properties.name === e.unit);
      if (f) {
        selected = f; smsAudience = null;
        world.pointOfView({ lat: f.properties.lat, lng: f.properties.lng, altitude: 0.26 }, 900);
        paintGlobe(); renderDetail();
      }
    });
    return li;
  }

  // The recommendation block — role-aware.
  function buildAdvice(rec, level, unitName) {
    const box = el('div', 'n-advice');
    const def = ROLES.DEFS[role];

    const head = el('div', 'adv-head');
    head.append(el('span', 'adv-kind', rec.primary));
    if (rec.zones.length) head.append(el('span', 'adv-zone', rec.zones[0]));
    head.append(el('span', 'adv-role', def.label));
    box.append(head);

    box.append(el('div', 'adv-lead', ROLES.headline(role, level, unitName)));

    if (rec.crops.length) {
      const r = el('div', 'adv-row');
      r.append(el('span', 'adv-lab', 'At risk'));
      const chips = el('span', 'adv-chips');
      rec.crops.forEach(c => chips.append(el('span', 'crop', c)));
      r.append(chips);
      box.append(r);
    }

    const steps = ROLES.steps(role, rec.kinds, level).slice(0, 4);
    if (steps.length) {
      const r = el('div', 'adv-row');
      r.append(el('span', 'adv-lab', 'Next steps'));
      const ul = el('ul', 'adv-actions');
      steps.forEach(a => ul.append(el('li', null, a)));
      r.append(ul);
      box.append(r);
    }

    if (rec.resources.length) {
      const r = el('div', 'adv-row');
      r.append(el('span', 'adv-lab', 'Resources'));
      const list = el('div', 'adv-res');
      rec.resources.forEach(res => {
        const d = el('div', 'res');
        const t = el('div', 'res-t');
        t.append(el('span', 'res-n', res.name), el('span', 'res-b', res.body));
        d.append(t, el('div', 'res-w', res.what));
        d.title = `Eligibility: ${res.who}`;
        list.append(d);
      });
      r.append(list);
      box.append(r);
    }
    rec.gaps.forEach(g => box.append(el('div', 'adv-gap', g)));
    return box;
  }

  // =========================================================================
  //  Live mode
  // =========================================================================
  // Live data is published at county level, so a sub-county inherits its
  // parent county's current classification rather than inventing one.
  const liveKey = name => {
    if (resolution === 'county') return name;
    const f = KENYA_SUBCOUNTIES.features.find(x => x.properties.name === name);
    return f ? f.properties.county : name;
  };
  function liveLevel(name) {
    const e = LIVE && LIVE.current && LIVE.current[liveKey(name)];
    return e ? (ENGINE.PHASE_TO_LEVEL[e.phase] ?? 0) : 0;
  }

  async function loadLive({ force = false } = {}) {
    const btn = $('#live-toggle');
    btn.classList.add('loading');
    try {
      const r = await fetch('/api/live' + (force ? '?refresh=1' : ''));
      if (!r.ok) throw new Error(r.status);
      LIVE = await r.json();
    } catch { LIVE = null; }
    finally {
      btn.classList.remove('loading');
      renderLiveBar();
      if (liveMode) { paintGlobe(); renderMarkers(); updateStats(); updateLegend(); }
    }
    return LIVE;
  }

  function renderLiveBar() {
    $('#disclaimer').textContent = liveMode
      ? 'Live FEWS NET classifications · recommendations are ours · prototype'
      : 'All classifications from FEWS NET · recommendations are ours · prototype';
    const bar = $('#live-bar');
    if (!liveMode) { bar.hidden = true; return; }
    bar.hidden = false;
    if (!LIVE || !LIVE.n_counties) {
      bar.className = 'warn';
      bar.innerHTML = '<b>Live feed unavailable.</b> Start with ' +
        '<code>python3 serve.py</code> to proxy FEWS NET, or stay in replay.';
      return;
    }
    const n3 = Object.values(LIVE.current).filter(v => v.phase >= 3).length;
    const stamp = LIVE.fetched_at ? new Date(LIVE.fetched_at).toLocaleString() : 'cached';
    bar.className = LIVE.stale ? 'warn' : '';
    bar.innerHTML = `<span class="dot"></span><b>FEWS NET live</b> · period ` +
      `<b>${LIVE.reporting_period || '—'}</b> · <b>${n3}</b> of ${LIVE.n_counties} ` +
      `counties at IPC Phase 3+ · fetched ${stamp}` +
      (LIVE.refreshing ? ' · <i>refreshing…</i>' : '') + (LIVE.stale ? ' · <b>STALE</b>' : '');
  }

  function renderLiveFeed() {
    feedEl.innerHTML = ''; rendered = -1;
    if (!LIVE || !LIVE.current) { $('#feed-empty').hidden = false; return; }
    const zonesOf = c => {
      const u = MODEL && MODEL.byName.get(c);
      return (u && u.zones) || [];
    };
    const rows = Object.entries(LIVE.current)
      .map(([unit, v]) => ({ unit, ...v, level: ENGINE.PHASE_TO_LEVEL[v.phase] ?? 0 }))
      .filter(r => r.level >= 1)
      .sort((a, b) => b.phase - a.phase || a.unit.localeCompare(b.unit));
    for (const r of rows) {
      const proj = LIVE.projection_ml1 && LIVE.projection_ml1[r.unit];
      feedEl.append(buildNote({
        t: now, unit: r.unit, county: r.unit,
        from: r.level, to: r.level, fromPhase: r.phase, toPhase: r.phase,
        escalation: true, period: r.as_of,
        projection: proj ? proj.phase : null,
        zones: zonesOf(r.unit),
        audiences: ENGINE.audiencesFor(r.level),
        drivers: [
          `FEWS NET Current Situation, published ${r.as_of}`,
          proj ? `Their near-term projection: Phase ${proj.phase} ${ENGINE.PHASE_NAME[proj.phase]}`
               : 'No near-term projection published for this unit',
        ],
      }, false));
    }
    $('#feed-empty').hidden = rows.length > 0;
  }

  // =========================================================================
  //  Detail panel
  // =========================================================================
  const closeDetail = () => { selected = null; $('#detail').hidden = true; paintGlobe(); };

  function renderDetail() {
    if (!selected) { $('#detail').hidden = true; return; }
    const name = selected.properties.name;
    const u = unitAt(name);
    const county = selected.properties.county || name;
    const zones = selected.properties.zones || (u && u.zones) || [];

    const covered = hasData(name);
    const level = levelAt(name);
    const lk = liveKey(name);
    const row = liveMode
      ? { level,
          phase: (LIVE && LIVE.current[lk] || {}).phase,
          asOf: (LIVE && LIVE.current[lk] || {}).as_of,
          projection: (LIVE && LIVE.projection_ml1 && LIVE.projection_ml1[lk])
            ? LIVE.projection_ml1[lk].phase : null }
      : (u ? u.series[now] : null);

    const d = $('#detail');
    d.hidden = false;
    d.innerHTML = '';

    const L = ENGINE.LEVELS[level];
    const head = el('div', 'd-head');
    const ht = el('div');
    ht.append(el('h3', null, name));
    ht.append(el('div', 'sub',
      (county !== name ? `${county} County · ` : '') +
      (covered ? `FEWS NET ${row.asOf || ENGINE.dateAt(now).label}` : 'no FEWS NET coverage')));
    const chip = el('span', 'chip', covered ? `${L.glyph} ${L.ipc}` : '— no data');
    chip.style.background = covered ? L.color : '#55555f';
    chip.style.alignSelf = 'center';
    chip.style.marginLeft = 'auto';
    const close = el('button', 'd-close', '×');
    close.addEventListener('click', closeDetail);
    head.append(ht, chip, close);
    d.append(head);

    const body = el('div', 'd-body');

    if (!covered) {
      body.append(el('div', 'sms',
        'FEWS NET does not publish a classification for this unit. We show no ' +
        'colour rather than guessing one.'));
      d.append(body);
      return;
    }

    const pm = el('div', 'd-pm');
    const big = el('span', 'big', `P${row.phase}`);
    big.style.color = L.color;
    const w1 = el('div');
    w1.append(big, el('div', 'unit', `IPC ${ENGINE.PHASE_NAME[row.phase]} — FEWS NET published`));
    pm.append(w1);
    if (row.projection != null) {
      const w2 = el('div');
      const b2 = el('span', 'big', `P${row.projection}`);
      b2.style.color = ENGINE.LEVELS[ENGINE.PHASE_TO_LEVEL[row.projection] ?? 0].color;
      w2.append(b2, el('div', 'unit', 'their near-term projection'));
      pm.append(w2);
    }
    body.append(pm);

    if (zones.length) {
      const s = el('div', 'd-sect');
      s.append(el('span', 'd-lab', 'FEWS NET livelihood zones'));
      const w = el('div', 'adv-chips');
      zones.forEach(z => w.append(el('span', 'crop', z)));
      s.append(w);
      body.append(s);
    }

    if (level >= 1) {
      const s = el('div', 'd-sect');
      s.append(el('span', 'd-lab', `Recommended response · ${ROLES.DEFS[role].label}`));
      s.append(buildAdvice(ADVICE.build(county, level, zones), level, name));
      body.append(s);
    }

    const auds = ENGINE.audiencesFor(level);
    if (!smsAudience || !auds.includes(smsAudience)) {
      smsAudience = auds.includes('farmer') ? 'farmer' : (auds[0] || null);
    }
    const s3 = el('div', 'd-sect');
    s3.append(el('span', 'd-lab', auds.length ? 'Message each audience receives' : 'No alert at this level'));
    if (!auds.length) {
      s3.append(el('div', 'sms', 'IPC Phase 1 — nobody is messaged. A monthly digest is optional.'));
    } else {
      const tabs = el('div', 'aud-tabs');
      auds.forEach(a => {
        const b = el('button', a === smsAudience ? 'on' : '', ENGINE.AUDIENCES[a].label);
        b.addEventListener('click', () => { smsAudience = a; renderDetail(); });
        tabs.append(b);
      });
      s3.append(tabs);
      const text = ENGINE.composeSMS(name, row, smsAudience,
        ADVICE.shortAction(county, level, zones));
      s3.append(el('div', 'sms', text));
      const segs = Math.ceil(text.length / 160);
      const meta = el('div', 'sms-meta');
      meta.append(el('span', null, `${text.length} chars · GSM-7`));
      meta.append(el('span', segs > 1 ? 'over' : '', `${segs} segment${segs > 1 ? 's' : ''}`));
      s3.append(meta);
    }
    body.append(s3);
    d.append(body);
  }

  // =========================================================================
  //  Boot
  // =========================================================================
  $('#role-badge').addEventListener('click', () => {
    $('#login').hidden = false;
    requestAnimationFrame(() => $('#login').classList.remove('gone'));
  });

  async function boot() {
    buildRolePicker();
    buildLegend();

    let lhz = { zones: {} };
    try {
      [TIMELINE, lhz] = await Promise.all([
        fetch('data/fews-timeline.json').then(r => r.json()),
        fetch('data/kenya-livelihoods.json').then(r => r.json()),
      ]);
    } catch (err) {
      console.error('FEWS NET data failed to load.', err);
      $('#login-card').insertAdjacentHTML('beforeend',
        '<p class="login-note" style="color:#ffd43b">Data failed to load. ' +
        'Serve over HTTP with <code>python3 serve.py</code>.</p>');
      return;
    }
    ADVICE.init(lhz);

    const qs = new URLSearchParams(location.search);
    const qr = qs.get('role');
    setRole(ROLES.DEFS[qr] ? qr : 'ngo', !!ROLES.DEFS[qr]);

    const c = qs.get('country');
    if (c && COUNTRIES.some(x => x.name.toLowerCase() === c.toLowerCase())) {
      $('#login').hidden = true;
      selectCountry(COUNTRIES.find(x => x.name.toLowerCase() === c.toLowerCase()).name);
      if (qs.get('res')) applyResolution(qs.get('res'));
      const t = parseInt(qs.get('t'), 10);
      setTime(Number.isFinite(t) ? t : 0, { rebuild: true });
      const unit = qs.get('unit');
      if (unit) {
        const f = featuresFor(resolution).find(x => x.properties.name === unit);
        if (f) { selected = f; paintGlobe(); renderDetail(); }
      }
      if (qs.get('live') === '1') { await loadLive(); $('#live-toggle').click(); }

      const tip = qs.get('tip');
      if (tip) {
        setTimeout(() => {
          const pick = tip === '1'
            ? [...markerEls.values()].sort((a, b) => b.d.level - a.d.level)[0]
            : markerEls.get(tip);
          if (pick) showTip(pick.d, pick.el);
        }, 900);
      }
    }
    loadLive();
  }

  boot();
})();
