"""Overpass-API building lookup for SolarMap.PH.

Queries Overpass for OSM building polygons within a radius of a point.
Returns shapely-style polygon records plus metadata. Used by the per-building
solar localization stage and by the homeowner roof-lookup tool on the site.

OSM is the source of truth for building geometry in SolarMap.PH. Microsoft
Building Footprints would be a higher-coverage alternative, but the
user-facing site already keys off OSM building IDs, so we keep one canonical
ID space across the pipeline and the UI.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "solar-map-ph/2.1 (per-building-solar; +https://github.com/xmpuspus/solar-map-ph)"


@dataclass
class BuildingFeature:
    osm_id: int
    osm_type: str           # "way" or "relation"
    coords: list[list[float]]   # [[lon, lat], ...] outer ring, closed
    centroid: tuple[float, float]   # (lon, lat)
    bbox: tuple[float, float, float, float]   # (min_lon, min_lat, max_lon, max_lat)
    area_m2: float
    building_type: str | None
    is_residential: bool
    is_commercial: bool

    def to_geojson_feature(self) -> dict:
        return {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [self.coords]},
            "properties": {
                "osm_id": self.osm_id,
                "osm_type": self.osm_type,
                "area_m2": self.area_m2,
                "building_type": self.building_type,
                "is_residential": self.is_residential,
                "is_commercial": self.is_commercial,
            },
        }


# Shared with the site's RoofLookup component so building classification is
# consistent across the pipeline and the homeowner UI.
RESIDENTIAL_TAGS = {
    "house", "residential", "detached", "semidetached_house", "terrace",
    "apartments", "bungalow", "cabin", "dormitory", "barracks",
}
COMMERCIAL_TAGS = {
    "commercial", "industrial", "warehouse", "supermarket", "retail",
    "office", "school", "kindergarten", "university", "college", "hospital",
    "church", "civic", "government", "public", "yes",  # 'yes' falls through
    "transportation", "depot", "manufacture",
}


def overpass_buildings(lat: float, lon: float, radius_m: float = 200) -> list[dict]:
    """Run the Overpass building-within-radius query."""
    query = (
        "[out:json][timeout:25];("
        f'way["building"](around:{radius_m},{lat},{lon});'
        f'relation["building"](around:{radius_m},{lat},{lon});'
        ");out geom;"
    )
    body = "data=" + urllib.parse.quote(query)
    req = urllib.request.Request(
        OVERPASS_URL,
        data=body.encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["elements"]


def _polygon_area_m2(coords: list[list[float]]) -> float:
    """Approximate area of a small polygon (lon, lat -> meters via local-flat).

    Cheaper than turf.area but accurate enough for tile-scale buildings.
    """
    if len(coords) < 4:
        return 0.0
    # Convert to local meters via mean lat
    lats = [p[1] for p in coords]
    lons = [p[0] for p in coords]
    mean_lat = sum(lats) / len(lats)
    import math
    cos_lat = math.cos(math.radians(mean_lat))
    M_PER_DEG = 111_320.0
    pts_m = [
        ((lon - lons[0]) * M_PER_DEG * cos_lat, (lat - lats[0]) * M_PER_DEG)
        for lon, lat in coords
    ]
    # Shoelace
    n = len(pts_m)
    s = 0.0
    for i in range(n):
        x0, y0 = pts_m[i]
        x1, y1 = pts_m[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2.0


def _centroid(coords: list[list[float]]) -> tuple[float, float]:
    n = max(1, len(coords))
    return (sum(p[0] for p in coords) / n, sum(p[1] for p in coords) / n)


def parse_overpass_elements(elements: list[dict]) -> list[BuildingFeature]:
    out: list[BuildingFeature] = []
    for el in elements:
        coords: list[list[float]] | None = None
        if el.get("type") == "way" and el.get("geometry"):
            coords = [[p["lon"], p["lat"]] for p in el["geometry"]]
        elif el.get("type") == "relation" and el.get("members"):
            outer = next(
                (m for m in el["members"] if m.get("role") == "outer" and m.get("geometry")),
                None,
            )
            if outer and outer.get("geometry"):
                coords = [[p["lon"], p["lat"]] for p in outer["geometry"]]
        if not coords or len(coords) < 4:
            continue
        # Close ring
        if coords[0] != coords[-1]:
            coords = coords + [coords[0]]
        area = _polygon_area_m2(coords)
        if area < 12:
            continue
        tags = el.get("tags") or {}
        b_type_raw = tags.get("building")
        b_type = b_type_raw if b_type_raw and b_type_raw != "yes" else (tags.get("amenity") or tags.get("shop"))
        is_res = bool(b_type) and b_type in RESIDENTIAL_TAGS
        is_com = bool(b_type) and b_type in COMMERCIAL_TAGS
        lons = [p[0] for p in coords]
        lats = [p[1] for p in coords]
        out.append(BuildingFeature(
            osm_id=el["id"],
            osm_type=el["type"],
            coords=coords,
            centroid=_centroid(coords),
            bbox=(min(lons), min(lats), max(lons), max(lats)),
            area_m2=area,
            building_type=b_type,
            is_residential=is_res,
            is_commercial=is_com,
        ))
    return out


def fetch_buildings_around(lat: float, lon: float, radius_m: float = 200,
                            cache_dir: Path | None = None) -> list[BuildingFeature]:
    """Fetch + parse + cache. Cache key is rounded lat/lon/radius."""
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = f"{lat:.5f}_{lon:.5f}_r{int(radius_m)}.json"
        cache_path = cache_dir / key
        if cache_path.exists():
            try:
                elements = json.loads(cache_path.read_text())
                return parse_overpass_elements(elements)
            except Exception:
                pass
    elements = overpass_buildings(lat, lon, radius_m)
    if cache_dir is not None:
        cache_path = cache_dir / key
        cache_path.write_text(json.dumps(elements))
    return parse_overpass_elements(elements)


if __name__ == "__main__":
    # Smoke test: fetch buildings near Greenhills, San Juan
    test_lat, test_lon = 14.6042, 121.0498
    bs = fetch_buildings_around(test_lat, test_lon, radius_m=200)
    print(f"Found {len(bs)} buildings near {test_lat},{test_lon}")
    for b in bs[:5]:
        print(f"  osm_id={b.osm_id} type={b.osm_type} area={b.area_m2:.0f}m2  building={b.building_type}")
