#!/usr/bin/env python3
"""Quick feasibility extraction of extra agro-climatic indicators per admin unit and month.

    python pipeline/experts/agroclimate/extract_agroclimate.py --iso3 ZWE [--start 2001 --end 2024]

Same pattern as pipeline/extract_signals.py: one reduceRegions per (dataset, year) with the 12
monthly composites stacked as bands; raw results cached in pipeline/cache/agroclimate/<ISO3>/.
Derived indices (z-scores, TCI, VHI, SPEI-like water balance) are computed by analyse.py.

Datasets (all verified in Earth Engine on 2026-10-16):
  MODIS/061/MOD11A2             LST day 1 km 8-day   -> lst_crop, lst_grass (deg C, monthly mean, QC<=1)
  NASA/FLDAS/NOAH01/C/GL/M/V001 FEWS NET LDAS 0.1 deg monthly -> fl_sm1 (0-10 cm), fl_sm2 (10-40 cm),
                                fl_sm3 (40-100 cm) m3/m3, fl_evap (kg/m2/s), fl_rain (kg/m2/s), fl_tair (K)
  NASA/GLDAS/V021/NOAH/G025/T3H GLDAS 2.1 0.25 deg 3-hourly -> monthly mean gl_pet (W/m2), gl_evap (kg/m2/s),
                                gl_rootmoist (kg/m2), gl_sm1 (kg/m2)
  MODIS/061/MOD16A2GF           ET/PET 500 m 8-day (gap-filled, produced yearly: NOT operational) -> m16_et, m16_pet
                                (kg/m2/8day, monthly mean of composites, cropland mask)
  IDAHO_EPSCOR/TERRACLIMATE     4 km monthly (released yearly: NOT operational) -> tc_def, tc_pet, tc_soil, tc_pdsi
Raw values only; nothing is filled. Output: pipeline/cache/agroclimate/<ISO3>/raw_<ISO3>.parquet (long).
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

HERE = Path(__file__).resolve().parent
PIPE = HERE.parent.parent
sys.path.insert(0, str(PIPE))

EE_PROJECT = "drought-warning-zw-1016"
BOUNDS = "WM/geoLab/geoBoundaries/600/ADM{adm}"
WORLDCOVER = "ESA/WorldCover/v200"
CACHE = PIPE / "cache" / "agroclimate"
DATA = PIPE / "data"

import ee  # noqa: E402


def unit_ids(iso3: str) -> dict:
    g = json.loads((DATA / f"units_{iso3}.geojson").read_text())
    return {f["properties"]["shapeID"]: f["properties"].get("shapeName") for f in g["features"]}


def units_fc(iso3: str, ids: set):
    for adm in (2, 1):
        fc = ee.FeatureCollection(BOUNDS.format(adm=adm)).filter(ee.Filter.eq("shapeGroup", iso3))
        got = set(fc.aggregate_array("shapeID").getInfo())
        if got == ids:
            return fc, adm
    raise RuntimeError(f"{iso3}: no geoBoundaries ADM level matches units geojson ids")


def month_range(y, m):
    s = ee.Date.fromYMD(y, m, 1)
    return s, s.advance(1, "month")


def empty_band(name):
    return ee.Image.constant(0).updateMask(ee.Image.constant(0)).rename(name).toFloat()


def masks():
    wc = ee.ImageCollection(WORLDCOVER).first().select("Map")
    return wc.eq(40), wc.eq(30).Or(wc.eq(20))


def lst_year(y):
    crop, grass = masks()

    def prep(img):
        qc = img.select("QC_Day")
        good = qc.bitwiseAnd(3).lte(1)
        return img.select("LST_Day_1km").multiply(0.02).subtract(273.15).updateMask(good)

    col = ee.ImageCollection("MODIS/061/MOD11A2")
    bands = []
    for m in range(1, 13):
        s, e = month_range(y, m)
        c = col.filterDate(s, e).map(prep)
        for tag, mk in (("crop", crop), ("grass", grass)):
            name = f"lst_{tag}_{m:02d}"
            bands.append(ee.Image(ee.Algorithms.If(
                c.size().gt(0), c.mean().updateMask(mk).rename(name).toFloat(), empty_band(name))))
    return ee.Image.cat(bands)


def fldas_year(y):
    col = ee.ImageCollection("NASA/FLDAS/NOAH01/C/GL/M/V001").select(
        ["SoilMoi00_10cm_tavg", "SoilMoi10_40cm_tavg", "SoilMoi40_100cm_tavg", "Evap_tavg",
         "Rainf_f_tavg", "Tair_f_tavg"],
        ["fl_sm1", "fl_sm2", "fl_sm3", "fl_evap", "fl_rain", "fl_tair"])
    bands = []
    for m in range(1, 13):
        s, e = month_range(y, m)
        c = col.filterDate(s, e)
        names = [f"{v}_{m:02d}" for v in ["fl_sm1", "fl_sm2", "fl_sm3", "fl_evap", "fl_rain", "fl_tair"]]
        bands.append(ee.Image(ee.Algorithms.If(
            c.size().gt(0), c.first().rename(names).toFloat(),
            ee.Image.cat([empty_band(n) for n in names]))))
    return ee.Image.cat(bands)


def gldas_year(y):
    col = ee.ImageCollection("NASA/GLDAS/V021/NOAH/G025/T3H").select(
        ["PotEvap_tavg", "Evap_tavg", "RootMoist_inst", "SoilMoi0_10cm_inst"],
        ["gl_pet", "gl_evap", "gl_rootmoist", "gl_sm1"])
    bands = []
    for m in range(1, 13):
        s, e = month_range(y, m)
        c = col.filterDate(s, e)
        names = [f"{v}_{m:02d}" for v in ["gl_pet", "gl_evap", "gl_rootmoist", "gl_sm1"]]
        bands.append(ee.Image(ee.Algorithms.If(
            c.size().gt(0), c.mean().rename(names).toFloat(),
            ee.Image.cat([empty_band(n) for n in names]))))
    return ee.Image.cat(bands)


def mod16_year(y):
    crop, _ = masks()
    col = ee.ImageCollection("MODIS/061/MOD16A2GF").select(["ET", "PET"])

    def prep(img):
        # fill values >= 32761 are invalid
        et, pet = img.select("ET"), img.select("PET")
        return ee.Image.cat([et.updateMask(et.lt(32700)).multiply(0.1),
                             pet.updateMask(pet.lt(32700)).multiply(0.1)]).rename(["m16_et", "m16_pet"])

    bands = []
    for m in range(1, 13):
        s, e = month_range(y, m)
        c = col.filterDate(s, e).map(prep)
        names = [f"m16_et_{m:02d}", f"m16_pet_{m:02d}"]
        bands.append(ee.Image(ee.Algorithms.If(
            c.size().gt(0), c.mean().updateMask(crop).rename(names).toFloat(),
            ee.Image.cat([empty_band(n) for n in names]))))
    return ee.Image.cat(bands)


def terra_year(y):
    col = ee.ImageCollection("IDAHO_EPSCOR/TERRACLIMATE").select(
        ["def", "pet", "soil", "pdsi"], ["tc_def", "tc_pet", "tc_soil", "tc_pdsi"])
    bands = []
    for m in range(1, 13):
        s, e = month_range(y, m)
        c = col.filterDate(s, e)
        names = [f"{v}_{m:02d}" for v in ["tc_def", "tc_pet", "tc_soil", "tc_pdsi"]]
        bands.append(ee.Image(ee.Algorithms.If(
            c.size().gt(0), c.first().rename(names).toFloat(),
            ee.Image.cat([empty_band(n) for n in names]))))
    return ee.Image.cat(bands)


DATASETS = {   # key -> (builder, scale m)
    "lst": (lst_year, 1000),
    "fldas": (fldas_year, 11132),
    "gldas": (gldas_year, 27830),
    "mod16": (mod16_year, 500),
    "terra": (terra_year, 4638),
}


def reduce_to_records(img, fc, scale, tile_scale=4):
    bn = img.bandNames()
    red = img.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=scale, tileScale=tile_scale)
    red = red.select(ee.List(["shapeID"]).cat(bn), None, False)
    return [f["properties"] for f in red.getInfo()["features"]]


def fetch_cached(key, iso3, build, fc, scale, retries=4):
    path = CACHE / iso3 / f"{key}.json"
    if path.exists():
        return key, json.loads(path.read_text()), True
    last = None
    for attempt in range(retries):
        try:
            recs = reduce_to_records(build(), fc, scale, tile_scale=4 if attempt < 2 else 16)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(recs))
            tmp.rename(path)
            return key, recs, False
        except Exception as exc:
            last = exc
            wait = 10 * (attempt + 1)
            print(f"  ! {key} attempt {attempt + 1} failed: {str(exc)[:160]} (retry in {wait}s)", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"{key} failed after {retries} attempts: {last}")


def records_to_long(recs, year):
    rows = []
    for r in recs:
        uid = r["shapeID"]
        for k, v in r.items():
            if k == "shapeID":
                continue
            var, mm = k.rsplit("_", 1)
            rows.append((uid, pd.Timestamp(year, int(mm), 1), var, np.nan if v is None else float(v)))
    return pd.DataFrame(rows, columns=["unit_id", "month", "var", "value"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso3", nargs="+", default=["ZWE"])
    ap.add_argument("--start", type=int, default=2001)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--datasets", nargs="+", default=list(DATASETS))
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    ee.Initialize(project=EE_PROJECT)
    for iso3 in args.iso3:
        t0 = time.time()
        ids = unit_ids(iso3)
        fc, adm = units_fc(iso3, set(ids))
        print(f"{iso3}: {len(ids)} units (ADM{adm})", flush=True)
        tasks = []
        for ds in args.datasets:
            build, scale = DATASETS[ds]
            for y in range(args.start, args.end + 1):
                tasks.append((f"{ds}_{y}", lambda y=y, b=build: b(y), scale))
        results = {}
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = [pool.submit(fetch_cached, k, iso3, b, fc, s) for k, b, s in tasks]
            for fu in as_completed(futs):
                k, recs, cached = fu.result()
                results[k] = recs
                if not cached:
                    print(f"  fetched {k} ({time.time() - t0:.0f}s)", flush=True)
        parts = [records_to_long(recs, int(k.rsplit("_", 1)[1])) for k, recs in results.items()]
        raw = pd.concat(parts, ignore_index=True)
        raw["unit_name"] = raw.unit_id.map(ids)
        raw["iso3"] = iso3
        out = CACHE / iso3 / f"raw_{iso3}.parquet"
        raw.to_parquet(out, index=False)
        print(f"  {iso3}: wrote {out} rows={len(raw)} vars={sorted(raw['var'].unique())} ({time.time() - t0:.0f}s)",
              flush=True)


if __name__ == "__main__":
    main()
