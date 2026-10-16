"""Features per (unit, reference month r). Only months <= r are used (no future data).

Per signal: current value, lags 1-3, 3-month trend (x_r - x_{r-3}).
Plus 3-month rain as % of normal, month-of-year sin/cos, static crop/grass fractions.
Per target row: lead (months from r to window start), season phase (months since planting start,
mod 12) and a bimodal flag.

Note: SPI / z / VCI baselines (2001-2020) come from the signals table as specified in CONTRACT.md;
that is a fixed climatology, not information about the target season.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import BASE_END, BASE_START, DRY_SIGNALS, Country, months_between

SIGS = ["spi_1m", "spi_3m", "spi_6m", "ndvi_z_crop", "ndvi_z_grass", "vci_crop", "vci_grass",
        "sm1_z", "sm2_z", "t2m_z"]


def unit_month_features(c: Country) -> pd.DataFrame:
    w = c.wide
    g = w.groupby(level="unit_id", group_keys=False)
    out = {}
    for s in SIGS:
        x = w[s]
        out[s] = x
        for L in (1, 2, 3):
            out[f"{s}_l{L}"] = g[s].shift(L)
        out[f"{s}_tr3"] = x - out[f"{s}_l3"]
    # 3-month rain as fraction of normal (normal = baseline mean of the same 3-month sum)
    p3 = g["precip_mm"].rolling(3, min_periods=3).sum().reset_index(level=0, drop=True).reindex(w.index)
    mon = w.index.get_level_values("month")
    base = (mon.year >= BASE_START) & (mon.year <= BASE_END)
    key = pd.DataFrame({"u": w.index.get_level_values("unit_id"), "m": mon.month, "p3": p3.values})
    clim = key[base].groupby(["u", "m"]).p3.mean()
    norm = clim.reindex(pd.MultiIndex.from_arrays([key.u, key.m])).values
    out["rain_pct3"] = pd.Series(np.where(norm > 0, p3.values / norm - 1.0, np.nan), index=w.index)
    for s in DRY_SIGNALS:                   # state variables, no lags/trends; apply_latency moves them to r-1
        out[s] = w[s]
    f = pd.DataFrame(out)
    f["month_sin"] = np.sin(2 * np.pi * mon.month / 12)
    f["month_cos"] = np.cos(2 * np.pi * mon.month / 12)
    st = c.static.reindex(w.index.get_level_values("unit_id"))
    f["crop_frac"] = st["crop_frac"].values
    f["grass_frac"] = st["grass_frac"].values
    return f


FEATURES = None   # filled lazily


def feature_columns(f: pd.DataFrame) -> list:
    return list(f.columns) + ["lead", "phase", "bimodal"]


def make_xy(feat: pd.DataFrame, targets: pd.DataFrame, leads, plant_start: dict, bimodal: dict) -> pd.DataFrame:
    """targets: rows from labels.build_targets. Returns one row per (target, lead) with features at r=W0-lead.

    plant_start: unit -> calendar month of the main season's planting start (for phase).
    """
    parts = []
    for L in leads:
        t = targets.copy()
        t["lead"] = L
        t["r"] = t["W0"] - pd.DateOffset(months=L)
        parts.append(t)
    t = pd.concat(parts, ignore_index=True)
    return attach(feat, t, plant_start, bimodal)


def attach(feat: pd.DataFrame, t: pd.DataFrame, plant_start: dict, bimodal: dict) -> pd.DataFrame:
    """t needs columns unit_id, r, lead. Joins unit-month features at (unit_id, r)."""
    idx = pd.MultiIndex.from_arrays([t["unit_id"], t["r"]])
    X = feat.reindex(idx).reset_index(drop=True)
    X.index = t.index
    ps = t["unit_id"].map(plant_start)
    X["phase"] = ((t["r"].dt.month - ps) % 12).astype(float)
    X["bimodal"] = t["unit_id"].map(bimodal).astype(float)
    X["lead"] = t["lead"].astype(float)
    return pd.concat([t.drop(columns=[k for k in X.columns if k in t.columns]), X], axis=1)


# ----------------------------------------------------------------------------- v2 climate features
# (pipeline/experiments/report.md section D). Added outside unit_month_features so the IPC model and
# the leakage tests keep their inputs. Not shifted by apply_latency: both are public in the issue month.
SFC_COLS = ["sfc_z_m13", "sfc_pbn_m13", "sfc_z_m46", "sfc_pbn_m46"]
SOUTH_ISO = {"ZWE", "MWI", "ZMB", "MOZ", "NAM", "BWA", "ZAF", "MDG", "AGO"}
SOUTH_LAT = -8.0


def seasonal_fc_features(iso3: str, index: pd.MultiIndex, data_dir) -> pd.DataFrame:
    """NMME MME3 forecast issued in month r for months r+1..r+3 / r+4..r+6 (anomaly z, P(below normal))."""
    from pathlib import Path
    out = pd.DataFrame(index=index, columns=SFC_COLS, dtype=float)
    f = Path(data_dir) / f"seasonal_fc_{iso3}.parquet"
    if not f.exists():
        return out                                    # missing is missing
    d = pd.read_parquet(f)
    d["issue_month"] = pd.to_datetime(d["issue_month"])
    d = d[d["product"] == "NMME/MME3"]
    g = d.groupby(["unit_id", "issue_month", "target_window"])[["anom_z", "p_below_normal"]].mean().unstack("target_window")
    g.columns = [f"sfc_{'z' if a == 'anom_z' else 'pbn'}_{b.replace('-', '')}" for a, b in g.columns]
    g = g.reindex(index)
    for c in out.columns:
        if c in g:
            out[c] = g[c].values
    return out


def unit_lat(iso3: str, units, data_dir) -> dict:
    """Centroid latitude (mean of polygon vertices) per unit from units_<ISO3>.geojson; NaN if absent."""
    import json
    from pathlib import Path
    f = Path(data_dir) / f"units_{iso3}.geojson"
    out = {u: np.nan for u in units}
    if not f.exists():
        return out
    for ft in json.loads(f.read_text())["features"]:
        pr, g = ft["properties"], ft["geometry"]
        uid = pr.get("shapeID") or pr.get("id")
        geoms = g["geometries"] if g["type"] == "GeometryCollection" else [g]
        ys = []
        for gg in geoms:
            polys = gg["coordinates"] if gg["type"] == "MultiPolygon" else [gg["coordinates"]] if gg["type"] == "Polygon" else []
            for p in polys:
                ys += [pt[1] for pt in p[0]]
        if uid in out and ys:
            out[uid] = float(np.mean(ys))
    return out


def oni_x_south(iso3: str, index: pd.MultiIndex, data_dir) -> pd.Series:
    """ONI trimester ending r-1 (NOAA, public by ~10th of r) x (+1 south of 8S, -1 north)."""
    import json
    from pathlib import Path
    f = Path(__file__).resolve().parent / "experiments" / "climate_indices.json"
    if not f.exists():
        return pd.Series(np.nan, index=index)
    oni = pd.Series({pd.Timestamp(k + "-01"): v for k, v in json.loads(f.read_text())["oni_trimester_end"].items()})
    mon = index.get_level_values("month")
    known = oni.reindex(mon - pd.DateOffset(months=1)).values
    units = index.get_level_values("unit_id")
    lat = unit_lat(iso3, pd.unique(units), data_dir)
    la = np.array([lat.get(u, np.nan) for u in units], float)
    south = np.where(np.isnan(la), iso3 in SOUTH_ISO, la < SOUTH_LAT)
    return pd.Series(known * np.where(south, 1.0, -1.0), index=index)


def climate_features(c: Country, index: pd.MultiIndex, data_dir) -> pd.DataFrame:
    f = seasonal_fc_features(c.iso3, index, data_dir)
    f["oni_x_south"] = oni_x_south(c.iso3, index, data_dir).values
    return f
