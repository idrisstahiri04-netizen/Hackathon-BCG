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
IPC_DIR = Path(__file__).resolve().parent / "ipc_model" / "out"
IPC_COL = "cal_eo_fews:lgbm"     # recommended in ipc_model/report.md
CRISIS_WATCH_P = 0.57            # precision-first point from ipc_model/report.md (CV precision 0.60, recall 0.62); 0.31 (max-F1) left Watch on in ~90% of districts in calm 2020/21-2021/22
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


MAX_P_LEAD = 6          # Model A leads with a skill-tested model (1-3 main bundle, 4-6 LONG bundle)
FC_LEADS = range(1, 9)  # CONTRACT 4b: forecast keys "1".."8"


def forecast_candidates(P: dict, months: pd.DatetimeIndex, long_ok: bool) -> pd.DataFrame:
    """CONTRACT 4/4b: for issue month r and lead L (1-6), the event windows that cover target month
    T = r + L. Windows starting <= 3 months after r use the main model (lead feature clip(d, 0, 3)),
    windows starting 4-6 months after r the LONG model (lead feature d). If no window covers T, the
    next season window (start <= 6 months after r) is used and labelled as such."""
    t = P["targets"].set_index(["unit_id", "event", "W0"])["prev_label"]
    maxd = 6 if long_ok else 3
    rows = []
    for u, ss in P["ss"].items():
        inst = season_instances(ss, months.min().year, months.max().year + 1)
        wins = [(e, getattr(it, e), int(it.agyear)) for it in inst.itertuples(index=False) for e in MODEL_EVENTS]
        for r in months:
            for L in range(1, MAX_P_LEAD + 1):
                T = r + pd.DateOffset(months=L)
                cov = [(e, W0, ag) for e, W0, ag in wins
                       if months_between(r, W0) <= maxd and 0 <= months_between(W0, T) <= WINDOW_LEN[e] - 1]
                use, cover = cov, True
                if not cov:
                    nxt = [(e, W0, ag) for e, W0, ag in wins if 0 < months_between(T, W0) and months_between(r, W0) <= maxd]
                    if nxt:
                        w0 = min(x[1] for x in nxt)
                        use, cover = [x for x in nxt if x[1] == w0], False
                for e, W0, ag in use:
                    d = months_between(r, W0)
                    lab = t.get((u, e, W0), np.nan)
                    rows.append(dict(unit_id=u, r=r, L=L, event=e, W0=W0, agyear=ag, cover=cover,
                                     model="long" if d >= 4 else "main",
                                     lead=int(d) if d >= 4 else int(min(max(d, 0), 3)),
                                     prev_label=np.nan if lab is None else lab))
    return pd.DataFrame(rows)


def load_fews(iso3: str, data_dir):
    """FEWS NET ML1/ML2 projections per unit (polygon-matched ipc_units_<ISO3>.parquet, phase_w20)."""
    f = Path(data_dir) / f"ipc_units_{iso3}.parquet"
    if not f.exists():
        return None
    d = pd.read_parquet(f, columns=["unit_id", "scenario", "projection_start", "projection_end",
                                    "reporting_date", "phase_w20"])
    d = d[d.scenario.isin(["ML1", "ML2"])].dropna(subset=["phase_w20"]).copy()
    for c in ("projection_start", "projection_end", "reporting_date"):
        d[c] = pd.to_datetime(d[c])
    d["pub"] = d.reporting_date.dt.to_period("M").dt.to_timestamp()
    return {u: g.sort_values("pub") for u, g in d.groupby("unit_id")}


def fews_lookup(g, r, T):
    """Latest outlook published on/before issue month r; the scenario whose window covers T."""
    if g is None:
        return None
    h = g[g.pub <= r]
    if h.empty:
        return None
    h = h[h.pub == h.pub.max()]
    h = h[(h.projection_start <= T) & (h.projection_end >= T)]
    if h.empty:
        return None
    x = h.sort_values("scenario").iloc[0]
    return int(round(x.phase_w20)), x.scenario, x.pub.strftime("%Y-%m")


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


def _r(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), 3)


FEWS_NA = "FEWS NET outlook not available"
WATCH_REASONS = {"district_evidence": "district evidence (satellite / weather families)",
                 "ipc_outlook": "FEWS NET-informed Crisis outlook (p_crisis)",
                 "climate_readiness": "climate readiness (country-wide: El Niño + dry seasonal forecast)"}


