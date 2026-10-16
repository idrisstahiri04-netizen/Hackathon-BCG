"""Static urban flag per admin unit (built-up share from ESA WorldCover v200 class 50 + WorldPop density).

Why: town / city-council units (e.g. ZWE "Bindura Urban", Harare, Epworth) are tiny, have little or no
cropland, and their satellite signals mostly describe the surrounding farmland. A Warning there is not a
farmer/herder Warning. Export marks them `urban: true` (levels stay visible; farmer/herder Warning counts
and SMS exclude them). Rule (fixed before looking at alert outcomes; checked only against the unit list, e.g. ZWE rural districts have
built_frac <= 0.012, town councils >= 0.014):
    urban = built_frac >= 0.15
         or (built_frac >= 0.05 and (area < 1000 km2 or pop density >= 1000 / km2))
         or (official unit name says town/city: Urban, Town, City, Cidade, Township, Municipality,
             Arrondissement, Mjini, and area < 5000 km2)

    python pipeline/urban_units.py [--iso3 ZWE KEN ...]
Output: pipeline/data/urban_units.csv (iso3, unit_id, unit_name, area_km2, built_frac, pop_density, urban)
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import ee
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "urban_units.csv"
ADM = {"KEN": 1}                 # everything else ADM2 (CONTRACT.md countries table)
ALL = "ZWE KEN MWI ZMB MOZ TZA ETH SOM NAM BWA ZAF MDG AGO UGA".split()
BUILT_MIN, BUILT_DENSE, DENS_MIN, AREA_SMALL, AREA_NAME = 0.15, 0.05, 1000.0, 1000.0, 5000.0
URBAN_NAME = re.compile(r"\b(urban|town|city|cidade|township|municipality|arrondissement|mjini)\b", re.I)


def is_urban(name, area, built, dens) -> bool:
    b = 0.0 if pd.isna(built) else float(built)
    d = 0.0 if pd.isna(dens) else float(dens)
    a = float("inf") if pd.isna(area) else float(area)
    return bool(b >= BUILT_MIN or (b >= BUILT_DENSE and (a < AREA_SMALL or d >= DENS_MIN))
                or (URBAN_NAME.search(str(name)) and a < AREA_NAME))


def country(iso3: str) -> pd.DataFrame:
    fc = ee.FeatureCollection(f"WM/geoLab/geoBoundaries/600/ADM{ADM.get(iso3, 2)}").filter(
        ee.Filter.eq("shapeGroup", iso3))
    fc = fc.map(lambda f: f.set("area_km2", f.geometry().area(100).divide(1e6)))
    built = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map").eq(50).rename("built_frac")
    red = built.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=100, tileScale=8)
    rows = red.select(["shapeID", "shapeName", "area_km2", "mean"], None, False).getInfo()["features"]
    d = pd.DataFrame([{"iso3": iso3, "unit_id": r["properties"]["shapeID"], "unit_name": r["properties"]["shapeName"],
                       "area_km2": r["properties"].get("area_km2"), "built_frac": r["properties"].get("mean")}
                      for r in rows])
    pf = HERE / "data" / f"pop_{iso3}.csv"
    pop = pd.read_csv(pf).set_index("unit_id")["pop_millions"] if pf.exists() else pd.Series(dtype=float)
    d["pop_density"] = d.unit_id.map(pop) * 1e6 / d.area_km2
    d["urban"] = [is_urban(*x) for x in zip(d.unit_name, d.area_km2, d.built_frac, d.pop_density)]
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso3", nargs="+", default=ALL)
    a = ap.parse_args()
    ee.Initialize(project="drought-warning-zw-1016")
    old = pd.read_csv(OUT) if OUT.exists() else pd.DataFrame()
    parts = [country(i) for i in a.iso3]
    new = pd.concat(parts, ignore_index=True)
    if len(old):
        new = pd.concat([old[~old.iso3.isin(a.iso3)], new], ignore_index=True)
    new.sort_values(["iso3", "unit_id"]).to_csv(OUT, index=False)
    for d in parts:
        print(d.iso3.iloc[0], len(d), "urban:", int(d.urban.sum()), sorted(d[d.urban].unit_name))


if __name__ == "__main__":
    main()
