#!/usr/bin/env python3
"""Sample ~10% of extracted statements (seeded) and print each with 250 chars of document context
around its evidence span, so a human can judge: does the quote support the (area, phase, window)?
Usage: python pipeline/outlooks/spot_check.py ZWE [frac] [seed]
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd

iso3 = sys.argv[1] if len(sys.argv) > 1 else "ZWE"
frac = float(sys.argv[2]) if len(sys.argv) > 2 else 0.10
seed = int(sys.argv[3]) if len(sys.argv) > 3 else 7
RAW = Path(__file__).resolve().parent.parent / "data" / "raw_outlooks"

rows = []
for f in sorted((RAW / "extractions").glob(f"{iso3}__*.json")):
    r = json.load(open(f))
    for i, st in enumerate(r["statements"]):
        rows.append({"doc_id": r["doc_id"], "idx": i, "pub": r["publication_date"], **st})
df = pd.DataFrame(rows)
sample = df.sample(frac=frac, random_state=seed).sort_values(["pub", "doc_id", "idx"])
print(f"{len(df)} statements, sampling {len(sample)}\n")


def ws(s):
    return re.sub(r"\s+", " ", s.replace("’", "'")).strip().lower()


for k, (_, s) in enumerate(sample.iterrows(), 1):
    d = RAW / iso3 / s.doc_id.split("__", 1)[1]
    text = (d / "text.txt").read_text(encoding="utf-8")
    t_ws, e_ws = ws(text), ws(s.evidence_span)
    j = t_ws.find(e_ws)
    ctx = t_ws[max(0, j - 250): j + len(e_ws) + 250] if j >= 0 else "(NOT FOUND)"
    print(f"--- #{k} {s.doc_id} (pub {s.pub}) stmt {s.idx}")
    print(f"    area={s.area_name!r} [{s.area_type}] {s.statement_type} phase={s.projected_phase} sev={s.projected_severity} "
          f"window={s.window_start}..{s.window_end} rain={s.rain_outlook} conf={s.confidence}")
    print(f"    QUOTE: {s.evidence_span}")
    print(f"    CONTEXT: ...{ctx}...\n")
