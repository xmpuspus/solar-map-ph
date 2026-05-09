"""Build review sheets of every high-confidence detection from the NCR scan.

For each Feature in rooftop_solar_ncr.geojson with tier=high, look up the
matching tile JPG in ncr_tiles/ and stitch them onto a 5x5 review sheet.
Saves one sheet per page with caption (idx, lat, lon, score) per cell.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
GEOJSON = ROOT / "site" / "public" / "data" / "rooftop_solar_ncr.geojson"
TILES = ROOT / "detection" / "scan" / "ncr_tiles"
OUT = ROOT / "detection" / "scan" / "review_sheets"
OUT.mkdir(parents=True, exist_ok=True)

GRID = 5
THUMB = 256
LABEL_H = 32


def main() -> int:
    if not GEOJSON.exists():
        print("[review] no geojson yet", file=sys.stderr)
        return 1
    fc = json.loads(GEOJSON.read_text())
    feats = fc.get("features", [])
    high = [f for f in feats if f["properties"].get("tier") == "high"]
    cand = [f for f in feats if f["properties"].get("tier") == "candidate"]
    print(f"[review] {len(high)} high + {len(cand)} candidate")

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
    except OSError:
        font = ImageFont.load_default()

    cell_w, cell_h = THUMB, THUMB + LABEL_H
    sheet_w = GRID * cell_w
    sheet_h = GRID * cell_h
    page_size = GRID * GRID

    for tier_name, tier_feats in (("high", high), ("candidate", cand)):
        # Sort by score desc
        tier_feats = sorted(tier_feats, key=lambda f: -f["properties"]["score"])
        pages = (len(tier_feats) + page_size - 1) // page_size
        for page in range(pages):
            sheet = Image.new("RGB", (sheet_w, sheet_h), "white")
            draw = ImageDraw.Draw(sheet)
            page_feats = tier_feats[page * page_size:(page + 1) * page_size]
            for i, f in enumerate(page_feats):
                tid = f["properties"]["tile_id"]
                tile_path = TILES / f"{tid}.jpg"
                if not tile_path.exists():
                    continue
                row = i // GRID
                col = i % GRID
                tile = Image.open(tile_path).convert("RGB").resize((THUMB, THUMB), Image.LANCZOS)
                x = col * cell_w
                y = row * cell_h
                sheet.paste(tile, (x, y))
                lat = f["geometry"]["coordinates"][1]
                lon = f["geometry"]["coordinates"][0]
                score = f["properties"]["score"]
                label = f"s={score:.2f}  {lat:.4f},{lon:.4f}"
                draw.rectangle([x, y + THUMB, x + cell_w, y + cell_h], fill="black")
                draw.text((x + 4, y + THUMB + 6), label, fill="white", font=font)
            out_path = OUT / f"detections_{tier_name}_{page:02d}.png"
            sheet.save(out_path, optimize=True)
            print(f"[review] wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
