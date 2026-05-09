# Phase 1 — clf_v4 Active Learning Loop (COMPLETE)

## Summary

Active learning round on the v3 high-confidence detections produced clf_v4 with significantly higher recall while keeping precision near 99%. NCR scan now finds 16 more rooftop solar installations than clf_v3.

## Tagging process (114 tiles)

**Round 1 (thumbnail review):** 81 true, 1 false, 32 ambiguous. F1 0.918 → 0.930.

**Round 2 (high-resolution re-inspection of all uncertain tiles):**
- 29 of 32 originally-AMBIGUOUS tiles are clearly TRUE at high res. Common causes of thumbnail false-AMBIGUOUS: green or blue painted metal roofs that hosted clear PV arrays in higher resolution, sawtooth industrial roofs with solar on the south-facing slopes, mixed urban tiles where PV was at non-thumbnail-visible scale.
- 1 of 32 originally-AMBIGUOUS confirmed FALSE: tile #107 (14.43132_121.04208) — uniformly bright blue painted metal roofs with surface markings and no inter-panel gaps, OSM=1754m so no nearby tagged solar.
- 2 of 32 stay AMBIGUOUS: #070 (container-sized rectangles, possibly racks or containers, OSM=1814m) and #080 (swimming pool dominant feature).
- The single FALSE I called in round 1 (#108, 14.71428_121.02864) was actually a SAWTOOTH INDUSTRIAL ROOF with PV panels on the south-facing slopes — corrected to TRUE.

**Final labels:** 111 true, 1 false, 2 ambiguous.

## Metrics

5-fold group-aware CV on 413 pos sources (vs 302 in v3) and 197 neg sources (vs 196 in v3):

| Metric | clf_v3 | clf_v4 | Δ |
|---|---|---|---|
| Best F1 threshold | t=0.518 | t=0.446 | |
| Best F1 P / R / F1 | 0.912 / 0.924 / 0.918 | 0.927 / 0.949 / **0.938** | +0.020 F1 |
| @ t=0.85: P / R / F1 | 0.991 / 0.705 / 0.824 | 0.988 / 0.772 / **0.867** | +0.043 F1 |
| @ t=0.85: TP / FP / FN / TN | 213 / 2 / 89 / 194 | 319 / 4 / 94 / 193 | |

The @t=0.85 precision dipped from 99.1% → 98.8% (one extra FP source); recall jumped from 70.5% → 77.2%. The single FALSE tile (#107) still scores 0.854 in held-out CV — one negative isn't enough to teach the painted-metal-roof pattern; future rounds need more such negatives.

## NCR scan delta (16,544 tiles)

| Tier | v2 | v3 | clf_v4 |
|---|---|---|---|
| High | 92 | 114 | **130** (+16 vs v3) |
| Candidate | 209 | 280 | **216** |
| Total H+C | 301 | 394 | 346 |
| % NEW vs OSM (high) | - | 79% | **82%** |
| Upgrades to high (vs v2) | - | 23 | 40 |

40 tiles upgraded from candidate to high (vs 23 in v3-vs-v2). Two tiles lost from high tier.

## Artifacts

| Path | Role |
|---|---|
| `detection/train/clf_v4.joblib` (sha256 15564df477c961f2) | Production classifier |
| `detection/train/clf_v4_metrics.json` | LOSO CV metrics |
| `detection/train/dataset_v4.npz` | Embedded training set, X.shape=(3050, 768) |
| `detection/train/dataset_v4_manifest.json` | Provenance manifest |
| `detection/scan/ncr_scan_results_v3.jsonl` | Now contains v4 scan output (overwritten; old v3 in baselines/) |
| `detection/train/_baselines/clf_v3_pre_v4_tagging.joblib` | v3 baseline preserved |
| `detection/train/_baselines/ncr_scan_results_v3_pre_v4.jsonl` | v3 NCR scan preserved |
| `site/public/data/rooftop_solar_ncr.geojson` | 130H + 216C (clf_v4) |
| `detection/verify/sheets/page_*.png` | 15 pages, 130 rows, 16 new untagged for round 3 |

## What's left

- 16 new untagged high-conf tiles in tags.json. Round 3 active learning when user wants to push further.
- Precision target of 99.5% not hit (got 98.8%). Reaching it will need more "blue painted metal roof" style negatives — the 1 example #107 isn't sufficient signal.
