"""Step 6 of v1.2: recover served-LGU admin polygons that the name-based
fetch_region_polygons.py missed.

Root cause (memory: vercel-site-root-boundary / v11 known gaps): some served
LGUs in regions.json use a name that does not match the OSM admin relation's
`name` tag (EB Magalona, Mandaue, "Lapu-Lapu City" vs OSM "Lapu-Lapu"). The
name-only query returns nothing, no polygon is written, and aggregate_region's
assign_city returns None for every detection in that LGU, so the detections
silently drop out of the published city tables and the map sidebar undercounts.

This script, for every served LGU with no polygon in <slug>_lgus.geojson:
  1. consults pipeline/regions/served_lgu_osm_map.json (verified relation-ID
     overrides) first;
  2. else queries Overpass for an admin relation matching any of a set of name
     variants (exact, strip " City", and the OSM name / name:en / official_name
     / alt_name tags), PH-scoped, picking the smallest relation whose centroid
     lies in the region bbox;
  3. appends the recovered polygon to <slug>_lgus.geojson with the same schema
     (name uses the regions.json canonical name so assign_city matches), and
     records the resolved relation ID back into served_lgu_osm_map.json.

After this, re-run aggregate_region.py for each touched region. Detections that
fall outside every served polygon (rectangular bbox > franchise area, e.g.
Calabarzon) are a separate concern handled in aggregate_region.py by an
explicit out-of-franchise bucket, not by this script.

Run:
    python pipeline/regions/fetch_missing_lgu_polygons.py
    python pipeline/regions/fetch_missing_lgu_polygons.py --region cebu
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGIONS_JSON = ROOT / "pipeline" / "regions" / "regions.json"
OUT_DIR = ROOT / "pipeline" / "regions"
OVERRIDE_MAP = ROOT / "pipeline" / "regions" / "served_lgu_osm_map.json"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "SolarMap.PH missing-lgu fetcher (https://github.com/xmpuspus/solar-map-ph)"


RETRYABLE_HTTP = {429, 500, 502, 503, 504}


def overpass(query: str, max_retries: int = 8) -> dict:
    """POST to Overpass with backoff. The public instance is frequently
    overloaded and returns 429/502/503/504 transiently; those must be retried,
    not treated as a permanent miss (a 504 is not 'this LGU does not exist')."""
    delay = 5.0
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
            if e.code in RETRYABLE_HTTP and attempt < max_retries - 1:
                time.sleep(delay)
                delay = min(delay * 1.7, 90)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay = min(delay * 1.7, 90)
                continue
            raise
    raise RuntimeError("overpass: max retries")


def name_variants(name: str) -> list[str]:
    v = {name}
    if name.endswith(" City"):
        v.add(name[: -len(" City")])
    else:
        v.add(name + " City")
    if name.startswith("Santa "):
        v.add("Sta. " + name[len("Santa "):])
    if name.startswith("Sto. "):
        v.add("Santo " + name[len("Sto. "):])
    return sorted(v)


def _relation_to_feature(rel: dict, canonical_name: str) -> dict | None:
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union

    outer, inner = [], []
    for m in rel.get("members", []):
        coords = [(pt["lon"], pt["lat"]) for pt in m.get("geometry", [])]
        if len(coords) < 2:
            continue
        (outer if m.get("role") == "outer" else inner).append(LineString(coords))
    if not outer:
        return None
    outer_polys = list(polygonize(unary_union(outer)))
    if not outer_polys:
        return None
    inner_polys = list(polygonize(unary_union(inner))) if inner else []
    polys: list = []
    for poly in outer_polys:
        rings = [list(poly.exterior.coords)]
        for ip in inner_polys:
            if poly.contains(ip):
                rings.append(list(ip.exterior.coords))
        polys.append([[[lon, lat] for lon, lat in ring] for ring in rings])
    return {
        "type": "Feature",
        "properties": {
            "name": canonical_name,
            "osm_id": rel["id"],
            "admin_level": rel.get("tags", {}).get("admin_level"),
        },
        "geometry": {
            "type": "MultiPolygon" if len(polys) > 1 else "Polygon",
            "coordinates": polys if len(polys) > 1 else polys[0],
        },
    }


NOMINATIM = "https://nominatim.openstreetmap.org/lookup"


def fetch_by_relation_id_nominatim(rel_id: int, canonical_name: str) -> dict | None:
    """Resolve a verified OSM relation's boundary polygon via Nominatim
    lookup (polygon_geojson=1). Reliable and Overpass-independent: one call,
    returns ready GeoJSON. Used for override-map entries."""
    q = urllib.parse.urlencode({"osm_ids": f"R{rel_id}", "format": "json",
                                "polygon_geojson": 1})
    req = urllib.request.Request(f"{NOMINATIM}?{q}",
                                 headers={"User-Agent": USER_AGENT})
    delay = 4.0
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            break
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            if attempt < 4:
                time.sleep(delay)
                delay = min(delay * 1.7, 40)
                continue
            return None
    if not data:
        return None
    g = data[0].get("geojson")
    if not g or g.get("type") not in ("Polygon", "MultiPolygon"):
        return None
    return {
        "type": "Feature",
        "properties": {
            "name": canonical_name,
            "osm_id": rel_id,
            "admin_level": (data[0].get("extratags") or {}).get("admin_level"),
        },
        "geometry": g,
    }


def fetch_by_relation_id(rel_id: int, canonical_name: str) -> dict | None:
    q = f"[out:json][timeout:120];relation({rel_id});out geom;"
    data = overpass(q)
    rels = [e for e in data.get("elements", []) if e.get("type") == "relation"]
    return _relation_to_feature(rels[0], canonical_name) if rels else None


def centroid(feat: dict) -> tuple[float, float]:
    coords = feat["geometry"]["coordinates"]
    rings = coords if feat["geometry"]["type"] == "Polygon" else [p[0] for p in coords]
    pts = [pt for ring in ([rings[0]] if feat["geometry"]["type"] == "Polygon" else rings) for pt in ring]
    lons = [p[0] for p in pts]
    lats = [p[1] for p in pts]
    return sum(lats) / len(lats), sum(lons) / len(lons)


def fetch_by_name(name: str, bbox: tuple[float, float, float, float]) -> dict | None:
    min_lat, min_lon, max_lat, max_lon = bbox
    variants = name_variants(name)
    name_filter = "".join(
        f'relation["boundary"="administrative"]["admin_level"~"^[5-9]$"]'
        f'["{tag}"="{v}"](4.5,116,21.5,127);\n'
        for v in variants
        for tag in ("name", "name:en", "official_name", "alt_name")
    )
    q = f"[out:json][timeout:150];(\n{name_filter});out geom;"
    data = overpass(q)
    rels = [e for e in data.get("elements", []) if e.get("type") == "relation"]
    if not rels:
        return None

    def area(rel: dict) -> float:
        lats, lons = [], []
        for m in rel.get("members", []):
            for pt in m.get("geometry", []):
                lats.append(pt["lat"])
                lons.append(pt["lon"])
        return (max(lats) - min(lats)) * (max(lons) - min(lons)) if lats else float("inf")

    rels.sort(key=area)
    for rel in rels:
        feat = _relation_to_feature(rel, name)
        if feat is None:
            continue
        clat, clon = centroid(feat)
        # Sanity: centroid inside (slightly padded) region bbox.
        if min_lat - 0.3 <= clat <= max_lat + 0.3 and min_lon - 0.3 <= clon <= max_lon + 0.3:
            return feat
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", help="single region slug (default: all)")
    ap.add_argument("--only-overrides", action="store_true",
                    help="resolve only LGUs in the override map via direct "
                         "relation fetch; skip the name-variant Overpass search "
                         "(futile for LGUs OSM has no admin relation for)")
    args = ap.parse_args()

    cfg = json.loads(REGIONS_JSON.read_text())
    override = json.loads(OVERRIDE_MAP.read_text())
    overrides: dict = override.get("overrides", {})

    regions = cfg["regions"]
    if args.region:
        regions = [r for r in regions if r["slug"] == args.region]

    resolved_total = 0
    for region in regions:
        slug = region["slug"]
        path = OUT_DIR / f"{slug}_lgus.geojson"
        if not path.exists():
            print(f"[missing-lgu] {slug}: no base geojson, skip", file=sys.stderr)
            continue
        fc = json.loads(path.read_text())
        have = {f["properties"]["name"] for f in fc["features"]}
        missing = [lgu for lgu in region["served_lgus"] if lgu not in have]
        if not missing:
            print(f"[missing-lgu] {slug}: all {len(have)} served LGUs have polygons")
            continue
        print(f"[missing-lgu] {slug}: {len(missing)} missing -> {missing}")
        added = 0
        for lgu in missing:
            feat = None
            key = f"{slug}:{lgu}"
            if key in overrides:
                try:
                    feat = fetch_by_relation_id_nominatim(int(overrides[key]), lgu)
                except Exception as e:
                    print(f"  [{slug}] {lgu}: override fetch error {e}", file=sys.stderr)
                time.sleep(1.1)  # Nominatim courtesy rate limit
            if feat is None and not args.only_overrides:
                time.sleep(1.2)
                try:
                    feat = fetch_by_name(lgu, tuple(region["bbox"]))
                except Exception as e:
                    print(f"  [{slug}] {lgu}: name fetch error {e}", file=sys.stderr)
            if feat is None:
                print(f"  [{slug}] {lgu}: STILL UNRESOLVED")
                continue
            feat["properties"]["region"] = slug
            feat["properties"]["franchise"] = region["franchise"]
            fc["features"].append(feat)
            overrides[key] = feat["properties"]["osm_id"]
            added += 1
            resolved_total += 1
            print(
                f"  [{slug}] {lgu}: OK osm_id={feat['properties']['osm_id']} "
                f"admin_level={feat['properties']['admin_level']}"
            )
            time.sleep(1.2)
        if added:
            path.write_text(json.dumps(fc))
            print(f"[missing-lgu] {slug}: appended {added}, now {len(fc['features'])} polygons")

    override["overrides"] = overrides
    OVERRIDE_MAP.write_text(json.dumps(override, indent=2))
    print(f"[missing-lgu] resolved {resolved_total} LGUs; override map updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
