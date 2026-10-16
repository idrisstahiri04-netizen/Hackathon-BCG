"""Audit fixtures: small SYNTHETIC signals (invented numbers) in CONTRACT.md section 1 long format."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PIPE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PIPE))

SIG = ["precip_mm", "spi_1m", "spi_3m", "spi_6m", "ndvi_crop", "ndvi_grass", "ndvi_z_crop",
       "ndvi_z_grass", "vci_crop", "vci_grass", "sm1_z", "sm2_z", "t2m_z"]


def make_long(n_units=4, start="2001-01-01", end="2024-12-01", seed=0, iso3="ZWE"):
    rng = np.random.default_rng(seed)
    months = pd.date_range(start, end, freq="MS")
    clim = 5 + 180 * np.exp(-np.minimum((np.arange(1, 13) - 1) % 12, (1 - np.arange(1, 13)) % 12) ** 2 / 4)
    rows = []
    for i in range(n_units):
        uid = f"U{i:02d}"
        for s in SIG:
            if s == "precip_mm":
                v = clim[months.month - 1] * rng.gamma(4, 0.25, len(months))
            elif s.startswith("vci"):
                v = rng.uniform(0, 100, len(months))
            elif s.startswith("ndvi_") and "_z_" not in s:
                v = rng.uniform(0.1, 0.8, len(months))
            else:
                v = rng.normal(0, 1, len(months))
            rows.append(pd.DataFrame(dict(unit_id=uid, unit_name=f"Unit {i}", iso3=iso3,
                                          month=months, signal_type=s, value=v)))
        for s in ("crop_frac", "grass_frac"):
            rows.append(pd.DataFrame(dict(unit_id=[uid], unit_name=f"Unit {i}", iso3=iso3,
                                          month=[pd.Timestamp("2001-01-01")], signal_type=s,
                                          value=[rng.uniform(0.1, 0.5)])))
    return pd.concat(rows, ignore_index=True)


@pytest.fixture
def long_df():
    return make_long()
