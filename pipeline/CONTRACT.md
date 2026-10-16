# Data contract between pipeline and frontend

All helpers build to this. Do not change it without telling the orchestrator.

## Countries (config)
The **declaration date must stay the last column** (`pipeline/export_risk.py: contract_declaration` reads the first
`YYYY-MM-DD` in the last cell of the row whose first cell is the iso3; "none found" = no declaration, no Emergency level).
Source URLs live in the column before it so URL dates can never be mistaken for the declaration.

| iso3 | admin level | replay crisis | source (verified 2026-10-16) | declaration date |
|---|---|---|---|---|
| ZWE | ADM2 (geoBoundaries, 91 units) | 2023-24 El Niño drought | National state of disaster (drought), President Mnangagwa 3 Apr 2024 (spec; see data/sources.yaml) | 2024-04-03 |
| KEN | ADM1 (47 counties, matches existing prototype) | 2020-23 Horn of Africa drought | Drought declared a national disaster by President Kenyatta, 8 Sep 2021 (see data/sources.yaml) | 2021-09-08 |
| MWI | ADM2 (28 districts) | 2023-24 El Niño drought | State of disaster in 23 of 28 districts, President Chakwera (see paragraph below) | 2024-03-23 |
| ZMB | ADM2 (116 districts) | 2023-24 El Niño drought | Drought declared national disaster and emergency, President Hichilema (see paragraph below) | 2024-02-29 |
| MOZ | ADM2 (156 districts) | 2023-24 El Niño drought (centre/south) | none found. Only a flood-driven national orange alert of 27 Feb 2024 (AIM https://aimnews.org/2024/02/27/governo-mocambicano-decreta-alerta-laranja/) and a Government-UN drought Flash Appeal, Aug 2024 (https://humanitarianaction.info/plan/1207/article/mozambique-drought-flash-appeal-2024-2025); no national drought declaration | none found |
| TZA | ADM2 (170 districts) | 2022-23 dry season (Drought Contingency Plan only) | none found. No national drought/food emergency declared 2019-2024 (last one 1997); 2022-23 Drought Contingency Plan is a plan, not a declaration (https://actalliance.org/?p=270748) | none found |
| ETH | ADM2 (74 zones) | 2020-23 Horn of Africa drought | none found. Federal government issued no declaration; humanitarian appeals only (OCHA Horn of Africa drought overview, revised 28 Nov 2022 https://reliefweb.int/report/ethiopia/horn-africa-drought-regional-humanitarian-overview-call-action-revised-28-november-2022) | none found |
| SOM | ADM2 (118 districts) | 2020-23 Horn of Africa drought | PM Mohamed Hussein Roble declared a drought state of emergency after an extraordinary cabinet meeting, Tue 23 Nov 2021 (Anadolu https://www.aa.com.tr/en/africa/somalia-declares-state-of-emergency-over-deadly-drought/2428567 ; OCHA bulletin https://reliefweb.int/report/somalia/somalia-humanitarian-bulletin-november-2021) | 2021-11-23 |
| NAM | ADM2 (103 constituencies) | 2023-24 El Niño drought (earlier: 2018/19 drought) | Presidential Proclamation 18, Government Gazette 8370: "with effect from 22 May 2024, a State of Emergency exists in Namibia on account of the persisting national disaster of drought" (https://www.lac.org.na/laws/2024/8370.pdf). Earlier: Proclamation 14, GG 6900, w.e.f. 6 May 2019 (https://www.lac.org.na/laws/2019/6900.pdf) | 2024-05-22 |
| BWA | ADM2 (25 districts/sub-districts) | 2023-24 El Niño drought (earlier: 2018/19 drought year, declared 20 May 2019 https://dailynews.gov.bw/news-detail/49316) | President Masisi declared 2023/24 an "extreme agricultural drought year"; government statement issued Thursday 20 Jun 2024 (Xinhua 21 Jun 2024 https://english.news.cn/20240621/017ce752ddc4420ebf6970a3879ba2f3/c.html ; ReliefWeb https://reliefweb.int/disaster/dr-2024-000091-bwa). Drought-year declaration, not a formal state of disaster | 2024-06-20 |
| ZAF | ADM2 (52 district + metropolitan municipalities) | 2018-20 drought (no national declaration for 2023-24) | Minister of CoGTA declared a National State of Disaster: Drought, Government Notice 243, Gazette 43066, 4 Mar 2020; extended by GN 632, lapsed 4 Jul 2020 (CoGTA https://www.cogta.gov.za/index.php/2020/03/05/drought-declared-a-national-disaster/ ; gazette https://www.saflii.org/za/gaz/ZAGovGaz/saggv657n43066d04m2020450.pdf) | 2020-03-04 |
| MDG | ADM2 (119 districts) | 2020-21 Grand Sud drought | none found. Government-UN Flash Appeal (Jan 2021) and a National Response Plan, no national "état de catastrophe" located (ReliefWeb disaster page https://reliefweb.int/disaster/dr-2018-000141-mdg) | none found |
| AGO | ADM2 (157 municipalities) | 2019-21 southern drought (Cunene, Huíla, Namibe) | none found at national level. Cunene provincial government declared "estado de calamidade" late Feb 2019 (Lusa/DN https://www.dn.pt/lusa/ministro-da-agricultura-angolano-quer-solucoes-definitivas-para-acudir-a-seca-no-cunene--10748746.html); an Al Jazeera caption claiming a presidential state of emergency in Jan 2019 could not be corroborated | none found |
| UGA | ADM2 (151 districts) | 2022 Karamoja hunger crisis | none found. Cabinet relief package and ministerial disaster-status statement to Parliament, 14 Jul 2022; no national declaration (https://eagle.co.ug/2022/07/15/govt-turns-to-partners-over-karamoja-hunger/) | none found |

New-country rows researched 2026-10-16 (web search, primary gazette/government pages fetched for NAM, ZAF, BWA, SOM; ReliefWeb pages returned 403 at the time and are cited from search results). MWI and ZMB dates verified by web search 2026-10-16. MWI: state of disaster in 23 of 28 districts declared by President Chakwera on 2024-03-23 (OCHA/Humanitarian Action https://humanitarianaction.info/article/malawi ; AP https://apnews.com/article/malawi-africa-drought-disaster-el-nino-ccdb755b84133d0e2796da3296410edf). ZMB: drought declared a national disaster and emergency by President Hichilema on Thursday 2024-02-29 (official statement https://www.cabinet.gov.zm/?p=2506 ; DMMU sitrep 1 https://reliefweb.int/report/zambia/republic-zambia-disaster-management-and-mitigation-unit-drought-response-situation-report-no-1-19th-april-2024 ; https://www.aljazeera.com/news/2024/2/29/zambia-declares-national-disaster-after-drought-devastates-agriculture).

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
- dry-spell / season timing (CHIRPS v3 pentad), stored separately in `pipeline/data/dryspell_<ISO3>.parquet` (same long format; see pipeline/dryspell/report.md). Feed the probability model only, never alert levels:
  - dry_spell_max      longest run of consecutive pentads < 5 mm since season onset (NaN outside onset .. last rainy month + 1)
  - days_since_rain    pentads since the last pentad >= 10 mm, cap 36
  - onset_anom         onset pentad minus 2001-2020 median onset (+ = late; censored before onset)
  - season_rain_pct    season-to-date rain as % of the 2001-2020 mean of the same partial sum

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

## 4. Forecast fields (added for the Forecast view)
Each series row MAY carry:
```
forecast: {
  "1": { p, p_crisis, target_label },   // chance for the window starting 1 month after the issue month
  "2": { p, p_crisis, target_label },
  "3": { p, p_crisis, target_label }    // p = Model A (bad season, event per season phase), p_crisis = Model B (IPC3+), null if unavailable
}
```
All values out-of-sample (CV fold model for CV seasons, final model for hold-out/live). `target_label` e.g. "Apr 2024".
meta.n_months may exceed 72 when live months are added (t=0 is still Jan 2019); meta.live_t = index of the latest issued month ("today") or null.

### 4b. Extended horizon to +8 months (user request: follow the FEWS NET outlook cycle)
`forecast` keys may go "1".."8". Per lead:
```
{ p, p_crisis, fews_phase, fews_scenario, fews_published, target_label, source }
```
- p: Model A chance (bad season) — available as far as the model has skill-tested leads (≥ 1..6 with NMME m1-3/m4-6 + ONI); null beyond.
- p_crisis: Model B (IPC) — h13 for leads 1–3, h46 for 4–6 if trained; null beyond.
- fews_phase: FEWS NET projected IPC phase (1–5) for the target month from the LATEST outlook published on or before the issue month (ML1 = near term ≈ first 4 months, ML2 = medium term ≈ months 5–8); fews_scenario "ML1"/"ML2"; fews_published = publication month. Null if no outlook covers that month (e.g. FEWS NET pause 2025). Unit value = area-weighted worst phase covering ≥20% (same mapping as ipc_units).
- source: short text, e.g. "model+FEWS ML1".
Expected visual effect: the FEWS NET layer changes in steps when a new outlook is published (~every 4 months); our model updates monthly.
