"""FEWS-proxy crisis probability for months the eo_fews IPC model cannot score (FEWS NET feed missing).

ML-expert fallback (docs/experts/ml.md, pipeline/experts/ml/xml_fews_proxy.py): an EO + NMME + ONI model whose
target is "FEWS NET projects IPC3+ for t+1..t+3". Here it is fitted once on every issue month up to LAST_FIT
(all past data; nothing after LAST_FIT is used) and scored on the live issue months after LAST_FIT, which have
no FEWS inputs and no eo_fews output. In-sample-free by construction: live months are strictly after training.

    python pipeline/ipc_model/proxy_live.py [--iso3 ZWE KEN MWI] [--last-issue 2026-09-01]
Output: pipeline/out/ipc_proxy_live.parquet (iso3, unit_id, month, p_proxy)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PIPE = HERE.parent
for p in (str(HERE), str(PIPE)):
    if p not in sys.path:
        sys.path.insert(0, p)
import ipc_data as D          # noqa: E402
import train_ipc as T         # noqa: E402


class Proxy:
    """Same as pipeline/experts/ml/xml_fews_proxy.Proxy: mean of logreg and LightGBM raw probabilities."""

    def __init__(self, cols):
        self.cols = cols

    def fit(self, d, yp):
        self.lr = T.LogReg(self.cols).fit(d, yp)
        self.gb = T.LGBM(self.cols).fit(d, yp)
        return self

    def raw(self, d):
        return 0.5 * (self.lr.raw(d) + self.gb.raw(d))

LAST_FIT = "2024-12-01"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso3", nargs="+", default=["ZWE", "KEN", "MWI"])
    ap.add_argument("--last-issue", default="2026-09-01")
    ap.add_argument("--out", default=str(PIPE / "out" / "ipc_proxy_live.parquet"))
    a = ap.parse_args()
    D.LAST_ISSUE = a.last_issue                       # build rows through the live month
    parts = []
    for iso in a.iso3:
        df, _ = D.build_country(iso)
        parts.append(df)
    rows = pd.concat(parts, ignore_index=True)
    rows["month"] = pd.to_datetime(rows["month"])
    eo = T.feature_sets(rows)["eo"]
    yp = np.where(rows["fews_h13"].notna(), (rows["fews_h13"] >= 3).astype(float), np.nan)
    fit = (rows["month"] <= pd.Timestamp(LAST_FIT)).values & ~np.isnan(yp)
    live = (rows["month"] > pd.Timestamp(LAST_FIT)).values
    print(f"fit rows {fit.sum()} (target rate {np.nanmean(yp[fit]):.3f}); live rows {live.sum()}")
    m = Proxy(eo).fit(rows[fit], yp[fit].astype(int))
    out = rows.loc[live, ["iso3", "unit_id", "month"]].copy()
    out["p_proxy"] = m.raw(rows[live])
    y6 = np.where(rows["fews_h46"].notna(), (rows["fews_h46"] >= 3).astype(float), np.nan)   # lead 4-6 variant
    fit6 = (rows["month"] <= pd.Timestamp(LAST_FIT)).values & ~np.isnan(y6)
    out["p_proxy_h46"] = Proxy(eo).fit(rows[fit6], y6[fit6].astype(int)).raw(rows[live])
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(a.out, index=False)
    print(out.groupby("iso3").p_proxy.describe().round(3))


if __name__ == "__main__":
    main()
