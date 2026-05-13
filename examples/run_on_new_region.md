# Running ghost-watts on a new region

This recipe shows how to apply the detection pipeline to any geography outside the Meralco franchise without code changes. The Earth Engine quarterly pipeline already accepts a `--region-polygons` path; the detection scan uses a bbox flag.

The natural extension is to other Philippine LGUs outside the Meralco franchise: **Cebu, Davao, Iloilo, Cagayan de Oro, Bacolod**. Same imagery vintage assumptions, same climate, same regulatory frame, same rate caps. The recipe below walks through Cebu Metro.

## What you need

- A region polygon as a GeoJSON file. Pull from OpenStreetMap, GADM, or hand-draw in geojson.io. PSA's PSGC-coded LGU polygons are also a good source for PH regions.
- Sufficient disk for satellite tiles. A 50 km x 50 km region at 240 m stride is ~43,000 tiles, ~17 GB cached.
- Python 3.11+, pip, the pinned deps from `requirements.txt`.

## 1. Generate the tile grid

```python
from ghost_watts import grid_centers

# Cebu Metro: Cebu City + Mandaue + Lapu-Lapu, roughly the urban core
centers = grid_centers((10.28, 123.85, 10.42, 124.00), tile_meters=240.0)
print(f"{len(centers)} tile centers")
```

`grid_centers` recomputes degrees-per-meter at the region's mean latitude, so no NCR-specific constants leak into your run.

## 2. Fetch the imagery

The bundled `detection/scan/ncr_scan.py` defaults to the Meralco-franchise bbox, but supports an override:

```bash
python detection/scan/ncr_scan.py \
    --bbox "10.28,123.85,10.42,124.00" \
    --tiles-dir ./cebu_tiles \
    --results-jsonl ./cebu_scan.jsonl
```

Esri World Imagery licensing permits research use under the rate cap (~5 req/s). For commercial use, switch to your own imagery source by editing the `ESRI_BASE` URL in `ncr_scan.py`.

## 3. Score and aggregate

```python
import numpy as np
from PIL import Image

from ghost_watts import score_features
from detection.train.build_dataset_v3 import load_clip, embed

processor, model = load_clip()
imgs = [Image.open(p).convert("RGB") for p in tile_paths]
features = embed(processor, model, imgs)

scores = score_features(features, calibrated=True)
high_conf_mask = scores >= 0.85
```

The decision threshold 0.85 was calibrated on PH imagery (NCR specifically). Recall on visually similar PH regions (Cebu, Davao, Iloilo) should transfer well because the climate, roof colors, and panel installation patterns are consistent across the country. For non-PH regions in different climates, plan for one round of active learning on the new region: tag ~50 high-confidence detections, ~50 negatives, retrain. See `detection/active_learning.md` for the protocol.

## 4. Output

`detection/scan/aggregate_and_compare.py` writes GeoJSON. To run it on your region:

```bash
python detection/scan/aggregate_and_compare.py \
    --results-jsonl ./cebu_scan.jsonl \
    --out ./cebu_solar.geojson
```

## What may need tweaking

- **`detection/scan/sam_panel_segments.py:NCR_BBOX`** is hardcoded. If you run the v2.1 per-building stage, change it to your region bbox.
- **`pipeline/franchise_cities.json` and `pipeline/lgu_friction.json`** are Meralco-franchise specific. For other PH regions, either build the equivalent index for the local distribution utility (VECO for Cebu, DLPC for Davao, MORE for Iloilo) or skip the EE pipeline and run only the detection side.
- **Esri tile vintage** varies by region. PH coverage outside Metro Manila tends to be even more stale than NCR's 1-3 year gap. Check the imagery date in your bbox before drawing trend conclusions.

## What probably doesn't need tweaking

- The classifier itself transfers well across PH regions for **commercial** rooftops (warehouses, malls, schools). Residential transferability is weaker because residential roof colors and panel sizes vary by province.
- The active-learning UI (`detection/verify/build_verification_sheets.py`) is region-agnostic.

## PH distribution-utility cross-reference

If you adapt the EE pipeline (city-level composite signal), here are the equivalent indices to replace `franchise_cities.json`:

| Region | Utility | Cities (start) |
|---|---|---|
| Metro Cebu | Visayan Electric (VECO) | Cebu City, Mandaue, Lapu-Lapu, Talisay |
| Metro Davao | Davao Light (DLPC) | Davao City, Panabo, Tagum |
| Metro Iloilo | MORE Electric | Iloilo City, Pavia, Oton, San Miguel |
| Metro Cagayan de Oro | CEPALCO | Cagayan de Oro, Opol, El Salvador |

Each utility publishes its franchise polygon in annual reports; OpenStreetMap covers most LGU boundaries.

## Citation

If your paper uses ghost-watts on a new region, please cite both the model (`CITATION.cff`) and note the threshold + recalibration setup in your methods section.
