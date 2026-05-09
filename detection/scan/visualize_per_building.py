"""Visualize per-building panel polygons drawn on top of their source tiles.

For each building in per_building_solar_ncr.geojson, find the source tile
(properties.tile_id), draw the panel polygon as an orange overlay, and save
to detection/scan/per_building_thumbs/<osm_id>_<kwp>kwp.jpg.

Useful for QA: scan the directory by file size, look for misaligned polygons.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
TILES = ROOT / "detection" / "scan" / "ncr_tiles"
GEOJSON = ROOT / "site" / "public" / "data" / "per_building_solar_ncr.geojson"
OUT_DIR = ROOT / "detection" / "scan" / "per_building_thumbs"

TILE_PX = 600
HALF_DEGREE = 0.0011


def lonlat_to_pixel(lon: float, lat: float, tile_lat: float, tile_lon: float) -> tuple[int, int]:
    px_x = (lon - (tile_lon - HALF_DEGREE)) / (2 * HALF_DEGREE) * TILE_PX
    px_y = ((tile_lat + HALF_DEGREE) - lat) / (2 * HALF_DEGREE) * TILE_PX
    return int(px_x), int(px_y)


def main() -> int:
    if not GEOJSON.exists():
        print(f"[viz] missing geojson: {GEOJSON}", file=sys.stderr)
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fc = json.loads(GEOJSON.read_text())
    print(f"[viz] {len(fc['features'])} buildings")

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
    except OSError:
        font = ImageFont.load_default()

    n_ok = 0
    n_skip = 0
    for f in fc["features"]:
        p = f["properties"]
        tile_id = p.get("tile_id")
        if not tile_id:
            n_skip += 1
            continue
        tile_path = TILES / f"{tile_id}.jpg"
        if not tile_path.exists():
            n_skip += 1
            continue
        # Reconstruct tile center from tile_id (lat_lon)
        try:
            tile_lat = float(tile_id.split("_")[0])
            tile_lon = float(tile_id.split("_")[1])
        except Exception:
            n_skip += 1
            continue

        img = Image.open(tile_path).convert("RGB")
        draw = ImageDraw.Draw(img, "RGBA")

        # Project polygon to pixel
        polygon = f["geometry"]["coordinates"][0]
        px_pts = [lonlat_to_pixel(pt[0], pt[1], tile_lat, tile_lon) for pt in polygon]
        # Fill + outline
        draw.polygon(px_pts, fill=(217, 119, 87, 80), outline=(217, 119, 87, 255))

        # Caption
        kwp = p.get("kwp_estimate", 0)
        conf = p.get("confidence", 0)
        n_segs = p.get("n_segments_merged", 1)
        b_type = p.get("building_type") or "untagged"
        label = f"#{p['building_osm_id']} {b_type} {kwp:.1f}kWp conf={conf:.2f} segs={n_segs}"
        draw.rectangle([0, 0, TILE_PX, 24], fill=(0, 0, 0, 200))
        draw.text((6, 4), label, fill="white", font=font)

        out_path = OUT_DIR / f"{p['building_osm_id']}_{int(kwp):04d}kwp.jpg"
        img.save(out_path, quality=85)
        n_ok += 1

    print(f"[viz] wrote {n_ok} thumbs to {OUT_DIR} ({n_skip} skipped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
