"""Experiment harness: reproduces the main model's leave-one-agyear-out CV (train.py) on a
cached row table, so feature / model variants can be scored with identical folds, calibration
and metrics. Nothing here modifies the main pipeline modules; they are imported.

    python pipeline/experiments/harness.py build      # cache rows_base.parquet (all 4 countries)
    python pipeline/experiments/harness.py baseline   # CV of the main models on the cached rows

Hold-out rows (agyear >= 2023, KEN 2020-22) are kept in the table flagged test=True and are
NEVER used by cv() - they exist only so a final, once-only check can be run by the main helper.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

HERE = Path(__file__).resolve().parent
OUT = Path(os.environ.get("EXP_OUT", str(HERE)))   # artefacts (caches, OOF, results); HERE = code + small data
OUT.mkdir(parents=True, exist_ok=True)
PIPE = HERE.parent
sys.path.insert(0, str(PIPE))

import lightgbm as lgb                                   # noqa: E402
import train as T                                        # noqa: E402
from common import CV_FIRST, CV_LAST, DATA_DIR, EVENTS   # noqa: E402
from features import attach, make_xy                     # noqa: E402
from common import LATENCY                               # noqa: E402

ISO3S = ["ZWE", "KEN", "MWI", "ZMB"]
ALL_LEADS = list(range(0, 7))            # rows are built for leads 0-6; cv() trains on TRAIN_LEADS by default
TRAIN_LEADS = tuple(T.TRAIN_LEADS)       # (0, 1, 2, 3) as in train.py
ROWS = OUT / "rows_base.parquet"
FEAT = OUT / "feat_base.parquet"       # unit-month feature table (for adding features)
N_JOBS = 4


# ----------------------------------------------------------------------------- dataset
def centroids(iso3: str, data_dir=DATA_DIR) -> pd.DataFrame:
    """Unit centroids (mean of ring vertices) from units_<ISO3>.geojson; lat drives the ENSO sign."""
    g = json.loads((Path(data_dir) / f"units_{iso3}.geojson").read_text())
    rows = []
    for ft in g["features"]:
        pts = []

        def walk(c):
            if isinstance(c, dict):
                if "coordinates" in c:
                    walk(c["coordinates"])
                elif "geometries" in c:
                    for x in c["geometries"]:
                        walk(x)
                return
            if isinstance(c[0], (int, float)):
                pts.append(c[:2])
            else:
                for x in c:
                    walk(x)
        if ft.get("geometry"):
            walk(ft["geometry"])
        a = np.array(pts) if pts else np.full((1, 2), np.nan)
        rows.append(dict(unit_id=ft["properties"].get("shapeID"), iso3=iso3, lon=a[:, 0].mean(), lat=a[:, 1].mean()))
    return pd.DataFrame(rows)


def build(iso3s=ISO3S, data_dir=DATA_DIR):
    preps = {i: T.prepare_country(i, data_dir) for i in iso3s}
    def _rows(P):
        X = make_xy(P["feat"], P["targets"], ALL_LEADS, P["plant"], P["bim"])
        X = T.add_families(X, P["ss"], T.crop_dominant(P["c"]))   # same families as train.build_rows (v1.1)
        X["test"] = [T.is_test(P["iso3"], a) for a in X["agyear"]]
        return X
    rows = pd.concat([_rows(P) for P in preps.values()], ignore_index=True)
    cols = T.feature_cols(next(iter(preps.values()))["feat"])
    rows = rows.reset_index(drop=True)          # keep NaN labels: alternative labels may be defined
    rows.to_parquet(ROWS, index=False)
    feats = []
    for i, P in preps.items():
        f = P["feat"].copy()
        f["iso3"] = i
        feats.append(f.reset_index())
    pd.concat(feats, ignore_index=True).to_parquet(FEAT, index=False)
    (OUT / "cols_base.json").write_text(json.dumps(cols))
    cen = [centroids(i, data_dir) for i in iso3s if (Path(data_dir) / f"units_{i}.geojson").exists()]
    if cen:
        pd.concat(cen, ignore_index=True).to_parquet(OUT / "unit_centroids.parquet", index=False)
    # also keep the wide signal grid (post crop-fallback) and season info for new features
    wides = []
    for i, P in preps.items():
        w = P["c"].wide.copy()
        w["iso3"] = i
        wides.append(w.reset_index())
    pd.concat(wides, ignore_index=True).to_parquet(OUT / "wide_base.parquet", index=False)
    seas = {}
    for i, P in preps.items():
        for u, ss in P["ss"].items():
            seas[u] = dict(iso3=i, plant=P["plant"][u], bimodal=bool(P["bim"][u]),
                           seasons=[dict(core_start=s.core_start, rainy=s.rainy, planting=s.planting,
                                         crop=s.crop, grass=s.grass) for s in ss])
    (OUT / "seasons_base.json").write_text(json.dumps(seas))
    print(f"rows={len(rows)} cv={int((~rows.test & rows.agyear.between(CV_FIRST, CV_LAST)).sum())} "
          f"test={int(rows.test.sum())} cols={len(cols)}")
    return rows, cols


def load():
    rows = pd.read_parquet(ROWS)
    cols = json.loads((OUT / "cols_base.json").read_text())
    return rows, cols


# ----------------------------------------------------------------------------- CV
def _fit(d, cols, models, lgb_params, mono):
    y = d["label"].values.astype(int)
    out = {}
    if "logreg" in models or "ensemble" in models:
        out["logreg"] = T.LogReg(cols).fit(d, y)
    if "lgbm" in models or "ensemble" in models:
        out["lgbm"] = _LGBM(cols, lgb_params, mono).fit(d, y)
    if "ensemble" in models:
        out["ensemble"] = T.Ensemble(out["logreg"], out["lgbm"])
    if "persistence" in models:
        out["persistence"] = T.Persistence().fit(d, y)
    if "rule" in models:
        out["rule"] = T.Rule().fit(d, y)
    return out


class _LGBM(T.LGBM):
    """Same as train.LGBM but with overridable params / monotone constraints."""

    def __init__(self, cols, params=None, mono=None, n_iter=None):
        super().__init__(cols, n_iter)
        self.params = dict(T.LGB_PARAMS if params is None else params)
        if mono is not None:
            self.params["monotone_constraints"] = [mono.get(c, 0) for c in cols]
            self.params["monotone_constraints_method"] = "advanced"

    def fit(self, d, y):
        yrs = np.array(sorted(d["agyear"].unique()))
        val = np.random.default_rng(T.SEED + int(yrs.sum())).choice(yrs, size=min(3, len(yrs) // 4 or 1),
                                                                       replace=False)
        iv = d["agyear"].isin(val).values
        dtr = lgb.Dataset(d.loc[~iv, self.cols], y[~iv])
        dva = lgb.Dataset(d.loc[iv, self.cols], y[iv])
        b = lgb.train(self.params, dtr, 800, valid_sets=[dva], callbacks=[lgb.early_stopping(50, verbose=False)])
        self.best = max(20, b.best_iteration or 200)
        self.b = lgb.train(self.params, lgb.Dataset(d[self.cols], y), self.best)
        return self


def cv(rows: pd.DataFrame, cols: list, models=("logreg", "lgbm", "ensemble"), lgb_params=None, mono=None,
       events=EVENTS, n_jobs=N_JOBS, group_fn=None, train_leads=TRAIN_LEADS, label_col="label") -> pd.DataFrame:
    """Leave-one-agyear-out over CV rows; returns OOF frame with raw_<m> and cross-fitted cal_<m>.

    group_fn(rows) -> Series of group keys lets a model be fitted per group (e.g. per country);
    folds are still by agyear and calibration still pooled (as in train.py)."""
    cvr = rows[~rows.test & rows.agyear.between(CV_FIRST, CV_LAST) & rows.lead.isin(train_leads)].copy()
    if label_col != "label":
        cvr["label"] = cvr[label_col]
        cvr["prev_label"] = cvr[label_col.replace("label", "prev_label")] if label_col.replace("label", "prev_label") in cvr else np.nan
    cvr = cvr.dropna(subset=["label"])
    folds = sorted(cvr.agyear.unique())
    outs = []
    for ev in events:
        d = cvr[cvr.event == ev].copy()
        raw = {m: np.full(len(d), np.nan) for m in models}
        todo = [yv for yv in folds if (d.agyear == yv).any() and d.label.values[(d.agyear != yv).values].sum() > 0]
        groups = group_fn(d) if group_fn else pd.Series("all", index=d.index)
        jobs = [(yv, g) for yv in todo for g in groups.unique()]
        fitted = Parallel(n_jobs=n_jobs)(
            delayed(_fit)(d[(d.agyear != yv).values & (groups == g).values], cols, models, lgb_params, mono)
            for yv, g in jobs)
        for (yv, g), ms in zip(jobs, fitted):
            va = (d.agyear == yv).values & (groups == g).values
            for m in models:
                raw[m][va] = ms[m].raw(d[va])
        cal = {m: np.full(len(d), np.nan) for m in models}
        for yv in todo:
            va = (d.agyear == yv).values
            for m in models:
                ok = ~va & ~np.isnan(raw[m])
                cal[m][va] = T.iso(raw[m][ok], d.label.values[ok]).predict(raw[m][va])
        o = d[["unit_id", "iso3", "agyear", "event", "lead", "label", "W0", "r"] + T.ae.FAMS + ["agreeing"]].copy()
        for m in models:
            o[f"raw_{m}"], o[f"cal_{m}"] = raw[m], cal[m]
        outs.append(o)
    return pd.concat(outs, ignore_index=True)


def table(oof: pd.DataFrame, models=("logreg", "lgbm", "ensemble"), leads=T.EVAL_LEADS, iso3=None) -> dict:
    s = oof[oof.lead.isin(leads)]
    if iso3:
        s = s[s.iso3 == iso3]
    res = {}
    for m in models:
        res[m] = {}
        for ev in EVENTS:
            x = s[s.event == ev]
            mt = T.metrics(x.label, x[f"cal_{m}"])
            mr = T.metrics(x.label, x[f"raw_{m}"], brier=False)
            mt["roc_auc"], mt["pr_auc"] = mr["roc_auc"], mr["pr_auc"]
            res[m][ev] = mt
        for k, key in (("mean_pr_auc", "pr_auc"), ("mean_roc_auc", "roc_auc"), ("mean_brier", "brier")):
            vals = [res[m][ev][key] for ev in EVENTS if res[m][ev][key] is not None]
            res[m][k] = round(float(np.mean(vals)), 4) if vals else None
    return res


def summary(name: str, tab: dict, base: dict | None = None, model="ensemble") -> str:
    t = tab[model]
    line = f"{name:40s} {model:8s} PR {t['mean_pr_auc']:.4f} Brier {t['mean_brier']:.4f}"
    if base:
        b = base[model]
        line += f"  dPR {t['mean_pr_auc'] - b['mean_pr_auc']:+.4f} dBrier {t['mean_brier'] - b['mean_brier']:+.4f}"
    line += "  | " + " ".join(f"{ev[:4]} {t[ev]['pr_auc']}/{t[ev]['brier']}" for ev in EVENTS)
    return line


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build":
        build()
    elif cmd == "baseline":
        rows, cols = load()
        models = ("persistence", "rule", "logreg", "lgbm", "ensemble")
        oof = cv(rows, cols, models=models)
        oof.to_parquet(OUT / "oof_baseline.parquet", index=False)
        tab = table(oof, models=models)
        (OUT / "cv_baseline.json").write_text(json.dumps(tab, indent=1))
        for m in models:
            print(summary("baseline", tab, model=m))
