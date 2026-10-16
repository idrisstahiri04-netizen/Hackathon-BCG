"""1. No future leakage: features at reference month r = W0 - lead use only months <= r."""
import numpy as np
import pandas as pd
import pytest

from common import to_country, unit_seasons
import features as F
import labels as L
from conftest import make_long

DYN = ["precip_mm", "spi_1m", "spi_3m", "spi_6m", "ndvi_crop", "ndvi_grass", "ndvi_z_crop",
       "ndvi_z_grass", "vci_crop", "vci_grass", "sm1_z", "sm2_z", "t2m_z"]


def perturb_after(df, r, seed=99):
    d = df.copy()
    rng = np.random.default_rng(seed)
    m = (d.month > r) & d.signal_type.isin(DYN)
    d.loc[m, "value"] = d.loc[m, "value"] * 7.3 + rng.normal(50, 20, m.sum())
    return d


def feats(df):
    return F.unit_month_features(to_country(df, "ZWE"))


@pytest.mark.parametrize("r", ["2023-09-01", "2023-11-01", "2024-01-01", "2021-03-01"])
def test_unit_month_features_ignore_future(long_df, r):
    r = pd.Timestamp(r)
    a, b = feats(long_df), feats(perturb_after(long_df, r))
    sel = a.index.get_level_values("month") <= r
    pd.testing.assert_frame_equal(a[sel], b[sel], check_exact=False, rtol=1e-12)


def test_baseline_period_features_ignore_future_except_fixed_climatology(long_df):
    """In-baseline r: everything except rain_pct3 (whose 2001-2020 normal is a fixed climatology)."""
    r = pd.Timestamp("2010-06-01")
    a, b = feats(long_df), feats(perturb_after(long_df, r))
    sel = a.index.get_level_values("month") <= r
    cols = [c for c in a.columns if c != "rain_pct3"]
    pd.testing.assert_frame_equal(a.loc[sel, cols], b.loc[sel, cols], check_exact=False, rtol=1e-12)


def test_make_xy_rows_use_r_strictly_before_window(long_df):
    c = to_country(long_df, "ZWE")
    ss = unit_seasons(c)
    t = L.build_targets(c, ss)
    xy = F.make_xy(F.unit_month_features(c), t, [1, 2, 3], {u: s[0].planting[0] for u, s in ss.items()},
                   {u: len(s) > 1 for u, s in ss.items()})
    xy = xy.loc[:, ~xy.columns.duplicated()]   # make_xy returns "lead" twice (t and X)
    assert (xy["r"] < xy["W0"]).all()
    lead_m = (xy.W0.dt.year - xy.r.dt.year) * 12 + (xy.W0.dt.month - xy.r.dt.month)
    assert (lead_m == xy["lead"]).all() and (xy["lead"] >= 1).all()


def test_make_xy_end_to_end_perturb_from_window_start_minus_lead(long_df):
    """For the 2023/24 targets, perturb every month after r=W0-lead; that row's X must not change."""
    c0 = to_country(long_df, "ZWE")
    ss = unit_seasons(c0)
    t = L.build_targets(c0, ss)
    t = t[t.agyear == 2023]
    assert len(t)
    ps = {u: s[0].planting[0] for u, s in ss.items()}
    bm = {u: len(s) > 1 for u, s in ss.items()}
    base = F.make_xy(F.unit_month_features(c0), t, [1, 2, 3], ps, bm)
    fcols = [x for x in F.feature_columns(F.unit_month_features(c0))]
    for r in sorted(base.r.unique()):
        c1 = to_country(perturb_after(long_df, r), "ZWE")
        pert = F.make_xy(F.unit_month_features(c1), t, [1, 2, 3], ps, bm)
        m = base.r == r
        pd.testing.assert_frame_equal(base.loc[m, fcols], pert.loc[m, fcols], check_exact=False, rtol=1e-12)
