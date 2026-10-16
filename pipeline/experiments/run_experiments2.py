"""Second batch: ONI variants (interaction only, binned, linear-member only), combos.

    python pipeline/experiments/run_experiments2.py oni_south_only oni_lr_only ...
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = Path(os.environ.get("EXP_OUT", str(HERE)))   # artefacts (caches, OOF, results); HERE = code + small data
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import harness as H                       # noqa: E402
import harness_ext as HX                  # noqa: E402
import extra_features as X                # noqa: E402
import train as T                         # noqa: E402
from run_experiments import monotone_map, RESULTS, MODELS   # noqa: E402


def add_binned(rows):
    rows = rows.copy()
    rows["oni_bin"] = np.round(rows["oni"] * 2) / 2            # 0.5 degC bins
    rows["oni_x_south_bin"] = np.round(rows["oni_x_south"] * 2) / 2
    rows["enso_phase_south"] = np.sign(rows["oni_x_south"]) * (rows["oni_x_south"].abs() >= 0.5)  # -1/0/+1
    return rows


# spec keys: groups (extra feature groups joined), lr_extra / gb_extra (subset of the joined extra
# cols given to each member; None = all), mono, lgb, lr_C
EXPERIMENTS = {
    "oni_south_only": dict(groups=["oni"], lr_extra=["oni_x_south"], gb_extra=["oni_x_south"]),
    "oni_south_nolat": dict(groups=["oni"], lr_extra=["oni", "oni_d3", "oni_x_south"], gb_extra=["oni", "oni_d3", "oni_x_south"]),
    "oni_lr_only": dict(groups=["oni"], lr_extra=["oni", "oni_d3", "oni_x_south", "lat"], gb_extra=[]),
    "oni_south_lr_only": dict(groups=["oni"], lr_extra=["oni_x_south"], gb_extra=[]),
    "oni_binned": dict(groups=["oni"], binned=True, lr_extra=["oni_x_south"], gb_extra=["oni_x_south_bin"]),
    "oni_phase": dict(groups=["oni"], binned=True, lr_extra=["oni_x_south"], gb_extra=["enso_phase_south"]),
    "oni_south_mono": dict(groups=["oni"], lr_extra=["oni_x_south"], gb_extra=["oni_x_south"], mono=True,
                           mono_extra={"oni_x_south": 1}),
    "oni_lr_only_C1": dict(groups=["oni"], lr_extra=["oni", "oni_d3", "oni_x_south", "lat"], gb_extra=[], lr_C=1.0),
    "lr_C1": dict(groups=[], lr_C=1.0),
    "lr_C001": dict(groups=[], lr_C=0.01),
    "ens_w_lr70": dict(groups=[], weights=(0.7, 0.3)),
    # combos (fill after batch 1)
    "combo_oni_south_cum": dict(groups=["oni", "cum_rain"], lr_extra=["oni_x_south", "rain_cum_pct"],
                                gb_extra=["oni_x_south", "rain_cum_pct"]),
    "combo_oni_lr_cum": dict(groups=["oni", "cum_rain"], lr_extra=["oni", "oni_d3", "oni_x_south", "lat", "rain_cum_pct"],
                             gb_extra=["rain_cum_pct"]),
    "combo_oni_lr_cum_gated": dict(groups=["oni", "cum_rain", "spi_gated"],
                                   lr_extra=["oni", "oni_d3", "oni_x_south", "lat", "rain_cum_pct", "spi_1m_g", "spi_3m_g"],
                                   gb_extra=["rain_cum_pct", "spi_1m_g", "spi_3m_g"]),
    "combo_oni_south_cum_mono": dict(groups=["oni", "cum_rain"], lr_extra=["oni_x_south", "rain_cum_pct"],
                                     gb_extra=["oni_x_south", "rain_cum_pct"], mono=True, mono_extra={"oni_x_south": 1}),
}


def run(name, spec, rows, cols, base_tab):
    r, extra = X.with_extra(rows, spec.get("groups", [])) if spec.get("groups") else (rows, [])
    if spec.get("binned"):
        r = add_binned(r)
    lr_extra = spec.get("lr_extra"); gb_extra = spec.get("gb_extra")
    cols_lr = cols + (extra if lr_extra is None else lr_extra)
    cols_gb = cols + (extra if gb_extra is None else gb_extra)
    mono = None
    if spec.get("mono"):
        mono = monotone_map(cols_gb); mono.update(spec.get("mono_extra", {}))
    oof = HX.cv2(r, cols_lr, cols_gb, lgb_params=spec.get("lgb"), mono=mono, lr_C=spec.get("lr_C"),
                 weights=spec.get("weights", (0.5, 0.5)))
    oof.to_parquet(OUT / f"oof_{name}.parquet", index=False)
    tab = H.table(oof, models=MODELS)
    rec = {"name": name, "cols_lr": len(cols_lr), "cols_gb": len(cols_gb), "lr_extra": cols_lr[len(cols):], "gb_extra": cols_gb[len(cols):]}
    for m in MODELS:
        rec[m] = {"mean_pr_auc": tab[m]["mean_pr_auc"], "mean_brier": tab[m]["mean_brier"],
                  "d_pr_auc": round(tab[m]["mean_pr_auc"] - base_tab[m]["mean_pr_auc"], 4),
                  "d_brier": round(tab[m]["mean_brier"] - base_tab[m]["mean_brier"], 4),
                  "events": {ev: {"pr_auc": tab[m][ev]["pr_auc"], "brier": tab[m][ev]["brier"],
                                  "d_pr_auc": round(tab[m][ev]["pr_auc"] - base_tab[m][ev]["pr_auc"], 4)} for ev in T.EVENTS}}
    for iso in ("ZWE", "KEN"):
        ti = H.table(oof, models=MODELS, iso3=iso)
        rec[f"{iso}_ensemble"] = {"mean_pr_auc": ti["ensemble"]["mean_pr_auc"], "mean_brier": ti["ensemble"]["mean_brier"]}
    with open(RESULTS, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    for m in MODELS:
        print(H.summary(name, tab, base_tab, model=m), flush=True)


def main():
    names = [a for a in sys.argv[1:] if not a.startswith("--")] or list(EXPERIMENTS)
    rows, cols = H.load()
    base_tab = json.loads((OUT / "cv_baseline.json").read_text())
    for n in names:
        run(n, EXPERIMENTS[n], rows, cols, base_tab)


if __name__ == "__main__":
    main()
