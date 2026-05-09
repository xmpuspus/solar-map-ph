"""Aggregate per-cell saturation up to city/municipality level.

For each franchise city polygon:
  - Count detections (high + candidate) whose tile center falls inside
  - Sum kWp from per_building polygons whose centroid falls inside
  - Estimate "saturation score" = sum_kwp / built_area_proxy
    (we don't have feeder-level capacity per city, so rank cities by
    raw installed kWp + by kWp-per-detected-building)

Output: site/public/data/city_solar_saturation.json
  list of { city, province, n_high, n_candidate, n_buildings, sum_kwp, mean_kwp_per_building }
  sorted descending by sum_kwp.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TILE = ROOT / "site" / "public" / "data" / "rooftop_solar_ncr.geojson"
PB = ROOT / "site" / "public" / "data" / "per_building_solar_ncr.geojson"
CITIES = ROOT / "site" / "public" / "data" / "franchise_cities_polygons.geojson"
OUT = ROOT / "site" / "public" / "data" / "city_solar_saturation.json"


def point_in_polygon(point: tuple[float, float], poly: list[list[float]]) -> bool:
    x, y = point
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i][0], poly[i][1]
        xj, yj = poly[j][0], poly[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def point_in_geometry(point, geom) -> bool:
    if not geom:
        return False
    if geom["type"] == "Polygon":
        for ring in geom["coordinates"]:
            # Outer ring; ignore holes for our purposes (PH cities don't have holes typically)
            if point_in_polygon(point, ring):
                return True
        return False
    if geom["type"] == "MultiPolygon":
        for poly in geom["coordinates"]:
            for ring in poly:
                if point_in_polygon(point, ring):
                    return True
        return False
    return False


def main() -> int:
    if not all(p.exists() for p in (TILE, PB, CITIES)):
        print("[city-sat] missing inputs", file=sys.stderr)
        return 1
    cities = json.loads(CITIES.read_text())
    tiles = json.loads(TILE.read_text())
    pbs = json.loads(PB.read_text())

    rollup = []
    for city_feat in cities["features"]:
        cprops = city_feat["properties"] or {}
        city_name = cprops.get("name") or cprops.get("city") or cprops.get("ADM3_EN") or "?"
        province = cprops.get("province") or cprops.get("ADM2_EN") or ""
        n_high = n_cand = 0
        # Count tile detections inside city
        for f in tiles["features"]:
            pt = tuple(f["geometry"]["coordinates"])  # (lon, lat)
            if not point_in_geometry(pt, city_feat["geometry"]):
                continue
            tier = f["properties"]["tier"]
            if tier == "high":
                n_high += 1
            elif tier == "candidate":
                n_cand += 1
        # Per-building installs
        n_b = 0
        sum_kwp = 0.0
        for f in pbs["features"]:
            ring = f["geometry"]["coordinates"][0]
            clon = sum(p[0] for p in ring) / max(1, len(ring))
            clat = sum(p[1] for p in ring) / max(1, len(ring))
            if not point_in_geometry((clon, clat), city_feat["geometry"]):
                continue
            n_b += 1
            sum_kwp += f["properties"]["kwp_estimate"]

        rollup.append({
            "city": city_name,
            "province": province,
            "n_high": n_high,
            "n_candidate": n_cand,
            "n_buildings_solar": n_b,
            "sum_kwp": round(sum_kwp, 1),
            "mean_kwp_per_building": round(sum_kwp / n_b, 1) if n_b else 0.0,
        })

    rollup.sort(key=lambda r: -r["sum_kwp"])
    OUT.write_text(json.dumps(rollup, indent=2))
    print(f"[city-sat] wrote {len(rollup)} cities -> {OUT}")
    print()
    print("Top 10 by total installed kWp:")
    for r in rollup[:10]:
        print(f"  {r['city']:<25} {r['n_high']:>3}H {r['n_candidate']:>3}C  {r['n_buildings_solar']:>3}bldg  {r['sum_kwp']:>8.0f} kWp")
    print()
    print("Bottom 10 (cities with detections but smallest installed):")
    nonzero = [r for r in rollup if r["sum_kwp"] > 0]
    for r in nonzero[-10:]:
        print(f"  {r['city']:<25} {r['n_high']:>3}H {r['n_candidate']:>3}C  {r['n_buildings_solar']:>3}bldg  {r['sum_kwp']:>8.1f} kWp")
    return 0


if __name__ == "__main__":
    sys.exit(main())
