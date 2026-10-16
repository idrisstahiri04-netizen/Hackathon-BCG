"""Candidate extra features, computed per (unit_id, month) from the cached wide signal grid
(pipeline/experiments/wide_base.parquet) and joined to the cached rows at (unit_id, r).
Only months <= r are used. Baseline for 'normal' = 2001-2020 (same as the signals table).

Feature groups (keys of GROUPS):
  cum_rain    rain_cum_pct: season-to-date rain / normal season-to-date rain - 1 (NaN outside rainy season + 2 months)
  dry_spell   dry_months: months since the last month with >= 20 mm and >= 50% of its climatological mean (cap 12)
  ndvi_slope  *_d1: 1-month change of ndvi_z_crop/grass and vci_crop/grass (2 composites ~ 1 month)
  soil_grad   sm_grad: sm1_z - sm2_z (surface drying faster than root zone)
  phase_x     interactions for the linear model: spi_3m / vci / sm1_z x {early, mid, late} season dummies
  spi_gated   spi_1m_g, spi_3m_g: SPI only inside rainy season (+1 month), else NaN
  oni         ONI known at origin (trimester ending at r-1), its 3-month change, x south-Africa flag, lat
  oni_lag0    same but trimester ending at r (assumes ONI available with the month-r satellite data)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = Path(os.environ.get("EXP_OUT", str(HERE)))   # artefacts (caches, OOF, results); HERE = code + small data
OUT.mkdir(parents=True, exist_ok=True)
BASE_START, BASE_END = 2001, 2020
LAT = 1            # data latency (months): extras derived from satellite/reanalysis are joined at r - LAT
SAT_COLS = {"rain_cum_pct", "dry_months", "ndvi_z_crop_d1", "ndvi_z_grass_d1", "vci_crop_d1", "vci_grass_d1",
            "sm_grad", "spi_1m_g", "spi_3m_g"}
SOUTH = {"ZWE", "MWI", "ZMB", "MOZ", "NAM", "BWA", "ZAF", "MDG", "AGO"}   # fallback if no centroid
SOUTH_LAT = -8.0   # units with centroid latitude < -8 get the southern-Africa ENSO sign (El Nino -> dry DJF)


def _wide(path=None) -> pd.DataFrame:
    w = pd.read_parquet(path or OUT / "wide_base.parquet")
    w["month"] = pd.to_datetime(w["month"])
    return w.sort_values(["unit_id", "month"]).reset_index(drop=True)


def _seasons(path=None) -> dict:
    return json.loads((path or OUT / "seasons_base.json").read_text())


# ----------------------------------------------------------------------------- precip-based
def cum_rain(w: pd.DataFrame, seas: dict) -> pd.Series:
    """Season-to-date rain vs normal. Window = from the first rainy month of the nearest season start
    (up to 7 months back) to r; only while r is within rainy season + 2 months."""
    g = w.groupby("unit_id")["precip_mm"]
    roll = {k: g.rolling(k + 1, min_periods=k + 1).sum().reset_index(level=0, drop=True) for k in range(8)}
    mon = w["month"].dt.month.values
    k_of = np.full(len(w), -1)
    for u, info in seas.items():
        m = (w["unit_id"] == u).values
        best = np.full(m.sum(), 99)
        for s in info["seasons"]:
            first = s["rainy"][0]
            k = (mon[m] - first) % 12
            k = np.where(k <= len(s["rainy"]) + 1, k, 99)
            best = np.minimum(best, k)
        k_of[m] = np.where(best < 99, best, -1)
    cum = np.full(len(w), np.nan)
    for k in range(8):
        sel = k_of == k
        cum[sel] = roll[k].values[sel]
    cum = pd.Series(cum, index=w.index)
    yr = w["month"].dt.year
    base = (yr >= BASE_START) & (yr <= BASE_END)
    key = pd.DataFrame({"u": w["unit_id"], "m": mon, "c": cum})
    clim = key[base].groupby(["u", "m"]).c.mean()
    norm = clim.reindex(pd.MultiIndex.from_arrays([key.u, key.m])).values
    return pd.Series(np.where(norm > 0, cum.values / norm - 1.0, np.nan), index=w.index, name="rain_cum_pct")


def dry_months(w: pd.DataFrame) -> pd.Series:
    mon = w["month"].dt.month
    yr = w["month"].dt.year
    base = (yr >= BASE_START) & (yr <= BASE_END)
    clim = w[base].groupby(["unit_id", mon[base]])["precip_mm"].mean()
    cl = clim.reindex(pd.MultiIndex.from_arrays([w["unit_id"], mon])).values
    wet = (w["precip_mm"].values >= 20) & (w["precip_mm"].values >= 0.5 * cl)
    out = np.full(len(w), np.nan)
    for u, idx in w.groupby("unit_id").indices.items():
        n = np.nan
        for i in idx:
            if np.isnan(w["precip_mm"].values[i]):
                out[i] = n
                continue
            n = 0.0 if wet[i] else (n + 1 if not np.isnan(n) else np.nan)
            out[i] = n
    return pd.Series(np.minimum(out, 12), index=w.index, name="dry_months")


# ----------------------------------------------------------------------------- vegetation / soil
def ndvi_slope(w: pd.DataFrame) -> pd.DataFrame:
    g = w.groupby("unit_id")
    out = {}
    for s in ["ndvi_z_crop", "ndvi_z_grass", "vci_crop", "vci_grass"]:
        out[f"{s}_d1"] = w[s] - g[s].shift(1)
    return pd.DataFrame(out, index=w.index)


def soil_grad(w: pd.DataFrame) -> pd.Series:
    return (w["sm1_z"] - w["sm2_z"]).rename("sm_grad")


def spi_gated(w: pd.DataFrame, seas: dict) -> pd.DataFrame:
    mon = w["month"].dt.month.values
    inr = np.zeros(len(w), bool)
    for u, info in seas.items():
        m = (w["unit_id"] == u).values
        rm = set()
        for s in info["seasons"]:
            rm |= set(s["rainy"]) | {s["rainy"][-1] % 12 + 1}
        inr[m] = np.isin(mon[m], list(rm))
    return pd.DataFrame({"spi_1m_g": np.where(inr, w["spi_1m"], np.nan),
                         "spi_3m_g": np.where(inr, w["spi_3m"], np.nan)}, index=w.index)


# ----------------------------------------------------------------------------- ENSO
def load_oni() -> pd.DataFrame:
    """NOAA ONI. Row SEAS=DJF YR=1950 -> trimester Dec 1949..Feb 1950, centred Jan 1950, ends Feb 1950.
    Returns DataFrame indexed by the trimester's END month (first of month) with column oni."""
    jf = HERE / "climate_indices.json"
    if jf.exists():
        d = json.loads(jf.read_text())["oni_trimester_end"]
        return pd.DataFrame({"oni": [np.nan if v is None else v for v in d.values()]},
                            index=pd.to_datetime(list(d.keys()))).sort_index()
    f = HERE / "data" / "oni" / "oni.ascii.txt"
    d = pd.read_fwf(f)
    d.columns = [c.strip() for c in d.columns]
    seas = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON", "OND", "NDJ"]
    centre = d["SEAS"].map({s: i + 1 for i, s in enumerate(seas)})
    end = pd.to_datetime(dict(year=d["YR"], month=centre, day=1)) + pd.DateOffset(months=1)
    out = pd.DataFrame({"oni": d["ANOM"].astype(float).values}, index=end).sort_index()
    return out[~out.index.duplicated()]


