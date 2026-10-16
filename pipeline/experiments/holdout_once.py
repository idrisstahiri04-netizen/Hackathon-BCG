"""Once-only hold-out evaluation of ONE configuration chosen by CV (never iterate on this).

    python pipeline/experiments/holdout_once.py <experiment-name-from-run_experiments3> [--extra]

The configuration is fitted on all CV rows (agyear 2001-2022, not test; plus extra countries if the
experiment pools them), calibrated with isotonic regression on its own CV OOF (oof_<name>.parquet must
exist), then scored on the hold-out rows (agyear >= 2023 and KEN 2020-22) exactly like train.py's final
models. Also scores the baseline configuration the same way for a side-by-side. Writes
holdout_<name>.json and holdout_<name>.parquet. Metrics: leads 1-3, pooled and per country.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = Path(os.environ.get("EXP_OUT", str(HERE)))
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import harness as H                         # noqa: E402
import harness_ext as HX                    # noqa: E402
import extra_features as X                  # noqa: E402
import train as T                           # noqa: E402
from run_experiments3 import EXPERIMENTS, load_extra, monotone_map   # noqa: E402

MODELS = ("logreg", "lgbm", "ensemble")


def fit_score(rows, spec, cols, name):
    label = spec.get("label", "label")
    events = spec.get("events", T.EVENTS)
    r, extra = X.with_extra(rows, spec.get("groups", [])) if spec.get("groups") else (rows, [])
    cols_lr = cols + (extra if spec.get("lr_extra") is None else spec["lr_extra"])
    cols_gb = cols + (extra if spec.get("gb_extra") is None else spec["gb_extra"])
    mono = monotone_map(cols_gb) if spec.get("mono") else None
    train_leads = spec.get("train_leads", H.TRAIN_LEADS)
    ex = load_extra(spec, spec.get("groups", []))
    if label != "label":
        r["label"] = r[label]
    oof = pd.read_parquet(OUT / f"oof_{name}.parquet")
    cv = r[~r.test & r.agyear.between(2001, 2022) & r.lead.isin(train_leads)].dropna(subset=["label"])
    te = r[r.test & r.lead.isin([1, 2, 3])].dropna(subset=["label"]).copy()
    parts = []
    for ev in events:
        d = cv[cv.event == ev]
        if ex is not None:
            e = ex[(ex.event == ev) & ex.agyear.between(2001, 2022) & ex.lead.isin(train_leads)].copy()
            if label != "label":
                e["label"] = e[label]
            d = pd.concat([d, e.dropna(subset=["label"])], ignore_index=True)
        ms = HX._fit2(d, cols_lr, cols_gb, spec.get("lgb"), mono, spec.get("lr_C"))
        o = oof[(oof.event == ev) & oof.lead.isin([1, 2, 3])]
        s = te[te.event == ev].copy()
        w = spec.get("weights", (0.5, 0.5))
        raw = {"logreg": ms["logreg"].raw(s), "lgbm": ms["lgbm"].raw(s)}
        raw["ensemble"] = w[0] * raw["logreg"] + w[1] * raw["lgbm"]
        for m in MODELS:
            ok = ~np.isnan(o[f"raw_{m}"].values)
            cal = T.iso(o[f"raw_{m}"].values[ok], o["label"].values[ok])
            s[f"raw_{m}"] = raw[m]; s[f"cal_{m}"] = cal.predict(raw[m])
        parts.append(s)
    return pd.concat(parts, ignore_index=True), events


def tables(ho, events, iso3s=("ZWE", "KEN", "MWI", "ZMB")):
    def tab(df):
        out = {}
        for m in MODELS:
            out[m] = {}
            for ev in events:
                x = df[df.event == ev]
                mt = T.metrics(x.label, x[f"cal_{m}"]); mr = T.metrics(x.label, x[f"raw_{m}"], brier=False)
                mt["roc_auc"], mt["pr_auc"] = mr["roc_auc"], mr["pr_auc"]
                out[m][ev] = mt
        return out
    res = {"all": tab(ho)}
    for i in iso3s:
        if (ho.iso3 == i).any():
            res[i] = tab(ho[ho.iso3 == i])
    return res


def main():
    name = sys.argv[1]
    spec = EXPERIMENTS[name]
    rows, cols = H.load()
    if spec.get("label", "label") != "label":
        rows = pd.read_parquet(OUT / "rows_alt.parquet")
    ho, events = fit_score(rows, spec, cols, name)
    ho.to_parquet(OUT / f"holdout_{name}.parquet", index=False)
    res = {"experiment": name, "spec": {k: (list(v) if isinstance(v, tuple) else v) for k, v in spec.items()},
           "note": "hold-out scored once with the CV-chosen configuration; never used for tuning", "metrics": tables(ho, events)}
    if (OUT / "oof_baseline.parquet").exists() and name != "baseline":
        base_spec = {"groups": []}
        EXPERIMENTS["baseline"] = base_spec
        hb, _ = fit_score(rows, base_spec, cols, "baseline")
        res["baseline_metrics"] = tables(hb, events)
    (OUT / f"holdout_{name}.json").write_text(json.dumps(res, indent=1, default=str))
    for k, t in res["metrics"].items():
        line = f"{name} hold-out {k}: " + " ".join(
            f"{ev[:4]} ens ROC/PR/Brier {t['ensemble'][ev]['roc_auc']}/{t['ensemble'][ev]['pr_auc']}/{t['ensemble'][ev]['brier']} (b{t['ensemble'][ev]['pos_rate']})"
            for ev in events)
        if "baseline_metrics" in res and k in res["baseline_metrics"]:
            b = res["baseline_metrics"][k]
            line += " | baseline " + " ".join(f"{ev[:4]} {b['ensemble'][ev]['roc_auc']}/{b['ensemble'][ev]['pr_auc']}/{b['ensemble'][ev]['brier']}" for ev in events)
        print(line, flush=True)


if __name__ == "__main__":
    main()
