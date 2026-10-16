# Data contract between pipeline and frontend

All helpers build to this. Do not change it without telling the orchestrator.

## Countries (config)
| iso3 | admin level | replay crisis | declaration date |
|---|---|---|---|
| ZWE | ADM2 (geoBoundaries, 91 units) | 2023-24 El Niño drought | 2024-04-03 |
| KEN | ADM1 (47 counties, matches existing prototype) | 2020-23 Horn of Africa drought | 2021-09-08 |
| MWI | ADM2 | 2023-24 El Niño drought | 2024-03-23 |
| ZMB | ADM2 | 2023-24 El Niño drought | 2024-02-29 |
MWI and ZMB dates verified 2026-10-16: MWI state of disaster declared by President Chakwera on 2024-03-23 (23 of 28 districts; https://www.africanews.com/2024/03/25/malawi-declares-state-of-disaster-over-drought-wrought-by-el-nino/); ZMB national disaster and emergency declared by President Hichilema on 2024-02-29 (https://www.aljazeera.com/news/2024/2/29/zambia-declares-national-disaster-after-drought-devastates-agriculture, https://zambia.un.org/en/node/271472).

Unit id = geoBoundaries `shapeID`. Unit name = `shapeName`.

## 1. Signals table (pipeline/data/signals_<ISO3>.parquet), long format
columns: unit_id, unit_name, iso3, month (YYYY-MM-01), signal_type, value
signal_type (monthly, 2001-01 .. 2024-12):
- precip_mm            CHIRPS v3 pentad summed to month (mean over unit)
- spi_1m, spi_3m, spi_6m   standardized precipitation index (gamma fit per unit & calendar month, baseline 2001-2020)
- ndvi_crop, ndvi_grass    MODIS MOD13Q1 NDVI monthly mean, QA-filtered, masked to WorldCover 40 (crop) / 30+20 (grass+shrub)
- ndvi_z_crop, ndvi_z_grass  z-score vs same calendar month 2001-2020
- vci_crop, vci_grass      VCI 0-100 vs per-unit per-calendar-month min/max 2001-2020
- sm1_z, sm2_z             ERA5-Land volumetric_soil_water_layer_1/2 z-score
- t2m_z                    ERA5-Land temperature_2m z-score
- crop_frac, grass_frac    static share of unit area (store with month = 2001-01-01)

## 2. Geometry for the globe (data/geo/<ISO3>.js)
`window.GEO_DATA = window.GEO_DATA || {}; GEO_DATA["ZWE"] = <FeatureCollection>;`
feature.properties: id, name, lat, lng (centroid), pop (millions, WorldPop 2020 if available else null), crop (frac), grass (frac).
Rings clockwise (see prep_data.py note), simplified, 3 dp.

## 3. Risk output for the frontend (data/risk/<ISO3>.js)
`window.RISK_DATA = window.RISK_DATA || {}; RISK_DATA["ZWE"] = {...}`
```
{
  meta: { iso3, country, start_year: 2019, n_months: 72,
          declaration: { t, date, label }, model_version, metrics: {...}, generated_at },
  units: [ { id, name, series: [   // length n_months, t = 0 is Jan 2019
     { t, level (0-3, after hysteresis), p (0-1), confidence ("low"|"medium"|"high"),
       agreeing (int, number of families in alarm), families: { rain: bool, vegetation: bool, soil: bool, heat: bool },
       event ("none"|"cant_plant"|"crop_failure"|"no_grass"), horizon (weeks),
       drivers: [string, ...max 3], signals: { spi_1m, spi_3m, ndvi_z_crop, ndvi_z_grass, vci_crop, vci_grass, sm1_z, t2m_z } }
  ] } ]
}
```
Families: rain (SPI), vegetation (NDVI/VCI), soil (soil moisture). heat is supporting only, never counts toward the 2-family rule alone. Rules: Warning needs >= 2 of {rain, vegetation, soil} where rain and soil are both weather — so Warning requires vegetation + (rain or soil). Hysteresis: 2 runs up, 3 runs down. Audiences add "herder" (event no_grass).
