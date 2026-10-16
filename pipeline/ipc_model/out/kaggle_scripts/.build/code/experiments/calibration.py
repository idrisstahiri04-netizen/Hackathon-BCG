"""Calibration method comparison on the baseline OOF raw scores (no refits).

Cross-fitted exactly like train.py: fold k's calibrator is fitted on all other folds' raw OOF scores.
Methods: isotonic (current), Platt (logistic on logit of raw), beta calibration (logistic on
log(p), -log(1-p)), none (raw score as probability), isotonic + shrink toward pooled base rate.
Metric: Brier (leads 1-3) per event; PR-AUC is unchanged by monotone calibration except isotonic ties.

    python pipeline/experiments/calibration.py [oof parquet] [model]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, average_precision_score

HERE = Path(__file__).resolve().parent
OUT = Path(os.environ.get("EXP_OUT", str(HERE)))   # artefacts (caches, OOF, results); HERE = code + small data
OUT.mkdir(parents=True, exist_ok=True)
EVENTS = ["cant_plant", "crop_failure", "no_grass"]
EPS = 1e-4


def _logit(p):
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def fit_predict(method, x_tr, y_tr, x_te):
    if method == "none":
        return np.clip(x_te, 0, 1)
    if method == "isotonic":
        ir = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(x_tr, y_tr)
        return ir.predict(x_te)
    if method == "platt":
        lr = LogisticRegression(C=1e6, max_iter=1000).fit(_logit(x_tr)[:, None], y_tr)
        return lr.predict_proba(_logit(x_te)[:, None])[:, 1]
    if method == "beta":
        f = lambda p: np.c_[np.log(np.clip(p, EPS, 1)), -np.log(np.clip(1 - p, EPS, 1))]
        lr = LogisticRegression(C=1e6, max_iter=1000).fit(f(x_tr), y_tr)
        return lr.predict_proba(f(x_te))[:, 1]
    if method == "iso_lead":          # isotonic per lead (calibrates each horizon separately)
        raise RuntimeError("handled in caller")
    raise ValueError(method)


def crossfit(d: pd.DataFrame, raw: str, method: str, by_lead=False) -> np.ndarray:
    out = np.full(len(d), np.nan)
    x, y, f = d[raw].values, d["label"].values.astype(int), d["agyear"].values
    L = d["lead"].values
    for yv in np.unique(f):
        te = f == yv
        tr = ~te & ~np.isnan(x)
        if by_lead:
            for ld in np.unique(L):
                tt, rr = te & (L == ld), tr & (L == ld)
                out[tt] = fit_predict(method, x[rr], y[rr], x[tt])
        else:
            out[te] = fit_predict(method, x[tr], y[tr], x[te])
    return out


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT / "oof_baseline.parquet"
    model = sys.argv[2] if len(sys.argv) > 2 else "ensemble"
    oof = pd.read_parquet(path)
    rows = []
    for ev in EVENTS:
        d = oof[(oof.event == ev)].dropna(subset=[f"raw_{model}", "label"]).copy()
        ev_mask = d.lead.isin([1, 2, 3]).values
        for method, by_lead in [("none", False), ("isotonic", False), ("platt", False), ("beta", False),
                                ("isotonic", True), ("platt", True)]:
            p = crossfit(d, f"raw_{model}", method, by_lead)
            y = d.label.values[ev_mask]
            pm = p[ev_mask]
            rows.append(dict(event=ev, method=method + ("_by_lead" if by_lead else ""),
                             brier=round(brier_score_loss(y, pm), 4),
                             pr_auc=round(average_precision_score(y, pm), 4),
                             mean_p=round(float(pm.mean()), 3), base=round(float(y.mean()), 3),
                             p_gt_05=round(float((pm >= 0.5).mean()), 3)))
    res = pd.DataFrame(rows)
    piv = res.pivot(index="method", columns="event", values="brier")
    piv["mean"] = piv.mean(axis=1).round(4)
    print(f"== Brier by calibration method ({model}, leads 1-3, cross-fitted by agyear fold)")
    print(piv.sort_values("mean").to_string())
    print("\n== detail")
    print(res.to_string(index=False))
    res.to_csv(OUT / f"calibration_{model}.csv", index=False)


if __name__ == "__main__":
    main()