def watch_reasons(lvl, fam_raw, crisis, climate) -> list:
    """Why a unit is at its level: district evidence (family rule) beats the IPC-outlook trigger, which beats
    country-wide climate readiness. Rows held by hysteresis keep the reason that raised them."""
    out, last = [], None
    for k in range(len(lvl)):
        now = ("district_evidence" if fam_raw[k] >= 1 else "ipc_outlook" if crisis[k]
               else "climate_readiness" if climate[k] else None)
        if lvl[k] == 0:
            last = None
            out.append(None)
            continue
        if lvl[k] >= 2:
            now = "district_evidence"         # Warning/Emergency only come from the family rule
        last = now or last
        out.append(last)
    return out


def load_urban(iso3: str) -> set:
    """Unit ids flagged urban by pipeline/urban_units.py (WorldCover built-up + WorldPop density)."""
    f = Path(DATA_DIR) / "urban_units.csv"
    if not f.exists():
        return set()
    d = pd.read_csv(f)
    return set(d[(d.iso3 == iso3) & d.urban.astype(bool)].unit_id)


def forecast_row(u, m, k, fp, flab, pc, pc46, fews, proxy=False) -> dict:
    out = {}
    g = fews.get(u) if fews else None
    for L in FC_LEADS:
        T = m + pd.DateOffset(months=L)
        p = _r(fp.get((u, m, L))) if L <= MAX_P_LEAD else None
        pcr = _r(pc[k]) if L <= 3 else (_r(pc46[k]) if L <= 6 else None)
        fw = fews_lookup(g, m, T)
        ipc_name = "IPC proxy (satellite-only)" if (proxy and L <= 3) else "IPC model"
        src = [x for x, ok in (("model", p is not None), (ipc_name, pcr is not None),
                               (f"FEWS {fw[1]}" if fw else "", fw is not None)) if ok]
        source = "+".join(src) if src else "none"
        if fw is None:                    # say why the FEWS layer is empty instead of a silent null
            source = (f"{source}; " if src else "") + FEWS_NA
        out[str(L)] = {"p": p, "p_crisis": pcr,
                       "fews_phase": fw[0] if fw else None, "fews_scenario": fw[1] if fw else None,
                       "fews_published": fw[2] if fw else None,
                       "target_label": flab.get((u, m, L)) or T.strftime("%b %Y"),
                       "source": source}
    return out


def forecast_skill(metrics_path: Path, win: str) -> dict:
    """Per-lead back-test skill for the UI (CV, leave-one-season-out; pooled 4 core countries).
    p: winner by lead (ROC / PR-AUC / Brier / base rate) from metrics_<ISO3>.json (leads 1-3) and
    metrics_LONG_<ISO3>.json (leads 4-6); p_crisis: IPC model eo_fews:lgbm CV, transition rows (h13 / h46)."""
    out = {}
    def by_lead(f, w):
        if not f.exists():
            return {}
        j = json.loads(f.read_text())
        return {int(k): v for k, v in (j.get("cv_by_lead_winner") or {}).items()}, j.get("winner", w)
    a = by_lead(metrics_path, win) or ({}, win)
    lp = Path(metrics_path).with_name(Path(metrics_path).name.replace("metrics_", "metrics_LONG_"))
    b = by_lead(lp, win) or ({}, win)
    ipc = {}
    mf = IPC_DIR / "metrics.json"
    if mf.exists():
        mj = json.loads(mf.read_text())
        for h in ("h13", "h46"):
            x = ((mj.get(f"cv_{h}") or {}).get("ALL") or {}).get(IPC_COL.replace("cal_", ""))
            if x:
                ipc[h] = {k: x["transition"].get(k) for k in ("roc", "pr", "brier", "base", "n")}
    for L in FC_LEADS:
        lp_ = (a[0] if L <= 3 else b[0]).get(L) if L <= MAX_P_LEAD else None
        out[str(L)] = {"p": lp_, "p_crisis": ipc.get("h13") if L <= 3 else (ipc.get("h46") if L <= 6 else None),
                       "fews": "FEWS NET ML1/ML2 projection (not scored here)" if L <= 8 else None}
    return out


