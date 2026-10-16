#!/usr/bin/env python3
"""Independent audit of pipeline/data/signals_ZWE.parquet (CONTRACT.md section 1).

Written separately from pipeline/extract_signals.py: it recomputes a small
sample in Earth Engine with its own code path (per-unit reduceRegion, native
MODIS 250 m scale) and checks the parquet against it, plus structural checks.

Usage:
    python pipeline/audit/verify_signals.py            # EE sample + parquet checks
    python pipeline/audit/verify_signals.py --no-ee    # reuse cached EE sample

Writes pipeline/audit/ee_sample.json (cache) and pipeline/audit/data_check.md.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PARQUET = HERE.parent / "data" / "signals_ZWE.parquet"
CACHE = HERE / "ee_sample.json"
REPORT = HERE / "data_check.md"

EE_PROJECT = "drought-warning-zw-1016"
UNITS = ["Mbire", "Binga", "Hwange", "Beitbridge", "Mwenezi"]
# (year, month, expected anomaly sign, label)
MONTHS = [
    (2023, 11, None, "2023-11 (El Nino onset; sign not asserted)"),
    (2024, 1, -1, "2024-01 El Nino drought"),
    (2024, 2, -1, "2024-02 El Nino drought (driest Feb on record)"),
    (2015, 1, -1, "2015-01 drought"),
    (2016, 1, -1, "2016-01 2015/16 El Nino drought peak"),
    (2017, 1, +1, "2017-01 wet season"),
]
TOL = 0.05
N_UNITS = 91
MONTHLY_TYPES = ["precip_mm", "spi_1m", "spi_3m", "spi_6m", "ndvi_crop", "ndvi_grass",
                 "ndvi_z_crop", "ndvi_z_grass", "vci_crop", "vci_grass",
                 "sm1_z", "sm2_z", "t2m_z"]
STATIC_TYPES = ["crop_frac", "grass_frac"]


# ----------------------------------------------------------------- Earth Engine
def ee_sample() -> dict:
    import ee
    ee.Initialize(project=EE_PROJECT)
    fc = (ee.FeatureCollection("WM/geoLab/geoBoundaries/600/ADM2")
          .filter(ee.Filter.eq("shapeGroup", "ZWE"))
          .filter(ee.Filter.inList("shapeName", UNITS)))
    wc = ee.Image(ee.ImageCollection("ESA/WorldCover/v200").first()).select("Map")
    crop_m = wc.eq(40)
    grass_m = wc.eq(20).Or(wc.eq(30))

    chirps = ee.ImageCollection("UCSB-CHC/CHIRPS/V3/PENTAD").select("precipitation")
    modis = ee.ImageCollection("MODIS/061/MOD13Q1")
    era5 = ee.ImageCollection("ECMWF/ERA5_LAND/MONTHLY_AGGR").select(
        "volumetric_soil_water_layer_1")
    base = ee.Filter.date("2001-01-01", "2021-01-01")

    def ndvi_qa(img):
        # SummaryQA 0 = good, 1 = marginal; drop snow/cloud (2,3) and fill (-1)
        q = img.select("SummaryQA")
        return img.select("NDVI").updateMask(q.gte(0).And(q.lte(1))).multiply(0.0001)

    def month_img(y, m):
        s = ee.Date.fromYMD(y, m, 1)
        e = s.advance(1, "month")
        p = chirps.filterDate(s, e).sum().rename("precip")
        n = modis.filterDate(s, e).map(ndvi_qa).mean()
        sm = era5.filterDate(s, e).mean().rename("sm1")
        return p, n, sm

    def clim_img(m):
        cal = ee.Filter.calendarRange(m, m, "month")
        # mean monthly precip total = sum over 20 Januaries / 20
        p = chirps.filter(base).filter(cal).sum().divide(20).rename("precip")
        n = modis.filter(base).filter(cal).map(ndvi_qa).mean()
        sm = era5.filter(base).filter(cal).mean().rename("sm1")
        return p, n, sm

    def reduce(p, n, sm):
        img_p = p
        img_n = ee.Image.cat([n.updateMask(crop_m).rename("ndvi_crop"),
                              n.updateMask(grass_m).rename("ndvi_grass")])
        def per_feat(f):
            g = f.geometry()
            rp = img_p.reduceRegion(ee.Reducer.mean(), g, 5000, maxPixels=1e10, tileScale=4)
            rn = img_n.reduceRegion(ee.Reducer.mean(), g, 250, maxPixels=1e10, tileScale=8)
            rs = sm.reduceRegion(ee.Reducer.mean(), g, 11000, maxPixels=1e10, tileScale=4)
            return ee.Feature(None, rp.combine(rn).combine(rs)).set(
                "unit_id", f.get("shapeID"), "unit_name", f.get("shapeName"))
        out = ee.FeatureCollection(fc.map(per_feat)).getInfo()["features"]
        return [o["properties"] for o in out]

    res = {"computed_at": datetime.now(timezone.utc).isoformat(), "obs": {}, "clim": {}}
    for y, m, _, _ in MONTHS:
        key = f"{y}-{m:02d}"
        print("EE month", key, flush=True)
        res["obs"][key] = reduce(*month_img(y, m))
    for m in sorted({m for _, m, _, _ in MONTHS}):
        print("EE climatology month", m, flush=True)
        res["clim"][str(m)] = reduce(*clim_img(m))
    if CACHE.exists():  # keep precip-zero cache
        res["precip_zeros"] = json.loads(CACHE.read_text()).get("precip_zeros", {})
    CACHE.write_text(json.dumps(res, indent=1))
    return res


def verify_precip_zeros(zr: pd.DataFrame) -> dict:
    """Recompute every parquet precip_mm == 0 in EE: (unit mean, pentad count)."""
    if not len(zr):
        return {}
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    zc = cache.setdefault("precip_zeros", {})
    todo = [(r.unit_id, r.month) for _, r in zr.iterrows() if f"{r.unit_id}|{r.month}" not in zc]
    if todo:
        import ee
        ee.Initialize(project=EE_PROJECT)
        fc = ee.FeatureCollection("WM/geoLab/geoBoundaries/600/ADM2").filter(
            ee.Filter.eq("shapeGroup", "ZWE"))
        ch = ee.ImageCollection("UCSB-CHC/CHIRPS/V3/PENTAD").select("precipitation")
        for uid, mth in todo:
            s = ee.Date(mth)
            c = ch.filterDate(s, s.advance(1, "month"))
            g = fc.filter(ee.Filter.eq("shapeID", uid)).first().geometry()
            mean = c.sum().reduceRegion(ee.Reducer.mean(), g, 5566).get("precipitation").getInfo()
            zc[f"{uid}|{mth}"] = [mean, c.size().getInfo()]
        CACHE.write_text(json.dumps(cache, indent=1))
    return {f"{u}|{m}": zc[f"{u}|{m}"] for u, m in ((r.unit_id, r.month) for _, r in zr.iterrows())}


# ---------------------------------------------------------------------- checks
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-ee", action="store_true")
    args = ap.parse_args()
    ee_res = json.loads(CACHE.read_text()) if args.no_ee and CACHE.exists() else ee_sample()

    rows = []  # (check, status, detail)

    def add(check, ok, detail=""):
        if isinstance(ok, (bool, np.bool_)):
            status = "PASS" if bool(ok) else "FAIL"
        else:
            status = str(ok)
        rows.append((check, status, detail))

    # --- EE sample tables
    obs = []
    for key, recs in ee_res["obs"].items():
        for r in recs:
            obs.append({"month": key + "-01", **r})
    obs = pd.DataFrame(obs)
    clim = []
    for m, recs in ee_res["clim"].items():
        for r in recs:
            clim.append({"cal_month": int(m), **r})
    clim = pd.DataFrame(clim)
    obs["cal_month"] = pd.to_datetime(obs["month"]).dt.month
    ee_df = obs.merge(clim, on=["unit_id", "unit_name", "cal_month"], suffixes=("", "_clim"))
    for v in ["precip", "ndvi_crop", "ndvi_grass", "sm1"]:
        ee_df[v + "_anom"] = ee_df[v] - ee_df[v + "_clim"]

    # --- 2. anomaly signs
    sign_lines = []
    for y, m, exp, label in MONTHS:
        key = f"{y}-{m:02d}-01"
        sub = ee_df[ee_df.month == key]
        for v in ["precip", "ndvi_crop", "ndvi_grass", "sm1"]:
            a = sub[v + "_anom"].dropna()
            n_neg, n_pos = int((a < 0).sum()), int((a > 0).sum())
            med = float(a.median()) if len(a) else np.nan
            if exp is None:
                ok = "INFO"
            else:
                agree = n_neg if exp < 0 else n_pos
                ok = agree >= 3  # majority of 5 units
                if not ok and v.startswith("ndvi"):
                    # NDVI lags rain by 1-2 months; an early-season green-up is
                    # physically possible, so flag rather than fail
                    ok = "WARN"
            add(f"anom sign {label}: {v}", ok,
                f"{n_neg} units below / {n_pos} above 2001-20 mean; median anom {med:+.4g}")
        sign_lines.append(sub)

    # --- 3. parquet
    if not PARQUET.exists():
        add("parquet exists", False, str(PARQUET))
        write_report(rows, ee_df, None)
        return
    d = pd.read_parquet(PARQUET)
    d["month"] = pd.to_datetime(d["month"]).dt.strftime("%Y-%m-01")
    add("columns per contract",
        set(["unit_id", "unit_name", "iso3", "month", "signal_type", "value"]) <= set(d.columns),
        ", ".join(d.columns))

    # compare values
    piv = d[d.signal_type.isin(["precip_mm", "ndvi_crop", "ndvi_grass", "spi_1m", "sm1_z"])].pivot_table(
        index=["unit_id", "month"], columns="signal_type", values="value", aggfunc="first").add_prefix("pq_").reset_index()
    piv = piv.rename(columns={"pq_unit_id": "unit_id", "pq_month": "month"})
    cmp = ee_df.merge(piv, on=["unit_id", "month"], how="left")
    for ee_col, pq_col in [("precip", "pq_precip_mm"), ("ndvi_crop", "pq_ndvi_crop"),
                           ("ndvi_grass", "pq_ndvi_grass")]:
        rel = (cmp[pq_col] - cmp[ee_col]).abs() / cmp[ee_col].abs()
        bad = cmp[(rel > TOL) | cmp[pq_col].isna() | cmp[ee_col].isna()]
        det = f"max rel diff {rel.max():.2%}, median {rel.median():.2%} over {rel.notna().sum()} unit-months"
        if len(bad):
            det += "; out of tolerance: " + "; ".join(
                f"{r.unit_name} {r.month[:7]} EE={r[ee_col]:.4g} PQ={r[pq_col]:.4g}" for _, r in bad.iterrows())
        add(f"value match {pq_col} vs independent EE (tol 5%)", len(bad) == 0, det)
    for ee_col, pq_col in [("precip_anom", "pq_spi_1m"), ("sm1_anom", "pq_sm1_z")]:
        c = cmp.dropna(subset=[ee_col, pq_col])
        c = c[(c[ee_col].abs() > 1e-9)]
        agree = (np.sign(c[ee_col]) == np.sign(c[pq_col]))
        # allow sign disagreement only when SPI near 0 (median vs mean)
        hard = c[~agree & (c[pq_col].abs() > 0.5)]
        det = f"{int(agree.sum())}/{len(c)} same sign"
        if (~agree).any():
            det += "; disagree: " + "; ".join(
                f"{r.unit_name} {r.month[:7]} anom={r[ee_col]:+.3g} {pq_col}={r[pq_col]:+.2f}"
                for _, r in c[~agree].iterrows())
        add(f"sign {pq_col} vs EE anomaly", len(hard) == 0, det)

    # VCI range
    for t in ["vci_crop", "vci_grass"]:
        v = d.loc[d.signal_type == t, "value"].dropna()
        add(f"{t} within 0-100", bool(len(v)) and v.between(0, 100).all(),
            f"n={len(v)} min={v.min():.3g} max={v.max():.3g}, out of range={int((~v.between(0,100)).sum())}")

    for t in ["spi_1m", "spi_3m", "spi_6m"]:
        v = d.loc[d.signal_type == t, "value"].dropna()
        add(f"{t} range", v.between(-3, 3).all() and "INFO",
            f"min {v.min():.2f} max {v.max():.2f}; clipped at -3: {int((v <= -3).sum())}, at +3: {int((v >= 3).sum())} "
            "(extractor clips to [-3,3]; extreme events like Feb 2024 saturate)")

    # duplicates
    dup = d.duplicated(["unit_id", "month", "signal_type"]).sum()
    add("no duplicate (unit_id, month, signal_type)", dup == 0, f"{dup} duplicates")

    # units
    nu = d.unit_id.nunique()
    add("91 units", nu == N_UNITS, f"{nu} unit_ids, {d.unit_name.nunique()} names")
    add("iso3 = ZWE only", set(d.iso3.unique()) == {"ZWE"}, str(sorted(d.iso3.unique())))

    # signal vocabulary
    types = set(d.signal_type.unique())
    missing_t = set(MONTHLY_TYPES + STATIC_TYPES) - types
    extra_t = types - set(MONTHLY_TYPES + STATIC_TYPES)
    add("all contract signal types present", not missing_t,
        f"missing={sorted(missing_t)} extra={sorted(extra_t)}")

    # coverage 2001-01..2024-12
    months = pd.date_range("2001-01-01", "2024-12-01", freq="MS").strftime("%Y-%m-01")
    units = d.unit_id.unique()
    for t in MONTHLY_TYPES:
        s = d[d.signal_type == t]
        have = s.dropna(subset=["value"])
        exp_n = len(units) * len(months)
        rows_n = len(s)
        nonnull = len(have)
        out_rng = (~s.month.isin(months)).sum()
        miss_months = sorted(set(months) - set(have.month))
        det = (f"rows {rows_n}/{exp_n}, non-null {nonnull} ({nonnull/exp_n:.1%}); "
               f"months outside range {out_rng}; first {have.month.min()} last {have.month.max()}")
        if miss_months:
            det += f"; months with no value in any unit: {len(miss_months)} " + (
                ", ".join(m[:7] for m in miss_months[:12]) + (" ..." if len(miss_months) > 12 else ""))
        # per-unit gaps
        per_unit = have.groupby("unit_id").size()
        short = per_unit[per_unit < len(months)]
        allnan = sorted(set(s.unit_name) - set(have.unit_name))
        part = s[s.unit_id.isin(short.index)].drop_duplicates("unit_id").unit_name.tolist()
        if len(short) or allnan:
            det += (f"; units all-NaN: {allnan}; units with partial gaps: "
                    f"{[n for n in part if n not in allnan]}")
        ok = rows_n >= exp_n * 0.999 and not miss_months
        if t.startswith("spi_3") or t.startswith("spi_6"):
            # first 2/5 months can legitimately be NaN
            ok = rows_n >= exp_n * 0.98
        add(f"coverage {t}", ok, det)
    for t in STATIC_TYPES:
        s = d[d.signal_type == t]
        add(f"static {t}: one row per unit at 2001-01-01, in [0,1]",
            len(s) == len(units) and (s.month == "2001-01-01").all() and s.value.between(0, 1).all(),
            f"rows {len(s)}, months {sorted(s.month.unique())[:3]}, range {s.value.min():.3g}-{s.value.max():.3g}")

    # zero-for-missing
    zero_det = []
    zero_bad = False
    for t in MONTHLY_TYPES:
        s = d[d.signal_type == t]
        z = (s.value == 0).sum()
        if not z:
            continue
        if t == "precip_mm":
            zr = s[s.value == 0]
            ver = verify_precip_zeros(zr)
            notreal = [k for k, (mean, npent) in ver.items() if npent < 6 or (mean or 0) > 0.05]
            zero_det.append(f"precip_mm zeros={z}, re-checked in EE: {z - len(notreal)} are real 0 mm "
                            f"(all pentads present, CHIRPS sum 0 over unit)"
                            + (f"; NOT real: {notreal}" if notreal else "")
                            + " [" + ", ".join(f"{r.unit_name} {r.month[:7]}" for _, r in zr.iterrows()) + "]")
            if notreal:
                zero_bad = True
        elif t.startswith("vci"):
            b = s[(s.value == 0) & (s.month < "2021-01-01")].copy()
            b["cm"] = b.month.str[5:7]
            per = b.groupby(["unit_id", "cm"]).size()
            zero_det.append(f"{t} zeros={z} (expected: VCI=0 at the baseline-minimum year; "
                            f"max {per.max() if len(per) else 0} zero per unit x calendar month in 2001-20, "
                            f"{int((s[s.month >= '2021-01-01'].value == 0).sum())} after 2020 = clipped below baseline min)")
            if len(per) and per.max() > 1:
                zero_bad = True
        else:
            zero_det.append(f"{t} zeros={z}")
            if t.startswith(("ndvi_crop", "ndvi_grass")) or z > 5:
                zero_bad = True
    # NDVI at 0 in units with crop_frac > 0 would be suspicious; NaN counts reported
    nan_det = []
    for t in MONTHLY_TYPES:
        s = d[d.signal_type == t]
        n = s.value.isna().sum()
        if n:
            nan_det.append(f"{t} NaN={n}")
    add("no zero-for-missing", not zero_bad,
        ("; ".join(zero_det) or "no exact zeros") + " | NaN kept: " + ("; ".join(nan_det) or "none"))

    # physical ranges
    for t, lo, hi in [("precip_mm", 0, 1500), ("ndvi_crop", -0.2, 1), ("ndvi_grass", -0.2, 1)]:
        v = d.loc[d.signal_type == t, "value"].dropna()
        add(f"{t} physical range [{lo},{hi}]", v.between(lo, hi).all(),
            f"min {v.min():.4g} max {v.max():.4g}")

    # internal consistency: SPI-1 sign vs precip anomaly vs per-unit 2001-20 calendar-month median
    p = d[d.signal_type == "precip_mm"][["unit_id", "month", "value"]].rename(columns={"value": "p"})
    s1 = d[d.signal_type == "spi_1m"][["unit_id", "month", "value"]].rename(columns={"value": "spi"})
    j = p.merge(s1, on=["unit_id", "month"]).dropna()
    j["cm"] = pd.to_datetime(j.month).dt.month
    j["y"] = pd.to_datetime(j.month).dt.year
    med = j[(j.y >= 2001) & (j.y <= 2020)].groupby(["unit_id", "cm"]).p.median().rename("pmed")
    j = j.join(med, on=["unit_id", "cm"])
    wet = j[j.cm.isin([11, 12, 1, 2, 3]) & ((j.p - j.pmed).abs() > 0.1 * j.pmed)]
    agree = (np.sign(wet.p - wet.pmed) == np.sign(wet.spi)).mean()
    rho = j.groupby(["unit_id", "cm"]).apply(
        lambda g: g.p.rank().corr(g.spi.rank()) if len(g) > 5 else np.nan, include_groups=False).median()
    add("spi_1m sign vs precip anomaly (all units, wet season, |anom|>10% of median)",
        agree > 0.97, f"agreement {agree:.1%} over {len(wet)} unit-months; median rank corr per unit/cal-month {rho:.3f}")

    # national-mean sanity: Feb 2024 SPI, Jan 2016 SPI, Jan 2017 SPI
    for mth, exp in [("2024-02-01", -1), ("2016-01-01", -1), ("2017-01-01", 1)]:
        v = d[(d.signal_type == "spi_1m") & (d.month == mth)].value
        frac = (np.sign(v) == exp).mean()
        add(f"national spi_1m {mth[:7]} expected {'dry' if exp<0 else 'wet'}", frac > 0.6,
            f"mean {v.mean():+.2f}; {frac:.0%} of units with expected sign")

    write_report(rows, ee_df, cmp, d)


def write_report(rows, ee_df, cmp, d=None):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    n_fail = sum(r[1] == "FAIL" for r in rows)
    L = [f"# Data check: pipeline/data/signals_ZWE.parquet", "",
         f"Generated {now} by `pipeline/audit/verify_signals.py` (independent code path, "
         f"not importing extract_signals.py).", ""]
    if PARQUET.exists():
        st = PARQUET.stat()
        L.append(f"Parquet mtime {datetime.fromtimestamp(st.st_mtime, timezone.utc):%Y-%m-%d %H:%M UTC}, "
                 f"{st.st_size} bytes, {len(d) if d is not None else '?'} rows.")
    L += ["", f"**{len(rows) - n_fail} checks not failed, {n_fail} FAIL.**", "",
          "Independent EE method: per-unit `reduceRegion` mean; CHIRPS v3 pentads summed per "
          "calendar month (5 km); MOD13Q1 NDVI x0.0001 masked SummaryQA in {0,1}, monthly mean of "
          "16-day composites with start date in the month, then masked to WorldCover v200 class 40 "
          "(crop) / 20+30 (shrub+grass), 250 m; ERA5-Land monthly volumetric_soil_water_layer_1 (11 km). "
          "Climatology = 2001-2020 same calendar month.", "",
          "Sample units: " + ", ".join(UNITS) + ".", "",
          "| check | result | detail |", "|---|---|---|"]
    for c, s, det in rows:
        L.append(f"| {c} | {s} | {det.replace('|', '/')} |")
    L += ["", "## Independent EE sample vs parquet", "",
          "| unit | month | precip EE | precip PQ | precip clim | ndvi_crop EE | PQ | clim | "
          "ndvi_grass EE | PQ | clim | sm1 EE | sm1 clim | spi_1m PQ | sm1_z PQ |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    src = cmp if cmp is not None else ee_df
    f = lambda x, n=3: "" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{n}g}"
    for _, r in src.sort_values(["month", "unit_name"]).iterrows():
        L.append("| " + " | ".join([
            r.unit_name, r.month[:7], f(r.precip, 4), f(r.get("pq_precip_mm"), 4), f(r.precip_clim, 4),
            f(r.ndvi_crop), f(r.get("pq_ndvi_crop")), f(r.ndvi_crop_clim),
            f(r.ndvi_grass), f(r.get("pq_ndvi_grass")), f(r.ndvi_grass_clim),
            f(r.sm1), f(r.sm1_clim), f(r.get("pq_spi_1m"), 2), f(r.get("pq_sm1_z"), 2)]) + " |")
    REPORT.write_text("\n".join(L) + "\n")
    print("\n".join(L[:60]))


if __name__ == "__main__":
    main()
