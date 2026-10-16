// SMS audit: every audience x level x event over every real unit/month in data/risk/*.js.
// Usage: node tests/e2e/sms_audit.js   (from repo root). Read-only; prints a JSON summary.
global.window = global; window.window = global;
const fs = require('fs'), path = require('path');
const ROOT = path.resolve(__dirname, '../..');
eval(fs.readFileSync(path.join(ROOT, 'js/real.js'), 'utf8') + ';global.REAL=REAL;');

// GSM 03.38 basic set and extension table (extension chars cost 2 septets).
const BASIC = new Set(('@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !"#¤%&\'()*+,-./0123456789:;<=>?' +
  '¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà').split(''));
const EXT = new Set('^{}\\[~]|€\f'.split(''));
function measure(t) {
  const chars = [...t];
  const gsm = chars.every(c => BASIC.has(c) || EXT.has(c));
  if (gsm) {
    const sept = chars.reduce((s, c) => s + (EXT.has(c) ? 2 : 1), 0);
    return { enc: 'GSM-7', units: sept, limit: 160, segs: sept <= 160 ? 1 : Math.ceil(sept / 153), naive: t.length };
  }
  const u16 = t.length;
  return { enc: 'UCS-2', units: u16, limit: 70, segs: u16 <= 70 ? 1 : Math.ceil(u16 / 67), naive: t.length,
    bad: chars.filter(c => !BASIC.has(c) && !EXT.has(c)) };
}
const PROB = /\d\s*%|P\(|\bprob|\b0\.\d|risk \d|chance/i;
const AUDS = Object.keys(REAL.AUDIENCES);
const REQ_STOP = new Set(['farmer', 'herder']);   // consumer-facing: need STOP + reply codes

const out = { combos: {}, failures: [], uiCountMismatch: [], countries: {} };
for (const iso of ['ZWE', 'KEN', 'MWI', 'ZMB']) {
  const f = path.join(ROOT, 'data/risk', iso + '.js');
  if (!fs.existsSync(f)) continue;
  eval(fs.readFileSync(f, 'utf8'));
  const R = (window.RISK_DATA || {})[iso];
  if (!R || !R.units || String(R.meta && R.meta.model_version).toUpperCase() === 'STUB') { out.countries[iso] = 'skipped (no real output)'; continue; }
  let n = 0;
  for (const u of R.units) for (const row of u.series) {
    if (row.level < 1) continue;
    const routed = REAL.audiencesFor(row.level, row);
    for (const a of AUDS) {
      // Also audit unrouted farmer/herder variants so every template is exercised.
      if (!routed.includes(a) && !(row.level >= 2 && (a === 'farmer' || a === 'herder'))) continue;
      const text = REAL.composeSMS(u.name, row, a);
      const m = measure(text); n++;
      const key = `${a}|L${row.level}|${row.event}`;
      const c = out.combos[key] || (out.combos[key] = { n: 0, maxUnits: 0, enc: new Set(), longest: '', routed: false, overs: 0 });
      c.n++; c.enc.add(m.enc); if (routed.includes(a)) c.routed = true;
      if (m.units > c.maxUnits) { c.maxUnits = m.units; c.longest = `${iso}:${u.name}: ${text}`; }
      const probs = (a === 'farmer' || a === 'herder') && PROB.test(text);
      const stop = REQ_STOP.has(a) && !(/STOP/.test(text) && /Reply 1/.test(text));
      const over = m.units > m.limit;
      if (over) c.overs++;
      if (m.naive !== m.units && m.naive <= 160 && m.units > 160) out.uiCountMismatch.push({ iso, unit: u.name, t: row.t, a, naive: m.naive, septets: m.units });
      if ((over || probs || stop || m.enc !== 'GSM-7') && out.failures.length < 400)
        out.failures.push({ iso, unit: u.name, t: row.t, a, level: row.level, event: row.event, enc: m.enc, units: m.units, over, probs, stop, routed: routed.includes(a), text });
    }
  }
  out.countries[iso] = n;
}
for (const k in out.combos) out.combos[k].enc = [...out.combos[k].enc].join(',');
const summary = {
  countries: out.countries,
  combos: Object.fromEntries(Object.entries(out.combos).sort().map(([k, v]) => [k, `${v.routed ? 'routed' : 'UNROUTED'} n=${v.n} max=${v.maxUnits} ${v.enc} overs=${v.overs}`])),
  longest: Object.fromEntries(Object.entries(out.combos).sort().map(([k, v]) => [k, v.longest])),
  failureCount: out.failures.length,
  failuresByKind: out.failures.reduce((s, f) => { const k = `${f.a}|${f.routed ? 'routed' : 'unrouted'}|${f.over ? 'over' : ''}${f.probs ? 'prob' : ''}${f.stop ? 'nostop' : ''}${f.enc !== 'GSM-7' ? f.enc : ''}`; s[k] = (s[k] || 0) + 1; return s; }, {}),
  failureSamples: out.failures.slice(0, 15),
  uiCountMismatch: out.uiCountMismatch.length, uiCountMismatchSamples: out.uiCountMismatch.slice(0, 5),
};
console.log(JSON.stringify(summary, null, 1));
