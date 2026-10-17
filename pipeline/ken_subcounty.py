"""Kenya sub-county export. Sub-counties inherit their parent county's seasonal forecast (NMME ~1 deg, coarser
than counties) and market prices (market-level), then export_risk scores the existing models as country KEN.

    python pipeline/ken_subcounty.py   # builds pipeline/cache/ken_sub/ (KENSUB files renamed to KEN) and exports data/risk/KEN.js
"""
import json, shutil, subprocess, sys
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
D = HERE / "data"
T = HERE / "cache" / "ken_sub"
ALIAS = {"Tharaka-Nithi": "Tharaka", "Tharaka Nithi": "Tharaka"}


def county_map():
    cid = {f["properties"]["shapeName"]: f["properties"]["shapeID"]
           for f in json.load(open(D / "units_KEN.geojson"))["features"]}
    sub = {f["properties"]["shapeID"]: cid[ALIAS.get(f["properties"]["county"], f["properties"]["county"])]
           for f in json.load(open(D / "units_KENSUB.geojson"))["features"]}
    return sub


def inherit(df, sub, names):
    rows = []
    for s, c in sub.items():
        x = df[df.unit_id == c].copy()
        x["unit_id"] = s
        if "unit_name" in x:
            x["unit_name"] = names[s]
        rows.append(x)
    return pd.concat(rows, ignore_index=True)


def main():
    if T.exists():
        shutil.rmtree(T)
    T.mkdir(parents=True)
    for f in D.iterdir():
        if "KEN" in f.name and "KENSUB" not in f.name:
            continue
        n = f.name.replace("KENSUB", "KEN")
        (T / n).symlink_to(f)
    sub = county_map()
    names = {f["properties"]["shapeID"]: f["properties"]["shapeName"]
             for f in json.load(open(D / "units_KENSUB.geojson"))["features"]}
    for n in ["seasonal_fc_KEN", "prices_KEN"]:
        inherit(pd.read_parquet(D / f"{n}.parquet"), sub, names).to_parquet(T / f"{n}.parquet")
    # out dir with live p_crisis (eo_fews / FEWS-proxy, h13+h46) inherited from the parent county; rest symlinked
    O = HERE / "cache" / "ken_sub_out"
    if O.exists():
        shutil.rmtree(O)
    O.mkdir(parents=True)
    for f in (HERE / "out").iterdir():
        if f.name not in ("ipc_eofews_live.parquet", "ipc_proxy_live.parquet"):
            (O / f.name).symlink_to(f)
    for n in ["ipc_eofews_live", "ipc_proxy_live"]:
        d = pd.read_parquet(HERE / "out" / f"{n}.parquet")
        k = d[d.iso3 == "KEN"]
        pd.concat([d[d.iso3 != "KEN"], inherit(k, sub, names)], ignore_index=True).to_parquet(O / f"{n}.parquet")
    subprocess.run([sys.executable, str(HERE / "export_risk.py"), "--iso3", "KEN", "--data-dir", str(T),
                    "--out-dir", str(O)], check=True)


if __name__ == "__main__":
    main()
