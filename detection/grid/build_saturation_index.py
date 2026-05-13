"""Compute NCR-wide solar saturation index.

For each 240m grid cell across the NCR scan extent, compute:
  - n_panels_high      : high-confidence detected installs within 300m
  - n_panels_candidate : candidate detected installs within 300m
  - sum_kwp_installed  : sum of kwp_estimate for matched per-building features within 300m
  - n_buildings_solar  : unique OSM buildings with detected panels within 300m
  - tier               : "early" | "growing" | "saturated"

Tiering:
  early      : 0-2 high-conf installs and < 50 kWp total within 300m
  growing    : 3-7 high-conf installs OR 50-300 kWp within 300m
  saturated  : 8+ high-conf installs OR > 300 kWp within 300m

The 300 kWp threshold approximates 50% of a typical 50 kVA / ~40 kW PH residential
LV transformer's daytime hosting capacity (Meralco engineers run hosting-capacity
studies above ~15% feeder penetration; 300 kWp on a single residential feeder is
already well past that). The panel-count threshold captures cases where many
small installs accumulate.

Output: site/public/data/solar_saturation_ncr.geojson
  FeatureCollection of Polygon cells, each ~240m square in lon/lat.
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PER_BUILDING = ROOT / "site" / "public" / "data" / "per_building_solar_ncr.geojson"
TILE_LEVEL = ROOT / "site" / "public" / "data" / "rooftop_solar_ncr.geojson"
OUT = ROOT / "site" / "public" / "data" / "solar_saturation_ncr.geojson"

# NCR bbox + 240m cell size (matches detection/scan/ncr_scan.py)
NCR_BBOX = (14.40, 120.92, 14.78, 121.13)
TILE_DEG_LAT = 0.00216
TILE_DEG_LON = 0.00224

# 300m halo around each cell center for "in your neighborhood" lookup
HALO_M = 300.0

# Tier thresholds -- see module docstring
SATURATED_PANELS = 8
SATURATED_KWP = 300
GROWING_PANELS = 3
GROWING_KWP = 50


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def cell_polygon(lat: float, lon: float) -> list[list[float]]:
    """Return a closed Polygon ring [[lon, lat], ...] for a cell centered at lat/lon."""
    half_lat = TILE_DEG_LAT / 2
    half_lon = TILE_DEG_LON / 2
    return [
        [lon - half_lon, lat - half_lat],
        [lon + half_lon, lat - half_lat],
        [lon + half_lon, lat + half_lat],
        [lon - half_lon, lat + half_lat],
        [lon - half_lon, lat - half_lat],
    ]


def tier_for(n_high: int, kwp: float) -> str:
    if n_high >= SATURATED_PANELS or kwp >= SATURATED_KWP:
        return "saturated"
    if n_high >= GROWING_PANELS or kwp >= GROWING_KWP:
        return "growing"
    return "early"


def main() -> int:
    if not TILE_LEVEL.exists():
        print(f"[sat] missing {TILE_LEVEL}", file=sys.stderr)
        return 1
    tile_fc = json.loads(TILE_LEVEL.read_text())
    pb_fc = json.loads(PER_BUILDING.read_text()) if PER_BUILDING.exists() else {"features": []}

    # Build numpy arrays of detection lat/lon for fast neighborhood lookup
    high_pts = np.array(
        [
            (f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0])
            for f in tile_fc["features"]
            if f["properties"]["tier"] == "high"
        ],
        dtype=np.float64,
    )
    cand_pts = np.array(
        [
            (f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0])
            for f in tile_fc["features"]
            if f["properties"]["tier"] == "candidate"
        ],
        dtype=np.float64,
    )

    # Per-building points + kwp (use the polygon centroid)
    pb_pts = []
    pb_kwp = []
    pb_osm_id = []
    for f in pb_fc["features"]:
        ring = f["geometry"]["coordinates"][0]
        clon = sum(p[0] for p in ring) / max(1, len(ring))
        clat = sum(p[1] for p in ring) / max(1, len(ring))
        pb_pts.append((clat, clon))
        pb_kwp.append(f["properties"]["kwp_estimate"])
        pb_osm_id.append(f["properties"]["building_osm_id"])
    pb_pts = np.array(pb_pts, dtype=np.float64) if pb_pts else np.zeros((0, 2))
    pb_kwp = np.array(pb_kwp, dtype=np.float64) if pb_kwp else np.zeros(0)

    print(f"[sat] high pts: {len(high_pts)}  candidate pts: {len(cand_pts)}  per_building pts: {len(pb_pts)}")

    # Generate cells
    s, w, n, e = NCR_BBOX
    lats = np.arange(s + TILE_DEG_LAT / 2, n, TILE_DEG_LAT)
    lons = np.arange(w + TILE_DEG_LON / 2, e, TILE_DEG_LON)
    n_cells = len(lats) * len(lons)
    print(f"[sat] generating {n_cells} cells ({len(lats)} x {len(lons)})")

    feats: list[dict] = []
    n_emit = 0
    n_drop = 0

    # Pre-build: convert the halo (300m) to a coarse degree budget so we can pre-filter
    # candidates per cell (avoid O(n_cells * n_pts) haversine).
    deg_budget = HALO_M / 111_320.0 * 1.5  # generous

    for la in lats:
        # Pre-filter all points within deg_budget of THIS lat row to avoid scanning all per cell
        if len(high_pts):
            row_high_mask = np.abs(high_pts[:, 0] - la) < deg_budget
            row_high = high_pts[row_high_mask]
        else:
            row_high = high_pts
        if len(cand_pts):
            row_cand_mask = np.abs(cand_pts[:, 0] - la) < deg_budget
            row_cand = cand_pts[row_cand_mask]
        else:
            row_cand = cand_pts
        if len(pb_pts):
            row_pb_mask = np.abs(pb_pts[:, 0] - la) < deg_budget
            row_pb = pb_pts[row_pb_mask]
            row_pb_kwp = pb_kwp[row_pb_mask]
        else:
            row_pb = pb_pts
            row_pb_kwp = pb_kwp

        for lo in lons:
            # Compute haversine from cell center to all candidates in row
            def within_halo(arr):
                if len(arr) == 0:
                    return np.zeros(0, dtype=bool)
                lat_diff = np.radians(arr[:, 0] - la)
                lon_diff = np.radians(arr[:, 1] - lo)
                a = (
                    np.sin(lat_diff / 2) ** 2
                    + np.cos(np.radians(la)) * np.cos(np.radians(arr[:, 0])) * np.sin(lon_diff / 2) ** 2
                )
                d = 2 * 6_371_000.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
                return d <= HALO_M

            high_mask = within_halo(row_high)
            cand_mask = within_halo(row_cand)
            pb_mask = within_halo(row_pb) if len(row_pb) else np.zeros(0, dtype=bool)

            n_high = int(high_mask.sum())
            n_cand = int(cand_mask.sum())
            sum_kwp = float(row_pb_kwp[pb_mask].sum()) if len(row_pb) else 0.0
            n_buildings = int(pb_mask.sum())

            # Skip cells with no detections at all to keep file size manageable
            if n_high == 0 and n_cand == 0 and n_buildings == 0:
                n_drop += 1
                continue

            tier = tier_for(n_high, sum_kwp)
            feats.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [cell_polygon(float(la), float(lo))]},
                    "properties": {
                        "cell_lat": round(float(la), 5),
                        "cell_lon": round(float(lo), 5),
                        "n_panels_high": n_high,
                        "n_panels_candidate": n_cand,
                        "n_buildings_solar": n_buildings,
                        "sum_kwp_installed": round(sum_kwp, 1),
                        "tier": tier,
                    },
                }
            )
            n_emit += 1

    fc = {
        "type": "FeatureCollection",
        "features": feats,
        "_meta": {
            "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "halo_radius_m": HALO_M,
            "cell_size_m_approx": 240,
            "n_cells_emitted": n_emit,
            "n_cells_empty_dropped": n_drop,
            "tier_thresholds": {
                "saturated_panels_min": SATURATED_PANELS,
                "saturated_kwp_min": SATURATED_KWP,
                "growing_panels_min": GROWING_PANELS,
                "growing_kwp_min": GROWING_KWP,
            },
            "interpretation": {
                "early": "Few or no detected installs in 300m. You'd be a pioneer -- fast approval likely.",
                "growing": "Adoption climbing in 300m. Expect more attention from Meralco engineers.",
                "saturated": "High solar density in 300m. Your installer should request a hosting-capacity check before sizing.",
            },
            "sources": {
                "tile_level": "site/public/data/rooftop_solar_ncr.geojson",
                "per_building": "site/public/data/per_building_solar_ncr.geojson",
            },
        },
    }
    OUT.write_text(json.dumps(fc, indent=1))
    print(f"[sat] wrote {n_emit} cells (dropped {n_drop} empty) -> {OUT}")
    print("[sat] tier distribution:")
    from collections import Counter

    c = Counter(f["properties"]["tier"] for f in feats)
    for t in ("early", "growing", "saturated"):
        print(f"  {t}: {c.get(t, 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
