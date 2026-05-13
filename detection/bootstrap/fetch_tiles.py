"""Fetch Esri hi-res tiles for every OSM-tagged solar location.

Inputs:  detection/bootstrap/osm_solar_ncr_plus.geojson
Outputs: detection/bootstrap/tiles/{idx:04d}.jpg  (one 600x600 tile per location)
         detection/bootstrap/tiles/index.json     (idx -> {lat, lon, osm_id, location, ...})

Filtering: by default, only fetch where location=roof (the cleanest positive set).
Pass --location=any to grab every location tag (includes surface = ground-mount + lamps).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "detection" / "bootstrap" / "osm_solar_ncr_plus.geojson"
OUT_DIR = ROOT / "detection" / "bootstrap" / "tiles"
OUT_INDEX = ROOT / "detection" / "bootstrap" / "tiles" / "index.json"

ESRI_BASE = (
    "https://services.arcgisonline.com/arcgis/rest/services/"
    "World_Imagery/MapServer/export"
)
TILE_PX = 600
HALF_DEGREE = 0.0011  # ~120m at lat 14.6, gives a ~240m view
USER_AGENT = "solar-map-ph/2.0 (osm-solar-tiles; +https://github.com/xmpuspus/solar-map-ph)"


def fetch_tile(lon: float, lat: float, out_path: Path, max_retries: int = 3) -> bool:
    if out_path.exists() and out_path.stat().st_size > 1000:
        return True
    bbox = f"{lon - HALF_DEGREE},{lat - HALF_DEGREE},{lon + HALF_DEGREE},{lat + HALF_DEGREE}"
    params = {
        "bbox": bbox,
        "bboxSR": "4326",
        "size": f"{TILE_PX},{TILE_PX}",
        "imageSR": "3857",
        "format": "jpg",
        "f": "image",
    }
    url = f"{ESRI_BASE}?{urlencode(params)}"
    for attempt in range(1, max_retries + 1):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=30) as resp:
                data = resp.read()
            if len(data) < 1000:
                raise RuntimeError(f"tiny response: {len(data)} bytes")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(data)
            return True
        except Exception as exc:
            print(f"  attempt {attempt} failed for {lon:.5f},{lat:.5f}: {exc}", file=sys.stderr)
            if attempt < max_retries:
                time.sleep(2 * attempt)
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--location", default="roof", help="OSM location tag filter (roof|surface|any)")
    ap.add_argument("--limit", type=int, default=None, help="Cap on number of tiles to fetch")
    args = ap.parse_args()

    fc = json.loads(SRC.read_text())
    feats = fc["features"]
    if args.location != "any":
        feats = [f for f in feats if f["properties"].get("location") == args.location]
    print(f"[fetch] {len(feats)} candidates after location filter '{args.location}'")
    if args.limit:
        feats = feats[: args.limit]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index = []
    rate_limit_s = 1.0 / 5  # 5 req/s
    last_t = 0.0
    n_ok = 0
    n_fail = 0
    for i, f in enumerate(feats):
        lon, lat = f["geometry"]["coordinates"]
        out_path = OUT_DIR / f"{i:04d}.jpg"
        # rate limit
        wait = rate_limit_s - (time.time() - last_t)
        if wait > 0:
            time.sleep(wait)
        last_t = time.time()
        ok = fetch_tile(lon, lat, out_path)
        if ok:
            n_ok += 1
        else:
            n_fail += 1
        index.append({
            "idx": i,
            "lat": lat,
            "lon": lon,
            "osm_type": f["properties"].get("osm_type"),
            "osm_id": f["properties"].get("osm_id"),
            "location": f["properties"].get("location"),
            "operator": f["properties"].get("operator"),
            "rating": f["properties"].get("rating"),
            "name": f["properties"].get("name"),
            "fetch_ok": ok,
        })
        if (i + 1) % 25 == 0:
            print(f"[fetch] {i+1}/{len(feats)} ok={n_ok} fail={n_fail}")

    OUT_INDEX.write_text(json.dumps(index, indent=2))
    print(f"\n[fetch] complete: ok={n_ok}/{len(feats)} fail={n_fail}")
    print(f"[fetch] index -> {OUT_INDEX}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
