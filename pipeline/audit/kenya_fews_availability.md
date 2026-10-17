# Kenya FEWS NET layer: availability audit (UI vs decoded data)

Run: fresh Chrome context per URL (hard refresh), own server :8880, `?country=Kenya&t=N&view=fK&layer=fews&role=gov`.
Scripts: `tests/e2e/ken_fews_audit.js` (flow, 64 URL loads, "Our model"/"Both" spot checks) and `tests/e2e/ken_fews_sweep.js` (all t=0..92 x +1/+3/+6, legend counts read from the UI).
Screenshots: `tests/e2e/screens/ken_fews_*.png`.

## Result
- Flow: landing visible -> Government / NGO -> search "Kenya" -> map loads. 0 JS page errors, 0 console errors. Load ~5-7 s per hard refresh via URL; ~14 s for landing + pick + search + map.
- UI legend count == decoded-data count in **279/279** cells (93 months x +1/+3/+6). **0 mismatches, 0 code/decoding bugs.**
- Coverage is all-or-nothing: every cell is 290/290 or 0/290. No partial coverage, so no sub-county lacks a FEWS polygon (class c = none).
- "Now" view: layer switch is hidden by design (legend shows model risk levels, not FEWS). Spot checks of "Our model" and "Both" at t=0, 60, 80, 92: load clean, FEWS counts unchanged.
- Labels seen: `No FEWS NET outlook covers <month> yet (latest outlook published <month>)`, `FEWS NET paused (2025) - no outlook`, `No FEWS NET outlook covers <month> yet`. All correct for the cells they appear on.
- Scenario: +1 is mostly ML1 (about 1.5 months ahead), +3 is ML2 for most months, +6 is ML2. Cells with 290 always carry a published month; the 0 cells never do.

## Table: units with FEWS data /290 (reason code if 0)
Codes: a = target beyond latest FEWS outlook (expected). b = 2025 FEWS pause (target Feb-Jul 2025, or no outlook issued during the pause, expected). Last columns: latest published month in leads 1,3,6; scenario per lead.

