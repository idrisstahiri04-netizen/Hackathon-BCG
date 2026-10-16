"""Build the (unit, issue month) table for the IPC-target model.

Target: district enters / is in FEWS NET IPC Phase 3+ (Current Situation, CS) in the next 1-3 months
(h13) or 4-6 months (h46) after the issue month t. Everything in a row is known at the end of month t:

  signals (CHIRPS/MODIS/ERA5)  : common.apply_latency (1-month lag) on features.unit_month_features
  seasonal forecast (NMME MME3): issue_month == t (released ~8th-10th of t)
  ONI (NOAA)                   : trimester ending t-1 (published first week of t)
  FEWS NET outlook text        : outlook_<ISO3>.parquet, publish_month <= t, latest report within 3 months
  FEWS NET FDW ML1/ML2         : reporting_date <= t-1 (same 1-month latency as the CS map)
  lagged IPC state             : CS phase at t-1 (IPC_LATENCY = 1), i.e. the latest published map
  prices                       : prices_<ISO3>.parquet if present, 1-month lag (optional hook)

IPC truth -> monthly panel: CS maps exist ~3x/year (Feb, Jun, Oct; Dec 2018 instead of Oct 2018).
District phase = MAX over its livelihood-zone pieces (same as pipeline/audit/compare_ipc.py, generous
to IPC3+). The phase of a map is carried forward month by month until the next map (ffill, limit 5
months, so the 6-month Jun->Dec 2018 gap is covered). No back-fill, no interpolation between phases:
a district that moves 2->3 between maps is counted as entering at the month of the map that shows it.
Label h13 at issue t = 1 if max phase over months t+1..t+3 >= 3, 0 if all three months are known and
< 3, else missing. Same for h46 (t+4..t+6).

Unit mapping: ZWE/MWI as compare_ipc.py (district element of the FEWS full name, aliases, strip
Rural/Urban). KEN counties: any element of the FEWS full name that equals a county name (alias
"Tharaka Nithi" -> "Tharaka"). ZMB excluded: FEWS NET IPC for Zambia stops 2017-10 and never shows
Phase 3+, so it has no positive labels and no truth for the 2023/24 replay.

Usage: python pipeline/ipc_model/ipc_data.py --iso3 ZWE KEN MWI   (writes pipeline/out/ipc_model/rows.parquet)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PIPE = HERE.parent
sys.path.insert(0, str(PIPE))
from common import DATA_DIR, OUT_DIR, agyear, apply_latency, is_test, load_country, unit_seasons  # noqa: E402
from features import unit_month_features  # noqa: E402

IPC_LATENCY = 1            # months: a CS map dated month s is usable from the end of month s+1
FFILL_LIMIT = 5            # months a CS phase is carried forward (covers the Jun->Dec 2018 gap)
SOUTH = {"ZWE": 1, "MWI": 1, "ZMB": 1, "KEN": 0}
ALIASES = {
    "ZWE": {"centenary": "centenary/ muzarabani", "shurugwi urban": "shurugwi town", "harare urban": "harare"},
    "MWI": {},
    "KEN": {"tharaka nithi": "tharaka", "elgeyo marakwet": "elgeyo-marakwet", "muranga": "murang'a"},
}
HORIZONS = {"h13": (1, 3), "h46": (4, 6)}
FIRST_ISSUE, LAST_ISSUE = "2016-01-01", "2024-12-01"


# ----------------------------------------------------------------------------- month helpers
def mi(ts) -> np.ndarray:
    """month index: year*12 + month-1 (vectorised over datetime-like)."""
    ts = pd.DatetimeIndex(pd.to_datetime(ts))
    return (ts.year * 12 + ts.month - 1).values


def mi_to_ts(m) -> pd.DatetimeIndex:
    m = np.asarray(m, int)
    return pd.to_datetime(pd.DataFrame({"year": m // 12, "month": m % 12 + 1, "day": 1})).values


# ----------------------------------------------------------------------------- unit mapping
def unit_of_full_name(full: str, iso3: str, ours: dict) -> str | None:
    parts = [p.strip() for p in str(full).split(", ")]
    al = ALIASES.get(iso3, {})
    if iso3 == "KEN":
        for el in parts[1:-1]:
            s = el.lower()
            s = al.get(s, s)
            if s in ours:
                return ours[s]
        return None
    name = parts[-3] if len(parts) >= 4 else parts[0]
    s = name.lower()
    s = al.get(s, s)
    if s in ours:
        return ours[s]
    s2 = re.sub(r"\s+(rural|urban)$", "", s)
    return ours.get(s2)


def load_ipc(iso3: str, names: pd.Series) -> tuple[pd.DataFrame, dict]:
    df = pd.read_parquet(DATA_DIR / f"ipc_{iso3}.parquet")
    df = df[df.unit_type.astype(str).str.startswith("fsc_admin")].copy()
    ours = {str(n).strip().lower(): uid for uid, n in names.items()}
    fulls = df.geographic_unit_full_name.astype(str).unique()
    m = {f: unit_of_full_name(f, iso3, ours) for f in fulls}
    df["unit_id"] = df.geographic_unit_full_name.astype(str).map(m)
    matched_units = {v for v in m.values() if v}
    info = dict(fews_units=len(fulls), fews_units_matched=int(sum(v is not None for v in m.values())),
                our_units=len(names), our_units_matched=len(matched_units),
                our_unmatched=sorted(str(names[u]) for u in names.index if u not in matched_units),
                fews_unmatched=sorted(f for f, v in m.items() if v is None)[:40])
    return df.dropna(subset=["unit_id"]), info


# ----------------------------------------------------------------------------- IPC monthly panel
def ipc_panel(ipc: pd.DataFrame, units: list, months: np.ndarray) -> pd.DataFrame:
    """Monthly (unit, mi) panel: phase (ffilled CS max over pieces), share3, snap_age, is_snap."""
    cs = ipc[ipc.scenario == "CS"].copy()
    cs["value"] = pd.to_numeric(cs["value"], errors="coerce")
    cnt = cs.groupby("projection_start").fnid.nunique()
    snaps = cnt[cnt >= 0.5 * cnt.max()].index
    cs = cs[cs.projection_start.isin(snaps)]
    cs["smi"] = mi(cs.projection_start)
    g = cs.groupby(["unit_id", "smi"])["value"]
    ph = g.max()
    sh = g.apply(lambda v: float((v >= 3).mean()) if v.notna().any() else np.nan)
    snap = pd.DataFrame({"phase_snap": ph, "share3_snap": sh}).reset_index()
    grid = pd.MultiIndex.from_product([units, months], names=["unit_id", "mi"]).to_frame(index=False)
    p = grid.merge(snap, left_on=["unit_id", "mi"], right_on=["unit_id", "smi"], how="left")
    p["is_snap"] = p.smi.notna()
    p["snap_mi"] = p.smi
    p = p.sort_values(["unit_id", "mi"])
    gg = p.groupby("unit_id", group_keys=False)
    for c, src in (("phase", "phase_snap"), ("share3", "share3_snap"), ("snap_mi_f", "snap_mi")):
        p[c] = gg[src].ffill(limit=FFILL_LIMIT)
    p["snap_age"] = p.mi - p.snap_mi_f
    return p[["unit_id", "mi", "phase", "share3", "snap_age", "is_snap"]]


def state_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Lagged IPC state known at issue t: panel values at t - IPC_LATENCY, plus history."""
    p = panel.sort_values(["unit_id", "mi"]).copy()
    g = p.groupby("unit_id", group_keys=False)
    p["ge3"] = (p.phase >= 3).astype(float).where(p.phase.notna())
    # months since last IPC3+ month (within 36), any IPC3+ in last 12 months, phase 4 months ago
    p["last3_mi"] = p.mi.where(p.ge3 == 1).astype(float)
    p["last3_mi"] = g["last3_mi"].ffill()
    p["m_since3"] = (p.mi - p.last3_mi).clip(upper=36)
    p["any3_12"] = g["ge3"].transform(lambda s: s.rolling(12, min_periods=1).max())
    p["phase_prev4"] = g["phase"].shift(4)
    st = p[["unit_id", "mi", "phase", "share3", "snap_age", "m_since3", "any3_12", "phase_prev4"]].copy()
    st["mi"] = st.mi + IPC_LATENCY          # value of month s is known at issue s + latency
    st = st.rename(columns={"phase": "st_phase", "share3": "st_share3", "snap_age": "st_snap_age",
                            "m_since3": "st_m_since3", "any3_12": "st_any3_12", "phase_prev4": "st_phase_prev4"})
    st["st_snap_age"] = st.st_snap_age + IPC_LATENCY
    st["st_m_since3"] = st.st_m_since3.fillna(36.0)
    st["st_delta4"] = st.st_phase - st.st_phase_prev4
    return st


