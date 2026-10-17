#!/usr/bin/env python3
"""Run extend_live signals + dryspell steps for the 290 Kenya sub-counties (tag KENSUB).
    python pipeline/live/extend_kensub.py
Same masking/verification as extend_live.py; sub-county geometries from pipeline/data/units_KENSUB.geojson.
"""
import sys
from pathlib import Path
import extend_live as el

GJ = str(el.DATA / "units_KENSUB.geojson")
el.ADM["KENSUB"] = 1
_orig = el.es.main


def _main():
    sys.argv += ["--geojson", GJ, "--tag", "KENSUB"]
    _orig()


el.es.main = _main

if __name__ == "__main__":
    import ee
    ee.Initialize(project=el.es.EE_PROJECT)
    comp = el.completeness(2026)
    st = el.load_status()
    el.step_signals("KENSUB", 2026, comp, st)
    el.step_dryspell("KENSUB", 2026, comp, st)
    el.save_status(st)
