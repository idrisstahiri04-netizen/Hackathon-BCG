"""ML-expert experiment B: spatial / neighbour features + Malawi-specific behaviour for Model A
(satellite labels crop_failure / no_grass, leave-one-agyear-out CV 2001-2022, leads 1-3, latency applied).

Runs on Kaggle (scripts/kaggle/run.sh, KERNEL_SLUG=drought-xml); the repo file lives in pipeline/experts/ml/
and is staged into pipeline/experiments/ by pipeline/experts/ml/run_kaggle.sh (push_code.sh only bundles
that directory). Imports resolve from wherever the file sits.

Reuses the experiment harness (same folds, cross-fitted isotonic calibration, metrics) -> deltas are honest.
Hold-out (agyear >= 2023, KEN 2020-22) is scored ONCE for one configuration declared here before any
result is seen: PICK = best CV mean PR-AUC among {nb, nat, nb_nat} (never among the Malawi variants).

Experiments
  base          current features (5 models incl. persistence / rule)                    reference
  nb            + neighbour-mean of 9 signals at r-1 (queen contiguity, NaN-aware)
  nat           + country-wide mean of the same signals at r-1 (regional anomaly)
  nb_nat        + both + own-minus-neighbour differences (spi_3m, vci, sm1_z)
  nb_nat_oni    nb_nat + ONI x south (best prior extra) -> additivity check
  nb_nat_prev   nb_nat + neighbours' previous-season label mean (spatial persistence)
  percountry    base features, one model per country (group_fn = iso3)              Malawi question
  iso_onehot    base features + country dummies (fixed effects)                      Malawi question
Outputs (EXP_OUT, default pipeline/out/xml): xml_spatial_results.json, xml_spatial_tables.md, oof_xml_*.parquet
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
P = HERE
while not (P / "common.py").exists() and P != P.parent:
    P = P.parent
PIPE = P
EXP = PIPE / "experiments"
OUT = Path(os.environ.get("EXP_OUT", str(PIPE / "out" / "xml")))
OUT.mkdir(parents=True, exist_ok=True)
os.environ["EXP_OUT"] = str(OUT)          # harness / extra_features read it at import
for p in (str(HERE), str(EXP), str(PIPE)):
    if p not in sys.path:
        sys.path.insert(0, p)
import harness as H            # noqa: E402
import harness_ext as HX       # noqa: E402
import extra_features as X     # noqa: E402
import train as T              # noqa: E402

EV2 = ["crop_failure", "no_grass"]
MODELS = ("logreg", "lgbm", "ensemble")
ALLM = ("persistence", "rule", "logreg", "lgbm", "ensemble")
ISOS = ["ZWE", "KEN", "MWI", "ZMB"]
SIGS_NB = ["spi_1m", "spi_3m", "spi_6m", "ndvi_z_crop", "ndvi_z_grass", "vci_crop", "vci_grass", "sm1_z", "t2m_z"]
LAT = 1                                   # satellite latency: unit-month features joined at r-1 (as extra_features)
NB_FILE = HERE / "xml_neighbours.json"
PICK_CANDIDATES = ["nb", "nat", "nb_nat"]  # hold-out candidates, declared before results
N_JOBS = int(os.environ.get("XML_NJOBS", "4"))
H.N_JOBS = N_JOBS


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


# ----------------------------------------------------------------------------- spatial features
def spatial_unit_month(w: pd.DataFrame, nbmap: dict) -> pd.DataFrame:
    """Per (unit_id, month): nb_<s> = NaN-aware mean over contiguity neighbours, nat_<s> = country mean."""
    w = w.copy()
    w["month"] = pd.to_datetime(w["month"])
    parts = []
    for iso, wi in w.groupby("iso3"):
        units = sorted(wi.unit_id.unique())
        pos = {u: i for i, u in enumerate(units)}
        A = np.zeros((len(units), len(units)))
        for u in units:
            for v in nbmap.get(u, {}).get("nb", []):
                if v in pos:
                    A[pos[u], pos[v]] = 1.0
        out, months = {}, None
        for s in SIGS_NB:
            M = wi.pivot(index="month", columns="unit_id", values=s).reindex(columns=units)
            months = M.index
            V = M.values.astype(float)
            ok = ~np.isnan(V)
            num = np.where(ok, V, 0.0) @ A.T
            den = ok.astype(float) @ A.T
            with np.errstate(invalid="ignore", divide="ignore"):
                nb = np.where(den > 0, num / den, np.nan)
                nat = np.where(ok.sum(1) > 0, np.nansum(V, 1) / np.maximum(ok.sum(1), 1), np.nan)
            out[f"nb_{s}"] = nb.ravel()                                    # month-major, unit-minor
            out[f"nat_{s}"] = np.repeat(nat[:, None], len(units), 1).ravel()
        f = pd.DataFrame(out)
        f["month"] = np.repeat(months.values, len(units))
        f["unit_id"] = np.tile(np.array(units, dtype=object), len(months))
        parts.append(f)
    return pd.concat(parts, ignore_index=True).set_index(["unit_id", "month"])


def join_spatial(rows: pd.DataFrame, sp: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    rows = rows.copy()
    idx = pd.MultiIndex.from_arrays([rows["unit_id"], rows["r"] - pd.DateOffset(months=LAT)])
    J = sp.reindex(idx)
    nb_cols = [c for c in sp.columns if c.startswith("nb_")]
    nat_cols = [c for c in sp.columns if c.startswith("nat_")]
    for c in sp.columns:
        rows[c] = J[c].values
    dif = []
    for s in ("spi_3m", "vci_crop", "vci_grass", "sm1_z"):
        rows[f"dif_{s}"] = rows[s] - rows[f"nb_{s}"]
        dif.append(f"dif_{s}")
    return rows, {"nb": nb_cols, "nat": nat_cols, "dif": dif}


def neighbour_prev_label(rows: pd.DataFrame, nbmap: dict) -> pd.Series:
    """Mean of neighbours' previous-season label for the same event/season instance (known before r)."""
    key = rows[["unit_id", "event", "anchor" if "anchor" in rows else "W0", "prev_label"]].copy()
    kcol = "anchor" if "anchor" in rows else "W0"
    tab = key.drop_duplicates(["unit_id", "event", kcol]).set_index(["unit_id", "event", kcol])["prev_label"]
    out = np.full(len(rows), np.nan)
    d = tab.to_dict()
    for i, (u, e, k) in enumerate(zip(rows["unit_id"], rows["event"], rows[kcol])):
        vals = [d.get((v, e, k)) for v in nbmap.get(u, {}).get("nb", [])]
        vals = [x for x in vals if x is not None and not (isinstance(x, float) and np.isnan(x))]
        if vals:
            out[i] = float(np.mean(vals))
    return pd.Series(out, index=rows.index)