def labels(panel: pd.DataFrame) -> pd.DataFrame:
    """y_h = 1 if max phase over t+a..t+b >= 3; 0 if all months known and < 3; else NaN."""
    piv = panel.pivot(index="unit_id", columns="mi", values="phase")
    allm = np.arange(piv.columns.min(), piv.columns.max() + 7)
    piv = piv.reindex(columns=allm)
    out = {}
    for h, (a, b) in HORIZONS.items():
        mx = pd.concat([piv.shift(-k, axis=1) for k in range(a, b + 1)], keys=range(a, b + 1))
        mxv = mx.groupby(level=1).max()
        nn = mx.notna().groupby(level=1).sum()
        y = pd.DataFrame(np.where(mxv >= 3, 1.0, np.where(nn == (b - a + 1), 0.0, np.nan)),
                         index=mxv.index, columns=mxv.columns)
        out[h] = y.reset_index().melt(id_vars="unit_id", var_name="mi", value_name=f"y_{h}")
    lab = out["h13"].merge(out["h46"], on=["unit_id", "mi"])
    lab["mi"] = lab.mi.astype(int)
    return lab


# ----------------------------------------------------------------------------- FEWS NET projections (FDW)
def fdw_ml(ipc: pd.DataFrame, grid: pd.DataFrame) -> pd.DataFrame:
    """Latest FDW ML1/ML2 projection known at issue t (reporting month <= t - IPC_LATENCY, <= 4 months old)."""
    ml = ipc[ipc.scenario.isin(["ML1", "ML2"])].copy()
    if ml.empty:
        return grid[["unit_id", "mi"]].assign(fdw_ml1=np.nan, fdw_ml2=np.nan, fdw_ml1_share3=np.nan,
                                              fdw_age=np.nan, fdw_ml1_ps=np.nan, fdw_ml1_pe=np.nan,
                                              fdw_ml2_ps=np.nan, fdw_ml2_pe=np.nan)
    ml["value"] = pd.to_numeric(ml["value"], errors="coerce")
    ml["rep"] = mi(pd.to_datetime(ml.reporting_date))
    ml["ps"] = mi(ml.projection_start)
    ml["pe"] = mi(ml.projection_end)
    g = ml.groupby(["unit_id", "rep", "scenario"])
    agg = pd.DataFrame({"v": g["value"].max(), "sh": g["value"].apply(lambda v: float((v >= 3).mean()) if v.notna().any() else np.nan),
                        "ps": g["ps"].min(), "pe": g["pe"].max()}).reset_index()
    w = agg.pivot(index=["unit_id", "rep"], columns="scenario", values=["v", "sh", "ps", "pe"])
    w.columns = [f"{a}_{b}" for a, b in w.columns]
    w = w.reset_index()
    w["avail"] = w.rep + IPC_LATENCY
    rows = []
    for k in range(0, 5):               # latest report within 4 months
        t = w.copy(); t["mi"] = t.avail + k; t["fdw_age"] = k; rows.append(t)
    allr = pd.concat(rows).sort_values(["unit_id", "mi", "fdw_age"]).drop_duplicates(["unit_id", "mi"], keep="first")
    out = grid[["unit_id", "mi"]].merge(allr, on=["unit_id", "mi"], how="left")
    ren = {"v_ML1": "fdw_ml1", "v_ML2": "fdw_ml2", "sh_ML1": "fdw_ml1_share3", "ps_ML1": "fdw_ml1_ps",
           "pe_ML1": "fdw_ml1_pe", "ps_ML2": "fdw_ml2_ps", "pe_ML2": "fdw_ml2_pe"}
    for c in ren:
        if c not in out:
            out[c] = np.nan
    out = out.rename(columns=ren)
    return out[["unit_id", "mi", "fdw_ml1", "fdw_ml2", "fdw_ml1_share3", "fdw_age",
                "fdw_ml1_ps", "fdw_ml1_pe", "fdw_ml2_ps", "fdw_ml2_pe"]]


