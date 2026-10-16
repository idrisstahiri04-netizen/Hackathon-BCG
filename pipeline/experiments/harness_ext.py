"""Extension of harness.cv allowing different feature sets for the linear and the tree member
(e.g. ONI only in logreg), and coarsened features. Kept separate so a running batch that imported
harness.py is not affected."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

HERE = Path(__file__).resolve().parent
OUT = Path(os.environ.get("EXP_OUT", str(HERE)))   # artefacts (caches, OOF, results); HERE = code + small data
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import harness as H                                   # noqa: E402
import train as T                                     # noqa: E402
from common import CV_FIRST, CV_LAST, EVENTS          # noqa: E402

MODELS = ("logreg", "lgbm", "ensemble")


def _fit2(d, cols_lr, cols_gb, lgb_params, mono, lr_C):
    y = d["label"].values.astype(int)
    lr = T.LogReg(cols_lr)
    if lr_C is not None:
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        lr.m = make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler(),
                             LogisticRegression(C=lr_C, class_weight="balanced", max_iter=3000))
        lr.m.fit(d[cols_lr].values, y)
    else:
        lr.fit(d, y)
    gb = H._LGBM(cols_gb, lgb_params, mono).fit(d, y)
    return {"logreg": lr, "lgbm": gb, "ensemble": T.Ensemble(lr, gb)}


def cv2(rows, cols_lr, cols_gb, lgb_params=None, mono=None, lr_C=None, n_jobs=H.N_JOBS, events=EVENTS,
        weights=(0.5, 0.5), train_leads=H.TRAIN_LEADS, label_col="label", extra_train=None):
    """extra_train: rows from additional countries, used only for fitting (same agyear folds, never
    evaluated, never calibrated on). Must already carry the feature columns."""
    cvr = rows[~rows.test & rows.agyear.between(CV_FIRST, CV_LAST) & rows.lead.isin(train_leads)].copy()
    if label_col != "label":
        cvr["label"] = cvr[label_col]
    cvr = cvr.dropna(subset=["label"])
    ex = None
    if extra_train is not None:
        ex = extra_train[extra_train.agyear.between(CV_FIRST, CV_LAST) & extra_train.lead.isin(train_leads)].copy()
        if label_col != "label":
            ex["label"] = ex[label_col]
        ex = ex.dropna(subset=["label"])
    folds = sorted(cvr.agyear.unique())
    outs = []
    for ev in events:
        d = cvr[cvr.event == ev].copy()
        raw = {m: np.full(len(d), np.nan) for m in MODELS}
        todo = [yv for yv in folds if (d.agyear == yv).any() and d.label.values[(d.agyear != yv).values].sum() > 0]
        def _train(yv):
            tr = d[(d.agyear != yv).values]
            if ex is not None:
                tr = pd.concat([tr, ex[(ex.event == ev) & (ex.agyear != yv)]], ignore_index=True)
            return tr
        fitted = Parallel(n_jobs=n_jobs)(
            delayed(_fit2)(_train(yv), cols_lr, cols_gb, lgb_params, mono, lr_C) for yv in todo)
        for yv, ms in zip(todo, fitted):
            va = (d.agyear == yv).values
            raw["logreg"][va] = ms["logreg"].raw(d[va])
            raw["lgbm"][va] = ms["lgbm"].raw(d[va])
            raw["ensemble"][va] = weights[0] * raw["logreg"][va] + weights[1] * raw["lgbm"][va]
        cal = {m: np.full(len(d), np.nan) for m in MODELS}
        for yv in todo:
            va = (d.agyear == yv).values
            for m in MODELS:
                ok = ~va & ~np.isnan(raw[m])
                cal[m][va] = T.iso(raw[m][ok], d.label.values[ok]).predict(raw[m][va])
        o = d[["unit_id", "iso3", "agyear", "event", "lead", "label", "W0", "r"] + T.ae.FAMS + ["agreeing"]].copy()
        for m in MODELS:
            o[f"raw_{m}"], o[f"cal_{m}"] = raw[m], cal[m]
        outs.append(o)
    return pd.concat(outs, ignore_index=True)
