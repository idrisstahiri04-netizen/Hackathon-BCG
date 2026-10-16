# Data contract between pipeline and frontend

All helpers build to this. Do not change it without telling the orchestrator.

## Countries (config)
| iso3 | admin level | replay crisis | declaration date |
|---|---|---|---|
| ZWE | ADM2 (geoBoundaries, 91 units) | 2023-24 El Niño drought | 2024-04-03 |
| KEN | ADM1 (47 counties, matches existing prototype) | 2020-23 Horn of Africa drought | 2021-09-08 |
| MWI | ADM2 | 2023-24 El Niño drought | 2024-03-23 |
| ZMB | ADM2 | 2023-24 El Niño drought | 2024-02-29 |
MWI and ZMB dates verified by web search 2026-10-16. MWI: state of disaster in 23 of 28 districts declared by President Chakwera on 2024-03-23 (OCHA/Humanitarian Action https://humanitarianaction.info/article/malawi ; AP https://apnews.com/article/malawi-africa-drought-disaster-el-nino-ccdb755b84133d0e2796da3296410edf). ZMB: drought declared a national disaster and emergency by President Hichilema on Thursday 2024-02-29 (official statement https://www.cabinet.gov.zm/?p=2506 ; DMMU sitrep 1 https://reliefweb.int/report/zambia/republic-zambia-disaster-management-and-mitigation-unit-drought-response-situation-report-no-1-19th-april-2024 ; https://www.aljazeera.com/news/2024/2/29/zambia-declares-national-disaster-after-drought-devastates-agriculture).

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
     { t, level (0-3, after hysteresis), held (bool: level kept only by hysteresis, raw level lower), p (0-1 or null; satellite-event probability, information only), p_crisis (0-1 or null; FEWS NET-informed P(enter IPC3+ within 1-3 months), shown to NGOs as "chance of Crisis within 3 months"), confidence ("low"|"medium"|"high"),
       agreeing (int, number of families in alarm), families: { rain: bool, vegetation: bool, soil: bool, heat: bool },
       event ("none"|"cant_plant"|"crop_failure"|"no_grass"), horizon (weeks),
       drivers: [string, ...max 3], signals: { spi_1m, spi_3m, ndvi_z_crop, ndvi_z_grass, vci_crop, vci_grass, sm1_z, t2m_z } }
  ] } ]
}
```
Families: rain (SPI), vegetation (NDVI/VCI), soil (soil moisture). heat is supporting only, never counts toward the 2-family rule alone. Rules: Warning needs >= 2 of {rain, vegetation, soil} where rain and soil are both weather — so Warning requires vegetation + (rain or soil). v1.1 spec mode: Watch = any one family or strong rain+soil dryness; Warning = vegetation + (rain or soil); Emergency = Warning + official declaration in force (declaration month to end of that agricultural year). Levels never use p; p_crisis >= 0.57 (announcement/text family; precision-first CV point of the IPC model) may raise a level to Watch only, never Warning, and only where the latest published IPC phase is < 3 and only in the agricultural decision window (Oct-Apr for ZWE/MWI/ZMB = planting, growing and lean season; KEN = each own rainy season OND/MAM +/- 1 month). The window is an agricultural-calendar rule (when NGOs/officers can still act on planting, inputs and pre-positioning), fixed a priori, not tuned on replay outcomes; p is information (null if missing). Hysteresis: up to the level held for the last 2 runs, down after 3 runs below; no fast entry; `held` = true while a level is kept only by the 3-runs-down rule (families/agreeing then show the current, weaker evidence). Audiences add "herder" (event no_grass).
