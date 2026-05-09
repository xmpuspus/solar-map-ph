"""Stitch fetched OSM solar tiles into review sheets for visual verification.

A 5x5 grid sheet (25 tiles per page) of 256px thumbnails with caption rows
showing the tile index. Sheets saved to detection/bootstrap/sheets/.

Usage:
    python build_review_sheets.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
TILES = ROOT / "detection" / "bootstrap" / "tiles"
INDEX = TILES / "index.json"
SHEETS = ROOT / "detection" / "bootstrap" / "sheets"

GRID = 5  # 5x5 = 25 tiles per sheet
THUMB = 256
LABEL_H = 32


def main() -> int:
    if not INDEX.exists():
        print(f"[sheets] missing {INDEX}", file=sys.stderr)
        return 1
    SHEETS.mkdir(parents=True, exist_ok=True)
    items = json.loads(INDEX.read_text())
    items = [it for it in items if it.get("fetch_ok")]
    print(f"[sheets] {len(items)} successful tiles to stitch")

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
    except OSError:
        font = ImageFont.load_default()

    cell_w = THUMB
    cell_h = THUMB + LABEL_H
    sheet_w = GRID * cell_w
    sheet_h = GRID * cell_h

    page_size = GRID * GRID
    pages = (len(items) + page_size - 1) // page_size
    for page in range(pages):
        sheet = Image.new("RGB", (sheet_w, sheet_h), "white")
        draw = ImageDraw.Draw(sheet)
        page_items = items[page * page_size:(page + 1) * page_size]
        for i, it in enumerate(page_items):
            row = i // GRID
            col = i % GRID
            tile_path = TILES / f"{it['idx']:04d}.jpg"
            if not tile_path.exists():
                continue
            tile = Image.open(tile_path).convert("RGB").resize((THUMB, THUMB), Image.LANCZOS)
            x = col * cell_w
            y = row * cell_h
            sheet.paste(tile, (x, y))
            label = f"{it['idx']:04d}  {it['lat']:.4f},{it['lon']:.4f}"
            if it.get("operator"):
                label += f"  {it['operator'][:20]}"
            draw.rectangle([x, y + THUMB, x + cell_w, y + cell_h], fill="black")
            draw.text((x + 4, y + THUMB + 6), label, fill="white", font=font)
        out = SHEETS / f"sheet_{page:02d}.png"
        sheet.save(out, optimize=True)
        print(f"[sheets] wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
