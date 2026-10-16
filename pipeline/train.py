"""Train and evaluate the shortage-risk models (satellite-only targets, see labels.py).

    python pipeline/train.py --iso3 ZWE [KEN MWI ZMB]     # pools every country given
    python pipeline/train.py --iso3 ZWE --data-dir pipeline/tests/data   # synthetic smoke test

Models (one set per event: cant_plant, crop_failure, no_grass; lead is a feature):
  a persistence   previous season's label for the same unit/event
  b rule          number of alarmed families (rain/vegetation/soil) at the reference month
  c logreg        median-impute + standard-scale + L2 logistic regression, class-weighted
  d lgbm          small regularised LightGBM, early stopping on held-out training seasons
  e ensemble      mean of c and d raw scores
Every score is calibrated with isotonic regression, cross-fitted on the CV out-of-fold scores
(fold k's calibrator never sees fold k). Final calibrator = all OOF scores.

Validation: leave-one-agricultural-year-out over 2001..2022, all countries pooled.
Hold-out (never used for fitting, tuning or model choice): agyear >= 2023 (the 2023/24 season)
and KEN 2020-2022. Evaluated once, at the end, with the final models.
Training rows use leads 0-3; reported metrics use leads 1-3 only (lead 0 exists for the nowcast
the frontend shows inside a window).

Outputs: pipeline/out/model_<tag>.joblib, pipeline/out/metrics_<ISO3>.json,
pipeline/out/thresholds_<tag>.json, pipeline/out/model_report.md, pipeline/out/oof_<tag>.parquet
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import warnings
from pathlib import Path

import joblib
from joblib import Parallel, delayed
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import alert_engine as ae
from common import (CV_FIRST, CV_LAST, DATA_DIR, EVENTS, LATENCY, OUT_DIR, apply_latency, is_test,
                    load_country, unit_seasons)
from features import attach, make_xy, unit_month_features
from labels import build_targets

warnings.filterwarnings("ignore", category=UserWarning)
MODELS = ["persistence", "rule", "logreg", "lgbm", "ensemble"]
# cant_plant had no CV skill (ROC < 0.5, Brier worse than climatology) -> no model; it survives only
# as a rule-based Watch reason (strong weather-only dryness in the planting window), see export_risk.py
MODEL_EVENTS = ["crop_failure", "no_grass"]
TRAIN_LEADS = [0, 1, 2, 3]
EVAL_LEADS = [1, 2, 3]
SEED = 7
SIG_AT_R = ["spi_1m", "spi_3m", "ndvi_z_crop", "ndvi_z_grass", "vci_crop", "vci_grass", "sm1_z", "t2m_z"]
LGB_PARAMS = dict(objective="binary", learning_rate=0.05, num_leaves=15, max_depth=5,
                  min_child_samples=60, feature_fraction=0.7, bagging_fraction=0.8, bagging_freq=1,
                  lambda_l2=5.0, min_gain_to_split=0.0, verbose=-1, seed=SEED, num_threads=1)


# ----------------------------------------------------------------------------- dataset
def in_season_months(ss) -> set:
    m = set()
    for s in ss:
        m |= set(s.rainy) | set(s.crop) | set(s.grass)
    return m


CROP_GRASS = [("ndvi_crop", "ndvi_grass"), ("ndvi_z_crop", "ndvi_z_grass"), ("vci_crop", "vci_grass")]


def crop_fallback(c):
    """Units with no cropland (crop signals all NaN) use their grass signals for crop labels/features.
    Returns the list of such units. c.wide is modified in place; keep a copy for display."""
    w = c.wide
    no_crop = [u for u in c.names.index if w.loc[u, "vci_crop"].isna().all()]
    if no_crop:
        m = w.index.get_level_values("unit_id").isin(no_crop)
        for a, b in CROP_GRASS:
            w.loc[m, a] = w.loc[m, b].values
    return no_crop


def rainy_months(ss) -> set:
    m = set()
    for s in ss:
        m |= set(s.rainy) | {s.rainy[-1] % 12 + 1}
    return m


def prepare_country(iso3: str, data_dir) -> dict:
    c = load_country(iso3, data_dir)
    display = c.wide.copy()
    no_crop = crop_fallback(c)
    ss = unit_seasons(c)
    targets = build_targets(c, ss)
    feat = apply_latency(unit_month_features(c))      # only data published by issue month r
    display = apply_latency(display)                  # what an operator would see at month r
    plant = {u: v[0].planting[0] for u, v in ss.items()}
    bim = {u: len(v) > 1 for u, v in ss.items()}
    return dict(iso3=iso3, c=c, ss=ss, targets=targets, feat=feat, plant=plant, bim=bim,
                display=display, no_crop=no_crop)


def crop_dominant(c) -> dict:
    """Unit counts as cropland for the vegetation family if crop_frac >= 0.2 (else grass)."""
    cf = c.static["crop_frac"]
    return {u: bool(v >= 0.2) if pd.notna(v) else False for u, v in cf.items()}


def add_families(X: pd.DataFrame, ss: dict, crop_dom: dict | None = None) -> pd.DataFrame:
    seas = {u: in_season_months(v) for u, v in ss.items()}
    rain = {u: rainy_months(v) for u, v in ss.items()}
    # gate on the month the data describe (issue month minus latency)
    mveg = (X["r"] - pd.DateOffset(months=LATENCY["modis"])).dt.month
    mrain = (X["r"] - pd.DateOffset(months=LATENCY["chirps"])).dt.month
    ins = np.array([m in seas[u] for u, m in zip(X["unit_id"], mveg)])
    inr = np.array([m in rain[u] for u, m in zip(X["unit_id"], mrain)])
    cols = SIG_AT_R + [c for c in ("vci_crop_l1", "vci_grass_l1") if c in X]
    fam = ae.families(X[cols], ins, inr, X["unit_id"].map(crop_dom or {}).fillna(False).values)
    for k in ae.FAMS + ["agreeing", "strong_weather"]:
        X[k] = fam[k].values
    X["in_season"] = ins
    X["in_rainy"] = inr
    return X


def build_rows(P: dict) -> pd.DataFrame:
    X = make_xy(P["feat"], P["targets"], TRAIN_LEADS, P["plant"], P["bim"])
    X = add_families(X, P["ss"], crop_dominant(P["c"]))
    X["test"] = [is_test(P["iso3"], a) for a in X["agyear"]]
    return X


def feature_cols(feat: pd.DataFrame) -> list:
    return list(feat.columns) + ["lead", "phase", "bimodal"]


# ----------------------------------------------------------------------------- models
class Persistence:
    def fit(self, d, y):
        self.prior = float(np.mean(y)); return self

    def raw(self, d):
        return d["prev_label"].fillna(self.prior).values.astype(float)


class Rule:
    def fit(self, d, y):
        return self

    def raw(self, d):
        return d["agreeing"].values.astype(float) + 0.01 * d["heat"].values


class LogReg:
    def __init__(self, cols):
        self.cols = cols

    def fit(self, d, y):
        self.m = make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler(),
                               LogisticRegression(C=0.1, class_weight="balanced", max_iter=2000))
        self.m.fit(d[self.cols].values, y); return self

    def raw(self, d):
        return self.m.predict_proba(d[self.cols].values)[:, 1]


class LGBM:
    def __init__(self, cols, n_iter=None):
        self.cols, self.n_iter = cols, n_iter

    def fit(self, d, y):
        if self.n_iter is None:          # early stopping on 3 held-out training seasons
            yrs = np.array(sorted(d["agyear"].unique()))
            val = np.random.default_rng(SEED + int(yrs.sum())).choice(yrs, size=min(3, len(yrs) // 4 or 1),
                                                                         replace=False)
            iv = d["agyear"].isin(val).values
            dtr = lgb.Dataset(d.loc[~iv, self.cols], y[~iv])
            dva = lgb.Dataset(d.loc[iv, self.cols], y[iv])
            b = lgb.train(LGB_PARAMS, dtr, 800, valid_sets=[dva],
                          callbacks=[lgb.early_stopping(50, verbose=False)])
            self.best = max(20, b.best_iteration or 200)
        else:
            self.best = self.n_iter
        self.b = lgb.train(LGB_PARAMS, lgb.Dataset(d[self.cols], y), self.best)
        return self

    def raw(self, d):
        return self.b.predict(d[self.cols])


class Ensemble:
    def __init__(self, lr, gb):
        self.lr, self.gb = lr, gb

    def raw(self, d):
        return 0.5 * (self.lr.raw(d) + self.gb.raw(d))


def fit_all(d: pd.DataFrame, cols, n_iter=None) -> dict:
    y = d["label"].values.astype(int)
    m = {"persistence": Persistence().fit(d, y), "rule": Rule().fit(d, y),
         "logreg": LogReg(cols).fit(d, y), "lgbm": LGBM(cols, n_iter).fit(d, y)}
    m["ensemble"] = Ensemble(m["logreg"], m["lgbm"])
    return m


def iso(x, y):
    return IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(x, y)


def metrics(y, p, brier=True) -> dict:
    y, p = np.asarray(y, float), np.asarray(p, float)
    ok = ~np.isnan(y) & ~np.isnan(p)
    y, p = y[ok], p[ok]
    out = {"n": int(len(y)), "pos_rate": round(float(y.mean()), 3) if len(y) else None}
    if len(y) and 0 < y.sum() < len(y):
        out["roc_auc"] = round(float(roc_auc_score(y, p)), 3)
        out["pr_auc"] = round(float(average_precision_score(y, p)), 3)
    else:
        out["roc_auc"] = out["pr_auc"] = None
    out["brier"] = round(float(brier_score_loss(y, p)), 4) if (len(y) and brier) else None
    return out


# ----------------------------------------------------------------------------- main
def run(iso3s, data_dir, out_dir: Path, tag: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    preps = {i: prepare_country(i, data_dir) for i in iso3s}
    rows = pd.concat([build_rows(P) for P in preps.values()], ignore_index=True)
    cols = feature_cols(next(iter(preps.values()))["feat"])
    rows = rows.dropna(subset=["label"])
    cv = rows[~rows.test & rows.agyear.between(CV_FIRST, CV_LAST)].copy()
    te = rows[rows.test].copy()
    folds = sorted(cv.agyear.unique())
    print(f"[{tag}] rows cv={len(cv)} test={len(te)} folds={len(folds)} countries={iso3s}")

    bundle = {"tag": tag, "iso3s": iso3s, "cols": cols, "events": {}, "train_leads": TRAIN_LEADS}
    oof_all, report = [], {}
    for ev in MODEL_EVENTS:
        d = cv[cv.event == ev]
        raw = {m: np.full(len(d), np.nan) for m in MODELS}
        fold_models, best_iters = {}, []
        todo = [yv for yv in folds if (d.agyear == yv).any() and d.label.values[(d.agyear != yv).values].sum() > 0]
        fitted = Parallel(n_jobs=min(11, len(todo)))(
            delayed(fit_all)(d[(d.agyear != yv).values], cols) for yv in todo)
        for yv, ms in zip(todo, fitted):
            va = (d.agyear == yv).values
            best_iters.append(ms["lgbm"].best)
            for m in MODELS:
                raw[m][va] = ms[m].raw(d[va])
            fold_models[int(yv)] = ms
        # cross-fitted isotonic calibration
        cal = {m: np.full(len(d), np.nan) for m in MODELS}
        fold_cal = {}
        for yv in fold_models:
            va = (d.agyear == yv).values
            fold_cal[yv] = {}
            for m in MODELS:
                ok = ~va & ~np.isnan(raw[m])
                ir = iso(raw[m][ok], d.label.values[ok])
                cal[m][va] = ir.predict(raw[m][va])
                fold_cal[yv][m] = ir
        final_cal = {m: iso(raw[m][~np.isnan(raw[m])], d.label.values[~np.isnan(raw[m])]) for m in MODELS}
        o = d[["unit_id", "iso3", "agyear", "event", "lead", "label", "W0", "r", "anchor", "season"] + ae.FAMS
              + ["agreeing", "strong_weather"] + SIG_AT_R].copy()
        for m in MODELS:
            o[f"raw_{m}"], o[f"cal_{m}"] = raw[m], cal[m]
        oof_all.append(o)
        n_iter = int(np.median(best_iters)) if best_iters else 200
        final = fit_all(d, cols, n_iter=n_iter)
        bundle["events"][ev] = dict(fold_models=fold_models, fold_cal=fold_cal, final=final,
                                    final_cal=final_cal, lgbm_iter=n_iter)
        print(f"  {ev}: folds={len(fold_models)} lgbm_iter={n_iter}")

    oof = pd.concat(oof_all, ignore_index=True)
    ev_oof = oof[oof.lead.isin(EVAL_LEADS)]

    def table(df, pcol_prefix="cal_", group_iso=None):
        res = {}
        for m in MODELS:
            res[m] = {}
            for ev in MODEL_EVENTS:
                s = df[df.event == ev]
                if group_iso:
                    s = s[s.iso3 == group_iso]
                mt = metrics(s.label, s[f"{pcol_prefix}{m}"])
                if pcol_prefix == "cal_":      # AUCs are rank-based: report them on raw scores
                    mr = metrics(s.label, s[f"raw_{m}"], brier=False)
                    mt["roc_auc"], mt["pr_auc"] = mr["roc_auc"], mr["pr_auc"]
                res[m][ev] = mt
            vals = [res[m][ev]["pr_auc"] for ev in MODEL_EVENTS if res[m][ev]["pr_auc"] is not None]
            res[m]["mean_pr_auc"] = round(float(np.mean(vals)), 3) if vals else None
            vals = [res[m][ev]["roc_auc"] for ev in MODEL_EVENTS if res[m][ev]["roc_auc"] is not None]
            res[m]["mean_roc_auc"] = round(float(np.mean(vals)), 3) if vals else None
            vals = [res[m][ev]["brier"] for ev in MODEL_EVENTS if res[m][ev]["brier"] is not None]
            res[m]["mean_brier"] = round(float(np.mean(vals)), 4) if vals else None
        return res

    cv_tab = table(ev_oof)
    season_tabs = {}
    for i in iso3s:
        s_ = ev_oof[ev_oof.iso3 == i]
        if s_["season"].nunique() > 1:          # bimodal: score each rainy season on its own
            nm = lambda m: "MAM long rains" if 2 <= m <= 6 else ("OND short rains" if 8 <= m <= 12 else f"core m{m}")
            season_tabs[i] = {}
            for key, g in s_.groupby(s_["anchor"].dt.month.map(nm)):
                season_tabs[i][key] = {m: {ev: metrics(g[g.event == ev].label, g[g.event == ev][f"cal_{m}"])
                                           for ev in MODEL_EVENTS} for m in MODELS}
                for m in MODELS:
                    for ev in MODEL_EVENTS:
                        mr = metrics(g[g.event == ev].label, g[g.event == ev][f"raw_{m}"], brier=False)
                        season_tabs[i][key][m][ev]["roc_auc"] = mr["roc_auc"]
                        season_tabs[i][key][m][ev]["pr_auc"] = mr["pr_auc"]
    winner = max(MODELS, key=lambda m: cv_tab[m]["mean_pr_auc"] or -1)
    bundle["winner"] = winner
    print(f"[{tag}] CV mean PR-AUC:", {m: cv_tab[m]["mean_pr_auc"] for m in MODELS}, "-> winner", winner)

    # per-lead CV (winner)
    by_lead = {}
    for L in EVAL_LEADS:
        s = ev_oof[ev_oof.lead == L]
        by_lead[L] = {ev: metrics(s[s.event == ev].label, s[s.event == ev][f"cal_{winner}"]) for ev in MODEL_EVENTS}
        for ev in MODEL_EVENTS:
            mr = metrics(s[s.event == ev].label, s[s.event == ev][f"raw_{winner}"], brier=False)
            by_lead[L][ev]["roc_auc"], by_lead[L][ev]["pr_auc"] = mr["roc_auc"], mr["pr_auc"]

    # thresholds tuned on CV OOF only (winner, leads 1-3)
    tw = ev_oof.rename(columns={f"cal_{winner}": "p_cal"})
    th = ae.rule_stats(tw)          # v1.1: levels come from the spec rule; nothing tuned
    bundle["thresholds"] = {}
    bundle["latency"] = dict(LATENCY)
    print(f"[{tag}] spec-rule CV stats:", th)

    # ---------------- hold-out: evaluated once with the final models
    ho = {}
    if len(te):
        parts = []
        for ev in MODEL_EVENTS:
            s = te[te.event == ev].copy()
            if not len(s):
                continue
            E = bundle["events"][ev]
            for m in MODELS:
                r_ = E["final"][m].raw(s)
                s[f"raw_{m}"], s[f"cal_{m}"] = r_, E["final_cal"][m].predict(r_)
            parts.append(s)
        tho = pd.concat(parts, ignore_index=True)
        tho_e = tho[tho.lead.isin(EVAL_LEADS)]
        ho["all"] = table(tho_e)
        for i in iso3s:
            if (tho_e.iso3 == i).any():
                ho[i] = table(tho_e, group_iso=i)
        tho.to_parquet(out_dir / f"holdout_{tag}.parquet", index=False)

    oof.to_parquet(out_dir / f"oof_{tag}.parquet", index=False)
    joblib.dump(bundle, out_dir / f"model_{tag}.joblib")
    (out_dir / f"thresholds_{tag}.json").write_text(json.dumps(th, indent=2))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for i in iso3s:
        mj = {"iso3": i, "trained_on": iso3s, "generated_at": now, "winner": winner,
              "selection": "highest mean CV PR-AUC over events (leads 1-3)",
              "cv_design": f"leave-one-agricultural-year-out {CV_FIRST}-{CV_LAST}, countries pooled",
              "holdout_design": "agyear>=2023 (2023/24 season) + KEN 2020-2022; final models, evaluated once",
              "labels": "satellite-only (v1.1): crop_failure >=2 of 3 months vci_crop<35 in core+1; no_grass >=2 of 3 "
                        "months vci_grass<35 in the 3 months after rains; cant_plant spi_1m<-1 & sm1_z<-1 in first 2 rainy months",
              "cv_pooled": cv_tab, "cv_this_country": table(ev_oof, group_iso=i) if (ev_oof.iso3 == i).any() else None,
              "cv_by_lead_winner": by_lead, "thresholds": th, "data_latency_months": LATENCY,
              "lead_definition": "lead L = months from issue month r to window start; features use only "
                                 "data published by end of r (signals of r-1), so data-to-window gap is L+1",
              "holdout": ho.get(i), "holdout_pooled": ho.get("all"),
              "cv_by_season": season_tabs.get(i),
              "dropped": "cant_plant model dropped: no CV skill (pre-latency run: ROC 0.485, PR-AUC 0.168 = base "
                         "0.168, Brier 0.146 > climatology 0.140). Kept only as a rule-based Watch reason."}
        (out_dir / f"metrics_{i}.json").write_text(json.dumps(mj, indent=2, default=str))
    write_report(out_dir, tag, iso3s, cv_tab, by_lead, winner, th, ho, cv, te, season_tabs)
    return bundle


def fmt_row(name, t):
    cells = []
    for ev in MODEL_EVENTS:
        x = t[ev]
        cells.append(f"{x['roc_auc'] if x['roc_auc'] is not None else '-'} / "
                     f"{x['pr_auc'] if x['pr_auc'] is not None else '-'} / {x['brier']} (base {x['pos_rate']})")
    return f"| {name} | " + " | ".join(cells) + f" | {t['mean_pr_auc']} |"


def write_report(out_dir, tag, iso3s, cv_tab, by_lead, winner, th, ho, cv, te, season_tabs=None):
    L = [f"# Model report ({tag})", "",
         f"Generated {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}. Countries pooled: {', '.join(iso3s)}.",
         f"CV: leave-one-agricultural-year-out {CV_FIRST}-{CV_LAST} ({cv.agyear.nunique()} folds, {len(cv)} rows incl. lead 0). "
         f"Hold-out: {len(te)} rows (agyear>=2023, KEN 2020-22), scored once with final models.",
         "Labels are satellite-only (VCI / SPI / soil moisture), not food-security outcomes.",
         f"Data latency modelled: {LATENCY} months. A value issued at month r uses only signals of month r-1 "
         "(CHIRPS final ~3 wk, MODIS 16-day ~1-2 wk, ERA5-Land via ERA5T/CDS ~5 days after month end). "
         "Lead L = months from issue to window start.",
         "Metrics: leads 1-3 months. Cells = ROC-AUC / PR-AUC / Brier (base rate). AUCs on raw scores, Brier on "
         "cross-fitted isotonic-calibrated probabilities.", "",
         "## Cross-validation (pooled)", "",
         "| model | " + " | ".join(MODEL_EVENTS) + " | mean PR-AUC |", "|---|" + "---|" * (len(MODEL_EVENTS) + 1)]
    for m in MODELS:
        L.append(fmt_row(m, cv_tab[m]))
    L += ["", f"**Winner (CV PR-AUC): {winner}**", "", "### Winner by lead (CV)", "",
          "| lead | " + " | ".join(MODEL_EVENTS) + " |", "|---|" + "---|" * len(MODEL_EVENTS)]
    for ld, t in by_lead.items():
        L.append(f"| {ld} | " + " | ".join(f"{t[e]['roc_auc']} / {t[e]['pr_auc']} / {t[e]['brier']}" for e in MODEL_EVENTS) + " |")
    L += ["", "cant_plant: model dropped (no CV skill: pre-latency ROC 0.485, PR-AUC 0.168 = base rate 0.168, "
          "Brier worse than climatology). It is now only a rule-based Watch reason (strong rain+soil dryness).", ""]
    for i, tabs in (season_tabs or {}).items():
        L += [f"### {i} CV by its own rainy seasons (winner {winner})", "",
              "| season | " + " | ".join(MODEL_EVENTS) + " |", "|---|" + "---|" * len(MODEL_EVENTS)]
        for key, t in tabs.items():
            L.append(f"| {key} | " + " | ".join(
                f"{t[winner][e]['roc_auc']} / {t[winner][e]['pr_auc']} / {t[winner][e]['brier']} (base {t[winner][e]['pos_rate']})"
                for e in MODEL_EVENTS) + " |")
        L.append("")
    L += ["", "## Spec alert rule vs satellite label on CV rows (informational; levels do not use p)", "", "```", json.dumps(th, indent=1), "```"]
    if ho:
        L += ["", "## Hold-out (evaluated once)", ""]
        for k, tab in ho.items():
            L += [f"### {k}", "", "| model | " + " | ".join(MODEL_EVENTS) + " | mean PR-AUC |",
                  "|---|" + "---|" * (len(MODEL_EVENTS) + 1)]
            for m in MODELS:
                L.append(fmt_row(m, tab[m]))
            L.append("")
        L.append("Caveat: the ZWE/MWI/ZMB hold-out is a single season in which most units were in drought; "
                 "AUC there only measures which units the model ranks worst, not whether it sees the year coming.")
    (out_dir / "model_report.md").write_text("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso3", nargs="+", required=True)
    ap.add_argument("--data-dir", default=str(DATA_DIR))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--tag", default=None)
    a = ap.parse_args()
    iso3s = [i.upper() for i in a.iso3]
    # call through the imported module so pickled model classes live in "train", not "__main__"
    import train as _self
    _self.run(iso3s, a.data_dir, Path(a.out_dir), a.tag or "_".join(iso3s))


if __name__ == "__main__":
    main()
