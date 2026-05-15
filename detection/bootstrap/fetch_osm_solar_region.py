"""Step 2b of v1.2: bootstrap community-verified solar positives per v1.1
region by querying OpenStreetMap via Overpass.

Generalizes fetch_osm_solar.py (NCR-only) to every region in
pipeline/regions/regions.json. For each region's bbox, fetch nodes/ways tagged
generator:source=solar or generator:method=photovoltaic. These are
human-mapped real installations: positives for the step-3 per-region holdouts
and for region-stratified clf_v5 training, and the reference set for the
step-5 region-aware OSM cross-match.

regions.json bbox is [min_lat, min_lon, max_lat, max_lon] which is exactly
Overpass's (south, west, north, east) order.

Output: detection/bootstrap/osm_solar_<slug>.geojson per region.

Run:
    python detection/bootstrap/fetch_osm_solar_region.py            # all regions
    python detection/bootstrap/fetch_osm_solar_region.py --region cebu
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
REGIONS_JSON = ROOT / "pipeline" / "regions" / "regions.json"
OUT_DIR = ROOT / "detection" / "bootstrap"
OVERPASS = "https://overpass-api.de/api/interpreter"
USER_AGENT = "solar-map-ph/1.2 (osm-region-bootstrap; +https://github.com/xmpuspus/solar-map-ph)"


def build_query(bbox: tuple[float, float, float, float]) -> str:
    s, w, n, e = bbox
    return f"""
[out:json][timeout:120];
(
  node["generator:source"="solar"]({s},{w},{n},{e});
  way["generator:source"="solar"]({s},{w},{n},{e});
  node["generator:method"="photovoltaic"]({s},{w},{n},{e});
  way["generator:method"="photovoltaic"]({s},{w},{n},{e});
  node["power"="generator"]["generator:source"~"solar|photovoltaic"]({s},{w},{n},{e});
  way["power"="plant"]["plant:source"="solar"]({s},{w},{n},{e});
);
out center tags;
"""


def fetch_overpass(query: str, retries: int = 3) -> dict:
    body = ("data=" + query).encode("utf-8")
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = Request(
                OVERPASS,
                data=body,
                headers={
                    "User-Agent": USER_AGENT,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            with urlopen(req, timeout=180) as resp:
                return json.loads(resp.read())
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(20 * attempt)
    raise RuntimeError(f"Overpass failed after {retries} attempts: {last_err}")


def to_features(elements: list[dict]) -> list[dict]:
    features = []
    for el in elements:
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None or lon is None:
            continue
        tags = el.get("tags") or {}
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "osm_type": el.get("type"),
                    "osm_id": el.get("id"),
                    "power": tags.get("power"),
                    "generator_source": tags.get("generator:source"),
                    "generator_method": tags.get("generator:method"),
                    "name": tags.get("name"),
                    "operator": tags.get("operator"),
                    "location": tags.get("location"),  # roof / ground / etc.
                    "all_tags": tags,
                },
            }
        )
    # Dedup at ~1 m.
    seen = set()
    unique = []
    for f in features:
        key = (round(f["geometry"]["coordinates"][0], 5), round(f["geometry"]["coordinates"][1], 5))
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    return unique


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", help="single region slug (default: all)")
    args = ap.parse_args()

    cfg = json.loads(REGIONS_JSON.read_text())
    regions = cfg["regions"]
    if args.region:
        regions = [r for r in regions if r["slug"] == args.region]
        if not regions:
            print(f"[osm-region] no such region: {args.region}", file=sys.stderr)
            return 1

    summary = {}
    for r in regions:
        slug = r["slug"]
        bbox = tuple(r["bbox"])  # (s, w, n, e)
        out = OUT_DIR / f"osm_solar_{slug}.geojson"
        print(f"[osm-region] {slug} bbox={bbox}")
        try:
            data = fetch_overpass(build_query(bbox))
        except RuntimeError as e:
            print(f"[osm-region] {slug}: FAILED {e}", file=sys.stderr)
            summary[slug] = "FAILED"
            continue
        feats = to_features(data.get("elements", []))
        by_loc: dict[str, int] = {}
        for f in feats:
            loc = f["properties"].get("location") or "(unspecified)"
            by_loc[loc] = by_loc.get(loc, 0) + 1
        fc = {
            "type": "FeatureCollection",
            "features": feats,
            "_meta": {
                "source": "OpenStreetMap via Overpass",
                "region": slug,
                "query_bbox": list(bbox),
                "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "unique_count": len(feats),
                "location_breakdown": by_loc,
            },
        }
        out.write_text(json.dumps(fc, indent=2))
        print(f"[osm-region] {slug}: {len(feats)} solar tags  loc={by_loc}  -> {out.name}")
        summary[slug] = len(feats)
        time.sleep(8)  # be polite to the public Overpass instance

    print(f"\n[osm-region] summary: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
