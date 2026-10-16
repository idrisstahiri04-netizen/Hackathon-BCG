"""Shared config + loaders for the model pipeline (labels, features, train, alerts, export).

Input is pipeline/data/signals_<ISO3>.parquet in CONTRACT.md section 1 format.
Everything is keyed on (unit_id, month). Missing data stays NaN.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA_DIR = HERE / "data"
OUT_DIR = HERE / "out"
RISK_DIR = ROOT / "data" / "risk"

START_YEAR, N_MONTHS = 2019, 72          # frontend timeline: t=0 is Jan 2019
BASE_START, BASE_END = 2001, 2020        # climatology baseline (same as signals)
CV_FIRST, CV_LAST = 2001, 2022           # agricultural years used for CV

# iso3 -> (country, declaration date, label, hold-out agricultural years beyond >=2023)
COUNTRIES = {
    "ZWE": ("Zimbabwe", "2024-04-03", "National state of disaster declared (drought)", []),
    "KEN": ("Kenya", "2021-09-08", "Drought declared a national disaster", [2020, 2021, 2022]),
    "MWI": ("Malawi", "2024-03-23", "State of disaster declared in 23 of 28 districts", []),
    "ZMB": ("Zambia", "2024-02-29", "Drought declared a national disaster and emergency", []),
}
TEST_FROM_AGYEAR = 2023                  # agyear 2023 = the 2023/24 season: never in CV

DYNAMIC = ["precip_mm", "spi_1m", "spi_3m", "spi_6m", "ndvi_crop", "ndvi_grass",
           "ndvi_z_crop", "ndvi_z_grass", "vci_crop", "vci_grass", "sm1_z", "sm2_z", "t2m_z"]
STATIC = ["crop_frac", "grass_frac"]
# Data latency (months). A risk value for month t is issued at the end of month t and may only use
# signals published by then. Month-m products become available: CHIRPS final ~3 weeks after m
# (prelim ~2 days, but we use final), MODIS MOD13Q1 16-day composites ~1-2 weeks after the period,
# ERA5-Land via ERA5T / CDS near-real-time ~5 days after m (the Earth Engine monthly collection
# lags 2-3 months; we assume the CDS route). So every source is usable with a 1-month lag:
# issue month t uses signals of month t-1. Change here to stress-test (e.g. era5: 3).
LATENCY = {"chirps": 1, "modis": 1, "era5": 1}
SOURCE = {"precip_mm": "chirps", "spi_1m": "chirps", "spi_3m": "chirps", "spi_6m": "chirps",
          "rain_pct3": "chirps", "ndvi_crop": "modis", "ndvi_grass": "modis", "ndvi_z_crop": "modis",
          "ndvi_z_grass": "modis", "vci_crop": "modis", "vci_grass": "modis",
          "sm1_z": "era5", "sm2_z": "era5", "t2m_z": "era5"}


def source_of(col: str):
    for k in sorted(SOURCE, key=len, reverse=True):
        if col == k or col.startswith(k + "_"):
            return SOURCE[k]
    return None


def apply_latency(df: pd.DataFrame) -> pd.DataFrame:
    """df indexed (unit_id, month). Shift every source-derived column by its latency, per unit."""
    out = df.copy()
    g = df.groupby(level="unit_id", group_keys=False)
    for col in df.columns:
        src = source_of(col)
        if src and LATENCY[src]:
            out[col] = g[col].shift(LATENCY[src])
    return out


EVENTS = ["cant_plant", "crop_failure", "no_grass"]
EVENT_PRIORITY = {"crop_failure": 0, "no_grass": 1, "cant_plant": 2}
LEADS = [1, 2, 3]


def agyear(ts: pd.Timestamp) -> int:
    """Agricultural year: Jul..Jun. A season whose core starts Dec 2023 -> 2023 (the 2023/24 season)."""
    return ts.year if ts.month >= 7 else ts.year - 1


def is_test(iso3: str, ag: int) -> bool:
    return ag >= TEST_FROM_AGYEAR or ag in COUNTRIES.get(iso3, (None, None, None, []))[3]


# ----------------------------------------------------------------------------- loading
def load_signals(iso3: str, data_dir: Path = DATA_DIR) -> pd.DataFrame:
    df = pd.read_parquet(Path(data_dir) / f"signals_{iso3}.parquet")
    df["month"] = pd.to_datetime(df["month"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


@dataclass
class Country:
    iso3: str
    wide: pd.DataFrame        # index (unit_id, month) complete monthly grid, columns DYNAMIC
    static: pd.DataFrame      # index unit_id, columns STATIC
    names: pd.Series          # unit_id -> unit_name


def to_country(df: pd.DataFrame, iso3: str) -> Country:
    names = df.drop_duplicates("unit_id").set_index("unit_id")["unit_name"].sort_index()
    st = df[df.signal_type.isin(STATIC)]
    # static may be stored at any month; take the first non-null per unit
    static = (st.dropna(subset=["value"]).groupby(["unit_id", "signal_type"])["value"].first()
              .unstack().reindex(index=names.index, columns=STATIC))
    dyn = df[df.signal_type.isin(DYNAMIC)]
    w = dyn.pivot_table(index=["unit_id", "month"], columns="signal_type", values="value", aggfunc="mean")
    w = w.reindex(columns=DYNAMIC)
    months = pd.date_range(dyn.month.min(), dyn.month.max(), freq="MS")
    full = pd.MultiIndex.from_product([names.index, months], names=["unit_id", "month"])
    w = w.reindex(full)
    return Country(iso3, w, static, names)


def load_country(iso3: str, data_dir: Path = DATA_DIR) -> Country:
    return to_country(load_signals(iso3, data_dir), iso3)


# ----------------------------------------------------------------------------- seasons
@dataclass
class Season:
    idx: int                  # 0 = main season, 1 = second season (bimodal)
    core_start: int           # calendar month 1..12 of the 3 wettest consecutive months
    rainy: list               # calendar months of the rainy season (ordered)
    planting: list            # first 2 rainy-season months
    crop: list                # core shifted +1 month (vegetation lags rain)
    grass: list               # 3 months after the rainy season ends


def _mm(m: int) -> int:
    return (m - 1) % 12 + 1


def detect_seasons(precip: pd.Series) -> list[Season]:
    """precip: monthly series for one unit (DatetimeIndex). Uses the baseline years only."""
    p = precip[(precip.index.year >= BASE_START) & (precip.index.year <= BASE_END)]
    if p.notna().sum() < 36:
        p = precip
    clim = p.groupby(p.index.month).mean().reindex(range(1, 13))
    if clim.isna().all():
        raise ValueError("no precipitation data for season detection")
    clim = clim.fillna(clim.mean())
    c = clim.values
    s3 = np.array([c[k] + c[(k + 1) % 12] + c[(k + 2) % 12] for k in range(12)])   # start k (0-based)
    p0 = int(np.argmax(s3))
    starts = [p0]
    dist = lambda a, b: min((a - b) % 12, (b - a) % 12)
    cand = [k for k in range(12) if dist(k, p0) >= 4]
    if cand:
        k2 = max(cand, key=lambda k: s3[k])
        # bimodal if second peak is substantial and separated by a real dry dip on both sides
        def arc(a, b):          # months strictly between window a (ends a+2) and window b start
            out, m = [], (a + 3) % 12
            while m != b:
                out.append(c[m]); m = (m + 1) % 12
            return out
        peak = min(s3[p0], s3[k2]) / 3
        a1, a2 = arc(p0, k2), arc(k2, p0)
        if s3[k2] >= 0.45 * s3[p0] and a1 and a2 and min(a1) < 0.75 * peak and min(a2) < 0.75 * peak:
            starts.append(k2)
    wet = c.mean()
    core_sets = [{(k + i) % 12 for i in range(3)} for k in starts]
    seasons = []
    for i, k in enumerate(starts):
        other = set().union(*[cs for j, cs in enumerate(core_sets) if j != i]) if len(starts) > 1 else set()
        months = [k, (k + 1) % 12, (k + 2) % 12]
        # extend backwards / forwards while the month is wetter than the annual monthly mean
        while len(months) < 6:
            b = (months[0] - 1) % 12
            if c[b] >= wet and b not in other and b not in months:
                months.insert(0, b)
            else:
                break
        while len(months) < 6:
            f = (months[-1] + 1) % 12
            if c[f] >= wet and f not in other and f not in months:
                months.append(f)
            else:
                break
        cal = [m + 1 for m in months]
        seasons.append(Season(
            idx=i, core_start=k + 1, rainy=cal, planting=cal[:2],
            crop=[_mm(k + 2 + j) for j in range(3)],
            grass=[_mm(cal[-1] + 1 + j) for j in range(3)]))
    return seasons


def season_instances(seasons: list[Season], first_year: int, last_year: int) -> pd.DataFrame:
    """One row per (season, year): absolute window start dates for every event."""
    rows = []
    for s in seasons:
        for y in range(first_year - 1, last_year + 2):
            anchor = pd.Timestamp(y, s.core_start, 1)
            # absolute start of each window, relative to the anchor (core start)
            off_plant = (s.planting[0] - s.core_start + 6) % 12 - 6       # usually -1 or 0
            off_crop = 1
            off_grass = (s.grass[0] - s.core_start) % 12
            rows.append(dict(season=s.idx, anchor=anchor, agyear=agyear(anchor),
                             cant_plant=anchor + pd.DateOffset(months=off_plant),
                             crop_failure=anchor + pd.DateOffset(months=off_crop),
                             no_grass=anchor + pd.DateOffset(months=off_grass)))
    return pd.DataFrame(rows)


WINDOW_LEN = {"cant_plant": 2, "crop_failure": 3, "no_grass": 3}


def unit_seasons(c: Country) -> dict:
    out = {}
    for u in c.names.index:
        out[u] = detect_seasons(c.wide.loc[u, "precip_mm"])
    return out


def months_between(a: pd.Timestamp, b: pd.Timestamp) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)
