"""3. CV is grouped by season (agricultural) year and the 2023/24 hold-out never reaches training,
calibration, threshold tuning or model selection."""
import json

import numpy as np
import pandas as pd
import pytest

import train as T
from common import CV_FIRST, CV_LAST
from conftest import make_long


class SeqParallel:                     # run joblib work in-process so fit_all can be spied on
    def __init__(self, *a, **k):
        pass

    def __call__(self, gen):
        return [f(*a, **k) for f, a, k in gen]


def _run(tmp, tag, monkeypatch, df=None, garbage_rows=False, spy=None):
    d = tmp / tag
    (d / "data").mkdir(parents=True)
    (df if df is not None else make_long(n_units=4, seed=1)).to_parquet(d / "data" / "signals_ZWE.parquet")
    if spy is not None:
        monkeypatch.setattr(T, "Parallel", SeqParallel)
        orig_fit = T.fit_all

        def fit_spy(dd, cols, n_iter=None):
            spy.append(dict(years=set(dd.agyear.unique()), test=bool(dd.test.any()),
                            final=n_iter is not None, event=dd.event.iloc[0]))
            return orig_fit(dd, cols, n_iter)
        monkeypatch.setattr(T, "fit_all", fit_spy)
    if garbage_rows:
        orig = T.build_rows

        def build_garbage(P):
            X = orig(P)
            m = X["test"].values
            rng = np.random.default_rng(123)
            cols = T.feature_cols(P["feat"]) + ["prev_label"]
            for c in dict.fromkeys(cols):
                X.loc[m, c] = rng.normal(0, 50, m.sum())
            X.loc[m, "label"] = rng.integers(0, 2, m.sum()).astype(float)
            for c in ["rain", "vegetation", "soil", "heat"]:
                X.loc[m, c] = rng.integers(0, 2, m.sum()).astype(bool)
            X.loc[m, "agreeing"] = X.loc[m, ["rain", "vegetation", "soil"]].sum(axis=1)
            return X
        monkeypatch.setattr(T, "build_rows", build_garbage)
    T.run(["ZWE"], d / "data", d / "out", "T")
    out = d / "out"
    mj = json.loads((out / "metrics_ZWE.json").read_text())
    return dict(metrics=mj, oof=pd.read_parquet(out / "oof_T.parquet"),
                th=json.loads((out / "thresholds_T.json").read_text()), out=out)


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    tmp = tmp_path_factory.mktemp("cv")
    spy = []
    try:
        clean = _run(tmp, "clean", mp, spy=spy)
        mp.undo()
        garb = _run(tmp, "garbage", mp, garbage_rows=True)
        mp.undo()
        # raw signals of the hold-out season months scrambled (well after every 2022 window)
        df = make_long(n_units=4, seed=1)
        rng = np.random.default_rng(9)
        m = df.month >= "2023-08-01"
        df.loc[m, "value"] = rng.normal(0, 30, m.sum())
        sig = _run(tmp, "garbage_signals", mp, df=df)
    finally:
        mp.undo()
    return dict(clean=clean, garb=garb, sig=sig, spy=spy)


def test_holdout_has_rows_and_differs(runs):
    h1, h2 = runs["clean"]["metrics"]["holdout"], runs["garb"]["metrics"]["holdout"]
    assert h1 is not None and h1 != h2, "hold-out garbage should change hold-out metrics (sanity)"


@pytest.mark.parametrize("variant", ["garb", "sig"])
def test_cv_metrics_identical_with_garbage_holdout(runs, variant):
    a, b = runs["clean"], runs[variant]
    for k in ("cv_pooled", "cv_this_country", "cv_by_lead_winner", "winner", "thresholds"):
        assert a["metrics"][k] == b["metrics"][k], f"{k} changed when hold-out was garbage ({variant})"
    assert a["th"] == b["th"]
    pd.testing.assert_frame_equal(a["oof"], b["oof"])


def test_oof_only_cv_years(runs):
    oof = runs["clean"]["oof"]
    assert oof.agyear.between(CV_FIRST, CV_LAST).all()
    assert (oof.agyear < 2023).all()


def test_folds_leave_one_agyear_out_and_never_see_holdout(runs):
    spy = runs["spy"]
    assert spy, "fit_all never called"
    assert not any(s["test"] for s in spy), "a training set contained hold-out rows"
    assert all(max(s["years"]) <= CV_LAST and min(s["years"]) >= CV_FIRST for s in spy)
    for ev in {s["event"] for s in spy}:
        calls = [s for s in spy if s["event"] == ev]
        final = [s for s in calls if s["final"]]
        folds = [s for s in calls if not s["final"]]
        assert len(final) == 1
        allyrs = final[0]["years"]
        held = [allyrs - s["years"] for s in folds]
        assert all(len(h) == 1 for h in held), "each fold must drop exactly one agricultural year"
        assert len({next(iter(h)) for h in held}) == len(folds), "fold years must be distinct"


def test_no_model_trained_on_cant_plant(runs):
    import joblib
    assert "cant_plant" not in T.MODEL_EVENTS
    assert not any(s["event"] == "cant_plant" for s in runs["spy"]), "fit_all called on cant_plant rows"
    b = joblib.load(runs["clean"]["out"] / "model_T.joblib")
    assert "cant_plant" not in b["events"]
    assert set(runs["clean"]["oof"].event.unique()) <= set(T.MODEL_EVENTS)
