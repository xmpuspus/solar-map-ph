"""Post-Phase-5 JSONL deduper.

Phase 5's extended-bbox scan (14.20,120.88,14.85,121.22) generates a 240m grid
that is shifted ~100m from the original NCR grid (14.40,120.92,14.78,121.13).
Inside the NCR area both grids coexist after the scan: the original 16,544
NCR records + ~16,000 new-grid records covering the same NCR area at a 100m
offset. This is NOT a duplicate -- they're adjacent cells with full 240m
extents that overlap. But for the public GeoJSON we want clean, non-overlapping
NCR coverage at the original grid plus new coverage in the franchise extension.

Strategy:
  - Keep every record whose lat,lon is OUTSIDE the original NCR bbox (these are
    the new-franchise records -- Bulacan, Cavite, Rizal, Laguna).
  - For records INSIDE the original NCR bbox: keep only the ORIGINAL grid
    (the first batch of 16,544 records, identifiable by their grid origin).

To distinguish original-grid NCR from new-grid NCR: the original NCR grid
starts at lat=14.40108, lon=120.92112 with stride 0.00216 / 0.00224, so its
tile centers all satisfy `(lat - 14.40108) % 0.00216 ≈ 0` and `(lon - 120.92112) % 0.00224 ≈ 0`.
The new-grid centers start at lat=14.20108, lon=120.88112 and don't satisfy
the same modular alignment.

Usage:
  python3 detection/scan/dedupe_jsonl.py \
      --in detection/scan/ncr_scan_results_v3.jsonl \
      --out detection/scan/ncr_scan_results_v3_clean.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# Original NCR grid origin (from ncr_scan.py with bbox 14.40,120.92,14.78,121.13)
ORIG_NCR_BBOX = (14.40, 120.92, 14.78, 121.13)
TILE_DEG_LAT = 0.00216
TILE_DEG_LON = 0.00224
ORIG_LAT_ORIGIN = ORIG_NCR_BBOX[0] + TILE_DEG_LAT / 2  # 14.40108
ORIG_LON_ORIGIN = ORIG_NCR_BBOX[1] + TILE_DEG_LON / 2  # 120.92112


def in_ncr(lat: float, lon: float) -> bool:
    return ORIG_NCR_BBOX[0] <= lat <= ORIG_NCR_BBOX[2] and ORIG_NCR_BBOX[1] <= lon <= ORIG_NCR_BBOX[3]


def is_orig_grid(lat: float, lon: float, tol: float = 5e-5) -> bool:
    """Does this lat/lon sit on the original NCR grid?"""
    lat_off = (lat - ORIG_LAT_ORIGIN) / TILE_DEG_LAT
    lon_off = (lon - ORIG_LON_ORIGIN) / TILE_DEG_LON
    return (
        abs(lat_off - round(lat_off)) < tol
        and abs(lon_off - round(lon_off)) < tol
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", dest="dst", required=True)
    args = ap.parse_args()

    n_in = 0
    n_kept = 0
    n_drop_ncr_offgrid = 0
    n_kept_dedupe = 0
    seen_ids: set[str] = set()  # by exact tile_id (5-decimal); idempotent for true duplicates

    out_records = []
    with Path(args.src).open() as f:
        for line in f:
            r = json.loads(line)
            n_in += 1
            tid = r["tile_id"]
            if tid in seen_ids:
                n_kept_dedupe += 1
                continue
            lat, lon = r["lat"], r["lon"]
            if in_ncr(lat, lon) and not is_orig_grid(lat, lon):
                # Inside NCR but on the new (offset) grid -- drop, original grid covers this
                n_drop_ncr_offgrid += 1
                continue
            seen_ids.add(tid)
            out_records.append(r)
            n_kept += 1

    with Path(args.dst).open("w") as f:
        for r in out_records:
            f.write(json.dumps(r) + "\n")

    print(f"in={n_in}")
    print(f"  kept (orig NCR grid + new franchise): {n_kept}")
    print(f"  dropped (NCR area, off-grid): {n_drop_ncr_offgrid}")
    print(f"  dropped (exact tile_id duplicates): {n_kept_dedupe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
