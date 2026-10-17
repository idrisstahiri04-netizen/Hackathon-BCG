"""
Build the sub-county (ADM2) layer — a 6.2x resolution increase over counties.

Why this is worth doing: FEWS NET already publishes at sub-county x livelihood
zone. Aggregating to county threw away 6,090 observations and kept 987. Kenya
has 290 sub-counties and geoBoundaries ADM2 has exactly 290 units, because both
are the IEBC sub-county division.

Inputs : ken_adm2_raw.geojson   (geoBoundaries gbOpen KEN ADM2, CC BY 3.0 IGO,
                                 source IEBC / OCHA ROSEA)
         data/kenya-counties.js (to assign each sub-county to its parent)
         fews_kenya_ipc_raw.json
Outputs: data/kenya-subcounties.js
         data/fews-ipc-subcounty.json

The join is done WITHIN a county: each ADM2 polygon is first assigned to its
parent county by centroid containment, then matched to a FEWS NET sub-county
name among that county's names only. Matching 290 names globally invites
collisions (there are several "Central" and "North" units); matching ~6 names
inside one county does not.
"""

import collections
import difflib
import json
import math
import os
import re

from prep_data import rdp, ring_area_centroid, EPSILON

ADM2_RAW = "ken_adm2_raw.geojson"
FEWS_RAW = "fews_kenya_ipc_raw.json"
OUT_GEO = "data/kenya-subcounties.js"
OUT_IPC = "data/fews-timeline.json"

PHASE = {"Minimal": 1, "Stressed": 2, "Crisis": 3, "Emergency": 4, "Famine": 5}
START, END = "2019-01", "2025-01"

# geoBoundaries spelling -> FEWS NET spelling. Several are genuine typos in the
# boundary file ("Cental Imenti", "Mukurweni"); the rest are renames.
ALIASES = {
    "buret": "bureti",
    "centalimenti": "centralimenti",
    "mukurweni": "mukurweini",
    "homabay": "homabaytown",
    "subanorth": "mbita",
    "subasouth": "suba",
    # Pre-2013 names still used in the boundary file.
    "dujis": "garissatownship",
    "gachoka": "mbeeresouth",
    "siakago": "mbeerenorth",
}

norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower().replace("'", ""))


def simplify_ring(ring, eps):
    pts = [(round(x, 3), round(y, 3)) for x, y in ring]
    pts = rdp(pts, eps)
    out = [pts[0]]
    for p in pts[1:]:
        if p != out[-1]:
            out.append(p)
    if out[0] != out[-1]:
        out.append(out[0])
    return out if len(out) >= 4 else None


