"""Download FEWS NET IPC phases (FDW ipcphase) + the classification-unit GEOMETRIES (FDW feature API).

Usage: python -I pipeline/ipc_model/fetch_ipc_geo.py ZWE MOZ ETH ...
Reuses pipeline/audit/fetch_ipc.py (bulk CSV per country -> pipeline/cache/ipc_raw/<ISO3>/ipcphase.csv,
parquet -> pipeline/data/ipc_<ISO3>.parquet; existing parquets are not rewritten) with ISO2 codes for the
extra countries. Then, for every unit_type that carries IPC rows (fsc_admin_lhz, fsc_admin, fsc_lhz, ...),
downloads https://fdw.fews.net/api/feature/?country_code=XX&unit_type=T&format=geojson into
pipeline/cache/ipc_raw/<ISO3>/features_<T>.geojson (+ _meta.json: url, fetched_at, sha256, licence). Untouched,
idempotent (cached files reused). Prints how many IPC fnids have a geometry.
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
sys.path.insert(0, str(PIPE / "audit"))
import fetch_ipc  # noqa: E402

ISO2 = {"ZWE": "ZW", "KEN": "KE", "MWI": "MW", "ZMB": "ZM", "MOZ": "MZ", "ETH": "ET", "SOM": "SO", "MDG": "MG",
        "UGA": "UG", "TZA": "TZ", "AGO": "AO", "NAM": "NA", "BWA": "BW", "ZAF": "ZA"}
fetch_ipc.ISO2.update(ISO2)
CACHE = fetch_ipc.CACHE
DATA = fetch_ipc.OUT
FEATURE_URL = "https://fdw.fews.net/api/feature/?country_code={iso2}&unit_type={ut}&format=geojson"
SKIP_TYPES = {"admin0"}


def _get(url: str, dest: Path, tries: int = 5) -> bytes:
    if dest.exists():
        return dest.read_bytes()
    for attempt in range(tries):
        try:
            r = requests.get(url, timeout=900)
            r.raise_for_status()
            dest.write_bytes(r.content)
            dest.with_name(dest.name + "_meta.json").write_text(json.dumps({
                "url": url, "fetched_at": datetime.now(timezone.utc).isoformat(),
                "sha256": hashlib.sha256(r.content).hexdigest(), "bytes": len(r.content),
                "licence": "FEWS NET public data usage policy (data_usage_policy=Public)"}, indent=1))
            return r.content
        except Exception as e:  # noqa: BLE001
            print(f"  retry {attempt} {url}: {e}", file=sys.stderr)
            time.sleep(20 * (attempt + 1))
    raise RuntimeError(url)


def fetch_country(iso3: str) -> dict:
    df = fetch_ipc.fetch(iso3)
    p = DATA / f"ipc_{iso3}.parquet"
    if not p.exists():
        df.to_parquet(p, index=False)
    info = {"iso3": iso3, "ipc_rows": int(len(df)), "scenarios": df.groupby("scenario").size().to_dict(),
            "unit_types": df.unit_type.value_counts().to_dict(),
            "cs_months": sorted(df.loc[df.scenario == "CS", "projection_start"].dt.strftime("%Y-%m").unique()),
            "features": {}}
    if df.empty:
        return info
    need = set(df.fnid.astype(str))
    have = set()
    for ut in sorted(set(df.unit_type.astype(str)) - SKIP_TYPES):
        dest = CACHE / iso3 / f"features_{ut}.geojson"
        raw = _get(FEATURE_URL.format(iso2=ISO2[iso3], ut=ut), dest)
        try:
            gj = json.loads(raw)
        except Exception as e:  # noqa: BLE001
            info["features"][ut] = f"bad json: {e}"
            continue
        fn = [f.get("properties", {}).get("fnid") for f in gj.get("features", [])]
        have |= set(map(str, fn))
        info["features"][ut] = {"n_features": len(fn), "bytes": len(raw)}
    info["fnids_ipc"] = len(need)
    info["fnids_with_geometry"] = len(need & have)
    info["fnids_missing_geometry"] = sorted(need - have)[:20]
    return info


if __name__ == "__main__":
    out = {}
    for iso3 in (sys.argv[1:] or ["ZWE"]):
        try:
            out[iso3] = fetch_country(iso3)
        except Exception as e:  # noqa: BLE001
            out[iso3] = {"error": repr(e)}
        print(iso3, json.dumps({k: v for k, v in out[iso3].items() if k != "cs_months"}, default=str), flush=True)
    (CACHE / "fetch_geo_summary.json").write_text(json.dumps(out, indent=1, default=str))
