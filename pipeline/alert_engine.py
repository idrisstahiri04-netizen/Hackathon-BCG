"""Alert engine (v1.1 "spec mode"): source families, levels, hysteresis, drivers.

Families (signals as published at the issue month, i.e. after data latency; never future data):
  rain       rainy season (+1 month) only: spi_3m <= -1  or  spi_1m <= -1.5
  soil       rainy season (+1 month) only: sm1_z <= -1          (audit M5: dry-season z is noise)
  vegetation in-season only, dominant land cover (crop if crop_frac >= 0.2 and crop data exist, else
             grass): VCI < 35 in the current AND previous published month, or ndvi_z <= -1 in both
             crop and grass (grass only where no crop data). Tightened on CV years 2001-2022 only:
             the old min(crop,grass) "z<=-1 or VCI<35" fired in 28% of in-season months of normal
             seasons; this rule 15.5% (and 37% in label-positive seasons).
  heat       t2m_z >= 1.5            (supporting only, never counts toward any level)
A missing signal never raises a family (missing is missing).

Levels (spec rule only; the model probability p is NOT used for levels, audit B3; p is exported as
information for NGO / food-bank text):
  1 Watch    any one of rain / vegetation / soil, or strong rain+soil dryness (spi_3m <= -1.5 and sm1_z <= -1.5)
  2 Warning  vegetation and (rain or soil)      (two independent families: EO + weather)
  3 Emerg.   Warning and an official declaration in force (from the declaration month to the end of
             that agricultural year only, never other years). No satellite-only Emergency (audit B1).
Hysteresis (spec): go up to the level held for the last 2 runs; go down only after 3 runs below
(to the highest of those 3). No fast entry, no one-step limit. held = level kept only by hysteresis.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_THRESHOLDS = {"p_watch": 0.35, "p_warn": 0.50, "p_emerg": 0.75, "p_fast": None}
FAMS = ["rain", "vegetation", "soil", "heat"]
CORE_FAMS = ["rain", "vegetation", "soil"]
STRONG_SPI3, STRONG_SM1 = -1.5, -1.5


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




def families(df: pd.DataFrame, in_season, in_rainy=None, crop_dom=None) -> pd.DataFrame:
    """df: signals at the issue month (+ vci_crop_l1 / vci_grass_l1 = previous published month).
    in_season: vegetation meaningful; in_rainy: rainy season + 1 month; crop_dom: unit is cropland."""
    n = len(df)
    inr = np.ones(n, bool) if in_rainy is None else np.asarray(in_rainy, bool)
    cd = np.zeros(n, bool) if crop_dom is None else np.asarray(crop_dom, bool)
    col = lambda k: np.asarray(df[k], float) if k in df else np.full(n, np.nan)
    rain = (_le(df["spi_3m"], -1.0) | _le(df["spi_1m"], -1.5)) & inr
    vc, vg = col("vci_crop"), col("vci_grass")
    vcp, vgp = col("vci_crop_l1"), col("vci_grass_l1")
    use_c = cd & ~np.isnan(vc)
    vci = np.where(use_c, vc, vg)
    vprev = np.where(use_c, vcp, vgp)
    zc, zg = col("ndvi_z_crop"), col("ndvi_z_grass")
    zboth = np.where(~np.isnan(zc), _le(zc, -1.0) & _le(zg, -1.0), _le(zg, -1.0))
    veg = ((_lt(vci, 35.0) & _lt(vprev, 35.0)) | zboth) & np.asarray(in_season, bool)
    soil = _le(df["sm1_z"], -1.0) & inr
    heat = _ge(df["t2m_z"], 1.5)
    out = pd.DataFrame({"rain": rain, "vegetation": veg, "soil": soil, "heat": heat}, index=df.index)
    out["agreeing"] = out[CORE_FAMS].sum(axis=1).astype(int)
    out["strong_weather"] = _le(df["spi_3m"], STRONG_SPI3) & _le(df["sm1_z"], STRONG_SM1) & inr
    return out


def conditions(fam: pd.DataFrame, decl_in_force=None) -> dict:
    n = len(fam)
    dif = np.zeros(n, bool) if decl_in_force is None else np.asarray(decl_in_force, bool)
    warn = (fam["vegetation"] & (fam["rain"] | fam["soil"])).values.astype(bool)
    watch = fam[CORE_FAMS].any(axis=1).values.astype(bool) | fam["strong_weather"].values.astype(bool)
    return {"watch": watch | warn, "warn": warn, "emerg": warn & dif}


def raw_levels(fam: pd.DataFrame, decl_in_force=None) -> np.ndarray:
    c = conditions(fam, decl_in_force)
    lvl = np.zeros(len(fam), int)
    lvl[c["watch"]] = 1
    lvl[c["warn"]] = 2
    lvl[c["emerg"]] = 3
    return lvl


def hysteresis(raw, fast=None, up: int = 2, down: int = 3, one_step: bool = False):
    """raw: monthly raw levels for one unit (chronological). Returns (levels, held).

    Up: to the level held for the last `up` runs (min of them). Down: after `down` runs below, to the
    highest of those runs. fast (1-run entry) and one_step are off by default (spec v1.1).
    held[k] = True when the displayed level is kept only by hysteresis (raw level < displayed level).
    """
    raw = [int(r) for r in raw]
    fast = np.zeros(len(raw), bool) if fast is None else np.asarray(fast, bool)
    level, out, held, hist = 0, [], [], []
    for k, r in enumerate(raw):
        hist.append(r)
        if r > level and fast[k]:
            level = r
        elif r > level and len(hist) >= up and all(h > level for h in hist[-up:]):
            level = level + 1 if one_step else min(hist[-up:])
        elif r < level and len(hist) >= down and all(h < level for h in hist[-down:]):
            level = level - 1 if one_step else max(hist[-down:])
        out.append(level)
        held.append(r < level)
    return np.array(out, int), np.array(held, bool)


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




def rule_stats(oof: pd.DataFrame) -> dict:
    """CV out-of-fold rows (leads 1-3): how well the spec Watch / Warning conditions at the issue
    month anticipate the satellite label. Informational only (nothing is tuned on it)."""
    d = oof.dropna(subset=["label"]).reset_index(drop=True)
    y = d["label"].values.astype(bool)
    c = conditions(d)

    def st(pred):
        tp = (pred & y).sum(); fp = (pred & ~y).sum(); fn = (~pred & y).sum()
        return {"rate": round(float(pred.mean()), 3),
                "precision": round(float(tp / (tp + fp)), 3) if tp + fp else None,
                "recall": round(float(tp / (tp + fn)), 3) if tp + fn else None,
                "f1": round(float(2 * tp / (2 * tp + fp + fn)), 3) if tp else 0.0}
    return {"cv_base_rate": round(float(y.mean()), 3), "watch": st(c["watch"]), "warn": st(c["warn"]),
            "note": "levels come from the spec family rule; p is information only (v1.1, audit B3)"}


CLIMATE_REASON = "climate readiness (El Niño + dry forecast)"


def climate_readiness(oni_x_south, sfc_pbn_m13) -> np.ndarray:
    """Watch-only climate input for NGO / officer audiences (Ready-Set-Go 'ready'):
    signed ONI (x +1 south of 8S, -1 north; trimester ending r-1) >= 1.0, or >= 0.5 with NMME
    P(below normal, months r+1..r+3) >= 0.5. Never counts toward Warning; missing never fires.
    Evidence: pipeline/experiments/report.md section C (CV years only)."""
    o = np.asarray(oni_x_south, float)
    pb = np.asarray(sfc_pbn_m13, float)
    return _ge(o, 1.0) | (_ge(o, 0.5) & _ge(pb, 0.5))
