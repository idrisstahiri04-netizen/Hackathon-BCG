"""ML-expert experiment A: a satellite + seasonal-forecast "FEWS NET proxy" to cut the crisis model's dependence
on the FEWS NET feed.

Idea (distillation / stacking): FEWS NET's own ML1/ML2 projections are a strong predictor of IPC3+ (CV ROC 0.86 on
transition rows) but they are a feed that can be late or down. We train a proxy on EO-only features whose TARGET is
"FEWS NET projects Phase 3+ for months t+1..t+3" (fews_h13 >= 3, known at issue t). The proxy's probability is then
used as a feature of the IPC model instead of the real projections -> a model that works when FEWS NET is down.

Honesty: same rows / folds / purge / calibration as pipeline/ipc_model/train_ipc.py (leave-one-season-out
2015/16..2022/23, hold-out agyear >= 2023 + KEN 2020-22 scored once). The proxy feature is built NESTED: for outer
fold k, training rows of fold j get a proxy fitted on folds not in {j, k}; test rows of fold k get a proxy fitted on
all folds != k. Nothing of fold k (neither IPC truth nor FEWS projections) touches its own features.

Feature sets compared (h13, transition rows = known state < IPC3 at issue):
  eo              signals + NMME + ONI + statics (train_ipc "eo")                    current no-FEWS model
  eo_proxy        eo + p_proxy                                                        the proposal
  eo_fews         eo + FEWS text + FDW projections (train_ipc "eo_fews")              current FEWS-dependent model
  eo_fews_masked  eo_fews models, but FEWS columns set to NaN at prediction time       what happens when the feed is down
Plus the proxy's own skill (vs its FEWS target, and directly vs IPC truth) and the ZWE 2023/24 replay at CV-tuned
max-F1 thresholds (crossings before the 2024-04-03 declaration).

Outputs (EXP_OUT, default pipeline/out/xml): xml_proxy_metrics.json, xml_proxy_tables.md, oof/holdout parquet.
    python pipeline/experiments/xml_fews_proxy.py [--iso3 ZWE KEN MWI] [--smoke]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

HERE = Path(__file__).resolve().parent
P = HERE
while not (P / "common.py").exists() and P != P.parent:
    P = P.parent
PIPE = P
OUT = Path(os.environ.get("EXP_OUT", str(PIPE / "out" / "xml")))
OUT.mkdir(parents=True, exist_ok=True)
for p in (str(HERE), str(PIPE / "ipc_model"), str(PIPE)):
    if p not in sys.path:
        sys.path.insert(0, p)
import ipc_data as D   # noqa: E402
import train_ipc as T  # noqa: E402

H13 = "h13"
MODELS = ("logreg", "lgbm", "ensemble")


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


# ----------------------------------------------------------------------------- proxy
class Proxy:
    """EO-only model of P(FEWS NET projects IPC3+ for t+1..t+3). Mean of logreg and LightGBM raw probabilities."""

    def __init__(self, cols):
        self.cols = cols

    def fit(self, d: pd.DataFrame, yp: np.ndarray):
        self.lr = T.LogReg(self.cols).fit(d, yp)
        self.gb = T.LGBM(self.cols).fit(d, yp)
        return self

    def raw(self, d: pd.DataFrame) -> np.ndarray:
        return 0.5 * (self.lr.raw(d) + self.gb.raw(d))


def nested_proxy(rows: pd.DataFrame, eo: list, yp: np.ndarray, folds: list, we_ag: np.ndarray, cv_mask: np.ndarray):
    """Returns (p_outer, p_inner): p_outer[i] = proxy fitted without fold(i) (for test rows / final stacking);
    p_inner[k][i] = proxy fitted without folds {k, fold(i)} (features of training rows when fold k is held out)."""
    n = len(rows)
    ag = rows.agyear.values
    okp = ~np.isnan(yp)
    p_outer = np.full(n, np.nan)
    p_inner = {k: np.full(n, np.nan) for k in folds}
    cache = {}

    def fit_excluding(excl: tuple):
        if excl in cache:
            return cache[excl]
        tr = cv_mask & okp & ~np.isin(ag, excl) & ~np.isin(we_ag, excl)
        m = Proxy(eo).fit(rows[tr], yp[tr].astype(int))
        cache[excl] = m
        return m

    for k in folds:
        te = cv_mask & (ag == k)
        p_outer[te] = fit_excluding((k,)).raw(rows[te])
        for j in folds:
            if j == k:
                continue
            tj = cv_mask & (ag == j)
            p_inner[k][tj] = fit_excluding(tuple(sorted((j, k)))).raw(rows[tj])
        log(f"  proxy outer fold {k}: {len(cache)} proxy fits so far")
    return p_outer, p_inner


# ----------------------------------------------------------------------------- CV with the proxy feature
def run_cv(rows: pd.DataFrame, fsets: dict, p_outer: np.ndarray, p_inner: dict, fews_cols: list) -> pd.DataFrame:
    h = H13
    y = rows[f"y_{h}"].values
    we_ag = T.ag_of_mi(rows[f"win_end_{h}"].values)
    cv_mask = ~rows.test.values
    ag = rows.agyear.values
    folds = sorted(np.unique(ag[cv_mask]))
    names = ["persistence", "fews"] + [f"{v}:{m}" for v in fsets for m in ("logreg", "lgbm")] + ["eo_fews_masked:logreg", "eo_fews_masked:lgbm"]
    raw = {n: np.full(len(rows), np.nan) for n in names}
    for k in folds:
        te = cv_mask & (ag == k)
        tr = cv_mask & (ag != k) & (we_ag != k) & ~np.isnan(y)
        d_tr = rows[tr].copy()
        d_te = rows[te].copy()
        d_tr["p_proxy"] = p_inner[k][tr]           # nested: never fitted on fold k
        d_te["p_proxy"] = p_outer[te]
        y_tr = y[tr].astype(int)
        for v, cols in fsets.items():
            lr = T.LogReg(cols).fit(d_tr, y_tr)
            gb = T.LGBM(cols).fit(d_tr, y_tr)
            raw[f"{v}:logreg"][te] = lr.raw(d_te)
            raw[f"{v}:lgbm"][te] = gb.raw(d_te)
            if v == "eo_fews":
                dm = d_te.copy()
                dm[fews_cols] = np.nan
                raw["eo_fews_masked:logreg"][te] = lr.raw(dm)
                raw["eo_fews_masked:lgbm"][te] = gb.raw(dm)
        log(f"  cv fold {k}: train {tr.sum()} test {te.sum()}")
    raw["persistence"][cv_mask] = (rows.st_phase + 0.5 * rows.st_share3.fillna(0)).values[cv_mask]
    raw["fews"][cv_mask] = rows[f"fews_{h}"].values[cv_mask]
    cal = {n: np.full(len(rows), np.nan) for n in names}
    evalm = cv_mask & ~np.isnan(y) & rows.st_phase.notna().values
    for n in names:
        for k in folds:
            te = cv_mask & (ag == k)
            fit = evalm & cv_mask & (ag != k) & ~np.isnan(raw[n])
            if fit.sum() < 50 or len(np.unique(y[fit])) < 2:
                continue
            ok = te & ~np.isnan(raw[n])
            cal[n][ok] = T.iso_fit(raw[n][fit], y[fit]).predict(raw[n][ok])
    for v in list(fsets) + ["eo_fews_masked"]:
        raw[f"{v}:ensemble"] = 0.5 * (cal[f"{v}:logreg"] + cal[f"{v}:lgbm"])
        cal[f"{v}:ensemble"] = raw[f"{v}:ensemble"]
    oof = rows[["iso3", "unit_id", "unit_name", "month", "mi", "agyear", "season", "test", "st_phase", f"y_{h}", f"fews_{h}"]].copy()
    oof["p_proxy"] = p_outer
    for n in raw:
        oof[f"raw_{n}"] = raw[n]
        oof[f"cal_{n}"] = cal[n]
    return oof[cv_mask].reset_index(drop=True)


def run_holdout(rows: pd.DataFrame, fsets: dict, eo: list, yp: np.ndarray, p_outer: np.ndarray, oof: pd.DataFrame, fews_cols: list):
    h = H13
    y = rows[f"y_{h}"].values
    we_ag = T.ag_of_mi(rows[f"win_end_{h}"].values)
    we_test = np.array([T.is_test(i, a) for i, a in zip(rows.iso3.values, we_ag)])
    tr = ~rows.test.values & ~np.isnan(y) & ~we_test
    te = rows.test.values
    trp = ~rows.test.values & ~np.isnan(yp) & ~we_test
    proxy = Proxy(eo).fit(rows[trp], yp[trp].astype(int))
    d_tr = rows[tr].copy(); d_tr["p_proxy"] = p_outer[tr]          # OOF proxy for the stacked training rows
    d_te = rows[te].copy(); d_te["p_proxy"] = proxy.raw(d_te)
    y_tr = y[tr].astype(int)
    raw, imp = {}, {}
    for v, cols in fsets.items():
        lr = T.LogReg(cols).fit(d_tr, y_tr)
        gb = T.LGBM(cols).fit(d_tr, y_tr)
        raw[f"{v}:logreg"] = lr.raw(d_te); raw[f"{v}:lgbm"] = gb.raw(d_te)
        imp[v] = gb.importance().head(15).round(1).to_dict()
        if v == "eo_fews":
            dm = d_te.copy(); dm[fews_cols] = np.nan
            raw["eo_fews_masked:logreg"] = lr.raw(dm); raw["eo_fews_masked:lgbm"] = gb.raw(dm)
    raw["persistence"] = (rows.st_phase + 0.5 * rows.st_share3.fillna(0)).values[te]
    raw["fews"] = rows[f"fews_{h}"].values[te]
    ev = oof[f"y_{h}"].notna() & oof.st_phase.notna()
    cal = {}
    for n, r in raw.items():
        fit = (ev & oof[f"raw_{n}"].notna()).values
        c = np.full(len(r), np.nan); ok = ~np.isnan(r)
        c[ok] = T.iso_fit(oof[f"raw_{n}"].values[fit], oof[f"y_{h}"].values[fit]).predict(r[ok])
        cal[n] = c
    for v in list(fsets) + ["eo_fews_masked"]:
        raw[f"{v}:ensemble"] = 0.5 * (cal[f"{v}:logreg"] + cal[f"{v}:lgbm"]); cal[f"{v}:ensemble"] = raw[f"{v}:ensemble"]
    ho = rows.loc[te, ["iso3", "unit_id", "unit_name", "month", "mi", "agyear", "season", "test", "st_phase", "truth_phase",
                       "truth_is_snap", f"y_{h}", f"fews_{h}"]].copy().reset_index(drop=True)
    ho["p_proxy"] = d_te["p_proxy"].values
    for n in raw:
        ho[f"raw_{n}"] = raw[n]; ho[f"cal_{n}"] = cal[n]
    return ho, imp


# ----------------------------------------------------------------------------- reporting
def cell(m):
    return T.cell(m)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso3", nargs="+", default=["ZWE", "KEN", "MWI"])
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    if a.smoke:
        T.N_TREES = 20
    parts, infos = [], {}
    for iso in a.iso3:
        df, info = D.build_country(iso)
        parts.append(df); infos[iso] = {k: v for k, v in info.items() if k not in ("our_unmatched", "fews_unmatched", "snapshots")}
        log(iso, infos[iso])
    rows = pd.concat(parts, ignore_index=True)
    rows["test"] = rows.test.astype(bool)
    rows.to_parquet(OUT / "xml_proxy_rows.parquet", index=False)
    fs = T.feature_sets(rows)
    eo, eo_fews = fs["eo"], fs["eo_fews"]
    fews_cols = [c for c in eo_fews if c not in eo]
    fsets = {"eo": eo, "eo_proxy": eo + ["p_proxy"], "eo_fews": eo_fews}
    log("rows", rows.shape, {k: len(v) for k, v in fsets.items()})

    y = rows[f"y_{H13}"].values
    yp = np.where(rows[f"fews_{H13}"].notna(), (rows[f"fews_{H13}"] >= 3).astype(float), np.nan)
    we_ag = T.ag_of_mi(rows[f"win_end_{H13}"].values)
    cv_mask = ~rows.test.values
    folds = sorted(np.unique(rows.agyear.values[cv_mask]))
    log(f"proxy target coverage on CV rows: {np.mean(~np.isnan(yp[cv_mask])):.3f}, rate {np.nanmean(yp[cv_mask]):.3f}; folds {folds}")

    log("nested proxy ...")
    p_outer, p_inner = nested_proxy(rows, eo, yp, folds, we_ag, cv_mask)
    log("CV ...")
    oof = run_cv(rows, fsets, p_outer, p_inner, fews_cols)
    oof.to_parquet(OUT / "xml_proxy_oof_h13.parquet", index=False)
    res = {"countries": a.iso3, "build": infos, "n_rows": int(len(rows)), "fews_cols_masked": fews_cols,
           "cv_seasons": [int(f) for f in folds], "n_trees": T.N_TREES}
    # proxy skill
    m = cv_mask & ~np.isnan(yp) & ~np.isnan(p_outer)
    tr_m = m & (rows.st_phase.values < 3)
    res["proxy_skill"] = {
        "vs_fews_target_all": {"roc": round(float(roc_auc_score(yp[m], p_outer[m])), 3), "n": int(m.sum()), "base": round(float(yp[m].mean()), 3)},
        "vs_fews_target_transition": {"roc": round(float(roc_auc_score(yp[tr_m], p_outer[tr_m])), 3), "n": int(tr_m.sum()), "base": round(float(yp[tr_m].mean()), 3)},
        "proxy_vs_ipc_truth_transition": T.metrics(oof.loc[oof.st_phase < 3, f"y_{H13}"], oof.loc[oof.st_phase < 3, "p_proxy"]),
    }
    res["cv_h13"] = T.tables(oof, H13)
    res["cv_h13_by_country"] = T.tables(oof, H13, by="iso3")
    res["cv_h13_by_season_ZWE"] = T.tables(oof[oof.iso3 == "ZWE"].reset_index(drop=True), H13, by="season")
    names = [c[4:] for c in oof.columns if c.startswith("raw_")]
    res["cv_h13_bootstrap"] = T.season_bootstrap(oof, H13, [n for n in names if n.endswith(":lgbm") or n in ("fews", "persistence")])
    thrs = {}
    for v in list(fsets) + ["eo_fews_masked"]:
        cands = {mm: res["cv_h13"]["ALL"][f"{v}:{mm}"]["transition"]["pr"] or -1 for mm in MODELS}
        win = max(cands, key=cands.get)
        thrs[v] = {"winner": f"{v}:{win}", "cv_transition_pr": cands, **T.tune_thresholds(oof, H13, f"{v}:{win}")}
    res["thresholds"] = thrs

    log("hold-out once ...")
    ho, imp = run_holdout(rows, fsets, eo, yp, p_outer, oof, fews_cols)
    ho.to_parquet(OUT / "xml_proxy_holdout_h13.parquet", index=False)
    res["holdout_h13"] = T.tables(ho, H13)
    res["holdout_h13_by_country"] = T.tables(ho, H13, by="iso3")
    res["importance_h13"] = imp
    rep = {}
    for v in list(fsets) + ["eo_fews_masked"]:
        n = thrs[v]["winner"]
        _, s = T.replay(ho, "ZWE", n, thrs[v]["f1"]["thr"], "f1")
        rep[v] = s
        if (ho.iso3 == "MWI").any():
            _, s2 = T.replay(ho, "MWI", n, thrs[v]["f1"]["thr"], "f1")
            rep[f"{v}_MWI"] = {k: s2[k] for k in ("n_transitions", "transitions_warned", "warned_before_decl", "false_alarms_calm_units", "lead_months_median")}
    res["replay"] = rep
    res["seconds"] = round(time.time() - t0, 1)
    (OUT / "xml_proxy_metrics.json").write_text(json.dumps(res, indent=1, default=str))

    grp = ["persistence", "fews", "eo:lgbm", "eo:ensemble", "eo_proxy:lgbm", "eo_proxy:ensemble", "eo_fews:lgbm", "eo_fews_masked:lgbm"]
    md = ["# ML-expert experiment A: satellite-only FEWS NET proxy (IPC3+ within 1-3 months)", "",
          f"Generated {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}; countries {a.iso3}; rows {len(rows)}; "
          f"CV seasons {res['cv_seasons']}; LightGBM trees {T.N_TREES}. Cells: ROC / PR-AUC (raw) / Brier (calibrated).", "",
          "Proxy skill: " + json.dumps(res["proxy_skill"], default=str), "",
          T.md_table(res["cv_h13"], H13, "Cross-validation (leave-one-season-out, purged)"),
          T.md_by_group(res["cv_h13_by_country"], H13, "CV by country", grp),
          T.md_by_group(res["cv_h13_by_season_ZWE"], H13, "CV ZWE by season", ["persistence", "fews", "eo:lgbm", "eo_proxy:lgbm", "eo_fews:lgbm", "eo_fews_masked:lgbm"]),
          T.md_table(res["holdout_h13"], H13, "Hold-out (scored once; ZWE/MWI 2023/24+, KEN 2020-24)"),
          T.md_by_group(res["holdout_h13_by_country"], H13, "Hold-out by country", grp),
          "## CV thresholds (transition rows, max F1)\n\n```\n" + json.dumps({k: (v["winner"], v["f1"]) for k, v in thrs.items()}, indent=1) + "\n```\n",
          "## Replay ZWE 2023/24 (and MWI), CV thresholds\n\n```\n" + json.dumps(rep, indent=1, default=str) + "\n```\n",
          "## Season bootstrap (transition rows)\n\n```\n" + json.dumps(res["cv_h13_bootstrap"], indent=1) + "\n```\n",
          "## LightGBM gain (hold-out models)\n\n```\n" + json.dumps(imp, indent=1) + "\n```\n"]
    (OUT / "xml_proxy_tables.md").write_text("\n".join(md))
    log(f"done in {res['seconds']} s")
    print("\n".join(md[:8]))


if __name__ == "__main__":
    main()
