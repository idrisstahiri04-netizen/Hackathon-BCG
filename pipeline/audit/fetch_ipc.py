"""Download FEWS NET IPC-compatible phase classifications (FDW ipcphase API, anonymous).

Usage: python -I pipeline/audit/fetch_ipc.py [ISO3 ...]   (default: ZWE)
Raw bulk CSV -> pipeline/cache/ipc_raw/<ISO3>/ipcphase.csv (+ _meta.json: url, fetched_at, sha256). Untouched.
Output -> pipeline/data/ipc_<ISO3>.parquet: scenarios CS, ML1, ML2; projection_start 2016..2024.
The API ignores date/scenario filters, so we download the whole country CSV and filter client-side.
Idempotent: cached CSV is reused.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
PIPE = HERE.parent
CACHE = PIPE / "cache" / "ipc_raw"
OUT = PIPE / "data"
ISO2 = {"ZWE": "ZW", "KEN": "KE", "MWI": "MW", "ZMB": "ZM"}
BASE = "https://fdw.fews.net/api/ipcphase/"
KEEP = ["fnid", "geographic_unit_full_name", "geographic_unit_name", "unit_type",
        "classification_scale", "scenario", "scenario_name", "projection_start",
        "projection_end", "reporting_date", "value", "description", "preference_rating",
        "is_allowing_for_assistance", "status", "source_document", "id"]


def fetch(iso3: str) -> pd.DataFrame:
    """One bulk CSV per country (paged JSON hits a 403 rate limit after ~2 pages)."""
    d = CACHE / iso3
    d.mkdir(parents=True, exist_ok=True)
    f = d / "ipcphase.csv"
    url = f"{BASE}?country_code={ISO2[iso3]}&format=csv"
    if not f.exists():
        for attempt in range(5):
            try:
                r = requests.get(url, timeout=600)
                r.raise_for_status()
                break
            except Exception as e:  # noqa: BLE001
                print(f"  retry {attempt} {url}: {e}", file=sys.stderr)
                time.sleep(20 * (attempt + 1))
        else:
            raise RuntimeError(url)
        f.write_bytes(r.content)
        (d / "_meta.json").write_text(json.dumps({
            "source_id": f"fews_fdw_ipcphase_{iso3.lower()}", "url": url,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "sha256": hashlib.sha256(r.content).hexdigest(),
            "licence": "FEWS NET public data usage policy (data_usage_policy=Public)"}, indent=1))
    df = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
    df = df[[c for c in KEEP if c in df.columns]]
    df["projection_start"] = pd.to_datetime(df["projection_start"])
    df["projection_end"] = pd.to_datetime(df["projection_end"])
    df = df[df["scenario"].isin(["CS", "ML1", "ML2"])]
    df = df[df["projection_start"].dt.year.between(2016, 2024)]
    df["iso3"] = iso3
    df = df.drop_duplicates("id")
    return df.reset_index(drop=True)


if __name__ == "__main__":
    for iso3 in (sys.argv[1:] or ["ZWE"]):
        df = fetch(iso3)
        p = OUT / f"ipc_{iso3}.parquet"
        df.to_parquet(p, index=False)
        print(iso3, len(df), "rows ->", p,
              df.groupby("scenario").size().to_dict(), df["unit_type"].value_counts().to_dict())
