"""
Build the browser geometry asset for one country (CONTRACT.md section 2).

    python3 pipeline/prep_geo.py --iso3 ZWE            # one country
    python3 pipeline/prep_geo.py --iso3 ZWE KEN MWI ZMB

Input : pipeline/data/units_<ISO3>.geojson if it exists (made by the signals
        helper). Otherwise the geoBoundaries gbOpen simplified file is fetched
        from the API and kept raw under pipeline/data/raw/geoboundaries/<date>/
        with a _meta.json (url, fetched_at, sha256, licence).
Output: data/geo/<ISO3>.js
        window.GEO_DATA = window.GEO_DATA || {}; GEO_DATA["ZWE"] = <FeatureCollection>;
        feature.properties: id, name, lat, lng, pop (millions|null), crop, grass (frac|null)

Rings are simplified (Douglas-Peucker), rounded to 3 dp, and re-wound so the
exterior ring is CLOCKWISE (three-globe wants the opposite of the GeoJSON
right-hand rule; get it wrong and one district paints the whole globe).
"""

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.join(ROOT, "pipeline")
ADM = {"ZWE": "ADM2", "MWI": "ADM2", "ZMB": "ADM2", "KEN": "ADM1"}
# Coarser for big ADM1 counties, finer for small ADM2 districts.
EPSILON = {"ADM1": 0.012, "ADM2": 0.006}


# ---- geometry helpers (same maths as prep_data.py) --------------------------
def perp_distance(pt, start, end):
    if start == end:
        return math.dist(pt, start)
    (x0, y0), (x1, y1), (x2, y2) = pt, start, end
    return abs((y2 - y1) * x0 - (x2 - x1) * y0 + x2 * y1 - y2 * x1) / math.dist(start, end)


def rdp(points, eps):
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi <= lo + 1:
            continue
        worst, wi = 0.0, lo
        for i in range(lo + 1, hi):
            d = perp_distance(points[i], points[lo], points[hi])
            if d > worst:
                worst, wi = d, i
        if worst > eps:
            keep[wi] = True
            stack += [(lo, wi), (wi, hi)]
    return [p for p, k in zip(points, keep) if k]


def simplify_ring(ring, eps):
    pts = rdp([(round(p[0], 3), round(p[1], 3)) for p in ring], eps)
    out = [pts[0]]
    for p in pts[1:]:
        if p != out[-1]:
            out.append(p)
    if out[0] != out[-1]:
        out.append(out[0])
    return out if len(out) >= 4 else None


def ring_area_centroid(ring):
    a = cx = cy = 0.0
    for i in range(len(ring) - 1):
        (x0, y0), (x1, y1) = ring[i], ring[i + 1]
        c = x0 * y1 - x1 * y0
        a += c
        cx += (x0 + x1) * c
        cy += (y0 + y1) * c
    a *= 0.5
    if abs(a) < 1e-12:
        return 0.0, ring[0][0], ring[0][1]
    return a, cx / (6 * a), cy / (6 * a)


# ---- input ------------------------------------------------------------------
def fetch_geoboundaries(iso3, adm):
    api = f"https://www.geoboundaries.org/api/current/gbOpen/{iso3}/{adm}/"
    meta = json.load(urllib.request.urlopen(api, timeout=60))
    url = meta["simplifiedGeometryGeoJSON"]
    day = dt.date.today().isoformat()
    out_dir = os.path.join(PIPE, "data", "raw", "geoboundaries", day)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{iso3}_{adm}_simplified.geojson")
    if not os.path.exists(path):
        body = urllib.request.urlopen(url, timeout=120).read()
        with open(path, "wb") as fh:
            fh.write(body)
        with open(path + "._meta.json", "w") as fh:
            json.dump({
                "url": url, "api": api,
                "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "sha256": hashlib.sha256(body).hexdigest(),
                "licence": meta.get("boundaryLicense"),
                "source": meta.get("boundarySource"),
            }, fh, indent=1)
    return json.load(open(path)), f"geoBoundaries gbOpen {iso3} {adm} ({meta.get('boundaryLicense')})"


def load_units(iso3):
    adm = ADM.get(iso3, "ADM2")
    # An already-downloaded geoBoundaries file (same shapeIDs) wins: the
    # units_<ISO3>.geojson copies carry a few damaged polygons (e.g. MWI
    # Mangochi swallowing Lake Malawi), so prefer the untouched raw download.
    raw_dir = os.path.join(PIPE, "data", "raw", "geoboundaries")
    if os.path.isdir(raw_dir):
        for day in sorted(os.listdir(raw_dir), reverse=True):
            path = os.path.join(raw_dir, day, f"{iso3}_{adm}_simplified.geojson")
            if os.path.exists(path):
                meta = {}
                if os.path.exists(path + "._meta.json"):
                    meta = json.load(open(path + "._meta.json"))
                return (json.load(open(path)),
                        f"geoBoundaries gbOpen {iso3} {adm} ({meta.get('licence')})", adm)
    local = os.path.join(PIPE, "data", f"units_{iso3}.geojson")
    if os.path.exists(local):
        return json.load(open(local)), f"pipeline/data/units_{iso3}.geojson", adm
    print(f"[{iso3}] {local} missing, fetching geoBoundaries {adm}", file=sys.stderr)
    fc, src = fetch_geoboundaries(iso3, adm)
    return fc, src, adm