# ----------------------------------------------------------------------------- tables
def tab_all(oof: pd.DataFrame, models, leads=(1, 2, 3)) -> dict:
    res = {"pooled": H.table(oof, models=models, leads=list(leads))}
    for iso in ISOS:
        if (oof.iso3 == iso).any():
            res[iso] = H.table(oof, models=models, leads=list(leads), iso3=iso)
    res["by_lead"] = {L: H.table(oof, models=models, leads=[L]) for L in leads}
    return res


def m2(t: dict, m: str, key="pr_auc") -> float | None:
    v = [t[m][e][key] for e in EV2 if t[m][e].get(key) is not None]
    return round(float(np.mean(v)), 4) if v else None


def fmt(t, m, iso_tab=None):
    s = []
    for e in EV2:
        x = t[m][e]
        s.append(f"{x['roc_auc']} / {x['pr_auc']} / {x['brier']} (b {x['pos_rate']})")
    return " | ".join(s)


def md_block(name: str, res: dict, base: dict | None, models) -> list[str]:
    L = [f"### {name}", "", "| scope | model | crop_failure ROC/PR/Brier | no_grass ROC/PR/Brier | mean PR | d mean PR vs base |",
         "|---|---|---|---|---|---|"]
    for scope in ["pooled"] + ISOS:
        if scope not in res:
            continue
        for m in models:
            mp = m2(res[scope], m)
            d = ""
            if base and scope in base and m in base[scope]:
                bp = m2(base[scope], m)
                if mp is not None and bp is not None:
                    d = f"{mp - bp:+.4f}"
            L.append(f"| {scope} | {m} | {fmt(res[scope], m)} | {mp} | {d} |")
    L.append("")
    L.append("| lead | " + " | ".join(f"{m} crop ROC/PR; grass ROC/PR" for m in models) + " |")
    L.append("|---|" + "---|" * len(models))
    for Ld, t in res["by_lead"].items():
        cells = []
        for m in models:
            cells.append("; ".join(f"{t[m][e]['roc_auc']}/{t[m][e]['pr_auc']}" for e in EV2))
        L.append(f"| {Ld} | " + " | ".join(cells) + " |")
    L.append("")
    return L


