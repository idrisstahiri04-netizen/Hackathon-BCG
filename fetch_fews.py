"""
Pull real IPC food-insecurity phases for Kenya from the FEWS NET Data Warehouse.

This is ground truth. It is what the risk engine should be validated against,
and it is the dataset the project spec already names as the target
("precision and recall of Warning+ alerts against FEWS NET / IPC Phase 3+
transitions").

Source : https://fdw.fews.net/api/ipcphase/?format=json&country_code=KE
Licence: data_usage_policy = "Public" on every record
Auth   : none

The API has no server-side date or admin-level filter, so it returns every
Kenya record ever published - about 235 MB, 162k rows, 2011-2026. We download
once, cache the raw file, and reduce it to a small county-month table.

Output: data/fews-ipc-kenya.json
    { "meta": {...}, "counties": [...], "months": [...],
      "phases": { "<county>": { "<YYYY-MM>": 1..5 } } }

Phase scale (IPC): 1 Minimal, 2 Stressed, 3 Crisis, 4 Emergency, 5 Famine.
Note IPC Phase 3+ ("Crisis") is the humanitarian action threshold.
"""

import collections
import json
import os
import re
import urllib.request

RAW = "fews_kenya_ipc_raw.json"
OUT = "data/fews-ipc-kenya.json"
OUT_LHZ = "data/kenya-livelihoods.json"
URL = "https://fdw.fews.net/api/ipcphase/?format=json&country_code=KE"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"

PHASE = {"Minimal": 1, "Stressed": 2, "Crisis": 3, "Emergency": 4, "Famine": 5}

# Demo window, matching js/sim.js
START, END = "2019-01", "2025-01"


def download():
    if os.path.exists(RAW):
        print(f"using cached {RAW} ({os.path.getsize(RAW)/1e6:.0f} MB)")
        return
    print("downloading ~235 MB from FEWS NET, this takes about 30s...")
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r, open(RAW, "wb") as fh:
        fh.write(r.read())
    print(f"saved {RAW} ({os.path.getsize(RAW)/1e6:.0f} MB)")


def county_of(record):
    """Unit names look like
         "<Livelihood Zone>, <Sub-county>, <County>, Kenya"      (2017+)
         "<Unit>, <County>, <Province>, Kenya"                   (pre-2017)
    so the county sits second-from-last before the country."""
    parts = [p.strip() for p in record["geographic_unit_full_name"].split(",")]
    return parts[-2] if len(parts) >= 3 else None


# The livelihood zone is the leading part of the unit name, before the
# sub-county. Zone names themselves can contain commas ("Central Highlands,
# High Potential Zone"), so we cut at the last taxonomy keyword rather than
# at a fixed comma position.
BASE_ZONE = re.compile(r"^(.*?\b(?:Zone|Fishing|Farming))\b", re.I)


def livelihood_zones(rows):
    """county -> [livelihood zones, most common first].

    This is real FEWS NET livelihood classification, not our invention. It is
    what makes the recommendations specific: a pastoral county gets livestock
    advice, a high-potential county gets grain advice.
    """
    per_county = collections.defaultdict(collections.Counter)
    for r in rows:
        full = r["geographic_unit_full_name"]
        if full.count(",") < 2:
            continue
        parts = [p.strip() for p in full.split(",")]
        head = ", ".join(parts[:-2])            # drop "<County>, Kenya"
        m = BASE_ZONE.match(head)
        zone = re.sub(r"\s+", " ", (m.group(1) if m else parts[0]).strip())
        per_county[parts[-2]][zone] += 1
    return {c: [z for z, _ in v.most_common()] for c, v in per_county.items()}


def main():
    download()
    print("parsing...")
    with open(RAW) as fh:
        raw = json.load(fh)

    # "Current Situation" only. ML1/ML2 are FEWS NET's own near- and
    # medium-term projections - keep them out of the label set, they are a
    # forecasting baseline to compare against, not ground truth.
    rows = [
        r for r in raw
        if r.get("scenario") == "CS"
        and r.get("unit_type") == "fsc_admin_lhz"
        and r.get("reporting_date")
        and START <= r["reporting_date"][:7] < END
    ]

    # A county spans several livelihood zones. Take the worst zone: a county is
    # in Crisis if any meaningful part of it is, which is how these
    # classifications are read operationally.
    agg = collections.defaultdict(int)
    for r in rows:
        c, v = county_of(r), PHASE.get(r["description"])
        if c and v:
            key = (c, r["reporting_date"][:7])
            agg[key] = max(agg[key], v)

    counties = sorted({k[0] for k in agg})
    months = sorted({k[1] for k in agg})

    phases = collections.defaultdict(dict)
    for (c, m), v in agg.items():
        phases[c][m] = v

    # Sanity-check the join against the geometry we actually render.
    with open("data/kenya-counties.js") as fh:
        geo = json.loads(fh.read().split("=", 1)[1].rstrip(";\n"))
    ours = {f["properties"]["name"] for f in geo["features"]}
    norm = lambda s: re.sub(r"[^a-z]", "", s.lower())
    have = {norm(c) for c in counties}
    missing = sorted(o for o in ours if norm(o) not in have)

    out = {
        "meta": {
            "source": "FEWS NET Data Warehouse (fdw.fews.net), IPC phase, Current Situation",
            "url": URL,
            "licence": "Public (data_usage_policy on every record)",
            "scale": {1: "Minimal", 2: "Stressed", 3: "Crisis", 4: "Emergency", 5: "Famine"},
            "aggregation": "max phase across the livelihood zones within each county",
            "window": [START, END],
            "n_observations": len(agg),
        },
        "counties": counties,
        "months": months,
        "phases": dict(phases),
    }
    os.makedirs("data", exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(out, fh, separators=(",", ":"), sort_keys=True)

    print(f"\n{len(counties)} counties x {len(months)} reporting months "
          f"= {len(agg)} observations")
    print(f"matched against rendered geometry: {47 - len(missing)}/47"
          + (f"  MISSING: {missing}" if missing else ""))
    print(f"wrote {OUT} ({os.path.getsize(OUT)/1024:.0f} KB)")

    worst = collections.Counter()
    for c, ms in phases.items():
        worst[max(ms.values())] += 1
    print("counties by worst phase reached:",
          {["", "Minimal", "Stressed", "Crisis", "Emergency", "Famine"][k]: v
           for k, v in sorted(worst.items())})

    # --- livelihood zones (drives the recommendations) ---------------------
    lhz = livelihood_zones(
        r for r in raw
        if r.get("unit_type") == "fsc_admin_lhz" and r.get("reporting_date", "") >= "2019"
    )
    with open(OUT_LHZ, "w") as fh:
        json.dump({
            "meta": {
                "source": "FEWS NET livelihood zones, parsed from fsc_admin_lhz unit names",
                "url": URL,
                "note": "county -> livelihood zones present, most common first",
            },
            "zones": lhz,
        }, fh, separators=(",", ":"), sort_keys=True)
    allz = sorted({z for v in lhz.values() for z in v})
    print(f"\nlivelihood zones: {len(allz)} distinct across {len(lhz)} counties")
    print(f"wrote {OUT_LHZ} ({os.path.getsize(OUT_LHZ)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
