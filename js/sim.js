/* ============================================================================
   sim.js — the risk engine for the prototype.

   SIMULATED DATA. Every number below is generated, not measured. It is scripted
   to follow the real 2020-2023 Horn of Africa drought: five consecutive failed
   rainy seasons, Kenya's national drought disaster declaration of 8 Sept 2021,
   the 2022 peak, and the El Nino recovery/flooding of late 2023.

   In the real system this file is replaced by:
     - Earth Engine CHIRPS SPI + MODIS NDVI anomalies  (Role A)
     - WFP market prices from HDX                      (Role A)
     - ReliefWeb LLM extraction -> announcement table   (Role B)
     - the fusion model + hysteresis                    (Role B)

   The interface it exposes is the one the real engine must match:
   a risk_assessment per (unit_id, month).
   ============================================================================ */

const SIM = (() => {

  // ---- Timeline ------------------------------------------------------------
  const START_YEAR = 2019;
  const N_MONTHS = 72;                       // Jan 2019 -> Dec 2024, 6 years
  const MONTH_NAMES = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

  const dateAt = t => ({
    year: START_YEAR + Math.floor(t / 12),
    month: t % 12,
    label: `${MONTH_NAMES[t % 12]} ${START_YEAR + Math.floor(t / 12)}`,
  });

  // ---- The rainfall script -------------------------------------------------
  // Kenya has two rainy seasons: MAM "long rains" and OND "short rains".
  // Values are fraction of the long-term seasonal mean. This sequence is the
  // spine of the whole demo — it is what makes the map turn red on cue.
  const SEASONS = {
    '2019-MAM': 0.78,   // delayed, below normal
    '2019-OND': 1.65,   // exceptionally wet, widespread flooding
    '2020-MAM': 1.18,   // good season
    '2020-OND': 0.68,   // FAILURE 1 — the drought begins
    '2021-MAM': 0.62,   // FAILURE 2
    '2021-OND': 0.52,   // FAILURE 3 — national disaster declared 8 Sept 2021
    '2022-MAM': 0.45,   // FAILURE 4 — driest on record for much of the ASALs
    '2022-OND': 0.50,   // FAILURE 5 — peak crisis
    '2023-MAM': 0.88,   // below normal but recovering
    '2023-OND': 1.72,   // El Nino, very wet, flooding
    '2024-MAM': 1.38,   // wet, April 2024 floods
    '2024-OND': 1.02,   // near normal
  };

  // Which season governs a given month. Jan-Feb still live off the previous
  // short rains; Jun-Sep are the lean months that reflect how MAM went.
  function seasonRatio(t) {
    const { year, month } = dateAt(t);
    if (month <= 1) return SEASONS[`${year - 1}-OND`] ?? 1.0;   // Jan, Feb
    if (month <= 8) return SEASONS[`${year}-MAM`] ?? 1.0;       // Mar - Sep
    return SEASONS[`${year}-OND`] ?? 1.0;                        // Oct - Dec
  }

  // ---- Official source: real FEWS NET IPC classifications -----------------
  // This replaces the hand-written announcement table. Every value below comes
  // from the FEWS NET Data Warehouse (fdw.fews.net), "Current Situation"
  // scenario, aggregated to county level — see fetch_fews.py.
  //
  // Per the spec's risk table, the official family alone can never push a unit
  // above level 1. It only ever confirms what satellite and price data show.
  const IPC_LABEL = ['', 'Minimal', 'Stressed', 'Crisis', 'Emergency', 'Famine'];
  // IPC phase -> announcement severity 0-3. Phase 3 "Crisis" is the
  // humanitarian action threshold, so that is where severity becomes decisive.
  const IPC_TO_SEV = { 1: 0, 2: 1, 3: 2, 4: 3, 5: 3 };

  let FEWS = { phases: {}, months: [] };    // injected by build()

  function monthKey(t) {
    const d = dateAt(t);
    return `${d.year}-${String(d.month + 1).padStart(2, '0')}`;
  }

  // FEWS NET reports roughly quarterly, so a given month inherits the most
  // recent classification published on or before it. We do not interpolate —
  // an official classification stands until it is superseded.
  function announcementAt(t, countyName) {
    const series = FEWS.phases[countyName];
    if (!series) return { sev: 0, text: null, phase: null, asOf: null };
    const key = monthKey(t);
    let best = null;
    for (const m of Object.keys(series)) {
      if (m <= key && (!best || m > best)) best = m;
    }
    if (!best) return { sev: 0, text: null, phase: null, asOf: null };
    const phase = series[best];
    const [y, mo] = best.split('-');
    return {
      sev: IPC_TO_SEV[phase] ?? 0,
      phase,
      asOf: `${MONTH_NAMES[+mo - 1]} ${y}`,
      text: `FEWS NET classified this county IPC Phase ${phase} ${IPC_LABEL[phase]} (${MONTH_NAMES[+mo - 1]} ${y})`,
    };
  }

  // ---- Deterministic noise -------------------------------------------------
  // Seeded so the demo replays identically every single time. Nothing in this
  // file may call Math.random().
  function hash(str) {
    let h = 2166136261;
    for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }
  function noise(name, t, salt) {
    const h = hash(`${name}|${t}|${salt}`);
    return ((h % 10000) / 10000 - 0.5) * 2;      // -1 .. 1
  }

  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const sigmoid = z => 1 / (1 + Math.exp(-z));

  // ---- Levels --------------------------------------------------------------
  const LEVELS = [
    { n: 0, key: 'normal',    label: 'Normal',    color: '#0ca30c', glyph: '●' },
    { n: 1, key: 'watch',     label: 'Watch',     color: '#ffd43b', glyph: '▲' },
    { n: 2, key: 'warning',   label: 'Warning',   color: '#ec833a', glyph: '▲' },
    { n: 3, key: 'emergency', label: 'Emergency', color: '#d03b3b', glyph: '■' },
  ];

  // Who gets told, per the spec's audience table. Declaration order is the
  // display order: the people closest to the harvest come first.
  // Level 1 reaches institutions only — farmers are not alerted on a weak
  // signal, because alert fatigue is what kills these systems.
  const AUDIENCES = {
    farmer:    { label: 'Farmers',            minLevel: 2 },
    coop:      { label: 'Cooperatives',       minLevel: 2 },
    extension: { label: 'Extension officers', minLevel: 1 },
    foodbank:  { label: 'Food banks',         minLevel: 1 },
    ngo:       { label: 'NGOs & funds',       minLevel: 1 },
    gov:       { label: 'Government',         minLevel: 2 },
  };
  const audiencesFor = lvl =>
    Object.entries(AUDIENCES).filter(([, a]) => lvl >= a.minLevel).map(([k]) => k);

  // ---- Per-county time series ---------------------------------------------
  function buildSeries(props) {
    const { name, aridity, crop } = props;
    const out = [];

    let water = 0;                 // running soil-water balance, 0 = normal
    let rawRun = { level: 0, n: 0 };
    let level = 0;                 // the hysteresis-smoothed level

    for (let t = 0; t < N_MONTHS; t++) {
      const ratio = seasonRatio(t) + noise(name, t, 'rain') * 0.09;

      // Soil water balance. Arid counties have almost no buffer, so a bad
      // season bites immediately and a good one flushes through just as fast.
      const decay = 0.88 - 0.10 * aridity;
      const uptake = 0.30 + 0.22 * aridity;
      water = water * decay + (ratio - 1) * uptake;

      // --- Signals, one per source family -----------------------------------
      const spi = clamp((ratio - 1) * 2.4 + noise(name, t, 'spi') * 0.22, -3, 3);

      // Vegetation lags rainfall by about a month and is what the satellite sees.
      const ndvi = clamp(water * (1.9 + 0.9 * aridity) + noise(name, t, 'ndvi') * 0.25, -3, 3);

      // Prices respond to the national harvest outlook ~3 months later, with a
      // transport premium in remote counties.
      const natRatio = t >= 3 ? seasonRatio(t - 3) : 1;
      const price = clamp(
        Math.max(0, 1 - natRatio) * 72 * (0.70 + 0.62 * aridity) + noise(name, t, 'px') * 3.5,
        -8, 95
      );

      const ann = announcementAt(t, name);

      // Farmer SMS replies: share reporting a poor or failed harvest.
      const crowd = clamp(0.10 + Math.max(0, -ndvi) * 0.24 + noise(name, t, 'cr') * 0.05, 0, 0.92);

      // --- Fusion ------------------------------------------------------------
      const z = 0.46 * Math.max(0, -spi)
              + 0.42 * Math.max(0, -ndvi)
              + 0.013 * Math.max(0, price)
              + 0.30 * ann.sev
              + 0.55 * Math.max(0, crowd - 0.25);
      const vulnerability = 0.55 + 0.72 * aridity;
      const p = clamp(sigmoid(z * vulnerability * 1.25 - 2.05), 0.01, 0.97);

      // --- Source agreement --------------------------------------------------
      // Independent families, not independent signals. Two satellite products
      // agreeing is still one family.
      const families = {
        weather: spi < -0.70,
        eo:      ndvi < -0.70,
        market:  price > 14,
        official: ann.sev >= 1,
        crowd:   crowd > 0.40,
      };
      const agreeing = Object.values(families).filter(Boolean).length;

      // --- Level, with the spec's escalation gates ---------------------------
      let raw = p >= 0.70 ? 3 : p >= 0.46 ? 2 : p >= 0.26 ? 1 : 0;
      // Level 2+ needs two or more independent families to agree.
      if (agreeing < 2) raw = Math.min(raw, 1);
      // Level 3 needs an official declaration or a genuine price spike.
      if (!(ann.sev >= 2 || price > 28)) raw = Math.min(raw, 2);

      // Hysteresis: 2 consecutive runs to escalate, 3 to stand down. This is
      // what stops a single cloudy month from flipping a county red and back.
      rawRun = raw === rawRun.level ? { level: raw, n: rawRun.n + 1 } : { level: raw, n: 1 };
      const needed = raw > level ? 2 : 3;
      if (raw !== level && rawRun.n >= needed) level = raw;

      const confidence = agreeing >= 4 ? 'high' : agreeing >= 2 ? 'medium' : 'low';

      out.push({
        t, level, p, confidence, agreeing, families,
        spi, ndvi, price, crowd,
        annSev: ann.sev, annText: ann.text,
        ipcPhase: ann.phase, ipcAsOf: ann.asOf,
        rainPct: Math.round((ratio - 1) * 100),
        horizon: aridity > 0.7 ? 8 : 10,
        drivers: describeDrivers({ spi, ndvi, price, crowd, ann, ratio }),
      });
    }
    return out;
  }

  // Top three drivers, ranked by how much each pushed the score up, rendered as
  // the plain sentences that go into the SMS and the sidebar.
  function describeDrivers({ spi, ndvi, price, crowd, ann, ratio }) {
    const cands = [
      { w: 0.46 * Math.max(0, -spi),
        text: `rainfall ${Math.round((ratio - 1) * 100)}% vs normal` },
      // Kept free of non-GSM-7 characters (no sigma, no curly quotes): these
      // strings go into SMS bodies, and one such character switches the whole
      // message to UCS-2 and halves the segment to 70 chars.
      { w: 0.42 * Math.max(0, -ndvi),
        text: `crop greenness ${ndvi.toFixed(1)} below normal` },
      { w: 0.013 * Math.max(0, price),
        text: `maize price +${Math.round(price)}%` },
      { w: 0.30 * ann.sev,
        text: ann.phase
          ? `FEWS NET: IPC Phase ${ann.phase} ${IPC_LABEL[ann.phase]} (${ann.asOf})`
          : 'official drought classification' },
      { w: 0.55 * Math.max(0, crowd - 0.25),
        text: `${Math.round(crowd * 100)}% of farmer replies report a poor or failed harvest` },
    ];
    return cands.filter(c => c.w > 0.04).sort((a, b) => b.w - a.w).slice(0, 3).map(c => c.text);
  }

  // ---- SMS composition -----------------------------------------------------
  // One GSM-7 segment is 160 chars. The UI shows the count because fitting one
  // segment is a real constraint, not a detail — it is half the cost model.
  function composeSMS(countyName, row, audience) {
    const L = LEVELS[row.level].label.toUpperCase();
    const pc = Math.round(row.p * 100);
    const price = Math.round(row.price);
    const rain = row.rainPct;

    switch (audience) {
      case 'farmer': {
        // Farmers get an action, never a probability — a public forecast moves
        // the market and can cause the shortage it predicts.
        // The action is matched to the county's actual livelihood zone: you do
        // not tell a Turkana herder to plant, or a Kisii farmer to destock.
        const act = typeof ADVICE !== 'undefined'
          ? ADVICE.shortAction(countyName, row.level)
          : 'Keep 2 months of grain';
        return row.level >= 3
          ? `EMERGENCY ${countyName}: prices +${price}%. ${act}. Reply 1 ok 2 poor 3 failed. STOP to quit`
          : `WARNING ${countyName}: rain ${rain}% vs normal, poor season likely. ${act}. Reply 1 ok 2 poor 3 failed. STOP to quit`;
      }
      case 'coop':
        return `${L} ${countyName}: shortage risk ${pc}% in ${row.horizon} wks. Advise members to hold grain and bulk-buy inputs now. Share with all members. Details: [link]`;
      case 'foodbank':
        return `${L} ${countyName}: shortage risk ${pc}% in ${row.horizon} wks (rain, prices). Raise cereal stock at the nearest branch now, before the price peak. [link]`;
      case 'ngo':
        return `${L} ${countyName}: P(shortage, ${row.horizon} wks)=${row.p.toFixed(2)}, driver ${row.drivers[0] || 'multiple'}. ${row.agreeing} of 5 sources agree, confidence ${row.confidence}. Dashboard: [link]`;
      case 'gov':
        return `${L} ${countyName}: P(shortage, ${row.horizon} wks)=${row.p.toFixed(2)}, confidence ${row.confidence}. Consider releasing strategic reserves. Sources: CHIRPS, MODIS, WFP. [link]`;
      case 'extension':
        return `${L} ${countyName}: prioritise visits in the worst-hit wards. Push drought-tolerant seed and early-harvest advice. ${row.agreeing} of 5 sources agree. [link]`;
      default:
        return '';
    }
  }

  // ---- Build everything up front ------------------------------------------
  // fewsData is data/fews-ipc-kenya.json. It drives the official source
  // family, so the engine must be built with it before any series is read.
  function build(features, fewsData) {
    FEWS = fewsData || { phases: {}, months: [] };
    const units = features.map(f => ({
      name: f.properties.name,
      props: f.properties,
      feature: f,
      series: buildSeries(f.properties),
    }));

    // Every level change, in time order. The sidebar is a slice of this.
    const events = [];
    for (const u of units) {
      for (let t = 1; t < N_MONTHS; t++) {
        const prev = u.series[t - 1].level;
        const now = u.series[t].level;
        if (now === prev) continue;
        const row = u.series[t];
        events.push({
          t, county: u.name, from: prev, to: now,
          escalation: now > prev,
          p: row.p,
          confidence: row.confidence,
          agreeing: row.agreeing,
          horizon: row.horizon,
          drivers: row.drivers,
          audiences: now > prev ? audiencesFor(now) : [],
          people: Math.round(u.props.pop * (0.25 + 0.20 * now) * 1000) / 1000,
          ipcPhase: row.ipcPhase,
          // The actionable half of the alert: what is at risk here and who
          // can do something about it. See js/advice.js.
          advice: typeof ADVICE !== 'undefined' && now > prev
            ? ADVICE.build(u.name, now) : null,
        });
      }
    }
    events.sort((a, b) => a.t - b.t || b.to - a.to || a.county.localeCompare(b.county));

    // National share of counties at Warning or above, per month — the little
    // area chart behind the timeline.
    const national = [];
    for (let t = 0; t < N_MONTHS; t++) {
      const warn = units.filter(u => u.series[t].level >= 2).length;
      national.push(warn / units.length);
    }

    return { units, events, national };
  }

  return {
    N_MONTHS, START_YEAR, LEVELS, AUDIENCES,
    dateAt, build, composeSMS, audiencesFor,
  };
})();