def kenya_extras():
    """Kenya census populations + crop share from the original prep_data.py,
    so the KEN asset carries the same numbers the prototype used."""
    sys.path.insert(0, ROOT)
    try:
        import prep_data as pd_  # noqa
        return pd_.POP, pd_.PROFILE, pd_.ALIASES
    except Exception:
        return {}, {}, {}


def num(v):
    try:
        return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)
    except (TypeError, ValueError):
        return None


def polygon_parts(g):
    """List of polygons (each a list of rings) from any GeoJSON geometry.
    units_<ISO3>.geojson sometimes wraps a unit in a GeometryCollection with
    stray LineStrings; only the polygon parts matter here."""
    if g["type"] == "Polygon":
        return [g["coordinates"]]
    if g["type"] == "MultiPolygon":
        return g["coordinates"]
    if g["type"] == "GeometryCollection":
        return [p for sub in g["geometries"] for p in polygon_parts(sub)]
    return []


def worldpop_extras(iso3):
    """unit_id -> population (millions) from pipeline/data/pop_<ISO3>.csv
    (made by pipeline/worldpop_pop.py). Empty dict if the file is absent."""
    path = os.path.join(PIPE, "data", f"pop_{iso3}.csv")
    if not os.path.exists(path):
        return {}, None
    import csv
    out, src = {}, None
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            v = num(row.get("pop_millions") or None)
            if v is not None:
                out[row["unit_id"]] = v
                src = src or f"{row.get('source')} {row.get('year')}"
    return out, src


# ---- main -------------------------------------------------------------------
def build(iso3):
    fc, src, adm = load_units(iso3)
    eps = EPSILON[adm]
    pop_k, prof_k, alias_k = kenya_extras() if iso3 == "KEN" else ({}, {}, {})
    # Kenya keeps its census numbers; other countries take WorldPop per unit_id.
    pop_w, pop_src = worldpop_extras(iso3) if iso3 != "KEN" else ({}, None)
    if pop_src:
        src += f"; pop: {pop_src}"
    feats = []
    for f in fc["features"]:
        pr = f["properties"]
        uid = pr.get("unit_id") or pr.get("shapeID") or pr.get("id")
        name = (pr.get("unit_name") or pr.get("shapeName") or pr.get("name") or "").strip()
        name = alias_k.get(name, name)
        polys = polygon_parts(f["geometry"])
        out, best, cx, cy = [], 0.0, 0.0, 0.0
        for poly in polys:
            rings = [r for r in (simplify_ring(r, eps) for r in poly) if r]
            if not rings:
                continue
            fixed = []
            for i, ring in enumerate(rings):
                a, _, _ = ring_area_centroid(ring)
                if (a < 0) != (i == 0):          # shell clockwise, holes CCW
                    ring = ring[::-1]
                fixed.append([list(p) for p in ring])
            out.append(fixed)
            a, rx, ry = ring_area_centroid(rings[0])
            if abs(a) > best:
                best, cx, cy = abs(a), rx, ry
        if not out:
            print(f"[{iso3}] dropped {name}: geometry vanished", file=sys.stderr)
            continue
        pop = num(pr.get("pop"))
        if pop is None and name in pop_k:
            pop = pop_k[name]
        if pop is None and uid in pop_w:
            pop = pop_w[uid]
        crop = num(pr.get("crop_frac", pr.get("crop")))
        if crop is None and name in prof_k:
            crop = prof_k[name][1]
        grass = num(pr.get("grass_frac", pr.get("grass")))
        feats.append({
            "type": "Feature",
            "properties": {
                "id": uid, "name": name,
                "lat": round(cy, 3), "lng": round(cx, 3),
                "pop": None if pop is None else round(pop, 3),
                "crop": None if crop is None else round(crop, 3),
                "grass": None if grass is None else round(grass, 3),
            },
            "geometry": {"type": "MultiPolygon", "coordinates": out},
        })
    feats.sort(key=lambda f: f["properties"]["name"])
    body = json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":"))
    os.makedirs(os.path.join(ROOT, "data", "geo"), exist_ok=True)
    path = os.path.join(ROOT, "data", "geo", f"{iso3}.js")
    with open(path, "w") as fh:
        fh.write(f"// {iso3} {adm} units. Source: {src}.\n")
        fh.write("// Generated by pipeline/prep_geo.py - do not edit by hand.\n")
        fh.write("window.GEO_DATA = window.GEO_DATA || {};\n")
        fh.write(f'GEO_DATA["{iso3}"] = {body};\n')
    verts = sum(len(r) for f in feats for p in f["geometry"]["coordinates"] for r in p)
    dup = len(feats) - len({f["properties"]["name"] for f in feats})
    print(f"[{iso3}] {len(feats)} units, {verts} vertices, {len(body)/1024:.0f} KB"
          + (f", {dup} duplicate names" if dup else "") + f" -> {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso3", nargs="+", required=True)
    for iso in ap.parse_args().iso3:
        build(iso.upper())
