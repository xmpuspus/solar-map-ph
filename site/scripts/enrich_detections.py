"""
Enrich site/public/data/rooftop_solar_ncr.geojson with osm_status (new|confirmed)
from detection/scan/match_report.json and lgu_name from a point-in-polygon join
against franchise_cities_polygons.geojson.

Also emit site/public/data/city_detection_counts.json with per-city aggregates:
  { name, n_high, n_candidate, n_new_high, n_confirmed_high, sum_kwp_high, density_per_km2 }

Run from repo root:  python3 site/scripts/enrich_detections.py
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "site" / "public" / "data"
DETECTIONS = DATA / "rooftop_solar_ncr.geojson"
PER_BUILDING = DATA / "per_building_solar_ncr.geojson"
FRANCHISE = DATA / "franchise_cities_polygons.geojson"
MATCH_REPORT = REPO / "detection" / "scan" / "match_report.json"
OUT_COUNTS = DATA / "city_detection_counts.json"


def point_in_ring(lon: float, lat: float, ring) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        intersect = ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi)
        if intersect:
            inside = not inside
        j = i
    return inside


def point_in_multipolygon(lon: float, lat: float, geom: dict) -> bool:
    if geom["type"] == "Polygon":
        polys = [geom["coordinates"]]
    elif geom["type"] == "MultiPolygon":
        polys = geom["coordinates"]
    else:
        return False
    for poly in polys:
        if not poly:
            continue
        outer = poly[0]
        if not point_in_ring(lon, lat, outer):
            continue
        in_hole = any(point_in_ring(lon, lat, hole) for hole in poly[1:])
        if not in_hole:
            return True
    return False


def bbox_of_geom(geom: dict) -> tuple[float, float, float, float]:
    if geom["type"] == "Polygon":
        polys = [geom["coordinates"]]
    elif geom["type"] == "MultiPolygon":
        polys = geom["coordinates"]
    else:
        return (math.inf, math.inf, -math.inf, -math.inf)
    minx = miny = math.inf
    maxx = maxy = -math.inf
    for poly in polys:
        for ring in poly:
            for x, y in ring:
                if x < minx:
                    minx = x
                if y < miny:
                    miny = y
                if x > maxx:
                    maxx = x
                if y > maxy:
                    maxy = y
    return minx, miny, maxx, maxy


def polygon_area_km2(geom: dict) -> float:
    """Equirectangular approximation -- close enough at city scale, no deps."""
    if geom["type"] == "Polygon":
        polys = [geom["coordinates"]]
    elif geom["type"] == "MultiPolygon":
        polys = geom["coordinates"]
    else:
        return 0.0
    earth_r = 6371.0088
    total = 0.0
    for poly in polys:
        if not poly:
            continue
        outer = poly[0]
        if len(outer) < 3:
            continue
        avg_lat = sum(p[1] for p in outer) / len(outer)
        cos_lat = math.cos(math.radians(avg_lat))
        s = 0.0
        for i in range(len(outer)):
            x1, y1 = outer[i]
            x2, y2 = outer[(i + 1) % len(outer)]
            s += (x2 - x1) * (y2 + y1)
        ring_area = abs(s) / 2.0
        ring_area_km2 = ring_area * (earth_r * math.radians(1)) ** 2 * cos_lat
        for hole in poly[1:]:
            if len(hole) < 3:
                continue
            s = 0.0
            for i in range(len(hole)):
                x1, y1 = hole[i]
                x2, y2 = hole[(i + 1) % len(hole)]
                s += (x2 - x1) * (y2 + y1)
            ring_area_km2 -= abs(s) / 2.0 * (earth_r * math.radians(1)) ** 2 * cos_lat
        total += ring_area_km2
    return total


def main() -> None:
    detections = json.loads(DETECTIONS.read_text())
    per_building = json.loads(PER_BUILDING.read_text())
    franchise = json.loads(FRANCHISE.read_text())
    match = json.loads(MATCH_REPORT.read_text())

    status_by_tile: dict[str, str] = {row["tile_id"]: row["status"] for row in match["rows"]}

    kwp_by_tile: dict[str, float] = {}
    for feat in per_building["features"]:
        props = feat["properties"]
        kwp = float(props.get("kwp_estimate") or 0.0)
        for tid in props.get("tile_ids") or [props.get("tile_id")]:
            if not tid:
                continue
            kwp_by_tile[tid] = kwp_by_tile.get(tid, 0.0) + kwp

    cities = []
    for feat in franchise["features"]:
        bbox = bbox_of_geom(feat["geometry"])
        area = polygon_area_km2(feat["geometry"])
        cities.append(
            {
                "name": feat["properties"]["name"],
                "province": feat["properties"].get("province", ""),
                "geometry": feat["geometry"],
                "bbox": bbox,
                "area_km2": area,
            }
        )

    n_with_status = 0
    n_with_city = 0
    aggregates: dict[str, dict] = defaultdict(
        lambda: {
            "n_high": 0,
            "n_candidate": 0,
            "n_new_high": 0,
            "n_confirmed_high": 0,
            "n_new_candidate": 0,
            "n_confirmed_candidate": 0,
            "sum_kwp_high": 0.0,
            "sum_kwp_all": 0.0,
        }
    )
    province_by_city: dict[str, str] = {}
    area_by_city: dict[str, float] = {}
    for c in cities:
        province_by_city[c["name"]] = c["province"]
        area_by_city[c["name"]] = c["area_km2"]

    for feat in detections["features"]:
        props = feat["properties"]
        tid = props["tile_id"]
        status = status_by_tile.get(tid, "unknown")
        props["osm_status"] = status
        if status != "unknown":
            n_with_status += 1

        kwp = kwp_by_tile.get(tid, 0.0)
        if kwp:
            props["kwp_estimate"] = round(kwp, 1)

        lon, lat = props["tile_center"]
        lgu = None
        for c in cities:
            minx, miny, maxx, maxy = c["bbox"]
            if not (minx <= lon <= maxx and miny <= lat <= maxy):
                continue
            if point_in_multipolygon(lon, lat, c["geometry"]):
                lgu = c["name"]
                break
        if lgu:
            props["lgu_name"] = lgu
            props["province"] = province_by_city.get(lgu, "")
            n_with_city += 1
            tier = props["tier"]
            agg = aggregates[lgu]
            if tier == "high":
                agg["n_high"] += 1
                if status == "new":
                    agg["n_new_high"] += 1
                elif status == "confirmed":
                    agg["n_confirmed_high"] += 1
                agg["sum_kwp_high"] += kwp
            else:
                agg["n_candidate"] += 1
                if status == "new":
                    agg["n_new_candidate"] += 1
                elif status == "confirmed":
                    agg["n_confirmed_candidate"] += 1
            agg["sum_kwp_all"] += kwp

    detections.setdefault("_meta", {})["enriched_with"] = {
        "osm_status_from": "detection/scan/match_report.json",
        "lgu_from": "site/public/data/franchise_cities_polygons.geojson",
        "kwp_from": "site/public/data/per_building_solar_ncr.geojson",
        "n_with_status": n_with_status,
        "n_with_city": n_with_city,
    }

    DETECTIONS.write_text(json.dumps(detections, separators=(",", ":")))

    rows = []
    for name, agg in aggregates.items():
        area = area_by_city.get(name, 0.0)
        rows.append(
            {
                "name": name,
                "province": province_by_city.get(name, ""),
                "n_high": agg["n_high"],
                "n_candidate": agg["n_candidate"],
                "n_new_high": agg["n_new_high"],
                "n_confirmed_high": agg["n_confirmed_high"],
                "n_new_candidate": agg["n_new_candidate"],
                "n_confirmed_candidate": agg["n_confirmed_candidate"],
                "sum_kwp_high": round(agg["sum_kwp_high"], 1),
                "sum_kwp_all": round(agg["sum_kwp_all"], 1),
                "area_km2": round(area, 2),
                "high_per_km2": round(agg["n_high"] / area, 4) if area else 0.0,
            }
        )
    rows.sort(key=lambda r: r["n_high"], reverse=True)
    OUT_COUNTS.write_text(
        json.dumps(
            {
                "_meta": {
                    "n_cities_with_detections": sum(1 for r in rows if r["n_high"] + r["n_candidate"] > 0),
                    "n_total_high": sum(r["n_high"] for r in rows),
                    "n_total_candidate": sum(r["n_candidate"] for r in rows),
                    "n_total_new_high": sum(r["n_new_high"] for r in rows),
                    "share_new_high": round(
                        sum(r["n_new_high"] for r in rows) / max(sum(r["n_high"] for r in rows), 1),
                        3,
                    ),
                },
                "rows": rows,
            },
            indent=2,
        )
    )

    print(f"detections enriched: {n_with_status}/{len(detections['features'])} have osm_status")
    print(f"detections enriched: {n_with_city}/{len(detections['features'])} have lgu_name")
    print(f"city aggregates written: {len(rows)} cities")
    top = rows[:5]
    for r in top:
        print(
            f"  {r['name']:18s} {r['n_high']:3d} high ({r['n_new_high']:3d} NEW), {r['n_candidate']:3d} cand, {r['sum_kwp_high']:.0f} kWp"
        )


if __name__ == "__main__":
    main()
