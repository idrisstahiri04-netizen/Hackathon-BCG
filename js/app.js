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
  // Only Kenya has a model behind it. The rest are listed so the search is
  // honest about where coverage does and does not exist yet.
  const COUNTRIES = [
    { name: 'Kenya',        lat:  0.53, lng: 37.86, alt: 0.38, live: true },
    { name: 'Ethiopia',     lat:  9.10, lng: 40.50, alt: 0.65 },
    { name: 'Somalia',      lat:  5.15, lng: 46.20, alt: 0.65 },
    { name: 'Uganda',       lat:  1.37, lng: 32.29, alt: 0.65 },
    { name: 'Tanzania',     lat: -6.37, lng: 34.89, alt: 0.65 },
    { name: 'Zimbabwe',     lat:-19.02, lng: 29.15, alt: 0.65 },
    { name: 'Zambia',       lat:-13.13, lng: 27.85, alt: 0.65 },
    { name: 'Malawi',       lat:-13.25, lng: 34.30, alt: 0.65 },
    { name: 'Niger',        lat: 17.61, lng:  8.08, alt: 0.65 },
    { name: 'Sudan',        lat: 15.60, lng: 30.22, alt: 0.65 },
    { name: 'South Sudan',  lat:  7.86, lng: 29.69, alt: 0.65 },
    { name: 'Nigeria',      lat:  9.08, lng:  8.68, alt: 0.65 },
    { name: 'Madagascar',   lat:-18.77, lng: 46.87, alt: 0.65 },
    { name: 'Morocco',      lat: 31.79, lng: -7.09, alt: 0.65 },
  ];

  const WORLD_VIEW = { lat: 6, lng: 24, altitude: 2.3 };

  // ---- Model --------------------------------------------------------------
  // Built in boot(), once the FEWS NET files have loaded — the official source
  // family depends on them, so there is no model before then.
  let MODEL = null;
  let byName = new Map();
  let LIVE = null;        // latest FEWS NET situation, from /api/live
  let liveMode = false;

  let now = 0;            // month index
  let rendered = -1;      // how far the feed has been filled, for incremental appends
  let playing = false;
  let speed = 1;
  let timer = null;
  let active = null;      // the selected country, or null
  let selected = null;    // the county open in the detail panel
  let hovered = null;
  let smsAudience = 'farmer';

  const levelColor = n => SIM.LEVELS[n].color;

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
  // The single source of truth for "what colour is this county right now".
  // In replay mode that is the model at month `now`; in live mode it is the
  // current FEWS NET classification.
  function levelAt(countyName) {
    if (liveMode) return liveLevel(countyName);
    const u = byName.get(countyName);
    return u ? u.series[now].level : 0;
  }

  function paintGlobe() {
    if (!active || !active.live || !MODEL) return;
    world
      .polygonAltitude(d => {
        const base = 0.008 + levelAt(d.properties.name) * 0.0075;
        return d === selected || d === hovered ? base + 0.014 : base;
      })
      .polygonCapColor(d => {
        const lvl = levelAt(d.properties.name);
        const c = levelColor(lvl);
        if (d === selected) return c;
        return c + (lvl === 0 ? 'b0' : 'd8');      // healthy counties sit back a little
      })
      .polygonSideColor(d => levelColor(levelAt(d.properties.name)) + '66')
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
      li.append(el('span', c.live ? 'tag live' : 'tag soon', c.live ? 'Live' : 'No coverage'));
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
    $('#hud-sub').textContent = c.live
      ? '47 counties · pilot country'
      : 'not yet modelled';

    if (c.live) {
      world.polygonsData(KENYA_COUNTIES.features);
      $('#spark').style.opacity = '1';
      $('#legend').hidden = false;
      $('#feed-sub').textContent = 'Kenya · 47 counties';
      setTime(0, { rebuild: true });
    } else {
      // Honest empty state rather than a fake map.
      world.polygonsData([]);
      $('#legend').hidden = true;
      $('#feed-sub').textContent = `${c.name} · no coverage`;
      $('#feed').innerHTML = '';
      $('#feed-count').textContent = '0';
      $('#spark').style.opacity = '.18';   // the curve is Kenya's, not theirs
      $('#feed-empty').hidden = false;
      $('#feed-empty').innerHTML =
        `<p>No model for ${c.name} yet.</p>` +
        `<p class="muted">Kenya is the pilot. Adding a country needs its admin boundaries, ` +
        `a crop mask and one season of price data.</p>`;
      ['#stat-units', '#stat-people', '#stat-sms'].forEach(s => $(s).textContent = '—');
      pause();
    }
  }

  // =========================================================================
  //  Timeline
  // =========================================================================
  const scrub = $('#scrub');
  scrub.max = String(SIM.N_MONTHS - 1);

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
    if (now >= SIM.N_MONTHS - 1) setTime(0, { rebuild: true });
    playing = true;
    $('.ic-play').hidden = true;
    $('.ic-pause').hidden = false;
    timer = setInterval(() => {
      if (now >= SIM.N_MONTHS - 1) { pause(); return; }
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
    t = Math.max(0, Math.min(SIM.N_MONTHS - 1, t));
    const wentBack = t < now;
    now = t;
    scrub.value = String(t);

    const d = SIM.dateAt(t);
    $('#clock-date').textContent = d.label;
    $('#clock-sub').textContent = `month ${t + 1} of ${SIM.N_MONTHS}`;

    if (!active || !active.live) return;

    paintGlobe();
    updateStats();
    updateLegendCounts();
    renderFeed({ rebuild: rebuild || wentBack });
    if (selected) renderDetail();
  }

  // Year ticks under the slider.
  (function buildTicks() {
    const wrap = $('#track-marks');
    for (let y = SIM.START_YEAR; y < SIM.START_YEAR + SIM.N_MONTHS / 12; y++) {
      const t = (y - SIM.START_YEAR) * 12;
      const m = el('span', 'yr', String(y));
      m.style.left = `${(t / (SIM.N_MONTHS - 1)) * 100}%`;
      wrap.append(m);
    }
  })();

  // The strip behind the slider: share of counties at Warning or above over
  // the whole window. One measure, one hue, no axis furniture — it exists to
  // show you where the crisis is, not to be read off precisely.
  function buildSpark() {
    const svg = $('#spark');
    const W = 1000, H = 30;
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    const pts = MODEL.national.map((v, i) => [
      (i / (SIM.N_MONTHS - 1)) * W,
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
    if (!MODEL) return;
    const warnPlus = MODEL.units.filter(u => levelAt(u.name) >= 2);
    if (liveMode) {
      const people = warnPlus.reduce((s, u) => s + u.props.pop, 0);
      const reach = MODEL.units
        .filter(u => levelAt(u.name) >= 1)
        .reduce((s, u) => s + u.props.pop * 1000 * 0.11 * SIM.audiencesFor(levelAt(u.name)).length / 3, 0);
      const el0 = $('#stat-units');
      el0.textContent = String(warnPlus.length);
      el0.style.color = warnPlus.length === 0 ? 'var(--lvl-0)'
                      : warnPlus.length > 20 ? 'var(--lvl-3)' : 'var(--lvl-2)';
      $('#stat-people').textContent = people >= 1 ? `${people.toFixed(1)}M` : `${Math.round(people * 1000)}k`;
      $('#stat-sms').textContent = fmtCompact(Math.round(reach));
      $('#stat-sms').closest('.stat').querySelector('.stat-lab').textContent = 'SMS if sent now';
      return;
    }
    $('#stat-sms').closest('.stat').querySelector('.stat-lab').textContent = 'SMS sent to date';
    const people = warnPlus.reduce((s, u) => s + u.props.pop, 0);

    // Cumulative messages: one per subscriber reached, each time a county
    // escalates. Rough, but it is the number that drives the cost model.
    let sms = 0;
    for (const e of MODEL.events) {
      if (e.t > now || !e.escalation) continue;
      sms += Math.round(e.people * 1000 * 0.11) * e.audiences.length / 3;
    }

    const u = $('#stat-units');
    u.textContent = String(warnPlus.length);
    u.style.color = warnPlus.length === 0 ? 'var(--lvl-0)'
                  : warnPlus.length > 20 ? 'var(--lvl-3)' : 'var(--lvl-2)';

    $('#stat-people').textContent = people >= 1 ? `${people.toFixed(1)}M` : `${Math.round(people * 1000)}k`;
    $('#stat-sms').textContent = fmtCompact(Math.round(sms));
  }

  function fmtCompact(n) {
    if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
    if (n >= 1e3) return `${(n / 1e3).toFixed(0)}k`;
    return String(n);
  }

  (function buildLegend() {
    const ul = $('#legend-items');
    SIM.LEVELS.forEach(L => {
      const li = el('li');
      li.dataset.level = L.n;
      const sw = el('span', 'sw', L.glyph);
      sw.style.background = L.color;
      li.append(sw, el('span', 'n', `L${L.n}`), el('span', null, L.label), el('span', 'ct', '0'));
      ul.append(li);
    });
  })();

  function updateLegendCounts() {
    if (!MODEL) return;
    const counts = [0, 0, 0, 0];
    MODEL.units.forEach(u => counts[levelAt(u.name)]++);
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

  // Renders the recommendation block: what is grown or herded here, what to
  // do about it, and who can actually supply the resources.
  function buildAdvice(rec, countyName) {
    const box = el('div', 'n-advice');

    const head = el('div', 'adv-head');
    head.append(el('span', 'adv-kind', rec.primary));
    if (rec.zones.length) {
      head.append(el('span', 'adv-zone', rec.zones[0]));
    }
    box.append(head);

    if (rec.crops.length) {
      const r = el('div', 'adv-row');
      r.append(el('span', 'adv-lab', 'At risk'));
      const chips = el('span', 'adv-chips');
      rec.crops.forEach(c => chips.append(el('span', 'crop', c)));
      r.append(chips);
      box.append(r);
    }

    if (rec.actions.length) {
      const r = el('div', 'adv-row');
      r.append(el('span', 'adv-lab', 'Do now'));
      const ul = el('ul', 'adv-actions');
      rec.actions.forEach(a => ul.append(el('li', null, a)));
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
        t.append(el('span', 'res-n', res.name));
        t.append(el('span', 'res-b', res.body));
        d.append(t);
        d.append(el('div', 'res-w', res.what));
        d.title = `Eligibility: ${res.who}`;
        list.append(d);
      });
      r.append(list);
      box.append(r);
    }

    // Say where help does NOT reach. A planner needs the gap, not just the list.
    rec.gaps.forEach(g => box.append(el('div', 'adv-gap', g)));
    return box;
  }

  function buildNote(e, animate) {
    const L = SIM.LEVELS[e.to];
    const li = el('li', 'note' + (animate ? ' is-new' : '') + (e.escalation ? '' : ' deesc'));
    li.style.setProperty('--lvl', L.color);
    li.dataset.county = e.county;
    li.dataset.t = e.t;

    const top = el('div', 'n-top');
    const chip = el('span', 'chip', `${L.glyph} L${e.to} ${L.label.toUpperCase()}`);
    top.append(chip, el('span', 'n-county', e.county));
    top.append(el('span', 'n-date', e.live ? (e.asOf || 'current') : SIM.dateAt(e.t).label));
    li.append(top);

    li.append(el('div', 'n-move',
      e.escalation
        ? `escalated from L${e.from} ${SIM.LEVELS[e.from].label}`
        : `stood down from L${e.from} ${SIM.LEVELS[e.from].label}`));

    if (e.escalation) {
      const line = el('div', 'n-line');
      if (e.live) {
        // Live mode carries no model probability — this is FEWS NET's own
        // published classification, so we show that and their projection.
        const IPCN = ['', 'Minimal', 'Stressed', 'Crisis', 'Emergency', 'Famine'];
        line.innerHTML =
          `<b>IPC Phase ${e.ipcPhase} ${IPCN[e.ipcPhase]}</b> as of <b>${e.asOf}</b>` +
          (e.projection
            ? ` · FEWS NET near-term projection <b>Phase ${e.projection} ${IPCN[e.projection]}</b>`
            : '') +
          ` · <b>${e.people.toFixed(2)}M</b> people`;
      } else {
        line.innerHTML =
          `Shortage risk <b>${Math.round(e.p * 100)}%</b> at <b>${e.horizon} weeks</b> · ` +
          `<b>${e.agreeing}/5</b> source families agree · confidence ${e.confidence} · ` +
          `<b>${e.people.toFixed(2)}M</b> people`;
      }
      li.append(line);

      const ul = el('ul', 'n-drivers');
      e.drivers.forEach(d => ul.append(el('li', null, d)));
      li.append(ul);

      // --- Recommendations: the actionable half of the alert ---------------
      if (e.advice) li.append(buildAdvice(e.advice, e.county));

      const nf = el('div', 'n-notify');
      nf.append(el('span', 'lab', 'Notify'));
      e.audiences.forEach(a => nf.append(el('span', 'aud', SIM.AUDIENCES[a].label)));
      li.append(nf);
    } else {
      li.append(el('div', 'n-line', 'Conditions improved. No new alerts sent.'));
    }

    li.addEventListener('click', () => {
      if (!e.live) setTime(e.t);        // live cards have no month to jump to
      const poly = KENYA_COUNTIES.features.find(f => f.properties.name === e.county);
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
  const FAMILY_LABELS = {
    weather: ['Rain', 'CHIRPS'],
    eo: ['Crop', 'MODIS'],
    market: ['Price', 'WFP'],
    official: ['Official', 'ReliefWeb'],
    crowd: ['Replies', 'SMS'],
  };

  function closeDetail() {
    selected = null;
    $('#detail').hidden = true;
    paintGlobe();
  }

  // Shapes the live FEWS NET entry like a model row so the detail panel can
  // render it without branching everywhere.
  function liveRow(unit, entry) {
    const phase = entry ? entry.phase : 1;
    const level = IPC_TO_LEVEL[phase] ?? 0;
    const proj = LIVE && LIVE.projection_ml1 && LIVE.projection_ml1[unit.name];
    const NAMES = ['', 'Minimal', 'Stressed', 'Crisis', 'Emergency', 'Famine'];
    return {
      level, p: null, confidence: 'official', agreeing: null,
      horizon: unit.props.aridity > 0.7 ? 8 : 10,
      spi: 0, ndvi: 0, price: 0, crowd: 0,
      annSev: phase >= 3 ? 2 : 0, ipcPhase: phase,
      asOf: entry ? entry.as_of : null,
      rainPct: 0,
      families: { weather: false, eo: false, market: false, official: !!entry, crowd: false },
      live: true,
      projection: proj ? proj.phase : null,
      drivers: [
        `FEWS NET: IPC Phase ${phase} ${NAMES[phase]}${entry ? ` (${entry.as_of})` : ''}`,
      ].concat(proj ? [`near-term projection: Phase ${proj.phase} ${NAMES[proj.phase]}`] : []),
    };
  }

  function renderDetail() {
    if (!selected) { $('#detail').hidden = true; return; }
    const unit = byName.get(selected.properties.name);
    // In live mode the panel must describe the real FEWS NET classification,
    // not the replay model sitting at whatever month the slider last held.
    const liveEntry = liveMode && LIVE && LIVE.current && LIVE.current[unit.name];
    const row = liveMode
      ? liveRow(unit, liveEntry)
      : unit.series[now];
    const L = SIM.LEVELS[row.level];
    const auds = SIM.audiencesFor(row.level);
    // Default to the farmer message. It is the one that shows the product is
    // about a person with a feature phone, not a dashboard.
    if (!smsAudience || !auds.includes(smsAudience)) {
      smsAudience = auds.includes('farmer') ? 'farmer' : (auds[0] || null);
    }

    const d = $('#detail');
    d.hidden = false;
    d.innerHTML = '';

    // --- header
    const head = el('div', 'd-head');
    const ht = el('div');
    ht.append(el('h3', null, unit.name));
    ht.append(el('div', 'sub',
      (liveMode ? `FEWS NET ${row.asOf || 'current'}` : SIM.dateAt(now).label) +
      ` · ${(unit.props.pop).toFixed(2)}M people`));
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
    if (row.live) {
      const NAMES = ['', 'Minimal', 'Stressed', 'Crisis', 'Emergency', 'Famine'];
      const big = el('span', 'big', `P${row.ipcPhase}`);
      big.style.color = L.color;
      const pwrap = el('div');
      pwrap.append(big);
      pwrap.append(el('div', 'unit', `IPC ${NAMES[row.ipcPhase]} — FEWS NET published classification`));
      pm.append(pwrap);
      if (row.projection) {
        const cwrap = el('div');
        cwrap.append(el('span', 'big', `P${row.projection}`));
        cwrap.append(el('div', 'unit', 'their near-term projection'));
        pm.append(cwrap);
      }
    } else {
      const big = el('span', 'big', `${Math.round(row.p * 100)}%`);
      big.style.color = L.color;
      const pwrap = el('div');
      pwrap.append(big);
      pwrap.append(el('div', 'unit', `probability of shortage at ${row.horizon} weeks`));
      const cwrap = el('div');
      cwrap.append(el('span', 'big', `${row.agreeing}/5`));
      cwrap.append(el('div', 'unit', `sources agree · ${row.confidence} confidence`));
      pm.append(pwrap, cwrap);
    }
    body.append(pm);

    // --- source agreement
    const s1 = el('div', 'd-sect');
    s1.hidden = !!row.live;
    s1.append(el('span', 'd-lab', 'Source families'));
    const fams = el('div', 'fams');
    const vals = {
      weather: `${row.spi.toFixed(1)}`,
      eo: `${row.ndvi.toFixed(1)}`,
      market: `${row.price > 0 ? '+' : ''}${Math.round(row.price)}%`,
      official: row.annSev ? `sev ${row.annSev}` : '—',
      crowd: `${Math.round(row.crowd * 100)}%`,
    };
    for (const [k, [short]] of Object.entries(FAMILY_LABELS)) {
      const f = el('div', 'fam' + (row.families[k] ? ' hit' : ''));
      f.append(el('span', 'fn', short), el('span', 'fv', vals[k]));
      f.title = `${FAMILY_LABELS[k][1]} — ${row.families[k] ? 'anomalous' : 'within normal range'}`;
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

    // --- Recommendations
    if (row.level >= 1) {
      const sr = el('div', 'd-sect');
      sr.append(el('span', 'd-lab', 'Recommended response'));
      sr.append(buildAdvice(ADVICE.build(unit.name, row.level), unit.name));
      body.append(sr);
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
        const b = el('button', a === smsAudience ? 'on' : '', SIM.AUDIENCES[a].label);
        b.addEventListener('click', () => { smsAudience = a; renderDetail(); });
        tabs.append(b);
      });
      s3.append(tabs);

      const text = SIM.composeSMS(unit.name, row, smsAudience);
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
  //  Live feed (FEWS NET current situation)
  // =========================================================================
  // Served by serve.py, which proxies fdw.fews.net (no CORS header of its own)
  // and caches the reduced result. Falls back to the committed snapshot.
  async function loadLive({ force = false } = {}) {
    const btn = $('#live-toggle');
    btn.classList.add('loading');
    try {
      const r = await fetch('/api/live' + (force ? '?refresh=1' : ''));
      if (!r.ok) throw new Error(r.status);
      LIVE = await r.json();
    } catch (err) {
      LIVE = null;                       // serve.py not running, or offline
    } finally {
      btn.classList.remove('loading');
      renderLiveBar();
      if (liveMode) paintGlobe();
    }
    return LIVE;
  }

  function renderLiveBar() {
    // The footer disclaimer must follow the mode. In live mode the numbers on
    // screen are real FEWS NET classifications, and calling them simulated
    // would be as wrong as the reverse.
    $('#disclaimer').textContent = liveMode
      ? 'Live FEWS NET IPC classifications \u00b7 recommendations are ours \u00b7 prototype'
      : 'Simulated risk model \u00b7 real FEWS NET official layer \u00b7 scripted to the 2020\u20132023 Horn of Africa drought';
    const bar = $('#live-bar');
    if (!liveMode) { bar.hidden = true; return; }
    bar.hidden = false;
    if (!LIVE || !LIVE.n_counties) {
      bar.className = 'warn';
      bar.innerHTML = '<b>Live feed unavailable.</b> Start the app with ' +
        '<code>python3 serve.py</code> to proxy FEWS NET, or stay in replay mode.';
      return;
    }
    const n3 = Object.values(LIVE.current).filter(v => v.phase >= 3).length;
    const stamp = LIVE.fetched_at
      ? new Date(LIVE.fetched_at).toLocaleString()
      : 'cached snapshot';
    bar.className = LIVE.stale ? 'warn' : '';
    bar.innerHTML =
      `<span class="dot"></span><b>FEWS NET live</b> · reporting period ` +
      `<b>${LIVE.reporting_period || '—'}</b> · <b>${n3}</b> of ` +
      `${LIVE.n_counties} counties at IPC Phase 3+ · fetched ${stamp}` +
      (LIVE.refreshing ? ' · <i>refreshing…</i>' : '') +
      (LIVE.stale ? ' · <b>STALE</b>' : '');
  }

  // In live mode the globe shows the current real classification rather than
  // the replayed model. IPC phase 1-5 maps onto our 0-3 ladder.
  const IPC_TO_LEVEL = { 1: 0, 2: 1, 3: 2, 4: 3, 5: 3 };
  function liveLevel(countyName) {
    const e = LIVE && LIVE.current && LIVE.current[countyName];
    return e ? (IPC_TO_LEVEL[e.phase] ?? 0) : 0;
  }

  $('#live-toggle').addEventListener('click', async () => {
    liveMode = !liveMode;
    $('#live-toggle').classList.toggle('on', liveMode);
    document.body.classList.toggle('live', liveMode);
    $('#timeline').classList.toggle('disabled', liveMode);
    if (liveMode) {
      pause();
      if (!LIVE) await loadLive();
      renderLiveBar();
      renderLiveFeed();
    } else {
      renderLiveBar();
      renderFeed({ rebuild: true });
    }
    paintGlobe();
    updateStats();
    updateLegendCounts();
    if (selected) renderDetail();
  });

  $('#live-refresh').addEventListener('click', async (ev) => {
    ev.stopPropagation();
    await loadLive({ force: true });
    if (liveMode) { renderLiveFeed(); paintGlobe(); updateStats(); updateLegendCounts(); }
  });

  // The feed in live mode lists every county currently at Phase 2+, worst
  // first, with the same recommendations attached.
  function renderLiveFeed() {
    feedEl.innerHTML = '';
    rendered = -1;
    if (!LIVE || !LIVE.current) { $('#feed-count').textContent = '0'; return; }
    const rows = Object.entries(LIVE.current)
      .map(([county, v]) => ({ county, ...v, level: IPC_TO_LEVEL[v.phase] ?? 0 }))
      .filter(r => r.level >= 1)
      .sort((a, b) => b.phase - a.phase || a.county.localeCompare(b.county));

    for (const r of rows) {
      const proj = LIVE.projection_ml1 && LIVE.projection_ml1[r.county];
      feedEl.append(buildNote({
        t: now, county: r.county, from: r.level, to: r.level,
        escalation: true, live: true,
        p: null, confidence: 'official', agreeing: null,
        horizon: null, ipcPhase: r.phase, asOf: r.as_of,
        projection: proj ? proj.phase : null,
        drivers: [`FEWS NET Current Situation, ${r.as_of}`],
        audiences: SIM.audiencesFor(r.level),
        people: (byName.get(r.county)?.props.pop || 0) * 0.3,
        advice: ADVICE.build(r.county, r.level),
      }, false));
    }
    $('#feed-count').textContent = String(rows.length);
    $('#feed-empty').hidden = rows.length > 0;
  }

  // =========================================================================
  //  Boot
  // =========================================================================
  async function boot() {
    let fews = { phases: {}, months: [] };
    let lhz = { zones: {} };
    try {
      [fews, lhz] = await Promise.all([
        fetch('data/fews-ipc-kenya.json').then(r => r.json()),
        fetch('data/kenya-livelihoods.json').then(r => r.json()),
      ]);
    } catch (err) {
      console.error('FEWS NET data failed to load; official source family will be empty.', err);
    }

    ADVICE.init(lhz);
    MODEL = SIM.build(KENYA_COUNTIES.features, fews);
    byName = new Map(MODEL.units.map(u => [u.name, u]));

    buildSpark();
    setTime(0);
    loadLive();                       // warm it, but never block the UI

    const qs = new URLSearchParams(location.search);
    const qCountry = qs.get('country');
    if (qCountry && COUNTRIES.some(c => c.name.toLowerCase() === qCountry.toLowerCase())) {
      const match = COUNTRIES.find(c => c.name.toLowerCase() === qCountry.toLowerCase());
      selectCountry(match.name);
      const qt = parseInt(qs.get('t'), 10);
      if (Number.isFinite(qt)) setTime(qt, { rebuild: true });
      const qCounty = qs.get('county');
      if (qCounty && byName.has(qCounty)) {
        selected = KENYA_COUNTIES.features.find(f => f.properties.name === qCounty);
        smsAudience = null;
        paintGlobe();
        renderDetail();
      }
    } else {
      searchInput.focus();
    }

    // ?live=1 opens straight into the FEWS NET current situation.
    if (qs.get('live') === '1') {
      await loadLive();
      $('#live-toggle').click();
    }
  }

  boot();
})();