def oni_features(w: pd.DataFrame, lag: int = 1) -> pd.DataFrame:
    """ONI of the trimester ending at month r-lag (lag=1: strictly known at r)."""
    o = load_oni()["oni"]
    end = w["month"] - pd.DateOffset(months=lag)
    cur = o.reindex(end).values
    prev = o.reindex(end - pd.DateOffset(months=3)).values
    cen = pd.read_parquet(OUT / "unit_centroids.parquet").set_index("unit_id")["lat"]
    lat = w["unit_id"].map(cen).values
    south = np.where(np.isnan(lat), w["iso3"].isin(SOUTH).values, lat < SOUTH_LAT).astype(float)
    sfx = "" if lag == 1 else f"_lag{lag}"
    return pd.DataFrame({f"oni{sfx}": cur, f"oni_d3{sfx}": cur - prev,
                         f"oni_x_south{sfx}": cur * (2 * south - 1), "lat": lat}, index=w.index)


def load_nino34() -> pd.Series:
    """Monthly Nino3.4 SST anomaly (ERSSTv5, 1991-2020 base), indexed by month."""
    jf = HERE / "climate_indices.json"
    if jf.exists():
        d = json.loads(jf.read_text())["nino34"]
        return pd.Series([np.nan if v is None else v for v in d.values()], index=pd.to_datetime(list(d.keys())), name="nino34").sort_index()
    f = HERE / "data" / "nino34" / "ersst5.nino.mth.91-20.ascii"
    d = pd.read_csv(f, sep=r"\s+")
    idx = pd.to_datetime(dict(year=d["YR"], month=d["MON"], day=1))
    return pd.Series(d.iloc[:, -1].astype(float).values, index=idx, name="nino34").sort_index()