def point_in_ring(pt, ring):
    """Ray casting. Used to find which county a sub-county centroid falls in."""
    x, y = pt
    inside = False
    n = len(ring)
    for i in range(n - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        if (y1 > y) != (y2 > y):
            xin = x1 + (y - y1) / (y2 - y1) * (x2 - x1)
            if x < xin:
                inside = not inside
    return inside


def load_counties():
    with open("data/kenya-counties.js") as fh:
        fc = json.loads(fh.read().split("=", 1)[1].rstrip(";\n"))
    out = []
    for f in fc["features"]:
        rings = [poly[0] for poly in f["geometry"]["coordinates"]]
        out.append((f["properties"]["name"], rings,
                    (f["properties"]["lng"], f["properties"]["lat"])))
    return out


def parent_county(centroid, counties):
    for name, rings, _ in counties:
        if any(point_in_ring(centroid, r) for r in rings):
            return name
    # Centroid fell outside every county (coastline, islands). Nearest centroid.
    return min(counties, key=lambda c: math.dist(centroid, c[2]))[0]


def fews_subcounties():
    """(county, subcounty) -> {month: phase}, plus livelihood zones and
    FEWS NET's own near-term projection (ML1) for the same unit."""
    with open(FEWS_RAW) as fh:
        raw = json.load(fh)
    BASE = re.compile(r"^(.*?\b(?:Zone|Fishing|Farming))\b", re.I)
    phases = collections.defaultdict(dict)
    proj = collections.defaultdict(dict)       # ML1, ~1.5 months ahead
    proj2 = collections.defaultdict(dict)      # ML2, ~5 months ahead
    zones = collections.defaultdict(collections.Counter)
    for r in raw:
        if r.get("unit_type") != "fsc_admin_lhz":
            continue
        sc = r.get("scenario")
        if sc not in ("CS", "ML1", "ML2"):
            continue
        d = r.get("reporting_date")
        v = PHASE.get(r.get("description"))
        if not (d and v) or not (START <= d[:7] < END):
            continue
        p = [x.strip() for x in r["geographic_unit_full_name"].split(",")]
        if len(p) < 4:
            continue
        county, sub = p[-2], p[-3]
        head = ", ".join(p[:-3])
        m = BASE.match(head)
        zone = re.sub(r"\s+", " ", (m.group(1) if m else head).strip())
        key = (county, sub)
        month = d[:7]
        # worst livelihood zone within the sub-county, as at county level
        if sc == "CS":
            phases[key][month] = max(phases[key].get(month, 0), v)
            zones[key][zone] += 1
        elif sc == "ML1":
            # FEWS NET's own near-term projection, issued alongside the
            # current-situation classification. Keep it so the UI can show
            # "they expect this to hold / worsen" without us modelling anything.
            proj[key][month] = max(proj[key].get(month, 0), v)
        else:
            # ML2, the medium-term projection - a real ~5-month forecast.
            proj2[key][month] = max(proj2[key].get(month, 0), v)
    return phases, proj, proj2, zones


def main():
    counties = load_counties()
    phases, projections, projections2, zones = fews_subcounties()

    by_county = collections.defaultdict(list)
    for (c, s) in phases:
        by_county[c].append(s)

    with open(ADM2_RAW) as fh:
        raw = json.load(fh)

    feats, matched, unmatched = [], 0, []
    for f in raw["features"]:
        name = f["properties"]["shapeName"].strip()
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]

        out_polys, best, cx, cy = [], 0.0, 0.0, 0.0
        for poly in polys:
            rings = [r for r in (simplify_ring(ring, EPSILON * 0.6) for ring in poly) if r]
            if not rings:
                continue
            fixed = []
            for i, ring in enumerate(rings):
                area, _, _ = ring_area_centroid(ring)
                # three-globe wants the exterior ring clockwise (see prep_data.py)
                if (area < 0) != (i == 0):
                    ring = ring[::-1]
                fixed.append([list(p) for p in ring])
            out_polys.append(fixed)
            area, rcx, rcy = ring_area_centroid(rings[0])
            if abs(area) > best:
                best, cx, cy = abs(area), rcx, rcy
        if not out_polys:
            continue

        county = parent_county((cx, cy), counties)

        # Match within the parent county only.
        cands = by_county.get(county, [])
        if not cands and county == "Tharaka-Nithi":
            cands = by_county.get("Tharaka", [])
        key = norm(name)
        key = ALIASES.get(key, key)
        hit = next((s for s in cands if norm(s) == key), None)
        if not hit and cands:
            close = difflib.get_close_matches(key, [norm(s) for s in cands], n=1, cutoff=0.78)
            if close:
                hit = next(s for s in cands if norm(s) == close[0])
        if not hit:
            # Border units whose centroid fell in a neighbouring county.
            for c2, names in by_county.items():
                g = next((s2 for s2 in names if norm(s2) == key), None)
                if g:
                    hit, county = g, c2
                    break
        if hit:
            matched += 1
        else:
            unmatched.append(f"{name} ({county})")

        z = [k for k, _ in zones[(county, hit)].most_common()] if hit else []
        feats.append({
            "type": "Feature",
            "properties": {
                "name": name,
                "county": county,
                "fews": hit,
                "zones": z[:3],
                "lat": round(cy, 3),
                "lng": round(cx, 3),
            },
            "geometry": {"type": "MultiPolygon", "coordinates": out_polys},
        })

    feats.sort(key=lambda f: (f["properties"]["county"], f["properties"]["name"]))
    body = json.dumps({"type": "FeatureCollection", "features": feats},
                      separators=(",", ":"))
    os.makedirs("data", exist_ok=True)
    with open(OUT_GEO, "w") as fh:
        fh.write("// Kenya ADM2 (290 sub-counties). geoBoundaries gbOpen KEN ADM2,\n")
        fh.write("// source IEBC / OCHA ROSEA, CC BY 3.0 IGO. Simplified for the browser.\n")
        fh.write("// Generated by prep_adm2.py - do not edit by hand.\n")
        fh.write("const KENYA_SUBCOUNTIES = " + body + ";\n")

    # ---- Timeline, both resolutions, 100% FEWS NET -----------------------
    # Nothing here is modelled or interpolated. Each period is one real FEWS
    # NET publication; a unit simply holds its last classification until the
    # next release, which is how these classifications are read operationally.
    sub, county_roll = {}, collections.defaultdict(lambda: collections.defaultdict(int))
    county_proj = collections.defaultdict(lambda: collections.defaultdict(int))
    county_proj2 = collections.defaultdict(lambda: collections.defaultdict(int))
    for f in feats:
        p_ = f["properties"]
        if not p_["fews"]:
            continue
        key = (p_["county"], p_["fews"])
        ser = phases[key]
        pr = projections.get(key, {})
        pr2 = projections2.get(key, {})
        sub[p_["name"]] = {"county": p_["county"], "zones": p_["zones"],
                           "phases": ser, "proj": pr, "proj2": pr2}
        for m, v in ser.items():
            county_roll[p_["county"]][m] = max(county_roll[p_["county"]][m], v)
        for m, v in pr.items():
            county_proj[p_["county"]][m] = max(county_proj[p_["county"]][m], v)
        for m, v in pr2.items():
            county_proj2[p_["county"]][m] = max(county_proj2[p_["county"]][m], v)

    periods = sorted({m for v in sub.values() for m in v["phases"]})
    out = {
        "meta": {
            "source": "FEWS NET Data Warehouse (fdw.fews.net), IPC phase",
            "scenarios": {
                "phases": "CS - Current Situation (observed, 0-1 months)",
                "proj":   "ML1 - FEWS NET near-term projection (median 1.5 months ahead)",
                "proj2":  "ML2 - FEWS NET medium-term projection (median 5.0 months ahead)",
            },
            "horizons": {"now": 0, "ml1": 1.5, "ml2": 5.0},
            "scale": {1: "Minimal", 2: "Stressed", 3: "Crisis",
                      4: "Emergency", 5: "Famine"},
            "level_map": {1: 0, 2: 1, 3: 2, 4: 3, 5: 3},
            "aggregation": "worst livelihood zone within the unit; counties roll up from sub-counties",
            "note": "No values are simulated, smoothed or interpolated.",
            "n_subcounties": len(sub), "n_counties": len(county_roll),
            "n_periods": len(periods),
        },
        "periods": periods,
        "subcounty": sub,
        "county": {c: {"phases": dict(v),
                       "proj": dict(county_proj.get(c, {})),
                       "proj2": dict(county_proj2.get(c, {}))}
                   for c, v in county_roll.items()},
    }
    with open(OUT_IPC, "w") as fh:
        json.dump(out, fh, separators=(",", ":"), sort_keys=True)

    verts = sum(len(r) for f in feats for p in f["geometry"]["coordinates"] for r in p)
    print(f"{len(feats)} sub-counties, {verts} vertices, {len(body)/1024:.0f} KB")
    print(f"matched to FEWS NET: {matched}/{len(feats)}")
    if unmatched:
        print(f"UNMATCHED ({len(unmatched)}): {unmatched[:12]}")
    nobs = sum(len(v["phases"]) for v in sub.values())
    print(f"timeline: {len(sub)} sub-counties + {len(county_roll)} counties "
          f"x {len(periods)} real FEWS NET periods = {nobs} observations")
    print(f"          {sum(len(v['proj']) for v in sub.values())} ML1 (~1.5mo) "
          f"+ {sum(len(v['proj2']) for v in sub.values())} ML2 (~5mo) projections")
    print(f"          periods {periods[0]} -> {periods[-1]}  (all observed, none interpolated)")
    print(f"wrote {OUT_IPC} ({os.path.getsize(OUT_IPC)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
