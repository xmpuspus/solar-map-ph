"""Build a 3x3 verification sheet of just the tiles that v3 promoted to high
that v2 had below the 0.85 threshold.

These are the highest-leverage tiles to verify in a second active-learning round:
the cleanup pass put them above the threshold, and the user's tag will either
confirm the upgrade or flag a mis-promotion.

Output: detection/verify/v3_new_sheets/page_*.png + v3_new_tags.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
TILES = ROOT / "detection" / "scan" / "ncr_tiles"
V2_JSONL = ROOT / "detection" / "scan" / "ncr_scan_results.jsonl"
V3_JSONL = ROOT / "detection" / "scan" / "ncr_scan_results_v3.jsonl"
OUT_DIR = ROOT / "detection" / "verify" / "v3_new_sheets"
TAGS_PATH = ROOT / "detection" / "verify" / "v3_new_tags.json"

GRID = 3
THUMB = 480
LABEL_H = 64


def load_scores(jsonl: Path) -> dict[str, dict]:
    out = {}
    with jsonl.open() as f:
        for line in f:
            try:
                r = json.loads(line)
                if r.get("fetch_ok") and r.get("score") is not None:
                    out[r["tile_id"]] = r
            except Exception:
                continue
    return out


def main() -> int:
    if not V3_JSONL.exists() or not V2_JSONL.exists():
        print("[v3-new] need both v2 and v3 jsonl files", file=sys.stderr)
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    v2 = load_scores(V2_JSONL)
    v3 = load_scores(V3_JSONL)

    new_in_v3 = []
    for tid, r3 in v3.items():
        s3 = r3["score"]
        if s3 < 0.85:
            continue
        s2 = v2.get(tid, {}).get("score", 0)
        if s2 >= 0.85:
            continue
        new_in_v3.append(
            {
                "tile_id": tid,
                "lat": r3["lat"],
                "lon": r3["lon"],
                "v2_score": round(s2, 3),
                "v3_score": round(s3, 3),
            }
        )
    new_in_v3.sort(key=lambda r: -r["v3_score"])
    print(f"[v3-new] {len(new_in_v3)} tiles newly promoted to high in v3")

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

    # Carry over any existing labels
    existing: dict[str, str | None] = {}
    if TAGS_PATH.exists():
        for r in json.loads(TAGS_PATH.read_text()):
            existing[r["tile_id"]] = r.get("label")

    tag_rows = []
    pages = (len(new_in_v3) + page_size - 1) // page_size
    for page in range(pages):
        sheet = Image.new("RGB", (sheet_w, sheet_h), "white")
        draw = ImageDraw.Draw(sheet)
        page_feats = new_in_v3[page * page_size : (page + 1) * page_size]
        for i, f in enumerate(page_feats):
            tid = f["tile_id"]
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
            draw.rectangle([x, y + THUMB, x + cell_w, y + cell_h], fill="black")
            line1 = f"#{global_idx:02d}  v3={f['v3_score']:.3f}  v2={f['v2_score']:.3f}  Δ={f['v3_score'] - f['v2_score']:+.3f}"
            line2 = f"{f['lat']:.5f},{f['lon']:.5f}  page{page:02d}-cell{i}"
            draw.text((x + 8, y + THUMB + 6), line1, fill="white", font=font)
            draw.text((x + 8, y + THUMB + 36), line2, fill="white", font=font_small)

            tag_rows.append(
                {
                    "tile_id": tid,
                    "idx": global_idx,
                    "page": page,
                    "cell": i,
                    "v2_score": f["v2_score"],
                    "v3_score": f["v3_score"],
                    "lat": f["lat"],
                    "lon": f["lon"],
                    "label": existing.get(tid),
                }
            )
        out_path = OUT_DIR / f"page_{page:02d}.png"
        sheet.save(out_path, optimize=True)
        print(f"[v3-new] wrote {out_path}")

    TAGS_PATH.write_text(json.dumps(tag_rows, indent=2))
    print(f"[v3-new] tag template -> {TAGS_PATH} ({len(tag_rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
