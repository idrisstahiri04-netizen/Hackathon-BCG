#!/usr/bin/env python3
"""Dry-spell / season-timing signals from CHIRPS v3 PENTAD, per admin unit and month.

    python pipeline/dryspell/extract_dryspell.py --iso3 ZWE KEN MWI ZMB ...   (default: all 14)

Earth Engine does the heavy part: for every (country, year) the 72 pentad images are stacked as
bands of one image (toBands) and reduced to the unit mean in a single reduceRegions. Raw per-year
results are cached in pipeline/cache/dryspell/<ISO3>/pentad_<year>.json. Everything else is pandas.

Output: pipeline/data/dryspell_<ISO3>.parquet in the CONTRACT section-1 long format
(unit_id, unit_name, iso3, month, signal_type, value). The value for month m is the state at the end
of the LAST pentad of m (so it is "month m data" and gets the normal CHIRPS latency of 1 month).

signal_type (new names, not in the main DYNAMIC list):
  dry_spell_max   longest run of consecutive dry pentads (< 5 mm) since the season's onset, up to the
                  end of m (frozen after the last rainy month). NaN before onset / outside the season.
  days_since_rain pentads since the last pentad with >= 10 mm (0 = the last pentad of m was wet), cap 36.
                  Always defined.
  onset_anom      onset of rains minus its 2001-2020 median for that unit+season, in pentads (+ = late).
                  Onset = first pentad p from the search start (first pentad of the month before the
                  first rainy month) with rain(p)+rain(p+1)+rain(p+2) >= 25 mm. Before the onset has
                  happened the value is censored: (pentads elapsed since search start) - median,
                  i.e. the smallest anomaly still possible. NaN outside search start .. last rainy month + 1.
  season_rain_pct rain from the first pentad of the first rainy month to the end of m (clipped at the
                  end of the rainy season) as % of the 2001-2020 mean of the same partial sum (100 = normal).

Seasons come from common.detect_seasons (per unit, from its own monthly CHIRPS climatology in
signals_<ISO3>.parquet), so the rainy months are the same ones labels/features already use.
Bimodal units get two seasons; a month belongs to the season whose search start is the most recent.
Missing stays NaN.
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
PIPE = HERE.parent
sys.path.insert(0, str(PIPE))
from common import BASE_END, BASE_START, detect_seasons, load_signals  # noqa: E402

EE_PROJECT = "drought-warning-zw-1016"
CHIRPS = "UCSB-CHC/CHIRPS/V3/PENTAD"
BOUNDS = "WM/geoLab/geoBoundaries/600/ADM{adm}"
SCALE = 5566
CACHE = PIPE / "cache" / "dryspell"
DATA = PIPE / "data"
ALL = ["ZWE", "KEN", "MWI", "ZMB", "MOZ", "TZA", "ETH", "SOM", "NAM", "BWA", "ZAF", "MDG", "AGO", "UGA"]

DRY_MM = 5.0        # dry pentad
WET_MM = 10.0       # "rain" pentad for days_since_rain
ONSET_MM = 25.0     # over 3 pentads
CAP_SINCE = 36      # pentads (half a year)
SIGNALS = ["dry_spell_max", "days_since_rain", "onset_anom", "season_rain_pct"]


# ----------------------------------------------------------------------------- Earth Engine
def unit_ids(iso3: str) -> dict:
    g = json.loads((DATA / f"units_{iso3}.geojson").read_text())
    return {f["properties"]["shapeID"]: f["properties"].get("shapeName") for f in g["features"]}


def units_fc(iso3: str, ids: set):
    """geoBoundaries collection at the ADM level whose shapeIDs match units_<ISO3>.geojson."""
    import ee
    for adm in (2, 1):
        fc = ee.FeatureCollection(BOUNDS.format(adm=adm)).filter(ee.Filter.eq("shapeGroup", iso3))
        got = set(fc.aggregate_array("shapeID").getInfo())
        if got == ids:
            return fc, adm
    raise RuntimeError(f"{iso3}: no geoBoundaries ADM level matches units geojson ids")


def pentad_year(fc, y: int, tile_scale: int = 4) -> list[dict]:
    import ee
    col = ee.ImageCollection(CHIRPS).select("precipitation").filter(ee.Filter.calendarRange(y, y, "year"))
    img = col.toBands()                       # bands 'YYYYMMDD_precipitation', 72 per year
    red = img.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=SCALE, tileScale=tile_scale)
    red = red.select(ee.List(["shapeID"]).cat(img.bandNames()), None, False)
    return [f["properties"] for f in red.getInfo()["features"]]


def fetch_year(iso3: str, fc, y: int, retries: int = 4):
    path = CACHE / iso3 / f"pentad_{y}.json"
    if path.exists():
        return y, json.loads(path.read_text()), True
    last = None
    for attempt in range(retries):
        try:
            recs = pentad_year(fc, y, tile_scale=4 if attempt < 2 else 16)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(recs))
            tmp.rename(path)
            return y, recs, False
        except Exception as exc:  # noqa: BLE001  EE timeouts / quota
            last = exc
            wait = 10 * (attempt + 1)
            print(f"  ! {iso3} {y} attempt {attempt + 1}: {str(exc)[:140]} (retry in {wait}s)", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"{iso3} {y} failed: {last}")


def pentad_frame(recs_by_year: dict, units: list) -> pd.DataFrame:
    """-> DataFrame index = pentad start date, columns = unit_id, values mm per pentad."""
    rows = {}
    for y, recs in recs_by_year.items():
        for r in recs:
            uid = r["shapeID"]
            for k, v in r.items():
                if k == "shapeID":
                    continue
                d = pd.Timestamp(k.split("_")[0])
                rows.setdefault(d, {})[uid] = np.nan if v is None else float(v)
    df = pd.DataFrame.from_dict(rows, orient="index").sort_index().reindex(columns=units)
    return df


# ----------------------------------------------------------------------------- pandas maths
def max_run(b: np.ndarray) -> float:
    """Longest run of True in a boolean array."""
    if b.size == 0:
        return np.nan
    idx = np.flatnonzero(np.concatenate(([True], ~b, [True])))
    return float((np.diff(idx) - 1).max())


def unit_features(p: np.ndarray, pdates: pd.DatetimeIndex, seasons, months: pd.DatetimeIndex) -> pd.DataFrame:
    """p: pentad rain for one unit (aligned to pdates). Returns DataFrame index=months, columns=SIGNALS."""
    n = len(p)
    # month index of every pentad relative to the first pentad's month
    pm = (pdates.year - pdates[0].year) * 12 + (pdates.month - pdates[0].month)
    first_of_month = {}          # absolute month number -> first pentad index
    last_of_month = {}
    for i, m in enumerate(pm):
        first_of_month.setdefault(int(m), i)
        last_of_month[int(m)] = i
    m0y, m0m = pdates[0].year, pdates[0].month

    def abs_month(ts: pd.Timestamp) -> int:
        return (ts.year - m0y) * 12 + (ts.month - m0m)

    # days_since_rain: pentads since last >= WET_MM, evaluated at the last pentad of each month
    since = np.full(n, np.nan)
    k = np.nan
    for i in range(n):
        if np.isnan(p[i]):
            since[i] = k
            continue
        k = 0.0 if p[i] >= WET_MM else (k + 1.0 if not np.isnan(k) else np.nan)
        since[i] = k

    # season instances: (season idx, S abs month, search start month, E abs month)
    inst = []
    y_first, y_last = pdates[0].year, pdates[-1].year
    for s in seasons:
        S, E = s.rainy[0], s.rainy[-1]
        span = (E - S) % 12                       # months from S to E
        for y in range(y_first - 1, y_last + 2):
            Sa = abs_month(pd.Timestamp(y, S, 1))
            inst.append(dict(idx=s.idx, year=y, S=Sa, start=Sa - 1, E=Sa + span))
    inst = [d for d in inst if d["start"] in first_of_month and d["S"] in first_of_month]
    for d in inst:
        i0 = first_of_month[d["start"]]
        ps = first_of_month[d["S"]]
        pe = last_of_month.get(d["E"], n - 1)
        d["i0"], d["ps"], d["pe"] = i0, ps, pe
        # onset: first pentad from i0 (<= pe) with 3-pentad sum >= ONSET_MM
        onset = None
        for q in range(i0, min(pe, n - 3) + 1):
            s3 = p[q] + p[q + 1] + p[q + 2]
            if not np.isnan(s3) and s3 >= ONSET_MM:
                onset = q
                break
        d["onset"] = onset
        d["onset_off"] = (onset - i0) if onset is not None else (pe - i0 + 1)   # censored at season end
        d["complete"] = d["E"] in last_of_month

    # climatology 2001-2020 by season idx: onset median, partial-sum mean per month offset k (0..span)
    clim_onset, clim_cum = {}, {}
    for s in seasons:
        ins = [d for d in inst if d["idx"] == s.idx and BASE_START <= d["year"] <= BASE_END and d["complete"]]
        clim_onset[s.idx] = float(np.median([d["onset_off"] for d in ins])) if ins else np.nan
        span = (s.rainy[-1] - s.rainy[0]) % 12
        cum = np.full((len(ins), span + 2), np.nan)
        for j, d in enumerate(ins):
            for kk in range(span + 2):
                q = min(last_of_month.get(d["S"] + kk, d["pe"]), d["pe"])
                seg = p[d["ps"]:q + 1]
                cum[j, kk] = np.nansum(seg) if np.isfinite(seg).any() else np.nan
        clim_cum[s.idx] = np.nanmean(cum, axis=0) if len(ins) else np.full(span + 2, np.nan)

    starts = np.array([d["start"] for d in inst])
    out = np.full((len(months), len(SIGNALS)), np.nan)
    for mi, ts in enumerate(months):
        am = abs_month(ts)
        if am not in last_of_month:
            continue
        q = last_of_month[am]
        out[mi, 1] = min(since[q], CAP_SINCE) if not np.isnan(since[q]) else np.nan
        cand = np.flatnonzero(starts <= am)
        if cand.size == 0:
            continue
        d = inst[cand[np.argmax(starts[cand])]]
        if am > d["E"] + 1:
            continue                               # dry season: timing signals are stale -> missing
        qe = min(q, d["pe"])
        # onset anomaly (censored before onset)
        co = clim_onset.get(d["idx"], np.nan)
        if not np.isnan(co):
            if d["onset"] is not None and d["onset"] <= q:
                out[mi, 2] = d["onset_off"] - co
            else:
                out[mi, 2] = (qe - d["i0"] + 1) - co
        if am >= d["S"]:
            kk = am - d["S"]
            cc = clim_cum.get(d["idx"])
            seg = p[d["ps"]:qe + 1]
            if cc is not None and kk < len(cc) and np.isfinite(cc[kk]) and cc[kk] > 0 and np.isfinite(seg).any():
                out[mi, 3] = 100.0 * np.nansum(seg) / cc[kk]
            if d["onset"] is not None and d["onset"] <= q:
                seg = p[d["onset"]:qe + 1]
                ok = ~np.isnan(seg)
                if ok.any():
                    out[mi, 0] = max_run(seg[ok] < DRY_MM)
    return pd.DataFrame(out, index=months, columns=SIGNALS)


def build_country(iso3: str, start: int, end: int, workers: int) -> pd.DataFrame:
    import ee
    t0 = time.time()
    names = unit_ids(iso3)
    units = sorted(names)
    fc, adm = units_fc(iso3, set(units))
    print(f"{iso3}: {len(units)} units (ADM{adm})", flush=True)
    recs = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(fetch_year, iso3, fc, y) for y in range(start - 1, end + 1)]
        for fu in as_completed(futs):
            y, r, cached = fu.result()
            recs[y] = r
    print(f"  {iso3}: pentads fetched ({time.time() - t0:.0f}s)", flush=True)
    pent = pentad_frame(recs, units)
    sig = load_signals(iso3)
    precip = sig[sig.signal_type == "precip_mm"].pivot_table(index="month", columns="unit_id", values="value")
    months = pd.date_range(f"{start}-01-01", f"{end}-12-01", freq="MS")
    parts = []
    for u in units:
        if u not in precip.columns or precip[u].notna().sum() < 36:
            print(f"  ! {iso3} {u}: no monthly precip for season detection, skipped", flush=True)
            continue
        ss = detect_seasons(precip[u])
        f = unit_features(pent[u].to_numpy(dtype=float), pent.index, ss, months)
        f = f.reset_index().rename(columns={"index": "month"}).melt(id_vars="month", var_name="signal_type", value_name="value")
        f["unit_id"], f["unit_name"], f["iso3"] = u, names[u], iso3
        parts.append(f)
    out = pd.concat(parts, ignore_index=True)[["unit_id", "unit_name", "iso3", "month", "signal_type", "value"]]
    out["month"] = out["month"].dt.strftime("%Y-%m-01")
    path = DATA / f"dryspell_{iso3}.parquet"
    out.to_parquet(path, index=False)
    cov = out.groupby("signal_type").value.apply(lambda s: round(100 * s.notna().mean(), 1)).to_dict()
    print(f"  {iso3}: wrote {path.name} rows={len(out)} non-NaN%={cov} ({time.time() - t0:.0f}s)", flush=True)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--iso3", nargs="*", default=ALL)
    ap.add_argument("--start", type=int, default=2001)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--workers", type=int, default=6, help="EE requests in flight per country")
    ap.add_argument("--countries-parallel", type=int, default=2)
    a = ap.parse_args()
    import ee
    ee.Initialize(project=EE_PROJECT)
    iso3s = [i.upper() for i in a.iso3]
    with ThreadPoolExecutor(max_workers=a.countries_parallel) as pool:
        futs = {pool.submit(build_country, i, a.start, a.end, a.workers): i for i in iso3s}
        for fu in as_completed(futs):
            try:
                fu.result()
            except Exception as exc:  # noqa: BLE001
                print(f"!! {futs[fu]} failed: {exc}", flush=True)


if __name__ == "__main__":
    main()
