"""v2 training for the IPC-target model: pooled over all countries with polygon-matched labels (ipc_data_v2.py).

Reuses train_ipc.py (models, LOSO CV with purge, cross-fitted isotonic calibration, metrics, thresholds,
hold-out, ZWE replay) and changes only:
  * feature sets:  eo (signals + NMME + ONI + statics), eo_p (eo + prices), eo_fews (eo + FDW ML1/ML2
    projections; the outlook-text ol_* features are dropped because they exist for ZWE/MWI only),
    eo_fews_p (eo_fews + prices), full (eo_fews_p + lagged IPC state)
  * ablations (h13, CV only): training on the v1 trio ZWE+KEN+MWI, and single-country training, each scored
    on the same transition rows as the pooled model -> "do more countries help?"
  * CV = leave-one-season-out 2015/16..2022/23 (KEN to 2019/20); hold-out = agyear >= 2023 (+ KEN 2020-22),
    scored once. Thresholds come from CV OOF only.
Usage: python pipeline/ipc_model/train_ipc_v2.py [--out pipeline/out/ipc_model_v2] [--cv-only] [--smoke]
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
import train_ipc as T  # noqa: E402
from common import OUT_DIR  # noqa: E402

V1_TRIO = ["ZWE", "KEN", "MWI"]


def feature_sets_v2(rows: pd.DataFrame) -> dict:
    cols = list(rows.columns)
    sig = cols[cols.index("spi_1m"): cols.index("grass_frac") + 1] + ["phase_m"]
    sfc = [c for c in cols if c.startswith("sfc_")]
    oni = ["oni", "oni_d3", "oni_x_south", "south"]
    price = [c for c in cols if c.startswith("price_")] + ["has_price"]
    fdw = ["fdw_ml1", "fdw_ml2", "fdw_ml1_share3", "fdw_age"]
    st = ["st_phase", "st_share3", "st_snap_age", "st_m_since3", "st_any3_12", "st_delta4"]
    eo = sig + sfc + oni
    return {"eo": eo, "eo_p": eo + price, "eo_fews": eo + fdw, "eo_fews_p": eo + fdw + price, "full": eo + fdw + price + st}


def transition_metrics_by_country(oof: pd.DataFrame, h: str, names: list) -> dict:
    y = oof[f"y_{h}"]
    m = (y.notna() & oof.st_phase.notna() & (oof.st_phase < 3)).values
    out = {}
    for g in ["ALL"] + sorted(oof.iso3.unique()):
        gm = m if g == "ALL" else m & (oof.iso3 == g).values
        out[g] = {n: T.metrics(y[gm], oof[f"raw_{n}"][gm]) for n in names}
    return out


def ablation(rows: pd.DataFrame, fsets: dict, h: str, oof_pooled: pd.DataFrame) -> dict:
    """Train on subsets (v1 trio / single country) and score on the same transition rows as the pooled model."""
    names = [f"{v}:lgbm" for v in fsets] + [f"{v}:logreg" for v in fsets]
    res = {"pooled": transition_metrics_by_country(oof_pooled, h, names)}
    subsets = {"trio_ZWE_KEN_MWI": V1_TRIO} | {f"only_{c}": [c] for c in sorted(rows.iso3.unique())}
    for tag, isos in subsets.items():
        sub = rows[rows.iso3.isin(isos)].reset_index(drop=True)
        if sub.empty or sub.loc[~sub.test, f"y_{h}"].sum() < 20:
            res[tag] = {"note": "too few positives"}
            continue
        print(f"== ablation {tag} ({len(sub)} rows)", flush=True)
        oof = T.run_cv(sub, fsets, h)
        res[tag] = transition_metrics_by_country(oof, h, names)
    return res


def md_ablation(ab: dict, fsets: dict) -> str:
    lines = ["### Ablation (h13, CV transition rows, ROC / PR-AUC): does pooling help?", ""]
    models = [f"{v}:lgbm" for v in fsets]
    lines.append("| train set | eval country | " + " | ".join(models) + " |")
    lines.append("|---|---|" + "---|" * len(models))
    for tag, by in ab.items():
        if "note" in by:
            lines.append(f"| {tag} | - | {by['note']} |")
            continue
        for g, mm in by.items():
            if g == "ALL" and tag.startswith("only_"):
                continue
            cells = []
            for n in models:
                r = mm.get(n)
                cells.append("-" if not r or r.get("roc") is None else f"{r['roc']:.3f} / {r['pr']:.3f} (n {r['n']}, base {r['base']})")
            lines.append(f"| {tag} | {g} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT_DIR / "ipc_model_v2"))
    ap.add_argument("--cv-only", action="store_true", help="no hold-out scoring (label sensitivity runs)")
    ap.add_argument("--no-ablation", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    rows = pd.read_parquet(out / "rows.parquet")
    rows["test"] = rows.test.astype(bool)
    if a.smoke:
        T.N_TREES = 20
    fsets = feature_sets_v2(rows)
    print("rows", rows.shape, "countries", rows.iso3.value_counts().to_dict(), "variants", {k: len(v) for k, v in fsets.items()}, flush=True)
    res = {"n_rows": int(len(rows)), "countries": sorted(rows.iso3.unique()), "rows_by_country": rows.iso3.value_counts().to_dict(),
           "variants": fsets, "cv_seasons": sorted(rows.loc[~rows.test, "season"].unique()), "lgb": {**T.LGB_PARAMS, "n_trees": T.N_TREES},
           "label_base_rates": {c: {"y_h13": round(float(g.y_h13.mean()), 3), "transition_h13": round(float(g.loc[g.st_phase < 3, "y_h13"].mean()), 3) if (g.st_phase < 3).any() else None,
                                    "rows_known_state": int(g.st_phase.notna().sum())} for c, g in rows.groupby("iso3")}}
    md = ["# IPC-target model v2: auto tables (train_ipc_v2.py)", "",
          "Cells: ROC-AUC / PR-AUC (raw score) / Brier (calibrated p). 'transition rows' = state at issue < IPC3.", "",
          "Label base rates per country (rows with known state):", "", "```", json.dumps(res["label_base_rates"], indent=1), "```", ""]
    oofs, hos, thrs_all = {}, {}, {}
    grp_models = ["persistence", "fews", "eo:lgbm", "eo_p:lgbm", "eo_fews:lgbm", "eo_fews_p:lgbm", "full:lgbm"]
    for h in T.HORIZONS:
        print("== CV", h, flush=True)
        oof = T.run_cv(rows, fsets, h)
        oofs[h] = oof
        res[f"cv_{h}"] = T.tables(oof, h)
        res[f"cv_{h}_by_country"] = T.tables(oof, h, by="iso3")
        res[f"cv_{h}_by_season_ZWE"] = T.tables(oof[oof.iso3 == "ZWE"].reset_index(drop=True), h, by="season")
        model_names = [c[4:] for c in oof.columns if c.startswith("raw_")]
        res[f"cv_{h}_bootstrap"] = T.season_bootstrap(oof, h, model_names)
        thrs = {}
        for v in fsets:
            cands = {m: res[f"cv_{h}"]["ALL"][f"{v}:{m}"]["transition"]["pr"] or -1 for m in ("logreg", "lgbm", "ensemble")}
            win = max(cands, key=cands.get)
            thrs[v] = {"winner": f"{v}:{win}", "cv_transition_pr": cands, **T.tune_thresholds(oof, h, f"{v}:{win}")}
        thrs_all[h] = thrs
        md.append(T.md_table(res[f"cv_{h}"], h, f"Cross-validation (pooled {'+'.join(res['countries'])}, leave-one-season-out)"))
        md.append(T.md_by_group(res[f"cv_{h}_by_country"], h, "CV by country", grp_models))
        md.append(T.md_by_group(res[f"cv_{h}_by_season_ZWE"], h, "CV ZWE by season", ["persistence", "fews", "eo:lgbm", "eo_fews:lgbm", "full:lgbm"]))
        oof.to_parquet(out / f"oof_{h}.parquet", index=False)
        if h == "h13" and not a.no_ablation:
            ab_sets = {k: fsets[k] for k in ("eo", "eo_fews")}
            res["ablation_h13"] = ablation(rows, ab_sets, h, oof)
            md.append(md_ablation(res["ablation_h13"], ab_sets))
        if a.cv_only:
            continue
        print("== hold-out", h, flush=True)
        ho, imp, info = T.run_holdout(rows, fsets, h, oof)
        hos[h] = ho
        res[f"holdout_{h}"] = T.tables(ho, h)
        res[f"holdout_{h}_by_country"] = T.tables(ho, h, by="iso3")
        res[f"holdout_{h}_info"] = info
        res[f"importance_{h}"] = imp
        md.append(T.md_table(res[f"holdout_{h}"], h, "Hold-out (evaluated once; agyear >= 2023 all countries, KEN 2020-24)"))
        md.append(T.md_by_group(res[f"holdout_{h}_by_country"], h, "Hold-out by country", grp_models))
        ho.to_parquet(out / f"holdout_{h}.parquet", index=False)
    res["thresholds"] = thrs_all
    md.append("## Thresholds (CV OOF transition rows)\n\n```\n" + json.dumps(thrs_all, indent=1) + "\n```\n")
    md.append("## Season bootstrap (transition rows, h13)\n\n```\n" + json.dumps(res["cv_h13_bootstrap"], indent=1) + "\n```\n")
    if not a.cv_only:
        rep, names, tmap = {}, [], {}
        ho = hos["h13"]
        for v in fsets:
            t = thrs_all["h13"][v]
            n = t["winner"]
            for kind in ("f1", "p60"):
                if t.get(kind):
                    tab, s = T.replay(ho, "ZWE", n, t[kind]["thr"], kind)
                    rep[f"{v}:{kind}"] = s
                    if kind == "f1":
                        tab.to_csv(out / f"replay_ZWE_{v}.csv", index=False)
                        names.append(n); tmap[n] = t["f1"]["thr"]
        res["replay_ZWE"] = rep
        mon = T.monthly(ho, "ZWE", names, tmap)
        mon.to_csv(out / "replay_ZWE_monthly.csv", index=False)
        if (ho.iso3 == "MWI").any():
            for v in ("eo_fews", "full"):
                n = thrs_all["h13"][v]["winner"]
                _, s = T.replay(ho, "MWI", n, thrs_all["h13"][v]["f1"]["thr"], "f1")
                res[f"replay_MWI_{v}"] = s
        md.append("## Replay ZWE 2023/24\n\n```\n" + json.dumps(rep, indent=1, default=str) + "\n```\n")
        md.append("## ZWE monthly\n\n" + mon.to_string() + "\n")
        md.append("## LightGBM gain, hold-out models\n\n```\n" + json.dumps(res["importance_h13"], indent=1) + "\n```\n")
        pd.DataFrame({f"{h}:{v}": pd.Series(res[f"importance_{h}"][v]) for h in T.HORIZONS for v in fsets}).to_csv(out / "importance.csv")
    (out / "metrics.json").write_text(json.dumps(res, indent=1, default=str))
    (out / "tables.md").write_text("\n".join(md))
    print("\n".join(md[:30]))
    print("thresholds", json.dumps({h: {v: (t["winner"], t["f1"]["thr"], t["f1"]["precision"], t["f1"]["recall"]) for v, t in tt.items()} for h, tt in thrs_all.items()}))


if __name__ == "__main__":
    main()
