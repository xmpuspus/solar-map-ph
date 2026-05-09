#!/usr/bin/env bash
# Post-Phase-5-scan finalizer.
#
# After the extended-franchise ncr_scan run completes, this:
#   1. Dedupes the JSONL by 4-decimal tile_id (collapses NCR-grid vs extended-grid
#      misalignment artifacts at <1m offset)
#   2. Snapshots the raw JSONL to baselines for provenance
#   3. Replaces ncr_scan_results_v3.jsonl with the deduped version
#   4. Re-runs aggregate_and_compare.py to produce the final GeoJSON
#   5. Rebuilds verify sheets so the next active-learning round has fresh tiles
#
# Usage:  bash detection/scan/finalize_franchise_scan.sh

set -euo pipefail

cd "$(dirname "$0")/../.."

SRC=detection/scan/ncr_scan_results_v3.jsonl
RAW_BACKUP=detection/train/_baselines/scan_v4_franchise_raw_$(date +%Y%m%dT%H%M%S).jsonl
DEDUPED=detection/scan/ncr_scan_results_v3_deduped.jsonl

if [ ! -f "$SRC" ]; then
    echo "[finalize] $SRC missing — did the scan run?"
    exit 1
fi
SRC_LINES=$(wc -l < "$SRC")
echo "[finalize] raw scan lines: $SRC_LINES"

cp "$SRC" "$RAW_BACKUP"
echo "[finalize] raw snapshot -> $RAW_BACKUP"

python3 detection/scan/dedupe_jsonl.py --in "$SRC" --out "$DEDUPED"
mv "$DEDUPED" "$SRC"
echo "[finalize] $SRC now has $(wc -l < "$SRC") deduped lines"

python3 detection/scan/aggregate_and_compare.py
python3 detection/verify/build_verification_sheets.py | tail -3

echo
echo "[finalize] === Per-area breakdown ==="
python3 detection/scan/per_area_summary.py

echo
echo "[finalize] DONE."
