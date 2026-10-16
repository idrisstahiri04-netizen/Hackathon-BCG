"""
Turn the raw geoBoundaries Kenya ADM1 file into a compact JS asset for the prototype.

Input : ken_raw.geojson   (geoBoundaries gbOpen KEN ADM1 simplified, public domain)
Output: data/kenya-counties.js

Does three things:
  1. Douglas-Peucker simplification + 3dp rounding, to get 841K down to something a
     browser can recolour 72 times without stuttering.
  2. Computes a centroid per county (used for the fly-to camera and label anchors).
  3. Attaches the agro-ecological metadata the risk simulation needs: how arid the
     county is, and how much of it is cropland. Those two numbers decide how hard a
     failed rainy season hits it.
"""

import json
import math

EPSILON = 0.012  # degrees, ~1.3 km. Keeps county outlines recognisable at globe zoom.


def perp_distance(pt, start, end):
    if start == end:
        return math.dist(pt, start)
    x0, y0 = pt
    x1, y1 = start
    x2, y2 = end
    num = abs((y2 - y1) * x0 - (x2 - x1) * y0 + x2 * y1 - y2 * x1)
    return num / math.dist(start, end)


def rdp(points, eps):
    """Iterative Douglas-Peucker. Iterative because some rings have 12k vertices
    and the recursive version blows the stack."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi <= lo + 1:
            continue
        worst, worst_i = 0.0, lo
        for i in range(lo + 1, hi):
            d = perp_distance(points[i], points[lo], points[hi])
            if d > worst:
                worst, worst_i = d, i
        if worst > eps:
            keep[worst_i] = True
            stack.append((lo, worst_i))
            stack.append((worst_i, hi))
    return [p for p, k in zip(points, keep) if k]


def simplify_ring(ring):
    pts = [(round(x, 3), round(y, 3)) for x, y in ring]
    pts = rdp(pts, EPSILON)
    # Collapse consecutive duplicates introduced by the rounding.
    out = [pts[0]]
    for p in pts[1:]:
        if p != out[-1]:
            out.append(p)
    if out[0] != out[-1]:
        out.append(out[0])
    return out if len(out) >= 4 else None


def ring_area_centroid(ring):
    """Signed shoelace area and area-weighted centroid of one ring."""
    a = cx = cy = 0.0
    for i in range(len(ring) - 1):
        x0, y0 = ring[i]
        x1, y1 = ring[i + 1]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a *= 0.5
    if abs(a) < 1e-12:
        return 0.0, ring[0][0], ring[0][1]
    return a, cx / (6 * a), cy / (6 * a)


# --- Agro-ecological metadata -------------------------------------------------
# aridity : 0 = humid highland, 1 = arid pastoral. Drives how fast a failed season
#           pushes the county up the risk ladder.
# crop    : share of the county that is cropped, 0-1. Drives how much a shortage
#           there matters for national supply, and the NDVI signal strength.
# Classification follows Kenya's standard ASAL / high-potential split (the 23 ASAL
# counties that the 2021 national drought disaster declaration covered).
PROFILE = {
    # Arid pastoral north and north-east - the counties that failed first in 2020.
    "Turkana": (0.96, 0.03), "Marsabit": (0.95, 0.04), "Mandera": (0.94, 0.05),
    "Wajir": (0.94, 0.04), "Garissa": (0.92, 0.06), "Isiolo": (0.91, 0.05),
    "Samburu": (0.88, 0.07), "Tana River": (0.85, 0.12), "West Pokot": (0.74, 0.18),
    "Baringo": (0.76, 0.16), "Lamu": (0.70, 0.20),
    # Semi-arid south-east and rift - marginal mixed farming, fails second.
    "Kitui": (0.78, 0.30), "Makueni": (0.74, 0.34), "Machakos": (0.68, 0.38),
    "Kajiado": (0.76, 0.14), "Narok": (0.58, 0.40), "Laikipia": (0.64, 0.24),
    "Taita Taveta": (0.72, 0.18), "Kilifi": (0.66, 0.26), "Kwale": (0.63, 0.28),
    "Embu": (0.50, 0.44), "Tharaka-Nithi": (0.58, 0.40), "Meru": (0.44, 0.50),
    "Nyeri": (0.36, 0.48), "Kirinyaga": (0.32, 0.58), "Murang'a": (0.34, 0.56),
    "Elgeyo-Marakwet": (0.46, 0.38), "Nakuru": (0.42, 0.46), "Nyandarua": (0.30, 0.54),
    # High-potential grain belt and lake basin - the last to turn, and the counties
    # that have to absorb national demand when the ASALs fail.
    "Trans Nzoia": (0.18, 0.72), "Uasin Gishu": (0.22, 0.70), "Nandi": (0.24, 0.62),
    "Bungoma": (0.20, 0.68), "Kakamega": (0.18, 0.66), "Vihiga": (0.20, 0.60),
    "Busia": (0.26, 0.58), "Siaya": (0.32, 0.54), "Kisumu": (0.34, 0.50),
    "Homa Bay": (0.36, 0.52), "Migori": (0.30, 0.56), "Kisii": (0.18, 0.64),
    "Nyamira": (0.18, 0.62), "Bomet": (0.24, 0.58), "Kericho": (0.22, 0.60),
    "Kiambu": (0.30, 0.44), "Nairobi": (0.40, 0.04), "Mombasa": (0.64, 0.03),
}
DEFAULT_PROFILE = (0.5, 0.35)

# Rough county populations (2019 census, millions) - used to size the "people
# affected" figure in the notification feed.
POP = {
    "Nairobi": 4.40, "Kiambu": 2.42, "Nakuru": 2.16, "Kakamega": 1.87, "Bungoma": 1.67,
    "Meru": 1.55, "Kilifi": 1.45, "Machakos": 1.42, "Kisii": 1.27, "Mombasa": 1.21,
    "Uasin Gishu": 1.16, "Mandera": 1.03, "Narok": 1.16, "Kitui": 1.14,
    "Turkana": 0.93, "Murang'a": 1.06, "Trans Nzoia": 0.99, "Homa Bay": 1.13,
    "Migori": 1.12, "Nyeri": 0.76, "Garissa": 0.84, "Makueni": 0.99, "Kwale": 0.87,
    "Siaya": 0.99, "Busia": 0.89, "Wajir": 0.78, "Kisumu": 1.16, "Nandi": 0.89,
    "Bomet": 0.88, "Kericho": 0.90, "Kajiado": 1.12, "Nyamira": 0.61, "Vihiga": 0.59,
    "Baringo": 0.67, "Laikipia": 0.52, "Embu": 0.61, "Kirinyaga": 0.61, "West Pokot": 0.62,
    "Nyandarua": 0.64, "Tharaka-Nithi": 0.39, "Elgeyo-Marakwet": 0.45, "Marsabit": 0.46,
    "Taita Taveta": 0.34, "Samburu": 0.31, "Tana River": 0.32, "Isiolo": 0.27, "Lamu": 0.14,
}

ALIASES = {  # geoBoundaries spellings -> the names used above
    "Muranga": "Murang'a", "Murang’a": "Murang'a",
    "Elgeyo Marakwet": "Elgeyo-Marakwet", "Elgeyo-Marakwet": "Elgeyo-Marakwet",
    "Tharaka Nithi": "Tharaka-Nithi", "Tharaka - Nithi": "Tharaka-Nithi",
    "Tharaka": "Tharaka-Nithi",
    "Taita Taveta": "Taita Taveta", "Taita/Taveta": "Taita Taveta",
    "Trans Nzoia": "Trans Nzoia", "Trans-Nzoia": "Trans Nzoia",
    "Nairobi City": "Nairobi", "Keiyo-Marakwet": "Elgeyo-Marakwet",
}


def main():
    raw = json.load(open("ken_raw.geojson"))
    features = []
    unmatched = []

    for feat in raw["features"]:
        name = feat["properties"]["shapeName"].strip()
        name = ALIASES.get(name, name)
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]

        out_polys, best_area, cx, cy = [], 0.0, 0.0, 0.0
        for poly in polys:
            rings = [r for r in (simplify_ring(ring) for ring in poly) if r]
            if not rings:
                continue

            # Winding. three-globe triangulates the cap on the sphere via
            # three-conic-polygon-geometry, which wants the exterior ring
            # CLOCKWISE - the opposite of the GeoJSON right-hand rule that
            # geoBoundaries ships. Get this backwards and the triangulation
            # takes the complement of the polygon: one county paints the
            # entire globe. Holes take the opposite winding to their shell.
            fixed = []
            for i, ring in enumerate(rings):
                area, _, _ = ring_area_centroid(ring)
                want_negative = (i == 0)          # shell clockwise, holes CCW
                if (area < 0) != want_negative:
                    ring = ring[::-1]
                fixed.append([list(p) for p in ring])
            out_polys.append(fixed)

            area, rcx, rcy = ring_area_centroid(rings[0])
            if abs(area) > best_area:
                best_area, cx, cy = abs(area), rcx, rcy
        if not out_polys:
            continue

        if name not in PROFILE:
            unmatched.append(name)
        aridity, crop = PROFILE.get(name, DEFAULT_PROFILE)

        features.append({
            "type": "Feature",
            "properties": {
                "name": name,
                "iso": feat["properties"].get("shapeISO", ""),
                "lat": round(cy, 3),
                "lng": round(cx, 3),
                "aridity": aridity,
                "crop": crop,
                "pop": POP.get(name, 0.5),
            },
            "geometry": {"type": "MultiPolygon", "coordinates": out_polys},
        })

    features.sort(key=lambda f: f["properties"]["name"])
    fc = {"type": "FeatureCollection", "features": features}

    body = json.dumps(fc, separators=(",", ":"))
    with open("data/kenya-counties.js", "w") as fh:
        fh.write("// Kenya ADM1 (47 counties). Source: geoBoundaries gbOpen KEN ADM1,\n")
        fh.write("// RCMRD / Africa GeoPortal, public domain. Simplified for the browser.\n")
        fh.write("// Generated by prep_data.py - do not edit by hand.\n")
        fh.write("const KENYA_COUNTIES = " + body + ";\n")

    verts = sum(len(r) for f in features for p in f["geometry"]["coordinates"] for r in p)
    print(f"{len(features)} counties, {verts} vertices, {len(body)/1024:.0f} KB")
    if unmatched:
        print("NO PROFILE MATCH (using default):", sorted(unmatched))


if __name__ == "__main__":
    main()
