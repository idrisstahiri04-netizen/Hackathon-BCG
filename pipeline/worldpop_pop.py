"""
Population per unit from WorldPop (Earth Engine), for the globe's "people affected".

    python3 pipeline/worldpop_pop.py --iso3 ZWE MWI ZMB KEN

Input : unit polygons via prep_geo.load_units (raw geoBoundaries download if
        present, else pipeline/data/units_<ISO3>.geojson; shapeID / shapeName)
Output: pipeline/data/pop_<ISO3>.csv  (unit_id, unit_name, pop_millions, source, year)

Uses the newest year in "WorldPop/GP/100m/pop" for the country (2020 as of
writing), band `population` (people per ~100 m pixel), summed per unit at the
dataset's native scale. GeometryCollection units are flattened to MultiPolygon
before the request. Idempotent: existing CSVs are rewritten in place.
"""

import argparse
import csv
import json
import os
import sys

import ee

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.join(ROOT, "pipeline")
COLLECTION = "WorldPop/GP/100m/pop"
PROJECT = "drought-warning-zw-1016"


def polygons_only(geom):
    """Return a (Multi)Polygon GeoJSON dict from any GeoJSON geometry."""
    t = geom["type"]
    if t == "Polygon":
        return {"type": "MultiPolygon", "coordinates": [geom["coordinates"]]}
    if t == "MultiPolygon":
        return geom
    if t == "GeometryCollection":
        polys = []
        for g in geom["geometries"]:
            sub = polygons_only(g)
            if sub:
                polys += sub["coordinates"]
        return {"type": "MultiPolygon", "coordinates": polys} if polys else None
    return None


def run(iso3):
    # Same geometry source and precedence as prep_geo.py (raw geoBoundaries
    # download first, then units_<ISO3>.geojson), so ids match the asset.
    sys.path.insert(0, PIPE)
    from prep_geo import load_units
    fc, src, _ = load_units(iso3)
    print(f"[{iso3}] geometry: {src}", file=sys.stderr)
    feats = []
    for f in fc["features"]:
        pr = f["properties"]
        geom = polygons_only(f["geometry"])
        if geom is None:
            print(f"[{iso3}] skip {pr.get('shapeName')}: no polygon", file=sys.stderr)
            continue
        uid = pr.get("unit_id") or pr.get("shapeID") or pr.get("id")
        name = (pr.get("unit_name") or pr.get("shapeName") or pr.get("name") or "").strip()
        feats.append(ee.Feature(ee.Geometry(geom, None, False), {"unit_id": uid, "unit_name": name}))

    col = ee.ImageCollection(COLLECTION).filter(ee.Filter.eq("country", iso3))
    img = col.sort("year", False).first()
    year = img.get("year").getInfo()
    scale = img.projection().nominalScale().getInfo()
    stats = img.select("population").reduceRegions(
        collection=ee.FeatureCollection(feats),
        reducer=ee.Reducer.sum(),
        scale=scale,
    ).getInfo()

    rows = []
    for f in stats["features"]:
        p = f["properties"]
        total = p.get("sum")
        rows.append({
            "unit_id": p["unit_id"],
            "unit_name": p["unit_name"],
            "pop_millions": "" if total is None else f"{total / 1e6:.2f}",
            "source": f"WorldPop {COLLECTION} (Earth Engine), CC BY 4.0",
            "year": year,
        })
    rows.sort(key=lambda r: r["unit_name"])
    out = os.path.join(PIPE, "data", f"pop_{iso3}.csv")
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["unit_id", "unit_name", "pop_millions", "source", "year"])
        w.writeheader()
        w.writerows(rows)
    nat = sum(float(r["pop_millions"]) for r in rows if r["pop_millions"])
    print(f"[{iso3}] {len(rows)} units, year {year}, scale {scale:.1f} m, national {nat:.2f} M -> {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso3", nargs="+", required=True)
    args = ap.parse_args()
    ee.Initialize(project=PROJECT)
    for iso in args.iso3:
        run(iso.upper())
