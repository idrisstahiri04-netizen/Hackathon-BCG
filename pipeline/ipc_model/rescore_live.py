"""Score live issue months (after the IPC model's last month) with the eo_fews LightGBM where real FEWS NET inputs exist.

No retraining of the published model: same features/params as train_ipc.py, fitted once on issue months <= LAST_FIT
(past data only), raw score mapped to probability by the isotonic fit of the existing OOF+hold-out eo_fews:lgbm scores.
Months without FEWS inputs (fdw_ml1 missing) are left to the proxy (ipc_proxy_live.parquet).
    python pipeline/ipc_model/rescore_live.py [--iso3 ZWE KEN MWI] [--last-issue 2026-09-01]
Output: pipeline/out/ipc_eofews_live.parquet (iso3, unit_id, month, p_eofews, st_phase)
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

LAST_FIT = "2024-12-01"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso3", nargs="+", default=["ZWE", "KEN", "MWI"])
    ap.add_argument("--last-issue", default="2026-09-01")
    a = ap.parse_args()
    D.LAST_ISSUE = a.last_issue
    rows = pd.concat([D.build_country(i)[0] for i in a.iso3], ignore_index=True)
    rows["month"] = pd.to_datetime(rows["month"])
    cols = T.feature_sets(rows)["eo_fews"]
    y = rows["y_h13"].values
    fit = (rows.month <= pd.Timestamp(LAST_FIT)).values & ~np.isnan(y)
    m = T.LGBM(cols).fit(rows[fit], y[fit].astype(int))
    o = pd.concat([pd.read_parquet(HERE / "out" / f"{n}_h13.parquet") for n in ("oof", "holdout")])
    o = o.dropna(subset=["raw_eo_fews:lgbm", "y_h13", "st_phase"])
    iso = T.iso_fit(o["raw_eo_fews:lgbm"].values, o["y_h13"].values)
    live = (rows.month > pd.Timestamp(LAST_FIT)).values & rows.fdw_ml1.notna().values
    out = rows.loc[live, ["iso3", "unit_id", "month", "st_phase"]].copy()
    out["p_eofews"] = iso.predict(m.raw(rows[live]))
    out.to_parquet(PIPE / "out" / "ipc_eofews_live.parquet", index=False)
    print(len(out), "live rows"); print(out.groupby("iso3").p_eofews.describe().round(3))
    print(out.groupby("iso3").month.agg(["min", "max"]))


if __name__ == "__main__":
    main()
