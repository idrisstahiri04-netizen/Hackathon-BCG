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
    sy = d["meta"]["start_year"]
    g = ROOT / "pipeline" / "data" / f"units_{iso}SUB.geojson"      # sub-county units carry their parent county
    cty = {x["properties"]["shapeID"]: x["properties"]["county"] for x in json.loads(g.read_text())["features"]} if g.exists() else {}
    for u in d["units"]:
        if u["id"] in cty:
            u["county"] = cty[u["id"]]
        u["series"] = [shrink_row(r, sy) for r in u["series"]]
    f.write_text(head + json.dumps(d, separators=(",", ":"), allow_nan=False) + ";\n")
    print(iso, f.stat().st_size)


if __name__ == "__main__":
    main(sys.argv[1])
