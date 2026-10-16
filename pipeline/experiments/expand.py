"""Build training-only rows for additional countries (pipeline/data/signals_<ISO3>.parquet).

    python pipeline/experiments/expand.py MOZ TZA ETH ...     # whichever files exist are used

Outputs rows_extra.parquet (leads 0-6, latency applied by train.prepare_country), wide_extra.parquet,
seasons_extra.json and appends centroids to unit_centroids.parquet. Agyears >= 2023 are dropped
entirely: the 2023/24 season is the hold-out for the core countries and the same regional drought,
so it must not enter training through a neighbour.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = Path(os.environ.get("EXP_OUT", str(HERE)))   # artefacts (caches, OOF, results); HERE = code + small data
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import harness as H                                  # noqa: E402
import train as T                                    # noqa: E402
from common import DATA_DIR, TEST_FROM_AGYEAR        # noqa: E402
from features import make_xy                         # noqa: E402


centroids = H.centroids


def main(iso3s):
    have = [i for i in iso3s if (DATA_DIR / f"signals_{i}.parquet").exists()]
    print("available:", have, "missing:", [i for i in iso3s if i not in have])
    rows, wides, seas, cens = [], [], {}, []
    for i in have:
        try:
            P = T.prepare_country(i, DATA_DIR)
        except Exception as e:                # noqa: BLE001
            print(f"  !! {i}: {e}"); continue
        X = make_xy(P["feat"], P["targets"], H.ALL_LEADS, P["plant"], P["bim"])
        X = T.add_families(X, P["ss"])
        X = X[X.agyear < TEST_FROM_AGYEAR].copy()
        X["test"] = False
        rows.append(X)
        w = P["c"].wide.copy(); w["iso3"] = i; wides.append(w.reset_index())
        for u, ss in P["ss"].items():
            seas[u] = dict(iso3=i, plant=P["plant"][u], bimodal=bool(P["bim"][u]),
                           seasons=[dict(core_start=s.core_start, rainy=s.rainy, planting=s.planting, crop=s.crop, grass=s.grass) for s in ss])
        if (DATA_DIR / f"units_{i}.geojson").exists():
            cens.append(centroids(i, DATA_DIR))
        cv = X[X.lead == 1]
        print(f"  {i}: units={X.unit_id.nunique()} rows={len(X)} label rate:",
              cv.groupby("event").label.mean().round(3).to_dict())
    if not rows:
        return
    R = pd.concat(rows, ignore_index=True)
    R.to_parquet(OUT / "rows_extra.parquet", index=False)
    pd.concat(wides, ignore_index=True).to_parquet(OUT / "wide_extra.parquet", index=False)
    (OUT / "seasons_extra.json").write_text(json.dumps(seas))
    if cens:
        c0 = pd.read_parquet(OUT / "unit_centroids.parquet")
        c = pd.concat([c0] + cens, ignore_index=True).drop_duplicates("unit_id", keep="last")
        c.to_parquet(OUT / "unit_centroids.parquet", index=False)
    for f in ("extra_um_extra.parquet",):
        (OUT / f).unlink(missing_ok=True)
    print(f"rows_extra: {len(R)} rows, {R.unit_id.nunique()} units, countries {sorted(R.iso3.unique())}")


if __name__ == "__main__":
    main([a.upper() for a in sys.argv[1:]] or ["MOZ", "TZA", "ETH", "SOM", "NAM", "BWA", "ZAF", "MDG", "AGO", "UGA"])