def fews_benchmark(df: pd.DataFrame) -> pd.DataFrame:
    """FEWS NET's own projection as a score per horizon: max projected phase of the ML windows that
    overlap the horizon window (NaN if no overlapping projection is known at issue)."""
    for h, (a, b) in HORIZONS.items():
        lo, hi = df.mi + a, df.mi + b
        s = np.full(len(df), np.nan)
        for sc in ("ml1", "ml2"):
            v, ps, pe = df[f"fdw_{sc}"].values, df[f"fdw_{sc}_ps"].values, df[f"fdw_{sc}_pe"].values
            ov = (ps <= hi.values) & (pe >= lo.values) & ~np.isnan(v)
            s = np.where(ov, np.fmax(s, v), s)
        df[f"fews_{h}"] = s
    return df


# ----------------------------------------------------------------------------- FEWS NET outlook text
def outlook_features(iso3: str, grid: pd.DataFrame) -> pd.DataFrame:
    cols = ["ol_cur", "ol_p13", "ol_p46", "ol_pany", "ol_p13_hi", "ol_score", "ol_age", "ol_n"]
    f = DATA_DIR / f"outlook_{iso3}.parquet"
    base = grid[["unit_id", "mi"]].copy()
    if not f.exists():
        for c in cols:
            base[c] = np.nan
        return base
    o = pd.read_parquet(f)
    if o.empty:
        for c in cols:
            base[c] = np.nan
        return base
    o = o.dropna(subset=["projected_phase"]).copy()
    o["pub"] = mi(pd.to_datetime(o.publish_month + "-01"))
    o["tgt"] = mi(pd.to_datetime(o.target_month + "-01"))
    o["ph"] = o.projected_phase.astype(float)
    docs = o[["unit_id", "pub"]].drop_duplicates()
    rows = []
    for k in range(0, 3):               # latest report within 3 months
        t = docs.copy(); t["mi"] = t.pub + k; t["ol_age"] = k; rows.append(t)
    latest = pd.concat(rows).sort_values(["unit_id", "mi", "ol_age"]).drop_duplicates(["unit_id", "mi"], keep="first")
    j = latest.merge(o[["unit_id", "pub", "tgt", "ph", "statement_type", "match_score"]], on=["unit_id", "pub"])
    j["h"] = j.tgt - j.mi
    cur = j.statement_type.eq("current") | (j.h <= 0)
    hi = j.match_score >= 90
    def agg(mask, name):
        return j[mask].groupby(["unit_id", "mi"]).ph.max().rename(name)
    parts = [agg(cur, "ol_cur"), agg(~cur & j.h.between(1, 3), "ol_p13"), agg(~cur & j.h.between(4, 6), "ol_p46"),
             agg(~cur & (j.h >= 1), "ol_pany"), agg(~cur & j.h.between(1, 3) & hi, "ol_p13_hi"),
             j.groupby(["unit_id", "mi"]).match_score.max().rename("ol_score"),
             j.groupby(["unit_id", "mi"]).ol_age.first().rename("ol_age"),
             j.groupby(["unit_id", "mi"]).size().rename("ol_n").astype(float)]
    feat = pd.concat(parts, axis=1).reset_index()
    return base.merge(feat, on=["unit_id", "mi"], how="left")


