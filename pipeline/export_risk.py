"""Export monthly risk for the frontend: data/risk/<ISO3>.js (CONTRACT.md section 3).

    python pipeline/export_risk.py --iso3 ZWE [--model pipeline/out/model_ZWE_KEN_MWI_ZMB.joblib]

Every month shown is out-of-sample: months whose season instance falls in a CV year are scored by
that year's leave-one-season-out fold model (+ its cross-fitted calibrator); hold-out seasons
(agyear >= 2023, KEN 2020-22) by the final model. Nothing in the frontend timeline is in-sample.

Per unit and month r, the candidate events are the upcoming or ongoing windows of each event
(window start W0 with -(len-1) <= W0 - r <= 3; lead feature clipped to 0..3). p = max calibrated
probability over candidates; event = the event giving that p (so event follows the season phase).
Months with no window within 3 months (short off-season) use the next window up to 6 months ahead
with lead clipped to 3 and get confidence "low".
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

import alert_engine as ae
from common import (LATENCY, COUNTRIES, N_MONTHS, OUT_DIR, RISK_DIR, ROOT, START_YEAR, DATA_DIR, WINDOW_LEN,
                    EVENTS, EVENT_PRIORITY, agyear, is_test, months_between, season_instances)
from features import attach
from train import MODEL_EVENTS, SIG_AT_R, add_families, crop_dominant, prepare_country

FAST_ENTRY = False          # spec: no 1-run escalation; set True only after a spec change
WARMUP = 12                 # months of hysteresis warm-up before Jan 2019


def candidates(P: dict, months: pd.DatetimeIndex) -> pd.DataFrame:
    t = P["targets"].set_index(["unit_id", "event", "W0"])["prev_label"]
    rows = []
    for u, ss in P["ss"].items():
        inst = season_instances(ss, months.min().year, months.max().year + 1)
        wins = [(e, getattr(it, e), int(it.agyear)) for it in inst.itertuples(index=False) for e in MODEL_EVENTS]
        for r in months:
            cand = []
            for e, W0, ag in wins:
                d = months_between(r, W0)
                if -(WINDOW_LEN[e] - 1) <= d <= 6:
                    cand.append((e, W0, d, ag))
            near = [c for c in cand if c[2] <= 3]
            far = not near
            use = near or sorted(cand, key=lambda c: c[2])[:1]
            for e, W0, d, ag in use:
                lab = t.get((u, e, W0), np.nan)
                rows.append(dict(unit_id=u, r=r, event=e, W0=W0, delta=d, agyear=int(ag),
                                 lead=int(min(max(d, 0), 3)), far=far,
                                 prev_label=np.nan if lab is None else lab))
    return pd.DataFrame(rows)


def score(bundle: dict, X: pd.DataFrame, iso3: str) -> np.ndarray:
    win = bundle["winner"]
    p = np.full(len(X), np.nan)
    for e in MODEL_EVENTS:
        E = bundle["events"][e]
        me = (X["event"] == e).values
        for ag in np.unique(X.loc[me, "agyear"]):
            m = me & (X["agyear"] == ag).values
            if not is_test(iso3, int(ag)) and int(ag) in E["fold_models"]:
                mdl, cal = E["fold_models"][int(ag)][win], E["fold_cal"][int(ag)][win]
            else:
                mdl, cal = E["final"][win], E["final_cal"][win]
            p[m] = cal.predict(mdl.raw(X.loc[m]))
    return p


def horizon_weeks(d, event) -> int:
    """Weeks from the issue date until the predicted window: 4 per month of lead (lead 1/2/3 ->
    4/8/12). Inside an ongoing window: 4 per remaining window month (min 4). The issue date already
    sits one month after the newest data (latency), so this is time-to-impact for the reader."""
    if d is None or (isinstance(d, float) and np.isnan(d)):
        return 4
    d = int(d)
    months = d if d >= 1 else WINDOW_LEN[event] + d - 1
    return int(4 * max(1, months))


def rnd(v, k=2):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), k)


def geo_ids(iso3: str):
    f = ROOT / "data" / "geo" / f"{iso3}.js"
    if not f.exists():
        return None
    body = f.read_text().split(f'GEO_DATA["{iso3}"] = ', 1)[1].rstrip().rstrip(";")
    return [ft["properties"]["id"] for ft in json.loads(body)["features"]]


def build(iso3: str, bundle: dict, data_dir, metrics_path: Path) -> dict:
    country, ddate, dlabel, _ = COUNTRIES[iso3]
    P = prepare_country(iso3, data_dir)
    start = pd.Timestamp(START_YEAR, 1, 1)
    months = pd.date_range(start - pd.DateOffset(months=WARMUP), periods=N_MONTHS + WARMUP, freq="MS")
    C = candidates(P, months)
    X = attach(P["feat"], C, P["plant"], P["bim"])
    X = add_families(X, P["ss"], crop_dominant(P["c"]))
    X["p"] = score(bundle, X, iso3)
    # one row per (unit, r): the candidate with highest p (ties -> event priority)
    X["prio"] = X["event"].map(EVENT_PRIORITY)
    best = (X.sort_values(["unit_id", "r", "p", "prio"], ascending=[True, True, False, True])
            .drop_duplicates(["unit_id", "r"]).set_index(["unit_id", "r"]))

    decl = pd.Timestamp(ddate)
    decl_t = months_between(start, decl)

    disp = P["display"]
    crop_dom = crop_dominant(P["c"])
    decl_m = pd.Timestamp(decl.year, decl.month, 1)
    units = []
    order = geo_ids(iso3) or list(P["c"].names.index)
    missing_geo = [u for u in order if u not in P["c"].names.index]
    order = [u for u in order if u in P["c"].names.index]
    order += [u for u in P["c"].names.index if u not in order]       # units without geometry go last
    for u in order:
        b = best.loc[u].reindex(months)
        du = disp.loc[u].reindex(months)
        sig = du[SIG_AT_R]
        fsig = sig.assign(vci_crop_l1=du["vci_crop"].shift(1), vci_grass_l1=du["vci_grass"].shift(1))
        # families from the original (non-fallback) signals
        fam = ae.families(fsig, b["in_season"].fillna(False).values.astype(bool), _rainy(P, u, months),
                          np.full(len(months), crop_dom[u]))
        p = b["p"].values                      # information only (NGO / food-bank text), not used for levels
        dif = np.array([(m >= decl_m) and (agyear(m) == agyear(decl_m)) for m in months])
        raw = ae.raw_levels(fam, dif)
        lvl, held = ae.hysteresis(raw)         # spec: 2 runs up, 3 runs down, no fast entry
        plant = plant_months(P["ss"][u])
        st = P["c"].static.loc[u]
        default_ev = "no_grass" if (st["grass_frac"] or 0) > (st["crop_frac"] or 0) else "crop_failure"
        lag = LATENCY["chirps"]
        series = []
        for k, m in enumerate(months):
            if m < start:
                continue
            t = months_between(start, m)
            f = {x: bool(fam[x].iloc[k]) for x in ae.FAMS}
            s = {x: rnd(sig[x].iloc[k], 1 if x.startswith("vci") else 2) for x in SIG_AT_R}
            nmiss = sum(v is None for v in s.values())
            conf = ae.confidence(int(fam["agreeing"].iloc[k]), nmiss)
            if bool(b["far"].iloc[k]) and conf == "high":
                conf = "medium"
            elif bool(b["far"].iloc[k]):
                conf = "low"
            d = b["delta"].iloc[k]
            series.append({
                "t": t, "level": int(lvl[k]), "held": bool(held[k]), "p": None if np.isnan(p[k]) else round(float(p[k]), 3),
                "confidence": conf, "agreeing": int(fam["agreeing"].iloc[k]), "families": f,
                "event": ("none" if lvl[k] == 0 else
                          "cant_plant" if (bool(fam["strong_weather"].iloc[k]) and
                                           (m - pd.DateOffset(months=lag)).month in plant and lvl[k] == 1)
                          else b["event"].iloc[k] if isinstance(b["event"].iloc[k], str) else default_ev),
                "horizon": horizon_weeks(d, b["event"].iloc[k]),
                "drivers": ae.drivers(s, f), "signals": s})
        units.append({"id": u, "name": str(P["c"].names[u]), "series": series})

    mj = json.loads(metrics_path.read_text()) if metrics_path.exists() else {}
    win = bundle["winner"]
    meta_metrics = {
        "winner": win, "trained_on": bundle["iso3s"],
        "cv_design": mj.get("cv_design"), "holdout_design": mj.get("holdout_design"),
        "labels": mj.get("labels"),
        "cv_pooled_winner": (mj.get("cv_pooled") or {}).get(win),
        "cv_this_country_winner": (mj.get("cv_this_country") or {}).get(win),
        "cv_mean_pr_auc_by_model": {m: v.get("mean_pr_auc") for m, v in (mj.get("cv_pooled") or {}).items()},
        "holdout_winner": (mj.get("holdout") or {}).get(win),
        "holdout_persistence": (mj.get("holdout") or {}).get("persistence"),
        "alert_rule": "v1.1 spec mode: Watch = any one family (rain/vegetation/soil) or strong rain+soil "
                      "dryness; Warning = vegetation + (rain or soil); Emergency = Warning + official "
                      "declaration in force (declaration month to end of that agricultural year). "
                      "Hysteresis 2 up / 3 down, no fast entry. p is information only.",
        "spec_rule_cv_stats": mj.get("thresholds"),
        "fast_entry": False,
        "data_latency_months": LATENCY,
        "issue_convention": "level/p for month t are issued at the end of month t from data of month t-1 "
                            "(latency already applied; do not add latency again)",
        "events": "crop_failure / no_grass from the model; cant_plant = rule-based Watch reason only "
                  "(strong rain+soil dryness in the planting window; the cant_plant model had no skill)",
        "signals_note": "signals and families at month t are the latest data published by the end of "
                        "month t (i.e. describe month t-1); see data_latency_months",
        "no_cropland_units_use_grass": P["no_crop"],
        "note": "Targets are satellite-derived (VCI/SPI/soil moisture), not food-security outcomes. "
                "Every month is scored out-of-sample (fold model for CV seasons, final model for hold-out).",
    }
    if missing_geo:
        meta_metrics["units_in_geo_without_signals"] = missing_geo
    return {"meta": {"iso3": iso3, "country": country, "start_year": START_YEAR, "n_months": N_MONTHS,
                     "declaration": {"t": decl_t, "date": ddate, "label": dlabel},
                     "model_version": f"sat-v1-{win}-{bundle['tag']}",
                     "metrics": meta_metrics,
                     "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")},
            "units": units}


def plant_months(ss) -> set:
    return {m for s in ss for m in s.planting}


def _rainy(P, u, months):
    from train import rainy_months
    rm = rainy_months(P["ss"][u])
    lag = LATENCY["chirps"]
    return np.array([(m - pd.DateOffset(months=lag)).month in rm for m in months])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso3", nargs="+", required=True)
    ap.add_argument("--model", default=None)
    ap.add_argument("--data-dir", default=str(DATA_DIR))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--risk-dir", default=str(RISK_DIR))
    a = ap.parse_args()
    out = Path(a.out_dir)
    for iso3 in [i.upper() for i in a.iso3]:
        mp = Path(a.model) if a.model else None
        if mp is None:                       # newest bundle that contains this country
            cands = sorted(out.glob("model_*.joblib"), key=lambda f: f.stat().st_mtime, reverse=True)
            mp = next(f for f in cands if iso3 in f.stem.split("_")[1:])
        bundle = joblib.load(mp)
        doc = build(iso3, bundle, a.data_dir, out / f"metrics_{iso3}.json")
        assert doc["meta"]["model_version"] != "STUB"
        rd = Path(a.risk_dir); rd.mkdir(parents=True, exist_ok=True)
        path = rd / f"{iso3}.js"
        with open(path, "w") as fh:
            fh.write(f"// Real model output - pipeline/export_risk.py ({doc['meta']['model_version']}).\n")
            fh.write("// Satellite-only signals (CHIRPS, MODIS, ERA5-Land). Shape: pipeline/CONTRACT.md section 3.\n")
            fh.write("window.RISK_DATA = window.RISK_DATA || {};\n")
            fh.write(f'RISK_DATA["{iso3}"] = {json.dumps(doc, separators=(",", ":"), allow_nan=False)};\n')
        lv = pd.Series([s["level"] for un in doc["units"] for s in un["series"]]).value_counts().sort_index()
        print(f"[{iso3}] {len(doc['units'])} units -> {path}  level counts {lv.to_dict()}  model {mp.name}")


if __name__ == "__main__":
    main()
