#!/usr/bin/env python3
"""Feasibility test of extra agro-climatic indicators against the current signals.

    python pipeline/experts/agroclimate/analyse.py --iso3 ZWE

Inputs : pipeline/data/signals_<ISO3>.parquet (current pipeline), pipeline/cache/agroclimate/<ISO3>/raw_<ISO3>.parquet
         (extract_agroclimate.py), pipeline/data/ipc_units_<ISO3>.parquet (FEWS NET IPC per unit, ground truth).
Outputs: pipeline/data/agroclimate_<ISO3>.parquet   derived indicators, CONTRACT long format
         pipeline/experts/agroclimate/results_<ISO3>.md   tables printed below

Tests
  T1  share of units "in alarm" per data month, drought seasons (2015/16, 2023/24) vs quiet (2016/17, 2020/21)
  T2  ROC-AUC of the indicator at data month Nov/Dec/Jan/Feb vs (a) the satellite label used by the pipeline
      (>= 2 of 3 crop months VCI < 35) and (b) FEWS NET IPC Phase 3+ (CS) in the post-harvest months Apr-Sep
  T3  alert replay with the spec rule + hysteresis when one family is swapped for the new indicator:
      Warnings before the declaration and false Warnings in quiet seasons
All indicators are oriented so that LOW = DRY. Baseline 2001-2020, per unit and calendar month. Missing stays NaN.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

HERE = Path(__file__).resolve().parent
PIPE = HERE.parent.parent
sys.path.insert(0, str(PIPE))
import alert_engine as ae  # noqa: E402
from common import BASE_END, BASE_START, COUNTRIES, agyear, load_country, unit_seasons  # noqa: E402
from train import crop_dominant, in_season_months, rainy_months  # noqa: E402

CACHE = PIPE / "cache" / "agroclimate"
DATA = PIPE / "data"
MM_PER_WM2_DAY = 0.0353          # 1 W/m2 of latent heat flux = 0.0864 MJ/m2/day / 2.45 MJ/kg

# indicator -> (kind, alarm threshold)   kind: "idx" 0-100 (alarm if < thr), "z" (alarm if <= thr)
IND = {
    # current pipeline signals
    "vci_dom": ("idx", 35), "ndvi_z_dom": ("z", -1), "spi_3m": ("z", -1), "spi_1m": ("z", -1.5), "sm1_z": ("z", -1),
    # new: MODIS LST (vegetation/heat family)
    "tci_dom": ("idx", 35), "vhi_dom": ("idx", 35), "lst_z_dom_neg": ("z", -1),
    # new: FLDAS (soil family, FEWS NET's own LDAS)
    "fl_sm1_z": ("z", -1), "fl_sm2_z": ("z", -1), "fl_sm3_z": ("z", -1), "fl_evap_z": ("z", -1),
    # new: GLDAS (soil / ET)
    "gl_rootmoist_z": ("z", -1), "gl_esi_z": ("z", -1),
    # new: water balance CHIRPS - GLDAS PET (rain family)
    "spei1_like": ("z", -1.5), "spei3_like": ("z", -1), "wb_season_z": ("z", -1),
    # not operational (yearly releases) - physics benchmark only
    "m16_esi_z": ("z", -1), "tc_def_z_neg": ("z", -1), "tc_pdsi": ("z", -2), "tc_soil_z": ("z", -1),
}
NEW = [k for k in IND if k not in ("vci_dom", "ndvi_z_dom", "spi_3m", "spi_1m", "sm1_z")]


def zscore(w: pd.DataFrame) -> pd.DataFrame:
    base = w[(w.index.year >= BASE_START) & (w.index.year <= BASE_END)]
    g = base.groupby(base.index.month)
    cm = range(1, 13)
    mu, sd, n = g.mean().reindex(cm), g.std(ddof=1).reindex(cm), g.count().reindex(cm).fillna(0)
    mu = mu.where(n >= 10)
    sd = sd.where((n >= 10) & (sd > 0))
    m = w.index.month
    return (w - mu.loc[m].values) / sd.loc[m].values


def idx100(w: pd.DataFrame, invert=False) -> pd.DataFrame:
    """VCI-style scaling: 100*(x-min)/(max-min) per calendar month (invert: 100*(max-x)/(max-min))."""
    base = w[(w.index.year >= BASE_START) & (w.index.year <= BASE_END)]
    g = base.groupby(base.index.month)
    cm = range(1, 13)
    lo, hi, n = g.min().reindex(cm), g.max().reindex(cm), g.count().reindex(cm).fillna(0)
    rng = (hi - lo).where((n >= 10) & ((hi - lo) > 0))
    m = w.index.month
    v = 100 * ((hi.loc[m].values - w) if invert else (w - lo.loc[m].values)) / rng.loc[m].values
    return v.clip(0, 100)


def dom(crop: pd.DataFrame, grass: pd.DataFrame, crop_dom: dict) -> pd.DataFrame:
    out = grass.copy()
    for u in out.columns:
        if crop_dom.get(u) and u in crop and crop[u].notna().any():
            out[u] = crop[u]
    return out


def build(iso3: str):
    c = load_country(iso3)
    ss = unit_seasons(c)
    cd = crop_dominant(c)
    units = list(c.names.index)
    months = pd.date_range("2001-01-01", "2024-12-01", freq="MS")
    cur = {k: c.wide[k].unstack("unit_id").reindex(index=months, columns=units)
           for k in ["precip_mm", "spi_1m", "spi_3m", "sm1_z", "vci_crop", "vci_grass", "ndvi_z_crop", "ndvi_z_grass"]}
    raw = pd.read_parquet(CACHE / iso3 / f"raw_{iso3}.parquet")
    R = {v: g.pivot(index="month", columns="unit_id", values="value").reindex(index=months, columns=units)
         for v, g in raw.groupby("var")}

    W = {}
    W["vci_dom"] = dom(cur["vci_crop"], cur["vci_grass"], cd)
    W["ndvi_z_dom"] = dom(cur["ndvi_z_crop"], cur["ndvi_z_grass"], cd)
    for k in ("spi_3m", "spi_1m", "sm1_z"):
        W[k] = cur[k]
    # LST -> TCI (Kogan), VHI = 0.5 VCI + 0.5 TCI, on the dominant cover
    lst = dom(R["lst_crop"], R["lst_grass"], cd)
    W["tci_dom"] = idx100(lst, invert=True)
    W["vhi_dom"] = 0.5 * W["vci_dom"] + 0.5 * W["tci_dom"]
    W["lst_z_dom_neg"] = -zscore(lst)
    for k in ("fl_sm1", "fl_sm2", "fl_sm3", "fl_evap"):
        W[f"{k}_z"] = zscore(R[k])
    W["gl_rootmoist_z"] = zscore(R["gl_rootmoist"])
    with np.errstate(divide="ignore", invalid="ignore"):
        W["gl_esi_z"] = zscore((R["gl_evap"] * 86400) / (R["gl_pet"] * MM_PER_WM2_DAY).where(R["gl_pet"] > 0))
        W["m16_esi_z"] = zscore((R["m16_et"] / R["m16_pet"].where(R["m16_pet"] > 0)))
    days = pd.Series(months.days_in_month, index=months).values[:, None]
    pet_mm = R["gl_pet"] * MM_PER_WM2_DAY * days
    D = cur["precip_mm"] - pet_mm
    W["spei1_like"] = zscore(D)
    W["spei3_like"] = zscore(D.rolling(3, min_periods=3).sum())
    # season-to-date water balance from October (southern-hemisphere season start)
    ag = pd.Series([agyear(m) for m in months], index=months)
    Dc = D.copy()
    Dc[(months.month >= 7) & (months.month <= 9)] = np.nan
    cum = Dc.groupby(ag.values).cumsum()
    cum[(months.month >= 7) & (months.month <= 9)] = np.nan
    W["wb_season_z"] = zscore(cum)
    W["tc_def_z_neg"] = -zscore(R["tc_def"])
    W["tc_pdsi"] = R["tc_pdsi"]
    W["tc_soil_z"] = zscore(R["tc_soil"])
    return c, ss, cd, units, months, W, R


def alarm(w: pd.DataFrame, key: str) -> pd.DataFrame:
    kind, thr = IND[key]
    return (w < thr) if kind == "idx" else (w <= thr)


def t1_shares(W, months, seasons=(2015, 2016, 2020, 2023)) -> pd.DataFrame:
    rows = []
    cal = [10, 11, 12, 1, 2, 3, 4, 5]
    for key, w in W.items():
        a = alarm(w, key)
        for sy in seasons:
            vals = []
            for m in cal:
                y = sy if m >= 7 else sy + 1
                ts = pd.Timestamp(y, m, 1)
                if ts not in a.index:
                    vals.append(np.nan); continue
                row = w.loc[ts]
                n = row.notna().sum()
                vals.append(np.nan if n < 5 else a.loc[ts][row.notna()].mean())
            rows.append([key, f"{sy}/{str(sy + 1)[2:]}"] + [None if np.isnan(v) else round(100 * v) for v in vals])
    return pd.DataFrame(rows, columns=["indicator", "season"] + ["Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May"])


def sat_label(c, ss, cd, W) -> pd.DataFrame:
    """(unit, agyear) -> 1 if >= 2 of the 3 crop months have dominant-cover VCI < 35 (pipeline label)."""
    v = W["vci_dom"]
    out = {}
    for u in v.columns:
        s = ss[u][0]
        for ay in range(2001, 2024):
            vals = []
            for m in s.crop:
                y = ay if m >= 7 else ay + 1
                ts = pd.Timestamp(y, m, 1)
                if ts in v.index:
                    vals.append(v.at[ts, u])
            vals = [x for x in vals if not np.isnan(x)]
            if len(vals) >= 2:
                out[(u, ay)] = float(sum(x < 35 for x in vals) >= 2)
    return pd.Series(out, name="sat").rename_axis(["unit_id", "agyear"])


def ipc_label(iso3: str) -> tuple[pd.Series, pd.Series]:
    p = DATA / f"ipc_units_{iso3}.parquet"
    if not p.exists():
        return pd.Series(dtype=float), pd.Series(dtype=float)
    d = pd.read_parquet(p)
    d = d[d.scenario == "CS"].copy()
    d["rep"] = pd.to_datetime(d.reporting_date)
    # post-harvest crisis of season ay: CS phase >= 3 reported Apr..Sep of ay+1
    post = d[d.rep.dt.month.between(4, 9)].copy()
    post["agyear"] = post.rep.dt.year - 1
    lab = post.groupby(["unit_id", "agyear"]).phase_w50.max().ge(3).astype(float).rename("ipc")
    # pre-season phase (Jul..Dec of ay) for the "not yet in crisis" subset
    pre = d[d.rep.dt.month.between(7, 12)].copy()
    pre["agyear"] = pre.rep.dt.year
    pre_ph = pre.sort_values("rep").groupby(["unit_id", "agyear"]).phase_w50.last().rename("pre")
    return lab, pre_ph


def t2_auc(W, months, sat, ipc, pre) -> pd.DataFrame:
    rows = []
    for key, w in W.items():
        x = w.stack(future_stack=True).rename("x").reset_index()
        x.columns = ["month", "unit_id", "x"]
        x["agyear"] = x.month.map(agyear)
        x["cm"] = x.month.dt.month
        rec = {"indicator": key}
        for lab_name, lab in (("sat", sat), ("ipc", ipc)):
            if lab.empty:
                continue
            for cm in (11, 12, 1, 2):
                sub = x[x.cm == cm].merge(lab.reset_index(), on=["unit_id", "agyear"]).dropna(subset=["x", lab_name])
                if lab_name == "ipc":
                    sub = sub.merge(pre.reset_index(), on=["unit_id", "agyear"], how="left")
                    sub = sub[sub.pre.notna() & (sub.pre < 3)]           # districts not yet in crisis
                y = sub[lab_name].values
                tag = f"{lab_name}_{['Nov', 'Dec', 'Jan', 'Feb'][[11, 12, 1, 2].index(cm)]}"
                if len(sub) < 30 or y.min() == y.max():
                    rec[tag] = np.nan
                else:
                    rec[tag] = round(roc_auc_score(y, -sub.x.values), 3)     # low = dry -> higher risk
                rec[f"n_{lab_name}"] = len(sub)
                rec[f"base_{lab_name}"] = round(float(y.mean()), 2) if len(y) else np.nan
        rows.append(rec)
    return pd.DataFrame(rows)


def t3_replay(iso3, c, ss, cd, units, W, cur_shift=1):
    """Spec rule + hysteresis, one family swapped. Returns rows of counts."""
    decl = pd.Timestamp(COUNTRIES[iso3][1])
    decl_m = pd.Timestamp(decl.year, decl.month, 1)
    months = pd.date_range("2014-01-01", "2024-12-01", freq="MS")
    display = c.wide.copy()
    disp = display.groupby(level="unit_id").shift(cur_shift)                  # 1-month latency
    S = {k: v.shift(cur_shift).reindex(months) for k, v in W.items()}         # new signals, same latency

    variants = {
        "current (VCI / SPI / ERA5 soil)": {},
        "vegetation = VHI (VCI+TCI)": {"vci": "vhi_dom"},
        "vegetation = TCI (LST only)": {"vci": "tci_dom"},
        "soil = FLDAS 0-10 cm": {"sm1_z": "fl_sm1_z"},
        "soil = FLDAS 10-40 cm": {"sm1_z": "fl_sm2_z"},
        "rain = SPEI-3-like (CHIRPS - PET)": {"spi_3m": "spei3_like"},
        "rain = season water balance": {"spi_3m": "wb_season_z"},
        "VHI + FLDAS 10-40 + SPEI-3": {"vci": "vhi_dom", "sm1_z": "fl_sm2_z", "spi_3m": "spei3_like"},
    }
    rows = []
    for name, swap in variants.items():
        first_warn, lvl_all = {}, {}
        for u in units:
            du = disp.loc[u].reindex(months)
            df = pd.DataFrame(index=months)
            df["spi_3m"] = S[swap["spi_3m"]][u].values if "spi_3m" in swap else du["spi_3m"].values
            df["spi_1m"] = du["spi_1m"].values
            if "vci" in swap:
                v = S[swap["vci"]][u]
                df["vci_crop"] = v.values; df["vci_grass"] = v.values
                df["vci_crop_l1"] = v.shift(1).values; df["vci_grass_l1"] = v.shift(1).values
            else:
                df["vci_crop"] = du["vci_crop"].values; df["vci_grass"] = du["vci_grass"].values
                df["vci_crop_l1"] = du["vci_crop"].shift(1).values; df["vci_grass_l1"] = du["vci_grass"].shift(1).values
            df["ndvi_z_crop"] = du["ndvi_z_crop"].values; df["ndvi_z_grass"] = du["ndvi_z_grass"].values
            df["sm1_z"] = S[swap["sm1_z"]][u].values if "sm1_z" in swap else du["sm1_z"].values
            df["t2m_z"] = du["t2m_z"].values
            seas, rm = in_season_months(ss[u]), rainy_months(ss[u])
            dm = [(m - pd.DateOffset(months=cur_shift)).month for m in months]
            ins = np.array([m in seas for m in dm]); inr = np.array([m in rm for m in dm])
            fam = ae.families(df, ins, inr, np.full(len(months), cd[u]))
            raw = ae.raw_levels(fam)
            lvl, _ = ae.hysteresis(raw)
            lvl_all[u] = pd.Series(lvl, index=months)
        L = pd.DataFrame(lvl_all)
        ag = np.array([agyear(m) for m in months])

        def before_decl(ay, dm_):
            # first issue month >= Oct of the season with level >= 2, issued end of month, before the declaration
            win = L[(ag == ay) & (months >= pd.Timestamp(ay, 10, 1))]
            first = win.ge(2).idxmax().where(win.ge(2).any())
            issued = first + pd.offsets.MonthEnd(0)
            ok = first.notna() & (issued < dm_)
            leads = (dm_ - issued[ok]).dt.days / 7
            return int(ok.sum()), (round(float(leads.median()), 1) if ok.any() else None)

        def quiet(ay):
            win = L[(ag == ay) & np.isin(months.month, [11, 12, 1, 2, 3, 4, 5, 6])]
            return int(win.ge(2).sum().sum()), int((win.ge(2).any()).sum())

        n24, lead24 = before_decl(2023, decl)
        n16, lead16 = before_decl(2015, pd.Timestamp("2016-02-29"))   # ZWE drought disaster declared early Feb 2016; cut-off end Feb for all
        rows.append({"variant": name, "warn_before_decl_2023/24": n24, "median_lead_wk": lead24,
                     "warn_by_Feb_2016 (2015/16)": n16, "lead16_wk": lead16,
                     "quiet 2016/17 warn unit-months (units)": "%d (%d)" % quiet(2016),
                     "quiet 2020/21 warn unit-months (units)": "%d (%d)" % quiet(2020),
                     "quiet 2022/23 warn unit-months (units)": "%d (%d)" % quiet(2022)})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso3", default="ZWE")
    args = ap.parse_args()
    iso3 = args.iso3.upper()
    c, ss, cd, units, months, W, R = build(iso3)
    out_md = []
    out_md.append(f"# Agro-climate indicator feasibility test: {iso3}\n")
    out_md.append(f"Units: {len(units)} (crop-dominant: {sum(cd.values())}). Baseline 2001-2020. Low = dry for every indicator.\n")

    # save long parquet (contract format)
    parts = []
    for k, w in W.items():
        if k in ("vci_dom", "ndvi_z_dom", "spi_3m", "spi_1m", "sm1_z"):
            continue
        lg = w.stack(future_stack=True).rename("value").reset_index()
        lg.columns = ["month", "unit_id", "value"]
        lg["signal_type"] = k
        parts.append(lg)
    long = pd.concat(parts, ignore_index=True)
    long["unit_name"] = long.unit_id.map(c.names)
    long["iso3"] = iso3
    long["month"] = long.month.dt.strftime("%Y-%m-01")
    long = long[["unit_id", "unit_name", "iso3", "month", "signal_type", "value"]]
    pq = DATA / f"agroclimate_{iso3}.parquet"
    long.to_parquet(pq, index=False)
    out_md.append(f"Saved {pq.relative_to(PIPE.parent)} rows={len(long)} signal_types={sorted(long.signal_type.unique())}\n")

    t1 = t1_shares(W, months)
    out_md.append("## T1. Share of units in alarm (%) by data month\n")
    out_md.append("Alarm: index < 35 (VCI/TCI/VHI), z <= -1 (SPI-1 <= -1.5, SPEI-1 <= -1.5, PDSI <= -2).\n")
    out_md.append(t1.to_markdown(index=False) + "\n")

    sat = sat_label(c, ss, cd, W)
    ipc, pre = ipc_label(iso3)
    t2 = t2_auc(W, months, sat, ipc, pre)
    out_md.append("## T2. ROC-AUC of indicator at data month vs outcome\n")
    out_md.append("sat = pipeline satellite label (>= 2 of 3 crop months VCI_dom < 35), seasons 2001/02-2023/24. "
                  "ipc = FEWS NET CS Phase >= 3 in Apr-Sep after the season, districts with pre-season phase < 3 only, seasons with IPC data. "
                  "Nov/Dec = planting, Jan/Feb = growing. Note VHI contains VCI, so its sat AUC is partly circular.\n")
    out_md.append(t2.to_markdown(index=False) + "\n")

    t3 = t3_replay(iso3, c, ss, cd, units, W)
    out_md.append("## T3. Alert replay (spec rule + hysteresis 2 up / 3 down, 1-month latency, no p_crisis Watch)\n")
    out_md.append(f"Declaration {COUNTRIES[iso3][1]}. 'warn_before_decl' = units whose first Warning of the season (issue month >= Oct, "
                  "issued at month end) came before the declaration. Quiet seasons: Warning unit-months Nov-Jun (units ever at Warning).\n")
    out_md.append(t3.to_markdown(index=False) + "\n")

    txt = "\n".join(out_md)
    (HERE / f"results_{iso3}.md").write_text(txt)
    print(txt)


if __name__ == "__main__":
    main()
