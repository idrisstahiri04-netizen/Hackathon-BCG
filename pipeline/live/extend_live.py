#!/usr/bin/env python3
"""Extend the signal tables to the latest complete month ("LIVE") without touching history.

    python pipeline/live/extend_live.py --step all --iso3 ZWE KEN MWI ZMB [--end 2026]

Wraps the existing extractors (they keep their per-year cache, so only the new years hit
Earth Engine / IRI) and then post-processes:
  signals   extract_signals.main(--end YEAR)  -> mask months a source has not finished, truncate
            to the last month any source has, verify months <= old end are bit-identical.
  dryspell  dryspell/extract_dryspell.build_country(... end=YEAR) with incomplete new months'
            pentads dropped before the maths; same verification + truncation.
  seasonal  seasonal_forecast with LAST_S moved to the latest NMME issue month; extra FORECAST
            chunks only (2024-07 ..), old issue months verified identical.

Month completeness (data-driven, from the Earth Engine collections themselves):
  chirps  6 pentads present in the month
  modis   a MOD13Q1 composite starting in the month's last 16 days exists (the one covering month end)
  era5    the monthly image exists
Baselines (2001-2020) are untouched; derived anomalies stay comparable. Missing stays NaN.
Writes pipeline/live/live_status.json for LIVE.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PIPE = HERE.parent
DATA = PIPE / "data"
STATUS = HERE / "live_status.json"
sys.path.insert(0, str(PIPE))
import extract_signals as es  # noqa: E402
import seasonal_forecast as sf  # noqa: E402

ADM = {"ZWE": 2, "KEN": 1, "MWI": 2, "ZMB": 2}
OLD_END = pd.Timestamp("2024-12-01")          # last month of the frozen history
FC_OLD_END = pd.Timestamp("2024-06-01")       # last NMME issue month of the frozen history
SIGNAL_SOURCE = {"precip_mm": "chirps", "spi_1m": "chirps", "spi_3m": "chirps", "spi_6m": "chirps",
                 "ndvi_crop": "modis", "ndvi_grass": "modis", "ndvi_z_crop": "modis",
                 "ndvi_z_grass": "modis", "vci_crop": "modis", "vci_grass": "modis",
                 "sm1_z": "era5", "sm2_z": "era5", "t2m_z": "era5"}
STATIC = {"crop_frac", "grass_frac"}


def load_status() -> dict:
    return json.loads(STATUS.read_text()) if STATUS.exists() else {}


def save_status(st: dict):
    st["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    STATUS.write_text(json.dumps(st, indent=2, default=str))


# ------------------------------------------------------------------ completeness
def image_dates(cid: str, start: str, end: str) -> list[pd.Timestamp]:
    import ee
    ts = ee.ImageCollection(cid).filterDate(start, end).aggregate_array("system:time_start").getInfo()
    return [pd.Timestamp(t, unit="ms") for t in ts]


def completeness(end_year: int) -> dict:
    """-> {source: {"complete_months": [YYYY-MM-01...], "last_image": str, "last_complete": str}}"""
    start, end = f"{OLD_END.year + 1}-01-01", f"{end_year + 1}-01-01"
    out = {}
    ch = image_dates(es.CHIRPS, start, end)
    cnt = pd.Series(1, index=pd.DatetimeIndex(ch)).groupby(lambda d: d.to_period("M")).sum()
    out["chirps"] = {"complete_months": [str(p.to_timestamp().date()) for p, n in cnt.items() if n == 6],
                     "pentads_per_month": {str(p): int(n) for p, n in cnt.items()},
                     "last_image": str(max(ch).date()) if ch else None}
    mo = image_dates(es.MODIS, start, end)
    months = pd.period_range(start, f"{end_year}-12", freq="M")
    done = []
    for p in months:
        m_end = p.to_timestamp(how="end").normalize()
        if any((d >= m_end - pd.Timedelta(days=15)) & (d <= m_end) for d in mo):
            done.append(str(p.to_timestamp().date()))
    out["modis"] = {"complete_months": done, "last_image": str(max(mo).date()) if mo else None}
    er = image_dates(es.ERA5, start, end)
    out["era5"] = {"complete_months": [str(d.normalize().date()) for d in er],
                   "last_image": str(max(er).date()) if er else None}
    for s in out:
        cm = out[s]["complete_months"]
        out[s]["last_complete"] = max(cm) if cm else str(OLD_END.date())
    return out


# ------------------------------------------------------------------ helpers
def compare_long(old: pd.DataFrame, new: pd.DataFrame, keys: list[str], val: str, label: str):
    """Assert new == old on the key set of old (NaN == NaN)."""
    m = old.merge(new, on=keys, how="left", suffixes=("_old", "_new"), validate="one_to_one")
    a, b = m[f"{val}_old"].to_numpy(float), m[f"{val}_new"].to_numpy(float)
    same = (np.isnan(a) & np.isnan(b)) | np.isclose(a, b, rtol=0, atol=1e-9, equal_nan=False)
    bad = int((~same).sum())
    print(f"  verify {label}: {len(m)} old rows, {bad} differ", flush=True)
    if bad:
        print(m[~same].head(10).to_string(), flush=True)
        raise SystemExit(f"{label}: history changed ({bad} rows) - aborting, nothing written")


def units_of(df: pd.DataFrame) -> set:
    return set(df["unit_id"].unique())


# ------------------------------------------------------------------ signals
def step_signals(iso3: str, end_year: int, comp: dict, st: dict):
    path = DATA / f"signals_{iso3}.parquet"
    old = pd.read_parquet(path)
    old_m = pd.to_datetime(old["month"])
    assert old_m.max() == OLD_END, f"{iso3}: unexpected old end {old_m.max()}"
    bak = HERE / "backup" / f"signals_{iso3}.parquet"
    bak.parent.mkdir(exist_ok=True)
    if not bak.exists():
        old.to_parquet(bak, index=False)

    argv = sys.argv
    sys.argv = ["extract_signals.py", "--iso3", iso3, "--adm", str(ADM[iso3]),
                "--end", str(end_year), "--no-geojson"]
    try:
        es.main()
    finally:
        sys.argv = argv

    new = pd.read_parquet(path)
    new["month_ts"] = pd.to_datetime(new["month"])
    if units_of(new) != units_of(old):
        old.to_parquet(path, index=False)
        raise SystemExit(f"{iso3}: unit set changed - restored old file")
    compare_long(old, new[new.month_ts <= OLD_END].drop(columns="month_ts"),
                 ["unit_id", "month", "signal_type"], "value", f"signals_{iso3}")

    # mask new months a source has not completed; truncate to the last month any source has
    masked = {}
    last_any = max(pd.Timestamp(comp[s]["last_complete"]) for s in comp)
    for sig, src in SIGNAL_SOURCE.items():
        ok = {pd.Timestamp(m) for m in comp[src]["complete_months"]}
        sel = (new.signal_type == sig) & (new.month_ts > OLD_END) & (~new.month_ts.isin(ok)) \
            & (new.month_ts <= last_any) & new.value.notna()
        if sel.any():
            masked[sig] = sorted({str(d.date()) for d in new.loc[sel, "month_ts"].unique()})
            new.loc[sel, "value"] = np.nan
    keep = (new.month_ts <= last_any) | new.signal_type.isin(STATIC)
    new = new[keep].drop(columns="month_ts").reset_index(drop=True)
    new.to_parquet(path, index=False)

    added = new[pd.to_datetime(new.month) > OLD_END]
    cov = (added.groupby([added.month, "signal_type"]).value.apply(lambda s: float(s.notna().mean()))
           .unstack().round(2))
    print(f"{iso3}: signals -> {path.name} rows {len(old)} -> {len(new)} (+{len(new) - len(old)}), "
          f"months to {added.month.max()}; masked partial months {masked}", flush=True)
    print(cov.to_string(), flush=True)
    st.setdefault("signals", {})[iso3] = {
        "rows_old": int(len(old)), "rows_new": int(len(new)), "rows_added": int(len(new) - len(old)),
        "last_month": str(added.month.max()), "masked_partial_months": masked,
        "coverage_new_months": {str(m): {k: v for k, v in row.items() if pd.notna(v)}
                                for m, row in cov.iterrows()}}


# ------------------------------------------------------------------ dryspell
def load_dryspell_module():
    spec = importlib.util.spec_from_file_location("extract_dryspell", PIPE / "dryspell" / "extract_dryspell.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def step_dryspell(iso3: str, end_year: int, comp: dict, st: dict, workers: int = 6):
    dx = load_dryspell_module()
    path = DATA / f"dryspell_{iso3}.parquet"
    old = pd.read_parquet(path)
    assert pd.to_datetime(old["month"]).max() == OLD_END
    bak = HERE / "backup" / f"dryspell_{iso3}.parquet"
    bak.parent.mkdir(exist_ok=True)
    if not bak.exists():
        old.to_parquet(bak, index=False)

    complete = {pd.Period(m, "M") for m in comp["chirps"]["complete_months"]}
    orig_pf = dx.pentad_frame
    dropped = {}

    def pentad_frame_live(recs_by_year, units):
        df = orig_pf(recs_by_year, units)
        per = df.index.to_period("M")
        bad = (df.index > OLD_END + pd.offsets.MonthEnd(0)) & ~np.isin(per, list(complete))
        if bad.any():
            dropped.update({str(p): int(n) for p, n in pd.Series(1, index=per[bad]).groupby(level=0).sum().items()})
        return df[~bad]

    dx.pentad_frame = pentad_frame_live
    dx.build_country(iso3, 2001, end_year, workers)

    new = pd.read_parquet(path)
    new["month_ts"] = pd.to_datetime(new["month"])
    if units_of(new) != units_of(old):
        old.to_parquet(path, index=False)
        raise SystemExit(f"{iso3}: dryspell unit set changed - restored old file")
    compare_long(old, new[new.month_ts <= OLD_END].drop(columns="month_ts"),
                 ["unit_id", "month", "signal_type"], "value", f"dryspell_{iso3}")
    last_any = max(pd.Timestamp(comp[s]["last_complete"]) for s in comp)
    new = new[new.month_ts <= last_any].drop(columns="month_ts").reset_index(drop=True)
    new.to_parquet(path, index=False)
    added = new[pd.to_datetime(new.month) > OLD_END]
    cov = added.groupby("signal_type").value.apply(lambda s: round(100 * s.notna().mean(), 1)).to_dict()
    print(f"{iso3}: dryspell -> rows {len(old)} -> {len(new)} (+{len(new) - len(old)}), "
          f"to {added.month.max()}, dropped partial pentad months {dropped}, non-NaN% new months {cov}", flush=True)
    st.setdefault("dryspell", {})[iso3] = {
        "rows_old": int(len(old)), "rows_new": int(len(new)), "rows_added": int(len(new) - len(old)),
        "last_month": str(added.month.max()), "dropped_partial_pentad_months": dropped,
        "nonnan_pct_new_months": cov}


# ------------------------------------------------------------------ seasonal forecast
def step_seasonal(iso3s: list[str], last_s: str, st: dict, workers: int = 3):
    sf.LAST_S = last_s
    jobs = []
    for model, kinds in sf.MODELS.items():
        a, b = kinds["FORECAST"]
        first = pd.Period(FC_OLD_END, "M") + 1
        last = min(pd.Period(b, "M"), pd.Period(last_s, "M"))
        if first > last:
            print(f"  {model}: no forecasts after {FC_OLD_END.date()} on IRI ({a}..{b})", flush=True)
            continue
        for ym0, ym1 in sf.month_chunks(str(first), str(last), sf.CHUNK_MONTHS):
            jobs.append((model, "FORECAST", ym0, ym1))
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for msg, ok in ex.map(lambda j: sf.fetch_chunk(*j), jobs):
            print("  " + msg, flush=True)
            if not ok:
                raise SystemExit("NMME chunk fetch failed")
    olds = {}
    for iso3 in iso3s:
        p = DATA / f"seasonal_fc_{iso3}.parquet"
        olds[iso3] = pd.read_parquet(p)
        bak = HERE / "backup" / p.name
        bak.parent.mkdir(exist_ok=True)
        if not bak.exists():
            olds[iso3].to_parquet(bak, index=False)
    sf.cmd_build(iso3s)
    for iso3 in iso3s:
        old = olds[iso3]
        new = pd.read_parquet(DATA / f"seasonal_fc_{iso3}.parquet")
        keys = ["unit_id", "issue_month", "target_window", "product"]
        hist = new[new.issue_month <= FC_OLD_END]
        for val in ("anom_z", "p_below_normal", "n_members"):
            compare_long(old, hist, keys, val, f"seasonal_fc_{iso3}.{val}")
        added = new[new.issue_month > FC_OLD_END]
        by_prod = added.groupby("product").agg(n=("anom_z", "size"), nonnan=("anom_z", lambda s: s.notna().mean()),
                                               last=("issue_month", "max"))
        print(f"{iso3}: seasonal_fc rows {len(old)} -> {len(new)} (+{len(new) - len(old)}), "
              f"issue to {new.issue_month.max().date()}", flush=True)
        print(by_prod.to_string(), flush=True)
        st.setdefault("seasonal_fc", {})[iso3] = {
            "rows_old": int(len(old)), "rows_new": int(len(new)), "rows_added": int(len(new) - len(old)),
            "last_issue_month": str(new.issue_month.max().date()),
            "products_after_2024_06": {p: {"rows": int(r.n), "nonnan_z": round(float(r.nonnan), 3),
                                           "last_issue": str(r["last"].date())} for p, r in by_prod.iterrows()}}


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--step", choices=["signals", "dryspell", "seasonal", "all"], default="all")
    ap.add_argument("--iso3", nargs="*", default=["ZWE", "KEN", "MWI", "ZMB"])
    ap.add_argument("--end", type=int, default=2026, help="last calendar year to fetch from Earth Engine")
    ap.add_argument("--last-s", default="2026-10", help="last NMME issue month available on IRI")
    a = ap.parse_args()
    iso3s = [i.upper() for i in a.iso3]
    st = load_status()
    t0 = time.time()
    if a.step in ("signals", "dryspell", "all"):
        import ee
        ee.Initialize(project=es.EE_PROJECT)
        comp = completeness(a.end)
        st["sources"] = comp
        save_status(st)
        for s, v in comp.items():
            print(f"{s}: last image {v['last_image']}, last complete month {v['last_complete']}", flush=True)
    if a.step in ("signals", "all"):
        for iso3 in iso3s:
            step_signals(iso3, a.end, comp, st)
            save_status(st)
    if a.step in ("dryspell", "all"):
        for iso3 in iso3s:
            step_dryspell(iso3, a.end, comp, st)
            save_status(st)
    if a.step in ("seasonal", "all"):
        step_seasonal(iso3s, a.last_s, st)
        save_status(st)
    print(f"done in {time.time() - t0:.0f}s -> {STATUS}")


if __name__ == "__main__":
    main()
