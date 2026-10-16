"""Alert engine: source families, raw levels, hysteresis, event choice and human drivers.

Families (from signals at the reference month only, never future data):
  rain       rainy season (+1 month) only: spi_3m <= -1  or  spi_1m <= -1.5
  vegetation in-season only: min(ndvi_z_crop, ndvi_z_grass) <= -1  or  min(vci_crop, vci_grass) < 35
  soil       sm1_z <= -1
  heat       t2m_z >= 1.5            (supporting only, never counts toward Warning)
A missing signal never raises a family (missing is missing, not an alarm and not a zero).

Raw level per month (p = calibrated model probability):
  1 Watch    any family (rain/vegetation/soil) or p >= P_WATCH
  2 Warning  vegetation and (rain or soil) and p >= P_WARN
  3 Emerg.   Warning and ((p >= P_EMERG and agricultural-year month >= declaration month)
                          or (min vci < 20 and spi_3m <= -2))
Hysteresis: a level is entered after 2 consecutive runs at or above it, left after 3 runs below.

P_WATCH / P_WARN defaults come from CONTRACT/brief; train.py may tune them on CV predictions only
(never the hold-out) and saves them to pipeline/out/thresholds_<tag>.json.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_THRESHOLDS = {"p_watch": 0.35, "p_warn": 0.50, "p_emerg": 0.75}
FAMS = ["rain", "vegetation", "soil", "heat"]
CORE_FAMS = ["rain", "vegetation", "soil"]


def _lt(x, t):
    x = np.asarray(x, dtype=float)
    return np.where(np.isnan(x), False, x < t)


def _le(x, t):
    x = np.asarray(x, dtype=float)
    return np.where(np.isnan(x), False, x <= t)


def _ge(x, t):
    x = np.asarray(x, dtype=float)
    return np.where(np.isnan(x), False, x >= t)


def nanmin2(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    with np.errstate(invalid="ignore"):
        return np.fmin(a, b)          # NaN only if both NaN


def families(df: pd.DataFrame, in_season, in_rainy=None) -> pd.DataFrame:
    """df: signals at the reference month; in_season: vegetation meaningful (rainy/crop/grass windows);
    in_rainy: rainy season + 1 month (SPI on tiny dry-season totals is noise, so rain is gated)."""
    if in_rainy is None:
        in_rainy = np.ones(len(df), bool)
    rain = (_le(df["spi_3m"], -1.0) | _le(df["spi_1m"], -1.5)) & np.asarray(in_rainy, bool)
    ndz = nanmin2(df["ndvi_z_crop"], df["ndvi_z_grass"])
    vci = nanmin2(df["vci_crop"], df["vci_grass"])
    veg = (_le(ndz, -1.0) | _lt(vci, 35.0)) & np.asarray(in_season, bool)
    soil = _le(df["sm1_z"], -1.0)
    heat = _ge(df["t2m_z"], 1.5)
    out = pd.DataFrame({"rain": rain, "vegetation": veg, "soil": soil, "heat": heat}, index=df.index)
    out["agreeing"] = out[CORE_FAMS].sum(axis=1).astype(int)
    return out


def raw_levels(fam: pd.DataFrame, p, sig: pd.DataFrame, after_decl, th: dict) -> np.ndarray:
    p = np.asarray(p, float)
    anyfam = fam[CORE_FAMS].any(axis=1).values
    warn_fam = (fam["vegetation"] & (fam["rain"] | fam["soil"])).values
    lvl = np.zeros(len(p), int)
    lvl[anyfam | _ge(p, th["p_watch"])] = 1
    warn = warn_fam & _ge(p, th["p_warn"])
    lvl[warn] = 2
    vci = nanmin2(sig["vci_crop"], sig["vci_grass"])
    extreme = _lt(vci, 20.0) & _le(sig["spi_3m"], -2.0)
    emerg = warn & ((_ge(p, th["p_emerg"]) & np.asarray(after_decl, bool)) | extreme)
    lvl[emerg] = 3
    return lvl


def hysteresis(raw, up: int = 2, down: int = 3) -> np.ndarray:
    """raw: monthly raw levels for one unit (chronological). 2 runs up, 3 runs down."""
    level, out, hist = 0, [], []
    for r in raw:
        hist.append(int(r))
        if r > level and len(hist) >= up and all(h > level for h in hist[-up:]):
            level = min(hist[-up:])
        elif r < level and len(hist) >= down and all(h < level for h in hist[-down:]):
            level = max(hist[-down:])
        out.append(level)
    return np.array(out, int)


def drivers(row: dict, fam: dict) -> list:
    """Top-3 human-readable drivers, ranked by how far each signal is past its threshold."""
    cand = []
    f = lambda k: row.get(k)
    ok = lambda v: v is not None and not (isinstance(v, float) and np.isnan(v))
    if fam["rain"]:
        s3, s1 = f("spi_3m"), f("spi_1m")
        if ok(s3) and s3 <= -1:
            cand.append(((-1 - s3) + 1, f"3-month rainfall index {s3:.1f} (well below normal)"))
        if ok(s1) and s1 <= -1.5:
            cand.append(((-1.5 - s1) + 1, f"last month's rain index {s1:.1f} (very dry)"))
    if fam["vegetation"]:
        for k, lab in (("vci_crop", "cropland"), ("vci_grass", "grazing land")):
            v = f(k)
            if ok(v) and v < 35:
                cand.append(((35 - v) / 15 + 1, f"{lab} greenness {v:.0f}/100 (VCI, poor)"))
        for k, lab in (("ndvi_z_crop", "cropland"), ("ndvi_z_grass", "grazing land")):
            v = f(k)
            if ok(v) and v <= -1:
                cand.append(((-1 - v) + 0.9, f"{lab} greenness {v:.1f} SD below normal"))
    if fam["soil"]:
        v = f("sm1_z")
        if ok(v):
            cand.append(((-1 - v) + 1, f"topsoil moisture {v:.1f} SD below normal"))
    if fam["heat"]:
        v = f("t2m_z")
        if ok(v):
            cand.append(((v - 1.5) + 0.5, f"hot: temperature {v:+.1f} SD above normal"))
    cand.sort(key=lambda c: -c[0])
    seen, out = set(), []
    for _, txt in cand:              # one line per land type / family keeps it readable
        key = txt.split(" ")[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(txt)
    return out[:3]


def confidence(agreeing: int, n_missing: int) -> str:
    if n_missing >= 3:
        return "low"
    return "high" if agreeing >= 3 else "medium" if agreeing == 2 else "low"


def tune_thresholds(oof: pd.DataFrame, grid_watch=None, grid_warn=None) -> dict:
    """oof: CV out-of-fold rows (leads 1-3) with columns p_cal, label, rain/vegetation/soil.

    Warning threshold: maximise F1 of the raw Warning condition against the label.
    Watch threshold: maximise F1 of (any family or p >= t) (F2 drove Watch to near-always-on).
    Uses CV predictions only.
    """
    grid_watch = grid_watch or [round(x, 2) for x in np.arange(0.15, 0.51, 0.05)]
    grid_warn = grid_warn or [round(x, 2) for x in np.arange(0.25, 0.71, 0.05)]
    d = oof.dropna(subset=["label", "p_cal"])
    y = d["label"].values.astype(bool)
    wf = (d["vegetation"] & (d["rain"] | d["soil"])).values
    anyf = d[CORE_FAMS].any(axis=1).values

    def fb(pred, beta):
        tp = (pred & y).sum(); fp = (pred & ~y).sum(); fn = (~pred & y).sum()
        if tp == 0:
            return 0.0
        pr, rc = tp / (tp + fp), tp / (tp + fn)
        return (1 + beta ** 2) * pr * rc / (beta ** 2 * pr + rc)

    res = {}
    sw = {t: fb(wf & (d.p_cal.values >= t), 1.0) for t in grid_warn}
    res["p_warn"] = float(max(sw, key=sw.get))
    sa = {t: fb(anyf | (d.p_cal.values >= t), 1.0) for t in grid_watch}
    res["p_watch"] = float(min(max(sa, key=sa.get), res["p_warn"]))
    res["p_emerg"] = max(DEFAULT_THRESHOLDS["p_emerg"], res["p_warn"] + 0.15)
    res["cv_f1_warn"] = round(float(sw[res["p_warn"]]), 3)
    res["cv_f1_watch"] = round(float(sa[res["p_watch"]]), 3)
    res["cv_f1_warn_default"] = round(float(fb(wf & (d.p_cal.values >= 0.5), 1.0)), 3)
    return res