| t | issue month | +1 | +3 | +6 | latest published | scenario +1,+3,+6 |
|---|---|---|---|---|---|---|
| 0 | Jan 2019 | 290 | 290 | 0a | 2018-12 | ML2,ML2,- |
| 1 | Feb 2019 | 290 | 290 | 290 | 2019-02 | ML1,ML1,ML2 |
| 2 | Mar 2019 | 290 | 290 | 290 | 2019-03 | ML1,ML2,ML2 |
| 3 | Apr 2019 | 290 | 290 | 0a | 2019-04 | ML1,ML2,- |
| 4 | May 2019 | 290 | 290 | 0a | 2019-05 | ML2,ML2,- |
| 5 | Jun 2019 | 290 | 290 | 290 | 2019-06 | ML1,ML1,ML2 |
| 6 | Jul 2019 | 290 | 290 | 290 | 2019-07 | ML1,ML2,ML2 |
| 7 | Aug 2019 | 290 | 290 | 0a | 2019-08 | ML1,ML2,- |
| 8 | Sep 2019 | 290 | 290 | 0a | 2019-08 | ML2,ML2,- |
| 9 | Oct 2019 | 290 | 290 | 290 | 2019-10 | ML1,ML1,ML2 |
| 10 | Nov 2019 | 290 | 290 | 290 | 2019-11 | ML1,ML2,ML2 |
| 11 | Dec 2019 | 290 | 290 | 0a | 2019-12 | ML1,ML2,- |
| 12 | Jan 2020 | 290 | 290 | 0a | 2020-01 | ML2,ML2,- |
| 13 | Feb 2020 | 290 | 290 | 290 | 2020-02 | ML1,ML1,ML2 |
| 14 | Mar 2020 | 290 | 290 | 290 | 2020-03 | ML1,ML2,ML2 |
| 15 | Apr 2020 | 290 | 290 | 0a | 2020-04 | ML1,ML2,- |
| 16 | May 2020 | 290 | 290 | 0a | 2020-05 | ML2,ML2,- |
| 17 | Jun 2020 | 290 | 290 | 290 | 2020-06 | ML1,ML1,ML2 |
| 18 | Jul 2020 | 290 | 290 | 290 | 2020-07 | ML1,ML2,ML2 |
| 19 | Aug 2020 | 290 | 290 | 0a | 2020-08 | ML1,ML2,- |
| 20 | Sep 2020 | 290 | 290 | 0a | 2020-09 | ML2,ML2,- |
| 21 | Oct 2020 | 290 | 290 | 290 | 2020-10 | ML1,ML1,ML2 |
| 22 | Nov 2020 | 290 | 290 | 290 | 2020-11 | ML1,ML2,ML2 |
| 23 | Dec 2020 | 290 | 290 | 0a | 2020-12 | ML1,ML2,- |
| 24 | Jan 2021 | 290 | 290 | 0a | 2021-01 | ML2,ML2,- |
| 25 | Feb 2021 | 290 | 290 | 290 | 2021-02 | ML1,ML1,ML2 |
| 26 | Mar 2021 | 290 | 290 | 290 | 2021-03 | ML1,ML2,ML2 |
| 27 | Apr 2021 | 290 | 290 | 0a | 2021-04 | ML1,ML2,- |
| 28 | May 2021 | 290 | 290 | 0a | 2021-05 | ML2,ML2,- |
| 29 | Jun 2021 | 290 | 290 | 290 | 2021-06 | ML1,ML1,ML2 |
| 30 | Jul 2021 | 290 | 290 | 290 | 2021-07 | ML1,ML2,ML2 |
| 31 | Aug 2021 | 290 | 290 | 0a | 2021-08 | ML1,ML2,- |
| 32 | Sep 2021 | 290 | 290 | 0a | 2021-09 | ML2,ML2,- |
| 33 | Oct 2021 | 290 | 290 | 290 | 2021-10 | ML1,ML1,ML2 |
| 34 | Nov 2021 | 290 | 290 | 290 | 2021-11 | ML1,ML2,ML2 |
| 35 | Dec 2021 | 290 | 290 | 0a | 2021-12 | ML1,ML2,- |
| 36 | Jan 2022 | 290 | 290 | 0a | 2022-01 | ML2,ML2,- |
| 37 | Feb 2022 | 290 | 290 | 290 | 2022-02 | ML1,ML1,ML2 |
| 38 | Mar 2022 | 290 | 290 | 290 | 2022-03 | ML1,ML2,ML2 |
| 39 | Apr 2022 | 290 | 290 | 0a | 2022-04 | ML1,ML2,- |
| 40 | May 2022 | 290 | 290 | 0a | 2022-05 | ML2,ML2,- |
| 41 | Jun 2022 | 290 | 290 | 290 | 2022-06 | ML1,ML1,ML2 |
| 42 | Jul 2022 | 290 | 290 | 290 | 2022-07 | ML1,ML2,ML2 |
| 43 | Aug 2022 | 290 | 290 | 0a | 2022-08 | ML1,ML2,- |
| 44 | Sep 2022 | 290 | 290 | 0a | 2022-09 | ML2,ML2,- |
| 45 | Oct 2022 | 290 | 290 | 290 | 2022-10 | ML1,ML1,ML2 |
| 46 | Nov 2022 | 290 | 290 | 290 | 2022-11 | ML1,ML2,ML2 |
| 47 | Dec 2022 | 290 | 290 | 0a | 2022-12 | ML1,ML2,- |
| 48 | Jan 2023 | 290 | 290 | 0a | 2023-01 | ML2,ML2,- |
| 49 | Feb 2023 | 290 | 290 | 290 | 2023-02 | ML1,ML1,ML2 |
| 50 | Mar 2023 | 290 | 290 | 290 | 2023-03 | ML1,ML2,ML2 |
| 51 | Apr 2023 | 290 | 290 | 0a | 2023-04 | ML1,ML2,- |
| 52 | May 2023 | 290 | 290 | 0a | 2023-05 | ML2,ML2,- |
| 53 | Jun 2023 | 290 | 290 | 290 | 2023-06 | ML1,ML1,ML2 |
| 54 | Jul 2023 | 290 | 290 | 290 | 2023-07 | ML1,ML2,ML2 |
| 55 | Aug 2023 | 290 | 290 | 0a | 2023-08 | ML1,ML2,- |
| 56 | Sep 2023 | 290 | 290 | 0a | 2023-09 | ML2,ML2,- |
| 57 | Oct 2023 | 290 | 290 | 290 | 2023-10 | ML1,ML1,ML2 |
| 58 | Nov 2023 | 290 | 290 | 290 | 2023-11 | ML1,ML2,ML2 |
| 59 | Dec 2023 | 290 | 290 | 0a | 2023-12 | ML1,ML2,- |
| 60 | Jan 2024 | 290 | 290 | 0a | 2024-01 | ML2,ML2,- |
| 61 | Feb 2024 | 290 | 290 | 290 | 2024-02 | ML1,ML1,ML2 |
| 62 | Mar 2024 | 290 | 290 | 290 | 2024-03 | ML1,ML2,ML2 |
| 63 | Apr 2024 | 290 | 290 | 0a | 2024-04 | ML1,ML2,- |
| 64 | May 2024 | 290 | 290 | 0a | 2024-05 | ML2,ML2,- |
| 65 | Jun 2024 | 290 | 290 | 290 | 2024-06 | ML1,ML1,ML2 |
| 66 | Jul 2024 | 290 | 290 | 290 | 2024-07 | ML1,ML2,ML2 |
| 67 | Aug 2024 | 290 | 290 | 0a | 2024-08 | ML1,ML2,- |
| 68 | Sep 2024 | 290 | 290 | 0b | 2024-09 | ML2,ML2,- |
| 69 | Oct 2024 | 290 | 290 | 290 | 2024-10 | ML1,ML1,ML2 |
| 70 | Nov 2024 | 290 | 290 | 290 | 2024-10 | ML1,ML2,ML2 |
| 71 | Dec 2024 | 290 | 290 | 0b | 2024-10 | ML1,ML2,- |
| 72 | Jan 2025 | 290 | 290 | 0b | 2024-10 | ML2,ML2,- |
| 73 | Feb 2025 | 290 | 290 | 0a | 2024-10 | ML2,ML2,- |
| 74 | Mar 2025 | 290 | 0b | 0a | 2024-10 | ML2,-,- |
| 75 | Apr 2025 | 290 | 0b | 0a | 2024-10 | ML2,-,- |
| 76 | May 2025 | 0b | 0b | 0a | - | -,-,- |
| 77 | Jun 2025 | 0b | 0b | 0a | - | -,-,- |
| 78 | Jul 2025 | 0b | 0a | 0a | - | -,-,- |
| 79 | Aug 2025 | 290 | 290 | 0a | 2025-08 | ML1,ML2,- |
| 80 | Sep 2025 | 290 | 290 | 0a | 2025-09 | ML2,ML2,- |
| 81 | Oct 2025 | 290 | 290 | 290 | 2025-10 | ML1,ML1,ML2 |
| 82 | Nov 2025 | 290 | 290 | 290 | 2025-11 | ML1,ML2,ML2 |
| 83 | Dec 2025 | 290 | 290 | 0a | 2025-12 | ML1,ML2,- |
| 84 | Jan 2026 | 290 | 290 | 0a | 2026-01 | ML2,ML2,- |
| 85 | Feb 2026 | 290 | 290 | 290 | 2026-02 | ML1,ML1,ML2 |
| 86 | Mar 2026 | 290 | 290 | 290 | 2026-03 | ML1,ML2,ML2 |
| 87 | Apr 2026 | 290 | 290 | 0a | 2026-04 | ML1,ML2,- |
| 88 | May 2026 | 290 | 290 | 0a | 2026-05 | ML2,ML2,- |
| 89 | Jun 2026 | 290 | 290 | 290 | 2026-06 | ML1,ML1,ML2 |
| 90 | Jul 2026 | 290 | 290 | 290 | 2026-07 | ML1,ML2,ML2 |
| 91 | Aug 2026 | 290 | 290 | 0a | 2026-08 | ML1,ML2,- |
| 92 | Sep 2026 | 290 | 290 | 0a | 2026-09 | ML2,ML2,- |

## Gap summary
- (a) beyond latest outlook: every month where +6 = 0 (outlooks reach about 5 months ahead). Also +3 = 0 at t=76..78 (right after the pause, nothing issued yet).
- (b) 2025 pause: t=72..78 (issue Jan-Jul 2025) with targets Feb-Jul 2025; no outlook was published May-Jul 2025 (all leads empty at t=76..78).
- (c) no polygon overlap: none. All 290 sub-counties get data whenever an outlook covers the target.
- (d) code/decoding bugs: none found.

## Fixes
None needed. Minor label note: at t=78 +1 (target Aug 2025) the message omits "(latest outlook published ...)" because no outlook exists in any lead; text is still correct.
