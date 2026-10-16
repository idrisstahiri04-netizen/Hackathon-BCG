/* ============================================================================
   engine.js — the timeline, driven entirely by FEWS NET.

   This file replaces the old sim.js. NOTHING HERE IS SIMULATED. Every phase on
   screen is a published FEWS NET IPC classification from the FEWS NET Data
   Warehouse (fdw.fews.net), "Current Situation" scenario.

   What is FEWS NET's:
     - the IPC phase for every unit, every period            (observed)
     - the near-term projection shown alongside it           (their forecast)
     - the livelihood zones that drive the recommendations
     - the sub-county geography

   What is ours:
     - mapping their 5 IPC phases onto a 4-level alert ladder
     - deciding who gets told at each level
     - the SMS wording
     - the recommended actions

   Each timeline step is one real FEWS NET publication, roughly quarterly. We
   do not interpolate between them: a unit holds its last published
   classification until the next release, which is how these are read
   operationally.
   ============================================================================ */

const ENGINE = (() => {

  const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

  // IPC phase -> our alert level. Phase 3 "Crisis" is the humanitarian action
  // threshold, so that is where we raise Warning.
  const PHASE_TO_LEVEL = { 1: 0, 2: 1, 3: 2, 4: 3, 5: 3 };
  const PHASE_NAME = ['', 'Minimal', 'Stressed', 'Crisis', 'Emergency', 'Famine'];

  const LEVELS = [
    { n: 0, key: 'normal',    label: 'Normal',    color: '#0ca30c', glyph: '●', ipc: 'IPC 1 Minimal' },
    { n: 1, key: 'watch',     label: 'Watch',     color: '#ffd43b', glyph: '▲', ipc: 'IPC 2 Stressed' },
    { n: 2, key: 'warning',   label: 'Warning',   color: '#ec833a', glyph: '▲', ipc: 'IPC 3 Crisis' },
    { n: 3, key: 'emergency', label: 'Emergency', color: '#d03b3b', glyph: '■', ipc: 'IPC 4+ Emergency' },
  ];

  // Level 1 reaches institutions only. Farmers are not messaged on a weak
  // signal — alert fatigue is what kills these systems.
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

  let PERIODS = [];        // the real FEWS NET release months
  let AXIS = [];           // every calendar month those releases span
  let STEP_RELEASE = [];   // axis step -> index of the release in force

  // The slider runs on a monthly axis so it moves smoothly, but the data is
  // never interpolated: each month shows the last classification FEWS NET
  // actually published on or before it, which is how these are read
  // operationally. 18 releases, ~69 slider steps.
  function buildAxis() {
    AXIS = []; STEP_RELEASE = [];
    if (!PERIODS.length) return;
    const [y0, m0] = PERIODS[0].split('-').map(Number);
    const [y1, m1] = PERIODS[PERIODS.length - 1].split('-').map(Number);
    const total = (y1 - y0) * 12 + (m1 - m0);
    let rel = 0;
    for (let i = 0; i <= total; i++) {
      const y = y0 + Math.floor((m0 - 1 + i) / 12);
      const m = ((m0 - 1 + i) % 12) + 1;
      const key = `${y}-${String(m).padStart(2, '0')}`;
      while (rel + 1 < PERIODS.length && PERIODS[rel + 1] <= key) rel++;
      AXIS.push(key);
      STEP_RELEASE.push(rel);
    }
  }

  const N_STEPS = () => AXIS.length;
  const releaseAt = step =>
    STEP_RELEASE[Math.max(0, Math.min(STEP_RELEASE.length - 1, step))] || 0;
  // The first slider step on which a given release becomes current.
  const stepOfRelease = r => Math.max(0, STEP_RELEASE.indexOf(r));

  function dateAt(step) {
    const key = AXIS[Math.max(0, Math.min(AXIS.length - 1, step))];
    if (!key) return { label: '—', key: null, isRelease: false };
    const [y, m] = key.split('-');
    const rel = releaseAt(step);
    return {
      label: `${MONTHS[+m - 1]} ${y}`,
      key, year: +y, month: +m - 1,
      release: PERIODS[rel],
      isRelease: PERIODS[rel] === key,
      releaseLabel: (() => {
        const [ry, rm] = PERIODS[rel].split('-');
        return `${MONTHS[+rm - 1]} ${ry}`;
      })(),
    };
  }

  // ---- Build ---------------------------------------------------------------
  // timeline: data/fews-timeline.json
  // resolution: 'county' | 'subcounty'
  // features: the matching GeoJSON features, keyed by properties.name
  function build(features, timeline, resolution) {
    PERIODS = timeline.periods;
    buildAxis();
    const src = timeline[resolution] || {};

    const units = features.map(f => {
      const name = f.properties.name;
      const rec = src[name] || {};
      const phases = rec.phases || {};
      const proj = rec.proj || {};

      // One row per release, holding the last published classification.
      const byRelease = [];
      let last = null, lastAsOf = null;
      for (let r = 0; r < PERIODS.length; r++) {
        const key = PERIODS[r];
        const fresh = phases[key] != null;
        if (fresh) { last = phases[key]; lastAsOf = key; }
        byRelease.push({
          release: r,
          period: key,
          phase: last,
          level: last != null ? (PHASE_TO_LEVEL[last] ?? 0) : null,
          asOf: lastAsOf,
          fresh,
          projection: proj[key] ?? null,
          hasData: last != null,
        });
      }
      // Then projected onto the monthly axis. Nothing new is invented here —
      // every month simply points at the release that was current for it.
      const series = AXIS.map((month, step) => {
        const row = byRelease[releaseAt(step)];
        return { ...row, t: step, month, carried: month !== row.period };
      });
      return {
        name,
        props: f.properties,
        county: f.properties.county || name,
        zones: rec.zones || f.properties.zones || [],
        feature: f,
        series,
        covered: Object.keys(phases).length > 0,
      };
    });

    const byName = new Map(units.map(u => [u.name, u]));

    // Real transitions only — a unit genuinely reclassified by FEWS NET.
    // Compared release-to-release, then placed on the month the release landed.
    const events = [];
    for (const u of units) {
      for (let r = 1; r < PERIODS.length; r++) {
        const a = u.series[stepOfRelease(r - 1)], b = u.series[stepOfRelease(r)];
        if (a.level == null || b.level == null || a.level === b.level) continue;
        if (!b.fresh) continue;                // not a new publication
        const t = stepOfRelease(r);
        events.push({
          t, unit: u.name, county: u.county,
          from: a.level, to: b.level,
          fromPhase: a.phase, toPhase: b.phase,
          escalation: b.level > a.level,
          period: b.period,
          projection: b.projection,
          zones: u.zones,
          audiences: b.level > a.level ? audiencesFor(b.level) : [],
          drivers: buildDrivers(a, b),
        });
      }
    }
    events.sort((x, y) => x.t - y.t || y.to - x.to || x.unit.localeCompare(y.unit));

    // Share of units at Warning or above, per slider step — the timeline strip.
    const national = AXIS.map((_, t) => {
      const live = units.filter(u => u.series[t].level != null);
      if (!live.length) return 0;
      return live.filter(u => u.series[t].level >= 2).length / live.length;
    });

    return { units, byName, events, national, periods: PERIODS, resolution };
  }

  // Drivers are statements of fact from FEWS NET, not model attributions.
  function buildDrivers(prev, now) {
    const out = [`FEWS NET reclassified: IPC Phase ${prev.phase} ${PHASE_NAME[prev.phase]} ` +
                 `→ Phase ${now.phase} ${PHASE_NAME[now.phase]}`];
    if (now.projection != null) {
      out.push(now.projection > now.phase
        ? `FEWS NET project further deterioration to Phase ${now.projection} ${PHASE_NAME[now.projection]}`
        : now.projection < now.phase
        ? `FEWS NET project improvement to Phase ${now.projection} ${PHASE_NAME[now.projection]}`
        : `FEWS NET project Phase ${now.projection} ${PHASE_NAME[now.projection]} to hold`);
    }
    out.push(`Published ${dateAt(now.t).label}, Current Situation scenario`);
    return out;
  }

  // ---- SMS -----------------------------------------------------------------
  // One GSM-7 segment is 160 characters. Non-GSM-7 characters halve that to 70,
  // so these templates avoid them entirely.
  function composeSMS(unitName, row, audience, advice) {
    const L = LEVELS[row.level];
    const tag = L.label.toUpperCase();
    const phase = `IPC${row.phase}`;
    const act = advice ? advice : 'Follow county guidance';

    switch (audience) {
      case 'farmer':
        // An action, never a probability. A public forecast moves the market
        // and can cause the shortage it predicts.
        return row.level >= 3
          ? `EMERGENCY ${unitName}: food crisis confirmed. ${act}. Reply 1 ok 2 poor 3 failed. STOP to quit`
          : `WARNING ${unitName}: food shortage likely this season. ${act}. Reply 1 ok 2 poor 3 failed. STOP to quit`;
      case 'coop':
        return `${tag} ${unitName}: FEWS NET ${phase}. Advise members now. ${act}. Share with all members. [link]`;
      case 'foodbank':
        return `${tag} ${unitName}: FEWS NET ${phase} ${PHASE_NAME[row.phase]}${row.projection ? `, projected IPC${row.projection}` : ''}. Raise cereal stock before the price peak. [link]`;
      case 'ngo':
        return `${tag} ${unitName}: FEWS NET ${phase} ${PHASE_NAME[row.phase]} as of ${row.asOf}${row.projection ? `, near-term projection IPC${row.projection}` : ''}. Dashboard: [link]`;
      case 'gov':
        return `${tag} ${unitName}: FEWS NET ${phase} ${PHASE_NAME[row.phase]}. Consider reserve release and County Steering Group review. [link]`;
      case 'extension':
        return `${tag} ${unitName}: FEWS NET ${phase}. Prioritise visits here. ${act}. [link]`;
      default:
        return '';
    }
  }

  return {
    LEVELS, AUDIENCES, PHASE_NAME, PHASE_TO_LEVEL,
    N_STEPS, dateAt, releaseAt, stepOfRelease, build, composeSMS, audiencesFor,
    get periods() { return PERIODS; },
    get axis() { return AXIS; },
  };
})();
