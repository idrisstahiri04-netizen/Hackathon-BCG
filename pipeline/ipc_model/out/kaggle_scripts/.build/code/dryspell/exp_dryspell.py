#!/usr/bin/env python3
"""Dry-spell feature experiment: the main model's leave-one-agyear-out CV with and without the four
dryspell_<ISO3>.parquet signals (dry_spell_max, days_since_rain, onset_anom, season_rain_pct).

    EXP_OUT=pipeline/out/dryspell python pipeline/dryspell/exp_dryspell.py          # Kaggle
    python pipeline/dryspell/exp_dryspell.py --smoke                                 # join check only

Reuses pipeline/experiments/harness.py (same folds, models, cross-fitted isotonic calibration and
metrics as train.py) and expand.py (training rows of the 10 extra countries, agyear < 2023 only).
Latency: a row issued at month r gets the dry-spell state of month r-1 (CHIRPS latency 1, as in
common.LATENCY). Hold-out rows (test=True) are never used by cv(); they are scored exactly once at
the end for the ZWE 2023/24 replay, with models fitted on CV rows only, and nothing is selected on them.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PIPE = HERE.parent
OUT = Path(os.environ.get("EXP_OUT", str(PIPE / "out" / "dryspell")))
os.environ["EXP_OUT"] = str(OUT)                 # harness / expand write their caches here
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(PIPE)); sys.path.insert(0, str(PIPE / "experiments"))
import harness as H                                        # noqa: E402
import train as T                                          # noqa: E402
from common import CV_FIRST, CV_LAST, DATA_DIR, LATENCY    # noqa: E402

DRY = ["dry_spell_max", "days_since_rain", "onset_anom", "season_rain_pct"]
CORE = ["ZWE", "KEN", "MWI", "ZMB"]
EXTRA = ["MOZ", "TZA", "ETH", "SOM", "NAM", "BWA", "ZAF", "MDG", "AGO", "UGA"]
MODELS = ("logreg", "lgbm", "ensemble")
EVENTS2 = list(T.MODEL_EVENTS)          # crop_failure, no_grass (cant_plant has no model)
LEADS = list(T.EVAL_LEADS)              # 1, 2, 3


def log(*a):
    print(f"[{dt.datetime.now(dt.timezone.utc).strftime('%H:%M:%S')}]", *a, flush=True)


# ----------------------------------------------------------------------------- data
def load_dry(iso3s, data_dir=DATA_DIR) -> pd.DataFrame:
    parts = []
    for i in iso3s:
        f = Path(data_dir) / f"dryspell_{i}.parquet"
        if f.exists():
            parts.append(pd.read_parquet(f))
        else:
            log(f"!! missing {f.name}")
    d = pd.concat(parts, ignore_index=True)
    d["month"] = pd.to_datetime(d["month"])
    return d.pivot_table(index=["unit_id", "month"], columns="signal_type", values="value").reindex(columns=DRY)


def join_dry(rows: pd.DataFrame, wide: pd.DataFrame) -> pd.DataFrame:
    """Dry-spell state of month r - LATENCY['chirps'] joined at the issue month r."""
    rows = rows.copy()
    idx = pd.MultiIndex.from_arrays([rows["unit_id"], rows["r"] - pd.DateOffset(months=LATENCY["chirps"])])
    X = wide.reindex(idx)
    for c in DRY:
        rows[c] = X[c].values
    return rows


def coverage(rows: pd.DataFrame) -> dict:
    cv = rows[~rows.test & rows.agyear.between(CV_FIRST, CV_LAST) & rows.lead.isin(LEADS) & rows.label.notna()]
    out = {}
    for ev in EVENTS2:
        s = cv[cv.event == ev]
        out[ev] = {c: round(float(s[c].notna().mean()), 3) for c in DRY} | {"n": int(len(s))}
    return out


# ----------------------------------------------------------------------------- metrics
def tab(oof: pd.DataFrame, model: str, leads=LEADS, iso3s=None) -> dict:
    s = oof[oof.lead.isin(leads)]
    if iso3s:
        s = s[s.iso3.isin(iso3s)]
    res = {}
    for ev in EVENTS2:
        x = s[s.event == ev]
        m = T.metrics(x.label, x[f"cal_{model}"])
        mr = T.metrics(x.label, x[f"raw_{model}"], brier=False)
        m["roc_auc"], m["pr_auc"] = mr["roc_auc"], mr["pr_auc"]
        res[ev] = m
    return res


def delta(a: dict, b: dict) -> dict:
    out = {}
    for ev in EVENTS2:
        out[ev] = {}
        for k in ("roc_auc", "pr_auc", "brier"):
            va, vb = a[ev].get(k), b[ev].get(k)
            out[ev][k] = None if va is None or vb is None else round(vb - va, 4)
        out[ev]["n"] = b[ev]["n"]
    return out


def compare(oof_b: pd.DataFrame, oof_d: pd.DataFrame, iso3s=None) -> dict:
    """base vs dry: pooled over leads 1-3, per lead, for each model."""
    res = {}
    for m in MODELS:
        b, d = tab(oof_b, m, iso3s=iso3s), tab(oof_d, m, iso3s=iso3s)
        res[m] = {"base": b, "dry": d, "delta": delta(b, d), "by_lead": {}}
        for L in LEADS:
            bl, dl = tab(oof_b, m, leads=[L], iso3s=iso3s), tab(oof_d, m, leads=[L], iso3s=iso3s)
            res[m]["by_lead"][L] = {"base": bl, "dry": dl, "delta": delta(bl, dl)}
    return res


def fmt(x, nd=3):
    """nd=4 is only used for deltas -> signed."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "-"
    return f"{x:+.{nd}f}" if nd == 4 else f"{x:.{nd}f}"


