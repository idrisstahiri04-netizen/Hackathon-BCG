"""Latency-era experiments (rows built with common.apply_latency, leads 0-6 available).

    python pipeline/experiments/run_experiments3.py <name> [<name> ...]
    python pipeline/experiments/run_experiments3.py --list

Every experiment: same leave-one-agyear-out folds as train.py, cross-fitted isotonic calibration,
metrics on leads 1-3 (or 1-6 for the long-lead runs), hold-out rows never used.
Results appended to results.jsonl; per-experiment OOF in oof_<name>.parquet.
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
import harness as H                        # noqa: E402
import harness_ext as HX                   # noqa: E402
import extra_features as X                 # noqa: E402
import train as T                          # noqa: E402
from run_experiments import monotone_map   # noqa: E402

RESULTS = OUT / "results.jsonl"
MODELS = ("logreg", "lgbm", "ensemble")
EV2 = ["crop_failure", "no_grass"]          # the events the main model keeps
ONI_LR = ["oni", "oni_d3", "oni_x_south", "lat"]
GROUPS_SFC = ["sfc_z_m13", "sfc_pbn_m13", "sfc_z_m46", "sfc_pbn_m46"]

EXPERIMENTS = {
    # ---- ENSO / climate indices (feature only in the linear member unless gb_extra says otherwise)
    "oni_lr_only": dict(groups=["oni"], lr_extra=ONI_LR, gb_extra=[]),
    "oni_both": dict(groups=["oni"], lr_extra=ONI_LR, gb_extra=ONI_LR),
    "oni_south_only": dict(groups=["oni"], lr_extra=["oni_x_south"], gb_extra=["oni_x_south"]),
    "oni_south_lr_only": dict(groups=["oni"], lr_extra=["oni_x_south"], gb_extra=[]),
    "oni_lag0_lr_only": dict(groups=["oni_lag0", "lat"], lr_extra=["oni_lag0", "oni_d3_lag0", "oni_x_south_lag0", "lat"], gb_extra=[]),
    "nino34_lr_only": dict(groups=["nino34", "lat"], lr_extra=["nino34", "nino34_3m", "nino34_x_south", "lat"], gb_extra=[]),
    "nino34_both": dict(groups=["nino34", "lat"], lr_extra=["nino34", "nino34_3m", "nino34_x_south", "lat"],
                        gb_extra=["nino34", "nino34_3m", "nino34_x_south", "lat"]),
    "oni_dmi_lr_only": dict(groups=["oni", "dmi"], lr_extra=ONI_LR + ["dmi", "dmi_3m", "dmi_x_east"], gb_extra=[]),
    "oni_dmi_both": dict(groups=["oni", "dmi"], lr_extra=ONI_LR + ["dmi", "dmi_3m", "dmi_x_east"],
                         gb_extra=["oni_x_south", "dmi_x_east"]),
    # ---- NMME seasonal rainfall forecast (issued in month r)
    "sfc_both": dict(groups=["seasonal_fc"]),
    "sfc_lr_only": dict(groups=["seasonal_fc"], gb_extra=[]),
    "sfc_m13_both": dict(groups=["seasonal_fc_m13"]),
    "combo_oni_sfc": dict(groups=["oni", "seasonal_fc"], lr_extra=ONI_LR + GROUPS_SFC, gb_extra=["oni_x_south"] + GROUPS_SFC),
    "combo_oni_sfc_lr": dict(groups=["oni", "seasonal_fc"], lr_extra=ONI_LR + GROUPS_SFC, gb_extra=[]),
    "combo_oni_sfc_cum": dict(groups=["oni", "seasonal_fc", "cum_rain"], lr_extra=ONI_LR + GROUPS_SFC + ["rain_cum_pct"],
                              gb_extra=["oni_x_south"] + GROUPS_SFC + ["rain_cum_pct"]),
    "pool_oni_sfc": dict(groups=["oni", "seasonal_fc"], lr_extra=ONI_LR + GROUPS_SFC, gb_extra=["oni_x_south"] + GROUPS_SFC, extra=True),
    "long_oni_sfc": dict(groups=["oni", "seasonal_fc"], lr_extra=ONI_LR + GROUPS_SFC, gb_extra=["oni_x_south"] + GROUPS_SFC,
                         train_leads=tuple(range(7)), eval_leads=(1, 2, 3, 4, 5, 6)),
    # ---- season-cumulative features
    "cum_rain": dict(groups=["cum_rain"]),
    "dry_spell": dict(groups=["dry_spell"]),
    "cum_dry_gated": dict(groups=["cum_rain", "dry_spell", "spi_gated"]),
    "ndvi_slope": dict(groups=["ndvi_slope"]),
    "phase_x": dict(groups=["phase_x"]),
    # ---- model variants
    "mono": dict(groups=[], mono=True),
    "lr_C1": dict(groups=[], lr_C=1.0),
    "ens_w_lr70": dict(groups=[], weights=(0.7, 0.3)),
    # ---- combos
    "combo_oni_lr_cum": dict(groups=["oni", "cum_rain"], lr_extra=ONI_LR + ["rain_cum_pct"], gb_extra=["rain_cum_pct"]),
    "combo_oni_dmi_lr_cum": dict(groups=["oni", "dmi", "cum_rain"], lr_extra=ONI_LR + ["dmi", "dmi_3m", "dmi_x_east", "rain_cum_pct"],
                                 gb_extra=["rain_cum_pct"]),
    "combo_oni_lr_cum_mono": dict(groups=["oni", "cum_rain"], lr_extra=ONI_LR + ["rain_cum_pct"], gb_extra=["rain_cum_pct"], mono=True),
    # ---- long leads: train on leads 0-6, evaluate leads 1-6 (per-lead table)
    "long_base": dict(groups=[], train_leads=tuple(range(7)), eval_leads=(1, 2, 3, 4, 5, 6)),
    "long_oni_lr_only": dict(groups=["oni"], lr_extra=ONI_LR, gb_extra=[], train_leads=tuple(range(7)), eval_leads=(1, 2, 3, 4, 5, 6)),
    "long_oni_both": dict(groups=["oni"], lr_extra=ONI_LR, gb_extra=ONI_LR, train_leads=tuple(range(7)), eval_leads=(1, 2, 3, 4, 5, 6)),
    # ---- pooled training with extra countries (rows_extra.parquet from expand.py)
    "pool_base": dict(groups=[], extra=True),
    "pool_oni_lr_only": dict(groups=["oni"], lr_extra=ONI_LR, gb_extra=[], extra=True),
    "pool_oni_lr_cum": dict(groups=["oni", "cum_rain"], lr_extra=ONI_LR + ["rain_cum_pct"], gb_extra=["rain_cum_pct"], extra=True),
    "pool_lab_mean35_oni": dict(groups=["oni"], lr_extra=ONI_LR, gb_extra=[], label="label_mean35", events=EV2, extra=True),
    # ---- alternative labels (rows_alt.parquet), base model and base + ONI(lr)
    "lab_mean35": dict(groups=[], label="label_mean35", events=EV2),
    "lab_min20": dict(groups=[], label="label_min20", events=EV2),
    "lab_q20": dict(groups=[], label="label_q20", events=EV2),
    "lab_mean_q20": dict(groups=[], label="label_mean_q20", events=EV2),
    "lab_mean35_oni": dict(groups=["oni"], lr_extra=ONI_LR, gb_extra=[], label="label_mean35", events=EV2),
    "lab_q20_oni": dict(groups=["oni"], lr_extra=ONI_LR, gb_extra=[], label="label_q20", events=EV2),
    "lab_mean_q20_oni": dict(groups=["oni"], lr_extra=ONI_LR, gb_extra=[], label="label_mean_q20", events=EV2),
}


def persistence_rule(oof_rows: pd.DataFrame, label_col: str) -> dict:
    """PR-AUC/Brier of the persistence and rule baselines for a label column (leads 1-3)."""
    d = oof_rows[oof_rows.lead.isin([1, 2, 3])].dropna(subset=[label_col])
    prev = label_col.replace("label", "prev_label")
    out = {}
    for ev in d.event.unique():
        s = d[d.event == ev]
        y = s[label_col].values
        pers = s[prev].fillna(y.mean()).values if prev in s else np.full(len(s), y.mean())
        rule = s["agreeing"].values.astype(float)
        out[ev] = {"base_rate": round(float(y.mean()), 3),
                   "persistence_pr": round(float(T.average_precision_score(y, pers)), 3) if 0 < y.sum() < len(y) else None,
                   "rule_pr": round(float(T.average_precision_score(y, rule)), 3) if 0 < y.sum() < len(y) else None}
    return out


def load_extra(spec, groups):
    """Extra-country rows (rows_extra.parquet, built by expand.py) with the same extra features joined."""
    f = OUT / "rows_extra.parquet"
    if not spec.get("extra") or not f.exists():
        return None
    ex = pd.read_parquet(f)
    if spec.get("label", "label") != "label":
        import labels_alt
        ex = labels_alt.alt_labels(ex, wide_path=OUT / "wide_extra.parquet")
    if groups:
        ex, _ = X.with_extra(ex, groups, um_path=OUT / "extra_um_extra.parquet", wide_path=OUT / "wide_extra.parquet",
                             seasons_path=OUT / "seasons_extra.json")
    return ex


def run(name, spec, rows, cols, base_tab):
    label = spec.get("label", "label")
    events = spec.get("events", T.EVENTS)
    r, extra = X.with_extra(rows, spec.get("groups", [])) if spec.get("groups") else (rows, [])
    lr_extra = spec.get("lr_extra"); gb_extra = spec.get("gb_extra")
    cols_lr = cols + (extra if lr_extra is None else lr_extra)
    cols_gb = cols + (extra if gb_extra is None else gb_extra)
    mono = None
    if spec.get("mono"):
        mono = monotone_map(cols_gb)
    train_leads = spec.get("train_leads", H.TRAIN_LEADS)
    eval_leads = spec.get("eval_leads", (1, 2, 3))
    extra = load_extra(spec, spec.get("groups", []))
    if extra is not None:
        print(f"   + extra training rows: {len(extra)} from {sorted(extra.iso3.unique())}", flush=True)
    oof = HX.cv2(r, cols_lr, cols_gb, lgb_params=spec.get("lgb"), mono=mono, lr_C=spec.get("lr_C"),
                 weights=spec.get("weights", (0.5, 0.5)), train_leads=train_leads, label_col=label, events=events,
                 extra_train=extra)
    oof.to_parquet(OUT / f"oof_{name}.parquet", index=False)
    tab = H.table(oof, models=MODELS, leads=list(eval_leads))
    rec = {"name": name, "label": label, "events": list(events), "train_leads": list(train_leads), "eval_leads": list(eval_leads),
           "lr_extra": cols_lr[len(cols):], "gb_extra": cols_gb[len(cols):]}
    for m in MODELS:
        rec[m] = {"events": {}}
        for ev in events:
            rec[m]["events"][ev] = {"pr_auc": tab[m][ev]["pr_auc"], "roc_auc": tab[m][ev]["roc_auc"], "brier": tab[m][ev]["brier"],
                                    "base": tab[m][ev]["pos_rate"]}
            if label == "label" and ev in base_tab[m] and tuple(eval_leads) == (1, 2, 3):
                rec[m]["events"][ev]["d_pr_auc"] = round(tab[m][ev]["pr_auc"] - base_tab[m][ev]["pr_auc"], 4)
                rec[m]["events"][ev]["d_brier"] = round(tab[m][ev]["brier"] - base_tab[m][ev]["brier"], 4)
        # headline = mean over the two kept events
        pr = [tab[m][ev]["pr_auc"] for ev in EV2 if ev in events and tab[m][ev]["pr_auc"] is not None]
        br = [tab[m][ev]["brier"] for ev in EV2 if ev in events and tab[m][ev]["brier"] is not None]
        rec[m]["mean2_pr_auc"] = round(float(np.mean(pr)), 4); rec[m]["mean2_brier"] = round(float(np.mean(br)), 4)
        if label == "label" and tuple(eval_leads) == (1, 2, 3):
            bpr = np.mean([base_tab[m][ev]["pr_auc"] for ev in EV2]); bbr = np.mean([base_tab[m][ev]["brier"] for ev in EV2])
            rec[m]["d_mean2_pr_auc"] = round(rec[m]["mean2_pr_auc"] - bpr, 4); rec[m]["d_mean2_brier"] = round(rec[m]["mean2_brier"] - bbr, 4)
    # per-lead table for the winner-type model (ensemble) and per country
    rec["by_lead_ensemble"] = {}
    for L in eval_leads:
        tl = H.table(oof, models=("ensemble",), leads=[L])
        rec["by_lead_ensemble"][L] = {ev: {"pr_auc": tl["ensemble"][ev]["pr_auc"], "roc_auc": tl["ensemble"][ev]["roc_auc"],
                                           "brier": tl["ensemble"][ev]["brier"]} for ev in events}
    for iso in ("ZWE", "KEN", "MWI", "ZMB"):
        ti = H.table(oof, models=("ensemble",), leads=list(eval_leads), iso3=iso)
        rec[f"{iso}_ensemble"] = {ev: {"pr_auc": ti["ensemble"][ev]["pr_auc"], "roc_auc": ti["ensemble"][ev]["roc_auc"],
                                       "base": ti["ensemble"][ev]["pos_rate"]} for ev in events}
    if label != "label":
        rec["baselines"] = persistence_rule(r[~r.test & r.agyear.between(2001, 2022)], label)
    with open(RESULTS, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    for m in MODELS:
        line = f"{name:28s} {m:8s} mean2 PR {rec[m]['mean2_pr_auc']:.4f} Brier {rec[m]['mean2_brier']:.4f}"
        if "d_mean2_pr_auc" in rec[m]:
            line += f"  dPR {rec[m]['d_mean2_pr_auc']:+.4f} dBrier {rec[m]['d_mean2_brier']:+.4f}"
        line += " | " + " ".join(f"{ev[:4]} {rec[m]['events'][ev]['roc_auc']}/{rec[m]['events'][ev]['pr_auc']}/{rec[m]['events'][ev]['brier']}(b{rec[m]['events'][ev]['base']})" for ev in events)
        print(line, flush=True)
    if len(eval_leads) > 3:
        for L in eval_leads:
            print(f"   lead {L}: " + " ".join(f"{ev[:4]} {rec['by_lead_ensemble'][L][ev]['roc_auc']}/{rec['by_lead_ensemble'][L][ev]['pr_auc']}" for ev in events), flush=True)
    if label != "label":
        print("   baselines:", rec["baselines"], flush=True)


def main():
    if "--list" in sys.argv:
        print("\n".join(EXPERIMENTS)); return
    names = [a for a in sys.argv[1:] if not a.startswith("--")] or list(EXPERIMENTS)
    rows, cols = H.load()
    if any(EXPERIMENTS[n].get("label", "label") != "label" for n in names):
        alt = pd.read_parquet(OUT / "rows_alt.parquet")
        rows = alt
    base_tab = json.loads((OUT / "cv_baseline.json").read_text())
    for n in names:
        run(n, EXPERIMENTS[n], rows, cols, base_tab)


if __name__ == "__main__":
    main()
