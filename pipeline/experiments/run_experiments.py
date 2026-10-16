"""Run one or more named experiments against the baseline CV (same folds, calibration, metrics).

    python pipeline/experiments/run_experiments.py feat_cum_rain feat_oni mono ...
    python pipeline/experiments/run_experiments.py --list

Each experiment writes oof_<name>.parquet and appends a row to results.jsonl (mean PR-AUC / Brier
over the 3 events, leads 1-3, plus per-event detail and per-country ZWE/KEN deltas).
Hold-out rows are never touched.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import harness as H                      # noqa: E402
import extra_features as X               # noqa: E402
import train as T                        # noqa: E402

RESULTS = HERE / "results.jsonl"
MODELS = ("logreg", "lgbm", "ensemble")


def monotone_map(cols: list) -> dict:
    """drier/browner -> riskier. Negative constraint = higher value lowers risk."""
    neg_roots = ["spi_1m", "spi_3m", "spi_6m", "ndvi_z_crop", "ndvi_z_grass", "vci_crop", "vci_grass",
                 "sm1_z", "sm2_z", "rain_pct3", "rain_cum_pct", "spi_1m_g", "spi_3m_g"]
    mono = {}
    for c in cols:
        root = c
        for suf in ("_l1", "_l2", "_l3", "_tr3", "_d1"):
            if c.endswith(suf):
                root = c[: -len(suf)]
        if root in neg_roots:
            mono[c] = -1
        elif root in ("t2m_z", "dry_months"):
            mono[c] = 1
    return mono


def _lgb(**kw):
    p = dict(T.LGB_PARAMS)
    p.update(kw)
    return p


EXPERIMENTS = {
    # ---- 1. features
    "feat_cum_rain": dict(groups=["cum_rain"]),
    "feat_dry_spell": dict(groups=["dry_spell"]),
    "feat_ndvi_slope": dict(groups=["ndvi_slope"]),
    "feat_soil_grad": dict(groups=["soil_grad"]),
    "feat_spi_gated": dict(groups=["spi_gated"]),
    "feat_phase_x": dict(groups=["phase_x"]),
    "feat_precip_all": dict(groups=["cum_rain", "dry_spell", "spi_gated"]),
    # ---- 3. ENSO
    "feat_oni": dict(groups=["oni"]),
    "feat_oni_plain": dict(groups=["oni_plain"]),
    "feat_lat_only": dict(groups=["lat"]),
    "feat_oni_lag0": dict(groups=["oni_lag0", "lat"]),
    # ---- 4. model variants
    "mono": dict(groups=[], mono=True),
    "per_country": dict(groups=[], group_fn=lambda d: d["iso3"]),
    "lgb_bigger": dict(groups=[], lgb=_lgb(num_leaves=31, max_depth=-1, min_child_samples=40)),
    "lgb_slower": dict(groups=[], lgb=_lgb(learning_rate=0.02)),
    "lgb_reg": dict(groups=[], lgb=_lgb(lambda_l2=20.0, min_child_samples=120, feature_fraction=0.5)),
    "lgb_unbalanced_off": dict(groups=[]),   # placeholder: identical to baseline (sanity for seed noise)
    # ---- combos (filled after singles are known)
}


def run(name: str, spec: dict, rows: pd.DataFrame, cols: list, base_tab: dict) -> dict:
    r, extra = X.with_extra(rows, spec.get("groups", [])) if spec.get("groups") else (rows, [])
    c = cols + extra
    mono = monotone_map(c) if spec.get("mono") else None
    oof = H.cv(r, c, models=MODELS, lgb_params=spec.get("lgb"), mono=mono, group_fn=spec.get("group_fn"))
    oof.to_parquet(HERE / f"oof_{name}.parquet", index=False)
    tab = H.table(oof, models=MODELS)
    rec = {"name": name, "n_cols": len(c), "extra": extra}
    for m in MODELS:
        rec[m] = {"mean_pr_auc": tab[m]["mean_pr_auc"], "mean_brier": tab[m]["mean_brier"],
                  "d_pr_auc": round(tab[m]["mean_pr_auc"] - base_tab[m]["mean_pr_auc"], 4),
                  "d_brier": round(tab[m]["mean_brier"] - base_tab[m]["mean_brier"], 4),
                  "events": {ev: {"pr_auc": tab[m][ev]["pr_auc"], "brier": tab[m][ev]["brier"],
                                  "d_pr_auc": round(tab[m][ev]["pr_auc"] - base_tab[m][ev]["pr_auc"], 4)}
                             for ev in T.EVENTS}}
    for iso in ("ZWE", "KEN"):
        ti = H.table(oof, models=MODELS, iso3=iso)
        rec[f"{iso}_ensemble"] = {"mean_pr_auc": ti["ensemble"]["mean_pr_auc"], "mean_brier": ti["ensemble"]["mean_brier"]}
    with open(RESULTS, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    for m in MODELS:
        print(H.summary(name, tab, base_tab, model=m), flush=True)
    return rec


def main():
    if "--list" in sys.argv:
        print("\n".join(EXPERIMENTS)); return
    names = [a for a in sys.argv[1:] if not a.startswith("--")] or list(EXPERIMENTS)
    rows, cols = H.load()
    base_tab = json.loads((HERE / "cv_baseline.json").read_text())
    for n in names:
        run(n, EXPERIMENTS[n], rows, cols, base_tab)


if __name__ == "__main__":
    main()
