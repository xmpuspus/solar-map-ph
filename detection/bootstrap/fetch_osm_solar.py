"""Bootstrap a verified solar-panel positive set by querying OpenStreetMap.

Targets Metro Manila + Bulacan + Cavite + Rizal + Laguna (the Meralco
franchise approximation) for nodes/ways tagged power=generator with
generator:source=solar OR generator:method=photovoltaic.

OSM data is community-verified — these are real solar installations
mapped by humans on the ground. Better than our case_studies.json which
was labeled by a single vision pass.

Output: detection/bootstrap/osm_solar_ncr_plus.geojson
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "detection" / "bootstrap" / "osm_solar_ncr_plus.geojson"
OUT.parent.mkdir(parents=True, exist_ok=True)

OVERPASS = "https://overpass-api.de/api/interpreter"

# Bounding box covering Meralco franchise (NCR + adjacent provinces).
# south, west, north, east
BBOX = (14.0, 120.6, 15.2, 121.5)

QUERY = f"""
[out:json][timeout:90];
(
  node["generator:source"="solar"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  way["generator:source"="solar"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  node["generator:method"="photovoltaic"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  way["generator:method"="photovoltaic"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  node["power"="generator"]["generator:source"~"solar|photovoltaic"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
);
out center tags;
"""


def fetch_overpass(query: str) -> dict:
    body = ("data=" + query).encode("utf-8")
    req = Request(OVERPASS, data=body, headers={
        "User-Agent": "ghost-watts/2.0 (osm-solar-bootstrap; +https://github.com/xmpuspus/ghost-watts)",
        "Content-Type": "application/x-www-form-urlencoded",
    })
    with urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def main() -> int:
    print(f"[osm] querying Overpass for solar generators in {BBOX}")
    t0 = time.time()
    data = fetch_overpass(QUERY)
    elements = data.get("elements", [])
    print(f"[osm] got {len(elements)} elements in {time.time()-t0:.1f}s")

    features = []
    for el in elements:
        # node has lat/lon directly; way has center lat/lon (because we asked "out center")
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None or lon is None:
            continue
        tags = el.get("tags") or {}
        feat = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "osm_type": el.get("type"),
                "osm_id": el.get("id"),
                "power": tags.get("power"),
                "generator_source": tags.get("generator:source"),
                "generator_method": tags.get("generator:method"),
                "generator_output_electricity": tags.get("generator:output:electricity"),
                "name": tags.get("name"),
                "operator": tags.get("operator"),
                "location": tags.get("location"),  # roof, ground, etc.
                "rating": tags.get("rating"),
                "all_tags": tags,
            },
        }
        features.append(feat)

    # Deduplicate by lat/lon (rounded to 5 decimals = ~1m)
    seen = set()
    unique = []
    for f in features:
        key = (round(f["geometry"]["coordinates"][0], 5), round(f["geometry"]["coordinates"][1], 5))
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)

    fc = {"type": "FeatureCollection", "features": unique, "_meta": {
        "source": "OpenStreetMap via Overpass",
        "query_bbox": BBOX,
        "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "raw_count": len(features),
        "unique_count": len(unique),
    }}
    OUT.write_text(json.dumps(fc, indent=2))
    print(f"[osm] wrote {OUT} (n={len(unique)})")

    # Summarize tag breakdown
    by_loc = {}
    by_src = {}
    for f in unique:
        p = f["properties"]
        by_loc[p.get("location") or "(none)"] = by_loc.get(p.get("location") or "(none)", 0) + 1
        by_src[p.get("generator_source") or "(none)"] = by_src.get(p.get("generator_source") or "(none)", 0) + 1
    print(f"\n[osm] location breakdown: {by_loc}")
    print(f"[osm] generator:source breakdown: {by_src}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