def md_compare(title: str, res: dict, model="ensemble") -> list[str]:
    r = res[model]
    L = [f"### {title} ({model})", "", "| event | lead | ROC base -> dry (d) | PR-AUC base -> dry (d) | Brier base -> dry (d) | n |", "|---|---|---|---|---|---|"]
    for ev in EVENTS2:
        rows_ = [("1-3", r["base"][ev], r["dry"][ev], r["delta"][ev])] + \
                [(str(Ld), r["by_lead"][Ld]["base"][ev], r["by_lead"][Ld]["dry"][ev], r["by_lead"][Ld]["delta"][ev]) for Ld in LEADS]
        for lead, b, d, dd in rows_:
            cells = []
            for k in ("roc_auc", "pr_auc", "brier"):
                cells.append(f"{fmt(b[k])} -> {fmt(d[k])} ({fmt(dd[k], 4)})" if b.get(k) is not None else "-")
            L.append(f"| {ev} | {lead} | " + " | ".join(cells) + f" | {d['n']} |")
    L.append("")
    return L


# ----------------------------------------------------------------------------- replay (hold-out, once)
def final_fit(rows: pd.DataFrame, cols: list, ev: str, oof: pd.DataFrame):
    d = rows[~rows.test & rows.agyear.between(CV_FIRST, CV_LAST) & rows.lead.isin(T.TRAIN_LEADS) & (rows.event == ev)]
    d = d.dropna(subset=["label"])
    y = d["label"].values.astype(int)
    lr = T.LogReg(cols).fit(d, y)
    gb = T.LGBM(cols).fit(d, y)
    ens = T.Ensemble(lr, gb)
    o = oof[oof.event == ev].dropna(subset=["raw_ensemble"])
    cal = T.iso(o["raw_ensemble"].values, o["label"].values)
    return lr, gb, ens, cal


def importance(lr, gb, cols: list) -> dict:
    gain = gb.b.feature_importance("gain")
    tot = gain.sum() or 1.0
    coef = lr.m[-1].coef_[0]
    return {c: {"lgbm_gain_share": round(float(gain[cols.index(c)] / tot), 4),
                "logreg_std_coef": round(float(coef[cols.index(c)]), 4)} for c in DRY if c in cols}


