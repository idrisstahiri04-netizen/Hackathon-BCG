"""IPC-target model: P(district in FEWS NET IPC Phase 3+ within 1-3 / 4-6 months | data known at issue month).

Input : pipeline/out/ipc_model/rows.parquet (from ipc_data.py)
Output: pipeline/out/ipc_model/{metrics.json, tables.md, thresholds.json, oof.parquet, holdout.parquet,
        replay_ZWE_<variant>.csv, replay_ZWE_monthly.csv, replay_summary.json, importance.csv}

Validation: leave-one-season-out over the non-test agricultural years (2015/16 .. 2022/23; KEN only to
2019/20 because its 2020-22 drought is a hold-out), rows of the held-out season AND training rows whose
label window reaches into that season are excluded ("purge"). Hold-out = agyear >= 2023 (+ KEN 2020-22),
scored once with models fitted on all CV rows (same purge against the test period).
Calibration: cross-fitted isotonic (fold k calibrated on the other folds' OOF scores); hold-out
calibrated on all CV OOF scores. Ensemble = mean of the calibrated logreg and lgbm probabilities.
Metrics: ROC-AUC / PR-AUC on raw scores, Brier on calibrated p; on all rows with known state and on
"transition" rows only (state at issue < IPC3, i.e. the early-warning case).
Baselines: persistence (lagged CS phase only), fews (FEWS NET's own ML1/ML2 projection overlapping the
horizon window, where one exists).
Thresholds are tuned on CV OOF transition rows only and then applied unchanged to the hold-out replay.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
PIPE = HERE.parent
sys.path.insert(0, str(PIPE))
from common import OUT_DIR, is_test  # noqa: E402

warnings.filterwarnings("ignore")
SEED = 7
HORIZONS = ["h13", "h46"]
LGB_PARAMS = dict(objective="binary", learning_rate=0.03, num_leaves=15, max_depth=5, min_child_samples=40,
                  feature_fraction=0.7, bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1,
                  seed=SEED, num_threads=4)
N_TREES = 400
DECL = {"ZWE": "2024-04-03", "MWI": "2024-03-23", "KEN": "2021-09-08"}
WPM = 52.1775 / 12


def mi_of(ts: str) -> int:
    t = pd.Timestamp(ts)
    return t.year * 12 + t.month - 1


def ag_of_mi(m) -> np.ndarray:
    return (np.asarray(m, int) - 6) // 12


# ----------------------------------------------------------------------------- feature sets
def feature_sets(rows: pd.DataFrame) -> dict:
    cols = list(rows.columns)
    sig = cols[cols.index("spi_1m"): cols.index("grass_frac") + 1] + ["phase_m"]
    sfc = [c for c in cols if c.startswith("sfc_")]
    oni = ["oni", "oni_d3", "oni_x_south", "south"]
    price = [c for c in cols if c.startswith("price_")]
    ol = [c for c in cols if c.startswith("ol_")]
    fdw = ["fdw_ml1", "fdw_ml2", "fdw_ml1_share3", "fdw_age"]
    st = ["st_phase", "st_share3", "st_snap_age", "st_m_since3", "st_any3_12", "st_delta4"]
    eo = sig + sfc + oni + price
    return {"eo": eo, "eo_fews": eo + ol + fdw, "full": eo + ol + fdw + st}


# ----------------------------------------------------------------------------- models
class LogReg:
    def __init__(self, cols):
        self.cols = cols

    def fit(self, d, y):
        self.m = make_pipeline(SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True),
                               StandardScaler(), LogisticRegression(C=0.1, class_weight="balanced", max_iter=3000))
        self.m.fit(d[self.cols].values.astype(float), y)
        return self

    def raw(self, d):
        return self.m.predict_proba(d[self.cols].values.astype(float))[:, 1]


class LGBM:
    def __init__(self, cols):
        self.cols = cols

    def fit(self, d, y):
        self.b = lgb.train(LGB_PARAMS, lgb.Dataset(d[self.cols].astype(float), y), N_TREES)
        return self

    def raw(self, d):
        return self.b.predict(d[self.cols].astype(float))

    def importance(self):
        return pd.Series(self.b.feature_importance("gain"), index=self.cols).sort_values(ascending=False)


def iso_fit(x, y):
    return IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(x, y)


def metrics(y, p, cal=None) -> dict:
    y, p = np.asarray(y, float), np.asarray(p, float)
    ok = ~np.isnan(y) & ~np.isnan(p)
    y, p = y[ok], p[ok]
    out = {"n": int(len(y)), "pos": int(y.sum()), "base": round(float(y.mean()), 3) if len(y) else None}
    if len(y) and 0 < y.sum() < len(y):
        out["roc"] = round(float(roc_auc_score(y, p)), 3)
        out["pr"] = round(float(average_precision_score(y, p)), 3)
    else:
        out["roc"] = out["pr"] = None
    if cal is not None:
        c = np.asarray(cal, float)[ok]
        okc = ~np.isnan(c)
        out["brier"] = round(float(brier_score_loss(y[okc], c[okc])), 4) if okc.sum() else None
    return out


def prf_at(y, p, thr) -> dict:
    y, p = np.asarray(y, float), np.asarray(p, float)
    ok = ~np.isnan(y) & ~np.isnan(p)
    y, pr = y[ok].astype(bool), p[ok] >= thr
    tp, fp, fn = int((y & pr).sum()), int((~y & pr).sum()), int((y & ~pr).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return dict(thr=round(float(thr), 3), tp=tp, fp=fp, fn=fn, precision=round(prec, 3), recall=round(rec, 3),
                f1=round(f1, 3), alarm_rate=round(float(pr.mean()), 3) if len(pr) else None)


# ----------------------------------------------------------------------------- CV
def run_cv(rows: pd.DataFrame, fsets: dict, h: str) -> tuple[pd.DataFrame, dict]:
    """Returns OOF frame (raw + calibrated scores per model) and feature importances."""
    y = rows[f"y_{h}"].values
    we_ag = ag_of_mi(rows[f"win_end_{h}"].values)
    cv_mask = ~rows.test.values
    folds = sorted(rows.loc[cv_mask, "agyear"].unique())
    names = ["persistence", "fews"] + [f"{v}:{m}" for v in fsets for m in ("logreg", "lgbm")]
    raw = {n: np.full(len(rows), np.nan) for n in names}
    fold_of = np.where(cv_mask, rows.agyear.values, -1)
    for k in folds:
        te = cv_mask & (rows.agyear.values == k)
        tr = cv_mask & (rows.agyear.values != k) & (we_ag != k) & ~np.isnan(y)
        d_tr, y_tr = rows[tr], y[tr].astype(int)
        for v, cols in fsets.items():
            raw[f"{v}:logreg"][te] = LogReg(cols).fit(d_tr, y_tr).raw(rows[te])
            raw[f"{v}:lgbm"][te] = LGBM(cols).fit(d_tr, y_tr).raw(rows[te])
        print(f"  {h} fold {k} train {tr.sum()} test {te.sum()}", flush=True)
    raw["persistence"][cv_mask] = (rows.st_phase + 0.5 * rows.st_share3.fillna(0)).values[cv_mask]
    raw["fews"][cv_mask] = rows[f"fews_{h}"].values[cv_mask]
    # cross-fitted isotonic calibration
    cal = {n: np.full(len(rows), np.nan) for n in names}
    evalm = cv_mask & ~np.isnan(y) & rows.st_phase.notna().values
    for n in names:
        for k in folds:
            te = fold_of == k
            fit = evalm & (fold_of != k) & ~np.isnan(raw[n])
            if fit.sum() < 50 or len(np.unique(y[fit])) < 2:
                continue
            ok = te & ~np.isnan(raw[n])
            cal[n][ok] = iso_fit(raw[n][fit], y[fit]).predict(raw[n][ok])
    for v in fsets:
        raw[f"{v}:ensemble"] = 0.5 * (cal[f"{v}:logreg"] + cal[f"{v}:lgbm"])
        cal[f"{v}:ensemble"] = raw[f"{v}:ensemble"]
    oof = rows[["iso3", "unit_id", "unit_name", "month", "mi", "agyear", "season", "test", "st_phase", f"y_{h}"]].copy()
    for n in raw:
        oof[f"raw_{n}"] = raw[n]
        oof[f"cal_{n}"] = cal[n]
    return oof[cv_mask].reset_index(drop=True)


def tables(oof: pd.DataFrame, h: str, by: str | None = None) -> dict:
    """Metrics per model on all rows and on transition rows (state < 3), optionally per group."""
    y = oof[f"y_{h}"]
    base = y.notna() & oof.st_phase.notna()
    names = [c[4:] for c in oof.columns if c.startswith("raw_")]
    groups = {"ALL": np.ones(len(oof), bool)} if by is None else {g: (oof[by] == g).values for g in sorted(oof[by].unique())}
    out = {}
    for g, gm in groups.items():
        out[g] = {}
        for n in names:
            m_all = base & gm
            m_tr = m_all & (oof.st_phase < 3)
            out[g][n] = {"all": metrics(y[m_all], oof[f"raw_{n}"][m_all], oof[f"cal_{n}"][m_all]),
                         "transition": metrics(y[m_tr], oof[f"raw_{n}"][m_tr], oof[f"cal_{n}"][m_tr])}
    return out


def season_bootstrap(oof: pd.DataFrame, h: str, names, n_rep=300) -> dict:
    """Block bootstrap over seasons for transition-row PR-AUC and ROC-AUC (5-95%)."""
    y = oof[f"y_{h}"]
    m = (y.notna() & oof.st_phase.notna() & (oof.st_phase < 3)).values
    d = oof[m]
    seasons = sorted(d.agyear.unique())
    rng = np.random.default_rng(SEED)
    idx_by = {s: np.where(d.agyear.values == s)[0] for s in seasons}
    out = {}
    for n in names:
        pr, roc = [], []
        sc = d[f"raw_{n}"].values
        yy = d[f"y_{h}"].values
        for _ in range(n_rep):
            pick = rng.choice(seasons, size=len(seasons), replace=True)
            ii = np.concatenate([idx_by[s] for s in pick])
            ok = ~np.isnan(sc[ii])
            if ok.sum() < 20 or len(np.unique(yy[ii][ok])) < 2:
                continue
            pr.append(average_precision_score(yy[ii][ok], sc[ii][ok]))
            roc.append(roc_auc_score(yy[ii][ok], sc[ii][ok]))
        if pr:
            out[n] = {"pr_5_95": [round(float(np.percentile(pr, 5)), 3), round(float(np.percentile(pr, 95)), 3)],
                      "roc_5_95": [round(float(np.percentile(roc, 5)), 3), round(float(np.percentile(roc, 95)), 3)]}
    return out


def tune_thresholds(oof: pd.DataFrame, h: str, name: str) -> dict:
    y = oof[f"y_{h}"]
    m = (y.notna() & oof.st_phase.notna() & (oof.st_phase < 3) & oof[f"cal_{name}"].notna()).values
    yy, p = y[m].values, oof[f"cal_{name}"][m].values
    grid = np.round(np.arange(0.05, 0.96, 0.01), 2)
    res = [prf_at(yy, p, t) for t in grid]
    best_f1 = max(res, key=lambda r: r["f1"])
    p60 = [r for r in res if r["precision"] >= 0.6 and r["tp"] > 0]
    best_p60 = max(p60, key=lambda r: r["recall"]) if p60 else None
    return {"f1": best_f1, "p60": best_p60, "n_rows": int(m.sum()), "base": round(float(yy.mean()), 3)}


# ----------------------------------------------------------------------------- hold-out
def run_holdout(rows: pd.DataFrame, fsets: dict, h: str, oof: pd.DataFrame) -> tuple[pd.DataFrame, dict, dict]:
    y = rows[f"y_{h}"].values
    we_ag = ag_of_mi(rows[f"win_end_{h}"].values)
    we_test = np.array([is_test(i, a) for i, a in zip(rows.iso3.values, we_ag)])
    tr = ~rows.test.values & ~np.isnan(y) & ~we_test
    te = rows.test.values
    d_tr, y_tr = rows[tr], y[tr].astype(int)
    raw, imp, models = {}, {}, {}
    for v, cols in fsets.items():
        lr = LogReg(cols).fit(d_tr, y_tr)
        gb = LGBM(cols).fit(d_tr, y_tr)
        raw[f"{v}:logreg"] = lr.raw(rows[te]); raw[f"{v}:lgbm"] = gb.raw(rows[te])
        imp[v] = gb.importance().head(20).round(1).to_dict()
    raw["persistence"] = (rows.st_phase + 0.5 * rows.st_share3.fillna(0)).values[te]
    raw["fews"] = rows[f"fews_{h}"].values[te]
    ev = oof[f"y_{h}"].notna() & oof.st_phase.notna()
    cal = {}
    for n, r in raw.items():
        fit = (ev & oof[f"raw_{n}"].notna()).values
        c = np.full(len(r), np.nan)
        ok = ~np.isnan(r)
        c[ok] = iso_fit(oof[f"raw_{n}"].values[fit], oof[f"y_{h}"].values[fit]).predict(r[ok])
        cal[n] = c
    for v in fsets:
        raw[f"{v}:ensemble"] = 0.5 * (cal[f"{v}:logreg"] + cal[f"{v}:lgbm"])
        cal[f"{v}:ensemble"] = raw[f"{v}:ensemble"]
    ho = rows.loc[te, ["iso3", "unit_id", "unit_name", "month", "mi", "agyear", "season", "test", "st_phase",
                       "truth_phase", "truth_is_snap", f"y_{h}", f"fews_{h}"]].copy().reset_index(drop=True)
    for n in raw:
        ho[f"raw_{n}"] = raw[n]
        ho[f"cal_{n}"] = cal[n]
    return ho, imp, {"n_train": int(tr.sum()), "n_test": int(te.sum())}


# ----------------------------------------------------------------------------- replay ZWE 2023/24
def replay(ho: pd.DataFrame, iso3: str, name: str, thr: float, label: str) -> tuple[pd.DataFrame, dict]:
    """ZWE 2023/24 replay. Season window = issue months Oct 2023 (pre-season CS map) .. Sep 2024 (last issue
    before the Oct 2024 map). A crossing counts only while the district's KNOWN state (lagged CS map) is still
    < IPC3, i.e. before FEWS NET has published Crisis for it. Transition = district < IPC3 on the Oct 2023 map
    and IPC3+ on a later map of the season. Lead = first IPC3+ map month - first crossing month; conservative
    lead assumes onset right after the previous map (lead - 3 months)."""
    d = ho[(ho.iso3 == iso3)].copy()
    oct_mi, decl_mi, end_mi = mi_of("2023-10-01"), mi_of(DECL[iso3]) - 1, mi_of("2024-09-01")
    d = d[(d.mi >= oct_mi) & (d.mi <= mi_of("2024-10-01"))]      # Oct 2024 row: truth only (last map of the season)
    if d.empty:
        return pd.DataFrame(), {"note": f"no {iso3} rows"}
    rows = []
    for uid, g in d.groupby("unit_id"):
        g = g.sort_values("mi")
        p = g[f"cal_{name}"].values
        known_lt3 = ~(g.st_phase.values >= 3)
        oct_state = g.loc[g.mi == oct_mi, "truth_phase"]
        oct_state = float(oct_state.iloc[0]) if len(oct_state) and pd.notna(oct_state.iloc[0]) else np.nan
        f3 = g.loc[g.truth_phase >= 3, "mi"]
        first3 = int(f3.min()) if len(f3) else None
        in_win = g.mi.values <= end_mi
        hit = (p >= thr) & known_lt3 & in_win
        first_x = int(g.mi.values[np.argmax(hit)]) if hit.any() else None
        hit2 = [int(g.mi.values[i]) for i in range(1, len(g)) if hit[i] and p[i - 1] >= thr]
        first_x2 = hit2[0] if hit2 else None
        fw = g.loc[(g["fews_h13"] >= 3) & known_lt3 & in_win, "mi"]
        first_fews = int(fw.min()) if len(fw) else None
        pm = {int(m): (None if np.isnan(v) else round(float(v), 3)) for m, v in zip(g.mi, p)}
        rows.append(dict(unit_id=uid, unit_name=g.unit_name.iloc[0], oct2023_phase=oct_state,
                         transition=(np.nan if np.isnan(oct_state) else float(oct_state < 3 and first3 is not None)),
                         first_ipc3=first3, first_cross=first_x, first_cross_2runs=first_x2, first_fews_proj3=first_fews,
                         lead_months=(None if first3 is None or first_x is None else first3 - first_x),
                         lead_2runs_months=(None if first3 is None or first_x2 is None else first3 - first_x2),
                         before_decl=(None if first_x is None else bool(first_x <= decl_mi)),
                         before_decl_2runs=(None if first_x2 is None else bool(first_x2 <= decl_mi)),
                         p_oct23=pm.get(mi_of("2023-10-01")), p_nov23=pm.get(mi_of("2023-11-01")), p_dec23=pm.get(mi_of("2023-12-01")),
                         p_jan24=pm.get(mi_of("2024-01-01")), p_feb24=pm.get(mi_of("2024-02-01")), p_mar24=pm.get(mi_of("2024-03-01")),
                         p_may24=pm.get(mi_of("2024-05-01")), p_max=round(float(np.nanmax(p)), 3) if np.isfinite(p).any() else None))
    t = pd.DataFrame(rows)
    fmt = lambda m: None if m is None or (isinstance(m, float) and np.isnan(m)) else f"{int(m) // 12}-{int(m) % 12 + 1:02d}"  # noqa: E731
    for c in ("first_ipc3", "first_cross", "first_cross_2runs", "first_fews_proj3"):
        t[c + "_ym"] = t[c].map(fmt)
    tr = t[t.transition.notna()]
    ev = tr[tr.transition == 1]
    ne = tr[tr.transition == 0]
    warned = tr.first_cross.notna()
    ld = ev.lead_months.dropna()
    ld2 = ev.lead_2runs_months.dropna()
    summ = dict(model=name, threshold=thr, threshold_kind=label, n_units=int(len(t)),
                n_oct2023_ipc3=int((tr.oct2023_phase >= 3).sum()), n_transitions=int(len(ev)),
                n_never_ipc3_by_oct2024=int((ne.oct2023_phase < 3).sum()),
                transitions_warned=int(ev.first_cross.notna().sum()),
                transitions_warned_2runs=int(ev.first_cross_2runs.notna().sum()),
                precision_vs_transition=round(float((warned & (tr.transition == 1)).sum() / warned.sum()), 3) if warned.sum() else None,
                recall_transition=round(float(ev.first_cross.notna().mean()), 3) if len(ev) else None,
                warned_before_decl=int(ev.before_decl.fillna(False).astype(bool).sum()),
                warned_before_decl_2runs=int(ev.before_decl_2runs.fillna(False).astype(bool).sum()),
                lead_months_median=(None if ld.empty else float(ld.median())),
                lead_months_conservative_median=(None if ld.empty else float((ld - 3).clip(lower=0).median())),
                lead_months_share_pos=(None if ld.empty else round(float((ld > 0).mean()), 3)),
                lead_weeks_median=(None if ld.empty else round(float(ld.median() * WPM), 1)),
                lead_2runs_months_median=(None if ld2.empty else float(ld2.median())),
                first_cross_by_month=ev.first_cross_ym.value_counts().sort_index().to_dict(),
                first_cross_2runs_by_month=ev.first_cross_2runs_ym.value_counts().sort_index().to_dict(),
                first_ipc3_by_month=ev.first_ipc3_ym.value_counts().sort_index().to_dict(),
                lead_by_entry_map={k: float(v) for k, v in ev.groupby("first_ipc3_ym").lead_months.median().items()},
                fews_proj_warned=int(ev.first_fews_proj3.notna().sum()),
                fews_proj_before_decl=int(((ev.first_fews_proj3.notna()) & (ev.first_fews_proj3 <= decl_mi)).sum()),
                fews_proj_lead_months_median=(None if ev.first_fews_proj3.dropna().empty else float((ev.first_ipc3 - ev.first_fews_proj3).dropna().median())),
                already_ipc3_oct2023_p_nov23_ge_thr=int((tr[tr.oct2023_phase >= 3].p_nov23.fillna(0) >= thr).sum()),
                false_alarms_calm_units=int(((tr.transition == 0) & (tr.oct2023_phase < 3) & warned).sum()))
    return t, summ


def monthly(ho: pd.DataFrame, iso3: str, names: list, thrs: dict) -> pd.DataFrame:
    d = ho[(ho.iso3 == iso3) & (ho.mi >= mi_of("2023-07-01")) & (ho.mi <= mi_of("2024-10-01"))].copy()
    if d.empty:
        return pd.DataFrame()
    oct_state = d[d.mi == mi_of("2023-10-01")].set_index("unit_id").truth_phase
    d["trans_cand"] = d.unit_id.map(oct_state).lt(3) & ~(d.st_phase >= 3)     # not IPC3+ in Oct 2023 and not yet known IPC3+
    out = d.groupby("month").agg(n=("unit_id", "size"), ipc3_truth=("truth_phase", lambda v: int((v >= 3).sum())),
                                 ipc3_state_known=("st_phase", lambda v: int((v >= 3).sum())),
                                 n_trans_cand=("trans_cand", "sum"))
    for n in names:
        out[f"mean_p_{n}"] = d.groupby("month")[f"cal_{n}"].mean().round(3)
        out[f"n_ge_thr_{n}"] = d.groupby("month")[f"cal_{n}"].apply(lambda v: int((v >= thrs[n]).sum()))
        out[f"n_trans_ge_thr_{n}"] = d[d.trans_cand].groupby("month")[f"cal_{n}"].apply(lambda v: int((v >= thrs[n]).sum()))
    return out.reset_index()


# ----------------------------------------------------------------------------- markdown
def cell(m):
    if not m or m.get("roc") is None:
        return "-"
    b = m.get("brier")
    return f"{m['roc']:.3f} / {m['pr']:.3f}" + (f" / {b:.4f}" if b is not None else "") + f" (n {m['n']}, base {m['base']})"


def md_table(tab: dict, h: str, title: str) -> str:
    names = list(next(iter(tab.values())).keys())
    lines = [f"### {title} — {h}", "", "| model | all rows | transition rows (state < 3) |", "|---|---|---|"]
    for n in names:
        a, t = tab["ALL"][n]["all"], tab["ALL"][n]["transition"]
        lines.append(f"| {n} | {cell(a)} | {cell(t)} |")
    return "\n".join(lines) + "\n"


def md_by_group(tab: dict, h: str, title: str, models: list) -> str:
    lines = [f"### {title} — {h} (transition rows)", "", "| group | " + " | ".join(models) + " |", "|---|" + "---|" * len(models)]
    for g, t in tab.items():
        lines.append(f"| {g} | " + " | ".join(cell(t[m]["transition"]) for m in models) + " |")
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT_DIR / "ipc_model"))
    ap.add_argument("--smoke", action="store_true", help="few trees, for a local syntax run only")
    ap.add_argument("--replay-only", action="store_true", help="recompute the replay from holdout_h13.parquet + metrics.json")
    a = ap.parse_args()
    out = Path(a.out)
    if a.replay_only:
        return replay_only(out)
    rows = pd.read_parquet(out / "rows.parquet")
    rows["test"] = rows.test.astype(bool)
    if a.smoke:
        global N_TREES
        N_TREES = 20
    fsets = feature_sets(rows)
    print("rows", rows.shape, "variants", {k: len(v) for k, v in fsets.items()}, flush=True)
    res = {"n_rows": int(len(rows)), "countries": sorted(rows.iso3.unique()), "variants": {k: v for k, v in fsets.items()},
           "cv_seasons": sorted(rows.loc[~rows.test, "season"].unique()), "lgb": {**LGB_PARAMS, "n_trees": N_TREES}}
    md = ["# IPC-target model: auto tables (generated by train_ipc.py)", "",
          "Cells: ROC-AUC / PR-AUC (raw score) / Brier (calibrated p). 'transition rows' = state at issue < IPC3.", ""]
    oofs, hos, thrs_all = {}, {}, {}
    for h in HORIZONS:
        print("== CV", h, flush=True)
        oof = run_cv(rows, fsets, h)
        oofs[h] = oof
        res[f"cv_{h}"] = tables(oof, h)
        res[f"cv_{h}_by_country"] = tables(oof, h, by="iso3")
        res[f"cv_{h}_by_season_ZWE"] = tables(oof[oof.iso3 == "ZWE"].reset_index(drop=True), h, by="season")
        model_names = [c[4:] for c in oof.columns if c.startswith("raw_")]
        res[f"cv_{h}_bootstrap"] = season_bootstrap(oof, h, model_names)
        # winner per variant by CV transition PR-AUC, then thresholds
        thrs = {}
        for v in fsets:
            cands = {m: res[f"cv_{h}"]["ALL"][f"{v}:{m}"]["transition"]["pr"] or -1 for m in ("logreg", "lgbm", "ensemble")}
            win = max(cands, key=cands.get)
            thrs[v] = {"winner": f"{v}:{win}", "cv_transition_pr": cands, **tune_thresholds(oof, h, f"{v}:{win}")}
        thrs_all[h] = thrs
        md.append(md_table(res[f"cv_{h}"], h, "Cross-validation (pooled ZWE+KEN+MWI, leave-one-season-out)"))
        md.append(md_by_group(res[f"cv_{h}_by_country"], h, "CV by country", ["persistence", "fews", "eo:ensemble", "eo_fews:ensemble", "full:ensemble"]))
        md.append(md_by_group(res[f"cv_{h}_by_season_ZWE"], h, "CV ZWE by season", ["persistence", "fews", "eo:ensemble", "full:ensemble"]))
        print("== hold-out", h, flush=True)
        ho, imp, info = run_holdout(rows, fsets, h, oof)
        hos[h] = ho
        res[f"holdout_{h}"] = tables(ho, h)
        res[f"holdout_{h}_by_country"] = tables(ho, h, by="iso3")
        res[f"holdout_{h}_info"] = info
        res[f"importance_{h}"] = imp
        md.append(md_table(res[f"holdout_{h}"], h, "Hold-out (evaluated once; ZWE/MWI 2023/24+, KEN 2020-24)"))
        md.append(md_by_group(res[f"holdout_{h}_by_country"], h, "Hold-out by country", ["persistence", "fews", "eo:ensemble", "eo_fews:ensemble", "full:ensemble"]))
        oof.to_parquet(out / f"oof_{h}.parquet", index=False)
        ho.to_parquet(out / f"holdout_{h}.parquet", index=False)
    res["thresholds"] = thrs_all
    # replay ZWE 2023/24 with h13 winners and CV-tuned thresholds
    rep = {}
    ho = hos["h13"]
    names, tmap = [], {}
    for v in fsets:
        t = thrs_all["h13"][v]
        n = t["winner"]
        for kind in ("f1", "p60"):
            if t.get(kind):
                tab, s = replay(ho, "ZWE", n, t[kind]["thr"], kind)
                rep[f"{v}:{kind}"] = s
                if kind == "f1":
                    tab.to_csv(out / f"replay_ZWE_{v}.csv", index=False)
                    names.append(n); tmap[n] = t["f1"]["thr"]
    res["replay_ZWE"] = rep
    mon = monthly(ho, "ZWE", names, tmap)
    mon.to_csv(out / "replay_ZWE_monthly.csv", index=False)
    if "MWI" in set(rows.iso3):
        n = thrs_all["h13"]["full"]["winner"]
        _, s = replay(ho, "MWI", n, thrs_all["h13"]["full"]["f1"]["thr"], "f1")
        res["replay_MWI_full"] = s
    md.append("## Thresholds (CV OOF transition rows)\n\n```\n" + json.dumps(thrs_all, indent=1) + "\n```\n")
    md.append("## Replay ZWE 2023/24\n\n```\n" + json.dumps(rep, indent=1, default=str) + "\n```\n")
    md.append("## ZWE monthly\n\n" + mon.to_string() + "\n")
    md.append("## Season bootstrap (transition rows, h13)\n\n```\n" + json.dumps(res["cv_h13_bootstrap"], indent=1) + "\n```\n")
    md.append("## LightGBM gain, hold-out models\n\n```\n" + json.dumps(res["importance_h13"], indent=1) + "\n```\n")
    (out / "metrics.json").write_text(json.dumps(res, indent=1, default=str))
    (out / "tables.md").write_text("\n".join(md))
    pd.DataFrame({f"{h}:{v}": pd.Series(res[f"importance_{h}"][v]) for h in HORIZONS for v in fsets}).to_csv(out / "importance.csv")
    print("\n".join(md[:8]))
    print("thresholds", json.dumps({h: {v: (t["winner"], t["f1"]["thr"], t["f1"]["precision"], t["f1"]["recall"]) for v, t in tt.items()} for h, tt in thrs_all.items()}))
    print("replay", json.dumps(rep, indent=0, default=str)[:3000])


def replay_only(out: Path):
    res = json.loads((out / "metrics.json").read_text())
    ho = pd.read_parquet(out / "holdout_h13.parquet")
    thrs_all = res["thresholds"]
    rep, names, tmap = {}, [], {}
    for v, t in thrs_all["h13"].items():
        n = t["winner"]
        for kind in ("f1", "p60"):
            if t.get(kind):
                tab, s = replay(ho, "ZWE", n, t[kind]["thr"], kind)
                rep[f"{v}:{kind}"] = s
                if kind == "f1":
                    tab.to_csv(out / f"replay_ZWE_{v}.csv", index=False)
                    names.append(n); tmap[n] = t["f1"]["thr"]
    res["replay_ZWE"] = rep
    mon = monthly(ho, "ZWE", names, tmap)
    mon.to_csv(out / "replay_ZWE_monthly.csv", index=False)
    if (ho.iso3 == "MWI").any():
        n = thrs_all["h13"]["full"]["winner"]
        _, s = replay(ho, "MWI", n, thrs_all["h13"]["full"]["f1"]["thr"], "f1")
        res["replay_MWI_full"] = s
    (out / "metrics.json").write_text(json.dumps(res, indent=1, default=str))
    (out / "replay_summary.json").write_text(json.dumps({"replay_ZWE": rep, "replay_MWI_full": res.get("replay_MWI_full")}, indent=1, default=str))
    print(json.dumps(rep, indent=1, default=str))
    print(mon.to_string())


if __name__ == "__main__":
    main()
