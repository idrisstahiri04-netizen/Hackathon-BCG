#!/usr/bin/env python3
"""Seasonal precipitation forecasts per admin unit from the NMME archive (IRI Data Library).

Why: satellite signals only confirm a drought once it is under way. Seasonal forecasts issued
Sep-Nov for the Dec-Feb rains are weather data that exist months before the harvest fails and
can make the warning proactive.

Product: North American Multi-Model Ensemble (NMME), monthly mean precipitation (mm/day) at 1 deg,
served by the IRI Data Library (no login needed for the Ingrid `data.nc` subset route; the DODS
binary route and the HTML browser require a free IRI account). Three models together cover
2001-01 .. 2024-06 with hindcasts (retrospective forecasts made with the frozen operational system)
plus real-time forecasts:

    model          hindcast S             forecast S             members (hind/fc)  leads
    CanSIPS-IC3    1980-01 .. 2021-11     2021-10 .. 2024-06     20 / 20            0.5..11.5
    GFDL-SPEAR     1991-01 .. 2020-12     2020-12 .. 2026-10     15 / 30            0.5..11.5
    NASA-GEOSS2S   1981-02 .. 2017-01     2017-02 .. 2026-10      4 / 10            0.5..8.5

Each model is standardised against ITS OWN hindcast climatology (1991-2020 where available,
per unit, per calendar start month, per target window, leave-one-year-out inside the climatology
window). The multi-model product "MME3" is the mean of the per-model z-scores; p_below_normal is
the pooled fraction of members below the model's own lower tercile.

Conventions
- S = forecast start month ("issue_month", first of month). NMME real-time forecasts are released
  around the 8th-10th of S, so a risk run at the end of month S may use the S forecast.
- target_window "m1-3" = months S+1..S+3 (leads 1.5, 2.5, 3.5); "m4-6" = S+4..S+6 (leads 4.5..6.5).
  Month S itself is excluded (it is already partly observed when the forecast is used).
- Unit aggregation: area-weighted (cos-lat) mean of the 1 deg cells overlapping each unit polygon.
- Missing data stays NaN. Nothing is filled with 0.

Output: pipeline/data/seasonal_fc_<ISO3>.parquet
    unit_id, issue_month, target_window, anom_z, p_below_normal, product, n_members

Usage:
    python pipeline/seasonal_forecast.py fetch                       # download/refresh raw NetCDF chunks
    python pipeline/seasonal_forecast.py build --iso3 ZWE ZMB MWI KEN
    python pipeline/seasonal_forecast.py sanity                      # Zimbabwe DJF checks (2023 vs 2016)
Raw chunks are cached in pipeline/cache/nmme/<model>/ with a _meta.json (url, fetched_at, sha256).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pandas as pd
import requests
import xarray as xr
from shapely.geometry import box, shape
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache" / "nmme"
OUT = HERE / "data"

IRI = "https://iridl.ldeo.columbia.edu/SOURCES/.Models/.NMME"
LICENCE = ("NMME output is distributed freely by NOAA/NCEP, IRI and the modelling centres for "
           "research and operational use; see https://www.cpc.ncep.noaa.gov/products/NMME/ and "
           "IRI Data Library terms https://iridl.ldeo.columbia.edu/dochelp/Documentation/")

# Region covering ZWE, ZMB, MWI, KEN (1 deg cell centres).
X0, X1, Y0, Y1 = 20, 45, -30, 6
LEADS = (0.5, 6.5)          # months; L=0.5 is month S itself
CHUNK_MONTHS = 24
FIRST_S = "1991-01"         # start of climatology window
LAST_S = "2024-06"          # last issue month we need
CLIM = (1991, 2020)         # climatology years (per model: intersected with hindcast availability)

# model -> {kind: (first S, last S)}; verified from the IRI DL coordinate arrays on 2026-10-16.
MODELS = {
    "CanSIPS-IC3": {"HINDCAST": ("1980-01", "2021-11"), "FORECAST": ("2021-10", "2024-06")},
    "GFDL-SPEAR": {"HINDCAST": ("1991-01", "2020-12"), "FORECAST": ("2020-12", "2026-10")},
    "NASA-GEOSS2S": {"HINDCAST": ("1981-02", "2017-01"), "FORECAST": ("2017-02", "2026-10")},
}
WINDOWS = {"m1-3": [1.5, 2.5, 3.5], "m4-6": [4.5, 5.5, 6.5]}
MME = "NMME/MME3"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ------------------------------------------------------------------ helpers
def ym_to_s(ym: str) -> int:
    """'2001-01' -> IRI S value (months since 1960-01-01)."""
    y, m = map(int, ym.split("-"))
    return (y - 1960) * 12 + (m - 1)


def s_to_ts(s) -> pd.Timestamp:
    s = int(round(float(s)))
    return pd.Timestamp(year=1960 + s // 12, month=s % 12 + 1, day=1)


def ingrid_month(ym: str) -> str:
    y, m = map(int, ym.split("-"))
    return f"{MONTHS[m - 1]} {y}"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def month_chunks(first: str, last: str, step: int):
    """Yield (ym_start, ym_end) inclusive chunks of `step` months."""
    a = pd.Period(first, "M")
    end = pd.Period(last, "M")
    while a <= end:
        b = min(a + step - 1, end)
        yield str(a), str(b)
        a = b + 1


# ------------------------------------------------------------------ fetch
def chunk_url(model: str, kind: str, ym0: str, ym1: str) -> str:
    sel = (f"/X/({X0})/({X1})/RANGEEDGES/Y/({Y0})/({Y1})/RANGEEDGES"
           f"/L/({LEADS[0]})/({LEADS[1]})/RANGEEDGES"
           f"/S/({ingrid_month(ym0)})/({ingrid_month(ym1)})/RANGEEDGES/data.nc")
    return f"{IRI}/.{model}/.{kind}/.MONTHLY/.prec" + quote(sel, safe="/()")


def chunk_path(model: str, kind: str, ym0: str, ym1: str) -> Path:
    return CACHE / model / f"{kind}_{ym0}_{ym1}.nc"


def valid_nc(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 1000:
        return False
    try:
        with xr.open_dataset(path, decode_times=False) as ds:
            return "prec" in ds and ds.sizes.get("S", 0) > 0
    except Exception:
        return False


def fetch_chunk(model: str, kind: str, ym0: str, ym1: str, retries: int = 4) -> tuple[str, bool]:
    path = chunk_path(model, kind, ym0, ym1)
    if valid_nc(path):
        return f"{model} {kind} {ym0}..{ym1}: cached", True
    path.parent.mkdir(parents=True, exist_ok=True)
    url = chunk_url(model, kind, ym0, ym1)
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=900, stream=True)
            ctype = r.headers.get("content-type", "")
            if r.status_code != 200 or "netcdf" not in ctype:
                body = r.content[:200].decode("utf-8", "replace")
                raise RuntimeError(f"HTTP {r.status_code} {ctype} {body!r}")
            tmp = path.with_suffix(".part")
            with open(tmp, "wb") as f:
                for blk in r.iter_content(1 << 20):
                    f.write(blk)
            tmp.rename(path)
            if not valid_nc(path):
                path.unlink(missing_ok=True)
                raise RuntimeError("downloaded file is not a readable NetCDF")
            meta = {"url": url, "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "sha256": sha256_of(path), "bytes": path.stat().st_size,
                    "licence": LICENCE, "product": f"NMME/{model}/{kind}", "variable": "prec (mm/day)"}
            path.with_name(path.stem + "_meta.json").write_text(json.dumps(meta, indent=2))
            return f"{model} {kind} {ym0}..{ym1}: fetched {meta['bytes'] / 1e6:.1f} MB", True
        except Exception as e:  # noqa: BLE001
            wait = 20 * (attempt + 1)
            print(f"  retry {attempt + 1} {model} {kind} {ym0}..{ym1}: {e} (sleep {wait}s)", flush=True)
            time.sleep(wait)
    return f"{model} {kind} {ym0}..{ym1}: FAILED", False


def needed_chunks():
    """Chunks for S in [FIRST_S, LAST_S], clipped to each model/kind availability."""
    jobs = []
    for model, kinds in MODELS.items():
        for kind, (a, b) in kinds.items():
            first = max(pd.Period(a, "M"), pd.Period(FIRST_S, "M"))
            last = min(pd.Period(b, "M"), pd.Period(LAST_S, "M"))
            if first > last:
                continue
            for ym0, ym1 in month_chunks(str(first), str(last), CHUNK_MONTHS):
                jobs.append((model, kind, ym0, ym1))
    return jobs


def cmd_fetch(workers: int):
    jobs = needed_chunks()
    print(f"{len(jobs)} chunks, {workers} workers", flush=True)
    ok = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(fetch_chunk, *j) for j in jobs]
        for f in as_completed(futs):
            msg, good = f.result()
            ok += good
            print(msg, flush=True)
    print(f"done: {ok}/{len(jobs)} ok")
    return ok == len(jobs)


# ------------------------------------------------------------------ units -> grid weights
def polygon_of(geom: dict):
    g = shape(geom)
    if g.geom_type == "GeometryCollection":
        parts = [p for p in g.geoms if p.geom_type in ("Polygon", "MultiPolygon")]
        g = unary_union(parts) if parts else None
    return g


def load_units(iso3: str) -> list[tuple[str, str, object]]:
    fc = json.loads((OUT / f"units_{iso3}.geojson").read_text())
    units = []
    for f in fc["features"]:
        g = polygon_of(f["geometry"])
        if g is None or g.is_empty:
            print(f"  WARNING unit {f['properties']['shapeID']} has no polygon geometry", flush=True)
            continue
        units.append((f["properties"]["shapeID"], f["properties"]["shapeName"], g))
    return units


def unit_weights(units, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """Weights [n_units, n_y, n_x]: overlap area (deg^2 * cos lat) of unit with each 1 deg cell."""
    w = np.zeros((len(units), len(ys), len(xs)), dtype=np.float64)
    for ui, (_, _, g) in enumerate(units):
        minx, miny, maxx, maxy = g.bounds
        for yi, y in enumerate(ys):
            if y + 0.5 < miny or y - 0.5 > maxy:
                continue
            for xi, x in enumerate(xs):
                if x + 0.5 < minx or x - 0.5 > maxx:
                    continue
                a = g.intersection(box(x - 0.5, y - 0.5, x + 0.5, y + 0.5)).area
                if a > 0:
                    w[ui, yi, xi] = a * np.cos(np.deg2rad(y))
    return w


# ------------------------------------------------------------------ load + aggregate
def model_series(model: str, weights: np.ndarray, xs: np.ndarray, ys: np.ndarray):
    """Return S values [nS], kinds [nS] ("HINDCAST"/"FORECAST"), prec_unit [nS, nM, nL, nU], leads."""
    n_u = weights.shape[0]
    w_flat = weights.reshape(n_u, -1)                      # [U, YX]
    per_s: dict[int, tuple[str, np.ndarray]] = {}
    leads = None
    chunks = sorted((CACHE / model).glob("*.nc"))
    for path in chunks:
        kind = path.name.split("_")[0]
        with xr.open_dataset(path, decode_times=False) as ds:
            ds = ds.transpose("S", "M", "L", "Y", "X")
            assert np.allclose(ds.X.values, xs) and np.allclose(ds.Y.values, ys), path
            if leads is None:
                leads = ds.L.values.astype(float)
            else:
                assert np.allclose(ds.L.values, leads), path
            arr = ds["prec"].values.astype(np.float32)   # [S, M, L, Y, X]
            s_vals = ds.S.values
        ok = np.isfinite(arr)
        arr0 = np.where(ok, arr, 0.0).reshape(*arr.shape[:3], -1)        # [S,M,L,YX]
        okf = ok.reshape(*arr.shape[:3], -1).astype(np.float32)
        num = arr0 @ w_flat.T.astype(np.float32)                        # [S,M,L,U]
        den = okf @ w_flat.T.astype(np.float32)
        tot = w_flat.sum(axis=1).astype(np.float32)
        # require >= 50 % of the unit's area covered by valid cells, else NaN
        unit = np.where(den >= 0.5 * tot, num / np.where(den > 0, den, np.nan), np.nan)
        for i, s in enumerate(s_vals):
            s = int(round(float(s)))
            prev = per_s.get(s)
            # real-time FORECAST wins over HINDCAST where both exist
            if prev is None or (kind == "FORECAST" and prev[0] == "HINDCAST"):
                per_s[s] = (kind, unit[i])
    if not per_s:
        raise FileNotFoundError(f"no cached chunks for {model} in {CACHE / model}; run `fetch` first")
    s_sorted = sorted(per_s)
    n_m = max(v.shape[0] for _, v in per_s.values())
    out = np.full((len(s_sorted), n_m, len(leads), n_u), np.nan, dtype=np.float32)
    kinds = []
    for i, s in enumerate(s_sorted):
        kind, v = per_s[s]
        out[i, : v.shape[0]] = v                             # fewer members -> NaN padding
        kinds.append(kind)
    return np.array(s_sorted), np.array(kinds), out, leads


def window_mean(prec: np.ndarray, leads: np.ndarray, lead_list) -> np.ndarray:
    idx = [int(np.argmin(np.abs(leads - L))) for L in lead_list]
    assert all(abs(leads[i] - L) < 1e-3 for i, L in zip(idx, lead_list)), (leads, lead_list)
    return prec[:, :, idx, :].mean(axis=2)                  # [S, M, U] (NaN if any lead NaN)


def standardise(s_vals: np.ndarray, kinds: np.ndarray, wm: np.ndarray):
    """Per S: z of ensemble mean and fraction of members below the lower tercile, using the
    model's own HINDCAST starts with the same calendar month inside CLIM (leave-one-year-out).
    wm: [S, M, U] window-mean precip. Returns z [S, U], p_below [S, U], n_members [S]."""
    ts = pd.DatetimeIndex([s_to_ts(s) for s in s_vals])
    years, months = ts.year.values, ts.month.values
    em = np.nanmean(wm, axis=1)                              # [S, U] ensemble mean
    n_mem = np.isfinite(wm).any(axis=2).sum(axis=1)          # [S]
    z = np.full(em.shape, np.nan, dtype=np.float32)
    pb = np.full(em.shape, np.nan, dtype=np.float32)
    for m in range(1, 13):
        same = np.where(months == m)[0]
        clim = np.array([i for i in same
                         if kinds[i] == "HINDCAST" and CLIM[0] <= years[i] <= CLIM[1]])
        if len(clim) < 10:
            print(f"  WARNING only {len(clim)} climatology years for start month {m}", flush=True)
            continue
        for i in same:
            ref = clim[clim != i]
            ref_em = em[ref]                                 # [n, U]
            mu = np.nanmean(ref_em, axis=0)
            sd = np.nanstd(ref_em, axis=0, ddof=1)
            with np.errstate(invalid="ignore", divide="ignore"):
                z[i] = (em[i] - mu) / np.where(sd > 0, sd, np.nan)
            pooled = wm[ref].reshape(-1, wm.shape[2])         # [n*M, U] members pooled
            q33 = np.nanpercentile(pooled, 100 / 3, axis=0)
            mem = wm[i]                                      # [M, U]
            valid = np.isfinite(mem)
            below = (mem < q33) & valid
            nv = valid.sum(axis=0)
            with np.errstate(invalid="ignore", divide="ignore"):
                pb[i] = np.where(nv > 0, below.sum(axis=0) / nv, np.nan)
    return z, pb, n_mem


def build_iso3(iso3: str, extra_windows: dict | None = None) -> pd.DataFrame:
    units = load_units(iso3)
    # grid coordinates from any cached chunk
    any_chunk = next(iter(sorted(CACHE.glob("*/*.nc"))), None)
    if any_chunk is None:
        raise FileNotFoundError("no cached NMME chunks; run `fetch` first")
    with xr.open_dataset(any_chunk, decode_times=False) as ds:
        xs, ys = ds.X.values.astype(float), ds.Y.values.astype(float)
    weights = unit_weights(units, xs, ys)
    covered = weights.sum(axis=(1, 2)) > 0
    if not covered.all():
        print(f"  WARNING {(~covered).sum()} units have no grid overlap", flush=True)
    windows = dict(WINDOWS)
    if extra_windows:
        windows.update(extra_windows)

    rows = []
    per_model = {}
    for model in MODELS:
        s_vals, kinds, prec, leads = model_series(model, weights, xs, ys)
        keep = (s_vals >= ym_to_s("2001-01")) & (s_vals <= ym_to_s(LAST_S))
        ts = pd.DatetimeIndex([s_to_ts(s) for s in s_vals])
        for win, lead_list in windows.items():
            wm = window_mean(prec, leads, lead_list)
            z, pb, n_mem = standardise(s_vals, kinds, wm)
            per_model[(model, win)] = (ts[keep], z[keep], pb[keep], n_mem[keep])
            for si in np.where(keep)[0]:
                for ui, (uid, _, _) in enumerate(units):
                    rows.append((uid, ts[si], win, z[si, ui], pb[si, ui], f"NMME/{model}", int(n_mem[si])))
    df = pd.DataFrame(rows, columns=["unit_id", "issue_month", "target_window", "anom_z",
                                     "p_below_normal", "product", "n_members"])

    # multi-model: mean z over models with data; pooled member fraction below the lower tercile
    single = df[df["product"] != MME].copy()
    single["n_below"] = single["p_below_normal"] * single["n_members"]
    single.loc[single["p_below_normal"].isna(), "n_members"] = 0
    g = single.groupby(["unit_id", "issue_month", "target_window"], sort=False)
    mme = g.agg(anom_z=("anom_z", "mean"), n_below=("n_below", "sum"),
                n_members=("n_members", "sum"), n_models=("anom_z", "count")).reset_index()
    with np.errstate(invalid="ignore", divide="ignore"):
        mme["p_below_normal"] = np.where(mme["n_members"] > 0, mme["n_below"] / mme["n_members"], np.nan)
    mme.loc[mme["n_models"] == 0, "anom_z"] = np.nan
    mme["product"] = MME
    mme = mme[["unit_id", "issue_month", "target_window", "anom_z", "p_below_normal", "product", "n_members"]]
    out = pd.concat([df, mme], ignore_index=True)
    out["issue_month"] = pd.to_datetime(out["issue_month"])
    out["anom_z"] = out["anom_z"].astype("float32")
    out["p_below_normal"] = out["p_below_normal"].astype("float32")
    out["n_members"] = out["n_members"].astype("int16")
    return out.sort_values(["product", "target_window", "unit_id", "issue_month"]).reset_index(drop=True)


def cmd_build(iso3s: list[str]):
    for iso3 in iso3s:
        t0 = time.time()
        df = build_iso3(iso3)
        path = OUT / f"seasonal_fc_{iso3}.parquet"
        df.to_parquet(path, index=False)
        n_units = df["unit_id"].nunique()
        print(f"{iso3}: {len(df)} rows, {n_units} units, issue {df.issue_month.min().date()}..{df.issue_month.max().date()}, "
              f"products {sorted(df['product'].unique())}, NaN z {df.anom_z.isna().mean():.1%}, {time.time() - t0:.0f}s -> {path}")


# ------------------------------------------------------------------ sanity
def cmd_sanity():
    """Zimbabwe DJF forecasts issued Sep/Oct/Nov 2023 (El Nino drought, should be dry) vs Nov 2016 (wet)."""
    # DJF relative to issue month: Sep -> leads 3.5,4.5,5.5 ; Oct -> 2.5..4.5 ; Nov -> 1.5..3.5
    djf = {"djf_from_sep": [3.5, 4.5, 5.5], "djf_from_oct": [2.5, 3.5, 4.5], "djf_from_nov": [1.5, 2.5, 3.5]}
    df = build_iso3("ZWE", extra_windows=djf)
    units = load_units("ZWE")
    lat = {uid: g.centroid.y for uid, _, g in units}
    name = {uid: nm for uid, nm, _ in units}
    df["lat"] = df["unit_id"].map(lat)
    df["region"] = np.where(df["lat"] > -18.0, "north", np.where(df["lat"] < -20.0, "south", "centre"))
    n_n, n_s = (df.drop_duplicates("unit_id").region == "north").sum(), (df.drop_duplicates("unit_id").region == "south").sum()
    print(f"\nZimbabwe units: north (centroid lat > -18) n={n_n}, south (lat < -20) n={n_s}")
    print("Example north:", sorted({name[u] for u in df[df.region == 'north'].unit_id})[:6])
    print("Example south:", sorted({name[u] for u in df[df.region == 'south'].unit_id})[:6])
    cases = [("2023-09-01", "djf_from_sep"), ("2023-10-01", "djf_from_oct"), ("2023-11-01", "djf_from_nov"),
             ("2016-09-01", "djf_from_sep"), ("2016-10-01", "djf_from_oct"), ("2016-11-01", "djf_from_nov"),
             ("2015-11-01", "djf_from_nov")]
    rows = []
    for issue, win in cases:
        sub = df[(df.issue_month == issue) & (df.target_window == win) & (df.region != "centre")]
        g = sub.groupby(["product", "region"]).agg(anom_z=("anom_z", "mean"), p_below=("p_below_normal", "mean"),
                                                   n_members=("n_members", "first"), n_units=("unit_id", "nunique"))
        g["issue"] = issue[:7]
        g["target"] = "DJF " + issue[:4] + "/" + str(int(issue[:4]) + 1)[2:]
        rows.append(g.reset_index())
    tab = pd.concat(rows)[["issue", "target", "product", "region", "anom_z", "p_below", "n_members", "n_units"]]
    pd.set_option("display.width", 160)
    print("\nDJF rainfall forecast, mean over units (anom_z: standardised ensemble-mean anomaly vs model hindcast "
          "climatology; p_below: fraction of members below lower tercile):")
    print(tab.to_string(index=False, float_format=lambda v: f"{v:+.2f}"))
    # Also the standard windows for the MME in Sep-Nov 2023
    std = df[(df["product"] == MME) & df.target_window.isin(WINDOWS) & df.issue_month.isin(
        pd.to_datetime(["2023-09-01", "2023-10-01", "2023-11-01", "2016-11-01"])) & (df.region != "centre")]
    g = std.groupby(["issue_month", "target_window", "region"]).agg(anom_z=("anom_z", "mean"), p_below=("p_below_normal", "mean"))
    print("\nStandard windows (MME3), Zimbabwe north/south means:")
    print(g.to_string(float_format=lambda v: f"{v:+.2f}"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--workers", type=int, default=4)
    b = sub.add_parser("build")
    b.add_argument("--iso3", nargs="+", default=["ZWE", "ZMB", "MWI", "KEN"])
    sub.add_parser("sanity")
    a = ap.parse_args()
    if a.cmd == "fetch":
        sys.exit(0 if cmd_fetch(a.workers) else 1)
    elif a.cmd == "build":
        cmd_build(a.iso3)
    elif a.cmd == "sanity":
        cmd_sanity()


if __name__ == "__main__":
    main()
