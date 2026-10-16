"""
PLACEHOLDER risk output, so the frontend can be built before the model exists.

    python3 pipeline/make_stub_risk.py                 # ZWE MWI ZMB
    python3 pipeline/make_stub_risk.py --iso3 ZWE KEN

Writes data/risk/<ISO3>.js in the exact CONTRACT.md section 3 shape with
meta.model_version = "STUB". Every number is invented (a smooth bump centred a
few months before the declaration date plus deterministic noise). The real
model overwrites these files. KEN is not in the default list so the Kenya
prototype keeps its scripted simulation (js/sim.js) until real output exists.

Needs data/geo/<ISO3>.js (run pipeline/prep_geo.py first).
"""

import argparse
import datetime as dt
import hashlib
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
START_YEAR, N_MONTHS = 2019, 72
COUNTRIES = {
    "ZWE": ("Zimbabwe", "2024-04-03", "National state of disaster declared (drought)"),
    "MWI": ("Malawi", "2024-03-23", "State of disaster declared in 23 of 28 districts"),
    "ZMB": ("Zambia", "2024-02-29", "Drought declared a national disaster and emergency"),
    "KEN": ("Kenya", "2021-09-08", "Drought declared a national disaster"),
}


def noise(*key):
    h = hashlib.md5("|".join(map(str, key)).encode()).digest()
    return int.from_bytes(h[:4], "big") / 2**32 * 2 - 1     # -1 .. 1


def load_geo(iso3):
    txt = open(os.path.join(ROOT, "data", "geo", f"{iso3}.js")).read()
    body = txt.split(f'GEO_DATA["{iso3}"] = ', 1)[1].rstrip().rstrip(";")
    return json.loads(body)["features"]


def series_for(iso3, uid, grass, decl_t):
    sens = 0.55 + 0.45 * (noise(uid, "sens") + 1) / 2      # how hard the unit is hit
    out, level, run_lvl, run_n = [], 0, 0, 0
    for t in range(N_MONTHS):
        m = t % 12
        bump = math.exp(-((t - (decl_t - 2)) / 4.5) ** 2)    # crisis bump
        sev = sens * bump + 0.12 * noise(uid, t, "n")
        spi3 = round(-2.6 * sev + 0.3 * noise(uid, t, "spi"), 2)
        spi1 = round(spi3 + 0.4 * noise(uid, t, "spi1"), 2)
        ndc = round(-2.2 * math.exp(-((t - (decl_t - 1)) / 4.5) ** 2) * sens + 0.3 * noise(uid, t, "ndc"), 2)
        ndg = round(ndc * (0.8 + 0.3 * (grass or 0.3)) + 0.2 * noise(uid, t, "ndg"), 2)
        sm1 = round(-2.0 * sev + 0.3 * noise(uid, t, "sm"), 2)
        t2m = round(1.5 * sev + 0.3 * noise(uid, t, "t2m"), 2)
        fam = {"rain": spi3 < -1.0, "vegetation": min(ndc, ndg) < -1.0,
               "soil": sm1 < -1.0, "heat": t2m > 1.0}
        agreeing = sum(fam[k] for k in ("rain", "vegetation", "soil"))
        p = round(1 / (1 + math.exp(-(3.2 * sev - 1.6))), 3)
        raw = 3 if p >= 0.75 else 2 if p >= 0.5 else 1 if p >= 0.3 else 0
        if not (fam["vegetation"] and (fam["rain"] or fam["soil"])):
            raw = min(raw, 1)
        run_lvl, run_n = (raw, run_n + 1) if raw == run_lvl else (raw, 1)
        if raw != level and run_n >= (2 if raw > level else 3):
            level = raw
        if level == 0:
            event = "none"
        elif m in (10, 11, 0):
            event = "cant_plant"
        elif (grass or 0) > 0.45 or noise(uid, "pastoral") > 0.5:
            event = "no_grass"
        else:
            event = "crop_failure"
        drivers = []
        if fam["rain"]:
            drivers.append(f"3-month rain index {spi3:.1f} (very dry)")
        if fam["vegetation"]:
            drivers.append(f"crop greenness {ndc:.1f} below normal")
        if fam["soil"]:
            drivers.append(f"topsoil moisture {sm1:.1f} below normal")
        out.append({
            "t": t, "level": level, "p": p,
            "confidence": "high" if agreeing >= 3 else "medium" if agreeing == 2 else "low",
            "agreeing": agreeing, "families": fam, "event": event,
            "horizon": 8 if event == "no_grass" else 10,
            "drivers": drivers[:3],
            "signals": {"spi_1m": spi1, "spi_3m": spi3, "ndvi_z_crop": ndc, "ndvi_z_grass": ndg,
                        "vci_crop": round(max(0, min(100, 50 + 20 * ndc)), 1),
                        "vci_grass": round(max(0, min(100, 50 + 20 * ndg)), 1),
                        "sm1_z": sm1, "t2m_z": t2m},
        })
    return out


def build(iso3):
    country, date, label = COUNTRIES[iso3]
    d = dt.date.fromisoformat(date)
    decl_t = (d.year - START_YEAR) * 12 + d.month - 1
    units = [{"id": f["properties"]["id"], "name": f["properties"]["name"],
              "series": series_for(iso3, f["properties"]["id"], f["properties"].get("grass"), decl_t)}
             for f in load_geo(iso3)]
    doc = {
        "meta": {"iso3": iso3, "country": country, "start_year": START_YEAR, "n_months": N_MONTHS,
                 "declaration": {"t": decl_t, "date": date, "label": label},
                 "model_version": "STUB",
                 "metrics": {"note": "PLACEHOLDER VALUES - not model output"},
                 "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")},
        "units": units,
    }
    os.makedirs(os.path.join(ROOT, "data", "risk"), exist_ok=True)
    path = os.path.join(ROOT, "data", "risk", f"{iso3}.js")
    with open(path, "w") as fh:
        fh.write("// STUB risk output - PLACEHOLDER numbers from pipeline/make_stub_risk.py.\n")
        fh.write("// Overwritten by the real model. Shape: pipeline/CONTRACT.md section 3.\n")
        fh.write("window.RISK_DATA = window.RISK_DATA || {};\n")
        fh.write(f'RISK_DATA["{iso3}"] = {json.dumps(doc, separators=(",", ":"))};\n')
    print(f"[{iso3}] STUB {len(units)} units -> {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso3", nargs="+", default=["ZWE", "MWI", "ZMB"])
    for iso in ap.parse_args().iso3:
        build(iso.upper())
