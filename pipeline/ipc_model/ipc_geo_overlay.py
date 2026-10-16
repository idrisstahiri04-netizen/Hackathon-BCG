"""Area-weighted overlay of FEWS NET IPC classification polygons onto our ADM2 units.

Usage: python pipeline/ipc_model/ipc_geo_overlay.py ZWE KEN MWI MOZ ETH SOM MDG UGA
Inputs : pipeline/data/units_<ISO3>.geojson (unit_id = shapeID), pipeline/data/ipc_<ISO3>.parquet (FDW ipcphase),
         pipeline/cache/ipc_raw/<ISO3>/features_<unit_type>.geojson (FDW feature API, from fetch_ipc_geo.py)
Output : pipeline/data/ipc_units_<ISO3>.parquet, one row per (unit_id, scenario, projection_start, reporting_date):
           share3     area share of the unit (within classified area) in IPC Phase 3+
           share_p2..5 area share in Phase >= p
           phase_w50  worst phase covering >= 50 % of the classified area (= area-weighted median phase)
           phase_w20  worst phase covering >= 20 % of the classified area
           phase_max  worst phase of any piece touching the unit (the old "max over pieces" rule)
           phase_mean area-weighted mean phase
           cover      share of the unit's area covered by classified pieces (rows with cover < MIN_COVER dropped)
           n_pieces   number of FEWS polygons with a value intersecting the unit
         pipeline/ipc_model/out/overlay_<ISO3>.json (coverage report), overlay_weights_<ISO3>.parquet (unit_id, fnid, area_frac).
Rules  : equal-area CRS EPSG:6933; geometries made valid; GeometryCollections reduced to their polygons;
         FEWS pieces of type admin0 / national_park / idp_camp are not used (not population units); the park area
         inside a unit is removed from the unit's area before weighting (Hwange, Hurungwe are mostly park);
         weights are computed per fnid, so every FEWS unit-set version (e.g. ZW2013C3 / ZW2021C3) is handled;
         pieces with a NaN phase do not count towards cover. Area weights, not population (no sub-unit population raster here).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, shape
from shapely.validation import make_valid

HERE = Path(__file__).resolve().parent
PIPE = HERE.parent
DATA = PIPE / "data"
CACHE = PIPE / "cache" / "ipc_raw"
OUT = HERE / "out"
EA_CRS = "EPSG:6933"
MIN_COVER = 0.5
MIN_PIECE_FRAC = 1e-4          # ignore slivers below 0.01 % of the unit area
SKIP_TYPES = {"admin0", "national_park", "idp_camp"}
PHASES = (2, 3, 4, 5)


def polys_only(geom):
    """Keep only the polygon parts of a geometry (drops stray points/lines from GeometryCollections)."""
    if geom is None or geom.is_empty:
        return None
    geom = make_valid(geom)
    if isinstance(geom, (Polygon, MultiPolygon)):
        return geom.buffer(0)
    if isinstance(geom, GeometryCollection):
        parts = [g for g in geom.geoms if isinstance(g, (Polygon, MultiPolygon))]
        flat = []
        for g in parts:
            flat.extend(g.geoms if isinstance(g, MultiPolygon) else [g])
        return MultiPolygon(flat).buffer(0) if flat else None
    return None


def safe_inter_area(a, b) -> float:
    try:
        return a.intersection(b).area
    except Exception:  # noqa: BLE001  (GEOS TopologyException on rare slivers)
        try:
            return a.buffer(0).intersection(b.buffer(0)).area
        except Exception:  # noqa: BLE001
            return a.buffer(1.0).intersection(b.buffer(1.0)).area


def load_units(iso3: str) -> gpd.GeoDataFrame:
    u = gpd.read_file(DATA / f"units_{iso3}.geojson")
    u = u.rename(columns={"shapeID": "unit_id", "shapeName": "unit_name"})[["unit_id", "unit_name", "geometry"]]
    u["geometry"] = u.geometry.map(polys_only)
    u = u.dropna(subset=["geometry"]).set_crs("EPSG:4326", allow_override=True).to_crs(EA_CRS)
    u["unit_area"] = u.geometry.area
    return u


def load_features(iso3: str) -> gpd.GeoDataFrame:
    parts = []
    for f in sorted((CACHE / iso3).glob("features_*.geojson")):
        ut = f.stem[len("features_"):]
        if ut in SKIP_TYPES and ut != "national_park":
            continue
        gj = json.loads(f.read_text())          # pyogrio chokes on the nested "attributes" object -> plain json
        recs = []
        for ft in gj.get("features", []):
            pr = ft.get("properties") or {}
            geom = ft.get("geometry")
            if not pr.get("fnid") or not geom:
                continue
            recs.append({"fnid": str(pr["fnid"]), "full_name": pr.get("full_name"), "unit_type_code": pr.get("unit_type_code"),
                         "start_date": pr.get("start_date"), "end_date": pr.get("end_date"), "unit_type": ut,
                         "geometry": shape(geom)})
        if recs:
            parts.append(gpd.GeoDataFrame(recs, geometry="geometry", crs="EPSG:4326"))
    if not parts:
        raise FileNotFoundError(f"no features_*.geojson for {iso3} in {CACHE / iso3}")
    g = pd.concat(parts, ignore_index=True)
    g = gpd.GeoDataFrame(g, geometry="geometry", crs="EPSG:4326")
    g["geometry"] = g.geometry.map(polys_only)
    g = g.dropna(subset=["geometry"]).drop_duplicates("fnid").to_crs(EA_CRS)
    return g[g.unit_type != "national_park"].copy(), g[g.unit_type == "national_park"].copy()


def exclude_parks(units: gpd.GeoDataFrame, parks: gpd.GeoDataFrame, feats: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """unit_area -> the part of the unit FEWS NET classifies at all: minus national parks/reserves (unpopulated,
    never classified) and minus area outside every FEWS polygon (lakes, e.g. Mangochi / Lago Niassa)."""
    units = units.copy()
    units["park_frac"] = 0.0
    units["outside_frac"] = 0.0
    allg = feats.geometry.union_all()
    outside = units.geometry.map(lambda g: g.area - safe_inter_area(g, allg)) / units.unit_area
    units["outside_frac"] = outside.fillna(0.0).clip(0, 0.98)
    if not parks.empty:
        park = parks.geometry.union_all()
        pf = units.geometry.map(lambda g: safe_inter_area(g, park)) / units.unit_area
        units["park_frac"] = pf.fillna(0.0).clip(0, 0.98)
    units["unit_area"] = units.unit_area * (1 - units.park_frac - units.outside_frac).clip(lower=0.02)
    return units


def weights(units: gpd.GeoDataFrame, feats: gpd.GeoDataFrame) -> pd.DataFrame:
    """(unit_id, fnid, area_frac): share of the unit's area inside each FEWS polygon."""
    cand = gpd.sjoin(units[["unit_id", "unit_area", "geometry"]], feats[["fnid", "geometry"]], how="inner", predicate="intersects")
    fg = feats.set_index("fnid").geometry
    rows = []
    for r in cand.itertuples(index=False):
        a = safe_inter_area(r.geometry, fg[r.fnid])
        frac = a / r.unit_area if r.unit_area > 0 else 0.0
        if frac >= MIN_PIECE_FRAC:
            rows.append((r.unit_id, r.fnid, frac))
    return pd.DataFrame(rows, columns=["unit_id", "fnid", "area_frac"])


