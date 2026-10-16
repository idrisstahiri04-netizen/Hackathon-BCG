"""Alternative (stricter / cleaner) targets, computed from the same windows as labels.py.

Per (unit, event, W0) using the unshifted wide signal grid (labels are outcomes, no latency):
  label          current: min VCI over window < 35                    (base ~0.45)
  label_mean35   window-mean VCI < 35
  label_min20    min VCI over window < 20
  label_q20      min VCI over window below the unit's 20th percentile of the same statistic
                 over baseline seasons 2001-2020 (per unit, event, season idx) -> base ~0.2 by construction
  label_mean_q20 window-mean VCI below the unit's 20th percentile (baseline 2001-2020)
cant_plant keeps its definition (not a VCI event); the alt columns are NaN for it.

Prev-season columns prev_label_<name> are added for the persistence baseline.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = Path(os.environ.get("EXP_OUT", str(HERE)))   # artefacts (caches, OOF, results); HERE = code + small data
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(HERE.parent))
from common import WINDOW_LEN, BASE_START, BASE_END   # noqa: E402

SIG = {"crop_failure": "vci_crop", "no_grass": "vci_grass"}
ALT = ["label_mean35", "label_min20", "label_q20", "label_mean_q20"]


def window_stats(rows: pd.DataFrame, wide_path=None) -> pd.DataFrame:
    """One row per (unit_id, event, W0, season, agyear) with window min / mean VCI."""
    w = pd.read_parquet(wide_path or OUT / "wide_base.parquet")
    w["month"] = pd.to_datetime(w["month"])
    inst = rows.drop_duplicates(["unit_id", "event", "W0"])[["unit_id", "event", "W0", "season", "agyear"]].copy()
    out = []
    for ev, sig in SIG.items():
        n = WINDOW_LEN[ev]
        s = inst[inst.event == ev]
        parts = []
        for k in range(n):
            p = s[["unit_id", "event", "W0"]].copy()
            p["month"] = p["W0"] + pd.DateOffset(months=k)
            parts.append(p)
        ex = pd.concat(parts).merge(w[["unit_id", "month", sig]], on=["unit_id", "month"], how="left")
        agg = ex.groupby(["unit_id", "event", "W0"])[sig].agg(vmin="min", vmean="mean", nobs="count").reset_index()
        out.append(agg)
    st = pd.concat(out, ignore_index=True).merge(inst, on=["unit_id", "event", "W0"], how="left")
    st.loc[st.nobs == 0, ["vmin", "vmean"]] = np.nan
    return st


def alt_labels(rows: pd.DataFrame, wide_path=None) -> pd.DataFrame:
    st = window_stats(rows, wide_path)
    st["label_mean35"] = (st.vmean < 35).astype(float).where(st.vmean.notna())
    st["label_min20"] = (st.vmin < 20).astype(float).where(st.vmin.notna())
    base = st[(st.W0.dt.year >= BASE_START) & (st.W0.dt.year <= BASE_END)]
    for col, src in (("label_q20", "vmin"), ("label_mean_q20", "vmean")):
        q = base.groupby(["unit_id", "event", "season"])[src].quantile(0.2).rename("q")
        st = st.merge(q, left_on=["unit_id", "event", "season"], right_index=True, how="left")
        st[col] = (st[src] < st["q"]).astype(float).where(st[src].notna() & st["q"].notna())
        st = st.drop(columns=["q"])
    st = st.sort_values(["unit_id", "event", "W0"])
    for col in ALT:
        st[col.replace("label", "prev_label")] = st.groupby(["unit_id", "event"])[col].shift(1)
    keep = ["unit_id", "event", "W0", "vmin", "vmean"] + ALT + [c.replace("label", "prev_label") for c in ALT]
    return rows.merge(st[keep], on=["unit_id", "event", "W0"], how="left")


if __name__ == "__main__":
    rows = pd.read_parquet(OUT / "rows_base.parquet")
    r = alt_labels(rows)
    cv = r[~r.test & r.agyear.between(2001, 2022) & (r.lead == 1)]
    print(cv.groupby("event")[["label"] + ALT].mean().round(3))
    print(cv.groupby(["iso3", "event"])[["label"] + ALT].mean().round(3))
    # persistence of each label (year-to-year autocorrelation) = how 'noisy' it is
    for c in ["label"] + ALT:
        p = c.replace("label", "prev_label")
        d = cv.dropna(subset=[c, p])
        d = d[d.event != "cant_plant"]
        if len(d):
            print(c, "n", len(d), "P(1|prev=1)", round(d[d[p] == 1][c].mean(), 3), "P(1|prev=0)", round(d[d[p] == 0][c].mean(), 3))
    r.to_parquet(OUT / "rows_alt.parquet", index=False)
