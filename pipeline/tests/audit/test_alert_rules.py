"""4. Alert rules: vegetation required for Warning, rain+soil alone never Warning, heat never
escalates on its own, hysteresis exactly 2 runs up / 3 runs down."""
import itertools

import numpy as np
import pandas as pd
import pytest

import inspect

import alert_engine as A


def raw_levels(fam, p, s, after_decl, th):
    """Adapter: raw_levels lost its after_decl argument in a later revision."""
    if "after_decl" in inspect.signature(A.raw_levels).parameters:
        return A.raw_levels(fam, p, s, after_decl, th)
    return A.raw_levels(fam, p, s, th)


def hyst(raw, **kw):
    out = A.hysteresis(raw, **kw)
    return out[0] if isinstance(out, tuple) else out

TH = dict(A.DEFAULT_THRESHOLDS)
NEUTRAL = dict(spi_1m=0.0, spi_3m=0.0, ndvi_z_crop=0.0, ndvi_z_grass=0.0, vci_crop=60.0,
               vci_grass=60.0, sm1_z=0.0, t2m_z=0.0)
DRY = dict(rain=dict(spi_1m=-2.5, spi_3m=-2.5), vegetation=dict(ndvi_z_crop=-2.5, ndvi_z_grass=-2.5,
           vci_crop=10.0, vci_grass=10.0), soil=dict(sm1_z=-2.5), heat=dict(t2m_z=3.0))


def sig(active, n=1):
    d = dict(NEUTRAL)
    for f in active:
        d.update(DRY[f])
    return pd.DataFrame([d] * n)


def level(active, p, in_season=True, after_decl=True):
    s = sig(active)
    fam = A.families(s, [in_season])
    return int(raw_levels(fam, [p], s, [after_decl], TH)[0]), fam.iloc[0]


ALL = ["rain", "vegetation", "soil", "heat"]
COMBOS = [c for k in range(5) for c in itertools.combinations(ALL, k)]


@pytest.mark.parametrize("active", COMBOS, ids=lambda c: "+".join(c) or "none")
@pytest.mark.parametrize("p", [0.0, 0.6, 1.0])
def test_warning_requires_vegetation_and_weather(active, p):
    lv, fam = level(active, p)
    assert bool(fam["rain"]) == ("rain" in active) and bool(fam["soil"]) == ("soil" in active)
    assert bool(fam["vegetation"]) == ("vegetation" in active) and bool(fam["heat"]) == ("heat" in active)
    if lv >= 2:
        assert "vegetation" in active and ("rain" in active or "soil" in active)


@pytest.mark.parametrize("p", [0.0, 0.6, 0.99])
def test_rain_plus_soil_never_warning(p):
    assert level(["rain", "soil"], p)[0] <= 1
    assert level(["rain", "soil", "heat"], p)[0] <= 1


def test_heat_alone_never_escalates():
    lv, fam = level(["heat"], 0.0)
    assert lv == 0 and fam["agreeing"] == 0
    for p in (0.6, 1.0):
        assert level(["heat"], p)[0] <= 1                 # p may give Watch, heat never more
        assert level(["heat"], p)[0] == level([], p)[0]   # heat adds nothing to the level


def test_heat_does_not_count_toward_two_family_rule():
    for one in ("rain", "vegetation", "soil"):
        assert level([one, "heat"], 1.0)[0] <= 1
        assert level([one, "heat"], 1.0)[1]["agreeing"] == 1


def test_vegetation_plus_rain_can_warn():
    assert level(["vegetation", "rain"], 0.9)[0] >= 2
    assert level(["vegetation", "soil"], 0.9)[0] >= 2


def test_missing_signal_never_raises_family():
    s = pd.DataFrame([{k: np.nan for k in NEUTRAL}])
    fam = A.families(s, [True])
    assert not fam[["rain", "vegetation", "soil", "heat"]].any(axis=None)
    assert int(raw_levels(fam, [0.0], s, [True], TH)[0]) == 0


def test_vegetation_out_of_season_off():
    assert not bool(level(["vegetation"], 0.0, in_season=False)[1]["vegetation"])


# ---------------------------------------------------------------- hysteresis
H = lambda raw: list(hyst(raw))


def test_single_spike_ignored():
    assert H([0, 2, 0, 0, 0]) == [0, 0, 0, 0, 0]
    assert H([0, 3, 0, 3, 0]) == [0] * 5


def test_up_after_exactly_two_runs():
    assert H([1, 1]) == [0, 1]
    assert H([0, 1, 1, 1, 1]) == [0, 0, 1, 1, 1]
    h = H([0, 2, 2, 2])
    assert h[1] == 0 and h[2] >= 1


def test_down_after_exactly_three_runs():
    assert H([1, 1, 0, 0, 0, 0]) == [0, 1, 1, 1, 0, 0]
    assert H([1, 1, 0, 0, 1, 0, 0, 0]) == [0, 1, 1, 1, 1, 1, 1, 0]   # interrupted fall resets


def test_two_down_runs_not_enough():
    assert H([1, 1, 0, 0, 1, 1]) == [0, 1, 1, 1, 1, 1]
    assert min(H([2, 2, 2, 0, 0, 2, 2])[2:]) == H([2, 2, 2, 0, 0, 2, 2])[2]


@pytest.mark.parametrize("seed", range(30))
def test_hysteresis_invariants_random(seed):
    rng = np.random.default_rng(seed)
    raw = rng.integers(0, 4, 60)
    out = hyst(raw)
    for i in range(len(raw)):
        prev = out[i - 1] if i else 0
        if out[i] > prev:   # rise: this and previous raw both above old level
            assert i >= 1 and raw[i] > prev and raw[i - 1] > prev and out[i] <= min(raw[i], raw[i - 1])
        if out[i] < prev:   # fall: last 3 raw all below old level
            assert i >= 2 and all(raw[j] < prev for j in (i, i - 1, i - 2))
    assert out.min() >= 0 and out.max() <= 3


def test_production_path_never_enters_on_a_single_run():
    """Spec: 2 runs up, strict. export_risk must not enable fast entry (FAST_ENTRY flag)."""
    import export_risk as X
    assert getattr(X, "FAST_ENTRY", False) is False, "export_risk.FAST_ENTRY is on: 1-run escalation"
    assert list(hyst([0, 3, 0, 0, 0])) == [0, 0, 0, 0, 0]
