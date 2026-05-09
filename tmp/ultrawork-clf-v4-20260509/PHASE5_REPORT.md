# Phase 5 — Meralco Extended Franchise Scan (COMPLETE)

## Result

Doubling the geographic footprint roughly doubled the high-confidence detection count.

| Tier | NCR-only (clf_v4 baseline) | NCR + Franchise (after Phase 5) |
|---|---|---|
| High (≥ 0.85) | 130 | **266** (+105%) |
| Candidate (0.70–0.85) | 216 | **351** (+63%) |
| Total | 346 | **617** |
| % NEW vs OSM (high) | 82% | **85%** |

Per-area breakdown:

| Area | High | Candidate |
|---|---|---|
| NCR (14.40–14.78 N, 120.92–121.13 E) | 130 | 216 |
| Extended franchise (Bulacan / Cavite / Rizal / Laguna) | 136 | 135 |
| **Total** | **266** | **351** |

## Scan execution

- **Bbox**: `(14.20, 120.88, 14.85, 121.22)` — covers NCR + the Meralco-adjacent industrial belts in Bulacan, Cavite, Rizal, Laguna
- **Tiles attempted (extended-grid)**: 43,848 + 1,904 already-skipped from the previous attempt = 45,752 unique grid cells
- **Tiles classified ok**: 43,513
- **Tiles failed**: 335 (0.77% failure rate, network errors against Esri's tile endpoint)
- **Wall time**: 4,143 sec (≈ 69 min)
- **Average rate**: 10.5 tiles/sec sustained (peaked at ~14 t/s, dropped under load)

The user's original 30-min estimate assumed ~24 t/s — Esri throttled the 32-worker pool down to ~10-14 t/s instead. With higher-speed imagery (mirrored TileServer, paid Mapbox) the same scan would finish in <30 min.

## Throughput note (for Phases 7-9 planning)

- Serial fetch: 0.55 t/s (~1.8s per tile, network-bound)
- 12 fetch workers: 1.3 t/s (Esri throttling to a low-concurrency lane)
- 32 fetch workers + caffeinate: 10.5 t/s sustained
- Bumping past 32 workers likely brings diminishing returns due to Esri rate-limit ceilings; the rate visibly dropped from 14 → 10.5 t/s as the scan progressed (server-side throttling tightening over a long-lived session)

For Phase 7 (Luzon, ~1.15M pre-filtered tiles): at 10.5 t/s steady, **~30 hours** local scan time. Phase 8 (Visayas + Mindanao, ~2-3M tiles): **~3-4 days**.

## Grid alignment fix

The extended bbox started at lat 14.20, which produces a 240m grid offset from the original NCR grid (which started at 14.40). The two grids were ~100m apart inside NCR area. Without correction the GeoJSON would have shown duplicate/overlapping detections in NCR.

Fix: `detection/scan/dedupe_jsonl.py` keeps records on the original NCR grid for NCR-area lat/lon, drops new-grid NCR records (preserves original-resolution NCR), and keeps everything outside NCR. Result: 45,752 deduped records, 0 exact-tile_id duplicates.

This is a one-time fix for Phase 5. For future expansions the bbox should be aligned to the NCR grid (south = `14.40 - n × TILE_DEG_LAT`, west = `120.92 - m × TILE_DEG_LON` for integer n, m). The aligned south-west corner for the same coverage is **(14.19912, 120.87968)**.

## Top 10 franchise high-confidence detections

| Rank | tile_id | score | location |
|---|---|---|---|
| 1 | 14.55532_121.13872 | 0.988 | Antipolo Rizal |
| 2 | 14.84476_121.01552 | 0.988 | San Jose del Monte Bulacan |
| 3 | 14.20540_121.08720 | 0.987 | Sta Rosa Laguna |
| 4 | 14.34364_121.01328 | 0.987 | Imus / Bacoor Cavite border |
| 5 | 14.56828_121.14096 | 0.986 | Antipolo Rizal |
| 6 | 14.25724_121.12080 | 0.984 | Sta Rosa / Cabuyao Laguna |
| 7 | 14.32852_120.95952 | 0.984 | Bacoor Cavite |
| 8 | 14.35228_121.06256 | 0.984 | Carmona Cavite |
| 9 | 14.22700_121.13872 | 0.983 | Cabuyao Laguna |
| 10 | 14.23348_121.09392 | 0.982 | Cabuyao Laguna |

The pattern matches the priors: industrial belts in Cavite, Laguna, and the SJDM/Marilao corridor in Bulacan, plus high-end Antipolo (where rooftop solar adoption tracks Rizal's affluent residential). The candidate tier (351 detections) extends this further into less-dense industrial pockets and small commercial sites.

## What's NOW production

| Path | New value |
|---|---|
| `site/public/data/rooftop_solar_ncr.geojson` | 266 high + 351 candidate, full-franchise coverage |
| `detection/scan/ncr_scan_results_v3.jsonl` | 45,752 deduped lines (NCR original-grid + franchise) |
| `detection/scan/match_report.json` | OSM cross-match per detection (40/226 high confirmed/new = 15%/85%) |
| `detection/verify/sheets/page_*.png` | Rebuilt for 266 high-conf tiles (~30 sheets, ~136 new untagged for round-3 active learning) |
| `detection/train/_baselines/scan_v4_franchise_raw_20260509T173007.jsonl` | Raw 62,296-line snapshot before dedupe (provenance) |

## Next active-learning round (when user wants)

The 136 new franchise high-conf tiles are unlabeled in `detection/verify/tags.json`. Round 3 active learning would tag those visually and retrain clf_v5 with a much larger positive pool (413 → 549+ sources). Expected: F1 keeps climbing toward 0.95.