# ----------------------------------------------------------------------------- seasonal forecast, ONI, prices
def seasonal_features(iso3: str, grid: pd.DataFrame) -> pd.DataFrame:
    base = grid[["unit_id", "mi"]].copy()
    f = DATA_DIR / f"seasonal_fc_{iso3}.parquet"
    if not f.exists():
        for c in ("sfc_z13", "sfc_p13", "sfc_z46", "sfc_p46", "sfc_z13_l1"):
            base[c] = np.nan
        return base
    s = pd.read_parquet(f)
    s = s[s["product"] == "NMME/MME3"].copy()
    s["mi"] = mi(s.issue_month)
    w = s.pivot_table(index=["unit_id", "mi"], columns="target_window", values=["anom_z", "p_below_normal"])
    w.columns = [f"{a}_{b}" for a, b in w.columns]
    w = w.reset_index().rename(columns={"anom_z_m1-3": "sfc_z13", "p_below_normal_m1-3": "sfc_p13",
                                        "anom_z_m4-6": "sfc_z46", "p_below_normal_m4-6": "sfc_p46"})
    l1 = w[["unit_id", "mi", "sfc_z13"]].copy(); l1["mi"] = l1.mi + 1; l1 = l1.rename(columns={"sfc_z13": "sfc_z13_l1"})
    out = base.merge(w, on=["unit_id", "mi"], how="left").merge(l1, on=["unit_id", "mi"], how="left")
    return out


