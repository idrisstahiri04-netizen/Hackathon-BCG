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
    // Pooled-training countries (ADM2 units; geo + risk files loaded by index.html).
    { name: 'Mozambique',   iso3: 'MOZ', lat:-18.67, lng: 35.53, alt: 0.60, unitWord: 'districts' },
    { name: 'Tanzania',     iso3: 'TZA', lat: -6.37, lng: 34.89, alt: 0.55, unitWord: 'districts' },
    { name: 'Ethiopia',     iso3: 'ETH', lat:  9.10, lng: 40.50, alt: 0.55, unitWord: 'zones' },
    { name: 'Somalia',      iso3: 'SOM', lat:  5.15, lng: 46.20, alt: 0.55, unitWord: 'districts' },
    { name: 'Namibia',      iso3: 'NAM', lat:-22.96, lng: 18.49, alt: 0.55, unitWord: 'constituencies' },
    { name: 'Botswana',     iso3: 'BWA', lat:-22.33, lng: 24.68, alt: 0.50, unitWord: 'districts' },
    { name: 'South Africa', iso3: 'ZAF', lat:-30.56, lng: 22.94, alt: 0.60, unitWord: 'municipalities' },
    { name: 'Madagascar',   iso3: 'MDG', lat:-18.77, lng: 46.87, alt: 0.55, unitWord: 'districts' },
    { name: 'Angola',       iso3: 'AGO', lat:-11.20, lng: 17.87, alt: 0.55, unitWord: 'municipalities' },
    { name: 'Uganda',       iso3: 'UGA', lat:  1.37, lng: 32.29, alt: 0.40, unitWord: 'districts' },
    { name: 'Niger',        lat: 17.61, lng:  8.08, alt: 0.65 },
    { name: 'Sudan',        lat: 15.60, lng: 30.22, alt: 0.65 },
    { name: 'South Sudan',  lat:  7.86, lng: 29.69, alt: 0.65 },
    { name: 'Nigeria',      lat:  9.08, lng:  8.68, alt: 0.65 },
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

  // ---- Forecast view (CONTRACT.md sections 4 and 4b) ------------------------
  // view = 'now' (alert levels) or 'f1'..'f8' (forecast at lead 1..8 months
  // from the issue month `now`). layer = 'model' (chance choropleth) | 'fews'
  // (FEWS NET projected IPC phase) | 'both' (chance fill, phase outline).
  // Everything that paints reads `leadOf()`; 0 means the Now view.
  let view = 'now';
  let lastLead = 3;             // what F toggles back to
  let layer = 'model';
  const MAX_LEAD = 8;
  const leadOf = () => (view === 'now' ? 0 : +view.slice(1));
  const VIEWS = ['now', ...Array.from({ length: MAX_LEAD }, (_, i) => `f${i + 1}`)];
  const LAYERS = ['model', 'fews', 'both'];
  const fewsOn = () => leadOf() > 0 && layer !== 'model';
  const modelOn = () => leadOf() > 0 && layer !== 'fews';

  // Sequential scale for a probability: one hue, light -> dark, 5 bins with
  // the Watch threshold as a bin edge. Validated with the dataviz checker on
  // the dark surface (monotone lightness, step gaps, 2:1 at the dark end).
  // Deliberately not the status ramp, which is reserved for alert levels.
  const FC = {
    colors: ['#fde0ef', '#f4a6cf', '#e765a8', '#c4267f', '#9e1468'],
    none: '#6b6a64',
    glyphs: ['1', '2', '3', '4', '5'],
  };
  // IPC phase colours (IPC / FEWS NET standard, with the phase number and
  // name always beside them). Reserved for the FEWS NET outlook layer.
  const IPC = {
    colors: { 1: '#cdfacd', 2: '#fae61e', 3: '#e67800', 4: '#c80000', 5: '#640000' },
    labels: { 1: 'Minimal', 2: 'Stressed', 3: 'Crisis', 4: 'Emergency', 5: 'Famine' },
    none: '#6b6a64',
  };
  const ipcColor = ph => (ph == null ? IPC.none : IPC.colors[ph] || IPC.none);
  const ipcText = ph => (ph == null ? 'no outlook' : `Phase ${ph} ${IPC.labels[ph] || ''}`.trim());
  const fcThr = () => (ENGINE.WATCH_P_CRISIS != null ? ENGINE.WATCH_P_CRISIS : 0.57);
  // Four bin edges, always ascending: the country's Watch threshold plus the
  // three fixed edges furthest from it (thresholds differ per country).
  const fcEdges = () => {
    const thr = fcThr();
    const fixed = [0.2, 0.4, 0.6, 0.75].filter(e => Math.abs(e - thr) >= 0.05)
      .sort((a, b) => Math.abs(b - thr) - Math.abs(a - thr)).slice(0, 3);
    return [...fixed, thr].sort((a, b) => a - b);
  };
  const pct = v => `${Math.round(v * 100)}%`;
  const fcLabels = () => {
    const edges = fcEdges(), thr = fcThr(), e = edges.map(pct);
    const watch = i => (edges[i] === thr ? ' (Watch)' : '');
    return [`< ${e[0]}`, `${e[0]} – ${e[1]}${watch(0)}`, `${e[1]} – ${e[2]}${watch(1)}`, `${e[2]} – ${e[3]}${watch(2)}`, `≥ ${e[3]}${watch(3)}`];
  };
  const binOf = v => {
    if (v == null || Number.isNaN(v)) return -1;
    const i = fcEdges().findIndex(e => v < e);
    return i === -1 ? 4 : i;
  };
  const fcColor = v => { const b = binOf(v); return b < 0 ? FC.none : FC.colors[b]; };
  const fcAt = (unit, t, lead) => ENGINE.forecastAt(unit.series[t], lead);
  // Ranking score for the next 3 months: the highest chance over leads 1..3.
  const fcMax3 = (unit, t) => {
    let best = null;
    for (let L = 1; L <= 3; L++) {
      const f = fcAt(unit, t, L);
      if (f.chance != null && (best == null || f.chance > best.chance)) best = f;
    }
    return best;
  };
  const chanceWord = kind => (kind === 'event' ? 'Chance of a bad season' : 'Chance of Crisis');
  const fcConf = lead => (ENGINE.forecastConfidence ? ENGINE.forecastConfidence(lead) : { label: '', source: '' });
  const confShort = lab => ({ 'High': 'H', 'Medium-High': 'M-H', 'Medium': 'M', 'Low-Medium': 'L-M', 'Low': 'L', 'Untested': '?' })[lab]
    || (/FEWS/.test(lab) ? 'FEWS' : lab);
  const modelLeads = () => Math.min(MAX_LEAD, Math.max(3, ENGINE.maxModelLead || 0));
  const confLine = () => {
    const n = modelLeads(), parts = [];
    for (let L = 1; L <= n; L++) parts.push(`+${L} ${fcConf(L).label}`);
    return `Confidence ${parts.join(' · ')} (${fcConf(1).source})` +
      (n < MAX_LEAD ? ` · +${n + 1}..+${MAX_LEAD}: no model forecast — FEWS NET only` : '');
  };
  const noteSeason = lead => `+${lead}-month forecasts show season-level risk; district detail is less certain.`;
  const NOTE_LIVE = 'live: some inputs missing (see data notes)';
  const NOTE_READ = 'How to read: FEWS NET outlook updates ~3×/year, so its layer changes in steps; our model updates monthly.';
  // Live month (after the replay window) with model forecast fields partly null.
  const liveGaps = t => {
    const end = ENGINE.REPLAY_END_T != null ? ENGINE.REPLAY_END_T : 71;
    if (t <= end || !MODEL.units.length) return false;
    let nul = 0, tot = 0;
    const n = modelLeads();
    for (const u of MODEL.units) for (let L = 1; L <= n; L++) { tot++; if (fcAt(u, t, L).chance == null) nul++; }
    return nul > 0 && nul < tot;
  };
  // Pending text for the current lead/layer, or null when the fields exist.
  const pendingText = lead => {
    const bits = [];
    if (modelOn() || layer === 'model') {
      if (lead > (ENGINE.maxModelLead || 0) && lead > 3) bits.push(`no model forecast fields for +${lead} yet (model leads 1–${Math.max(1, ENGINE.maxModelLead || 3)})`);
      else if (!ENGINE.hasForecast) bits.push(ENGINE.pCrisisAvailable === false
        ? 'forecast fields pending: the Crisis (IPC 3+) model has no output for this country yet, so +1 shows the satellite event chance p and +2/+3 have no forecast'
        : "forecast fields pending: shown from the model's p_crisis (chance of Crisis within 1–3 months), the same for +1 to +3");
    }
    if (fewsOn() && !ENGINE.hasFews) bits.push('FEWS NET outlook fields pending (fews_phase)');
    return bits.length ? bits.join(' · ') : null;
  };

  const levelColor = n => ENGINE.LEVELS[n].color;

  // Display-level hook for the live crowd signal (js/live.js, window.CROWD):
  // the model's exported level never changes; CROWD may show it +1 (max
  // Warning) when crowd reports and a satellite family agree.
  const dispLevel = (unit, row) =>
    (window.CROWD && typeof CROWD.displayLevel === 'function') ? CROWD.displayLevel(unit.id, row) : row.level;

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
    const lead = leadOf();
    if (lead) {
      // Forecast: our chance choropleth, the FEWS NET projected phase, or
      // both (chance fill, FEWS phase on the outline and sides).
      const fOf = d => fcAt(unitOf.get(d), now, lead);
      const fill = f => (layer === 'fews' ? ipcColor(f.fews_phase) : fcColor(f.chance));
      const rank = f => (layer === 'fews' ? (f.fews_phase == null ? 0 : f.fews_phase - 1) : Math.max(0, binOf(f.chance)));
      const low = f => (layer === 'fews' ? f.fews_phase == null : binOf(f.chance) <= 0);
      world
        .polygonAltitude(d => {
          const base = 0.008 + rank(fOf(d)) * 0.005;
          return d === selected || d === hovered ? base + 0.014 : base;
        })
        .polygonCapColor(d => {
          const f = fOf(d), c = fill(f);
          if (d === selected) return c;
          return c + (low(f) ? 'c0' : 'e6');
        })
        .polygonSideColor(d => { const f = fOf(d); return (layer === 'both' ? ipcColor(f.fews_phase) : fill(f)) + '88'; })
        .polygonStrokeColor(d => {
          if (d === selected) return '#ffffff';
          if (d === hovered) return '#ffffffaa';
          if (layer === 'both') { const ph = fOf(d).fews_phase; return ph == null ? '#00000055' : ipcColor(ph); }
          return '#00000055';
        });
      return;
    }
    const lvlOf = d => { const u = unitOf.get(d); return dispLevel(u, u.series[now]); };
    world
      .polygonAltitude(d => {
        const lvl = lvlOf(d);
        const base = 0.008 + lvl * 0.0075;
        return d === selected || d === hovered ? base + 0.014 : base;
      })
      .polygonCapColor(d => {
        const lvl = lvlOf(d);
        const c = levelColor(lvl);
        if (d === selected) return c;
        return c + (lvl === 0 ? 'b0' : 'd8');      // healthy counties sit back a little
      })
      .polygonSideColor(d => levelColor(lvlOf(d)) + '66')
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
    renderTop10();
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
        (decl ? ` · disaster declared ${fmtDate(decl.date)}` : ' · no national declaration in replay window');
      $('#stat-units').parentNode.querySelector('.stat-lab').textContent = `${c.unitWord} at Warning+`;
      world.polygonsData(FEATURES);
      $('#spark').style.opacity = '1';
      $('#legend').hidden = false;
      $('#view-switch').hidden = false;
      $('#top10').hidden = false;
      $('#go-today').hidden = ENGINE.liveT == null;
      renderLegend();
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
      $('#view-switch').hidden = true;
      $('#top10').hidden = true;
      $('#go-today').hidden = true;
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

  // Text fields keep their keys. The range slider keeps its own arrow keys
  // (native step + 'input' event) but Space still plays/pauses. On a focused
  // button, Space is taken over so it toggles play instead of clicking it.
  const isTextField = t => (t.tagName === 'INPUT' && t.type !== 'range') ||
    t.tagName === 'TEXTAREA' || t.isContentEditable;
  document.addEventListener('keyup', ev => {
    if (ev.code === 'Space' && ev.target.tagName === 'BUTTON') ev.preventDefault();
  });
  document.addEventListener('keydown', ev => {
    if (isTextField(ev.target)) return;
    if (ev.code === 'Space') { ev.preventDefault(); playing ? pause() : play(); return; }
    if (ev.target === scrub && ev.key.startsWith('Arrow')) return;
    if (ev.key === 'ArrowRight') setTime(now + 1);
    else if (ev.key === 'ArrowLeft') setTime(now - 1);
    else if (ev.key === 'Escape') closeDetail();
    else if (ev.key === 'f' || ev.key === 'F') { ev.preventDefault(); toggleView(); }
    else if (/^[0-8]$/.test(ev.key) && !ev.ctrlKey && !ev.metaKey && !ev.altKey) setView(ev.key === '0' ? 'now' : `f${ev.key}`);
    else if (ev.key === 'l' || ev.key === 'L') setLayer(LAYERS[(LAYERS.indexOf(layer) + 1) % LAYERS.length]);
  });

  // ---- Horizon switch: Now | +1 … +8, and the layer switch ------------------
  (function buildHorizon() {
    const row = $('#horizon');
    VIEWS.forEach(v => {
      const b = el('button', v === 'now' ? 'on' : '');
      b.type = 'button';
      b.dataset.view = v;
      b.setAttribute('aria-pressed', String(v === 'now'));
      if (v === 'now') {
        b.append(el('span', 'vs-long', 'Now'), el('span', 'vs-short', 'Now'), el('small', null, 'alert level'));
      } else {
        const L = +v.slice(1);
        b.append(el('span', 'vs-long', `+${L}`), el('span', 'vs-short', `+${L}`), el('small'), el('em', 'vs-conf'));
      }
      row.append(b);
    });
  })();

  function setView(v) {
    if (!VIEWS.includes(v)) return;
    view = v;
    if (v !== 'now') lastLead = +v.slice(1);
    [...$('#horizon').querySelectorAll('button')].forEach(b => {
      const on = b.dataset.view === v;
      b.classList.toggle('on', on);
      b.setAttribute('aria-pressed', String(on));
    });
    document.body.classList.toggle('fc-view', v !== 'now');
    $('#layer-switch').hidden = v === 'now';
    if (history.replaceState) {
      const q = new URLSearchParams(location.search);
      if (v === 'now') q.delete('view'); else q.set('view', v);
      const qs = q.toString();
      history.replaceState(null, '', location.pathname + (qs ? `?${qs}` : ''));
    }
    refreshForecastUI();
  }
  function setLayer(l) {
    if (!LAYERS.includes(l)) return;
    layer = l;
    [...$('#layer-switch').querySelectorAll('button')].forEach(b => {
      const on = b.dataset.layer === l;
      b.classList.toggle('on', on);
      b.setAttribute('aria-pressed', String(on));
    });
    document.body.classList.toggle('fews-layer', l !== 'model');
    if (history.replaceState) {
      const q = new URLSearchParams(location.search);
      if (l === 'model') q.delete('layer'); else q.set('layer', l);
      const qs = q.toString();
      history.replaceState(null, '', location.pathname + (qs ? `?${qs}` : ''));
    }
    refreshForecastUI();
  }
  function refreshForecastUI() {
    renderLegend();
    if (!active || !active.live) return;
    paintGlobe();
    updateStats();
    updateViewCaption();
    updateLegend();
    renderTop10();
    if (selected) renderDetail();
    announce();
  }
  // F: Now <-> the last forecast lead (default +3). L: cycle the layer.
  const toggleView = () => setView(view === 'now' ? `f${lastLead}` : 'now');
  $('#horizon').addEventListener('click', ev => {
    const b = ev.target.closest('button[data-view]');
    if (b) setView(b.dataset.view);
  });
  $('#layer-switch').addEventListener('click', ev => {
    const b = ev.target.closest('button[data-layer]');
    if (b) setLayer(b.dataset.layer);
  });

  // Target month under each lead button and the caption under the switch.
  const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function updateViewCaption() {
    const live = !!(active && active.live);
    [...$('#horizon').querySelectorAll('button[data-view^="f"]')].forEach(b => {
      const L = +b.dataset.view.slice(1);
      const d = live ? ENGINE.dateAt(now + L) : null;
      b.querySelector('small').textContent = d ? `${MON[d.month]}${d.month === 0 || L === 1 ? ` '${String(d.year).slice(2)}` : ''}` : '';
      const cf = live ? fcConf(L) : { label: '', source: '' };
      b.querySelector('.vs-conf').textContent = cf.label ? confShort(cf.label) : '';
      b.title = live ? `+${L} month${L > 1 ? 's' : ''}: forecast for ${d.label}, issued end of ${ENGINE.dateAt(now).label}` +
        (cf.label ? ` · confidence ${cf.label} (${cf.source})` : '') : '';
    });
    const cap = $('#view-cap');
    const lead = leadOf();
    cap.hidden = !lead || !live;
    cap.innerHTML = '';
    if (lead && live) {
      const cf = fcConf(lead);
      const tgt = ENGINE.dateAt(now + lead).label, iss = ENGINE.dateAt(now).label;
      const what = layer === 'fews' ? 'FEWS NET projected IPC phase' : layer === 'both'
        ? 'Our chance of Crisis (IPC 3+) as fill, FEWS NET projected phase on the outline' : 'Predicted chance of Crisis (IPC 3+)';
      cap.append(el('div', null, `${what} for ${tgt} · issued end of ${iss}` + (layer === 'fews' ? '' : ' · darker = higher')));
      cap.append(el('div', 'vc-conf', `Confidence ${cf.label} — ${cf.source}`));
      if (lead >= 3) cap.append(el('div', 'vc-note', noteSeason(lead)));
      if (liveGaps(now)) cap.append(el('div', 'vc-note', NOTE_LIVE));
      if (layer !== 'model') cap.append(el('div', 'vc-read', NOTE_READ));
      const pend = pendingText(lead);
      if (pend) cap.append(el('div', 'vc-pending', pend));
    }
  }

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
    updateViewCaption();
    updateLegend();
    renderTop10();
    renderFeed({ rebuild: rebuild || wentBack });
    if (selected) renderDetail();
  }

  $('#go-today').addEventListener('click', () => {
    if (active && active.live && ENGINE.liveT != null) setTime(ENGINE.liveT);
  });

  // Tell js/live.js (the SMS demo pages) which live country and month are on
  // screen, so "Run alerts for this month" posts the right {iso3, t}.
  function announce() {
    const live = !!(active && active.live);
    window.dispatchEvent(new CustomEvent('app:state', { detail: {
      iso3: live ? active.iso3 : null, country: active ? active.name : null,
      live, t: now, label: ENGINE.dateAt(now).label, view, lead: leadOf(), layer,
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
      const frac = decl.t / (ENGINE.N_MONTHS - 1);
      mk.style.left = `${frac * 100}%`;
      if (frac > 0.7) mk.classList.add('flip');   // label on the left near the end
      mk.title = `${decl.label} — ${fmtDate(decl.date)}`;
      mk.append(el('span', null, `declared ${fmtDate(decl.date)}`));
      $('#track-wrap').append(mk);
    }
    // TODAY marker: the latest issued month (meta.live_t), when the model
    // publishes live months beyond the replay window.
    const oldToday = $('#today-mark');
    if (oldToday) oldToday.remove();
    const liveT = active && active.live ? ENGINE.liveT : null;
    if (liveT != null && liveT >= 0 && liveT < ENGINE.N_MONTHS) {
      const mk = el('div');
      mk.id = 'today-mark';
      const frac = liveT / (ENGINE.N_MONTHS - 1);
      mk.style.left = `${frac * 100}%`;
      if (frac > 0.7) mk.classList.add('flip');
      mk.title = `Today — latest issued month ${ENGINE.dateAt(liveT).label}`;
      mk.append(el('span', null, 'TODAY'));
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
    const popKnown = MODEL.units.some(u => u.props.pop != null);
    const lead = leadOf();
    const unitWord = (active && active.unitWord) || 'counties';
    const u = $('#stat-units');
    let hot, people;
    if (lead && layer === 'fews') {
      // FEWS NET layer: units projected at IPC Phase 3+ for the target month.
      hot = MODEL.units.filter(x => { const f = fcAt(x, now, lead); return f.fews_phase != null && f.fews_phase >= 3; });
      people = hot.reduce((s, x) => s + (x.props.pop || 0), 0);
      u.textContent = String(hot.length);
      u.style.color = hot.length === 0 ? 'var(--lvl-0)' : 'var(--text-primary)';
      u.parentNode.querySelector('.stat-lab').textContent =
        `${unitWord} projected IPC 3+ by ${ENGINE.dateAt(now + lead).label} (FEWS NET)`;
      $('#stat-people').parentNode.querySelector('.stat-lab').textContent = 'population in them';
    } else if (lead) {
      // Forecast view: units whose predicted chance of Crisis at this lead
      // reaches the Watch threshold.
      hot = MODEL.units.filter(x => { const f = fcAt(x, now, lead); return f.chance != null && f.chance >= fcThr(); });
      people = hot.reduce((s, x) => s + (x.props.pop || 0), 0);
      u.textContent = String(hot.length);
      u.style.color = hot.length === 0 ? 'var(--lvl-0)' : 'var(--text-primary)';
      u.parentNode.querySelector('.stat-lab').textContent =
        `${unitWord} ≥ ${pct(fcThr())} chance of Crisis by ${ENGINE.dateAt(now + lead).label}`;
      $('#stat-people').parentNode.querySelector('.stat-lab').textContent = 'population in them';
    } else {
      hot = MODEL.units.filter((x, i) => rows[i].level >= 2);
      people = hot.reduce((s, x) => s + (x.props.pop || 0), 0);
      u.textContent = String(hot.length);
      u.style.color = hot.length === 0 ? 'var(--lvl-0)'
                    : hot.length > 20 ? 'var(--lvl-3)' : 'var(--lvl-2)';
      u.parentNode.querySelector('.stat-lab').textContent = `${unitWord} at Warning+`;
      $('#stat-people').parentNode.querySelector('.stat-lab').textContent = 'population at Warning+';
    }

    // Escalations this month, straight from the model's level changes. (No
    // "SMS sent" estimate: real send counts live in the backend, not here.)
    const escal = MODEL.events.filter(e => e.t === now && e.escalation).length;

    $('#stat-people').textContent = !popKnown ? '—' : people >= 1 ? `${people.toFixed(1)}M` : `${Math.round(people * 1000)}k`;
    $('#stat-sms').textContent = String(escal);
  }

  const fmtPop = m => (m >= 1 ? `${m.toFixed(1)}M` : m > 0 ? `${Math.round(m * 1000)}k` : "0");

  // Legend items depend on the view and layer: the four alert levels; the
  // five probability bins (our model); the five IPC phases (FEWS NET); or both.
  function renderLegend() {
    const ul = $('#legend-items');
    ul.innerHTML = '';
    const lg = $('#legend');
    lg.classList.toggle('fc', leadOf() > 0);
    if (!leadOf()) {
      ENGINE.LEVELS.forEach(L => {
        const li = el('li');
        li.dataset.level = L.n;
        const sw = el('span', 'sw', L.glyph);
        sw.style.background = L.color;
        li.append(sw, el('span', 'n', `L${L.n}`), el('span', null, L.label), el('span', 'ct', '0'));
        ul.append(li);
      });
      return;
    }
    const both = layer === 'both';
    if (modelOn()) {
      if (both) ul.append(el('li', 'lg-group', 'Our model · chance of Crisis (fill)'));
      fcLabels().forEach((lab, i) => {
        const li = el('li');
        li.dataset.bin = i;
        const sw = el('span', 'sw', FC.glyphs[i]);
        sw.style.background = FC.colors[i];
        if (i >= 2) sw.style.color = '#fff';
        li.append(sw, el('span', null, lab), el('span', 'ct', '0'));
        ul.append(li);
      });
      const li = el('li');
      li.dataset.bin = -1;
      li.hidden = true;
      const sw = el('span', 'sw', '?');
      sw.style.background = FC.none;
      li.append(sw, el('span', null, 'no forecast'), el('span', 'ct', '0'));
      ul.append(li);
    }
    if (fewsOn()) {
      if (both) ul.append(el('li', 'lg-group', 'FEWS NET outlook · projected IPC phase (outline)'));
      [1, 2, 3, 4, 5].forEach(ph => {
        const li = el('li');
        li.dataset.phase = ph;
        const sw = el('span', 'sw', String(ph));
        sw.style.background = IPC.colors[ph];
        if (ph >= 3) sw.style.color = '#fff';
        li.append(sw, el('span', null, `Phase ${ph} ${IPC.labels[ph]}`), el('span', 'ct', '0'));
        ul.append(li);
      });
      const li = el('li');
      li.dataset.phase = 0;
      const sw = el('span', 'sw', '?');
      sw.style.background = IPC.none;
      li.append(sw, el('span', null, 'no outlook'), el('span', 'ct', '0'));
      ul.append(li);
    }
  }
  renderLegend();

  function updateLegend() {
    const lead = leadOf();
    const title = $('#legend .legend-title');
    const note = $('#legend-note');
    if (!lead) {
      title.textContent = 'Shortage risk level';
      note.hidden = true;
      const counts = [0, 0, 0, 0];
      MODEL.units.forEach(u => counts[u.series[now].level]++);
      [...$('#legend-items').children].forEach(li => {
        li.querySelector('.ct').textContent = String(counts[+li.dataset.level]);
      });
      return;
    }
    title.textContent = `Forecast issued end of ${ENGINE.dateAt(now).label} for ` +
      `${ENGINE.dateAt(now + lead).label} — using only data available then`;
    const counts = [0, 0, 0, 0, 0], phases = [0, 0, 0, 0, 0, 0];
    let none = 0;
    MODEL.units.forEach(u => {
      const f = fcAt(u, now, lead);
      const b = binOf(f.chance); if (b < 0) none++; else counts[b]++;
      phases[f.fews_phase == null ? 0 : f.fews_phase]++;
    });
    [...$('#legend-items').children].forEach(li => {
      const ct = li.querySelector('.ct');
      if (!ct) return;
      if (li.dataset.bin != null) {
        const b = +li.dataset.bin;
        if (b < 0) { li.hidden = none === 0; ct.textContent = String(none); }
        else ct.textContent = String(counts[b]);
      } else if (li.dataset.phase != null) {
        const ph = +li.dataset.phase;
        if (ph === 0) li.hidden = phases[0] === 0;
        ct.textContent = String(phases[ph]);
      }
    });
    const cf = fcConf(lead);
    const lines = [{ c: 'ln-conf', s: `Confidence ${cf.label} — ${cf.source}.` }];
    if (lead >= 3) lines.push({ c: 'ln-note', s: noteSeason(lead) });
    if (liveGaps(now)) lines.push({ c: 'ln-note', s: NOTE_LIVE });
    if (layer !== 'model') lines.push({ c: 'ln-read', s: NOTE_READ });
    const pend = pendingText(lead);
    if (pend) lines.push({ c: 'ln-pending', s: pend[0].toUpperCase() + pend.slice(1) + '.' });
    note.hidden = false;
    note.innerHTML = '';
    lines.forEach(l => note.append(el('div', l.c, l.s)));
  }

  // =========================================================================
  //  Top 10 most at risk, next 3 months (for the issue month on the slider)
  // =========================================================================
  function renderTop10() {
    const box = $('#top10'), ol = $('#top10-list');
    if (!active || !active.live) { box.hidden = true; return; }
    box.hidden = false;
    const ranked = MODEL.units
      .map(u => ({ u, f: fcMax3(u, now) }))
      .filter(x => x.f && x.f.chance != null)
      .sort((a, b) => b.f.chance - a.f.chance || a.u.name.localeCompare(b.u.name))
      .slice(0, 10);
    $('#top10-sub').textContent = `issued end of ${ENGINE.dateAt(now).label} · ${ENGINE.dateAt(now + 1).label} – ${ENGINE.dateAt(now + 3).label}`;
    ol.innerHTML = '';
    if (!ranked.length) {
      ol.append(el('li', 't10-empty', 'No forecast for this month.'));
    }
    ranked.forEach(({ u, f }, i) => {
      const li = el('li', u.feature === selected ? 'is-sel' : '');
      li.dataset.id = u.id;
      li.setAttribute('role', 'button');
      li.tabIndex = 0;
      const lvl = dispLevel(u, u.series[now]), L = ENGINE.LEVELS[lvl];
      const dot = el('span', 'lv', `L${lvl}`);
      dot.style.background = L.color;
      dot.title = `${L.label} now`;
      const bar = el('span', 'bar');
      const fill = el('i');
      fill.style.width = `${Math.round(f.chance * 100)}%`;
      fill.style.background = fcColor(f.chance);
      bar.append(fill);
      const thr = el('b');
      thr.style.left = `${fcThr() * 100}%`;
      bar.append(thr);
      li.append(el('span', 'rk', String(i + 1)), el('span', 'nm', u.name), bar,
        el('span', 'pc', pct(f.chance)), dot);
      li.title = `${chanceWord(f.kind)} by ${f.target_label}: ${pct(f.chance)}`;
      const go = () => {
        selected = u.feature;
        smsAudience = null;
        world.pointOfView({ lat: u.props.lat, lng: u.props.lng, altitude: 0.55 }, 900);
        paintGlobe();
        renderDetail();
        renderTop10();
      };
      li.addEventListener('click', go);
      li.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); go(); } });
      ol.append(li);
    });
    const note = $('#top10-note');
    note.hidden = false;
    note.textContent = `Ranked on the highest chance over +1 to +3 months · ${confLine()}` +
      (ENGINE.hasForecast ? '' : ' · forecast fields pending (p_crisis shown)') +
      (liveGaps(now) ? ` · ${NOTE_LIVE}` : '');
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
    // The OFFICIAL declaration note is never trimmed (and is sticky in CSS).
    while (feedEl.children.length > 120) {
      const victim = [...feedEl.children].reverse().find(n => !n.classList.contains('decl'));
      if (!victim) break;
      victim.remove();
    }
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
        `Shortage risk <b>${e.p == null ? '—' : Math.round(e.p * 100) + '%'}</b> at <b>${e.horizon} weeks</b> · ` +
        `<b>${e.agreeing}/${ENGINE.N_FAMILIES}</b> source families agree · confidence ${e.confidence}` +
        (e.pop != null ? ` · population <b>${fmtPop(e.pop)}</b>` : '');
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
  // GSM 03.38: basic set costs 1 septet, the extension table (^{}\\[~]|€ and
  // form feed) costs 2 (escape + char). Multi-part messages carry a header:
  // 153 septets per part for GSM-7, 67 chars for UCS-2.
  const GSM7_BASIC = new Set(('@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !"#¤%&\'()*+,-./0123456789:;<=>?' +
    '¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà').split(''));
  const GSM7_EXT = new Set('^{}\\[~]|€\f'.split(''));
  function smsCost(text) {
    const chars = [...text];
    const gsm = chars.every(ch => GSM7_BASIC.has(ch) || GSM7_EXT.has(ch));
    if (gsm) {
      const n = chars.reduce((k, ch) => k + (GSM7_EXT.has(ch) ? 2 : 1), 0);
      return { gsm, n, unit: 'septets', segs: n <= 160 ? 1 : Math.ceil(n / 153) };
    }
    const n = chars.length;
    return { gsm, n, unit: 'chars', segs: n <= 70 ? 1 : Math.ceil(n / 67) };
  }

  function closeDetail() {
    selected = null;
    $('#detail').hidden = true;
    paintGlobe();
    renderTop10();
  }

  // Forecast block of the unit panel: "Chance of Crisis by <target>: NN%",
  // then a small SVG of the past 6 issued months (solid), the next 1-8
  // months of our model (dotted) with the Watch threshold, and the FEWS NET
  // projected phase as a stepped strip (ML1 near term / ML2 medium term,
  // with the publication month). All numbers are the model's own fields;
  // nothing is interpolated.
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const svgEl = (tag, attrs, txt) => {
    const n = document.createElementNS(SVG_NS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (txt != null) n.textContent = txt;
    return n;
  };
  const yearOf = label => { const m = /\b(20\d\d)\b/.exec(label || ''); return m ? m[1] : ''; };
  function buildForecastSection(unit) {
    const sect = el('div', 'd-sect fc-sect');
    const lead = leadOf() || 3;
    const f = fcAt(unit, now, lead);
    const thr = fcThr();
    const cf = fcConf(lead);

    // Headline number(s)
    if (layer !== 'fews') {
      const head = el('div', 'fc-head');
      const big = el('span', 'fc-big', f.chance == null ? '—' : pct(f.chance));
      const sw = el('span', 'fc-sw');
      sw.style.background = fcColor(f.chance);
      const lab = el('div', 'fc-lab');
      lab.append(el('span', null, `${chanceWord(f.kind)} by `), el('b', null, f.target_label), el('span', null, ':'));
      head.append(lab, sw, big);
      sect.append(head);
      sect.append(el('div', 'fc-sub',
        f.chance == null ? (f.pending ? `No model forecast fields for +${lead} yet.` : 'No forecast for this district and month.') :
        `issued end of ${ENGINE.dateAt(now).label}` +
        (f.kind === 'crisis' ? ` · IPC 3+ · Watch threshold ${pct(thr)}` : ' · satellite event model') +
        (f.chance >= thr && f.kind === 'crisis' ? ' · above threshold' : '') +
        (f.source ? ` · ${f.source}` : '')));
    }
    // FEWS NET projected phase line (headline in the FEWS layer)
    {
      const fl = el('div', layer === 'fews' ? 'fc-head fc-fews-head' : 'fc-fews-line');
      const chip = el('span', 'fc-ph', f.fews_phase == null ? '?' : String(f.fews_phase));
      chip.style.background = ipcColor(f.fews_phase);
      if (f.fews_phase != null && f.fews_phase >= 3) chip.style.color = '#fff';
      const txt = el('span');
      txt.append(el('span', null, 'FEWS NET projected '), el('b', null, f.fews_phase == null ? (ENGINE.hasFews ? 'no outlook' : 'pending') : ipcText(f.fews_phase)),
        el('span', null, ` for ${f.target_label}` + (f.fews_scenario ? ` · ${f.fews_scenario}` : '') + (f.fews_published ? ` · published ${f.fews_published}` : '')));
      fl.append(chip, txt);
      sect.append(fl);
    }
    const conf = el('div', 'fc-conf');
    conf.append(el('span', 'fc-conf-chip' + (cf.none ? ' none' : ''), cf.none ? cf.label : `${cf.label} confidence`),
      el('span', null, ` at +${lead} month${lead > 1 ? 's' : ''} — ${cf.source}`));
    sect.append(conf);

    // Chart data: past 6 issued months + now (solid), next 1..8 (dotted).
    const histKind = unit.series.some(r => r.p_crisis != null) ? 'crisis' : 'event';
    const histVal = r => (r.missing ? null : histKind === 'crisis' ? r.p_crisis : r.p);
    const pts = [];
    for (let k = -6; k <= 0; k++) {
      const t = now + k;
      pts.push({ i: k + 6, t, v: t >= 0 ? histVal(unit.series[t]) : null, label: ENGINE.dateAt(Math.max(0, t)).label, past: true });
    }
    for (let L = 1; L <= MAX_LEAD; L++) {
      const g = fcAt(unit, now, L);
      pts.push({ i: 6 + L, t: now + L, v: g.chance, label: g.target_label, past: false, lead: L, g });
    }
    const N = pts.length - 1;                               // 14 steps
    const W = 280, H = 164, padL = 28, padR = 6, padT = 10, plotB = 92;
    const x = i => padL + (i / N) * (W - padL - padR);
    const y = v => padT + (1 - v) * (plotB - padT);
    const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, class: 'fc-chart', role: 'img',
      'aria-label': `${chanceWord(histKind)}: past 6 months, next 8 months of our model, and the FEWS NET projected phase` });
    [0, 0.5, 1].forEach(g => {
      svg.append(svgEl('line', { x1: padL, x2: W - padR, y1: y(g), y2: y(g), class: 'fc-grid' }));
      svg.append(svgEl('text', { x: padL - 4, y: y(g) + 3, class: 'fc-ax', 'text-anchor': 'end' }, `${Math.round(g * 100)}%`));
    });
    if (histKind === 'crisis') {
      svg.append(svgEl('line', { x1: padL, x2: W - padR, y1: y(thr), y2: y(thr), class: 'fc-thr' }));
      svg.append(svgEl('text', { x: W - padR, y: y(thr) - 3, class: 'fc-thr-lab', 'text-anchor': 'end' }, `Watch ${pct(thr)}`));
    }
    const xn = (x(6) + x(7)) / 2;
    svg.append(svgEl('line', { x1: xn, x2: xn, y1: padT - 4, y2: plotB + 2, class: 'fc-now' }));
    svg.append(svgEl('text', { x: xn + 3, y: padT + 2, class: 'fc-now-lab' }, 'forecast →'));
    // model-lead shading: leads beyond the tested model are FEWS-only
    const ml = ENGINE.maxModelLead || 0;
    if (ml < MAX_LEAD) {
      const x0 = (x(6 + Math.max(ml, 0)) + x(7 + Math.max(ml, 0))) / 2;
      svg.append(svgEl('rect', { x: x0, y: padT - 4, width: W - padR - x0, height: plotB - padT + 6, class: 'fc-nomodel' }));
      svg.append(svgEl('text', { x: W - padR, y: plotB - 3, class: 'fc-nomodel-lab', 'text-anchor': 'end' }, 'no model forecast'));
    }
    const past = pts.filter(p => p.past && p.v != null);
    if (past.length > 1) {
      svg.append(svgEl('path', { d: past.map((p, k) => `${k ? 'L' : 'M'}${x(p.i).toFixed(1)},${y(p.v).toFixed(1)}`).join(''), class: 'fc-line' }));
    }
    const nowPt = pts[6];
    const fut = pts.filter(p => !p.past && p.v != null);
    if (fut.length) {
      const seq = (nowPt.v != null ? [nowPt] : []).concat(fut);
      if (seq.length > 1) {
        svg.append(svgEl('path', { d: seq.map((p, k) => `${k ? 'L' : 'M'}${x(p.i).toFixed(1)},${y(p.v).toFixed(1)}`).join(''), class: 'fc-line fc-dotted' }));
      }
    }
    pts.forEach(p => {
      if (p.v == null) {
        if (p.t >= 0 && (p.past || (p.lead <= Math.max(3, ml)))) svg.append(svgEl('text', { x: x(p.i), y: y(0) - 3, class: 'fc-miss', 'text-anchor': 'middle' }, '·'));
        return;
      }
      const sel = !p.past && p.lead === lead;
      const c = svgEl('circle', { cx: x(p.i), cy: y(p.v), r: sel ? 5 : p.past ? 2.6 : 3,
        class: p.past ? 'fc-dot' : `fc-dot fut${sel ? ' sel' : ''}` });
      c.append(svgEl('title', {}, `${p.label}: ${pct(p.v)}${p.past ? '' : ` (our model, +${p.lead} month${p.lead > 1 ? 's' : ''}, confidence ${fcConf(p.lead).label})`}`));
      svg.append(c);
    });
    // x labels: past at -6, -3, 0; every forecast lead
    pts.forEach(p => {
      if (p.t < 0) return;
      if (p.past && p.i % 3 !== 0) return;
      svg.append(svgEl('text', { x: x(p.i), y: plotB + 11, class: p.past ? 'fc-ax' : `fc-ax fut${!p.past && p.lead === lead ? ' sel' : ''}`, 'text-anchor': 'middle' },
        p.past ? p.label.slice(0, 3) : `+${p.lead}`));
    });
    // FEWS NET projected phase strip (steps), ML1/ML2 and publication month
    const sy = plotB + 17, sh = 12;
    svg.append(svgEl('text', { x: padL - 4, y: sy + 9, class: 'fc-ax', 'text-anchor': 'end' }, 'FEWS'));
    const half = (x(1) - x(0)) / 2;
    const scen = [];
    pts.filter(p => !p.past).forEach(p => {
      const ph = p.g.fews_phase;
      const r = svgEl('rect', { x: x(p.i) - half + 0.5, y: sy, width: 2 * half - 1, height: sh, rx: 2, class: 'fc-step' + (ph == null ? ' none' : '') });
      r.setAttribute('fill', ipcColor(ph));
      r.append(svgEl('title', {}, `${p.label}: FEWS NET ${ipcText(ph)}${p.g.fews_scenario ? ` (${p.g.fews_scenario}` + (p.g.fews_published ? `, published ${p.g.fews_published}` : '') + ')' : ''}`));
      svg.append(r);
      if (ph != null) svg.append(svgEl('text', { x: x(p.i), y: sy + 9, class: 'fc-step-lab' + (ph >= 3 ? ' dark' : ''), 'text-anchor': 'middle' }, String(ph)));
      if (p.g.fews_scenario) {
        const last = scen[scen.length - 1];
        if (last && last.s === p.g.fews_scenario && last.pub === (p.g.fews_published || '')) last.to = p.i;
        else scen.push({ s: p.g.fews_scenario, pub: p.g.fews_published || '', from: p.i, to: p.i });
      }
    });
    if (scen.length) {
      scen.forEach(g => {
        const x1 = x(g.from) - half + 1, x2 = x(g.to) + half - 1, ym = sy + sh + 5;
        svg.append(svgEl('path', { d: `M${x1},${ym - 2} V${ym} H${x2} V${ym - 2}`, class: 'fc-brace' }));
        svg.append(svgEl('text', { x: (x1 + x2) / 2, y: ym + 9, class: 'fc-brace-lab', 'text-anchor': 'middle' }, g.s));
      });
      // publication month(s) once, so the brace labels never collide
      const pubs = [...new Set(scen.map(g => g.pub).filter(Boolean))];
      if (pubs.length) svg.append(svgEl('text', { x: W - padR, y: H - 2, class: 'fc-pub', 'text-anchor': 'end' },
        `outlook published ${pubs.join(' / ')}`));
    } else {
      svg.append(svgEl('text', { x: (x(7) + x(14)) / 2, y: sy + sh + 14, class: 'fc-brace-lab', 'text-anchor': 'middle' },
        ENGINE.hasFews ? 'no FEWS NET outlook covers these months' : 'FEWS NET outlook: pending'));
    }
    sect.append(svg);

    const leg = el('div', 'fc-leg');
    leg.append(el('span', 'solid', 'past 6 months (issued)'), el('span', 'dotted', `our model +1 to +${MAX_LEAD}`), el('span', 'steps', 'FEWS NET phase (steps)'));
    sect.append(leg);
    const yr0 = yearOf(pts.find(p => p.t >= 0)?.label), yr1 = yearOf(pts[pts.length - 1].label);
    sect.append(el('div', 'fc-confs', `${yr0 && yr1 && yr0 !== yr1 ? `${yr0} → ${yr1} · ` : yr1 ? `${yr1} · ` : ''}${confLine()}`));
    if (lead >= 3) sect.append(el('div', 'fc-note', noteSeason(lead)));
    if (liveGaps(now)) sect.append(el('div', 'fc-note', NOTE_LIVE));
    sect.append(el('div', 'fc-read', NOTE_READ));
    const pend = pendingText(lead);
    if (pend) sect.append(el('div', 'fc-pending', pend[0].toUpperCase() + pend.slice(1) + '.'));
    else if (f.derived && !f.pending) sect.append(el('div', 'fc-pending', "Forecast fields pending: dotted values are the model's p_crisis for the 1–3 month window."));
    return sect;
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
      (unit.props.pop != null ? ` · population ${fmtPop(unit.props.pop)}` : ''));
    if (ENGINE.EVENTS[row.event]) sub.append(el('span', 'evt', ENGINE.EVENTS[row.event]));
    ht.append(sub);
    const dl = dispLevel(unit, row), DL = ENGINE.LEVELS[dl];
    const chip = el('span', 'chip' + (dl !== row.level ? ' crowd-up' : ''),
      `${DL.glyph} L${dl} ${DL.label.toUpperCase()}`);
    chip.style.background = DL.color;
    if (dl !== row.level) chip.title = `Model level L${row.level} ${L.label}; shown +1 because crowd reports and a satellite family agree`;
    chip.style.alignSelf = 'center';
    chip.style.marginLeft = 'auto';
    const close = el('button', 'd-close', '×');
    close.setAttribute('aria-label', 'Close');
    close.addEventListener('click', closeDetail);
    head.append(ht, chip, close);
    d.append(head);

    const body = el('div', 'd-body');

    // --- forecast: the headline chance and the past/next chart
    body.append(buildForecastSection(unit));

    // --- headline numbers
    const pm = el('div', 'd-pm');
    const big = el('span', 'big', row.p == null ? '—' : `${Math.round(row.p * 100)}%`);
    big.style.color = L.color;
    const pwrap = el('div');
    pwrap.append(big);
    pwrap.append(el('div', 'unit', `probability of shortage at ${row.horizon} weeks`));
    const cwrap = el('div');
    if (row.held) {
      // Level kept only by hysteresis: the sources no longer need to agree.
      cwrap.className = 'held';
      cwrap.append(el('span', 'big', 'held'));
      cwrap.append(el('div', 'unit',
        `needs 3 calm months to stand down · ${row.agreeing}/${ENGINE.N_FAMILIES} sources in alarm now`));
    } else {
      cwrap.append(el('span', 'big', `${row.agreeing}/${ENGINE.N_FAMILIES}`));
      cwrap.append(el('div', 'unit', `sources agree · ${row.confidence} confidence`));
    }
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

    // --- crowd reports (live, from the SMS backend; js/live.js)
    if (window.CROWD && typeof CROWD.detailSection === 'function') {
      const cs = CROWD.detailSection(unit, row);
      if (cs) body.append(cs);
    }

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

      const { gsm, n, unit: cu, segs } = smsCost(text);
      const meta = el('div', 'sms-meta');
      meta.append(el('span', null, `${n} ${cu} · ${gsm ? 'GSM-7' : 'UCS-2'}`));
      meta.append(el('span', segs > 1 ? 'over' : '', `${segs} segment${segs > 1 ? 's' : ''}`));
      s3.append(meta);
    }
    body.append(s3);

    d.append(body);
  }

  // =========================================================================
  //  Boot
  // =========================================================================
  // Small surface for js/live.js: the globe (HTML badges) and a repaint after
  // crowd data changes. Nothing else of the app state is exposed.
  window.APP = { world, repaint() { paintGlobe(); if (selected) renderDetail(); } };

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

  // Top-10 list starts collapsed on phones so the feed keeps room.
  if (window.matchMedia && window.matchMedia('(max-width: 720px)').matches) $('#top10').open = false;

  // Deep link: ?country=Zimbabwe&t=63&county=Mbire&view=f3&layer=both jumps
  // straight to a moment (view = now | f1..f8, layer = model | fews | both). Insurance for the pitch — if live
  // scrubbing goes wrong, reload into the peak of the crisis instead of
  // dragging the slider in front of an audience.
  const qs = new URLSearchParams(location.search);
  const qCountry = qs.get('country');
  const qView = (qs.get('view') || '').toLowerCase();
  if (VIEWS.includes(qView)) setView(qView);
  const qLayer = (qs.get('layer') || '').toLowerCase();
  if (LAYERS.includes(qLayer)) setLayer(qLayer);
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
      renderTop10();
    }
  } else {
    searchInput.focus();
  }
})();
