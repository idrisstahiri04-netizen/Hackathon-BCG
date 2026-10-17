#!/usr/bin/env python3
"""Extract monthly drought signals per admin unit from Google Earth Engine.

Output follows pipeline/CONTRACT.md section 1:
    pipeline/data/signals_<ISO3>.parquet   long format
        unit_id, unit_name, iso3, month ("YYYY-MM-01"), signal_type, value
    pipeline/data/units_<ISO3>.geojson     shapeID, shapeName, geometry

Usage:
    python pipeline/extract_signals.py --iso3 ZWE --adm 2 --start 2001 --end 2024

Earth Engine work is done server-side: for every (dataset, year) we stack the
12 monthly composites as bands of one image and run a single reduceRegions over
all units. Raw per-year results are cached in pipeline/cache/<ISO3>/ so reruns
skip finished years. Derived signals (SPI, z-scores, VCI) are computed locally.

Missing data stays NaN; nothing is ever filled with 0.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

import ee

EE_PROJECT = "drought-warning-zw-1016"
HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
OUT = HERE / "data"

BASE_START, BASE_END = 2001, 2020

CHIRPS = "UCSB-CHC/CHIRPS/V3/PENTAD"
MODIS = "MODIS/061/MOD13Q1"
ERA5 = "ECMWF/ERA5_LAND/MONTHLY_AGGR"
WORLDCOVER = "ESA/WorldCover/v200"
BOUNDS = "WM/geoLab/geoBoundaries/600/ADM{adm}"

SCALE = {"chirps": 5566, "modis": 500, "era5": 11132, "static": 100}


# --------------------------------------------------------------------------- EE
def units_fc(iso3: str, adm: int) -> ee.FeatureCollection:
    return ee.FeatureCollection(BOUNDS.format(adm=adm)).filter(
        ee.Filter.eq("shapeGroup", iso3))


def fc_from_geojson(path: str) -> ee.FeatureCollection:
    """Units from a local GeoJSON (props shapeID, shapeName), e.g. Kenya sub-counties."""
    gj = json.loads(Path(path).read_text())
    return ee.FeatureCollection([
        ee.Feature(ee.Geometry(f["geometry"], None, False),
                   {"shapeID": f["properties"]["shapeID"], "shapeName": f["properties"]["shapeName"]})
        for f in gj["features"]])


def landcover_masks():
    wc = ee.ImageCollection(WORLDCOVER).first().select("Map")
    crop = wc.eq(40)
    grass = wc.eq(30).Or(wc.eq(20))
    return crop, grass


def month_range(y: int, m: int):
    start = ee.Date.fromYMD(y, m, 1)
    return start, start.advance(1, "month")


def empty_band(name: str) -> ee.Image:
    return ee.Image.constant(0).updateMask(ee.Image.constant(0)).rename(name).toFloat()


def chirps_year(y: int) -> ee.Image:
    col = ee.ImageCollection(CHIRPS).select("precipitation")
    bands = []
    for m in range(1, 13):
        s, e = month_range(y, m)
        c = col.filterDate(s, e)
        name = f"precip_{m:02d}"
        bands.append(ee.Image(ee.Algorithms.If(
            c.size().gt(0), c.sum().rename(name).toFloat(), empty_band(name))))
    return ee.Image.cat(bands)


def modis_year(y: int) -> ee.Image:
    crop, grass = landcover_masks()

    def prep(img):
        qa = img.select("SummaryQA")
        return img.select("NDVI").multiply(0.0001).updateMask(qa.lte(1))

    col = ee.ImageCollection(MODIS)
    bands = []
    for m in range(1, 13):
        s, e = month_range(y, m)
        c = col.filterDate(s, e).map(prep)
        for tag, mask in (("crop", crop), ("grass", grass)):
            name = f"ndvi_{tag}_{m:02d}"
            bands.append(ee.Image(ee.Algorithms.If(
                c.size().gt(0),
                c.mean().updateMask(mask).rename(name).toFloat(),
                empty_band(name))))
    return ee.Image.cat(bands)


def era5_year(y: int) -> ee.Image:
    col = ee.ImageCollection(ERA5).select(
        ["volumetric_soil_water_layer_1", "volumetric_soil_water_layer_2", "temperature_2m"],
        ["sm1", "sm2", "t2m"])
    bands = []
    for m in range(1, 13):
        s, e = month_range(y, m)
        c = col.filterDate(s, e)
        names = [f"sm1_{m:02d}", f"sm2_{m:02d}", f"t2m_{m:02d}"]
        bands.append(ee.Image(ee.Algorithms.If(
            c.size().gt(0), c.first().rename(names).toFloat(),
            ee.Image.cat([empty_band(n) for n in names]))))
    return ee.Image.cat(bands)


def static_image() -> ee.Image:
    crop, grass = landcover_masks()
    return ee.Image.cat([crop.rename("crop_frac").toFloat(),
                         grass.rename("grass_frac").toFloat()])


def reduce_to_records(img: ee.Image, fc: ee.FeatureCollection, scale: int,
                      tile_scale: int = 4) -> list[dict]:
    band_names = img.bandNames()
    red = img.reduceRegions(collection=fc, reducer=ee.Reducer.mean(),
                            scale=scale, tileScale=tile_scale)
    # drop geometry, keep only id + bands to keep the payload small
    red = red.select(ee.List(["shapeID"]).cat(band_names), None, False)
    feats = red.getInfo()["features"]
    return [f["properties"] for f in feats]


def fetch_cached(key: str, iso3: str, build, fc, scale: int, retries: int = 4):
    path = CACHE / iso3 / f"{key}.json"
    if path.exists():
        return key, json.loads(path.read_text()), True
    last = None
    for attempt in range(retries):
        try:
            recs = reduce_to_records(build(), fc, scale,
                                     tile_scale=4 if attempt < 2 else 16)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(recs))
            tmp.rename(path)
            return key, recs, False
        except Exception as exc:  # EE timeouts / quota / transient
            last = exc
            wait = 10 * (attempt + 1)
            print(f"  ! {key} attempt {attempt + 1} failed: {str(exc)[:160]} (retry in {wait}s)",
                  flush=True)
            time.sleep(wait)
    raise RuntimeError(f"{key} failed after {retries} attempts: {last}")


# ----------------------------------------------------------------- local maths
def wide_from_records(recs: list[dict], year: int) -> pd.DataFrame:
    """records [{shapeID, precip_01..}] -> long rows (unit_id, month, var, value)."""
    rows = []
    for r in recs:
        uid = r["shapeID"]
        for k, v in r.items():
            if k == "shapeID":
                continue
            var, mm = k.rsplit("_", 1)
            rows.append((uid, pd.Timestamp(year, int(mm), 1), var,
                         np.nan if v is None else float(v)))
    return pd.DataFrame(rows, columns=["unit_id", "month", "var", "value"])


def spi_series(acc: pd.DataFrame) -> pd.DataFrame:
    """acc: index month (Timestamp), columns unit_id, values = k-month precip sums.

    Gamma fit per unit & calendar month on the 2001-2020 baseline, mixed
    distribution for zeros: H(x) = q + (1-q) G(x) for x > 0 and H(0) = q/2
    (centre of the zero-probability mass, avoids positive SPI for a dry month
    in a usually dry calendar month). Result clipped to [-3, 3].
    """
    out = pd.DataFrame(np.nan, index=acc.index, columns=acc.columns)
    base_mask = (acc.index.year >= BASE_START) & (acc.index.year <= BASE_END)
    for cm in range(1, 13):
        sel = acc.index.month == cm
        bsel = sel & base_mask
        for uid in acc.columns:
            base = acc.loc[bsel, uid].dropna().values
            if len(base) < 10:
                continue
            n0 = int((base <= 0).sum())
            pos = base[base > 0]
            q = n0 / len(base)
            x = acc.loc[sel, uid]
            if len(pos) < 5:
                # nearly always dry in this calendar month: SPI undefined
                continue
            if np.allclose(pos, pos[0]):
                continue
            try:
                a, loc, scale = stats.gamma.fit(pos, floc=0)
            except Exception:
                continue
            xv = x.values.astype(float)
            H = np.full_like(xv, np.nan)
            ok = ~np.isnan(xv)
            pos_m = ok & (xv > 0)
            zero_m = ok & (xv <= 0)
            H[pos_m] = q + (1 - q) * stats.gamma.cdf(xv[pos_m], a, loc=0, scale=scale)
            # zero in a calendar month that never had zeros in the baseline:
            # it is real data (driest on record), not missing -> lowest SPI
            H[zero_m] = q / 2 if q > 0 else 1e-6
            H = np.clip(H, 1e-6, 1 - 1e-6)
            out.loc[sel, uid] = np.clip(stats.norm.ppf(H), -3, 3)
    return out


def zscore(w: pd.DataFrame) -> pd.DataFrame:
    """w: index month, columns unit. z vs same calendar month 2001-2020."""
    base = w[(w.index.year >= BASE_START) & (w.index.year <= BASE_END)]
    g = base.groupby(base.index.month)
    cm = range(1, 13)
    mu, sd, n = (g.mean().reindex(cm), g.std(ddof=1).reindex(cm),
                 g.count().reindex(cm).fillna(0))
    mu = mu.where(n >= 10)
    sd = sd.where((n >= 10) & (sd > 0))
    m = w.index.month
    return (w - mu.loc[m].values) / sd.loc[m].values


def vci(w: pd.DataFrame) -> pd.DataFrame:
    base = w[(w.index.year >= BASE_START) & (w.index.year <= BASE_END)]
    g = base.groupby(base.index.month)
    cm = range(1, 13)
    lo, hi, n = (g.min().reindex(cm), g.max().reindex(cm),
                 g.count().reindex(cm).fillna(0))
    rng = (hi - lo).where((n >= 10) & ((hi - lo) > 0))
    m = w.index.month
    v = 100 * (w - lo.loc[m].values) / rng.loc[m].values
    return v.clip(0, 100)


def to_long(w: pd.DataFrame, signal: str, months: pd.DatetimeIndex) -> pd.DataFrame:
    w = w.reindex(months)
    w.index.name = "month"
    lg = w.stack(future_stack=True).rename("value").reset_index()
    lg.columns = ["month", "unit_id", "value"]
    lg["signal_type"] = signal
    return lg


# ------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--iso3", required=True)
    ap.add_argument("--adm", type=int, default=2)
    ap.add_argument("--start", type=int, default=2001)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--geojson", help="local unit geometries instead of geoBoundaries (e.g. pipeline/data/units_KENSUB.geojson)")
    ap.add_argument("--tag", help="name for cache dir + output files (default: ISO3); use with --geojson")
    ap.add_argument("--no-geojson", action="store_true")
    args = ap.parse_args()
    iso3 = args.iso3.upper()
    tag = (args.tag or iso3).upper()
    t0 = time.time()

    ee.Initialize(project=EE_PROJECT)
    fc = fc_from_geojson(args.geojson) if args.geojson else units_fc(iso3, args.adm)
    if args.geojson:
        args.no_geojson = True
    meta = fc.select(["shapeID", "shapeName"], None, False).getInfo()["features"]
    names = {f["properties"]["shapeID"]: f["properties"]["shapeName"] for f in meta}
    print(f"{iso3} ADM{args.adm}: {len(names)} units", flush=True)
    if not names:
        sys.exit("no units found")

    OUT.mkdir(parents=True, exist_ok=True)
    gj_path = OUT / f"units_{tag}.geojson"
    if not args.no_geojson and not gj_path.exists():
        gj = fc.map(lambda f: f.simplify(maxError=100)).select(
            ["shapeID", "shapeName"]).getInfo()
        gj = {"type": "FeatureCollection",
              "features": [{"type": "Feature", "properties": f["properties"],
                            "geometry": f["geometry"]} for f in gj["features"]]}
        gj_path.write_text(json.dumps(gj))
        print(f"wrote {gj_path}", flush=True)

    # CHIRPS one year earlier so SPI-3/6 exist from the first output month
    tasks = [("static", static_image, SCALE["static"])]
    for y in range(args.start - 1, args.end + 1):
        tasks.append((f"chirps_{y}", lambda y=y: chirps_year(y), SCALE["chirps"]))
    for y in range(args.start, args.end + 1):
        tasks.append((f"modis_{y}", lambda y=y: modis_year(y), SCALE["modis"]))
        tasks.append((f"era5_{y}", lambda y=y: era5_year(y), SCALE["era5"]))

    results = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(fetch_cached, k, tag, b, fc, s) for k, b, s in tasks]
        for fu in as_completed(futs):
            k, recs, cached = fu.result()
            results[k] = recs
            print(f"  {'cached' if cached else 'fetched'} {k} ({time.time() - t0:.0f}s)",
                  flush=True)

    # ---- assemble raw monthly table
    parts = []
    for k, recs in results.items():
        if k == "static":
            continue
        y = int(k.rsplit("_", 1)[1])
        parts.append(wide_from_records(recs, y))
    raw = pd.concat(parts, ignore_index=True)
    wide = {v: g.pivot(index="month", columns="unit_id", values="value").sort_index()
            for v, g in raw.groupby("var")}
    units = sorted(names)
    for v in wide:
        wide[v] = wide[v].reindex(columns=units)

    months = pd.date_range(f"{args.start}-01-01", f"{args.end}-12-01", freq="MS")
    full = pd.date_range(f"{args.start - 1}-01-01", f"{args.end}-12-01", freq="MS")
    pr = wide["precip"].reindex(full)

    out = [to_long(pr, "precip_mm", months)]
    for k in (1, 3, 6):
        acc = pr.rolling(k, min_periods=k).sum()
        out.append(to_long(spi_series(acc), f"spi_{k}m", months))
    for lc in ("crop", "grass"):
        w = wide[f"ndvi_{lc}"].reindex(months)
        out += [to_long(w, f"ndvi_{lc}", months),
                to_long(zscore(w), f"ndvi_z_{lc}", months),
                to_long(vci(w), f"vci_{lc}", months)]
    for v in ("sm1", "sm2", "t2m"):
        out.append(to_long(zscore(wide[v].reindex(months)), f"{v}_z", months))

    st = pd.DataFrame(results["static"]).set_index("shapeID").reindex(units)
    for col in ("crop_frac", "grass_frac"):
        out.append(pd.DataFrame({"month": pd.Timestamp(args.start, 1, 1),
                                 "unit_id": units,
                                 "value": pd.to_numeric(st[col], errors="coerce").values,
                                 "signal_type": col}))

    df = pd.concat(out, ignore_index=True)
    df["unit_name"] = df["unit_id"].map(names)
    df["iso3"] = iso3
    df["month"] = pd.to_datetime(df["month"]).dt.strftime("%Y-%m-01")
    df["value"] = df["value"].astype("float64")
    df = df[["unit_id", "unit_name", "iso3", "month", "signal_type", "value"]]
    path = OUT / f"signals_{tag}.parquet"
    df.to_parquet(path, index=False)

    print(f"wrote {path}: {len(df)} rows, {df['value'].isna().sum()} NaN, "
          f"{time.time() - t0:.0f}s total")
    print(df.groupby("signal_type")["value"].agg(["count", "size", "mean", "min", "max"])
          .round(3).to_string())


if __name__ == "__main__":
    main()