def load_long_bundle(iso3: str):
    f = Path(OUT_DIR) / "model_LONG.joblib"
    if not f.exists():
        return None
    b = joblib.load(f)
    return b if iso3 in b["iso3s"] or iso3 in b.get("pool", []) else None


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
    if ddate is None:                                  # date researched later into CONTRACT.md countries table
        ddate = contract_declaration(iso3)
        dlabel = "Drought disaster declared" if ddate else None
    P = prepare_country(iso3, data_dir)
    start = pd.Timestamp(START_YEAR, 1, 1)
    last = P["feat"].index.get_level_values("month").max()
    n_months = max(N_MONTHS, months_between(start, last) + 1)       # live months beyond 2024-12 if present
    live_t = months_between(start, last) if last > pd.Timestamp(2024, 12, 1) else None
    months = pd.date_range(start - pd.DateOffset(months=WARMUP), periods=n_months + WARMUP, freq="MS")
    C = candidates(P, months)
    X = attach(P["feat"], C, P["plant"], P["bim"])
    X = add_families(X, P["ss"], crop_dominant(P["c"]))
    X["p"] = score(bundle, X, iso3)
    # one row per (unit, r): the candidate with highest p (ties -> event priority)
    X["prio"] = X["event"].map(EVENT_PRIORITY)
    best = (X.sort_values(["unit_id", "r", "p", "prio"], ascending=[True, True, False, True])
            .drop_duplicates(["unit_id", "r"]).set_index(["unit_id", "r"]))

    decl = pd.Timestamp(ddate) if ddate else None
    decl_t = months_between(start, decl) if decl is not None else None

    # forecasts (section 4): Model A p per lead (max over covering windows), out-of-sample like p
    long_b = load_long_bundle(iso3)
    FC = forecast_candidates(P, months[months >= start], long_b is not None)
    fp, flab = {}, {}
    if len(FC):
        XF = attach(P["feat"], FC, P["plant"], P["bim"])
        XF = add_families(XF, P["ss"], crop_dominant(P["c"]))
        XF["p"] = np.nan
        mm = (XF["model"] == "main").values
        XF.loc[mm, "p"] = score(bundle, XF[mm], iso3)
        if long_b is not None and (~mm).any():
            XF.loc[~mm, "p"] = score(long_b, XF[~mm], iso3)
        fp = XF.groupby(["unit_id", "r", "L"])["p"].max().to_dict()
        # label: the target month if an event window covers it, else the season window the p refers to
        fl = XF.groupby(["unit_id", "r", "L"]).agg(cover=("cover", "first"), W0=("W0", "min"))
        flab = {k: (None if v.cover else f"{v.W0:%b %Y} season") for k, v in fl.iterrows()}
    pcr46 = load_p_crisis(iso3, "h46")
    fews = load_fews(iso3, data_dir)

    pcr = load_p_crisis(iso3)
    disp = P["display"]
    urban = load_urban(iso3)
    crop_dom = crop_dominant(P["c"])
    decl_m = pd.Timestamp(decl.year, decl.month, 1) if decl is not None else None
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
        dif = np.array([decl_m is not None and (m >= decl_m) and (agyear(m) == agyear(decl_m)) for m in months])
        raw = ae.raw_levels(fam, dif)
        fam_raw = raw.copy()
        # announcement/text family (FEWS NET-informed IPC model): may raise to Watch only, never higher
        if pcr is not None:
            pr_ = pcr.reindex(pd.MultiIndex.from_product([[u], months]))
            pc, known, pxy = pr_[IPC_COL].values, pr_["st_phase"].values, pr_["proxy"].fillna(0).values > 0
        else:
            pc = known = np.full(len(months), np.nan)
            pxy = np.zeros(len(months), bool)
        # trigger only where the latest KNOWN (published by the issue month) IPC phase is < 3, as tuned;
        # unknown phase -> no trigger. p_crisis itself is shown everywhere.
        if pcr46 is not None:
            pc46 = pcr46.reindex(pd.MultiIndex.from_product([[u], months]))[IPC_COL].values
        else:
            pc46 = np.full(len(months), np.nan)
        crisis = ~np.isnan(pc) & (pc >= CRISIS_WATCH_P) & ~np.isnan(known) & (np.nan_to_num(known, nan=9) < 3)
        # agricultural decision window only (calendar rule, not tuned on replay outcomes)
        win = decision_months(iso3, P["ss"][u])
        in_win = np.array([m.month in win for m in months])
        crisis &= in_win
        # climate readiness (ONI / NMME, public in the issue month): Watch only, decision months only
        fu = P["feat"].loc[u].reindex(months)
        climate = ae.climate_readiness(fu["oni_x_south"].values, fu["sfc_pbn_m13"].values) & in_win
        raw = np.where((crisis | climate) & (raw < 1), 1, raw)
        lvl, held = ae.hysteresis(raw)         # spec: 2 runs up, 3 runs down, no fast entry
        # Emergency only while the declaration is in force (cap held Emergency after the window);
        # held is recomputed so capped rows are held only if the raw level is below Warning
        lvl = np.where((lvl == 3) & ~dif, 2, lvl)
        held = raw < lvl
        why = watch_reasons(lvl, fam_raw, crisis, climate)
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
                "t": t, "level": int(lvl[k]), "held": bool(held[k]), "watch_reason": why[k], "p": None if np.isnan(p[k]) else round(float(p[k]), 3),
                "p_crisis": None if np.isnan(pc[k]) else round(float(pc[k]), 3),
                "confidence": conf, "agreeing": int(fam["agreeing"].iloc[k]), "families": f,
                "event": ("none" if lvl[k] == 0 else
                          "cant_plant" if (bool(fam["strong_weather"].iloc[k]) and
                                           (m - pd.DateOffset(months=lag)).month in plant and lvl[k] == 1)
                          else b["event"].iloc[k] if isinstance(b["event"].iloc[k], str) else default_ev),
                "horizon": horizon_weeks(d, b["event"].iloc[k]),
                "drivers": (ae.drivers(s, f)
                            + (["FEWS NET-based outlook: Crisis (IPC3+) likely within 3 months"] if crisis[k] else [])
                            + ([ae.CLIMATE_REASON] if climate[k] else []))[:3],
                "signals": s,
                "forecast": forecast_row(u, m, k, fp, flab, pc, pc46, fews, bool(pxy[k]))})
        units.append({"id": u, "name": str(P["c"].names[u]), "urban": u in urban, "series": series})

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
        "p_crisis": {"source": "pipeline/ipc_model (eo_fews:lgbm, FEWS NET outlook/projections + EO + seasonal "
                               "forecast), calibrated P(district enters IPC3+ within 1-3 months); CV fold predictions "
                               "for CV seasons, final model for hold-out; null where unavailable",
                     "available": pcr is not None,
                     "watch_threshold": CRISIS_WATCH_P,
                     "watch_only_if_known_phase_below": 3,
                     "watch_months": "Oct-Apr (ZWE/MWI/ZMB); KEN: own rainy seasons +/- 1 month (agricultural calendar rule)",
                     "rule": "announcement/text family: p_crisis >= threshold, in districts whose latest published IPC "
                             "phase is below 3, may raise the level to Watch (1) only (NGO / officer audiences); "
                             "never Warning; farmers unchanged"},
        "fast_entry": False,
        "watch_reason": {"values": WATCH_REASONS,
                         "rule": "per row (null at Normal): district_evidence if the family rule fires, else ipc_outlook "
                                 "if the p_crisis trigger fires, else climate_readiness; rows held by hysteresis keep "
                                 "the reason that raised them; Warning/Emergency are always district_evidence"},
        "urban_units": {"ids": sorted(x for x in urban if x in P["c"].names.index),
                        "rule": "pipeline/urban_units.py: WorldCover v200 built-up share >= 0.15, or >= 0.05 with area "
                                "< 1000 km2 or WorldPop density >= 1000/km2, or an official town/city unit name "
                                "(area < 5000 km2)",
                        "use": "levels stay visible; farmer/herder SMS and farm Warning counts exclude urban units "
                               "(town councils: little cropland, signals describe the surrounding farmland)"},
        "forecast_skill": forecast_skill(metrics_path, bundle["winner"]),
        "training_data": (json.loads((Path(OUT_DIR) / "training_data.json").read_text())
                          if (Path(OUT_DIR) / "training_data.json").exists() else None),
        "climate_readiness": {"rule": "Watch only (NGO / officer): signed ONI >= 1.0 or (signed ONI >= 0.5 and NMME "
                                      "P(below) m1-3 >= 0.5), decision months only (Oct-Apr; KEN own rainy seasons +/-1)",
                              "reason_label": "climate readiness (El Niño + dry forecast)"},
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
    return {"meta": {"iso3": iso3, "country": country, "start_year": START_YEAR, "n_months": n_months, "live_t": live_t,
                     "declaration": ({"t": decl_t, "date": ddate, "label": dlabel} if ddate else None),
                     "model_version": f"sat-v1-{win}-{bundle['tag']}",
                     "metrics": meta_metrics,
                     "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")},
            "units": units}


