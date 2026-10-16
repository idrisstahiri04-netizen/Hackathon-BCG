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

from common import BASE_END, BASE_START, Country, months_between

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
