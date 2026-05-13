"""Post-scan summary: split detections by NCR vs extended-franchise areas.

After the Phase-5 scan finishes, the GeoJSON contains detections across the
combined bbox (14.20,120.88,14.85,121.22). This script breaks them out by
geographic area for headline reporting.

Usage:
  python3 detection/scan/per_area_summary.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEOJSON = ROOT / "site" / "public" / "data" / "rooftop_solar_ncr.geojson"

# Original NCR bbox
NCR = (14.40, 120.92, 14.78, 121.13)


def in_ncr(lat: float, lon: float) -> bool:
    return NCR[0] <= lat <= NCR[2] and NCR[1] <= lon <= NCR[3]


def main():
    fc = json.loads(GEOJSON.read_text())
    feats = fc["features"]

    by_area = {"ncr": {"high": [], "candidate": []}, "franchise": {"high": [], "candidate": []}}
    for f in feats:
        lon, lat = f["geometry"]["coordinates"]
        tier = f["properties"]["tier"]
        area = "ncr" if in_ncr(lat, lon) else "franchise"
        by_area[area][tier].append(f)

    print("Per-area breakdown (lat × lon):")
    print(f"  NCR ({NCR[0]}-{NCR[2]} N, {NCR[1]}-{NCR[3]} E):")
    print(f"    high:      {len(by_area['ncr']['high']):4d}")
    print(f"    candidate: {len(by_area['ncr']['candidate']):4d}")
    print("  Extended franchise (Bulacan/Cavite/Rizal/Laguna):")
    print(f"    high:      {len(by_area['franchise']['high']):4d}")
    print(f"    candidate: {len(by_area['franchise']['candidate']):4d}")
    print()
    print(f"  Total high:      {len(by_area['ncr']['high']) + len(by_area['franchise']['high']):4d}")
    print(
        f"  Total candidate: {len(by_area['ncr']['candidate']) + len(by_area['franchise']['candidate']):4d}"
    )

    # Top 10 highest-scoring franchise (non-NCR) detections
    franchise_high = sorted(by_area["franchise"]["high"], key=lambda f: -f["properties"]["score"])[:10]
    print()
    print("Top 10 franchise high-conf detections:")
    for f in franchise_high:
        lon, lat = f["geometry"]["coordinates"]
        tile = f["properties"]["tile_id"]
        s = f["properties"]["score"]
        print(f"  {tile:30s} s={s:.3f}  ({lat:.4f}, {lon:.4f})")


if __name__ == "__main__":
    main()
