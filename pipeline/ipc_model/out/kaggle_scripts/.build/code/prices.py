"""Market price signals (price_anom, livestock_price_anom, tot_anom) per ADM unit-month.

Sources
  * WFP food prices on HDX (CKAN API, dataset `wfp-food-prices-for-<country>`), all countries.
  * FEWS NET Data Warehouse (fdw.fews.net, anonymous) for ZW/KE/MW/ZM: /api/market/ (lat/lon),
    /api/marketproduct/ (series list; `fnid=` filter), /api/marketpricefacts/?dataseries=<id>.
    The facts endpoint refuses offset >= 1000, so we pull series by series (<= 2 pages of 500,
    sliced by year when a series has > 1000 points).
Raw downloads are cached untouched under pipeline/cache/prices/{wfp,fdw}/ with _meta.json.

Method (CONTRACT: price_anom = % vs 5-year same-calendar-month mean, higher = worse)
  1. series = (source, market, commodity, unit, currency, price type); monthly median price.
  2. a series is split at redenominations / breaks (known dates + any > 20x month-to-month jump), so a
     baseline never spans a currency change. Zimbabwe: USD series only (nominal ZWL is hyperinflated and
     WFP's usdprice for ZWL rows uses the official rate, ~15x off the real USD price in 2023).
  3. anomaly per series-month = (p_t / mean(p same month, previous 5 years) - 1) * 100, needs >= 3 of 5
     prior years, clipped to +-100. Missing -> NaN, never 0.
  4. market value = median over the market's maize-family series (maize grain + maize meal); if none that
     month, median over the other staple cereals (sorghum, millet, rice, teff).
  5. unit value: units containing >= 1 market -> median over their markets ("direct"); units without a
     market -> nearest market within 100 km of the unit centroid that has a value that month ("borrowed");
     otherwise NaN.
  livestock_price_anom: same with live goat/cattle/sheep/camel series (natural sign: LOWER = worse).
  tot_anom: goat price / maize-family price in the same market and currency, anomaly as above
  (natural sign: LOWER = worse for herders).

LATENCY: WFP/FEWS NET monthly prices for month m are published ~1 month later. The model must shift
these signals by 1 month (same convention as common.LATENCY); nothing here is shifted.

Usage: python pipeline/prices.py [--iso3 ZWE KEN ...] [--no-fetch]
Outputs: pipeline/data/prices_<ISO3>.parquet (unit_id, unit_name, iso3, month, signal_type, value; full
unit x month grid, NaN where missing), pipeline/data/prices_coverage.csv, pipeline/data/PRICES.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape
from shapely.strtree import STRtree

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
CACHE = HERE / "cache" / "prices"
UA = {"User-Agent": "bcg-hackathon-prices/0.1 (drought early warning; contact via repo)"}

HDX_SLUG = {"ZWE": "zimbabwe", "KEN": "kenya", "MWI": "malawi", "ZMB": "zambia", "MOZ": "mozambique",
            "TZA": "united-republic-of-tanzania", "ETH": "ethiopia", "SOM": "somalia", "NAM": "namibia",
            "BWA": "botswana", "ZAF": "south-africa", "MDG": "madagascar", "AGO": "angola", "UGA": "uganda"}
FDW_CC = {"ZWE": "ZW", "KEN": "KE", "MWI": "MW", "ZMB": "ZM"}
# FEWS NET cpcv2 codes we pull: cereals + maize products + live animals (names seen in marketproduct lists)
FDW_CODES = {"R01122AC", "R01142AA", "R01142AC", "R01182AD", "R01182AC", "P23130AA", "P23130AB", "P23130AC",
             "P23120AC", "P23161AA", "P23161AQ", "L02123AB", "L02111AB"}
# currencies kept per country (None = all; series keep their own currency anyway)
KEEP_CURRENCY = {"ZWE": {"USD"}}
# known redenominations: split every local-currency series at these months (never baseline across them)
# (WFP already reports MOZ 2006 metical and ZMB 2013 kwacha rebases in new units - checked, no jump - so no
#  forced split there; the >20x jump detector below still catches any unconverted stretch.)
KNOWN_BREAKS = {"ZWE": ["2019-02-01", "2024-04-01"]}  # RTGS/ZWL, ZiG; applied to non-USD series only
# FEWS NET Zimbabwe relabelled its bucket units in Sep-Oct 2023 (volume -> standard weight of the same container:
# 20 L bucket of grain ~ 17.5 kg, 5 L tin ~ 4.5 kg). Treat them as one series, else every series breaks in the
# crisis window. Assumption documented in PRICES.md.
FDW_UNIT_ALIAS = {"20_L": "17.5 kg", "5_L": "4.5_kg"}
JUMP_SPLIT = 20.0            # month-to-month ratio above this (or below 1/x) = break, split the series
BASE_YEARS, MIN_YEARS = 5, 3
BORROW_KM = 100.0
LATENCY_MONTHS = 1           # documented; applied by the model, not here
MAIZE_FAMILY = {"maize", "maize_meal"}
OTHER_CEREALS = {"sorghum", "millet", "rice", "teff"}
LIVESTOCK = {"livestock"}


# --------------------------------------------------------------------------- fetch
def _get(url: str, tries: int = 5, binary: bool = False):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
                b = r.read()
                return b if binary else json.loads(b.decode())
        except Exception as e:  # noqa: BLE001
            print(f"  retry {i} {url}: {e}", file=sys.stderr)
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"failed: {url}")


def _meta(path: Path, url: str, licence: str):
    b = path.read_bytes()
    path.with_name(path.name + "._meta.json").write_text(json.dumps({
        "url": url, "fetched_at": datetime.now(timezone.utc).isoformat(), "sha256": hashlib.sha256(b).hexdigest(),
        "bytes": len(b), "licence": licence}, indent=1))


def fetch_wfp(iso3: str) -> bool:
    """HDX CKAN: package_show -> CSV resources. Returns False when the dataset does not exist (BWA)."""
    d = CACHE / "wfp" / iso3
    d.mkdir(parents=True, exist_ok=True)
    pk = d / "package.json"
    if not pk.exists():
        try:
            j = _get(f"https://data.humdata.org/api/3/action/package_show?id=wfp-food-prices-for-{HDX_SLUG[iso3]}", tries=1)
        except RuntimeError:  # 404: no WFP dataset for this country (BWA)
            j = {"success": False}
        pk.write_text(json.dumps(j))
    j = json.loads(pk.read_text())
    if not j.get("success"):
        return False
    lic = j["result"].get("license_title", "CC BY-IGO")
    for r in j["result"]["resources"]:
        if not r["url"].endswith(".csv"):
            continue
        f = d / Path(r["url"]).name
        if f.exists() and f.stat().st_size > 0:
            continue
        f.write_bytes(_get(r["url"], binary=True))
        _meta(f, r["url"], lic)
    return True


def fetch_fdw(cc: str):
    base = "https://fdw.fews.net/api"
    d = CACHE / "fdw" / cc
    (d / "series").mkdir(parents=True, exist_ok=True)
    if not (d / "markets.json").exists():
        rows, off = [], 0
        while True:
            j = _get(f"{base}/market/?country_code={cc}&format=json&page_size=500&offset={off}")
            rows += j["results"]; off += 500
            if not j.get("next"):
                break
        (d / "markets.json").write_text(json.dumps(rows))
        _meta(d / "markets.json", f"{base}/market/?country_code={cc}", "FEWS NET data usage policy")
    if not (d / "marketproduct_all.json").exists():  # list is also capped at offset 1000 -> per market
        rows = []
        for m in json.loads((d / "markets.json").read_text()):
            rows += _get(f"{base}/marketproduct/?country_code={cc}&format=json&page_size=500&fnid={m['fnid']}")["results"]
        (d / "marketproduct_all.json").write_text(json.dumps(rows))
    series = [s for s in json.loads((d / "marketproduct_all.json").read_text()) if s["product"] in FDW_CODES]
    for s in series:
        f = d / "series" / f"{s['id']}.json"
        if f.exists():
            continue
        rows, n = [], s["datapoint_count"] or 0
        slices = [""] if n <= 1000 else [f"&start_date={y}-01-01&end_date={y}-12-31" for y in range(1995, 2027)]
        for sl in slices:
            for off in (0, 500):
                j = _get(f"{base}/marketpricefacts/?country_code={cc}&format=json&page_size=500&dataseries={s['id']}&offset={off}{sl}")
                rows += j["results"]
                if not j.get("next"):
                    break
        f.write_text(json.dumps(rows))
    _meta(d / "marketproduct_all.json", f"{base}/marketproduct/?country_code={cc}&fnid=<market>", "FEWS NET data usage policy")


# --------------------------------------------------------------------------- load + classify
def classify(name: str) -> str | None:
    n = name.lower()
    if any(k in n for k in ("meat", "bread", "pasta", "seed", "bran", "husk", "milk", "butter", "milling", "cost", "donkey")):
        return None
    if n.startswith("livestock") or any(k in n for k in ("goat", "cattle", "bull", "sheep", "camel")):
        return "livestock"
    if "maize" in n:
        return "maize_meal" if any(k in n for k in ("meal", "flour", "crushed", "grits")) else "maize"
    if "sorghum" in n:
        return "sorghum"
    if "millet" in n:
        return "millet"
    if n.startswith("rice") and "paddy" not in n:
        return "rice"
    if "teff" in n:
        return "teff"
    return None


def load_wfp(iso3: str) -> pd.DataFrame:
    d = CACHE / "wfp" / iso3
    f = next(d.glob("wfp_food_prices_*.csv"))
    df = pd.read_csv(f, skiprows=[1], low_memory=False)
    mk = next(d.glob("wfp_markets_*.csv"), None)
    if mk is not None:  # fill missing coordinates from the markets table
        m = pd.read_csv(mk, skiprows=[1]).set_index("market_id")[["latitude", "longitude"]]
        df["latitude"] = df["latitude"].fillna(df["market_id"].map(m["latitude"]))
        df["longitude"] = df["longitude"].fillna(df["market_id"].map(m["longitude"]))
    df["group"] = df["commodity"].map(classify)
    df = df[df["group"].notna() & df["price"].gt(0)].copy()
    df["month"] = pd.to_datetime(df["date"]).dt.to_period("M").dt.to_timestamp()
    df["source"] = "wfp"
    df["market_key"] = "wfp:" + df["market_id"].astype(str)
    df["pricetype"] = df["pricetype"].str.lower()
    return df[["source", "market_key", "market", "latitude", "longitude", "month", "commodity", "group", "unit",
               "currency", "pricetype", "price"]]


def load_fdw(iso3: str) -> pd.DataFrame:
    d = CACHE / "fdw" / FDW_CC[iso3]
    mk = {m["fnid"]: m for m in json.loads((d / "markets.json").read_text())}
    rows = []
    for f in (d / "series").glob("*.json"):
        for r in json.loads(f.read_text()):
            if r.get("value") is None or r.get("status") in ("No Data", "Not Available"):
                continue
            m = mk.get(r["fnid"], {})
            rows.append((r["fnid"], r["market"], m.get("latitude"), m.get("longitude"), r["period_date"][:7],
                         r["product"], r["unit"], r["currency"], (r["price_type"] or "").lower(), r["value"]))
    df = pd.DataFrame(rows, columns=["fnid", "market", "latitude", "longitude", "month", "commodity", "unit",
                                     "currency", "pricetype", "price"])
    if df.empty:
        return df
    df["group"] = df["commodity"].map(classify)
    df = df[df["group"].notna() & df["price"].gt(0)].copy()
    df["unit"] = df["unit"].replace(FDW_UNIT_ALIAS)
    df["month"] = pd.to_datetime(df["month"] + "-01")
    df["source"] = "fdw"
    df["market_key"] = "fdw:" + df["fnid"]
    return df[["source", "market_key", "market", "latitude", "longitude", "month", "commodity", "group", "unit",
               "currency", "pricetype", "price"]]


def select_pricetype(df: pd.DataFrame) -> pd.DataFrame:
    """Retail only; wholesale is used for a (country, group) only when it has no retail series at all."""
    keep = []
    for g, sub in df.groupby("group"):
        if (sub["pricetype"] == "retail").any():
            keep.append(sub[sub["pricetype"] == "retail"])
        else:
            keep.append(sub[sub["pricetype"] == "wholesale"])
    return pd.concat(keep) if keep else df.iloc[0:0]


# --------------------------------------------------------------------------- anomalies
def monthly_series(df: pd.DataFrame, iso3: str) -> pd.DataFrame:
    key = ["source", "market_key", "commodity", "unit", "currency", "pricetype"]
    s = df.groupby(key + ["group", "month"], as_index=False)["price"].median()
    s = s.sort_values(key + ["month"])
    # break detection: known redenomination months + any jump > JUMP_SPLIT between consecutive observations
    known = pd.to_datetime(KNOWN_BREAKS.get(iso3, []))
    sid = s.groupby(key, sort=False).ngroup()
    prev = s.groupby(sid)["price"].shift()
    ratio = s["price"] / prev
    jump = (ratio > JUMP_SPLIT) | (ratio < 1 / JUMP_SPLIT)
    prev_m = s.groupby(sid)["month"].shift()
    crosses = pd.Series(False, index=s.index)
    for b in known:
        crosses |= (prev_m < b) & (s["month"] >= b) & (s["currency"] != "USD")
    brk = (jump | crosses).fillna(False).astype(int)
    s["segment"] = brk.groupby(sid).cumsum()
    s["series_id"] = sid.astype(str) + "/" + s["segment"].astype(str)
    s.attrs["n_breaks"] = int(brk.sum())
    return s


def anomaly(s: pd.DataFrame, value_col: str = "price") -> pd.DataFrame:
    """Per series_id: % vs mean of the same calendar month in the previous BASE_YEARS years (>= MIN_YEARS)."""
    out = []
    for _, g in s.groupby("series_id", sort=False):
        g = g.set_index("month")[value_col]
        if len(g) < MIN_YEARS + 1:
            continue
        idx = pd.DatetimeIndex(g.index)
        base = np.full(len(g), np.nan)
        cnt = np.zeros(len(g), dtype=int)
        lookup = g.to_dict()
        for i, t in enumerate(idx):
            vals = [lookup[t - pd.DateOffset(years=k)] for k in range(1, BASE_YEARS + 1) if (t - pd.DateOffset(years=k)) in lookup]
            cnt[i] = len(vals)
            if len(vals) >= MIN_YEARS:
                base[i] = float(np.mean(vals))
        a = (g.values / base - 1.0) * 100.0
        out.append(pd.DataFrame({"month": idx, "anom": np.clip(a, -100, 100), "n_base": cnt}, index=g.index).reset_index(drop=True)
                   .assign(series_id=_))
    if not out:
        return pd.DataFrame(columns=["series_id", "month", "anom", "n_base"])
    return pd.concat(out, ignore_index=True)


def market_values(s: pd.DataFrame, a: pd.DataFrame, groups_primary: set, groups_fallback: set) -> pd.DataFrame:
    """market_key x month -> median anomaly over primary-group series, else fallback-group series."""
    m = s[["series_id", "market_key", "group", "month"]].merge(a, on=["series_id", "month"])
    m = m[m["anom"].notna()]
    prim = m[m["group"].isin(groups_primary)].groupby(["market_key", "month"])["anom"].median()
    if groups_fallback:
        fb = m[m["group"].isin(groups_fallback)].groupby(["market_key", "month"])["anom"].median()
        prim = prim.combine_first(fb)
    return prim.rename("value").reset_index()


# --------------------------------------------------------------------------- geography
def _hav(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = 0.5 - np.cos((lat2 - lat1) * p) / 2 + np.cos(lat1 * p) * np.cos(lat2 * p) * (1 - np.cos((lon2 - lon1) * p)) / 2
    return 12742 * np.arcsin(np.sqrt(a))


def load_units(iso3: str):
    gj = json.loads((DATA / f"units_{iso3}.geojson").read_text())
    ids, names, geoms = [], [], []
    for ft in gj["features"]:
        g = shape(ft["geometry"])
        if g.geom_type == "GeometryCollection":
            g = shapely.unary_union([p for p in g.geoms if p.geom_type in ("Polygon", "MultiPolygon")])
        ids.append(ft["properties"]["shapeID"]); names.append(ft["properties"]["shapeName"]); geoms.append(g)
    return pd.DataFrame({"unit_id": ids, "unit_name": names}), geoms


def map_markets(markets: pd.DataFrame, units: pd.DataFrame, geoms) -> tuple[pd.DataFrame, dict]:
    """markets: market_key, latitude, longitude. Returns markets with unit_id (direct containment) and, per
    unit without a market, the ordered list of (market_key, km) within BORROW_KM of the unit centroid."""
    markets = markets.dropna(subset=["latitude", "longitude"]).drop_duplicates("market_key").reset_index(drop=True)
    pts = shapely.points(markets["longitude"].values, markets["latitude"].values)
    tree = STRtree(geoms)
    pi, gi = tree.query(pts, predicate="within")
    unit_of = dict(zip(markets.loc[pi, "market_key"], units.loc[gi, "unit_id"]))
    markets["unit_id"] = markets["market_key"].map(unit_of)
    direct = set(unit_of.values())
    borrow = {}
    for i, uid in enumerate(units["unit_id"]):
        if uid in direct:
            continue
        c = geoms[i].centroid
        km = _hav(c.y, c.x, markets["latitude"].values, markets["longitude"].values)
        order = np.argsort(km)
        borrow[uid] = [(markets.loc[j, "market_key"], float(km[j])) for j in order if km[j] <= BORROW_KM]
    return markets, borrow


def unit_values(mv: pd.DataFrame, markets: pd.DataFrame, borrow: dict, units: pd.DataFrame) -> tuple[pd.Series, dict]:
    """unit_id x month -> value. direct = median over contained markets; borrowed = nearest market with data."""
    mv = mv.merge(markets[["market_key", "unit_id"]], on="market_key", how="left")
    direct = mv.dropna(subset=["unit_id"]).groupby(["unit_id", "month"])["value"].median()
    piv = mv.pivot_table(index="month", columns="market_key", values="value")
    parts, mode = [direct], {}
    for uid in units["unit_id"]:
        if uid in direct.index.get_level_values(0):
            mode[uid] = ("direct", int(markets["unit_id"].eq(uid).sum()))
            continue
        cands = [k for k, _ in borrow.get(uid, []) if k in piv.columns]
        if not cands:
            mode[uid] = ("none", 0)
            continue
        ser = piv[cands].bfill(axis=1).iloc[:, 0].dropna()  # nearest market that has a value that month
        if ser.empty:
            mode[uid] = ("none", 0)
            continue
        mode[uid] = ("borrowed", len(cands))
        parts.append(pd.Series(ser.values, index=pd.MultiIndex.from_arrays([[uid] * len(ser), ser.index], names=["unit_id", "month"])))
    return pd.concat(parts), mode


# --------------------------------------------------------------------------- per country
def build(iso3: str, fetch: bool = True) -> dict:
    rep = {"iso3": iso3}
    frames = []
    if fetch and iso3 in HDX_SLUG:
        if not fetch_wfp(iso3):
            rep["wfp"] = "no HDX dataset"
    if (CACHE / "wfp" / iso3).exists() and list((CACHE / "wfp" / iso3).glob("wfp_food_prices_*.csv")):
        frames.append(load_wfp(iso3))
    if iso3 in FDW_CC:
        if fetch:
            fetch_fdw(FDW_CC[iso3])
        frames.append(load_fdw(iso3))
    if not frames:
        return rep | {"status": "no data"}
    raw = pd.concat(frames, ignore_index=True)
    if iso3 in KEEP_CURRENCY:
        n0 = len(raw)
        raw = raw[raw["currency"].isin(KEEP_CURRENCY[iso3])]
        rep["dropped_non_usd_rows"] = n0 - len(raw)
    raw = select_pricetype(raw)
    rep["rows"] = int(len(raw)); rep["markets"] = int(raw["market_key"].nunique())
    rep["rows_by_source"] = raw.groupby("source").size().to_dict()
    rep["rows_by_group"] = raw.groupby("group").size().to_dict()
    units, geoms = load_units(iso3)
    mk = raw.groupby("market_key", as_index=False).agg(latitude=("latitude", "first"), longitude=("longitude", "first"), market=("market", "first"))
    markets, borrow = map_markets(mk, units, geoms)
    rep["markets_with_coords"] = int(len(markets)); rep["markets_inside_a_unit"] = int(markets["unit_id"].notna().sum())

    s = monthly_series(raw, iso3)
    rep["series"] = int(s["series_id"].nunique()); rep["series_breaks"] = s.attrs["n_breaks"]
    a = anomaly(s)
    out, cov = [], []
    # price_anom
    mv = market_values(s, a, MAIZE_FAMILY, OTHER_CEREALS)
    if not mv.empty:
        uv, mode = unit_values(mv, markets, borrow, units)
        out.append(uv.rename("value").reset_index().assign(signal_type="price_anom")); cov.append(("price_anom", mode))
        used = s[["series_id", "group", "month"]].merge(a.dropna(subset=["anom"]), on=["series_id", "month"])
        rep["anomaly_rows_by_group"] = used.groupby("group").size().to_dict()
    # livestock
    mv = market_values(s, a, LIVESTOCK, set())
    if not mv.empty:
        uv, mode = unit_values(mv, markets, borrow, units)
        out.append(uv.rename("value").reset_index().assign(signal_type="livestock_price_anom")); cov.append(("livestock_price_anom", mode))
    # terms of trade goat : maize (same market, same currency)
    goat = s[(s["group"] == "livestock") & s["commodity"].str.lower().str.contains("goat")]
    if not goat.empty:
        gp = goat.groupby(["market_key", "currency", "month"])["price"].median().rename("goat")
        mp = s[s["group"].isin(MAIZE_FAMILY)].groupby(["market_key", "currency", "month"])["price"].median().rename("maize")
        tot = pd.concat([gp, mp], axis=1).dropna().reset_index()
        if not tot.empty:
            tot["tot"] = tot["goat"] / tot["maize"]
            tot["series_id"] = tot["market_key"] + "/" + tot["currency"]
            ta = anomaly(tot[["series_id", "month", "tot"]], "tot").dropna(subset=["anom"])
            mv = ta.merge(tot[["series_id", "market_key", "month"]], on=["series_id", "month"]).groupby(["market_key", "month"])["anom"].median().rename("value").reset_index()
            if not mv.empty:
                uv, mode = unit_values(mv, markets, borrow, units)
                out.append(uv.rename("value").reset_index().assign(signal_type="tot_anom")); cov.append(("tot_anom", mode))
    if not out:
        return rep | {"status": "no anomalies"}
    long = pd.concat(out, ignore_index=True)
    # full grid (units x months x signal types present) so NaN is explicit
    months = pd.date_range(long["month"].min(), long["month"].max(), freq="MS")
    grid = pd.MultiIndex.from_product([units["unit_id"], months, sorted(long["signal_type"].unique())], names=["unit_id", "month", "signal_type"]).to_frame(index=False)
    full = grid.merge(long, on=["unit_id", "month", "signal_type"], how="left").merge(units, on="unit_id")
    full["iso3"] = iso3
    full = full[["unit_id", "unit_name", "iso3", "month", "signal_type", "value"]].sort_values(["signal_type", "unit_id", "month"]).reset_index(drop=True)
    full["value"] = full["value"].astype("float64")
    full.to_parquet(DATA / f"prices_{iso3}.parquet", index=False)
    # coverage
    rows = []
    for sig, mode in cov:
        sub = long[long["signal_type"] == sig]
        per = sub.dropna(subset=["value"]).groupby("unit_id")["month"].agg(["min", "max", "count"])
        for uid, name in zip(units["unit_id"], units["unit_name"]):
            m, n = mode.get(uid, ("none", 0))
            r = per.loc[uid] if uid in per.index else None
            rows.append({"iso3": iso3, "unit_id": uid, "unit_name": name, "signal_type": sig, "mode": m, "n_markets": n,
                         "first_month": None if r is None else r["min"].strftime("%Y-%m"), "last_month": None if r is None else r["max"].strftime("%Y-%m"),
                         "n_months": 0 if r is None else int(r["count"])})
    rep["coverage"] = pd.DataFrame(rows)
    w = long[(long["month"] >= "2023-10-01") & (long["month"] <= "2024-04-01")].dropna(subset=["value"])
    rep["crisis_units"] = w.groupby("signal_type")["unit_id"].nunique().to_dict()   # 2023-24 El Nino window
    rep["months"] = (months[0].strftime("%Y-%m"), months[-1].strftime("%Y-%m"))
    rep["status"] = "ok"
    return rep


def write_md(reps: list[dict]):
    L = ["# Market price signals (pipeline/prices.py)", "",
         "Signals per unit-month, contract long format in `prices_<ISO3>.parquet` (full unit x month grid; NaN = insufficient data, never 0).",
         "", "| signal | definition | sign |", "|---|---|---|",
         "| price_anom | staple cereal retail price vs mean of the same calendar month in the previous 5 years (>= 3 years), %, clipped +-100; maize grain + maize meal, other cereals (sorghum/millet/rice/teff) only when a market has no maize value that month | higher = worse |",
         "| livestock_price_anom | live goat/cattle/sheep/camel price, same baseline | natural sign: LOWER = worse (distress sales) |",
         "| tot_anom | goat : maize-family terms of trade in the same market and currency, same baseline | natural sign: LOWER = worse for herders |",
         "", f"**Latency: prices for month m are published about {LATENCY_MONTHS} month later. Not shifted here; the model must lag these signals by {LATENCY_MONTHS} month (as in `common.LATENCY`).**",
         "", "Sources: WFP food prices on HDX (CC BY-IGO; `wfp-food-prices-for-<country>`), FEWS NET Data Warehouse market price facts (ZW/KE/MW/ZM; anonymous API). Anomalies are computed per series (source, market, commodity, unit, currency, price type) and series are split at known redenominations and at any >20x month-to-month jump, so no baseline spans a currency change. Zimbabwe uses USD series only: nominal ZWL is hyperinflated and WFP's `usdprice` for ZWL rows is converted at the official rate (Oct 2023 maize: ZWL 1,875/kg -> \"$0.028\" vs $0.45-0.48 in real USD quotes), so neither is usable. Retail prices; wholesale only where a country-commodity has no retail series. FEWS NET Zimbabwe relabelled bucket units in Sep-Oct 2023 (`20_L` -> `17.5 kg`, `5_L` -> `4.5_kg`, same container); these are merged into one series (assumption).",
         "", "Market -> unit: point-in-polygon on `units_<ISO3>.geojson`. Units with no market inside borrow the nearest market within 100 km of the unit centroid that has a value that month (`borrowed`); units with nothing within 100 km stay NaN (`none`).",
         "", "## Coverage", "", "| iso3 | signal | units direct | borrowed | none | units with a value Oct23-Apr24 | months with data | rows | markets (in unit) | series | breaks |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in reps:
        if r.get("status") != "ok":
            L.append(f"| {r['iso3']} | - | - | - | - | - | - | {r.get('status')} {r.get('wfp', '')} | | | |")
            continue
        cov = r["coverage"]
        for sig, c in cov.groupby("signal_type", sort=False):
            n = c["mode"].value_counts()
            L.append(f"| {r['iso3']} | {sig} | {n.get('direct', 0)} | {n.get('borrowed', 0)} | {n.get('none', 0)} | {r['crisis_units'].get(sig, 0)}/{len(c)} | {r['months'][0]}..{r['months'][1]} | {r['rows']} | {r['markets_with_coords']} ({r['markets_inside_a_unit']}) | {r['series']} | {r['series_breaks']} |")
    L += ["", "## Notes per country", ""]
    for r in reps:
        if r.get("status") != "ok":
            continue
        L.append(f"- **{r['iso3']}**: rows by source {r['rows_by_source']}; rows by commodity group {r['rows_by_group']}; anomaly rows by group {r.get('anomaly_rows_by_group', {})}"
                 + (f"; dropped {r['dropped_non_usd_rows']} non-USD rows" if "dropped_non_usd_rows" in r else "") + ".")
    L += ["", "Per-unit detail: `prices_coverage.csv` (mode, n_markets, first/last month, n_months).",
          "", "Known limits: Zimbabwe USD maize history is thin between 2019 and mid-2021 (WFP has no USD staples 2019-2023; FEWS NET USD series start 2021-07 for most markets), so the 3-of-5-years rule leaves most districts NaN in Oct 2023-Apr 2024: the values there come from the two long USD per-kg series (Harare, Makoni) and their <=100 km neighbours; the 22 FEWS NET bucket-unit markets only start 2021-07 and become usable from mid-2024. Relaxing to a 2-year baseline for those series would be a spec change (not done). Zambia: WFP collected only ~310-344 maize rows in 2022 and 2023 (vs ~2,000/yr before, 4,193 in 2024), so few ZMB units have values in the 2023-24 window. ZAF has one wholesale market (to 2022). BWA has no WFP dataset on HDX. Local-currency anomalies (all countries except ZWE) include general inflation; e.g. Malawi's Nov 2023 kwacha devaluation and Zambia's 2023-24 depreciation inflate price_anom."]
    (DATA / "PRICES.md").write_text("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso3", nargs="*", default=["ZWE", "KEN", "MWI", "ZMB", "MOZ", "TZA", "ETH", "SOM", "NAM", "BWA", "ZAF", "MDG", "AGO", "UGA"])
    ap.add_argument("--no-fetch", action="store_true")
    args = ap.parse_args()
    reps, covs = [], []
    for iso3 in args.iso3:
        t0 = time.time()
        try:
            r = build(iso3, fetch=not args.no_fetch)
        except Exception as e:  # noqa: BLE001
            r = {"iso3": iso3, "status": f"error: {e}"}
        reps.append(r)
        if "coverage" in r:
            covs.append(r["coverage"])
        print(f"{iso3}: {r.get('status')} rows={r.get('rows')} series={r.get('series')} markets={r.get('markets_with_coords')} ({time.time() - t0:.0f}s)")
    if covs:
        old = DATA / "prices_coverage.csv"
        prev = pd.read_csv(old) if old.exists() else pd.DataFrame()
        new = pd.concat(covs)
        if not prev.empty:
            prev = prev[~prev["iso3"].isin(new["iso3"].unique())]
            new = pd.concat([prev, new])
        new.to_csv(old, index=False)
    write_md(reps)




if __name__ == "__main__":
    main()
