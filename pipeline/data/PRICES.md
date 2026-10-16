# Market price signals (pipeline/prices.py)

Signals per unit-month, contract long format in `prices_<ISO3>.parquet` (full unit x month grid; NaN = insufficient data, never 0).

| signal | definition | sign |
|---|---|---|
| price_anom | staple cereal retail price vs mean of the same calendar month in the previous 5 years (>= 3 years), %, clipped +-100; maize grain + maize meal, other cereals (sorghum/millet/rice/teff) only when a market has no maize value that month | higher = worse |
| livestock_price_anom | live goat/cattle/sheep/camel price, same baseline | natural sign: LOWER = worse (distress sales) |
| tot_anom | goat : maize-family terms of trade in the same market and currency, same baseline | natural sign: LOWER = worse for herders |

**Latency: prices for month m are published about 1 month later. Not shifted here; the model must lag these signals by 1 month (as in `common.LATENCY`).**

Sources: WFP food prices on HDX (CC BY-IGO; `wfp-food-prices-for-<country>`), FEWS NET Data Warehouse market price facts (ZW/KE/MW/ZM; anonymous API). Anomalies are computed per series (source, market, commodity, unit, currency, price type) and series are split at known redenominations and at any >20x month-to-month jump, so no baseline spans a currency change. Zimbabwe uses USD series only: nominal ZWL is hyperinflated and WFP's `usdprice` for ZWL rows is converted at the official rate (Oct 2023 maize: ZWL 1,875/kg -> "$0.028" vs $0.45-0.48 in real USD quotes), so neither is usable. Retail prices; wholesale only where a country-commodity has no retail series. FEWS NET Zimbabwe relabelled bucket units in Sep-Oct 2023 (`20_L` -> `17.5 kg`, `5_L` -> `4.5_kg`, same container); these are merged into one series (assumption).

Market -> unit: point-in-polygon on `units_<ISO3>.geojson`. Units with no market inside borrow the nearest market within 100 km of the unit centroid that has a value that month (`borrowed`); units with nothing within 100 km stay NaN (`none`).

## Coverage

| iso3 | signal | units direct | borrowed | none | units with a value Oct23-Apr24 | months with data | rows | markets (in unit) | series | breaks |
|---|---|---|---|---|---|---|---|---|---|---|
| ZWE | price_anom | 26 | 33 | 32 | 14/91 | 2007-04..2026-09 | 7788 | 159 (157) | 553 | 5 |
| KEN | price_anom | 44 | 2 | 1 | 44/47 | 2003-01..2026-09 | 22507 | 321 (317) | 802 | 0 |
| KEN | livestock_price_anom | 18 | 1 | 28 | 19/47 | 2003-01..2026-09 | 22507 | 321 (317) | 802 | 0 |
| KEN | tot_anom | 18 | 1 | 28 | 19/47 | 2003-01..2026-09 | 22507 | 321 (317) | 802 | 0 |
| MWI | price_anom | 27 | 1 | 0 | 18/28 | 2001-01..2026-09 | 35780 | 177 (174) | 721 | 12 |
| ZMB | price_anom | 69 | 13 | 34 | 16/116 | 2005-01..2026-07 | 44673 | 220 (219) | 1302 | 0 |
| MOZ | price_anom | 52 | 54 | 50 | 78/156 | 1995-12..2026-03 | 16516 | 98 (96) | 292 | 0 |
| TZA | price_anom | 44 | 107 | 19 | 84/170 | 2019-01..2026-08 | 10745 | 61 (60) | 175 | 0 |
| ETH | price_anom | 42 | 13 | 19 | 46/74 | 2009-07..2026-07 | 23156 | 101 (100) | 670 | 22 |
| ETH | livestock_price_anom | 39 | 10 | 25 | 40/74 | 2009-07..2026-07 | 23156 | 101 (100) | 670 | 22 |
| ETH | tot_anom | 31 | 5 | 38 | 27/74 | 2009-07..2026-07 | 23156 | 101 (100) | 670 | 22 |
| SOM | price_anom | 38 | 56 | 24 | 57/118 | 1998-02..2026-08 | 18848 | 46 (46) | 249 | 5 |
| SOM | livestock_price_anom | 27 | 42 | 49 | 0/118 | 1998-02..2026-08 | 18848 | 46 (46) | 249 | 5 |
| SOM | tot_anom | 25 | 41 | 52 | 4/118 | 1998-02..2026-08 | 18848 | 46 (46) | 249 | 5 |
| NAM | price_anom | 8 | 56 | 39 | 0/103 | 2013-01..2022-05 | 2523 | 8 (8) | 21 | 0 |
| BWA | - | - | - | - | - | - | no data  | | | |
| ZAF | price_anom | 1 | 5 | 46 | 0/52 | 2003-01..2022-06 | 539 | 1 (1) | 2 | 0 |
| MDG | price_anom | 34 | 48 | 37 | 8/119 | 2007-01..2026-08 | 14232 | 474 (474) | 1373 | 0 |
| AGO | price_anom | 1 | 4 | 152 | 0/157 | 2011-01..2020-12 | 320 | 2 (2) | 4 | 0 |
| UGA | price_anom | 39 | 109 | 3 | 135/151 | 2009-01..2026-08 | 12288 | 42 (42) | 172 | 2 |

