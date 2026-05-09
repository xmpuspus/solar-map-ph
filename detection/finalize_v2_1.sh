#!/usr/bin/env bash
#
# Finalize v2.1 building-level after SAM completes.
# 1. Re-assemble per-building geojson with the full 114 tiles
# 2. Regenerate per-building debug thumbnails
# 3. Run astro build to verify the site compiles with the new data

set -euo pipefail

cd "$(dirname "$0")/.."

echo "[finalize] Step 1: assemble per-building geojson"
python3 detection/scan/assemble_per_building.py

echo
echo "[finalize] Step 1b: validate output"
python3 detection/scan/validate_per_building.py

echo
echo "[finalize] Step 2: regenerate per-building debug thumbnails"
python3 detection/scan/visualize_per_building.py

echo
echo "[finalize] Step 3: astro build (verify site compiles)"
cd site
npm run build 2>&1 | tail -8
cd ..

echo
echo "[finalize] DONE. Summary:"
python3 -c "
import json
fc = json.load(open('site/public/data/per_building_solar_ncr.geojson'))
n = len(fc['features'])
total_kwp = sum(f['properties']['kwp_estimate'] for f in fc['features'])
max_kwp = max(f['properties']['kwp_estimate'] for f in fc['features'])
print(f'  buildings with detected solar: {n}')
print(f'  total estimated kWp: {total_kwp:,.0f}')
print(f'  largest install: {max_kwp:,.1f} kWp')
print(f'  tiles processed: {fc[\"_meta\"][\"tiles_processed\"]}/114')
"