def load_p_crisis(iso3: str, h: str = "h13"):
    """Out-of-sample p of entering IPC3+ within 1-3 months (ipc_model, eo_fews:lgbm, calibrated):
    leave-one-season-out CV predictions (oof) for CV seasons, final model for hold-out seasons.
    Returns Series indexed (unit_id, month) or None if the country has no IPC model output."""
    parts = []
    for f in (f"oof_{h}.parquet", f"holdout_{h}.parquet"):
        fp = IPC_DIR / f
        if fp.exists():
            d = pd.read_parquet(fp, columns=["iso3", "unit_id", "month", "st_phase", IPC_COL])
            parts.append(d[d.iso3 == iso3])
    if not parts:
        return None
    d = pd.concat(parts, ignore_index=True)
    if d.empty:
        return None
    d["month"] = pd.to_datetime(d["month"])
    d = d.drop_duplicates(["unit_id", "month"], keep="last")      # hold-out wins if both
    d["proxy"] = 0.0
    if h == "h13":
        # ML-expert fallback: never serve eo_fews where its FEWS inputs were missing -> FEWS proxy (EO+NMME+ONI,
        # FEWS-projection target; out-of-sample nested CV / hold-out values)
        fb = IPC_DIR / "proxy_fallback_h13.parquet"
        if fb.exists():
            f = pd.read_parquet(fb)
            f = f[(f.iso3 == iso3) & f.fews_missing & f.p_proxy.notna()]
            f["month"] = pd.to_datetime(f["month"])
            d = d.merge(f[["unit_id", "month", "p_proxy"]], on=["unit_id", "month"], how="left")
            m = d.p_proxy.notna()
            d.loc[m, IPC_COL] = d.loc[m, "p_proxy"]
            d.loc[m, "proxy"] = 1.0
            d = d.drop(columns="p_proxy")
        # live months (after the IPC model's last issue month): proxy fitted on all past months
        lv = Path(OUT_DIR) / "ipc_proxy_live.parquet"
        if lv.exists():
            f = pd.read_parquet(lv)
            f = f[f.iso3 == iso3].copy()
            f["month"] = pd.to_datetime(f["month"])
            f = f[f.month > d.month.max()]
            if len(f):
                d = pd.concat([d, pd.DataFrame({"unit_id": f.unit_id, "month": f.month, IPC_COL: f.p_proxy,
                                                "st_phase": np.nan, "proxy": 1.0})], ignore_index=True)
    return d.set_index(["unit_id", "month"])[[IPC_COL, "st_phase", "proxy"]].astype(float)


