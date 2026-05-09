"""Build 3x3 verification sheets for high-confidence detections.

For each Feature in rooftop_solar_ncr.geojson with tier=high, render a 3x3
grid of larger thumbnails labeled with idx, score, lat, lon. Output sheets
to detection/verify/sheets/ and a JSON tag template to detection/verify/tags.json
that the user fills in.

Tag schema:
  {
    "tile_id": "14.62572_121.12048",
    "idx": 0,
    "score": 0.986,
    "lat": 14.62572,
    "lon": 121.12048,
    "label": null         <-- "true" | "false" | "ambiguous"
  }

Usage:
  python3 detection/verify/build_verification_sheets.py
  open detection/verify/sheets/page_00.png   # tag in JSON
  ...
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
GEOJSON = ROOT / "site" / "public" / "data" / "rooftop_solar_ncr.geojson"
TILES = ROOT / "detection" / "scan" / "ncr_tiles"
MATCH = ROOT / "detection" / "scan" / "match_report.json"
OUT_DIR = ROOT / "detection" / "verify" / "sheets"
OUT_DIR.mkdir(parents=True, exist_ok=True)
TAGS_PATH = ROOT / "detection" / "verify" / "tags.json"

GRID = 3
THUMB = 480  # bigger than the 5x5 sheet so panels are easier to see
LABEL_H = 64


def main() -> int:
    if not GEOJSON.exists():
        print("[verify] no geojson yet", file=sys.stderr)
        return 1
    fc = json.loads(GEOJSON.read_text())
    feats = fc.get("features", [])
    high = [f for f in feats if f["properties"].get("tier") == "high"]
    high.sort(key=lambda f: -f["properties"]["score"])
    print(f"[verify] {len(high)} high-confidence detections")

    # OSM-distance hint per tile (helps user tag faster: very-close = likely true)
    osm_hint: dict[str, dict] = {}
    if MATCH.exists():
        for r in json.loads(MATCH.read_text()).get("rows", []):
            key = f"{r['lat']:.5f}_{r['lon']:.5f}"
            osm_hint[key] = {
                "osm_m": r.get("nearest_osm_m"),
                "osm_loc": r.get("nearest_osm_location"),
                "status": r.get("status"),
            }

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
        font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
    except OSError:
        font = ImageFont.load_default()
        font_small = ImageFont.load_default()

    cell_w = THUMB
    cell_h = THUMB + LABEL_H
    sheet_w = GRID * cell_w
    sheet_h = GRID * cell_h
    page_size = GRID * GRID

    # Build tag template, preserving any existing labels (don't blow away progress)
    existing: dict[str, str | None] = {}
    if TAGS_PATH.exists():
        try:
            for r in json.loads(TAGS_PATH.read_text()):
                existing[r["tile_id"]] = r.get("label")
        except Exception:
            pass

    tag_rows = []
    pages = (len(high) + page_size - 1) // page_size
    for page in range(pages):
        sheet = Image.new("RGB", (sheet_w, sheet_h), "white")
        draw = ImageDraw.Draw(sheet)
        page_feats = high[page * page_size:(page + 1) * page_size]
        for i, f in enumerate(page_feats):
            tid = f["properties"]["tile_id"]
            tile_path = TILES / f"{tid}.jpg"
            row = i // GRID
            col = i % GRID
            x = col * cell_w
            y = row * cell_h
            if tile_path.exists():
                tile = Image.open(tile_path).convert("RGB").resize((THUMB, THUMB), Image.LANCZOS)
                sheet.paste(tile, (x, y))
            else:
                draw.rectangle([x, y, x + THUMB, y + THUMB], fill="lightgray")
                draw.text((x + 8, y + 8), "missing tile", fill="black", font=font)

            global_idx = page * page_size + i
            lat = f["geometry"]["coordinates"][1]
            lon = f["geometry"]["coordinates"][0]
            score = f["properties"]["score"]
            hint_key = f"{lat:.5f}_{lon:.5f}"
            hint = osm_hint.get(hint_key, {})
            osm_m = hint.get("osm_m")
            status = hint.get("status", "")
            hint_str = ""
            if osm_m is not None:
                if osm_m < 100:
                    hint_str = f"OSM<{int(osm_m)}m (likely TRUE)"
                elif osm_m < 200:
                    hint_str = f"OSM={int(osm_m)}m (adjacent)"
                else:
                    hint_str = f"OSM={int(osm_m)}m (NEW)"
            # Black label band with idx + score + coords + OSM hint
            draw.rectangle([x, y + THUMB, x + cell_w, y + cell_h], fill="black")
            line1 = f"#{global_idx:03d}  s={score:.3f}  {hint_str}"
            line2 = f"{lat:.5f},{lon:.5f}  page{page:02d}-cell{i}"
            draw.text((x + 8, y + THUMB + 6), line1, fill="white", font=font)
            draw.text((x + 8, y + THUMB + 36), line2, fill="white", font=font_small)

            tag_rows.append({
                "tile_id": tid,
                "idx": global_idx,
                "page": page,
                "cell": i,
                "score": score,
                "lat": lat,
                "lon": lon,
                "osm_nearest_m": osm_m,
                "osm_status": status,
                "label": existing.get(tid),
            })
        out_path = OUT_DIR / f"page_{page:02d}.png"
        sheet.save(out_path, optimize=True)
        print(f"[verify] wrote {out_path}")

    TAGS_PATH.write_text(json.dumps(tag_rows, indent=2))
    print(f"[verify] tag template -> {TAGS_PATH}  ({len(tag_rows)} rows)")
    print(f"[verify] sheets in   -> {OUT_DIR}")
    print()
    print("Next: open each page_*.png and edit tags.json setting label to one of:")
    print('  "true"      -> a real rooftop solar in this tile')
    print('  "false"     -> false positive, no solar visible')
    print('  "ambiguous" -> can\'t tell from imagery (will be excluded from training)')
    return 0


if __name__ == "__main__":
    sys.exit(main())
