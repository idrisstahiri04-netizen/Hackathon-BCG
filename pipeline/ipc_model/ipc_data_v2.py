"""v2 of ipc_data.py: polygon-matched IPC truth (area-weighted overlay) instead of name matching, more countries.

Differences to ipc_data.py (everything else is reused from it, unchanged):
  * truth comes from pipeline/data/ipc_units_<ISO3>.parquet (ipc_geo_overlay.py): one row per
    (unit, scenario, projection_start, reporting_date) with area-weighted phase summaries.
    Unit phase = --label: w50 (worst phase covering >= 50 % of the unit's classified area, default),
    w20 (worst phase covering >= 20 %), or max (worst touching piece, the old rule). share3 = area share in IPC3+.
  * FEWS NET numeric projections (FDW ML1/ML2) use the same unit-level phase; they exist for every country.
    Outlook text features (ol_*) stay as in v1 (ZWE/MWI/ZMB only; NaN elsewhere).
  * prices: price_<signal> from prices_<ISO3>.parquet (1-month publish latency, see PRICES.md) + has_price indicator.
  * SOUTH flag for the extra countries.
Usage: python pipeline/ipc_model/ipc_data_v2.py --iso3 ZWE KEN MWI MOZ ETH SOM MDG UGA [--label w50]
Writes <out>/rows.parquet + build_info.json (default pipeline/out/ipc_model_v2).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import ipc_data as B  # noqa: E402
from common import DATA_DIR, OUT_DIR  # noqa: E402

B.SOUTH.update({"MOZ": 1, "MDG": 1, "AGO": 1, "NAM": 1, "BWA": 1, "ZAF": 1, "TZA": 1, "ETH": 0, "SOM": 0, "UGA": 0})
LABEL_COL = {"w50": "phase_w50", "w20": "phase_w20", "max": "phase_max"}
_PHASE_COL = "phase_w50"


def load_ipc_units(iso3: str, names: pd.Series) -> tuple[pd.DataFrame, dict]:
    t = pd.read_parquet(DATA_DIR / f"ipc_units_{iso3}.parquet")
    t = t[t.unit_id.isin(names.index)].copy()
    t["value"] = t[_PHASE_COL].astype(float)
    t["fnid"] = t.unit_id                                  # one "piece" per unit now
    for c in ("projection_start", "projection_end", "reporting_date"):
        t[c] = pd.to_datetime(t[c])
    cs_units = set(t.loc[t.scenario == "CS", "unit_id"])
    info = dict(label_col=_PHASE_COL, our_units=len(names), our_units_matched=len(cs_units),
                our_unmatched=sorted(str(names[u]) for u in names.index if u not in cs_units),
                mean_cover=round(float(t.cover.mean()), 3))
    return t, info


def ipc_panel_v2(ipc: pd.DataFrame, units: list, months: np.ndarray) -> pd.DataFrame:
    """As ipc_data.ipc_panel, but share3 is the area share (not the fraction of pieces)."""
    cs = ipc[ipc.scenario == "CS"].copy()
    cnt = cs.groupby("projection_start").unit_id.nunique()
    snaps = cnt[cnt >= 0.5 * cnt.max()].index
    cs = cs[cs.projection_start.isin(snaps)]
    cs["smi"] = B.mi(cs.projection_start)
    g = cs.groupby(["unit_id", "smi"])
    snap = pd.DataFrame({"phase_snap": g["value"].max(), "share3_snap": g["share3"].max()}).reset_index()
    grid = pd.MultiIndex.from_product([units, months], names=["unit_id", "mi"]).to_frame(index=False)
    p = grid.merge(snap, left_on=["unit_id", "mi"], right_on=["unit_id", "smi"], how="left")
    p["is_snap"] = p.smi.notna()
    p["snap_mi"] = p.smi
    p = p.sort_values(["unit_id", "mi"])
    gg = p.groupby("unit_id", group_keys=False)
    for c, src in (("phase", "phase_snap"), ("share3", "share3_snap"), ("snap_mi_f", "snap_mi")):
        p[c] = gg[src].ffill(limit=B.FFILL_LIMIT)
    p["snap_age"] = p.mi - p.snap_mi_f
    return p[["unit_id", "mi", "phase", "share3", "snap_age", "is_snap"]]


def fdw_ml_v2(ipc: pd.DataFrame, grid: pd.DataFrame) -> pd.DataFrame:
    """As ipc_data.fdw_ml with the area share3 of the unit-level table."""
    ml = ipc[ipc.scenario.isin(["ML1", "ML2"])].copy()
    cols = ["fdw_ml1", "fdw_ml2", "fdw_ml1_share3", "fdw_age", "fdw_ml1_ps", "fdw_ml1_pe", "fdw_ml2_ps", "fdw_ml2_pe"]
    if ml.empty:
        return grid[["unit_id", "mi"]].assign(**{c: np.nan for c in cols})
    ml["rep"] = B.mi(ml.reporting_date)
    ml["ps"] = B.mi(ml.projection_start)
    ml["pe"] = B.mi(ml.projection_end)
    g = ml.groupby(["unit_id", "rep", "scenario"])
    agg = pd.DataFrame({"v": g["value"].max(), "sh": g["share3"].max(), "ps": g["ps"].min(), "pe": g["pe"].max()}).reset_index()
    w = agg.pivot(index=["unit_id", "rep"], columns="scenario", values=["v", "sh", "ps", "pe"])
    w.columns = [f"{a}_{b}" for a, b in w.columns]
    w = w.reset_index()
    w["avail"] = w.rep + B.IPC_LATENCY
    rows = []
    for k in range(0, 5):
        t = w.copy(); t["mi"] = t.avail + k; t["fdw_age"] = k; rows.append(t)
    allr = pd.concat(rows).sort_values(["unit_id", "mi", "fdw_age"]).drop_duplicates(["unit_id", "mi"], keep="first")
    out = grid[["unit_id", "mi"]].merge(allr, on=["unit_id", "mi"], how="left")
    ren = {"v_ML1": "fdw_ml1", "v_ML2": "fdw_ml2", "sh_ML1": "fdw_ml1_share3", "ps_ML1": "fdw_ml1_ps",
           "pe_ML1": "fdw_ml1_pe", "ps_ML2": "fdw_ml2_ps", "pe_ML2": "fdw_ml2_pe"}
    for c in ren:
        if c not in out:
            out[c] = np.nan
    return out.rename(columns=ren)[["unit_id", "mi"] + cols]


# plug the polygon-based truth into the v1 builder (build_country looks these up at call time)
B.load_ipc = load_ipc_units
B.ipc_panel = ipc_panel_v2
B.fdw_ml = fdw_ml_v2


def build_country(iso3: str) -> tuple[pd.DataFrame, dict]:
    df, info = B.build_country(iso3)
    df["has_price"] = df["price_price_anom"].notna().astype(float) if "price_price_anom" in df else 0.0
    info["has_price_share"] = round(float(df.has_price.mean()), 3)
    info["cs_rows_2023_24"] = int(((df.agyear == 2023) & df.y_h13.notna()).sum())
    return df, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso3", nargs="+", default=["ZWE", "KEN", "MWI", "MOZ", "ETH", "SOM", "MDG", "UGA"])
    ap.add_argument("--label", choices=list(LABEL_COL), default="w50")
    ap.add_argument("--out", default=str(OUT_DIR / "ipc_model_v2"))
    a = ap.parse_args()
    global _PHASE_COL
    _PHASE_COL = LABEL_COL[a.label]
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    parts, infos = [], {"label": a.label}
    for iso3 in a.iso3:
        df, info = build_country(iso3)
        parts.append(df); infos[iso3] = info
        print(iso3, {k: v for k, v in info.items() if k not in ("our_unmatched", "snapshots")}, flush=True)
        print("  unmatched ours:", info["our_unmatched"][:20], flush=True)
    rows = pd.concat(parts, ignore_index=True)
    for c in rows.columns:
        if c.startswith("price_"):
            rows[c] = rows[c].astype(float)
    rows.to_parquet(out / "rows.parquet", index=False)
    (out / "build_info.json").write_text(json.dumps(infos, indent=1, default=str))
    print("rows", rows.shape, "->", out / "rows.parquet")


if __name__ == "__main__":
    main()