def replay(rows: pd.DataFrame, cols: list, oof_b: pd.DataFrame, oof_d: pd.DataFrame, iso3="ZWE", agyear=2023) -> dict:
    """ZWE 2023/24 hold-out rows scored once with base and dry models fitted on CV rows only."""
    te = rows[rows.test & (rows.iso3 == iso3) & (rows.agyear == agyear) & rows.event.isin(EVENTS2) & rows.lead.isin([0, 1, 2, 3])].copy()
    te = te.dropna(subset=["label"])
    out = {"n_rows": int(len(te)), "by_event": {}, "importance": {}}
    series = []
    for ev in EVENTS2:
        s = te[te.event == ev].copy()
        if not len(s):
            continue
        lr_b, gb_b, ens_b, cal_b = final_fit(rows, cols, ev, oof_b)
        lr_d, gb_d, ens_d, cal_d = final_fit(rows, cols + DRY, ev, oof_d)
        s["p_base"] = cal_b.predict(ens_b.raw(s)); s["raw_base"] = ens_b.raw(s)
        s["p_dry"] = cal_d.predict(ens_d.raw(s)); s["raw_dry"] = ens_d.raw(s)
        out["importance"][ev] = importance(lr_d, gb_d, cols + DRY)
        e = s[s.lead.isin(LEADS)]
        mb, md = T.metrics(e.label, e.p_base), T.metrics(e.label, e.p_dry)
        mb_r, md_r = T.metrics(e.label, e.raw_base, brier=False), T.metrics(e.label, e.raw_dry, brier=False)
        mb["roc_auc"], mb["pr_auc"], md["roc_auc"], md["pr_auc"] = mb_r["roc_auc"], mb_r["pr_auc"], md_r["roc_auc"], md_r["pr_auc"]
        out["by_event"][ev] = {"holdout_base": mb, "holdout_dry": md}
        g = s.groupby(["lead", "r"])
        t = pd.DataFrame({"n": g.size(), "label_rate": g.label.mean(),
                          "p_base_mean": g.p_base.mean(), "p_dry_mean": g.p_dry.mean(),
                          "p_base_med": g.p_base.median(), "p_dry_med": g.p_dry.median(),
                          "share_base_ge50": g.p_base.apply(lambda x: (x >= 0.5).mean()),
                          "share_dry_ge50": g.p_dry.apply(lambda x: (x >= 0.5).mean())}).reset_index()
        t["event"] = ev
        for c in DRY:
            t[c + "_med"] = g[c].median().values
        series.append(t)
    ser = pd.concat(series, ignore_index=True) if series else pd.DataFrame()
    ser.to_csv(OUT / f"replay_{iso3}_{agyear}.csv", index=False)
    out["series_csv"] = f"replay_{iso3}_{agyear}.csv"
    return out, ser


