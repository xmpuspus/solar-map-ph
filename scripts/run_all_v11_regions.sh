#!/usr/bin/env bash
# Sequentially scan all remaining v1.1 regions. Esri's World Imagery layer has
# region-specific max-zoom limits; outside NCR a 400 px tile export works
# universally where 600 px returns HTTP 500. region_scan.py defaults to 400.
#
# Order: smallest -> largest so smaller regions ship first and Calabarzon (the
# biggest, ~9k fetches) runs last when momentum is built.
#
# Usage:
#   bash scripts/run_all_v11_regions.sh
#
# Writes to detection/scan/<region>.log (gitignored).
set -euo pipefail
cd "$(dirname "$0")/.."

REGIONS=(calabarzon bacolod iloilo cdo davao)

for slug in "${REGIONS[@]}"; do
  geojson="site/public/data/rooftop_solar_${slug}.geojson"
  # Calabarzon: skip the "already exists" early-out so it resumes from cached
  # JSONL (the v1.1.0 ship cut at 9.5% coverage). Other regions: skip if the
  # full geojson is already on disk.
  if [ -f "$geojson" ] && [ "$slug" != "calabarzon" ]; then
    echo "[run-all] $slug: $geojson already exists, skipping (delete to force re-scan)"
    continue
  fi
  echo "[run-all] starting $slug"
  SOLAR_MAP_PH_FETCH_WORKERS=2 PYTHONUNBUFFERED=1 \
    .venv/bin/python detection/scan/region_scan.py \
      --region "$slug" --built-up-threshold 0.05 \
      2>&1 | tee "detection/scan/${slug}.log"
  echo "[run-all] $slug done; aggregating"
  .venv/bin/python detection/scan/aggregate_region.py --region "$slug" 2>&1 | tee -a "detection/scan/${slug}.log"
done

echo "[run-all] all regions complete"
