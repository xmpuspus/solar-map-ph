"""One-time fetch of city/municipality polygons for the Meralco franchise.

Pulls each city's polygon from OpenStreetMap via Nominatim and saves a single
local GeoJSON. The pipeline reads this file instead of an EE asset, because
FAO/GAUL doesn't include city-level admin units for the Philippines.

Run:
    python fetch_boundaries.py

Re-run only when franchise_cities.json changes. Output is committed to git.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

PIPELINE_DIR = Path(__file__).parent
OUT_PATH = PIPELINE_DIR / "boundaries" / "franchise_cities_polygons.geojson"
SOURCE_PATH = PIPELINE_DIR / "franchise_cities.json"

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "ghost-watts/1.0 (+https://github.com/xmpuspus/ghost-watts; xpuspus@gmail.com)"
RATE_LIMIT_S = 1.1  # Nominatim: 1 req/sec, leave headroom


def query_one(name: str, province: str) -> dict | None:
    """Fetch the best polygon match for one city/municipality.

    Tries a few query formulations because PH city naming is uneven across OSM.
    """
    queries = [
        {"city": name, "state": province, "country": "Philippines"},
        {"q": f"{name}, {province}, Philippines"},
        {"q": f"{name} City, {province}, Philippines"},
        {"q": f"{name}, Philippines"},
    ]
    for params in queries:
        params = {
            **params,
            "format": "json",
            "polygon_geojson": "1",
            "limit": "5",
            "addressdetails": "1",
        }
        try:
            resp = requests.get(
                NOMINATIM,
                params=params,
                headers={"User-Agent": USER_AGENT, "Accept-Language": "en"},
                timeout=20,
            )
            resp.raise_for_status()
            results = resp.json()
        except Exception as exc:
            print(f"  request failed for {name} via {params}: {exc}", file=sys.stderr)
            time.sleep(RATE_LIMIT_S)
            continue

        for r in results:
            if r.get("geojson", {}).get("type") not in {"Polygon", "MultiPolygon"}:
                continue
            cls = r.get("class")
            typ = r.get("type")
            if cls == "boundary" and typ == "administrative":
                time.sleep(RATE_LIMIT_S)
                return r
            if cls == "place" and typ in {"city", "town", "municipality"}:
                time.sleep(RATE_LIMIT_S)
                return r
        time.sleep(RATE_LIMIT_S)
    return None


def main() -> int:
    with SOURCE_PATH.open() as f:
        raw = json.load(f)

    cities: list[dict] = []
    for key, value in raw.items():
        if key.startswith("_"):
            continue
        if isinstance(value, list):
            cities.extend(value)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    cached: dict[str, dict] = {}
    if OUT_PATH.exists():
        with OUT_PATH.open() as f:
            existing = json.load(f)
        for feat in existing.get("features", []):
            cached[feat["properties"]["psgc_code"]] = feat

    features: list[dict] = []
    misses: list[str] = []
    for i, c in enumerate(cities, start=1):
        if c["psgc_code"] in cached:
            features.append(cached[c["psgc_code"]])
            print(f"[{i}/{len(cities)}] {c['name']}: cached")
            continue
        print(f"[{i}/{len(cities)}] {c['name']}: fetching...")
        result = query_one(c["name"], c["province"])
        if result is None:
            misses.append(c["name"])
            print(f"  miss")
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": result["geojson"],
                "properties": {
                    "name": c["name"],
                    "psgc_code": c["psgc_code"],
                    "province": c["province"],
                    "osm_id": result.get("osm_id"),
                    "osm_type": result.get("osm_type"),
                    "display_name": result.get("display_name"),
                    "boundingbox": result.get("boundingbox"),
                },
            }
        )

    fc = {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "source": "OpenStreetMap via Nominatim",
            "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "count": len(features),
            "misses": misses,
        },
    }
    with OUT_PATH.open("w") as f:
        json.dump(fc, f)
    print(f"\nWrote {len(features)} polygons to {OUT_PATH}")
    if misses:
        print(f"Missed {len(misses)} cities: {', '.join(misses)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