def load_dmi() -> pd.Series:
    """Monthly Dipole Mode Index (HadISST), -9999 = missing."""
    jf = HERE / "climate_indices.json"
    if jf.exists():
        d = json.loads(jf.read_text())["dmi"]
        return pd.Series([np.nan if v is None else v for v in d.values()], index=pd.to_datetime(list(d.keys())), name="dmi").sort_index()
    f = HERE / "data" / "dmi" / "dmi.had.long.data"
    vals = {}
    for line in f.read_text().splitlines()[1:]:
        parts = line.split()
        if len(parts) == 13 and parts[0].isdigit():
            y = int(parts[0])
            for m, v in enumerate(parts[1:], 1):
                v = float(v)
                vals[pd.Timestamp(y, m, 1)] = np.nan if v <= -999 else v
    return pd.Series(vals, name="dmi").sort_index()


def index_features(w: pd.DataFrame, lag: int = 1) -> pd.DataFrame:
    """Monthly climate indices known at issue month r: value of month r-lag, and 3-month mean."""
    n34, dmi = load_nino34(), load_dmi()
    m = w["month"] - pd.DateOffset(months=lag)
    cen = pd.read_parquet(OUT / "unit_centroids.parquet").set_index("unit_id")["lat"]
    lat = w["unit_id"].map(cen).values
    south = np.where(np.isnan(lat), w["iso3"].isin(SOUTH).values, lat < SOUTH_LAT).astype(float)
    n = n34.reindex(m).values
    n3 = n34.rolling(3, min_periods=2).mean().reindex(m).values
    dm = dmi.reindex(m).values
    dm3 = dmi.rolling(3, min_periods=2).mean().reindex(m).values
    return pd.DataFrame({"nino34": n, "nino34_3m": n3, "nino34_x_south": n * (2 * south - 1),
                         "dmi": dm, "dmi_3m": dm3, "dmi_x_east": dm * (1 - south)}, index=w.index)


def seasonal_features(w: pd.DataFrame) -> pd.DataFrame:
    """NMME seasonal rainfall forecast issued in month r (pipeline/data/seasonal_fc_<ISO3>.parquet):
    anom_z and P(below normal) for the next 3 months (m1-3) and months 4-6 (m4-6). Product = multi-model
    mean (NMME/MME3) when present, else the mean over available products. NMME is published in the first
    ~10 days of the issue month, so it is known by the end of month r (our issue convention)."""
    data_dir = HERE.parent / "data"
    parts = []
    for iso in sorted(w["iso3"].unique()):
        f = data_dir / f"seasonal_fc_{iso}.parquet"
        if f.exists():
            parts.append(pd.read_parquet(f))
    out = pd.DataFrame(index=w.index, columns=["sfc_z_m13", "sfc_pbn_m13", "sfc_z_m46", "sfc_pbn_m46"], dtype=float)
    if not parts:
        return out
    d = pd.concat(parts, ignore_index=True)
    d["issue_month"] = pd.to_datetime(d["issue_month"])
    mme = d[d["product"] == "NMME/MME3"]
    d = mme if len(mme) else d
    g = d.groupby(["unit_id", "issue_month", "target_window"])[["anom_z", "p_below_normal"]].mean().unstack("target_window")
    g.columns = [f"sfc_{'z' if a == 'anom_z' else 'pbn'}_{b.replace('m', 'm').replace('-', '')}" for a, b in g.columns]
    idx = pd.MultiIndex.from_arrays([w["unit_id"], w["month"]])
    g = g.reindex(idx)
    for c in out.columns:
        if c in g.columns:
            out[c] = g[c].values
    return out