def unit_table(ipc: pd.DataFrame, w: pd.DataFrame) -> pd.DataFrame:
    """Aggregate FEWS piece phases to units with area weights, per (scenario, projection_start, reporting_date)."""
    d = ipc[~ipc.unit_type.isin(SKIP_TYPES)].copy()
    d["value"] = pd.to_numeric(d["value"], errors="coerce")
    d = d.dropna(subset=["value"])
    keys = ["fnid", "scenario", "projection_start", "projection_end", "reporting_date"]
    d = d.groupby(keys, as_index=False)["value"].max()          # duplicates = same window re-reported; keep worst
    m = d.merge(w, on="fnid", how="inner")
    m["w3"] = m.area_frac * (m.value >= 3)
    for p in PHASES:
        m[f"w{p}"] = m.area_frac * (m.value >= p)
    m["wv"] = m.area_frac * m.value
    gk = ["unit_id", "scenario", "projection_start", "projection_end", "reporting_date"]
    agg = {"area_frac": "sum", "wv": "sum", "value": "max", "fnid": "nunique", **{f"w{p}": "sum" for p in PHASES}}
    t = m.groupby(gk, as_index=False).agg(agg).rename(columns={"area_frac": "cover", "value": "phase_max", "fnid": "n_pieces"})
    t = t[t.cover >= MIN_COVER].copy()
    for p in PHASES:
        t[f"share_p{p}"] = t[f"w{p}"] / t.cover
    t["share3"] = t["share_p3"]
    t["phase_mean"] = t.wv / t.cover
    def worst(th):
        ph = np.ones(len(t))
        for p in PHASES:
            ph = np.where(t[f"share_p{p}"].values >= th, p, ph)
        return ph
    t["phase_w50"] = worst(0.5)
    t["phase_w20"] = worst(0.2)
    cols = gk + ["phase_w50", "phase_w20", "phase_max", "phase_mean", "share3"] + [f"share_p{p}" for p in PHASES] + ["cover", "n_pieces"]
    return t[cols].sort_values(gk).reset_index(drop=True)


