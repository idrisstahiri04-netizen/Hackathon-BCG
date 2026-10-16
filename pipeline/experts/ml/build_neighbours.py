"""Laptop-side (light): queen-contiguity neighbour lists per unit from pipeline/data/units_<ISO3>.geojson.

Writes pipeline/experts/ml/xml_neighbours.json = {"units": {unit_id: {"iso3": .., "nb": [unit_id, ...]}}, "meta": {...}}.
Units with no touching neighbour (islands, slivers) get their 3 nearest centroids instead (flagged).
Only geometry is used; no signal data, so nothing here can leak labels.

    /home/looooo/bcg/.venv/bin/python pipeline/experts/ml/build_neighbours.py --iso3 ZWE KEN MWI ZMB
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from shapely.geometry import shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

HERE = Path(__file__).resolve().parent
PIPE = HERE.parent.parent
DATA = PIPE / "data"


def load_units(iso3: str):
    g = json.loads((DATA / f"units_{iso3}.geojson").read_text())
    ids, geoms = [], []
    for ft in g["features"]:
        geom = ft.get("geometry")
        if not geom:
            continue
        s = shape(geom)
        if s.geom_type == "GeometryCollection":
            s = unary_union([p for p in s.geoms if p.geom_type in ("Polygon", "MultiPolygon")])
        s = s.buffer(0)
        ids.append(ft["properties"]["shapeID"])
        geoms.append(s)
    return ids, geoms


def neighbours(ids, geoms, tol_deg=2e-3, k_fallback=3):
    """Queen contiguity: polygons whose tol-buffered geometries intersect (tol ~200 m absorbs boundary slivers)."""
    buf = [g.buffer(tol_deg) for g in geoms]
    tree = STRtree(buf)
    cents = np.array([[g.centroid.x, g.centroid.y] for g in geoms])
    out, fallback = {}, []
    for i, g in enumerate(buf):
        hits = [int(j) for j in tree.query(g, predicate="intersects") if int(j) != i]
        if not hits:
            d = np.hypot(*(cents - cents[i]).T)
            d[i] = np.inf
            hits = [int(j) for j in np.argsort(d)[:k_fallback]]
            fallback.append(ids[i])
        out[ids[i]] = sorted(ids[j] for j in hits)
    return out, fallback


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso3", nargs="+", default=["ZWE", "KEN", "MWI", "ZMB"])
    a = ap.parse_args()
    units, meta = {}, {}
    for iso in a.iso3:
        ids, geoms = load_units(iso)
        nb, fb = neighbours(ids, geoms)
        for u in ids:
            units[u] = {"iso3": iso, "nb": nb[u]}
        deg = [len(v) for v in nb.values()]
        meta[iso] = {"units": len(ids), "mean_degree": round(float(np.mean(deg)), 2), "min_degree": int(min(deg)),
                     "max_degree": int(max(deg)), "fallback_units": len(fb)}
        print(iso, meta[iso])
    (HERE / "xml_neighbours.json").write_text(json.dumps({"units": units, "meta": meta}))
    print("->", HERE / "xml_neighbours.json")


if __name__ == "__main__":
    main()