def md_replay(ser: pd.DataFrame, iso3: str) -> list[str]:
    L = [f"### {iso3} 2023/24 replay (hold-out, scored once; ensemble, isotonic-calibrated p)", "",
         "Per issue month r (end of month, using data of r-1): mean p over units and share of units with p >= 0.5, base vs with dry-spell features; medians of the dry-spell features the model saw.", "",
         "| event | lead | r | n | label rate | p base | p dry | >=0.5 base | >=0.5 dry | dry_spell_max | days_since_rain | onset_anom | season_rain_pct |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, x in ser.sort_values(["event", "lead", "r"]).iterrows():
        L.append(f"| {x.event} | {int(x.lead)} | {pd.Timestamp(x.r):%Y-%m} | {int(x.n)} | {x.label_rate:.2f} | {x.p_base_mean:.3f} | {x.p_dry_mean:.3f} | "
                 f"{x.share_base_ge50:.2f} | {x.share_dry_ge50:.2f} | {fmt(x.dry_spell_max_med, 1)} | {fmt(x.days_since_rain_med, 1)} | {fmt(x.onset_anom_med, 1)} | {fmt(x.season_rain_pct_med, 0)} |")
    L.append("")
    return L


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="build ZWE rows, join, print coverage; no CV")
    ap.add_argument("--n-jobs", type=int, default=4)
    a = ap.parse_args()
    t0 = time.time()
    H.N_JOBS = a.n_jobs

    if a.smoke:
        import harness as H2
        H2.ROWS = OUT / "rows_smoke.parquet"; H2.FEAT = OUT / "feat_smoke.parquet"
        rows, cols = H2.build(["ZWE"])
        wide = load_dry(["ZWE"])
        rows = join_dry(rows, wide)
        print("coverage on CV rows:", json.dumps(coverage(rows), indent=1))
        print(rows[(rows.iso3 == "ZWE") & (rows.agyear == 2023) & (rows.event == "no_grass") & (rows.lead == 1)][["unit_id", "r", "W0"] + DRY].head())
        return

    # 1. rows: core 4 (harness.build) + 10 extra training countries (expand.main)
    if (OUT / "rows_base.parquet").exists() and (OUT / "cols_base.json").exists():
        rows4, cols = H.load()
    else:
        rows4, cols = H.build(CORE)
    log(f"core rows {len(rows4)} cols {len(cols)} ({time.time() - t0:.0f}s)")
    import expand
    if not (OUT / "rows_extra.parquet").exists():
        expand.main(EXTRA)
    rowsX = pd.read_parquet(OUT / "rows_extra.parquet")
    log(f"extra rows {len(rowsX)} countries {sorted(rowsX.iso3.unique())} ({time.time() - t0:.0f}s)")

    # 2. dry-spell features at r - 1
    wide = load_dry(CORE + EXTRA)
    rows4 = join_dry(rows4, wide)
    rowsX = join_dry(rowsX, wide)
    rows14 = pd.concat([rows4, rowsX], ignore_index=True)
    cov = {"core4": coverage(rows4), "all14": coverage(rows14)}
    log("coverage:", json.dumps(cov))

    # 3. CV with / without
    results = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "latency": LATENCY,
               "dry_features": DRY, "n_base_cols": len(cols), "coverage": cov, "cv": {}}
    oofs = {}
    for name, rows in (("core4", rows4), ("all14", rows14)):
        for variant, cc in (("base", cols), ("dry", cols + DRY)):
            log(f"cv {name} {variant} ...")
            oof = H.cv(rows, cc, models=MODELS, events=EVENTS2, n_jobs=a.n_jobs)
            oof.to_parquet(OUT / f"oof_{name}_{variant}.parquet", index=False)
            oofs[(name, variant)] = oof
            log(f"cv {name} {variant} done rows={len(oof)} ({time.time() - t0:.0f}s)")
        res = {"pooled": compare(oofs[(name, "base")], oofs[(name, "dry")])}
        if name == "all14":
            res["core4_subset"] = compare(oofs[(name, "base")], oofs[(name, "dry")], iso3s=CORE)
        res["by_country"] = {i: compare(oofs[(name, "base")], oofs[(name, "dry")], iso3s=[i]) for i in CORE}
        results["cv"][name] = res
        (OUT / "results.json").write_text(json.dumps(results, indent=1, default=str))

    # 4. replay (hold-out, once) with core-4 models
    log("replay ZWE 2023/24 ...")
    rep, ser = replay(rows4, cols, oofs[("core4", "base")], oofs[("core4", "dry")])
    results["replay_ZWE_2023"] = rep
    (OUT / "results.json").write_text(json.dumps(results, indent=1, default=str))

    # 5. markdown
    L = [f"# Dry-spell features: CV with vs without (generated {results['generated_at']})", "",
         f"Base feature columns: {len(cols)}; added: {', '.join(DRY)} (joined at r-{LATENCY['chirps']}). "
         f"Folds: leave-one-agyear-out {CV_FIRST}-{CV_LAST}; metrics on leads 1-3; AUCs on raw scores, Brier on cross-fitted isotonic p. "
         "d = dry - base.", "", "Coverage (share of CV rows with the feature present):", "```", json.dumps(cov, indent=1), "```", ""]
    for name, title in (("core4", "Pooled ZWE+KEN+MWI+ZMB (train + eval on 4)"), ("all14", "Pooled 14 countries (train + eval on 14)")):
        for m in MODELS:
            L += md_compare(f"{title}", results["cv"][name]["pooled"], model=m)
    L += md_compare("Pooled 14 countries, evaluated on the 4 core countries only", results["cv"]["all14"]["core4_subset"])
    for i in CORE:
        L += md_compare(f"core4 model, {i} rows only", results["cv"]["core4"]["by_country"][i])
    L += ["### Dry-spell feature importance in the final core-4 'dry' models (fitted on CV rows)", "", "```",
          json.dumps(rep["importance"], indent=1), "```", "",
          "### ZWE 2023/24 hold-out metrics (leads 1-3, scored once)", "", "```", json.dumps(rep["by_event"], indent=1), "```", ""]
    L += md_replay(ser, "ZWE")
    (OUT / "summary.md").write_text("\n".join(L) + "\n")
    log(f"done ({time.time() - t0:.0f}s) -> {OUT}")


if __name__ == "__main__":
    main()