# ----------------------------------------------------------------------------- hold-out once
def holdout_once(rows_tr: pd.DataFrame, rows_te: pd.DataFrame, cols_lr, cols_gb, oof: pd.DataFrame) -> dict:
    """Final models on all CV rows (leads 0-3), test rows leads 1-3, calibration from CV OOF. Scored once."""
    out = {}
    parts = []
    for ev in EV2:
        d = rows_tr[(rows_tr.event == ev)].dropna(subset=["label"])
        ms = HX._fit2(d, cols_lr, cols_gb, None, None, None)
        s = rows_te[(rows_te.event == ev) & rows_te.lead.isin([1, 2, 3])].dropna(subset=["label"]).copy()
        o = oof[oof.event == ev]
        for m in MODELS:
            raw = ms[m].raw(s) if m != "ensemble" else 0.5 * (ms["logreg"].raw(s) + ms["lgbm"].raw(s))
            ok = o[f"raw_{m}"].notna()
            cal = T.iso(o.loc[ok, f"raw_{m}"].values, o.loc[ok, "label"].values).predict(raw)
            s[f"raw_{m}"], s[f"cal_{m}"] = raw, cal
        parts.append(s)
    te = pd.concat(parts, ignore_index=True)
    out["pooled"] = H.table(te, models=MODELS, leads=[1, 2, 3])
    for iso in ISOS:
        if (te.iso3 == iso).any():
            out[iso] = H.table(te, models=MODELS, leads=[1, 2, 3], iso3=iso)
    return out, te