## Notes per country

- **ZWE**: rows by source {'fdw': 4717, 'wfp': 3071}; rows by commodity group {'maize': 2691, 'maize_meal': 1209, 'millet': 1678, 'rice': 400, 'sorghum': 1810}; anomaly rows by group {'maize': 818, 'maize_meal': 214, 'millet': 261, 'sorghum': 247}; dropped 6885 non-USD rows.
- **KEN**: rows by source {'fdw': 17086, 'wfp': 5421}; rows by commodity group {'livestock': 6076, 'maize': 12638, 'maize_meal': 1672, 'millet': 301, 'rice': 1493, 'sorghum': 327}; anomaly rows by group {'livestock': 5176, 'maize': 7346, 'maize_meal': 338, 'millet': 191, 'rice': 159, 'sorghum': 7}.
- **MWI**: rows by source {'fdw': 10819, 'wfp': 24961}; rows by commodity group {'maize': 24248, 'maize_meal': 528, 'millet': 697, 'rice': 9370, 'sorghum': 937}; anomaly rows by group {'maize': 12529, 'rice': 3868, 'sorghum': 183}.
- **ZMB**: rows by source {'fdw': 6648, 'wfp': 38025}; rows by commodity group {'maize': 15375, 'maize_meal': 21385, 'millet': 640, 'rice': 7041, 'sorghum': 232}; anomaly rows by group {'maize': 10463, 'maize_meal': 11160, 'millet': 21, 'rice': 3387, 'sorghum': 3}.
- **MOZ**: rows by source {'wfp': 16516}; rows by commodity group {'maize': 5206, 'maize_meal': 3817, 'rice': 7493}; anomaly rows by group {'maize': 3816, 'maize_meal': 1578, 'rice': 4081}.
- **TZA**: rows by source {'wfp': 10745}; rows by commodity group {'maize': 2102, 'maize_meal': 2102, 'millet': 2925, 'rice': 2075, 'sorghum': 1541}; anomaly rows by group {'maize': 1185, 'maize_meal': 1185, 'millet': 1021, 'rice': 1156, 'sorghum': 515}.
- **ETH**: rows by source {'wfp': 23156}; rows by commodity group {'livestock': 9100, 'maize': 6195, 'millet': 89, 'rice': 1883, 'sorghum': 4223, 'teff': 1666}; anomaly rows by group {'livestock': 2960, 'maize': 2868, 'millet': 14, 'rice': 557, 'sorghum': 1455, 'teff': 364}.
- **SOM**: rows by source {'wfp': 18848}; rows by commodity group {'livestock': 1446, 'maize': 4877, 'rice': 5154, 'sorghum': 7371}; anomaly rows by group {'livestock': 268, 'maize': 2962, 'rice': 3121, 'sorghum': 3630}.
- **NAM**: rows by source {'wfp': 2523}; rows by commodity group {'maize_meal': 636, 'millet': 439, 'rice': 892, 'sorghum': 556}; anomaly rows by group {'maize_meal': 457, 'millet': 331, 'rice': 673, 'sorghum': 412}.
- **ZAF**: rows by source {'wfp': 539}; rows by commodity group {'maize': 539}; anomaly rows by group {'maize': 467}.
- **MDG**: rows by source {'wfp': 14232}; rows by commodity group {'maize': 706, 'maize_meal': 3108, 'rice': 10418}; anomaly rows by group {'maize_meal': 301, 'rice': 1845}.
- **AGO**: rows by source {'wfp': 320}; rows by commodity group {'maize_meal': 160, 'rice': 160}; anomaly rows by group {'maize_meal': 120, 'rice': 120}.
- **UGA**: rows by source {'wfp': 12288}; rows by commodity group {'maize': 3255, 'maize_meal': 3216, 'millet': 2680, 'rice': 195, 'sorghum': 2942}; anomaly rows by group {'maize': 1611, 'maize_meal': 1669, 'millet': 1278, 'rice': 159, 'sorghum': 1448}.

Per-unit detail: `prices_coverage.csv` (mode, n_markets, first/last month, n_months).

Known limits: Zimbabwe USD maize history is thin between 2019 and mid-2021 (WFP has no USD staples 2019-2023; FEWS NET USD series start 2021-07 for most markets), so the 3-of-5-years rule leaves most districts NaN in Oct 2023-Apr 2024: the values there come from the two long USD per-kg series (Harare, Makoni) and their <=100 km neighbours; the 22 FEWS NET bucket-unit markets only start 2021-07 and become usable from mid-2024. Relaxing to a 2-year baseline for those series would be a spec change (not done). Zambia: WFP collected only ~310-344 maize rows in 2022 and 2023 (vs ~2,000/yr before, 4,193 in 2024), so few ZMB units have values in the 2023-24 window. ZAF has one wholesale market (to 2022). BWA has no WFP dataset on HDX. Local-currency anomalies (all countries except ZWE) include general inflation; e.g. Malawi's Nov 2023 kwacha devaluation and Zambia's 2023-24 depreciation inflate price_anom.