def oni_series() -> pd.Series:
    d = json.loads((PIPE / "experiments" / "climate_indices.json").read_text())["oni_trimester_end"]
    s = pd.Series({pd.Timestamp(k + "-01"): (np.nan if v is None else float(v)) for k, v in d.items()}).sort_index()
    s.index = mi(s.index)
    return s


def oni_features(grid: pd.DataFrame, south: int) -> pd.DataFrame:
    o = oni_series()
    out = grid[["unit_id", "mi"]].copy()
    cur = o.reindex(out.mi - 1).values           # trimester ending t-1: published in the first week of t
    prev = o.reindex(out.mi - 4).values
    out["oni"] = cur
    out["oni_d3"] = cur - prev
    out["oni_x_south"] = cur * (2 * south - 1)
    out["south"] = float(south)
    return out


def price_features(iso3: str, grid: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """Optional hook: prices_<ISO3>.parquet with unit_id, month and numeric columns; 1-month latency."""
    f = DATA_DIR / f"prices_{iso3}.parquet"
    base = grid[["unit_id", "mi"]].copy()
    if not f.exists():
        return base, []
    p = pd.read_parquet(f)
    if "month" not in p or "unit_id" not in p:
        return base, []
    p = p.copy()
    p["mi"] = mi(pd.to_datetime(p.month)) + 1          # value of month m usable from end of m+1
    num = [c for c in p.columns if c not in ("unit_id", "month", "mi", "unit_name", "iso3")
           and pd.api.types.is_numeric_dtype(p[c])]
    if "signal_type" in p and "value" in p:            # long format like signals
        w = p.pivot_table(index=["unit_id", "mi"], columns="signal_type", values="value", aggfunc="mean").reset_index()
        num = [c for c in w.columns if c not in ("unit_id", "mi")]
        p = w
    p = p.groupby(["unit_id", "mi"])[num].mean().reset_index()
    p = p.rename(columns={c: f"price_{c}" for c in num})
    return base.merge(p, on=["unit_id", "mi"], how="left"), [f"price_{c}" for c in num]


# ----------------------------------------------------------------------------- build
def build_country(iso3: str) -> tuple[pd.DataFrame, dict]:
    c = load_country(iso3)
    ss = unit_seasons(c)
    plant = {u: v[0].planting[0] for u, v in ss.items()}
    feat = apply_latency(unit_month_features(c))          # signals of t-1 at issue t
    feat = feat.reset_index()
    feat["mi"] = mi(feat.month)
    units = list(c.names.index)
    months = np.arange(mi([FIRST_ISSUE])[0] - 12, mi([LAST_ISSUE])[0] + 7)
    ipc, info = load_ipc(iso3, c.names)
    panel = ipc_panel(ipc, units, months)
    st = state_features(panel)
    lab = labels(panel)
    issue = np.arange(mi([FIRST_ISSUE])[0], mi([LAST_ISSUE])[0] + 1)
    grid = pd.MultiIndex.from_product([units, issue], names=["unit_id", "mi"]).to_frame(index=False)
    df = (grid.merge(st, on=["unit_id", "mi"], how="left").merge(lab, on=["unit_id", "mi"], how="left")
          .merge(feat.drop(columns=["month"]), on=["unit_id", "mi"], how="left")
          .merge(fdw_ml(ipc, grid), on=["unit_id", "mi"], how="left")
          .merge(outlook_features(iso3, grid), on=["unit_id", "mi"], how="left")
          .merge(seasonal_features(iso3, grid), on=["unit_id", "mi"], how="left")
          .merge(oni_features(grid, SOUTH.get(iso3, 0)), on=["unit_id", "mi"], how="left"))
    pr, price_cols = price_features(iso3, grid)
    df = df.merge(pr, on=["unit_id", "mi"], how="left")
    df = fews_benchmark(df)
    df["iso3"] = iso3
    df["unit_name"] = df.unit_id.map(c.names)
    df["month"] = mi_to_ts(df.mi)
    df["agyear"] = [agyear(t) for t in df.month]
    df["season"] = [f"{a}/{str(a + 1)[2:]}" for a in df.agyear]
    df["test"] = [is_test(iso3, a) for a in df.agyear]
    df["phase_m"] = ((df.month.dt.month - df.unit_id.map(plant)) % 12).astype(float)
    for h, (a, b) in HORIZONS.items():
        df[f"win_end_{h}"] = df.mi + b
    # truth bookkeeping for the replay: ffilled CS phase at t itself (not known at t; for evaluation only)
    df = df.merge(panel[["unit_id", "mi", "phase", "is_snap"]].rename(columns={"phase": "truth_phase", "is_snap": "truth_is_snap"}),
                  on=["unit_id", "mi"], how="left")
    info.update(price_cols=price_cols, rows=int(len(df)),
                rows_with_state=int(df.st_phase.notna().sum()),
                base_rate_h13=round(float(df.y_h13.mean()), 3) if df.y_h13.notna().any() else None,
                base_rate_h46=round(float(df.y_h46.mean()), 3) if df.y_h46.notna().any() else None,
                entry_rate_h13=round(float(df.loc[df.st_phase < 3, "y_h13"].mean()), 3) if (df.st_phase < 3).any() else None,
                snapshots=sorted(str(m)[:10] for m in mi_to_ts(panel.loc[panel.is_snap, "mi"].unique())))
    return df, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso3", nargs="+", default=["ZWE", "KEN", "MWI"])
    ap.add_argument("--out", default=str(OUT_DIR / "ipc_model"))
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    parts, infos = [], {}
    for iso3 in a.iso3:
        df, info = build_country(iso3)
        parts.append(df); infos[iso3] = info
        print(iso3, {k: v for k, v in info.items() if k not in ("our_unmatched", "fews_unmatched", "snapshots")}, flush=True)
        print("  unmatched ours:", info["our_unmatched"])
    rows = pd.concat(parts, ignore_index=True)
    rows.to_parquet(out / "rows.parquet", index=False)
    (out / "build_info.json").write_text(json.dumps(infos, indent=1, default=str))
    print("rows", rows.shape, "->", out / "rows.parquet")


if __name__ == "__main__":
    main()