# ----------------------------------------------------------------------------- phase interactions
def phase_x(rows: pd.DataFrame) -> pd.DataFrame:
    """Row-level (needs phase). early = phase 0-1 (planting), mid = 2-3 (core), late = 4-5."""
    ph = rows["phase"].values
    early, mid, late = (ph <= 1).astype(float), ((ph >= 2) & (ph <= 3)).astype(float), ((ph >= 4) & (ph <= 5)).astype(float)
    out = {}
    for s in ["spi_3m", "sm1_z"]:
        x = rows[s].fillna(0).values
        out[f"{s}_early"], out[f"{s}_mid"], out[f"{s}_late"] = x * early, x * mid, x * late
    vci = np.fmin(rows["vci_crop"].values, rows["vci_grass"].values)
    vci = np.where(np.isnan(vci), 50.0, vci) - 50.0
    out["vci_mid"], out["vci_late"] = vci * mid, vci * late
    out["lead_x_spi3"] = rows["lead"].values * rows["spi_3m"].fillna(0).values
    return pd.DataFrame(out, index=rows.index)


# ----------------------------------------------------------------------------- assembly
GROUPS = {
    "cum_rain": ["rain_cum_pct"],
    "dry_spell": ["dry_months"],
    "ndvi_slope": ["ndvi_z_crop_d1", "ndvi_z_grass_d1", "vci_crop_d1", "vci_grass_d1"],
    "soil_grad": ["sm_grad"],
    "spi_gated": ["spi_1m_g", "spi_3m_g"],
    "oni": ["oni", "oni_d3", "oni_x_south", "lat"],
    "oni_lag0": ["oni_lag0", "oni_d3_lag0", "oni_x_south_lag0"],
    "oni_plain": ["oni"],
    "oni_south": ["oni_x_south"],
    "nino34": ["nino34", "nino34_3m", "nino34_x_south"],
    "nino34_south": ["nino34_x_south"],
    "dmi": ["dmi", "dmi_3m", "dmi_x_east"],
    "seasonal_fc": ["sfc_z_m13", "sfc_pbn_m13", "sfc_z_m46", "sfc_pbn_m46"],
    "seasonal_fc_m13": ["sfc_z_m13", "sfc_pbn_m13"],
    "lat": ["lat"],
    "phase_x": ["spi_3m_early", "spi_3m_mid", "spi_3m_late", "sm1_z_early", "sm1_z_mid", "sm1_z_late",
                "vci_mid", "vci_late", "lead_x_spi3"],
}


def unit_month_extra(cache=None, wide_path=None, seasons_path=None) -> pd.DataFrame:
    """All unit-month level extra features, indexed by (unit_id, month). Cached to extra_um.parquet."""
    cache = cache or OUT / "extra_um.parquet"
    all_cols = {c for g in GROUPS.values() for c in g} - set(GROUPS["phase_x"])
    if cache.exists():
        e = pd.read_parquet(cache)
        if all_cols <= set(e.columns):           # stale cache (older feature set) -> rebuild
            e["month"] = pd.to_datetime(e["month"])
            return e.set_index(["unit_id", "month"])
    w = _wide(wide_path)
    seas = _seasons(seasons_path)
    parts = [w[["unit_id", "month"]], cum_rain(w, seas), dry_months(w), ndvi_slope(w), soil_grad(w),
             spi_gated(w, seas), oni_features(w, 1), oni_features(w, 0).drop(columns=["lat"]), index_features(w, 1),
             seasonal_features(w)]
    e = pd.concat(parts, axis=1)
    e.to_parquet(cache, index=False)
    return e.set_index(["unit_id", "month"])


def with_extra(rows: pd.DataFrame, groups: list, um_path=None, wide_path=None, seasons_path=None) -> tuple[pd.DataFrame, list]:
    """Returns rows with the extra columns joined at (unit_id, r) and the list of added columns."""
    cols = []
    rows = rows.copy()
    um_groups = [g for g in groups if g != "phase_x"]
    if um_groups:
        e = unit_month_extra(um_path, wide_path, seasons_path)
        need = sorted({c for g in um_groups for c in GROUPS[g]})
        idx = pd.MultiIndex.from_arrays([rows["unit_id"], rows["r"]])
        idx_lat = pd.MultiIndex.from_arrays([rows["unit_id"], rows["r"] - pd.DateOffset(months=LAT)])
        X = e[need].reindex(idx)
        X_lat = e[need].reindex(idx_lat)
        for c in need:
            rows[c] = (X_lat if c in SAT_COLS else X)[c].values
        cols += need
    if "phase_x" in groups:
        px = phase_x(rows)
        for c in px.columns:
            rows[c] = px[c].values
        cols += list(px.columns)
    return rows, cols
