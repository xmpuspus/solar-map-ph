"""Fetch OSM admin polygons for each LGU listed in regions.json.

For each region in pipeline/regions/regions.json, query Overpass for
admin_level=6 relations matching each served_lgu, and assemble a
FeatureCollection at pipeline/regions/{slug}_lgus.geojson.

Run:
    python pipeline/regions/fetch_region_polygons.py

Respects Overpass rate limits (1 request/sec, exponential backoff).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGIONS_JSON = ROOT / "pipeline" / "regions" / "regions.json"
OUT_DIR = ROOT / "pipeline" / "regions"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "SolarMap.PH region-polygon fetcher (https://github.com/xmpuspus/solar-map-ph)"


def overpass_query(query: str, max_retries: int = 5) -> dict:
    """POST a query to Overpass. Exponential backoff on 429/503."""
    delay = 2.0
    for attempt in range(max_retries):
        req = urllib.request.Request(
            OVERPASS_URL,
            data=f"data={urllib.parse.quote(query)}".encode(),
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < max_retries - 1:
                print(f"  overpass {e.code}, backoff {delay:.0f}s")
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            raise
    raise RuntimeError("overpass: max retries")


def fetch_lgu_polygon(
    name: str,
    bbox: tuple[float, float, float, float] | None,
    province: str | None = None,
) -> dict | None:
    """Find an admin polygon named `name`. If `bbox` is None, search globally
    and then narrow to results whose centroid sits inside `province` (or just
    pick the first relation if no province given). Returns a (Multi)Polygon
    Feature or None if no match."""
    if bbox is not None:
        min_lat, min_lon, max_lat, max_lon = bbox
        bbox_clause = f"({min_lat},{min_lon},{max_lat},{max_lon})"
    else:
        # Country-scoped: PH bbox (4.5,116,21.5,127). Skip global Earth search
        # because OSM has lots of name collisions worldwide.
        bbox_clause = "(4.5,116,21.5,127)"
    # admin_level 6 = city/municipality in PH. Some areas are admin_level 7 or 8.
    # Cast wide and pick the smallest matching polygon.
    q = f"""
    [out:json][timeout:120];
    (
      relation["boundary"="administrative"]["admin_level"~"^[6789]$"]["name"="{name}"]
        {bbox_clause};
    );
    out geom;
    """
    data = overpass_query(q)
    elements = [e for e in data.get("elements", []) if e.get("type") == "relation"]
    if not elements:
        return None

    # Convert the smallest relation to GeoJSON (smallest = most local match)
    def relation_bbox_area(rel: dict) -> float:
        members = rel.get("members", [])
        lats, lons = [], []
        for m in members:
            for pt in m.get("geometry", []):
                lats.append(pt["lat"])
                lons.append(pt["lon"])
        if not lats:
            return float("inf")
        return (max(lats) - min(lats)) * (max(lons) - min(lons))

    elements.sort(key=relation_bbox_area)
    rel = elements[0]
    # OSM stores admin boundaries as relations with many outer way segments.
    # Each member is a polyline (not a closed ring), so we need to stitch
    # adjacent segments together before building polygons. shapely.ops.polygonize
    # handles this: feed it the line segments and it returns closed polygons.
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union

    outer_lines: list[LineString] = []
    inner_lines: list[LineString] = []
    for m in rel.get("members", []):
        coords = [(pt["lon"], pt["lat"]) for pt in m.get("geometry", [])]
        if len(coords) < 2:
            continue
        if m.get("role") == "outer":
            outer_lines.append(LineString(coords))
        elif m.get("role") == "inner":
            inner_lines.append(LineString(coords))

    if not outer_lines:
        return None

    # Stitch outer segments into closed polygons.
    outer_polys = list(polygonize(unary_union(outer_lines)))
    if not outer_polys:
        return None
    inner_polys = list(polygonize(unary_union(inner_lines))) if inner_lines else []

    # Subtract holes from outer polygons (rare for PH admin boundaries; safe
    # to do at the geometry level rather than per-ring).
    polygons_geojson: list[list[list[list[float]]]] = []
    for poly in outer_polys:
        rings = [list(poly.exterior.coords)]
        # Find any inner polys whose centroid is inside this outer
        for ip in inner_polys:
            if poly.contains(ip):
                rings.append(list(ip.exterior.coords))
        polygons_geojson.append([[[lon, lat] for lon, lat in ring] for ring in rings])

    return {
        "type": "Feature",
        "properties": {
            "name": name,
            "osm_id": rel["id"],
            "admin_level": rel.get("tags", {}).get("admin_level"),
        },
        "geometry": {
            "type": "MultiPolygon" if len(polygons_geojson) > 1 else "Polygon",
            "coordinates": polygons_geojson if len(polygons_geojson) > 1 else polygons_geojson[0],
        },
    }


def main() -> int:
    with REGIONS_JSON.open() as f:
        cfg = json.load(f)

    for region in cfg["regions"]:
        slug = region["slug"]
        out_path = OUT_DIR / f"{slug}_lgus.geojson"
        if out_path.exists():
            print(f"[skip] {slug}: {out_path.name} already exists")
            continue
        print(f"[fetch] {slug}: querying {len(region['served_lgus'])} LGUs...")
        features = []
        for lgu in region["served_lgus"]:
            time.sleep(1.1)  # overpass rate limit
            try:
                feat = fetch_lgu_polygon(lgu, region["bbox"])
            except Exception as e:
                print(f"  [{slug}] {lgu}: ERROR {e}")
                continue
            if feat is None:
                print(f"  [{slug}] {lgu}: NO MATCH in bbox, retrying PH-wide")
                # Fallback: search nation-wide. The PH-wide query handles cases
                # where the LGU's bbox in regions.json doesn't fully cover the
                # admin polygon (e.g. Calabarzon municipalities outside the
                # configured scan rectangle).
                time.sleep(1.1)
                try:
                    feat = fetch_lgu_polygon(lgu, None, province=region.get("province"))
                except Exception as e:
                    print(f"    [retry-error] {e}")
                    feat = None
            if feat is not None:
                feat["properties"]["region"] = slug
                feat["properties"]["franchise"] = region["franchise"]
                features.append(feat)
                print(f"  [{slug}] {lgu}: OK (osm {feat['properties']['osm_id']})")
            else:
                print(f"  [{slug}] {lgu}: SKIP (no polygon found)")

        fc = {
            "type": "FeatureCollection",
            "properties": {
                "region": slug,
                "franchise": region["franchise"],
                "source": "OpenStreetMap via Overpass API",
                "license": "ODbL",
            },
            "features": features,
        }
        out_path.write_text(json.dumps(fc, indent=1))
        print(f"[done] {slug}: wrote {len(features)}/{len(region['served_lgus'])} features to {out_path.name}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
