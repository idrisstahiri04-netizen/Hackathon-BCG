| experiment | what changes | ens. mean PR-AUC (Δ) | ens. mean Brier (Δ) | logreg Δ | lgbm Δ | crop_failure ROC / PR | no_grass ROC / PR |
|---|---|---|---|---|---|---|---|
| baseline (main model, v1.1 labels, latency) | — | 0.3375 | 0.1819 | — | — | 0.589 / 0.272 | 0.603 / 0.403 |
| oni_south_only | ONI×south (signed) → both members | 0.3505 (+0.0130) | 0.1815 (-0.0004) | +0.0155 | +0.0050 | 0.646 / 0.32 | 0.588 / 0.381 |
| oni_lr_only | ONI, ΔONI, ONI×south, lat → logreg only | 0.3485 (+0.0110) | 0.1813 (-0.0006) | +0.0110 | +0.0000 | 0.633 / 0.302 | 0.591 / 0.395 |
| oni_both | same 4 → both members | 0.3450 (+0.0075) | 0.1824 (+0.0005) | +0.0110 | -0.0005 | 0.644 / 0.315 | 0.577 / 0.375 |
| nino34_lr_only | monthly Niño3.4 (+3-mo mean, ×south), lat → logreg | 0.3500 (+0.0125) | 0.1809 (-0.0010) | +0.0120 | +0.0000 | 0.636 / 0.304 | 0.592 / 0.396 |
| oni_dmi_lr_only | ONI set + IOD/DMI → logreg | 0.3430 (+0.0055) | 0.1822 (+0.0003) | +0.0015 | +0.0000 | 0.627 / 0.3 | 0.575 / 0.386 |
| sfc_both | NMME MME3 P(below) & anomaly, m1-3 & m4-6 → both | 0.3720 (+0.0345) | 0.1779 (-0.0040) | +0.0340 | +0.0275 | 0.662 / 0.322 | 0.62 / 0.422 |
| combo_oni_sfc | NMME + ONI×south → both | 0.3625 (+0.0250) | 0.1797 (-0.0022) | +0.0295 | +0.0135 | 0.664 / 0.336 | 0.592 / 0.389 |
| combo_oni_sfc_cum | NMME + ONI×south + season-to-date rain % | 0.3660 (+0.0285) | 0.1793 (-0.0026) | +0.0300 | +0.0200 | 0.667 / 0.338 | 0.596 / 0.394 |
| combo_oni_lr_cum | ONI(logreg) + season-to-date rain % | 0.3530 (+0.0155) | 0.1807 (-0.0012) | +0.0120 | +0.0070 | 0.64 / 0.307 | 0.594 / 0.399 |
| cum_rain | season-to-date rain % of normal | 0.3455 (+0.0080) | 0.1812 (-0.0007) | +0.0055 | +0.0070 | 0.602 / 0.283 | 0.605 / 0.408 |
| cum_dry_gated | + dry-spell months + SPI gated to rainy season | 0.3450 (+0.0075) | 0.1816 (-0.0003) | +0.0060 | +0.0055 | 0.601 / 0.284 | 0.602 / 0.406 |
| mono | LightGBM monotone constraints (drier → riskier) | 0.3435 (+0.0060) | 0.1819 (+0.0000) | +0.0000 | +0.0025 | 0.591 / 0.282 | 0.597 / 0.405 |
| ens_w_lr70 | ensemble weight 0.7 logreg / 0.3 lgbm | 0.3380 (+0.0005) | 0.1819 (+0.0000) | +0.0000 | +0.0000 | 0.59 / 0.278 | 0.6 / 0.398 |
| pool_base | +10 countries in training (eval on 4) | 0.3540 (+0.0165) | 0.1792 (-0.0027) | +0.0120 | +0.0235 | 0.596 / 0.29 | 0.617 / 0.418 |
| pool_oni_lr_only | pooled + ONI(logreg) | 0.3615 (+0.0240) | 0.1787 (-0.0032) | +0.0185 | +0.0235 | 0.625 / 0.308 | 0.616 / 0.415 |
| pool_oni_sfc | pooled + NMME + ONI×south | 0.3800 (+0.0425) | 0.1771 (-0.0048) | +0.0320 | +0.0450 | 0.665 / 0.341 | 0.626 / 0.419 |
| v2_sfc_oni | per-event: crop NMME+ONI×south, grass NMME | 0.3795 (+0.0420) | 0.1774 (-0.0045) | +0.0370 | +0.0350 | 0.666 / 0.337 | 0.62 / 0.422 |
| v2_sfc_oni_lr | per-event: crop NMME+ONI×south, grass NMME+ONI(logreg) | 0.3735 (+0.0360) | 0.1784 (-0.0035) | +0.0295 | +0.0345 | 0.666 / 0.337 | 0.603 / 0.41 |
| v2_sfc_pool | **v2**: per-event as above + pooled 14 countries | 0.3870 (+0.0495) | 0.1757 (-0.0062) | +0.0380 | +0.0520 | 0.664 / 0.34 | 0.629 / 0.434 |
