"""4. Alert rules (alert engine v1.1 "spec mode": levels = family rule + hysteresis, p not used).
Safety assertions: no Warning without vegetation; heat alone never escalates; rain+soil never Warning;
hysteresis exactly 2 runs up / 3 runs down (no fast entry in production); Emergency only with a
declaration in force (declaration season only)."""
import itertools
import inspect

import numpy as np
import pandas as pd
import pytest

import alert_engine as A

NEUTRAL = dict(spi_1m=0.0, spi_3m=0.0, ndvi_z_crop=0.0, ndvi_z_grass=0.0, vci_crop=60.0, vci_grass=60.0,
               vci_crop_l1=60.0, vci_grass_l1=60.0, sm1_z=0.0, t2m_z=0.0)
DRY = dict(rain=dict(spi_1m=-2.5, spi_3m=-0.5),          # rain via spi_1m only, not "strong weather"
           vegetation=dict(ndvi_z_crop=-2.5, ndvi_z_grass=-2.5, vci_crop=10.0, vci_grass=10.0,
                           vci_crop_l1=10.0, vci_grass_l1=10.0),
           soil=dict(sm1_z=-2.5), heat=dict(t2m_z=3.0))
ALL = ["rain", "vegetation", "soil", "heat"]
COMBOS = [c for k in range(5) for c in itertools.combinations(ALL, k)]


def sig(active, **over):
    d = dict(NEUTRAL)
    for f in active:
        d.update(DRY[f])
    d.update(over)
    return pd.DataFrame([d])


def fam_of(s, in_season=True, in_rainy=True, crop_dom=True):
    return A.families(s, [in_season], [in_rainy], [crop_dom])


def level(active, decl=False, **kw):
    fam = fam_of(sig(active), **kw)
    return int(A.raw_levels(fam, [decl])[0]), fam.iloc[0]


def hyst(raw, **kw):
    out = A.hysteresis(raw, **kw)
    return out[0] if isinstance(out, tuple) else out


H = lambda raw: [int(x) for x in hyst(raw)]


# ---------------------------------------------------------------- family rule
@pytest.mark.parametrize("active", COMBOS, ids=lambda c: "+".join(c) or "none")
@pytest.mark.parametrize("decl", [False, True])
def test_level_rule_all_family_mixes(active, decl):
    lv, fam = level(active, decl)
    for f in ALL:
        assert bool(fam[f]) == (f in active), f
    core = [f for f in active if f != "heat"]
    warn = "vegetation" in active and ("rain" in active or "soil" in active)
    expected = (3 if decl else 2) if warn else (1 if core else 0)
    assert lv == expected
    if lv >= 2:
        assert "vegetation" in active


@pytest.mark.parametrize("decl", [False, True])
def test_rain_plus_soil_never_warning(decl):
    assert level(["rain", "soil"], decl)[0] == 1
    assert level(["rain", "soil", "heat"], decl)[0] == 1
    s = sig(["rain", "soil"], spi_3m=-3.0, sm1_z=-3.0)          # strong weather-only: still Watch
    assert int(A.raw_levels(fam_of(s), [decl])[0]) == 1


def test_heat_alone_never_escalates():
    for decl in (False, True):
        lv, fam = level(["heat"], decl)
        assert lv == 0 and fam["agreeing"] == 0
    for one in ("rain", "vegetation", "soil"):
        assert level([one, "heat"])[0] == level([one])[0] == 1
        assert level([one, "heat"])[1]["agreeing"] == 1


def test_emergency_needs_declaration():
    assert level(["vegetation", "rain", "soil", "heat"], decl=False)[0] == 2
    assert level(["vegetation", "rain"], decl=True)[0] == 3
    assert level(["rain"], decl=True)[0] == 1
    assert level([], decl=True)[0] == 0


def test_missing_signal_never_raises_family():
    s = pd.DataFrame([{k: np.nan for k in NEUTRAL}])
    fam = fam_of(s)
    assert not fam[ALL].any(axis=None) and not bool(fam["strong_weather"].iloc[0])
    assert int(A.raw_levels(fam, [True])[0]) == 0


def test_vegetation_out_of_season_off():
    assert not bool(level(["vegetation"], in_season=False)[1]["vegetation"])


def test_rain_and_soil_gated_to_rainy_season():
    lv, fam = level(["rain", "soil", "vegetation"], in_rainy=False)
    assert not fam["rain"] and not fam["soil"] and lv == 1


def test_vegetation_vci_needs_two_consecutive_months():
    s = sig([], vci_crop=10.0, vci_grass=10.0)                 # current low, previous month normal
    assert not bool(fam_of(s).iloc[0]["vegetation"])
    s = sig([], vci_crop=10.0, vci_grass=10.0, vci_crop_l1=10.0, vci_grass_l1=10.0)
    assert bool(fam_of(s).iloc[0]["vegetation"])


def test_p_not_used_for_levels():
    assert "p" not in inspect.signature(A.raw_levels).parameters


# ---------------------------------------------------------------- hysteresis
def test_single_spike_ignored():
    assert H([0, 2, 0, 0, 0]) == [0] * 5
    assert H([0, 3, 0, 3, 0]) == [0] * 5


def test_up_after_exactly_two_runs():
    assert H([1, 1]) == [0, 1]
    assert H([0, 2, 2, 2]) == [0, 0, 2, 2]
    assert H([0, 1, 3, 3]) == [0, 0, 1, 3]                    # to the level held for the last 2 runs


def test_down_after_exactly_three_runs():
    assert H([2, 2, 0, 0, 0, 0]) == [0, 2, 2, 2, 0, 0]
    assert H([3, 3, 0, 0, 1]) == [0, 3, 3, 3, 1]              # to the highest of the 3 runs below
    assert H([2, 2, 0, 0, 2, 0, 0, 0]) == [0, 2, 2, 2, 2, 2, 2, 0]   # interrupted fall resets


def test_two_down_runs_not_enough():
    assert H([2, 2, 0, 0, 2, 2]) == [0, 2, 2, 2, 2, 2]


@pytest.mark.parametrize("seed", range(30))
def test_hysteresis_invariants_random(seed):
    rng = np.random.default_rng(seed)
    raw = rng.integers(0, 4, 60)
    out, held = A.hysteresis(raw)
    for i in range(len(raw)):
        prev = out[i - 1] if i else 0
        if out[i] > prev:
            assert i >= 1 and raw[i] > prev and raw[i - 1] > prev and out[i] <= min(raw[i], raw[i - 1])
        if out[i] < prev:
            assert i >= 2 and all(raw[j] < prev for j in (i, i - 1, i - 2))
        assert bool(held[i]) == (raw[i] < out[i])
    assert out.min() >= 0 and out.max() <= 3


def test_production_path_never_enters_on_a_single_run():
    """Spec: 2 runs up, strict. Default hysteresis and export_risk must not use fast entry."""
    import export_risk as X
    assert getattr(X, "FAST_ENTRY", False) is False, "export_risk.FAST_ENTRY is on: 1-run escalation"
    assert H([0, 3, 0, 0, 0]) == [0] * 5
    src = inspect.getsource(X.build)
    assert "fast" not in src.split("ae.hysteresis(")[1].split(")")[0], "export passes fast to hysteresis"
