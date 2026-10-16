/* ============================================================================
   real.js — the engine app.js uses, fed only by real pipeline output.

   Input: RISK_DATA[iso3] (data/risk/<ISO3>.js, CONTRACT.md section 3) and
          GEO_DATA[iso3]  (data/geo/<ISO3>.js,  CONTRACT.md section 2).
   Nothing is computed here that changes a level: level, p, families, event
   and drivers all come from the model. This file only shapes them for app.js
   and writes the SMS text.

   REAL.forCountry(iso3) returns an engine object with:
     START_YEAR, N_MONTHS, LEVELS, AUDIENCES, FAMILIES, N_FAMILIES,
     dateAt(t), audiencesFor(level, row), composeSMS(name, row, audience),
     build(features) -> { units, events, national }, meta, isReal, isStub
   ============================================================================ */

const REAL = (() => {
  const MONTH_NAMES = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

  const LEVELS = [
    { n: 0, key: 'normal',    label: 'Normal',    color: '#0ca30c', glyph: '●' },
    { n: 1, key: 'watch',     label: 'Watch',     color: '#ffd43b', glyph: '▲' },
    { n: 2, key: 'warning',   label: 'Warning',   color: '#ec833a', glyph: '▲' },
    { n: 3, key: 'emergency', label: 'Emergency', color: '#d03b3b', glyph: '■' },
  ];

  // Same routing as the spec; herders are only messaged when the model says
  // the problem is grazing (event no_grass), farmers otherwise.
  const AUDIENCES = {
    farmer:    { label: 'Farmers',            minLevel: 2 },
    herder:    { label: 'Herders',            minLevel: 2 },
    coop:      { label: 'Cooperatives',       minLevel: 2 },
    extension: { label: 'Extension officers', minLevel: 1 },
    foodbank:  { label: 'Food banks',         minLevel: 1 },
    ngo:       { label: 'NGOs & funds',       minLevel: 1 },
    gov:       { label: 'Government',         minLevel: 2 },
  };

  const EVENTS = {
    none:         null,
    cant_plant:   "Can't plant",
    crop_failure: 'Crop failure',
    no_grass:     'No grass',
  };

  // Shown in the detail panel. Only rain, vegetation and soil count toward
  // the agreement rule; heat is supporting evidence.
  const fmt = v => (v == null || Number.isNaN(v) ? '—' : (+v).toFixed(1));
  const FAMILIES = [
    { key: 'rain',       short: 'Rain',  src: 'CHIRPS SPI-3',        val: r => fmt(r.signals.spi_3m) },
    { key: 'vegetation', short: 'Green', src: 'MODIS NDVI z (crop)', val: r => fmt(r.signals.ndvi_z_crop) },
    { key: 'soil',       short: 'Soil',  src: 'ERA5-Land topsoil z', val: r => fmt(r.signals.sm1_z) },
    { key: 'heat',       short: 'Heat',  src: 'ERA5-Land 2m temp z (supporting only)', val: r => fmt(r.signals.t2m_z) },
  ];
  const N_FAMILIES = 3;

  // Keep SMS bodies GSM-7: one curly quote would switch to UCS-2 (70 chars).
  const gsmSafe = s => String(s)
    .replace(/[‘’ʼ`´]/g, "'").replace(/[“”]/g, '"')
    .replace(/[–—]/g, '-').normalize('NFD').replace(/[̀-ͯ]/g, '');

  // GSM-7 septets: extension-table chars cost 2 (the "[link]" brackets do).
  const septets = t => [...t].reduce((k, ch) => k + ('^{}\\[]~|€'.includes(ch) ? 2 : 1), 0);

  // Driver text for a one-segment message: full text if it fits, else drop
  // the "(...)" gloss, else cut at a word boundary (never mid-phrase).
  function fitDriver(text, budget) {
    let d = gsmSafe(text).trim();
    if (septets(d) <= budget) return d;
    d = d.replace(/\s*\([^)]*\)?\s*$/, '').trim();
    if (septets(d) <= budget) return d;
    const words = d.split(' ');
    while (words.length && septets(words.join(' ')) > budget) words.pop();
    return words.join(' ');
  }

  function audiencesFor(lvl, row) {
    const grazing = row && row.event === 'no_grass';
    return Object.entries(AUDIENCES)
      .filter(([k, a]) => lvl >= a.minLevel)
      .filter(([k]) => (k === 'herder' ? grazing : k === 'farmer' ? !grazing : true))
      .map(([k]) => k);
  }

  // Farmers and herders: an action, never a probability.
  function composeSMS(unitName, row, audience) {
    const name = gsmSafe(unitName);
    const L = LEVELS[row.level].label.toUpperCase();
    const hasP = row.p != null && !Number.isNaN(row.p);   // missing p is null, never 0
    const pc = hasP ? `${Math.round(row.p * 100)}%` : 'n/a';
    const pp = hasP ? row.p.toFixed(2) : 'n/a';
    const agree = row.held
      ? 'level held, needs 3 calm months'
      : `${row.agreeing}/3 families agree`;
    const em = row.level >= 3;
    switch (audience) {
      case 'farmer':
        if (row.event === 'cant_plant')
          return `${L} ${name}: rains late and poor. Wait for 2 good rains before planting, use short-season seed. Reply 1 ok 2 poor 3 failed. STOP to quit`;
        return em
          ? `EMERGENCY ${name}: harvest failed. Keep your grain, do not sell animals cheap. Ask chief about relief. Reply 1 ok 2 poor 3 failed. STOP to quit`
          : `WARNING ${name}: crops drying, poor harvest likely. Keep 2 months of grain, do not sell cheap. Reply 1 ok 2 poor 3 failed. STOP to quit`;
      case 'herder':
        return em
          ? `EMERGENCY ${name}: no grass left. Sell weak animals now, keep breeding stock, move herds to water. Reply 1 ok 2 poor 3 bad. STOP to quit`
          : `WARNING ${name}: grazing drying fast. Sell weak animals early while prices hold, plan herd moves. Reply 1 ok 2 poor 3 bad. STOP to quit`;
      case 'coop':
        // cooperatives forward to farmers: action only, no percentage
        return `${L} ${name}: crops at risk, satellite and weather agree. Advise members to hold grain, buy inputs now. Share with all members. [link]`;
      case 'foodbank':
        return `${L} ${name}: shortage risk ${pc} in ${row.horizon} wks. Raise cereal stock at the nearest branch now, before prices peak. [link]`;
      case 'ngo': {
        // NGOs see the FEWS NET-informed chance of IPC3+ Crisis (p_crisis), not the vegetation p
        const pcr = row.p_crisis != null && !Number.isNaN(row.p_crisis) ? `${Math.round(row.p_crisis * 100)}%` : null;
        const head = pcr ? `${L} ${name}: chance of Crisis within 3 months ${pcr}. ` : `${L} ${name}: `;
        const tail = `${agree}, conf ${row.confidence}. [link]`;
        const drv = fitDriver(row.drivers[0] || 'dry conditions', 160 - septets(head + tail) - 2);
        return head + (drv ? `${drv}. ` : '') + tail;
      }
      case 'gov':
        return `${L} ${name}: P(shortage,${row.horizon}wk)=${pp}, conf ${row.confidence}. Consider releasing reserves. Src: CHIRPS, MODIS, ERA5. [link]`;
      case 'extension':
        return `${L} ${name}: ${EVENTS[row.event] || 'drought'}. Prioritise visits to worst-hit wards, push drought-tolerant seed. ${row.held ? 'Level held.' : `${row.agreeing}/3 sources agree.`} [link]`;
      default:
        return '';
    }
  }

  function forCountry(iso3) {
    const R = (window.RISK_DATA || {})[iso3];
    if (!R) return null;
    const meta = R.meta;
    const START_YEAR = meta.start_year;
    const N_MONTHS = meta.n_months;
    const dateAt = t => ({
      year: START_YEAR + Math.floor(t / 12),
      month: t % 12,
      label: `${MONTH_NAMES[t % 12]} ${START_YEAR + Math.floor(t / 12)}`,
    });
    const riskById = new Map(R.units.map(u => [u.id, u]));
    const riskByName = new Map(R.units.map(u => [u.name, u]));

    // Missing data is missing: a unit with no model output stays grey-green
    // at level 0 with nulls rather than being invented.
    const emptyRow = t => ({
      t, level: 0, p: null, p_crisis: null, confidence: 'low', agreeing: 0,
      families: { rain: false, vegetation: false, soil: false, heat: false },
      event: 'none', horizon: 0, drivers: [], signals: {}, missing: true,
    });

    function build(features) {
      const units = features.map(f => {
        const r = riskById.get(f.properties.id) || riskByName.get(f.properties.name);
        const series = [];
        for (let t = 0; t < N_MONTHS; t++) {
          const row = r && r.series[t] ? { ...r.series[t] } : emptyRow(t);
          row.signals = row.signals || {};
          row.drivers = row.drivers || [];
          row.families = row.families || {};
          series.push(row);
        }
        return { id: f.properties.id, name: f.properties.name, props: f.properties, feature: f, series };
      });

      const events = [];
      for (const u of units) {
        for (let t = 1; t < N_MONTHS; t++) {
          const prev = u.series[t - 1].level, cur = u.series[t].level;
          if (cur === prev) continue;
          const row = u.series[t];
          events.push({
            t, county: u.name, id: u.id, from: prev, to: cur,
            escalation: cur > prev,
            p: row.p, confidence: row.confidence, agreeing: row.agreeing,
            horizon: row.horizon, drivers: row.drivers, event: row.event,
            audiences: cur > prev ? audiencesFor(cur, row) : [],
            pop: u.props.pop == null ? null : u.props.pop,   // real population, millions
          });
        }
      }
      events.sort((a, b) => a.t - b.t || b.to - a.to || a.county.localeCompare(b.county));

      const national = [];
      for (let t = 0; t < N_MONTHS; t++) {
        national.push(units.filter(u => u.series[t].level >= 2).length / Math.max(1, units.length));
      }
      return { units, events, national };
    }

    // ---- Forecast (CONTRACT.md sections 4 and 4b) --------------------------
    // A row MAY carry forecast["1".."8"] = { p, p_crisis, fews_phase,
    // fews_scenario, fews_published, target_label, source }. Leads 1..3 fall
    // back to existing real fields when the key is missing (p_crisis is
    // P(IPC3+ within 1-3 months) so it is the same number for leads 1..3; p
    // stands for lead 1 only). Leads without any field are "pending": every
    // value null. Nothing is extrapolated or invented.
    const num = v => (v == null || Number.isNaN(+v) ? null : +v);
    const MAX_LEAD = 8;
    let hasForecast = false, maxModelLead = 0, hasFews = false;
    const fewsLeads = new Set();
    for (const u of R.units) for (const r of (u.series || [])) {
      if (!r || !r.forecast) continue;
      for (const k of Object.keys(r.forecast)) {
        const f = r.forecast[k], L = +k;
        if (!f || !(L >= 1 && L <= MAX_LEAD)) continue;
        if (num(f.p_crisis) != null || num(f.p) != null) { hasForecast = true; if (L > maxModelLead) maxModelLead = L; }
        if (num(f.fews_phase) != null) { hasFews = true; fewsLeads.add(L); }
      }
    }
    const pcMeta = (meta.metrics && meta.metrics.p_crisis) || {};
    const WATCH_P_CRISIS = num(pcMeta.watch_threshold) != null ? num(pcMeta.watch_threshold) : 0.57;
    function forecastAt(row, lead) {
      lead = Math.max(1, Math.min(MAX_LEAD, lead | 0));
      const target_label = dateAt(row.t + lead).label;
      const f = row.forecast && row.forecast[String(lead)];
      let p = null, p_crisis = null, derived = true, pending = false;
      let fews_phase = null, fews_scenario = null, fews_published = null, source = null;
      if (f) {
        p = num(f.p); p_crisis = num(f.p_crisis); derived = false;
        fews_phase = num(f.fews_phase);
        if (fews_phase != null) fews_phase = Math.max(1, Math.min(5, Math.round(fews_phase)));
        fews_scenario = f.fews_scenario || null;
        fews_published = f.fews_published || null;
        source = f.source || null;
      } else if (!row.missing && lead <= 3) {
        p_crisis = num(row.p_crisis);
        p = lead === 1 ? num(row.p) : null;
      } else {
        pending = true;
      }
      const chance = p_crisis != null ? p_crisis : p;
      const kind = p_crisis != null ? 'crisis' : p != null ? 'event' : null;
      return { lead, p, p_crisis, chance, kind, derived, pending,
               fews_phase, fews_scenario, fews_published, source,
               target_label: (f && f.target_label) || target_label };
    }

    // Confidence per lead. If the export carries tested skill per lead
    // (meta.metrics.forecast_skill | skill_by_lead | lead_skill, keyed "1".."8"
    // with a `confidence`/`label` string or a roc_auc number) use it;
    // otherwise the back-test defaults for +1..+3 (Medium-High / Medium /
    // Low-Medium); beyond the tested leads: "no model forecast - FEWS NET only".
    const DEFAULT_CONF = { 1: 'Medium-High', 2: 'Medium', 3: 'Low-Medium' };
    const skillTab = (meta.metrics && (meta.metrics.forecast_skill || meta.metrics.skill_by_lead || meta.metrics.lead_skill)) || null;
    function forecastConfidence(lead) {
      lead = Math.max(1, Math.min(MAX_LEAD, lead | 0));
      const s = skillTab && (skillTab[String(lead)] || skillTab[lead]);
      if (s && typeof s === 'object') {
        const lab = s.confidence || s.label;
        if (typeof lab === 'string' && lab.trim()) return { label: lab.trim(), source: 'tested skill per lead', tested: true };
        const auc = num(s.roc_auc);
        if (auc != null) {
          const label = auc >= 0.75 ? 'High' : auc >= 0.65 ? 'Medium-High' : auc >= 0.6 ? 'Medium' : auc >= 0.55 ? 'Low-Medium' : 'Low';
          return { label, source: `tested skill per lead (ROC AUC ${auc.toFixed(2)})`, tested: true };
        }
      } else if (typeof s === 'string' && s.trim()) {
        return { label: s.trim(), source: 'tested skill per lead', tested: true };
      }
      if (lead <= 3) return { label: DEFAULT_CONF[lead], source: 'based on back-tests', tested: false };
      if (lead <= maxModelLead) return { label: 'Untested', source: 'model output exists but no skill test for this lead', tested: false };
      return { label: 'no model forecast — FEWS NET only', source: 'beyond tested leads', tested: false, none: true };
    }

    const isStub = String(meta.model_version).toUpperCase() === 'STUB';
    return {
      forecastConfidence,
      REPLAY_END_T: 71,            // t > 71 = live months added after the replay window
      isReal: true, isStub, meta,
      START_YEAR, N_MONTHS, LEVELS, AUDIENCES, EVENTS, FAMILIES, N_FAMILIES,
      dateAt, build, composeSMS, audiencesFor,
      forecastAt, hasForecast, WATCH_P_CRISIS, MAX_LEAD,
      maxModelLead, hasFews, fewsLeads: [...fewsLeads].sort((a, b) => a - b),
      pCrisisAvailable: pcMeta.available !== false,   // false = IPC model not run for this country
      liveT: Number.isFinite(+meta.live_t) && meta.live_t != null ? +meta.live_t : null,
      declaration: meta.declaration || null,
      // app.js never shows a STUB file; isStub is kept for callers that check.
      disclaimer: 'Real satellite + weather data (CHIRPS, MODIS, ERA5). Risk levels from our model.',
    };
  }

  return { forCountry, LEVELS, AUDIENCES, EVENTS, composeSMS, audiencesFor };
})();
