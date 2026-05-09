# detection/

CNN-based per-roof solar detection layer for ghost-watts.

The Sentinel-2 pipeline in `pipeline/` is structurally too coarse (10m / pixel) to claim solar at a specific roof. This module bootstraps a hi-res Esri + CLIP + logistic-regression detector that gives defensible per-roof predictions over Metro Manila.

## Layout

| Path | Role |
|---|---|
| `bootstrap/fetch_osm_solar.py` | Pull `power=generator + generator:source=solar` nodes from OSM via Overpass for the Meralco franchise area. |
| `bootstrap/fetch_tiles.py` | Fetch a 600x600 (~240m view, ~0.4m/px) Esri tile centered on each OSM-tagged location. |
| `bootstrap/build_review_sheets.py` | Stitch tiles into 5x5 sheets for human spot-check. |
| `spike/run_spike.py` | Initial pretrained-model evaluation (Mask2Former DeepSolar). |
| `spike/run_clip_spike.py` | CLIP zero-shot baseline. |
| `spike/pixel_chars.py` | Per-region pixel statistics (HSV, RGB) for hand-crafted features. |
| `train/build_dataset_v2.py` | Build CLIP-ViT-L embeddings for OSM positives + GT negatives + random NCR negatives. |
| `train/train_v2.py` | Train logistic regression on CLIP features with 5-fold group-aware CV. |
| `train/build_dataset_v3.py` | v3 dataset: v2 minus 2 noisy case studies, plus 4 known false-negative random tiles promoted to positives, plus any user-tagged "true" tiles from `verify/tags.json`. |
| `train/train_v3.py` | Train clf_v3 on the cleaned dataset. |
| `scan/ncr_scan.py` | Tile NCR on a 240m grid and classify every tile. Outputs streaming JSONL + final GeoJSON. Supports `--reuse-tiles` to re-classify cached tiles with a different `--clf` (no network fetch). |
| `scan/aggregate_and_compare.py` | Aggregate v3 JSONL to GeoJSON, run OSM cross-match, write `v2_vs_v3_delta.json`. |
| `scan/build_detection_sheet.py` | Stitch detection tiles into review sheets for visual verification. |
| `scan/sam_panel_segments.py` | v2.1: SAM auto-mask + color signature filter + CLIP+LR scoring per segment. Outputs `per_tile_segments.jsonl`. |
| `scan/assemble_per_building.py` | v2.1: intersect SAM segments with OSM building footprints, group by building, emit `per_building_solar_ncr.geojson`. |
| `verify/build_verification_sheets.py` | Active-learning UI: 3x3 PNG sheets of every high-confidence detection + tag template (`tags.json`). User edits the JSON to label true/false/ambiguous; `build_dataset_v3.py` reads the tags. |
| `buildings/fetch_buildings.py` | Python port of BubongTool's Overpass building lookup. Used by `assemble_per_building.py`. |
| `run_v3_pipeline.sh` | End-to-end orchestrator: rebuild dataset_v3, retrain, re-classify, aggregate, optionally re-run SAM + per-building. |

## Pipeline

```
OSM Overpass --> osm_solar_ncr_plus.geojson
                  |
                  v
          fetch_tiles.py (5 req/s, Esri)
                  |
                  v
          tiles/0000.jpg .. 0311.jpg (312 OSM-tagged rooftop arrays)
                  |
                  v
          build_dataset_v2.py
              + 6 case studies
              + 46 GT not_solar tiles
              + 154 random NCR tiles (as putative negatives)
                  |
                  v
          dataset_v2.npz  (2,500 rows, 768-dim CLIP features)
                  |
                  v
          train_v2.py  (5-fold group-aware CV)
                  |
                  v
          clf_v2.joblib  (logistic regression on CLIP features)
                  |
                  v
          ncr_scan.py  (16,544 tiles, 240m grid)
                  |
                  v
          rooftop_solar_ncr.geojson  (Points at score >= 0.70, tiered)
                  |
                  v
          BubongTool.astro  (per-address "solar detected near you" panel)
```

## Validation

5-fold group-aware cross-validation on 300 positive sources + 200 negative sources (each source's augmentations stay together). Per-source max score.

| Threshold | Precision | Recall | F1 | Notes |
|---|---|---|---|---|
| 0.525 | 0.909 | 0.903 | 0.906 | Best F1 |
| 0.700 | 0.949 | 0.810 | 0.874 | Broad scan |
| **0.850** | **0.981** | **0.680** | **0.803** | **High-confidence (production)** |
| 0.920 | 0.988 | 0.560 | 0.715 | Very high confidence |
| 0.960 | 1.000 | 0.347 | 0.515 | Zero false positives in eval |

**Caveat:** the LOSO precision is a lower bound. The 4 highest-scored "negatives" in the validation set all contain real visible rooftop solar arrays not in OSM — the classifier is discovering solar that the OSM community hasn't tagged yet.

## What didn't work

1. **Stanford DeepSolar Mask2Former (HuggingFace).** `abdulsalama/SV-solar-mask2-swin-large-ade-200-deepsolar-2023060311` saturated the segmentation mask at 100% on every input — gave 35% precision regardless of content.
2. **CLIP zero-shot.** F1 ≈ 0.5. CLIP wasn't trained on overhead aerial imagery; the texture of solar panels from above is outside its semantic scope.
3. **Linear-on-CLIP with 9 positives (case studies + GT solars only).** LOSO precision 17%. The dataset was too thin for the model to find the solar concept; it overfit to the augmentation distribution of the 9 positive sources.
4. **One of the original 6 hand-verified case studies (`case_valenzuela`) does not show clearly visible solar in its tile.** The v2 classifier scored it 0.18 — reasonable. Single-pass vision-model labeling on ambiguous PH industrial roofs has noise; OSM-bootstrapped data is cleaner because community editors verify on the ground.

## Reproducibility

```bash
# 1. Bootstrap the positive set
python3 detection/bootstrap/fetch_osm_solar.py
python3 detection/bootstrap/fetch_tiles.py --location=roof
python3 detection/bootstrap/build_review_sheets.py   # spot-check

# 2. Build dataset and train classifier
python3 detection/train/build_dataset_v2.py
python3 detection/train/train_v2.py

# 3. Run the NCR scan (~70 minutes)
python3 detection/scan/ncr_scan.py

# 4. Re-aggregate at any time
python3 -c "
from detection.scan.ncr_scan import aggregate_to_geojson
aggregate_to_geojson()
"
```

All scripts stream progress to stdout and re-running is safe (tile cache + JSONL are append-only and resumable).

## Limits and next steps

- Tile-level v3: 240m grid points. v2.1 (already shipped) localizes to OSM buildings.
- v2.1 kWp is a **lower bound** for large multi-building solar farms: each SAM segment is attributed to a single OSM building, so when a panel array spans multiple buildings (or one footprint and informal structures), only the matched building gets credit. Single-roof arrays (homes, single-tenant warehouses, malls) report accurately.
- Esri imagery vintage in PH is 1-3 years stale. Solar from 2024-2026 may not be visible. Real recall is therefore higher than the LOSO number suggests.
- The classifier learned warehouse-scale + commercial solar much better than residential (training set is biased that way; OSM tags large arrays more reliably than household 5-10 kWp installs).
- Active learning loop next: tag the 23 v3-promoted high tiles in `detection/verify/v3_new_sheets/`, then re-run `./detection/run_v3_pipeline.sh --include-sam`.
