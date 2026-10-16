"""SYNTHETIC signals in exact CONTRACT.md section 1 format, for testing the model pipeline.

Writes pipeline/tests/data/signals_ZWE.parquet (unimodal, 12 units) and signals_KEN.parquet
(bimodal, 8 units). Every number is invented. A season-level driver (ENSO-like AR(1)) makes
droughts somewhat predictable from pre-season signals; 2023/24 is forced to a strong drought
in ZWE and 2020-2022 in KEN. Deterministic (seed 7).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent / "data"
MONTHS = pd.date_range("2001-01-01", "2024-12-01", freq="MS")
rng = np.random.default_rng(7)


def clim_curve(peaks, width=1.4, amp=170.0, floor=4.0):
    m = np.arange(1, 13)
    c = np.full(12, floor)
    for pk, a in peaks:
        d = np.minimum((m - pk) % 12, (pk - m) % 12)
        c = c + amp * a * np.exp(-d ** 2 / (2 * width ** 2))
    return c


def zcal(x: pd.Series) -> pd.Series:
    base = x[(x.index.year >= 2001) & (x.index.year <= 2020)]
    mu = base.groupby(base.index.month).mean()
    sd = base.groupby(base.index.month).std()
    return (x - mu.reindex(x.index.month).values) / sd.reindex(x.index.month).values


def vci(x: pd.Series) -> pd.Series:
    base = x[(x.index.year >= 2001) & (x.index.year <= 2020)]
    lo = base.groupby(base.index.month).min().reindex(x.index.month).values
    hi = base.groupby(base.index.month).max().reindex(x.index.month).values
    return (100 * (x - lo) / (hi - lo)).clip(0, 100)


def make(iso3, n_units, peaks, drought_years):
    years = range(2000, 2026)
    e = {}
    v = 0.0
    for y in years:
        v = 0.5 * v + rng.normal(0, 1)
        e[y] = v
    for y, val in drought_years.items():
        e[y] = val
    rows = []
    for i in range(n_units):
        uid = f"SYN{iso3}{i:03d}"
        name = f"{iso3.title()} Unit {i}"
        wet = rng.uniform(0.5, 1.4)
        clim = clim_curve(peaks) * wet
        # agyear of each month: Jul..Jun
        ag = np.array([m.year if m.month >= 7 else m.year - 1 for m in MONTHS])
        unit_bias = {y: rng.normal(0, 0.35) for y in years}
        mult = np.exp(np.array([0.32 * e[a] + unit_bias[a] for a in ag]))
        pr = clim[MONTHS.month - 1] * mult * rng.gamma(4, 0.25, len(MONTHS))
        pr = pd.Series(pr, index=MONTHS)
        lp = np.log1p(pr)
        spi1 = zcal(lp)
        spi3 = zcal(np.log1p(pr.rolling(3, min_periods=1).sum()))
        spi6 = zcal(np.log1p(pr.rolling(6, min_periods=1).sum()))
        sm = np.zeros(len(MONTHS))
        for k in range(len(MONTHS)):
            sm[k] = (0.6 * sm[k - 1] if k else 0) + 0.8 * np.nan_to_num(spi1.iloc[k]) + rng.normal(0, 0.4)
        sm1 = zcal(pd.Series(sm, index=MONTHS))
        sm2 = zcal(pd.Series(sm, index=MONTHS).rolling(3, min_periods=1).mean() + rng.normal(0, 0.2, len(MONTHS)))
        green = clim_curve([(p + 1, a) for p, a in peaks], width=1.8, amp=1.0, floor=0.0)
        ndc = 0.25 + 0.35 * green[MONTHS.month - 1] / green.max() \
            + 0.06 * spi3.shift(1).fillna(0).values + rng.normal(0, 0.03, len(MONTHS))
        ndg = 0.22 + 0.30 * green[MONTHS.month - 1] / green.max() \
            + 0.05 * spi6.shift(1).fillna(0).values + rng.normal(0, 0.03, len(MONTHS))
        ndc, ndg = pd.Series(ndc, index=MONTHS), pd.Series(ndg, index=MONTHS)
        t2 = zcal(pd.Series(-0.5 * spi1.values + rng.normal(0, 0.8, len(MONTHS)), index=MONTHS))
        sig = {"precip_mm": pr, "spi_1m": spi1, "spi_3m": spi3, "spi_6m": spi6,
               "ndvi_crop": ndc, "ndvi_grass": ndg, "ndvi_z_crop": zcal(ndc), "ndvi_z_grass": zcal(ndg),
               "vci_crop": vci(ndc), "vci_grass": vci(ndg), "sm1_z": sm1, "sm2_z": sm2, "t2m_z": t2}
        # sprinkle missing data (missing is missing, not zero)
        for s, x in sig.items():
            x = x.copy()
            x[rng.random(len(x)) < 0.02] = np.nan
            for m, val in x.items():
                rows.append((uid, name, iso3, m.strftime("%Y-%m-01"), s, None if pd.isna(val) else float(val)))
        rows.append((uid, name, iso3, "2001-01-01", "crop_frac", float(rng.uniform(0.05, 0.5))))
        rows.append((uid, name, iso3, "2001-01-01", "grass_frac", float(rng.uniform(0.2, 0.7))))
    df = pd.DataFrame(rows, columns=["unit_id", "unit_name", "iso3", "month", "signal_type", "value"])
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT / f"signals_{iso3}.parquet", index=False)
    print(iso3, df.shape)


if __name__ == "__main__":
    make("ZWE", 12, [(1, 1.0)], {2023: -2.3, 2018: -1.5, 2015: -1.8})
    make("KEN", 8, [(4, 0.8), (11, 0.6)], {2020: -1.6, 2021: -2.0, 2022: -1.8, 2023: 1.5})
