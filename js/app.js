/* ============================================================================
   app.js — globe, search, timeline and the alert feed.

   One piece of state matters: `now`, the month index 0..71. Everything on
   screen is a pure function of it. Scrubbing backwards is therefore just as
   valid as playing forwards, which is what makes the demo safe to drive live.
   ============================================================================ */

(() => {
  'use strict';

  const $ = sel => document.querySelector(sel);
  const el = (tag, cls, txt) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt != null) n.textContent = txt;
    return n;
  };

  // ---- Countries the search knows about ----------------------------------
  // A country is LIVE only when its geometry (data/geo/<ISO3>.js) and REAL
  // model output (data/risk/<ISO3>.js, meta.model_version != "STUB") loaded.
  // Countries with an iso3 but no real output yet show as DATA IN PROGRESS.
  // There is no simulated fallback: the screen only ever shows real data.
  // The rest are listed so the search is honest about missing coverage.
  const COUNTRIES = [
    { name: 'Zimbabwe',     iso3: 'ZWE', lat:-19.02, lng: 29.15, alt: 0.42, unitWord: 'districts' },
    { name: 'Kenya',        iso3: 'KEN', lat:  0.53, lng: 37.86, alt: 0.38, unitWord: 'counties' },
    { name: 'Malawi',       iso3: 'MWI', lat:-13.25, lng: 34.30, alt: 0.42, unitWord: 'districts' },
    { name: 'Zambia',       iso3: 'ZMB', lat:-13.13, lng: 27.85, alt: 0.50, unitWord: 'districts' },
    { name: 'Ethiopia',     lat:  9.10, lng: 40.50, alt: 0.65 },
    { name: 'Somalia',      lat:  5.15, lng: 46.20, alt: 0.65 },
    { name: 'Uganda',       lat:  1.37, lng: 32.29, alt: 0.65 },
    { name: 'Tanzania',     lat: -6.37, lng: 34.89, alt: 0.65 },
    { name: 'Niger',        lat: 17.61, lng:  8.08, alt: 0.65 },
    { name: 'Sudan',        lat: 15.60, lng: 30.22, alt: 0.65 },
    { name: 'South Sudan',  lat:  7.86, lng: 29.69, alt: 0.65 },
    { name: 'Nigeria',      lat:  9.08, lng:  8.68, alt: 0.65 },
    { name: 'Madagascar',   lat:-18.77, lng: 46.87, alt: 0.65 },
    { name: 'Morocco',      lat: 31.79, lng: -7.09, alt: 0.65 },
  ];

  const WORLD_VIEW = { lat: 6, lng: 24, altitude: 2.3 };

  // ---- Engines --------------------------------------------------------------
  // Each live country gets an engine from REAL.forCountry (js/real.js).
  // TIMELINE is only the idle timeline shown before a country is picked.
  const TIMELINE = {
    START_YEAR: 2019, N_MONTHS: 72, LEVELS: REAL.LEVELS,
    dateAt: t => ({ label: `${['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][t % 12]} ${2019 + Math.floor(t / 12)}` }),
    declaration: null,
  };

  const isRealRisk = iso3 => {
    const R = (window.RISK_DATA || {})[iso3];
    return !!(R && R.meta && String(R.meta.model_version).toUpperCase() !== 'STUB');
  };

  function engineFor(c) {
    if (!c || !c.iso3) return null;
    const geo = (window.GEO_DATA || {})[c.iso3];
    if (geo && isRealRisk(c.iso3)) {
      return { engine: REAL.forCountry(c.iso3), features: geo.features };
    }
    return null;
  }

  let ENGINE = TIMELINE;       // timeline defaults before a country is picked
  let MODEL = { units: [], events: [], national: [] };
  let FEATURES = [];
  let unitOf = new Map();      // feature -> unit
  let byName = new Map();      // lower-case name -> unit

  let now = 0;            // month index
  let rendered = -1;      // how far the feed has been filled, for incremental appends
  let playing = false;
  let speed = 1;
  let timer = null;
  let active = null;      // the selected country, or null
  let selected = null;    // the county open in the detail panel
  let hovered = null;
  let smsAudience = 'farmer';

  const levelColor = n => ENGINE.LEVELS[n].color;

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
    .polygonsTransitionDuration(420)
    .polygonLabel(() => '')          // custom hover UI instead of the default tooltip
    .onPolygonHover(onHover)
    .onPolygonClick(onPolygonClick);

  world.pointOfView(WORLD_VIEW, 0);
  world.controls().autoRotate = true;
  world.controls().autoRotateSpeed = 0.32;
  world.controls().enableDamping = true;

  function fitGlobe() {
    world.width(globeEl.clientWidth).height(globeEl.clientHeight);
  }
  fitGlobe();
  new ResizeObserver(fitGlobe).observe(globeEl);

  // Polygon accessors are re-set (new function identity) whenever the month
  // changes — that is what makes globe.gl recolour and re-tween the counties.
  function paintGlobe() {
    if (!active || !active.live) return;
    world
      .polygonAltitude(d => {
        const lvl = unitOf.get(d).series[now].level;
        const base = 0.008 + lvl * 0.0075;
        return d === selected || d === hovered ? base + 0.014 : base;
      })
      .polygonCapColor(d => {
        const lvl = unitOf.get(d).series[now].level;
        const c = levelColor(lvl);
        if (d === selected) return c;
        return c + (lvl === 0 ? 'b0' : 'd8');      // healthy counties sit back a little
      })
      .polygonSideColor(d => {
        const lvl = unitOf.get(d).series[now].level;
        return levelColor(lvl) + '66';
      })
      .polygonStrokeColor(d =>
        d === selected ? '#ffffff' : d === hovered ? '#ffffffaa' : '#00000055');
  }

  function onHover(poly) {
    hovered = poly || null;
    globeEl.style.cursor = poly ? 'pointer' : '';
    paintGlobe();
  }

  function onPolygonClick(poly) {
    selected = poly;
    smsAudience = null;                 // let the panel pick a sensible default
    paintGlobe();
    renderDetail();
  }

  // =========================================================================
  //  Search
  // =========================================================================
  const searchInput = $('#search');
  const resultsEl = $('#results');
  let cursor = -1;

  function openResults(q) {
    const term = q.trim().toLowerCase();
    const hits = term
      ? COUNTRIES.filter(c => c.name.toLowerCase().includes(term))
      : COUNTRIES.slice(0, 6);

    resultsEl.innerHTML = '';
    if (!hits.length) {
      const li = el('li');
      li.append(el('span', null, 'No match'));
      li.style.pointerEvents = 'none';
      resultsEl.append(li);
    }
    hits.forEach((c, i) => {
      const li = el('li');
      li.setAttribute('role', 'option');
      li.dataset.name = c.name;
      li.append(el('span', null, c.name));
      li.append(el('span', c.live ? 'tag live' : c.inProgress ? 'tag wip' : 'tag soon',
        c.live ? 'Live' : c.inProgress ? 'Data in progress' : 'No coverage'));
      li.addEventListener('mousedown', ev => { ev.preventDefault(); selectCountry(c.name); });
      li.addEventListener('mouseenter', () => { cursor = i; markCursor(); });
      resultsEl.append(li);
    });
    cursor = hits.length ? 0 : -1;
    markCursor();
    resultsEl.hidden = false;
  }

  function markCursor() {
    [...resultsEl.children].forEach((li, i) =>
      li.setAttribute('aria-selected', String(i === cursor)));
  }

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
    const name = ev.target.dataset.demo;
    if (name) selectCountry(name);
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

    selected = null;
    hovered = null;
    $('#detail').hidden = true;
    $('#empty-hint').hidden = true;

    $('#hud').hidden = false;
    $('#hud-name').textContent = c.name;

    if (c.live) {
      loadCountry(c);
      const n = FEATURES.length;
      const decl = ENGINE.declaration;
      $('#hud-sub').textContent = `${n} ${c.unitWord}` +
        (decl ? ` · disaster declared ${fmtDate(decl.date)}` : '');
      $('#stat-units').parentNode.querySelector('.stat-lab').textContent = `${c.unitWord} at Warning+`;
      world.polygonsData(FEATURES);
      $('#spark').style.opacity = '1';
      $('#legend').hidden = false;
      $('#feed-sub').textContent = `${c.name} · ${n} ${c.unitWord}`;
      $('#disclaimer').textContent = ENGINE.disclaimer;
      $('#disclaimer').hidden = false;
      setTime(0, { rebuild: true });
    } else {
      $('#hud-sub').textContent = c.inProgress ? 'data in progress' : 'not yet modelled';
      $('#disclaimer').hidden = true;
      buildTicks();
      // Honest empty state rather than a fake map.
      world.polygonsData([]);
      $('#legend').hidden = true;
      $('#feed-sub').textContent = `${c.name} · ${c.inProgress ? 'data in progress' : 'no coverage'}`;
      $('#feed').innerHTML = '';
      $('#feed-count').textContent = '0';
      MODEL = { units: [], events: [], national: [] };
      buildSpark();                         // no curve: nothing real to show
      $('#feed-empty').hidden = false;
      $('#feed-empty').innerHTML = c.inProgress
        ? `<p>Data in progress for ${c.name}.</p>` +
          `<p class="muted">Boundaries are ready; the risk model has not published ` +
          `real output for this country yet. Nothing is shown until it does.</p>`
        : `<p>No model for ${c.name} yet.</p>` +
        `<p class="muted">Adding a country needs its admin boundaries, ` +
        `a crop/grass mask and the satellite + weather signals run through the model.</p>`;
      ['#stat-units', '#stat-people', '#stat-sms'].forEach(s => $(s).textContent = '—');
      pause();
      announce();
    }
  }

  function fmtDate(iso) {
    const [y, m, d] = iso.split('-').map(Number);
    return `${d} ${['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][m - 1]} ${y}`;
  }

  // Swap the engine, model and polygons for a live country.
  function loadCountry(c) {
    const { engine, features } = engineFor(c);
    ENGINE = engine;
    FEATURES = features;
    MODEL = ENGINE.build(features);
    unitOf = new Map(MODEL.units.map((u, i) => [features[i], u]));
    byName = new Map(MODEL.units.map(u => [u.name.toLowerCase(), u]));
    const decl = ENGINE.declaration;
    if (decl && decl.t >= 0 && decl.t < ENGINE.N_MONTHS) {
      MODEL.events.push({ kind: 'declaration', t: decl.t, label: decl.label, date: decl.date });
      MODEL.events.sort((a, b) => a.t - b.t);
    }
    now = 0;
    scrub.max = String(ENGINE.N_MONTHS - 1);
    buildTicks();
    buildSpark();
  }

  // =========================================================================
  //  Timeline
  // =========================================================================
  const scrub = $('#scrub');
  scrub.max = String(ENGINE.N_MONTHS - 1);

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
    if (ev.target.tagName === 'INPUT') return;
    if (ev.code === 'Space') { ev.preventDefault(); playing ? pause() : play(); }
    else if (ev.key === 'ArrowRight') setTime(now + 1);
    else if (ev.key === 'ArrowLeft') setTime(now - 1);
    else if (ev.key === 'Escape') closeDetail();
  });

  function play() {
    if (!active || !active.live) return;
    if (now >= ENGINE.N_MONTHS - 1) setTime(0, { rebuild: true });
    playing = true;
    $('.ic-play').hidden = true;
    $('.ic-pause').hidden = false;
    timer = setInterval(() => {
      if (now >= ENGINE.N_MONTHS - 1) { pause(); return; }
      setTime(now + 1);
    }, 950 / speed);
  }

  function pause() {
    playing = false;
    clearInterval(timer);
    $('.ic-play').hidden = false;
    $('.ic-pause').hidden = true;
  }

  function setTime(t, { rebuild = false } = {}) {
    t = Math.max(0, Math.min(ENGINE.N_MONTHS - 1, t));
    const wentBack = t < now;
    now = t;
    scrub.value = String(t);

    const d = ENGINE.dateAt(t);
    $('#clock-date').textContent = d.label;
    $('#clock-sub').textContent = `month ${t + 1} of ${ENGINE.N_MONTHS}`;
    announce();

    if (!active || !active.live) return;

    paintGlobe();
    updateStats();
    updateLegendCounts();
    renderFeed({ rebuild: rebuild || wentBack });
    if (selected) renderDetail();
  }

  // Tell js/live.js (the SMS demo pages) which live country and month are on
  // screen, so "Run alerts for this month" posts the right {iso3, t}.
  function announce() {
    const live = !!(active && active.live);
    window.dispatchEvent(new CustomEvent('app:state', { detail: {
      iso3: live ? active.iso3 : null, country: active ? active.name : null,
      live, t: now, label: ENGINE.dateAt(now).label,
    } }));
  }

  // Year ticks under the slider, plus the declaration marker.
  function buildTicks() {
    const wrap = $('#track-marks');
    wrap.innerHTML = '';
    const decl = active && active.live ? ENGINE.declaration : null;
    const old = $('#decl-mark');
    if (old) old.remove();
    if (decl && decl.t >= 0 && decl.t < ENGINE.N_MONTHS) {
      const mk = el('div');
      mk.id = 'decl-mark';
      mk.style.left = `${(decl.t / (ENGINE.N_MONTHS - 1)) * 100}%`;
      mk.title = `${decl.label} — ${fmtDate(decl.date)}`;
      mk.append(el('span', null, `declared ${fmtDate(decl.date)}`));
      $('#track-wrap').append(mk);
    }
    for (let y = ENGINE.START_YEAR; y < ENGINE.START_YEAR + ENGINE.N_MONTHS / 12; y++) {
      const t = (y - ENGINE.START_YEAR) * 12;
      const m = el('span', 'yr', String(y));
      m.style.left = `${(t / (ENGINE.N_MONTHS - 1)) * 100}%`;
      wrap.append(m);
    }
  }
  buildTicks();

  // The strip behind the slider: share of counties at Warning or above over
  // the whole window. One measure, one hue, no axis furniture — it exists to
  // show you where the crisis is, not to be read off precisely.
  function buildSpark() {
    const svg = $('#spark');
    if (!MODEL.national.length) { svg.innerHTML = ''; return; }
    const W = 1000, H = 30;
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    const pts = MODEL.national.map((v, i) => [
      (i / (ENGINE.N_MONTHS - 1)) * W,
      H - v * (H - 2) - 1,
    ]);
    const line = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' L');

    const area = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    area.setAttribute('d', `M0,${H} L${line} L${W},${H} Z`);
    area.setAttribute('fill', 'url(#spark-grad)');

    const stroke = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    stroke.setAttribute('d', `M${line}`);
    stroke.setAttribute('fill', 'none');
    stroke.setAttribute('stroke', '#ec833a');
    stroke.setAttribute('stroke-width', '1.5');
    stroke.setAttribute('vector-effect', 'non-scaling-stroke');

    svg.innerHTML =
      `<defs><linearGradient id="spark-grad" x1="0" y1="0" x2="0" y2="1">
         <stop offset="0%" stop-color="#ec833a" stop-opacity=".40"/>
         <stop offset="100%" stop-color="#ec833a" stop-opacity=".03"/>
       </linearGradient></defs>`;
    svg.append(area, stroke);
  }

  // =========================================================================
  //  Readout + legend
  // =========================================================================
  function updateStats() {
    const rows = MODEL.units.map(u => u.series[now]);
    const warnPlus = MODEL.units.filter((u, i) => rows[i].level >= 2);
    const people = warnPlus.reduce((s, u) => s + (u.props.pop || 0), 0);
    const popKnown = MODEL.units.some(u => u.props.pop != null);

    // Cumulative messages: one per subscriber reached, each time a county
    // escalates. Rough, but it is the number that drives the cost model.
    let sms = 0;
    for (const e of MODEL.events) {
      if (e.t > now || !e.escalation || e.people == null) continue;
      sms += Math.round(e.people * 1000 * 0.11) * e.audiences.length / 3;
    }

    const u = $('#stat-units');
    u.textContent = String(warnPlus.length);
    u.style.color = warnPlus.length === 0 ? 'var(--lvl-0)'
                  : warnPlus.length > 20 ? 'var(--lvl-3)' : 'var(--lvl-2)';

    $('#stat-people').textContent = !popKnown ? '—' : people >= 1 ? `${people.toFixed(1)}M` : `${Math.round(people * 1000)}k`;
    $('#stat-sms').textContent = popKnown ? fmtCompact(Math.round(sms)) : '—';
  }

  function fmtCompact(n) {
    if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
    if (n >= 1e3) return `${(n / 1e3).toFixed(0)}k`;
    return String(n);
  }

  (function buildLegend() {
    const ul = $('#legend-items');
    ENGINE.LEVELS.forEach(L => {
      const li = el('li');
      li.dataset.level = L.n;
      const sw = el('span', 'sw', L.glyph);
      sw.style.background = L.color;
      li.append(sw, el('span', 'n', `L${L.n}`), el('span', null, L.label), el('span', 'ct', '0'));
      ul.append(li);
    });
  })();

  function updateLegendCounts() {
    const counts = [0, 0, 0, 0];
    MODEL.units.forEach(u => counts[u.series[now].level]++);
    [...$('#legend-items').children].forEach(li => {
      li.querySelector('.ct').textContent = String(counts[+li.dataset.level]);
    });
  }

  // =========================================================================
  //  Alert feed
  // =========================================================================
  const feedEl = $('#feed');

  function renderFeed({ rebuild }) {
    if (rebuild) { feedEl.innerHTML = ''; rendered = -1; }

    const due = MODEL.events.filter(e => e.t > rendered && e.t <= now);
    // Newest first, so prepend in reverse.
    for (const e of due) feedEl.prepend(buildNote(e, !rebuild));
    rendered = now;

    const total = MODEL.events.filter(e => e.t <= now).length;
    $('#feed-count').textContent = String(total);
    $('#feed-empty').hidden = total > 0;
    if (total === 0) {
      $('#feed-empty').innerHTML =
        '<p>No alerts yet.</p><p class="muted">Press play, or drag the timeline forward.</p>';
    }

    // Keep the DOM bounded during a fast replay.
    while (feedEl.children.length > 120) feedEl.lastChild.remove();
    if (!rebuild) feedEl.scrollTop = 0;
  }

  function buildNote(e, animate) {
    if (e.kind === 'declaration') {
      const li = el('li', 'note decl' + (animate ? ' is-new' : ''));
      li.style.setProperty('--lvl', ENGINE.LEVELS[3].color);
      const top = el('div', 'n-top');
      top.append(el('span', 'chip', 'OFFICIAL'), el('span', 'n-county', active.name));
      top.append(el('span', 'n-date', fmtDate(e.date)));
      li.append(top);
      li.append(el('div', 'n-line', e.label + '. Compare with when the model first warned.'));
      li.querySelector('.chip').style.background = ENGINE.LEVELS[3].color;
      li.addEventListener('click', () => setTime(e.t));
      return li;
    }
    const L = ENGINE.LEVELS[e.to];
    const li = el('li', 'note' + (animate ? ' is-new' : '') + (e.escalation ? '' : ' deesc'));
    li.style.setProperty('--lvl', L.color);
    li.dataset.county = e.county;
    li.dataset.t = e.t;

    const top = el('div', 'n-top');
    const chip = el('span', 'chip', `${L.glyph} L${e.to} ${L.label.toUpperCase()}`);
    top.append(chip, el('span', 'n-county', e.county));
    if (e.escalation && ENGINE.EVENTS[e.event]) top.append(el('span', 'evt', ENGINE.EVENTS[e.event]));
    top.append(el('span', 'n-date', ENGINE.dateAt(e.t).label));
    li.append(top);

    li.append(el('div', 'n-move',
      e.escalation
        ? `escalated from L${e.from} ${ENGINE.LEVELS[e.from].label}`
        : `stood down from L${e.from} ${ENGINE.LEVELS[e.from].label}`));

    if (e.escalation) {
      const line = el('div', 'n-line');
      line.innerHTML =
        `Shortage risk <b>${Math.round(e.p * 100)}%</b> at <b>${e.horizon} weeks</b> · ` +
        `<b>${e.agreeing}/${ENGINE.N_FAMILIES}</b> source families agree · confidence ${e.confidence}` +
        (e.people != null ? ` · <b>${e.people.toFixed(2)}M</b> people` : '');
      li.append(line);

      const ul = el('ul', 'n-drivers');
      e.drivers.forEach(d => ul.append(el('li', null, d)));
      li.append(ul);

      const nf = el('div', 'n-notify');
      nf.append(el('span', 'lab', 'Notify'));
      e.audiences.forEach(a => nf.append(el('span', 'aud', ENGINE.AUDIENCES[a].label)));
      li.append(nf);
    } else {
      li.append(el('div', 'n-line', 'Conditions improved. No new alerts sent.'));
    }

    li.addEventListener('click', () => {
      setTime(e.t);
      const poly = FEATURES.find(f => (e.id != null ? f.properties.id === e.id : f.properties.name === e.county));
      if (poly) {
        selected = poly;
        smsAudience = null;
        world.pointOfView(
          { lat: poly.properties.lat, lng: poly.properties.lng, altitude: 0.55 }, 900);
        paintGlobe();
        renderDetail();
      }
    });

    return li;
  }

  // =========================================================================
  //  County detail
  // =========================================================================
  // GSM 03.38 basic set + extension table (extension chars cost 2, ignored here).
  const GSM7 = new Set(('@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !"#¤%&\'()*+,-./0123456789:;<=>?' +
    '¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà^{}\\[~]|€').split(''));
  const isGsm7 = t => [...t].every(ch => GSM7.has(ch));

  function closeDetail() {
    selected = null;
    $('#detail').hidden = true;
    paintGlobe();
  }

  function renderDetail() {
    if (!selected) { $('#detail').hidden = true; return; }
    const unit = unitOf.get(selected);
    const row = unit.series[now];
    const L = ENGINE.LEVELS[row.level];
    const auds = ENGINE.audiencesFor(row.level, row);
    // Default to the farmer message. It is the one that shows the product is
    // about a person with a feature phone, not a dashboard.
    if (!smsAudience || !auds.includes(smsAudience)) {
      smsAudience = auds.includes('farmer') ? 'farmer'
                  : auds.includes('herder') ? 'herder' : (auds[0] || null);
    }

    const d = $('#detail');
    d.hidden = false;
    d.innerHTML = '';

    // --- header
    const head = el('div', 'd-head');
    const ht = el('div');
    ht.append(el('h3', null, unit.name));
    const sub = el('div', 'sub', ENGINE.dateAt(now).label +
      (unit.props.pop != null ? ` · ${unit.props.pop.toFixed(2)}M people` : ''));
    if (ENGINE.EVENTS[row.event]) sub.append(el('span', 'evt', ENGINE.EVENTS[row.event]));
    ht.append(sub);
    const chip = el('span', 'chip', `${L.glyph} L${row.level} ${L.label.toUpperCase()}`);
    chip.style.background = L.color;
    chip.style.alignSelf = 'center';
    chip.style.marginLeft = 'auto';
    const close = el('button', 'd-close', '×');
    close.setAttribute('aria-label', 'Close');
    close.addEventListener('click', closeDetail);
    head.append(ht, chip, close);
    d.append(head);

    const body = el('div', 'd-body');

    // --- headline numbers
    const pm = el('div', 'd-pm');
    const big = el('span', 'big', `${Math.round(row.p * 100)}%`);
    big.style.color = L.color;
    const pwrap = el('div');
    pwrap.append(big);
    pwrap.append(el('div', 'unit', `probability of shortage at ${row.horizon} weeks`));
    const cwrap = el('div');
    cwrap.append(el('span', 'big', `${row.agreeing}/${ENGINE.N_FAMILIES}`));
    cwrap.append(el('div', 'unit', `sources agree · ${row.confidence} confidence`));
    pm.append(pwrap, cwrap);
    body.append(pm);

    // --- source agreement
    const s1 = el('div', 'd-sect');
    s1.append(el('span', 'd-lab', 'Source families'));
    const fams = el('div', 'fams');
    fams.style.setProperty('--fam-n', ENGINE.FAMILIES.length);
    for (const F of ENGINE.FAMILIES) {
      const f = el('div', 'fam' + (row.families[F.key] ? ' hit' : ''));
      f.append(el('span', 'fn', F.short), el('span', 'fv', F.val(row)));
      f.title = `${F.src} — ${row.families[F.key] ? 'anomalous' : 'within normal range'}`;
      fams.append(f);
    }
    s1.append(fams);
    body.append(s1);

    // --- drivers
    if (row.drivers.length) {
      const s2 = el('div', 'd-sect');
      s2.append(el('span', 'd-lab', 'Top drivers'));
      const ul = el('ul', 'drivers');
      row.drivers.forEach((t, i) => {
        const li = el('li');
        li.append(el('span', 'rank', `${i + 1}`), el('span', null, t));
        ul.append(li);
      });
      s2.append(ul);
      body.append(s2);
    }

    // --- SMS preview
    const s3 = el('div', 'd-sect');
    s3.append(el('span', 'd-lab',
      auds.length ? 'Message each audience would receive' : 'No alert at this level'));

    if (!auds.length) {
      s3.append(el('div', 'sms', 'Level 0 — nobody is messaged. A monthly digest is optional.'));
    } else {
      const tabs = el('div', 'aud-tabs');
      auds.forEach(a => {
        const b = el('button', a === smsAudience ? 'on' : '', ENGINE.AUDIENCES[a].label);
        b.addEventListener('click', () => { smsAudience = a; renderDetail(); });
        tabs.append(b);
      });
      s3.append(tabs);

      const text = ENGINE.composeSMS(unit.name, row, smsAudience);
      s3.append(el('div', 'sms', text));

      const gsm = isGsm7(text);
      const segs = Math.ceil(text.length / (gsm ? 160 : 70));
      const meta = el('div', 'sms-meta');
      meta.append(el('span', null, `${text.length} chars · ${gsm ? 'GSM-7' : 'UCS-2'}`));
      meta.append(el('span', segs > 1 ? 'over' : '', `${segs} segment${segs > 1 ? 's' : ''}`));
      s3.append(meta);
    }
    body.append(s3);

    d.append(body);
  }

  // =========================================================================
  //  Boot
  // =========================================================================
  COUNTRIES.forEach(c => {
    const h = engineFor(c);
    c.live = !!h;
    c.inProgress = !h && !!c.iso3;
  });
  // Live first, then in progress, then no coverage.
  const rank = c => (c.live ? 2 : c.inProgress ? 1 : 0);
  COUNTRIES.sort((a, b) => rank(b) - rank(a));
  {
    const hint = $('#empty-hint').querySelector('.muted');
    const btns = list => list.map(c => `<button class="linkish" data-demo="${c.name}">${c.name}</button>`).join(', ');
    const live = COUNTRIES.filter(c => c.live), wip = COUNTRIES.filter(c => c.inProgress);
    hint.innerHTML = (live.length ? `Live: ${btns(live)}. ` : 'No country has real model output yet. ') +
      (wip.length ? `Data in progress: ${wip.map(c => c.name).join(', ')}.` : '');
  }

  setTime(0);

  // Deep link: ?country=Zimbabwe&t=63&county=Mbire jumps straight to a moment.
  // Insurance for the pitch — if live scrubbing goes wrong, reload into the
  // peak of the crisis instead of dragging the slider in front of an audience.
  const qs = new URLSearchParams(location.search);
  const qCountry = qs.get('country');
  if (qCountry && COUNTRIES.some(c => c.name.toLowerCase() === qCountry.toLowerCase())) {
    const match = COUNTRIES.find(c => c.name.toLowerCase() === qCountry.toLowerCase());
    selectCountry(match.name);
    const qt = parseInt(qs.get('t'), 10);
    if (Number.isFinite(qt)) setTime(qt, { rebuild: true });
    const qCounty = qs.get('county');
    if (qCounty && byName.has(qCounty.toLowerCase())) {
      const unit = byName.get(qCounty.toLowerCase());
      selected = unit.feature;
      smsAudience = null;
      paintGlobe();
      renderDetail();
    }
  } else {
    searchInput.focus();
  }
})();
