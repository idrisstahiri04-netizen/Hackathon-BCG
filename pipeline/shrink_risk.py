"""Shrink data/risk/<ISO3>.js without changing what the UI reads (js/real.js, js/app.js).

    python pipeline/shrink_risk.py KEN

Rounds floats, drops null/empty/false fields (reader defaults them), drops forecast entries with no values,
drops target_label when it equals the month label the reader computes itself.
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIG_USED = {"spi_3m", "ndvi_z_crop", "sm1_z", "t2m_z"}      # the only signals js/real.js reads
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def lab(start_year, t):
    return f"{MON[t % 12]} {start_year + t // 12}"


def rnd(v, n=3):
    return round(v, n) if isinstance(v, float) else v


def shrink_row(r, sy):
    out = {}
    for k, v in r.items():
        if k == "forecast":
            fc = {}
            for L, f in v.items():
                g = {a: rnd(b) for a, b in f.items() if b is not None}
                if g.get("target_label") == lab(sy, r["t"] + int(L)):
                    del g["target_label"]
                if set(g) - {"target_label", "source"}:
                    fc[L] = g
            if fc:
                out[k] = fc
        elif k == "signals":
            s = {a: rnd(b, 2) for a, b in v.items() if b is not None and a in SIG_USED}
            if s:
                out[k] = s
        elif k in ("watch_reason", "p_crisis", "p") and v is None:
            continue
        elif k in ("held",) and not v:
            continue
        elif k == "families":
            out[k] = {a: True for a, b in v.items() if b}          # reader treats absent as false
        elif k == "drivers" and not v:
            continue
        else:
            out[k] = rnd(v)
    return out


def main(iso):
    f = ROOT / "data" / "risk" / f"{iso}.js"
    t = f.read_text()
    i = t.index(f'RISK_DATA["{iso}"] = ') + len(f'RISK_DATA["{iso}"] = ')
    head, d = t[:i], json.loads(t[i:].rstrip().rstrip(";"))
    if "fcf" in d["meta"]:
        return print(iso, "already shrunk")
    sy = d["meta"]["start_year"]
    g = ROOT / "pipeline" / "data" / f"units_{iso}SUB.geojson"      # sub-county units carry their parent county
    cty = {x["properties"]["shapeID"]: x["properties"]["county"] for x in json.loads(g.read_text())["features"]} if g.exists() else {}
    for u in d["units"]:
        if u["id"] in cty:
            u["county"] = cty[u["id"]]
        u["series"] = [shrink_row(r, sy) for r in u["series"]]
    # dictionary-encode the repeated forecast strings and store each lead as a fixed-order array
    # (meta.fcf = field order, meta.dict = string tables; 0 = same as the previous lead). Decoded in js/real.js.
    FCF = ["primary", "p", "fews_phase", "fews_scenario", "fews_published", "source", "target_label"]
    DICT = ("source", "fews_scenario", "fews_published", "primary", "target_label")
    idx = {k: {} for k in DICT}
    for u in d["units"]:
        for r in u["series"]:
            fc = r.get("forecast")
            if not fc:
                continue
            prev = None
            for L in list(fc):
                g = fc[L]
                assert set(g) <= set(FCF), set(g)
                arr = [(idx[k].setdefault(g[k], len(idx[k])) if k in DICT else g[k]) if k in g else None for k in FCF]
                while arr and arr[-1] is None:
                    arr.pop()
                fc[L] = 0 if arr == prev else arr
                prev = arr
    # row-level: string fields -> codes, families -> bitmask over FAM, signals -> array over SIGS (null = absent)
    RD = ("confidence", "event", "watch_reason")
    ridx = {k: {} for k in RD}
    FAM = ["rain", "vegetation", "soil", "heat"]
    SIGS = ["spi_3m", "ndvi_z_crop", "sm1_z", "t2m_z"]
    for u in d["units"]:
        for r in u["series"]:
            for k in RD:
                if isinstance(r.get(k), str):
                    r[k] = ridx[k].setdefault(r[k], len(ridx[k]))
            if "families" in r:
                assert set(r["families"]) <= set(FAM), r["families"]
                r["families"] = sum(1 << i for i, f in enumerate(FAM) if r["families"].get(f))
            if "signals" in r:
                assert set(r["signals"]) <= set(SIGS)
                a = [r["signals"].get(k) for k in SIGS]
                while a and a[-1] is None:
                    a.pop()
                r["signals"] = a
    d["meta"]["rowdict"] = {k: [x for x, _ in sorted(ridx[k].items(), key=lambda y: y[1])] for k in RD}
    d["meta"]["fam"], d["meta"]["sigs"] = FAM, SIGS
    d["meta"]["fcf"] = FCF
    d["meta"]["dict"] = {k: [x for x, _ in sorted(idx[k].items(), key=lambda y: y[1])] for k in DICT}
    f.write_text(head + json.dumps(d, separators=(",", ":"), allow_nan=False) + ";\n")
    print(iso, f.stat().st_size)


if __name__ == "__main__":
    main(sys.argv[1])