def run(iso3: str) -> dict:
    units = load_units(iso3)
    feats, parks = load_features(iso3)
    units = exclude_parks(units, parks, feats)
    ipc = pd.read_parquet(DATA / f"ipc_{iso3}.parquet")
    w = weights(units, feats)
    # only fnids that carry IPC rows matter for coverage
    used = set(ipc.loc[~ipc.unit_type.isin(SKIP_TYPES), "fnid"].astype(str))
    w_used = w[w.fnid.isin(used)]
    cover_by_unit = w_used.groupby("unit_id").area_frac.sum()        # summed over ALL versions -> can exceed 1
    t = unit_table(ipc, w)
    t.insert(0, "iso3", iso3)
    t.to_parquet(DATA / f"ipc_units_{iso3}.parquet", index=False)
    OUT.mkdir(parents=True, exist_ok=True)
    w.to_parquet(OUT / f"overlay_weights_{iso3}.parquet", index=False)
    cs = t[t.scenario == "CS"]
    per_snap = cs.groupby("projection_start").unit_id.nunique()
    good = per_snap[per_snap >= 0.5 * per_snap.max()] if len(per_snap) else per_snap
    units_cs = cs[cs.projection_start.isin(good.index)].unit_id.nunique()
    names = units.set_index("unit_id").unit_name
    missing = sorted(str(names[u]) for u in units.unit_id if u not in set(cs.unit_id))
    rep = {"iso3": iso3, "our_units": int(len(units)), "units_park_frac_gt_0.3": sorted(str(names[u]) for u in units.loc[units.park_frac > 0.3, "unit_id"]),
           "units_outside_frac_gt_0.3": sorted(str(names[u]) for u in units.loc[units.outside_frac > 0.3, "unit_id"]), "fews_polygons": int(len(feats)),
           "fews_polygons_with_ipc_rows": int(len(used & set(feats.fnid))),
           "units_with_cs_label": int(units_cs), "units_without_cs_label": missing[:30],
           "cs_snapshots": {str(k)[:7]: int(v) for k, v in good.items()},
           "cs_snapshots_dropped_small": {str(k)[:7]: int(v) for k, v in per_snap[~per_snap.index.isin(good.index)].items()},
           "median_cover": round(float(cs.cover.median()), 3) if len(cs) else None,
           "share3_mean_cs": round(float(cs.share3.mean()), 3) if len(cs) else None,
           "frac_units_cs_phase_w50_ge3": round(float((cs.phase_w50 >= 3).mean()), 3) if len(cs) else None,
           "frac_units_cs_phase_w20_ge3": round(float((cs.phase_w20 >= 3).mean()), 3) if len(cs) else None,
           "frac_units_cs_phase_max_ge3": round(float((cs.phase_max >= 3).mean()), 3) if len(cs) else None,
           "rows": int(len(t))}
    (OUT / f"overlay_{iso3}.json").write_text(json.dumps(rep, indent=1, default=str))
    return rep


if __name__ == "__main__":
    for iso3 in (sys.argv[1:] or ["ZWE"]):
        try:
            r = run(iso3)
            print(iso3, json.dumps({k: v for k, v in r.items() if k not in ("cs_snapshots",)}, default=str), flush=True)
        except Exception as e:  # noqa: BLE001
            print(iso3, "ERROR", repr(e), flush=True)
