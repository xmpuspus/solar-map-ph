"""Smoke-test per_building_solar_ncr.geojson for structural and value sanity.

Asserts:
  - geojson is a FeatureCollection with required _meta keys
  - every feature has Polygon geometry with closed ring + >=4 points
  - every feature has required properties (osm_id, kwp_estimate, etc.)
  - kwp_estimate > 0 and panel_area_m2 > 0
  - panel_area_m2 <= building_area_m2 (we cap at building footprint)
  - confidence in [0, 1]

Exits 0 on pass, 1 on any failure (with details printed).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEOJSON = ROOT / "site" / "public" / "data" / "per_building_solar_ncr.geojson"

REQUIRED_PROPS = {
    "building_osm_id", "building_osm_type", "building_area_m2",
    "panel_area_m2", "kwp_estimate", "confidence",
    "n_segments_merged", "tile_id",
}
REQUIRED_META = {
    "tiles_processed", "buildings_with_solar", "polygon_strategy", "area_strategy",
}


def main() -> int:
    if not GEOJSON.exists():
        print(f"FAIL: {GEOJSON} missing")
        return 1
    fc = json.loads(GEOJSON.read_text())

    fails = []
    if fc.get("type") != "FeatureCollection":
        fails.append("type != FeatureCollection")
    meta = fc.get("_meta", {})
    missing_meta = REQUIRED_META - set(meta.keys())
    if missing_meta:
        fails.append(f"missing _meta keys: {missing_meta}")

    feats = fc.get("features", [])
    if not feats:
        fails.append("zero features (no buildings detected)")

    seen_ids = set()
    for i, f in enumerate(feats):
        ctx = f"feature {i} (osm_id={f.get('properties',{}).get('building_osm_id')})"

        # Geometry
        geom = f.get("geometry") or {}
        if geom.get("type") != "Polygon":
            fails.append(f"{ctx}: non-Polygon geometry")
            continue
        coords = geom.get("coordinates") or []
        if len(coords) != 1:
            fails.append(f"{ctx}: expected 1 ring, got {len(coords)}")
            continue
        ring = coords[0]
        if len(ring) < 4:
            fails.append(f"{ctx}: ring has <4 points")
        elif ring[0] != ring[-1]:
            fails.append(f"{ctx}: ring not closed")

        # Properties
        p = f.get("properties") or {}
        missing = REQUIRED_PROPS - set(p.keys())
        if missing:
            fails.append(f"{ctx}: missing props {missing}")
            continue

        # Value sanity
        if p["kwp_estimate"] <= 0:
            fails.append(f"{ctx}: kwp_estimate <= 0 ({p['kwp_estimate']})")
        if p["panel_area_m2"] <= 0:
            fails.append(f"{ctx}: panel_area_m2 <= 0")
        if p["building_area_m2"] <= 0:
            fails.append(f"{ctx}: building_area_m2 <= 0")
        if p["panel_area_m2"] > p["building_area_m2"] + 1:  # +1 for float slop
            fails.append(f"{ctx}: panel_area {p['panel_area_m2']} > building {p['building_area_m2']}")
        if not (0 <= p["confidence"] <= 1):
            fails.append(f"{ctx}: confidence out of [0,1] ({p['confidence']})")
        if p["n_segments_merged"] < 1:
            fails.append(f"{ctx}: n_segments_merged < 1")

        # Duplicate building IDs
        bid = p["building_osm_id"]
        if bid in seen_ids:
            fails.append(f"{ctx}: duplicate building_osm_id {bid}")
        seen_ids.add(bid)

    # Summary
    print(f"validated {len(feats)} features ({fc.get('_meta',{}).get('tiles_processed','?')} tiles)")
    if fails:
        print(f"FAIL: {len(fails)} issues:")
        for f in fails[:30]:
            print(f"  - {f}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
