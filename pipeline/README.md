# Pipeline

Data contract: `CONTRACT.md` (section 1 = signals table, 2 = geometry, 3 = risk output).

## How to run

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r pipeline/requirements.txt
earthengine authenticate          # once; project drought-warning-zw-1016

# 1. Monthly signals per admin unit, 2001-01..2024-12 (Earth Engine, server-side)
python pipeline/extract_signals.py --iso3 ZWE --adm 2
python pipeline/extract_signals.py --iso3 KEN --adm 1
python pipeline/extract_signals.py --iso3 MWI --adm 2
python pipeline/extract_signals.py --iso3 ZMB --adm 2
#   -> pipeline/data/signals_<ISO3>.parquet  (long: unit_id, unit_name, iso3, month, signal_type, value)
#   -> pipeline/data/units_<ISO3>.geojson    (shapeID, shapeName, geometry)

# 2. Browser geometry (CONTRACT section 2)
python pipeline/prep_geo.py --iso3 ZWE KEN MWI ZMB      # -> data/geo/<ISO3>.js

# 3. Labels / features / placeholder risk
python pipeline/labels.py --iso3 ZWE
python pipeline/make_stub_risk.py                       # STUB data/risk/<ISO3>.js until the model exists
```

Notes
- Raw Earth Engine results are cached per dataset and year in `pipeline/cache/<ISO3>/`
  (gitignored). Reruns skip cached years; delete a file to refetch it. Derived signals
  (SPI, z-scores, VCI) are recomputed locally from the cache in seconds.
- Baseline for SPI (gamma fit per unit and calendar month, zeros as a mixed
  distribution), z-scores and VCI is 2001-2020.
- Missing data stays NaN, never 0 (e.g. units with no WorldCover cropland have no `ndvi_crop`).
- Sources: CHIRPS v3 pentad, MODIS MOD13Q1 v061 (SummaryQA <= 1), ERA5-Land monthly,
  ESA WorldCover v200 (crop = 40, grass/shrub = 30/20), geoBoundaries ADM1/ADM2.
