"""Fetch hi-res satellite imagery for every hot-spot, then stitch into review grids.

Used to ground-truth the multi-channel solar fingerprint. For each hot-spot
point in site/public/data/hot_spots_{quarter}.geojson, fetches a 512x512
Esri World Imagery tile centered on its lat/lon (~220m view) and saves to
docs/groundtruth/tiles/{idx:03d}_{psgc}.jpg.

Then stitches all tiles into 5x5 review grids saved as
docs/groundtruth/sheets/sheet_{n:02d}.png with per-cell labels (city,
area, hotspot index) so a reviewer can label them at a glance.

Run:
    python fetch_groundtruth.py --quarter 2026Q2

Esri imagery is free for review use. Imagery vintage in PH is typically
1-3 years old, so 2025-2026 installs may not be visible. Treat the
resulting precision number as a *lower bound* on the real precision.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFont

PIPELINE_DIR = Path(__file__).parent
DOCS_DIR = PIPELINE_DIR.parent / "docs" / "groundtruth"
TILES_DIR = DOCS_DIR / "tiles"
SHEETS_DIR = DOCS_DIR / "sheets"

ESRI_BASE = "https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/export"
TILE_PX = 512
HALF_DEGREE = 0.0011  # ~120m at lat 14.6, gives a ~240m view
GRID_COLS = 5
GRID_ROWS = 5
THUMB_PX = 256  # downsized for the review grid
LABEL_HEIGHT = 36
USER_AGENT = "solar-map-ph/1.0 (groundtruth research; +https://github.com/xmpuspus/solar-map-ph)"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ground-truth tile fetcher and stitcher")
    p.add_argument("--quarter", required=True, help="Quarter, e.g. 2026Q2")
    p.add_argument("--skip-fetch", action="store_true", help="Skip tile fetch, just re-stitch sheets")
    p.add_argument("--skip-stitch", action="store_true", help="Skip stitching, just fetch tiles")
    p.add_argument("--limit", type=int, help="Process at most N hotspots (testing)")
    return p.parse_args()


def load_hotspots(quarter: str) -> list[dict]:
    path = PIPELINE_DIR.parent / "site" / "public" / "data" / f"hot_spots_{quarter}.geojson"
    with path.open() as f:
        fc = json.load(f)
    return fc.get("features", [])


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
            print(f"  attempt {attempt} failed for {lon},{lat}: {exc}", file=sys.stderr)
            if attempt < max_retries:
                time.sleep(2 * attempt)
    return False


def fetch_all(hotspots: list[dict]) -> list[dict]:
    TILES_DIR.mkdir(parents=True, exist_ok=True)
    annotated: list[dict] = []
    for i, feat in enumerate(hotspots):
        coords = feat["geometry"]["coordinates"]
        lon, lat = coords[0], coords[1]
        psgc = feat["properties"].get("psgc_code", "unknown")
        name = feat["properties"].get("city", "unknown")
        idx = f"{i:03d}"
        out = TILES_DIR / f"{idx}_{psgc}.jpg"
        ok = fetch_tile(lon, lat, out)
        annotated.append(
            {
                "idx": idx,
                "psgc_code": psgc,
                "city": name,
                "lon": lon,
                "lat": lat,
                "area_m2": feat["properties"].get("area_m2"),
                "kwp_equiv": feat["properties"].get("kwp_equiv"),
                "tile_path": str(out.relative_to(PIPELINE_DIR.parent)),
                "fetched": ok,
            }
        )
        print(f"[{i + 1}/{len(hotspots)}] {name} ({psgc}): {'ok' if ok else 'FAILED'}")
        time.sleep(0.6)  # respectful pacing
    index_path = DOCS_DIR / "index.json"
    with index_path.open("w") as f:
        json.dump({"hotspots": annotated}, f, indent=2)
    print(f"\nWrote {len(annotated)} tile entries to {index_path}")
    return annotated


def get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def make_sheet(batch: list[dict], sheet_idx: int) -> Path:
    SHEETS_DIR.mkdir(parents=True, exist_ok=True)
    cell_w = THUMB_PX
    cell_h = THUMB_PX + LABEL_HEIGHT
    sheet_w = GRID_COLS * cell_w + (GRID_COLS + 1) * 4
    sheet_h = GRID_ROWS * cell_h + (GRID_ROWS + 1) * 4 + 60  # header strip
    sheet = Image.new("RGB", (sheet_w, sheet_h), (240, 238, 232))
    draw = ImageDraw.Draw(sheet)
    title_font = get_font(20)
    cell_font = get_font(11)
    cell_font_bold = get_font(12)
    idx_font = get_font(36)

    title = f"Sheet {sheet_idx + 1} · cells {batch[0]['idx']} to {batch[-1]['idx']}"
    draw.text((12, 14), title, fill=(11, 18, 32), font=title_font)
    draw.text(
        (12, 38),
        "label each: SOLAR if you see panel rectangles · NOT if no panels visible · UNCLEAR if cloudy/old imagery",
        fill=(68, 81, 112),
        font=cell_font,
    )

    for n, item in enumerate(batch):
        row = n // GRID_COLS
        col = n % GRID_COLS
        x = 4 + col * (cell_w + 4)
        y = 60 + 4 + row * (cell_h + 4)
        # frame
        draw.rectangle([x - 1, y - 1, x + cell_w, y + cell_h], outline=(142, 152, 172))
        # tile
        tile_path = PIPELINE_DIR.parent / item["tile_path"]
        if tile_path.exists():
            try:
                tile = Image.open(tile_path).convert("RGB").resize((cell_w, THUMB_PX))
                sheet.paste(tile, (x, y))
            except Exception as exc:
                draw.text((x + 8, y + 8), f"err: {exc}", fill=(180, 50, 50), font=cell_font)
        else:
            draw.text((x + 8, y + 8), "missing tile", fill=(180, 50, 50), font=cell_font)

        # idx overlay (top-left of tile, big and bold)
        idx_text = f"#{item['idx']}"
        # white halo
        for ox, oy in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            draw.text((x + 8 + ox, y + 6 + oy), idx_text, fill=(255, 255, 255), font=idx_font)
        draw.text((x + 8, y + 6), idx_text, fill=(11, 18, 32), font=idx_font)

        # label strip
        label_y = y + THUMB_PX + 2
        area_ha = (item.get("area_m2") or 0) / 10000
        kwp = item.get("kwp_equiv") or 0
        draw.text(
            (x + 6, label_y),
            f"{item['city']}",
            fill=(11, 18, 32),
            font=cell_font_bold,
        )
        draw.text(
            (x + 6, label_y + 16),
            f"{area_ha:.1f} ha · {kwp:.0f} kWp eq",
            fill=(68, 81, 112),
            font=cell_font,
        )

    out_path = SHEETS_DIR / f"sheet_{sheet_idx:02d}.png"
    sheet.save(out_path, "PNG", optimize=True)
    return out_path


def stitch(annotated: list[dict]) -> list[Path]:
    per_sheet = GRID_COLS * GRID_ROWS
    sheets: list[Path] = []
    for sheet_idx, start in enumerate(range(0, len(annotated), per_sheet)):
        batch = annotated[start : start + per_sheet]
        path = make_sheet(batch, sheet_idx)
        sheets.append(path)
        print(f"Stitched {path.name} ({len(batch)} cells)")
    return sheets


def main() -> int:
    args = parse_args()
    hotspots = load_hotspots(args.quarter)
    if args.limit:
        hotspots = hotspots[: args.limit]
    print(f"Total hotspots to ground-truth: {len(hotspots)}")

    annotated: list[dict]
    index_path = DOCS_DIR / "index.json"
    if args.skip_fetch:
        if not index_path.exists():
            raise SystemExit(f"--skip-fetch but {index_path} doesn't exist; run without --skip-fetch first")
        with index_path.open() as f:
            annotated = json.load(f)["hotspots"]
        print(f"Loaded {len(annotated)} existing tile entries")
    else:
        annotated = fetch_all(hotspots)

    if not args.skip_stitch:
        stitch(annotated)

    return 0


if __name__ == "__main__":
    sys.exit(main())
