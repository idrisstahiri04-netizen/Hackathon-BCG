"""TimesFM VCI forecasts as features / ensemble member (ZWE only, origins 2015-01..2024-06).

For a target row (unit, event, W0, lead L, r = W0 - L) we use only forecasts with origin_month == r
(strictly before every window month for L >= 1; for L = 0 the forecast covers W0+1..W0+3).
Features:
  tfm_min_<sig>     min forecast over window months W0..W0+len-1 that fall in r+1..r+3
  tfm_lead_<sig>    forecast for the first window month (W0) when L in 1..3
  tfm_q10_min_<sig> same as tfm_min but on the q10 quantile (pessimistic)
Only the window's signal matters (crop_failure -> vci_crop; no_grass -> vci_grass; cant_plant -> both).

Evaluation is restricted to the ZWE rows with agyear 2015-2022 (where the feature exists), comparing
the baseline model (trained on all rows, same folds) vs the model with TimesFM features, both scored
on that subset. Also an "ensemble member": p_tfm = isotonic(min forecast) cross-fitted, averaged with
the baseline calibrated p.

    python pipeline/experiments/timesfm_feat.py
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
import harness as H                                                  # noqa: E402
import train as T                                                    # noqa: E402
from common import WINDOW_LEN                                        # noqa: E402

TFM = HERE.parent / "out" / "timesfm_ZWE.parquet"
MODELS = ("logreg", "lgbm", "ensemble")


def tfm_features(rows: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    fc = pd.read_parquet(TFM)
    fc["origin_month"] = pd.to_datetime(fc["origin_month"]); fc["target_month"] = pd.to_datetime(fc["target_month"])
    rows = rows.copy()
    rows["_i"] = np.arange(len(rows))
    cols = []
    for sig in ("vci_crop", "vci_grass"):
        f = fc[fc.signal == sig]
        # explode each row into its window months, keep those within r+1..r+3
        parts = []
        for e, n in WINDOW_LEN.items():
            sub = rows[rows.event == e][["_i", "unit_id", "r", "W0"]]
            for k in range(n):
                p = sub.copy(); p["target_month"] = p["W0"] + pd.DateOffset(months=k)
                parts.append(p)
        ex = pd.concat(parts, ignore_index=True)
        ex = ex[(ex.target_month > ex.r) & (ex.target_month <= ex.r + pd.DateOffset(months=3))]
        m = ex.merge(f[["unit_id", "origin_month", "target_month", "forecast", "q10"]],
                     left_on=["unit_id", "r", "target_month"], right_on=["unit_id", "origin_month", "target_month"], how="inner")
        agg = m.groupby("_i").agg(mn=("forecast", "min"), q10=("q10", "min"))
        first = m[m.target_month == m.W0].set_index("_i")["forecast"]
        rows[f"tfm_min_{sig}"] = agg["mn"].reindex(rows["_i"]).values
        rows[f"tfm_q10_min_{sig}"] = agg["q10"].reindex(rows["_i"]).values
        rows[f"tfm_lead_{sig}"] = first.reindex(rows["_i"]).values
        cols += [f"tfm_min_{sig}", f"tfm_q10_min_{sig}", f"tfm_lead_{sig}"]
    # event-specific "the forecast that matters"
    ev_sig = rows.event.map({"crop_failure": "vci_crop", "no_grass": "vci_grass", "cant_plant": "vci_crop"})
    rows["tfm_min_event"] = np.where(ev_sig == "vci_crop", rows["tfm_min_vci_crop"], rows["tfm_min_vci_grass"])
    cols.append("tfm_min_event")
    return rows.drop(columns=["_i"]), cols


def subset_table(oof, mask_fn):
    o = oof[mask_fn(oof)]
    return H.table(o, models=MODELS)


def main():
    rows, cols = H.load()
    r2, tcols = tfm_features(rows)
    have = r2["tfm_min_event"].notna()
    print("rows with TimesFM feature:", int(have.sum()), "of", len(r2),
          "| by iso3:", r2.loc[have, "iso3"].value_counts().to_dict(),
          "| agyear range:", int(r2.loc[have, "agyear"].min()), int(r2.loc[have, "agyear"].max()))
    # correlation sanity: forecast vs label on CV rows
    cvm = ~r2.test & r2.agyear.between(2015, 2022) & have
    for ev in T.EVENTS:
        s = r2[cvm & (r2.event == ev) & r2.lead.isin([1, 2, 3])]
        from sklearn.metrics import roc_auc_score, average_precision_score
        if s.label.nunique() == 2:
            print(f"  {ev}: n={len(s)} AUC(-tfm_min_event)={roc_auc_score(s.label, -s.tfm_min_event):.3f} "
                  f"PR={average_precision_score(s.label, -s.tfm_min_event):.3f} base={s.label.mean():.3f}")
    base_oof = pd.read_parquet(OUT / "oof_baseline.parquet")
    sub = lambda o: (o.iso3 == "ZWE") & o.agyear.between(2015, 2022)
    base_tab = subset_table(base_oof, sub)
    oof = H.cv(r2, cols + tcols, models=MODELS)
    oof.to_parquet(OUT / "oof_timesfm_feat.parquet", index=False)
    tab = subset_table(oof, sub)
    # ensemble member: isotonic on -tfm_min_event, cross-fitted by fold, averaged with baseline cal_ensemble
    b = base_oof[sub(base_oof) & base_oof.lead.isin([1, 2, 3])].merge(
        r2[["unit_id", "event", "W0", "lead", "tfm_min_event"]], on=["unit_id", "event", "W0", "lead"], how="left")
    rec = {"subset": "ZWE agyear 2015-2022, leads 1-3", "n_rows": int(len(b))}
    for m in MODELS:
        rec[m] = {"base_pr": base_tab[m]["mean_pr_auc"], "feat_pr": tab[m]["mean_pr_auc"],
                  "d_pr": round(tab[m]["mean_pr_auc"] - base_tab[m]["mean_pr_auc"], 4),
                  "base_brier": base_tab[m]["mean_brier"], "feat_brier": tab[m]["mean_brier"],
                  "d_brier": round(tab[m]["mean_brier"] - base_tab[m]["mean_brier"], 4),
                  "events": {ev: {"base_pr": base_tab[m][ev]["pr_auc"], "feat_pr": tab[m][ev]["pr_auc"]} for ev in T.EVENTS}}
    # ensemble member
    from sklearn.metrics import brier_score_loss, average_precision_score
    out_ev = {}
    for ev in T.EVENTS:
        d = b[(b.event == ev)].dropna(subset=["tfm_min_event", "cal_ensemble"]).copy()
        p_t = np.full(len(d), np.nan)
        for yv in d.agyear.unique():
            te = (d.agyear == yv).values
            ir = T.iso(-d.tfm_min_event.values[~te], d.label.values[~te])
            p_t[te] = ir.predict(-d.tfm_min_event.values[te])
        p_mix = 0.5 * (p_t + d.cal_ensemble.values)
        out_ev[ev] = {"n": int(len(d)), "base_pr": round(average_precision_score(d.label, d.cal_ensemble), 4),
                      "tfm_only_pr": round(average_precision_score(d.label, p_t), 4),
                      "mix_pr": round(average_precision_score(d.label, p_mix), 4),
                      "base_brier": round(brier_score_loss(d.label, d.cal_ensemble), 4),
                      "tfm_only_brier": round(brier_score_loss(d.label, p_t), 4),
                      "mix_brier": round(brier_score_loss(d.label, p_mix), 4)}
    rec["ensemble_member"] = out_ev
    (OUT / "timesfm_feat_result.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec, indent=1))


if __name__ == "__main__":
    main()
