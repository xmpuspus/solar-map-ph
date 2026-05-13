"""Assemble per-building solar panel features from SAM segments + OSM buildings.

Inputs:
  detection/scan/per_tile_segments.jsonl
    (one tile per line, list of segment polygons each with score/lonlat_bbox/area)

For each tile with segments:
  1. Fetch OSM buildings around (tile_lat, tile_lon, radius=200m) via Overpass
     (cached to detection/buildings/cache/)
  2. For each segment polygon, find which building it intersects (centroid-in-polygon
     or bbox-overlap)
  3. Emit one Feature per (building, segment) pair with kwp_estimate = area_m2 / 6
     (rule of thumb: ~6 m^2 per kWp for crystalline silicon)

Output:
  site/public/data/per_building_solar_ncr.geojson

Properties on each Feature:
  building_osm_id, building_osm_type, building_type, area_m2 (panel),
  kwp_estimate, confidence (segment LR score), tile_id, tile_score
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEGMENTS_JSONL = ROOT / "detection" / "scan" / "per_tile_segments.jsonl"
OUT = ROOT / "site" / "public" / "data" / "per_building_solar_ncr.geojson"
BUILDING_CACHE = ROOT / "detection" / "buildings" / "cache"

sys.path.insert(0, str(ROOT))
from detection.buildings.fetch_buildings import (
    BuildingFeature, fetch_buildings_around, _polygon_area_m2,
)


def m_per_deg(lat: float) -> tuple[float, float]:
    """Local-flat meters-per-degree at given latitude."""
    return (111_320.0 * math.cos(math.radians(lat)), 111_320.0)


def polygon_area_m2_lonlat(coords: list[list[float]]) -> float:
    return _polygon_area_m2(coords)


def polygon_centroid(coords: list[list[float]]) -> tuple[float, float]:
    n = max(1, len(coords))
    return (sum(p[0] for p in coords) / n, sum(p[1] for p in coords) / n)


def point_in_polygon(point: tuple[float, float], poly: list[list[float]]) -> bool:
    """Ray-cast point-in-polygon. Polygon should be a closed ring [[lon,lat], ...]."""
    x, y = point
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i][0], poly[i][1]
        xj, yj = poly[j][0], poly[j][1]
        intersects = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi)
        if intersects:
            inside = not inside
        j = i
    return inside


def bbox_overlaps(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def best_building_for_segment(segment: dict, buildings: list[BuildingFeature]) -> BuildingFeature | None:
    """Return the building that contains the segment centroid; if none, the building
    whose polygon overlaps the segment bbox by largest area; else None."""
    if not buildings:
        return None
    seg_poly = segment.get("polygon") or []
    if not seg_poly:
        return None
    seg_centroid = polygon_centroid(seg_poly)
    seg_bbox = tuple(segment["lonlat_bbox"])

    # First pass: centroid inside any building
    for b in buildings:
        if not bbox_overlaps(seg_bbox, b.bbox):
            continue
        if point_in_polygon(seg_centroid, b.coords):
            return b

    # Second pass: largest bbox-overlap building
    best = None
    best_overlap = 0.0
    for b in buildings:
        if not bbox_overlaps(seg_bbox, b.bbox):
            continue
        overlap_w = max(0, min(seg_bbox[2], b.bbox[2]) - max(seg_bbox[0], b.bbox[0]))
        overlap_h = max(0, min(seg_bbox[3], b.bbox[3]) - max(seg_bbox[1], b.bbox[1]))
        overlap = overlap_w * overlap_h
        if overlap > best_overlap:
            best_overlap = overlap
            best = b
    return best


def main() -> int:
    if not SEGMENTS_JSONL.exists():
        print(f"[per-building] no segments file: {SEGMENTS_JSONL}", file=sys.stderr)
        return 1
    BUILDING_CACHE.mkdir(parents=True, exist_ok=True)

    # Group segments by building OSM id. SAM tends to over-segment a single solar
    # array on a large rooftop -- without grouping, one commercial roof would
    # produce 8-30 tiny features all hitting the same OSM building, which
    # inflates the per-building geojson and confuses the UI.
    by_building: dict[int, dict] = {}
    n_tiles = 0
    n_segs_in = 0
    n_unmatched = 0
    _meta_tracker: dict = {}

    with SEGMENTS_JSONL.open() as f:
        for line in f:
            try:
                tile_rec = json.loads(line)
            except Exception:
                continue
            n_tiles += 1
            segs = tile_rec.get("segments") or []
            if not segs:
                continue
            n_segs_in += len(segs)
            tile_lat = tile_rec["tile_lat"]
            tile_lon = tile_rec["tile_lon"]
            tile_id = tile_rec["tile_id"]
            tile_score = tile_rec["tile_score"]

            cache_hit = (BUILDING_CACHE / f"{tile_lat:.5f}_{tile_lon:.5f}_r200.json").exists()
            try:
                buildings = fetch_buildings_around(
                    tile_lat, tile_lon, radius_m=200, cache_dir=BUILDING_CACHE,
                )
                overpass_fetch_ok = True
            except Exception as exc:
                print(f"[per-building] overpass failed for {tile_id}: {exc}", file=sys.stderr)
                buildings = []
                overpass_fetch_ok = False
            # Only sleep when we actually hit Overpass (cache hits are free).
            # 1.1 s respects the public Overpass guideline of 1 req/s sustained.
            if not cache_hit:
                time.sleep(1.1)
            # Surface whether buildings == [] meant "no buildings here" vs "API failed"
            if not overpass_fetch_ok:
                # bump a counter visible in _meta so users can spot silent recall loss
                _meta_tracker.setdefault("tiles_overpass_failed", []).append(tile_id)

            for seg in segs:
                b = best_building_for_segment(seg, buildings)
                if b is None:
                    n_unmatched += 1
                    continue

                # Compute panel area in m^2 from the segment polygon
                if seg.get("polygon"):
                    panel_area_m2 = polygon_area_m2_lonlat(seg["polygon"])
                else:
                    bb = seg["lonlat_bbox"]
                    mpd_lon, mpd_lat = m_per_deg(tile_lat)
                    panel_area_m2 = abs(bb[2] - bb[0]) * mpd_lon * abs(bb[3] - bb[1]) * mpd_lat

                rec = by_building.setdefault(b.osm_id, {
                    "building": b,
                    "segments": [],
                    "tiles": set(),
                })
                rec["segments"].append({
                    "polygon": seg.get("polygon") or [],
                    "panel_area_m2": panel_area_m2,
                    "confidence": seg["score"],
                    "tile_id": tile_id,
                    "tile_score": tile_score,
                    "seg_idx": seg["seg_idx"],
                })
                rec["tiles"].add(tile_id)

    feats: list[dict] = []
    n_pairs = 0
    n_suppressed_residential = 0
    residential_aggregate: dict[str, int] = {}  # building_type -> count
    residential_kwp_total = 0.0
    for osm_id, rec in by_building.items():
        b = rec["building"]
        segs = rec["segments"]
        # Cap building's panel area at building footprint area (sanity gate against
        # SAM over-segmenting nearby ground as part of a panel).
        total_panel = sum(s["panel_area_m2"] for s in segs)
        total_panel = min(total_panel, b.area_m2)
        # Confidence is the max single-segment score
        max_conf = max(s["confidence"] for s in segs)
        # Polygon: use the highest-confidence segment as the displayed polygon.
        # Multi-polygon merging is overkill for v2.1 - a single representative
        # outline is enough for the site's per-building readout.
        best_seg = max(segs, key=lambda s: s["confidence"])
        polygon = best_seg["polygon"] or []
        if not polygon:
            continue
        kwp = round(total_panel / 6.0, 2)

        # Privacy: residential rooftops are aggregated into counts only, not
        # published as sub-meter polygons. A precise polygon plus building_type
        # equals an addressable home; that is reidentifiable PII even when the
        # underlying OSM data is public, because the aggregation is the harm.
        # Commercial, industrial, public, and unclassified buildings are kept.
        if b.is_residential:
            n_suppressed_residential += 1
            bt = b.building_type or "residential"
            residential_aggregate[bt] = residential_aggregate.get(bt, 0) + 1
            residential_kwp_total += kwp
            continue

        feats.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [polygon]},
            "properties": {
                "building_osm_id": b.osm_id,
                "building_osm_type": b.osm_type,
                "building_area_m2": round(b.area_m2, 1),
                "building_type": b.building_type,
                "is_residential": b.is_residential,
                "is_commercial": b.is_commercial,
                "panel_area_m2": round(total_panel, 1),
                "kwp_estimate": kwp,
                "confidence": round(max_conf, 4),
                "n_segments_merged": len(segs),
                "tile_ids": sorted(rec["tiles"]),
                "tile_id": best_seg["tile_id"],   # primary tile
                "tile_score": best_seg["tile_score"],
            },
        })
        n_pairs += 1

    fc = {
        "type": "FeatureCollection",
        "features": feats,
        "_meta": {
            "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tiles_processed": n_tiles,
            "segments_total": n_segs_in,
            "buildings_with_solar_published": n_pairs,
            "buildings_residential_suppressed": n_suppressed_residential,
            "segments_unmatched_to_building": n_unmatched,
            "kwp_per_m2": 1.0 / 6.0,
            "source_segments": str(SEGMENTS_JSONL.relative_to(ROOT)),
            "building_source": "OSM via Overpass (radius=200m around each tile)",
            "scoring": "0.6*CLIP+LR (clf_v4) + 0.4*color signature; merged per-building",
            "polygon_strategy": "highest-confidence segment per building",
            "area_strategy": "summed across segments, capped at building footprint area",
            "privacy_policy": (
                "Buildings tagged is_residential (house, apartments, residential, etc.) "
                "are aggregated into counts only and not published as polygons. "
                "See site/public/data/residential_solar_aggregate.json for the privacy-safe roll-up."
            ),
            "tiles_overpass_failed": len(_meta_tracker.get("tiles_overpass_failed", [])),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(fc, indent=1))

    # Privacy-safe residential aggregate (counts and totals, no geometry, no addresses).
    aggregate_path = OUT.parent / "residential_solar_aggregate.json"
    aggregate_path.write_text(json.dumps({
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_residential_buildings_with_solar": n_suppressed_residential,
        "kwp_residential_total": round(residential_kwp_total, 2),
        "by_building_type": dict(sorted(residential_aggregate.items())),
        "policy": (
            "Residential rooftops are intentionally not published as individual "
            "polygons. This roll-up is the only residential-scoped figure ghost-watts releases."
        ),
    }, indent=2))

    print(f"[per-building] {n_pairs} non-residential buildings published with detected solar")
    print(f"[per-building] {n_suppressed_residential} residential buildings suppressed (counts in {aggregate_path.name})")
    print(f"[per-building] {n_unmatched} segments had no matching OSM building (likely informal structures or off-roof)")
    print(f"[per-building] -> {OUT}")
    print(f"[per-building] -> {aggregate_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
