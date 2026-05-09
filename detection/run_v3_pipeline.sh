#!/usr/bin/env bash
#
# Re-run the full v3 + v2.1 pipeline end to end after the user has tagged
# verification sheets in detection/verify/tags.json.
#
# Steps:
#   1. Rebuild dataset_v3.npz with the latest tags
#   2. Retrain clf_v3.joblib (5-fold group-aware CV)
#   3. Re-classify cached NCR tiles with the new clf_v3 (fast: --reuse-tiles)
#   4. Aggregate to GeoJSON + OSM cross-match + v2 vs v3 delta report
#   5. Rebuild verify sheets so newly upgraded tiles can be tagged in the next round
#   6. (Optional) re-run SAM panel-segment + per-building if --include-sam
#
# Usage:
#   ./detection/run_v3_pipeline.sh             # P1 only (active learning loop)
#   ./detection/run_v3_pipeline.sh --include-sam   # P1 + P2.1 (rebuild building-level)
#
# Pre-conditions:
#   - detection/scan/ncr_tiles/*.jpg already cached (from a prior full ncr_scan run)
#   - detection/verify/tags.json populated (or absent for cleanup-only mode)

set -euo pipefail

cd "$(dirname "$0")/.."

INCLUDE_SAM=false
for arg in "$@"; do
    case "$arg" in
        --include-sam) INCLUDE_SAM=true ;;
        *) echo "unknown arg: $arg" >&2; exit 2 ;;
    esac
done

echo "[v3] === Step 1: build dataset_v3 ==="
python3 detection/train/build_dataset_v3.py

echo
echo "[v3] === Step 2: train clf_v3 ==="
python3 detection/train/train_v3.py

echo
echo "[v3] === Step 3: re-classify cached tiles with clf_v3 ==="
python3 detection/scan/ncr_scan.py \
    --reuse-tiles \
    --clf detection/train/clf_v3.joblib \
    --results-jsonl detection/scan/ncr_scan_results_v3.jsonl \
    --no-aggregate

echo
echo "[v3] === Step 4: aggregate + OSM cross-match + v2/v3 delta ==="
python3 detection/scan/aggregate_and_compare.py

echo
echo "[v3] === Step 5: rebuild verify sheets ==="
python3 detection/verify/build_verification_sheets.py

if [ "$INCLUDE_SAM" = true ]; then
    echo
    echo "[v3] === Step 6: SAM panel-segment + per-building (slow, ~45 min) ==="
    python3 detection/scan/sam_panel_segments.py --reset --thresh 0.70
    echo
    echo "[v3] === Step 7: assemble per-building geojson ==="
    python3 detection/scan/assemble_per_building.py
fi

echo
echo "[v3] DONE. Open detection/verify/sheets/page_*.png to keep tagging."