SOUTHERN_DECISION = {10, 11, 12, 1, 2, 3, 4}   # Oct-Apr: planting, growing and lean season (unimodal south)


SOUTH_ISO = {"ZWE", "MWI", "ZMB", "MOZ", "NAM", "BWA", "ZAF", "MDG", "AGO"}


def contract_declaration(iso3: str):
    """Declaration date for iso3 from the CONTRACT.md countries table (last column, YYYY-MM-DD) or None."""
    import re
    f = Path(__file__).resolve().parent / "CONTRACT.md"
    if not f.exists():
        return None
    for line in f.read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0] == iso3:
            m = re.search(r"\d{4}-\d{2}-\d{2}", cells[-1])
            return m.group(0) if m else None
    return None


def decision_months(iso3: str, ss) -> set:
    """Months in which the p_crisis Watch trigger may fire. Southern-hemisphere unimodal countries:
    Oct-Apr. KEN: each of the unit's own rainy seasons (OND / MAM as detected) +/- 1 month."""
    if iso3 in SOUTH_ISO:
        return SOUTHERN_DECISION
    out = set()
    for s_ in ss:
        r = list(s_.rainy)
        out |= set(r) | {(r[0] - 2) % 12 + 1, r[-1] % 12 + 1}
    return out


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
            mp = next((f for f in cands if iso3 in f.stem.split("_")[1:]), None) \
                or (out / "model_ZWE_KEN_MWI_ZMB.joblib")      # pooled countries use the main bundle
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
