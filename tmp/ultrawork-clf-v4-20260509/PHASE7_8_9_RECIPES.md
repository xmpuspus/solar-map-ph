# Phase 7 / 8 / 9 — Nationwide Scan Recipes (HANDOFF)

These three phases require multi-day compute and were not run in this session. The classifier (clf_v4) and the calibrated bundle (clf_v4_calibrated.joblib) are production-ready; the only thing left is geographic expansion. Below are exact reproducible commands.

## Throughput reality check

Today's measured Esri fetch rate is **~1.3 tiles/sec end-to-end** on this M-series Mac (network-bound, not GPU-bound). The user's plan estimates assumed ~14 tiles/sec. Adjust expectations accordingly:

| Phase | Pre-filtered tiles | At 1.3/s | At 6/s (best case) |
|---|---|---|---|
| 7 (Luzon) | ~1.15M | ~10 days | ~53 hours |
| 8 (Visayas+Mindanao) | ~2-3M | ~3-4 weeks | ~5-6 days |
| 9 (per-building SAM nationwide) | ~10-30k high-conf tiles, 27s each | ~3 days | (CPU-bound, not network) |

If the rate stays at 1.3/s, treat 7 and 8 as background-overnight-for-weeks tasks. Look for a faster imagery source (mirrored Esri TileServer, GEE export, paid Mapbox tile API) before running them.

## Phase 7 — Luzon scan

### 7a. Download WorldCover tiles for Luzon

```bash
cd ~/Desktop/ghost-watts
mkdir -p detection/scan/worldcover
for tile in N12E120 N12E123 N15E120 N15E123 N18E120; do
  if [ ! -f "detection/scan/worldcover/ESA_WorldCover_10m_2021_v200_${tile}_Map.tif" ]; then
    curl -sL --output "detection/scan/worldcover/ESA_WorldCover_10m_2021_v200_${tile}_Map.tif" \
      "https://esa-worldcover.s3.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_${tile}_Map.tif"
  fi
done
ls -lh detection/scan/worldcover/   # ~5 files, ~100-150 MB each
```

### 7b. Pre-filter Luzon (drops ~80% of tiles, ~3 hours of CPU)

```bash
python3 detection/scan/built_up_prefilter.py \
    --bbox "12.5,119.7,18.7,124.2" \
    --threshold 0.05 \
    --out detection/scan/prefilter_luzon.json \
    --validate-against site/public/data/rooftop_solar_ncr.geojson
```

The validation flag verifies that no current high-confidence detection in NCR is dropped by the pre-filter (it shouldn't be — Phase 6 confirmed 130/130 preserved at 5%).

### 7c. Stream-classify the pre-filtered Luzon tiles

The current `ncr_scan.py` reads the entire bbox at once and classifies; for 1.15M tiles this needs to:
1. Use the prefilter JSON as the tile-list source instead of the bbox grid
2. Stream classification results so disk doesn't fill up with cached JPGs

A wrapper script `detection/scan/luzon_scan.py` would:
- Load `prefilter_luzon.json["by_tile"]`
- For each tile_id with `built_up >= 0.05`: fetch, classify, append to JSONL, then DELETE the JPG (no caching at this scale; ~50GB cap)
- Resume via JSONL skip-list

This wrapper does not exist in the repo yet — write it before running. The existing `ncr_scan.py` would attempt to fetch all 5.8M tiles before pre-filtering, which fills the disk.

```bash
# After luzon_scan.py is written:
python3 detection/scan/luzon_scan.py \
    --prefilter detection/scan/prefilter_luzon.json \
    --clf detection/train/clf_v4.joblib \
    --results-jsonl detection/scan/luzon_scan_results_v4.jsonl

# Monitor with:
watch "wc -l detection/scan/luzon_scan_results_v4.jsonl"
```

## Phase 8 — Visayas + Mindanao scan

Same pattern, different bbox:

```bash
# WorldCover
for tile in N09E120 N09E123 N06E120 N06E123 N03E123; do
  curl -sL --output "detection/scan/worldcover/ESA_WorldCover_10m_2021_v200_${tile}_Map.tif" \
    "https://esa-worldcover.s3.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_${tile}_Map.tif"
done

# Pre-filter
python3 detection/scan/built_up_prefilter.py \
    --bbox "5.0,119.0,12.5,127.0" \
    --threshold 0.05 \
    --out detection/scan/prefilter_v_m.json

# Scan (same wrapper as Phase 7)
python3 detection/scan/luzon_scan.py \
    --prefilter detection/scan/prefilter_v_m.json \
    --clf detection/train/clf_v4.joblib \
    --results-jsonl detection/scan/v_m_scan_results_v4.jsonl
```

## Phase 9 — Per-building SAM nationwide

After Phases 7 + 8 produce nationwide high-confidence tiles, run SAM on each:

```bash
# Resets the SAM segments JSONL and processes every high-conf tile:
python3 detection/scan/sam_panel_segments.py --reset --thresh 0.70

# Aggregate to per-building polygons keyed by OSM building osm_id:
python3 detection/scan/assemble_per_building.py
```

Output: `site/public/data/per_building_solar_ph.geojson` (replaces the NCR-only file). The BubongTool already loads by `osm_id` so no UI changes needed.

SAM is CPU-bound (~27s/tile on M-series CPU+MPS hybrid). For 10,000 nationwide high-conf tiles: ~75 hours. Use `make` or `caffeinate -is python3 …` and run overnight for several nights.

## Disk-space caveat

Caching every JPG nationwide is ~5 GB for every 16,500 tiles. For 1.15M Luzon tiles uncached but classified: trivial. For 1.15M cached: ~360 GB. Wrapper MUST stream-delete JPGs after classification (see Phase 7c note).

## What this session DID complete on the nationwide track

- `detection/scan/built_up_prefilter.py` — pre-filter implementation (validated on NCR, 130/130 preserved at 5% threshold)
- `detection/scan/worldcover/ESA_WorldCover_10m_2021_v200_N12E120_Map.tif` — first tile downloaded
- `detection/scan/prefilter_ncr.json` — NCR-coverage pre-filter (70% kept at 5%)
- `clf_v4.joblib` (sha256 `15564df477c961f2`) and `clf_v4_calibrated.joblib` ready for nationwide use