# ----------------------------------------------------------------------------- main
def main():
    t0 = time.time()
    if not (OUT / "rows_base.parquet").exists():
        log("building rows (harness.build) ...")
        H.build()
    rows, cols = H.load()
    rows["r"] = pd.to_datetime(rows["r"]); rows["W0"] = pd.to_datetime(rows["W0"])
    if "anchor" in rows:
        rows["anchor"] = pd.to_datetime(rows["anchor"])
    nbmap = json.loads(NB_FILE.read_text())["units"]
    log(f"rows {rows.shape}, cols {len(cols)}, neighbours for {len(nbmap)} units")

    w = pd.read_parquet(OUT / "wide_base.parquet")
    sp = spatial_unit_month(w, nbmap)
    rows, grp = join_spatial(rows, sp)
    rows["nb_prev_label"] = neighbour_prev_label(rows, nbmap)
    for iso in ISOS:
        rows[f"iso_{iso}"] = (rows.iso3 == iso).astype(float)
    rows, oni_cols = X.with_extra(rows, ["oni_south"])
    log(f"spatial features joined: {len(grp['nb'])} nb, {len(grp['nat'])} nat, {len(grp['dif'])} dif; "
        f"nb NaN share {rows[grp['nb']].isna().mean().mean():.3f}")

    results, md = {}, ["# ML-expert experiment B: spatial / neighbour features and Malawi (Model A)", "",
                       f"Generated {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}. Rows: {len(rows)} (leads 0-6 built, "
                       f"train leads {H.TRAIN_LEADS}, eval leads 1-3). CV = leave-one-agyear-out 2001-2022 pooled "
                       f"{ISOS}; cross-fitted isotonic; AUCs on raw scores, Brier on calibrated p. "
                       "Hold-out never used except the single declared PICK at the end.", ""]
    cvr = rows[~rows.test & rows.agyear.between(H.CV_FIRST, H.CV_LAST)]
    # Malawi label diagnostics (CV years only)
    mw = cvr[(cvr.iso3 == "MWI") & (cvr.lead == 1)].dropna(subset=["label"])
    results["mwi_label_prevalence_by_agyear"] = mw.groupby(["agyear", "event"]).label.mean().unstack().round(2).to_dict()
    results["label_prevalence_by_country"] = cvr[cvr.lead == 1].dropna(subset=["label"]).groupby(["iso3", "event"]).label.mean().round(3).unstack().to_dict()

    # ---- base (all 5 models)
    log("exp base")
    oof = H.cv(rows, cols, models=ALLM, events=EV2, n_jobs=N_JOBS)
    oof.to_parquet(OUT / "oof_xml_base.parquet", index=False)
    base = tab_all(oof, ALLM)
    results["base"] = base
    md += md_block("base (current features; reference)", base, None, ALLM)
    oofs = {"base": oof}

    def dump():      # incremental: a crash in a later step must not lose earlier results
        (OUT / "xml_spatial_results.json").write_text(json.dumps(results, indent=1, default=str))
        (OUT / "xml_spatial_tables.md").write_text("\n".join(md))
    dump()

    skip = set(filter(None, os.environ.get("XML_SKIP", "").split(",")))
    specs = {
        "nb": (cols + grp["nb"], cols + grp["nb"]),
        "nat": (cols + grp["nat"], cols + grp["nat"]),
        "nb_nat": (cols + grp["nb"] + grp["nat"] + grp["dif"], cols + grp["nb"] + grp["nat"] + grp["dif"]),
        "nb_nat_oni": (cols + grp["nb"] + grp["nat"] + grp["dif"] + oni_cols, cols + grp["nb"] + grp["nat"] + grp["dif"] + oni_cols),
        "nb_nat_prev": (cols + grp["nb"] + grp["nat"] + grp["dif"] + ["nb_prev_label"], cols + grp["nb"] + grp["nat"] + grp["dif"] + ["nb_prev_label"]),
        "iso_onehot": (cols + [f"iso_{i}" for i in ISOS], cols + [f"iso_{i}" for i in ISOS]),
    }
    for name, (cl, cg) in specs.items():
        if name in skip:
            log(f"skip {name} (XML_SKIP)"); continue
        log(f"exp {name} ({len(cg)} gb cols)")
        o = HX.cv2(rows, cl, cg, events=EV2, n_jobs=N_JOBS)
        o.to_parquet(OUT / f"oof_xml_{name}.parquet", index=False)
        r = tab_all(o, MODELS)
        results[name] = r
        oofs[name] = o
        md += md_block(name, r, base, MODELS)
        log(f"   {name}: ens mean PR {m2(r['pooled'], 'ensemble')} (base {m2(base['pooled'], 'ensemble')}); "
            f"MWI ens {m2(r.get('MWI', {}), 'ensemble') if 'MWI' in r else None} (base {m2(base['MWI'], 'ensemble')})")
        dump()
    # ---- per-country models (Malawi question): one H.cv per country (own folds, own cross-fitted calibration)
    if "percountry" not in skip:
        log("exp percountry")
        parts = []
        for iso in ISOS:
            try:
                parts.append(H.cv(rows[rows.iso3 == iso], cols, models=MODELS, events=EV2, n_jobs=N_JOBS))
            except Exception as e:          # e.g. a country/event with too few positives in some fold
                log(f"   percountry {iso} failed: {e!r}")
        if parts:
            o = pd.concat(parts, ignore_index=True)
            o.to_parquet(OUT / "oof_xml_percountry.parquet", index=False)
            r = tab_all(o, MODELS)
            results["percountry"] = r
            md += md_block("percountry (one model per country, per-country calibration)", r, base, MODELS)
            log(f"   percountry: MWI ens {m2(r['MWI'], 'ensemble') if 'MWI' in r else None} (base {m2(base['MWI'], 'ensemble')})")
            dump()

    # ---- per-country isotonic calibration of the base ensemble (Brier only; AUC unchanged)
    o = oofs["base"]
    bc = {}
    for iso in ISOS:
        s = o[(o.iso3 == iso) & o.lead.isin([1, 2, 3])]
        for ev in EV2:
            x = s[s.event == ev].dropna(subset=["raw_ensemble"])
            # cross-fitted by agyear inside the country
            cal = np.full(len(x), np.nan)
            for yv in sorted(x.agyear.unique()):
                va = (x.agyear == yv).values
                if (~va).sum() > 50 and x.label.values[~va].sum() > 0:
                    cal[va] = T.iso(x.raw_ensemble.values[~va], x.label.values[~va]).predict(x.raw_ensemble.values[va])
            ok = ~np.isnan(cal)
            bc[f"{iso}:{ev}"] = {"brier_pooled_cal": T.metrics(x.label, x.cal_ensemble)["brier"],
                                 "brier_country_cal": round(float(np.mean((cal[ok] - x.label.values[ok]) ** 2)), 4) if ok.any() else None}
    results["country_calibration_base_ensemble"] = bc

    # ---- hold-out ONCE for the declared pick
    cands = {k: m2(results[k]["pooled"], "ensemble") for k in PICK_CANDIDATES}
    pick = max(cands, key=lambda k: cands[k] if cands[k] is not None else -1)
    results["holdout_pick"] = {"candidates": cands, "pick": pick}
    log(f"hold-out once: pick={pick} ({cands})")
    tr = rows[~rows.test & rows.agyear.between(H.CV_FIRST, H.CV_LAST) & rows.lead.isin(H.TRAIN_LEADS)]
    te = rows[rows.test]
    ho_base, _ = holdout_once(tr, te, cols, cols, oofs["base"])
    ho_pick, te_pick = holdout_once(tr, te, specs[pick][0], specs[pick][1], oofs[pick])
    te_pick.to_parquet(OUT / f"holdout_xml_{pick}.parquet", index=False)
    results["holdout_base"] = ho_base
    results[f"holdout_{pick}"] = ho_pick
    md += ["## Hold-out (scored once; 2023/24 all + KEN 2020-22; final models on CV rows)", "",
           f"Pick declared before results: best CV ensemble mean PR among {PICK_CANDIDATES} -> **{pick}** ({cands}).", "",
           "| scope | model | base crop ROC/PR | base grass ROC/PR | pick crop ROC/PR | pick grass ROC/PR | d mean PR |", "|---|---|---|---|---|---|---|"]
    for scope in ["pooled"] + ISOS:
        if scope not in ho_base:
            continue
        for m in MODELS:
            b, p = ho_base[scope][m], ho_pick[scope][m]
            d = (m2(ho_pick[scope], m) or 0) - (m2(ho_base[scope], m) or 0)
            md.append(f"| {scope} | {m} | {b['crop_failure']['roc_auc']}/{b['crop_failure']['pr_auc']} | {b['no_grass']['roc_auc']}/{b['no_grass']['pr_auc']} | "
                      f"{p['crop_failure']['roc_auc']}/{p['crop_failure']['pr_auc']} | {p['no_grass']['roc_auc']}/{p['no_grass']['pr_auc']} | {d:+.4f} |")
    md += ["", "## Malawi diagnostics", "", "Label prevalence (lead 1, CV years) by agyear:", "", "```",
           json.dumps(results["mwi_label_prevalence_by_agyear"], indent=0, default=str), "```", "",
           "Per-country isotonic vs pooled calibration (base ensemble, Brier):", "", "```", json.dumps(bc, indent=0), "```", ""]
    results["seconds"] = round(time.time() - t0, 1)
    (OUT / "xml_spatial_results.json").write_text(json.dumps(results, indent=1, default=str))
    (OUT / "xml_spatial_tables.md").write_text("\n".join(md))
    log(f"done in {results['seconds']} s -> {OUT}")
    print("\n".join(md[:12]))


if __name__ == "__main__":
    main()
