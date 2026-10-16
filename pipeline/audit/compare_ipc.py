"""Ground-truth audit: our satellite/weather alerts vs FEWS NET IPC phases (independent truth).

Usage: python -I pipeline/audit/compare_ipc.py [ISO3 ...] [--allow-stub]   (default ZWE)
Inputs:  data/risk/<ISO3>.js (CONTRACT section 3), pipeline/data/ipc_<ISO3>.parquet (fetch_ipc.py)
Outputs: pipeline/audit/out/units_<ISO3>.csv, pipeline/audit/out/metrics_<ISO3>.json

Unit mapping (no geometry needed): FEWS NET fsc_admin_lhz units are livelihood-zone pieces
*nested inside* one admin2 district; the district name is the 3rd-from-last element of
geographic_unit_full_name ("<LHZ>, <District>, <Province>, <Country>"). We match it to our
ADM2 name after normalisation + a small alias table. District phase per snapshot = MAX over
its LHZ pieces ("any part of the district in IPC3+"); NaN pieces stay missing.

Truth = FEWS NET Current Situation (CS) snapshots (Feb / Jun / Oct each year).
Season y = agricultural year planted Oct-Dec y. Its impact window = CS snapshots
Feb(y+1), Jun(y+1), Oct(y+1). "Transition" = unit not IPC3+ at the Oct(y) pre-season
snapshot, IPC3+ in the impact window. Alert window for season y = months Oct(y)..Jun(y+1).
Persistence baseline: predict IPC3+ in season y's window iff IPC3+ in season y-1's window.
FEWS NET projection benchmark: earliest monthly report (Jun y..Jun y+1) whose ML1/ML2 projection
puts any LHZ piece of the district in IPC3+ (uses reporting_date as the issue date).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PIPE = HERE.parent
ROOT = PIPE.parent
OUT = HERE / "out"
WPM = 52.1775 / 12  # weeks per month

ALIASES = {
    "ZWE": {"centenary": "centenary/ muzarabani", "shurugwi urban": "shurugwi town",
            "harare urban": "harare"},
    "MWI": {},
}


def fews_to_ours(name: str, iso3: str, ours: set[str]) -> str | None:
    """Map a FEWS NET admin2 name to one of our (lower-cased) unit names, else None."""
    s = name.strip().lower()
    s = ALIASES.get(iso3, {}).get(s, s)
    if s in ours:
        return s
    s2 = re.sub(r"\s+(rural|urban)$", "", s)
    return s2 if s2 in ours else None


def load_risk(iso3: str) -> dict:
    s = (ROOT / "data" / "risk" / f"{iso3}.js").read_text()
    i = s.index(f'RISK_DATA["{iso3}"]')
    body = s[s.index("=", i) + 1:].strip().rstrip(";")
    return json.loads(body)


def risk_panel(risk: dict) -> pd.DataFrame:
    y0 = risk["meta"]["start_year"]
    rows = []
    for u in risk["units"]:
        for e in u["series"]:
            rows.append((u["id"], u["name"], e["t"], e["level"]))
    df = pd.DataFrame(rows, columns=["unit_id", "unit_name", "t", "level"])
    df["month"] = pd.to_datetime([f"{y0 + t // 12}-{t % 12 + 1:02d}-01" for t in df.t])
    return df


def ipc_panel(iso3: str, units: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    df = pd.read_parquet(PIPE / "data" / f"ipc_{iso3}.parquet")
    df = df[df.unit_type.str.startswith("fsc_admin")]
    parts = df.geographic_unit_full_name.str.split(", ")
    ukey = {n.strip().lower(): i for i, n in zip(units.unit_id, units.unit_name)}
    df = df.assign(fews_name=[p[-3] if len(p) >= 4 else p[0] for p in parts])
    m = {f: fews_to_ours(f, iso3, set(ukey)) for f in df.fews_name.unique()}
    df["unit_id"] = df.fews_name.map(lambda f: ukey.get(m[f]) if m[f] else None)
    hit = {v for v in m.values() if v}
    match = {
        "our_units": len(ukey), "our_units_matched": len(hit),
        "fews_districts": len(m), "fews_districts_matched": int(sum(v is not None for v in m.values())),
        "our_unmatched": sorted(n for n in units.unit_name if n.strip().lower() not in hit),
        "fews_unmatched": sorted(k for k, v in m.items() if v is None),
        "method": "name match on admin2 element of FEWS NET fsc_admin_lhz full name; district = max over LHZ pieces",
    }
    df = df.dropna(subset=["unit_id"])
    ml = df[df.scenario.isin(["ML1", "ML2"]) & (df.value >= 3)]
    ml = ml.assign(rep=pd.to_datetime(ml.reporting_date))[["unit_id", "rep"]].drop_duplicates()
    df = df[df.scenario == "CS"]
    # snapshots = CS dates covering many units (drop single-row admin0 entries)
    cnt = df.groupby("projection_start").unit_id.nunique()
    snaps = cnt[cnt >= 0.5 * cnt.max()].index
    df = df[df.projection_start.isin(snaps)]
    g = df.groupby(["unit_id", "projection_start"]).value
    p = pd.DataFrame({"phase": g.max(), "share3": g.apply(lambda v: (v >= 3).mean() if v.notna().any() else np.nan)})
    return p.reset_index().rename(columns={"projection_start": "snap"}), match, ml


def season_tables(risk: pd.DataFrame, ipc: pd.DataFrame, ml: pd.DataFrame, seasons: list[int]) -> pd.DataFrame:
    ph = ipc.pivot(index="unit_id", columns="snap", values="phase")
    rows = []
    for y in seasons:
        pre = pd.Timestamp(f"{y}-10-01")
        win = [pd.Timestamp(f"{y + 1}-{m:02d}-01") for m in (2, 6, 10)]
        prev_win = [pd.Timestamp(f"{y}-{m:02d}-01") for m in (2, 6, 10)]
        a0, a1 = pre, pd.Timestamp(f"{y + 1}-06-01")
        r = risk[(risk.month >= a0) & (risk.month <= a1)]
        for uid, gr in r.groupby("unit_id"):
            def snapval(d):
                return ph.at[uid, d] if (uid in ph.index and d in ph.columns) else np.nan
            wv = [snapval(d) for d in win]
            pv = [snapval(d) for d in prev_win]
            first3 = next((d for d, v in zip(win, wv) if v >= 3), pd.NaT)
            fw = gr[gr.level >= 1].month.min()
            fwarn = gr[gr.level >= 2].month.min()
            # FEWS NET's own early warning: first monthly report (Jun y..Jun y+1) projecting IPC3+
            mu = ml[(ml.unit_id == uid) & (ml.rep >= pd.Timestamp(f"{y}-06-01")) & (ml.rep <= a1)]
            fproj = mu.rep.min()
            rows.append(dict(
                season=f"{y}/{str(y + 1)[2:]}", unit_id=uid, unit_name=gr.unit_name.iloc[0],
                phase_pre=snapval(pre),
                ipc3_window=(np.nan if all(np.isnan(wv)) else float(np.nanmax(wv) >= 3)),
                ipc3_prev_window=(np.nan if all(np.isnan(pv)) else float(np.nanmax(pv) >= 3)),
                first_ipc3=first3, first_watch=fw, first_warning=fwarn, first_fews_proj3=fproj,
                max_level=int(gr.level.max())))
    t = pd.DataFrame(rows)
    mdiff = lambda a, b: ((a.dt.year - b.dt.year) * 12 + (a.dt.month - b.dt.month)) * WPM  # noqa: E731
    t["warning_vs_fews_wk"] = mdiff(t.first_fews_proj3, t.first_warning)  # >0: we warned earlier
    t["fews_proj_lead_wk"] = mdiff(t.first_ipc3, t.first_fews_proj3)
    t["transition"] = np.where(t.ipc3_window.isna() | t.phase_pre.isna(), np.nan,
                               ((t.phase_pre < 3) & (t.ipc3_window == 1)).astype(float))
    t["pred_warning"] = t.first_warning.notna().astype(float)
    t["pred_watch"] = t.first_watch.notna().astype(float)
    for c in ("watch", "warning"):
        t[f"lead_wk_{c}"] = ((t.first_ipc3.dt.year - t[f"first_{c}"].dt.year) * 12
                             + (t.first_ipc3.dt.month - t[f"first_{c}"].dt.month)) * WPM
    return t


def prf(truth: pd.Series, pred: pd.Series) -> dict:
    m = truth.notna() & pred.notna()
    tr, pr = truth[m].astype(bool), pred[m].astype(bool)
    tp, fp, fn = int((tr & pr).sum()), int((~tr & pr).sum()), int((tr & ~pr).sum())
    tn = int((~tr & ~pr).sum())
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else None
    r3 = lambda x: None if x is None else round(x, 3)  # noqa: E731
    return dict(n=int(m.sum()), tp=tp, fp=fp, fn=fn, tn=tn, precision=r3(prec), recall=r3(rec), f1=r3(f1))


def summarise(t: pd.DataFrame) -> dict:
    out = {}
    tr = t[t.transition.notna()]
    # transitions: units not IPC3+ pre-season -> did they go IPC3+? (persistence predicts "no" by construction)
    out["transition_warning"] = prf(tr.transition, tr.pred_warning)
    out["transition_watch"] = prf(tr.transition, tr.pred_watch)
    out["transition_persistence"] = prf(tr.transition, tr.ipc3_prev_window)
    # level target: IPC3+ anywhere in impact window, all units with truth
    lv = t[t.ipc3_window.notna()]
    out["ipc3_window_warning"] = prf(lv.ipc3_window, lv.pred_warning)
    out["ipc3_window_persistence"] = prf(lv.ipc3_window, lv.ipc3_prev_window)
    hit = tr[(tr.transition == 1) & tr.first_warning.notna()]
    for c in ("warning", "watch"):
        h = tr[(tr.transition == 1) & tr[f"first_{c}"].notna()][f"lead_wk_{c}"]
        out[f"lead_weeks_{c}"] = (None if h.empty else
                                  dict(n=int(h.size), median=round(float(h.median()), 1),
                                       min=round(float(h.min()), 1), max=round(float(h.max()), 1),
                                       share_ge_4wk=round(float((h >= 4).mean()), 3)))
    out["transition_fews_projection"] = prf(tr.transition, tr.first_fews_proj3.notna().astype(float))
    for c in ("warning_vs_fews_wk", "fews_proj_lead_wk"):
        h = tr[(tr.transition == 1)][c].dropna()
        out[c] = (None if h.empty else dict(n=int(h.size), median=round(float(h.median()), 1),
                                             share_gt0=round(float((h > 0).mean()), 3)))
    out["n_transitions"] = int((tr.transition == 1).sum())
    out["n_units_with_warning"] = int(t.pred_warning.sum())
    _ = hit
    return out


def run(iso3: str, allow_stub: bool) -> dict:
    risk = load_risk(iso3)
    mv = risk["meta"].get("model_version")
    if mv == "STUB" and not allow_stub:
        raise SystemExit(f"{iso3}: risk file is STUB; rerun when the real model is exported (or --allow-stub)")
    rp = risk_panel(risk)
    units = rp[["unit_id", "unit_name"]].drop_duplicates()
    ipc, match, ml = ipc_panel(iso3, units)
    last = rp.month.max()
    seasons = [y for y in range(rp.month.min().year, last.year + 1)
               if pd.Timestamp(f"{y + 1}-06-01") <= last and pd.Timestamp(f"{y}-10-01") >= rp.month.min()]
    t = season_tables(rp, ipc, ml, seasons)
    OUT.mkdir(exist_ok=True)
    t.to_csv(OUT / f"units_{iso3}.csv", index=False)
    res = {"iso3": iso3, "model_version": mv, "generated_at": risk["meta"].get("generated_at"),
           "unit_match": match, "ipc_snapshots": sorted(str(d.date()) for d in ipc.snap.unique()),
           "seasons": {}}
    for s, g in t.groupby("season"):
        res["seasons"][s] = summarise(g)
    res["all_seasons"] = summarise(t)
    (OUT / f"metrics_{iso3}.json").write_text(json.dumps(res, indent=1, default=str))
    return res


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for iso in (args or ["ZWE"]):
        r = run(iso, "--allow-stub" in sys.argv)
        print(json.dumps({k: r[k] for k in ("iso3", "model_version")}, default=str))
        print(" match:", {k: v for k, v in r["unit_match"].items() if k != "method"})
        for s, m in {**r["seasons"], "ALL": r["all_seasons"]}.items():
            print(f" {s}: trans={m['n_transitions']} warnUnits={m['n_units_with_warning']} "
                  f"T-warn={m['transition_warning']} T-persist={m['transition_persistence']} "
                  f"L-warn={m['ipc3_window_warning']} L-persist={m['ipc3_window_persistence']} "
                  f"lead={m['lead_weeks_warning']} T-fewsproj={m['transition_fews_projection']} "
                  f"vsFEWS={m['warning_vs_fews_wk']} fewsLead={m['fews_proj_lead_wk']}")
