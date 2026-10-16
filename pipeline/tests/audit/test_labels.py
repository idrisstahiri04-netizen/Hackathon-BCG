"""2. Labels depend only on vci_* signals (season windows held fixed)."""
import numpy as np
import pandas as pd

from common import to_country, unit_seasons
import labels as L

NON_VCI = ["precip_mm", "spi_1m", "spi_3m", "spi_6m", "ndvi_crop", "ndvi_grass", "ndvi_z_crop",
           "ndvi_z_grass", "sm1_z", "sm2_z", "t2m_z", "crop_frac", "grass_frac"]


def _targets(df, ss):
    return L.build_targets(to_country(df, "ZWE"), ss)


def _scramble(df, types, seed=5):
    d = df.copy()
    rng = np.random.default_rng(seed)
    m = d.signal_type.isin(types)
    d.loc[m, "value"] = rng.normal(-3, 2, m.sum())     # strongly dry values
    return d


def test_labels_invariant_to_non_vci_signals(long_df):
    ss = unit_seasons(to_country(long_df, "ZWE"))       # windows fixed from the original rain climatology
    a = _targets(long_df, ss)
    b = _targets(_scramble(long_df, NON_VCI), ss)
    bad = a.label.fillna(-1) != b.label.fillna(-1)
    assert not bad.any(), f"labels changed for events {sorted(a.loc[bad, 'event'].unique())}"


def test_labels_respond_to_vci(long_df):
    ss = unit_seasons(to_country(long_df, "ZWE"))
    d = long_df.copy()
    d.loc[d.signal_type.isin(["vci_crop", "vci_grass"]), "value"] = 90.0
    hi = _targets(d, ss)
    d.loc[d.signal_type.isin(["vci_crop", "vci_grass"]), "value"] = 5.0
    lo = _targets(d, ss)
    for e in ("crop_failure", "no_grass"):
        assert (hi[hi.event == e].label == 0).all() and (lo[lo.event == e].label == 1).all()


def test_missing_vci_gives_nan_not_zero(long_df):
    ss = unit_seasons(to_country(long_df, "ZWE"))
    d = long_df.copy()
    d.loc[d.signal_type.isin(["vci_crop", "vci_grass"]), "value"] = np.nan
    t = _targets(d, ss)
    assert t[t.event.isin(["crop_failure", "no_grass"])].label.isna().all()
