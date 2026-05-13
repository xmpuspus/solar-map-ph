"""SAM-based panel-segment extraction over high-confidence v3 tiles.

For each high-confidence tile (from rooftop_solar_ncr.geojson):
  1. Run SAM AutomaticMaskGenerator (vit_b checkpoint) on the 600x600 tile
  2. For each mask, crop the bbox region from the tile + alpha-mask the rest
  3. Embed the crop with CLIP-ViT-L
  4. Score with clf_v3 LR head
  5. Keep masks with score >= THRESH (default 0.85)
  6. Convert mask pixel-bbox -> geographic bbox using the tile's lat/lon and
     HALF_DEGREE = 0.0011 (which is how ncr_scan.py defines the tile bbox)

Outputs:
  detection/scan/per_tile_segments.jsonl   (one line per tile -> list of segments)
  detection/scan/segment_thumbnails/<tile_id>/<seg_idx>.jpg  (visual debug)

Usage:
  python3 detection/scan/sam_panel_segments.py
  python3 detection/scan/sam_panel_segments.py --limit 5    # test on 5 tiles
  python3 detection/scan/sam_panel_segments.py --geojson <path>   # different input
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
TILES = ROOT / "detection" / "scan" / "ncr_tiles"
GEOJSON = ROOT / "site" / "public" / "data" / "rooftop_solar_ncr.geojson"
CLF_PATH = ROOT / "detection" / "train" / "clf_v3.joblib"
SAM_CKPT = ROOT / "detection" / "scan" / "sam_checkpoints" / "sam_vit_b_01ec64.pth"
OUT_JSONL = ROOT / "detection" / "scan" / "per_tile_segments.jsonl"
THUMBS = ROOT / "detection" / "scan" / "segment_thumbnails"

DEVICE = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
TILE_PX = 600
HALF_DEGREE = 0.0011  # matches ncr_scan.py: tile_bbox = [lon-HALF, lat-HALF, lon+HALF, lat+HALF]

SEG_KEEP_THRESH = 0.70
MIN_SEG_AREA_PX = 250  # ~16x16 px = ~6x6 m at 0.4 m/px (single panel row)
MAX_SEG_AREA_PX = 0.4 * TILE_PX * TILE_PX  # skip masks covering ~40%+ of tile

# Solar panel color signature: dark grey to dark blue, R+G+B all moderate-low
# In PH dusty conditions, panels often appear grey (close to neutral) rather than
# blue-shifted. We accept anything from grey-dark to blue-dark.
PANEL_RGB_MEAN_MAX = 140  # mean luminance must be below this (panels are dark-ish)
PANEL_RGB_MEAN_MIN = 25  # avoid pure black (shadows, holes)
PANEL_BLUE_BIAS_MIN = -25  # warmer-than-blue but still dark = OK (dusty panels)
PANEL_BLUE_BIAS_MAX = 60


def pixel_bbox_to_lonlat_bbox(
    px_bbox: tuple[int, int, int, int], tile_lat: float, tile_lon: float
) -> list[float]:
    """SAM bbox is (x, y, w, h) in pixels (x,y top-left). Convert to [min_lon, min_lat, max_lon, max_lat]."""
    x, y, w, h = px_bbox
    # Tile spans [tile_lon - HALF, tile_lon + HALF] in lon, similarly lat
    # but image y=0 is north (max lat), y=TILE_PX is south (min lat).
    lon_min = tile_lon - HALF_DEGREE + (x / TILE_PX) * (2 * HALF_DEGREE)
    lon_max = tile_lon - HALF_DEGREE + ((x + w) / TILE_PX) * (2 * HALF_DEGREE)
    lat_max = tile_lat + HALF_DEGREE - (y / TILE_PX) * (2 * HALF_DEGREE)
    lat_min = tile_lat + HALF_DEGREE - ((y + h) / TILE_PX) * (2 * HALF_DEGREE)
    return [round(lon_min, 7), round(lat_min, 7), round(lon_max, 7), round(lat_max, 7)]


def mask_to_lonlat_polygon(
    mask: np.ndarray, tile_lat: float, tile_lon: float, simplify_px: int = 4
) -> list[list[float]]:
    """Trace mask boundary, simplify, convert pixel coordinates to lon/lat.

    Returns a closed ring [[lon, lat], ...].
    """
    # Cheap polygonization: take the contour of the mask using marching squares
    # via PIL. We use a downsampled mask + bbox-corner approach if no library is available.
    try:
        from skimage import measure

        contours = measure.find_contours(mask.astype(np.uint8), 0.5)
        if not contours:
            return []
        # Largest contour by length
        biggest = max(contours, key=len)
        # skimage gives (row, col) pairs; downsample
        step = max(1, len(biggest) // 64)
        pts = biggest[::step]
        ring = []
        for r, c in pts:
            lon = tile_lon - HALF_DEGREE + (c / TILE_PX) * (2 * HALF_DEGREE)
            lat = tile_lat + HALF_DEGREE - (r / TILE_PX) * (2 * HALF_DEGREE)
            ring.append([round(lon, 7), round(lat, 7)])
        if ring and ring[0] != ring[-1]:
            ring.append(ring[0])
        return ring
    except ImportError:
        # Fallback: use the bbox as a 4-corner polygon
        ys, xs = np.where(mask)
        if len(xs) == 0:
            return []
        x_min, x_max = int(xs.min()), int(xs.max())
        y_min, y_max = int(ys.min()), int(ys.max())
        corners = [
            (x_min, y_min),
            (x_max, y_min),
            (x_max, y_max),
            (x_min, y_max),
            (x_min, y_min),
        ]
        ring = []
        for c, r in corners:
            lon = tile_lon - HALF_DEGREE + (c / TILE_PX) * (2 * HALF_DEGREE)
            lat = tile_lat + HALF_DEGREE - (r / TILE_PX) * (2 * HALF_DEGREE)
            ring.append([round(lon, 7), round(lat, 7)])
        return ring


def panel_color_score(rgb: np.ndarray, mask: np.ndarray) -> dict:
    """Compute mean RGB over the mask + simple panel-color heuristic.

    Returns {mean_rgb, brightness, blue_bias, looks_panel_like, color_score}.
    Solar panels in aerial imagery are characteristically dark with a slight
    blue-black appearance. Roof material and asphalt are warm-toned (R>B).
    """
    pixels = rgb[mask]
    if len(pixels) == 0:
        return {"looks_panel_like": False, "color_score": 0.0, "mean_rgb": [0, 0, 0]}
    mean_rgb = pixels.mean(axis=0)
    r, g, b = float(mean_rgb[0]), float(mean_rgb[1]), float(mean_rgb[2])
    brightness = (r + g + b) / 3
    blue_bias = b - r  # positive = blue, negative = red/warm
    # Hard gates
    looks_panel_like = (
        PANEL_RGB_MEAN_MIN < brightness < PANEL_RGB_MEAN_MAX
        and PANEL_BLUE_BIAS_MIN < blue_bias < PANEL_BLUE_BIAS_MAX
    )
    # Soft score: closer to "ideal panel" (brightness ~70, slight blue bias) = higher
    bright_diff = abs(brightness - 70) / 60  # 0 best, 1 = fully off
    blue_diff = abs(blue_bias - 8) / 30  # 0 best around blue_bias=8
    color_score = max(0.0, 1.0 - 0.5 * bright_diff - 0.5 * blue_diff)
    return {
        "looks_panel_like": looks_panel_like,
        "color_score": round(color_score, 3),
        "mean_rgb": [round(r, 1), round(g, 1), round(b, 1)],
        "brightness": round(brightness, 1),
        "blue_bias": round(blue_bias, 1),
    }


def crop_with_mask(
    rgb: np.ndarray,
    mask: np.ndarray,
    ctx_px: int = 192,
    out_size: int = 224,
    dim_factor: float = 0.0,
) -> Image.Image:
    """Crop a fixed-size square (ctx_px) centered on the mask, then resize to out_size.

    ctx_px=192 at 0.4m/px ~= 76m, which is about the scale of a typical commercial
    rooftop solar array (panels span 10-50m). This gives clf_v3 enough context
    to recognize "panels are visible here" without bleed from elsewhere on the tile.
    """
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return Image.fromarray(rgb)
    cy = int((ys.min() + ys.max()) / 2)
    cx = int((xs.min() + xs.max()) / 2)
    H, W = rgb.shape[:2]
    half = ctx_px // 2
    x_min = max(0, cx - half)
    x_max = min(W, cx + half)
    y_min = max(0, cy - half)
    y_max = min(H, cy + half)
    # Shift if at edge so we keep ctx_px size when possible
    if x_max - x_min < ctx_px and W >= ctx_px:
        if x_min == 0:
            x_max = ctx_px
        else:
            x_min = W - ctx_px
            x_max = W
    if y_max - y_min < ctx_px and H >= ctx_px:
        if y_min == 0:
            y_max = ctx_px
        else:
            y_min = H - ctx_px
            y_max = H
    crop = rgb[y_min:y_max, x_min:x_max].copy()
    if dim_factor > 0:
        crop_mask = mask[y_min:y_max, x_min:x_max]
        crop[~crop_mask] = (crop[~crop_mask].astype(np.float32) * dim_factor).astype(np.uint8)
    img = Image.fromarray(crop)
    return img.resize((out_size, out_size), Image.LANCZOS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="Process only first N high-confidence tiles")
    ap.add_argument(
        "--geojson", type=str, default=str(GEOJSON), help="Detections geojson (default: production)"
    )
    ap.add_argument("--clf", type=str, default=str(CLF_PATH), help="LR classifier joblib")
    ap.add_argument(
        "--thresh", type=float, default=SEG_KEEP_THRESH, help="Score threshold for keeping segments"
    )
    ap.add_argument("--save-thumbs", action="store_true", help="Save per-segment crop thumbnails for QA")
    ap.add_argument("--reset", action="store_true", help="Truncate output JSONL before running")
    ap.add_argument("--debug-scores", action="store_true", help="Print all segment scores (not just kept)")
    args = ap.parse_args()

    if not SAM_CKPT.exists():
        print(f"[seg] SAM checkpoint missing: {SAM_CKPT}", file=sys.stderr)
        return 1
    if not Path(args.clf).exists():
        print(f"[seg] classifier missing: {args.clf}", file=sys.stderr)
        return 1

    fc = json.loads(Path(args.geojson).read_text())
    high = [f for f in fc["features"] if f["properties"]["tier"] == "high"]
    high.sort(key=lambda f: -f["properties"]["score"])
    if args.limit:
        high = high[: args.limit]
    print(f"[seg] processing {len(high)} high-confidence tiles")

    # SAM
    from segment_anything import SamAutomaticMaskGenerator, sam_model_registry

    print(f"[seg] loading SAM vit_b on {DEVICE}")
    # MPS doesn't support all SAM ops; vit_b on CPU is ~3s/tile, MPS is ~1.5s/tile when supported
    sam_device = DEVICE if DEVICE != "mps" else "cpu"  # safer default; some SAM ops crash MPS
    sam = sam_model_registry["vit_b"](checkpoint=str(SAM_CKPT)).to(sam_device).eval()
    mask_gen = SamAutomaticMaskGenerator(
        sam,
        points_per_side=16,  # default 32; lower = faster, fewer masks (~2x speedup vs 24)
        pred_iou_thresh=0.85,
        stability_score_thresh=0.92,
        min_mask_region_area=MIN_SEG_AREA_PX,
    )

    # CLIP
    from transformers import CLIPModel, CLIPProcessor

    print(f"[seg] loading CLIP on {DEVICE}")
    proc = CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14", use_fast=True)
    clip = CLIPModel.from_pretrained("openai/clip-vit-large-patch14").to(DEVICE).eval()

    bundle = joblib.load(args.clf)
    clf_lr = bundle["clf"]
    print(f"[seg] loaded clf: {Path(args.clf).name}  version={bundle.get('version', '?')}")

    if args.reset and OUT_JSONL.exists():
        OUT_JSONL.unlink()
    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)

    if args.save_thumbs:
        THUMBS.mkdir(parents=True, exist_ok=True)

    # Resume support: skip tile_ids already processed
    done = set()
    if OUT_JSONL.exists():
        with OUT_JSONL.open() as f:
            for line in f:
                try:
                    done.add(json.loads(line)["tile_id"])
                except Exception:
                    continue
    if done:
        print(f"[seg] resume: skipping {len(done)} tiles already in {OUT_JSONL}")

    t0 = time.time()
    n_kept_total = 0
    n_proc = 0
    with OUT_JSONL.open("a") as fout:
        for f in high:
            tid = f["properties"]["tile_id"]
            if tid in done:
                continue
            tile_path = TILES / f"{tid}.jpg"
            if not tile_path.exists():
                continue
            tile_lat = f["geometry"]["coordinates"][1]
            tile_lon = f["geometry"]["coordinates"][0]
            tile_score = f["properties"]["score"]

            img = Image.open(tile_path).convert("RGB")
            rgb = np.asarray(img)
            try:
                masks = mask_gen.generate(rgb)
            except Exception as exc:
                print(f"[seg] SAM failed on {tid}: {exc}", file=sys.stderr)
                fout.write(json.dumps({"tile_id": tid, "error": str(exc), "segments": []}) + "\n")
                continue

            # Two-stage filter:
            #   1. Area + color signature (cheap; eliminates ~95% of masks)
            #   2. CLIP+LR score on context window (semantic check)
            # Solar panels are dark blue-black; this color gate alone removes most
            # roof/ground/wall masks before we burn CLIP cycles on them.
            kept_segments = []
            crops = []
            mask_metas = []
            color_metas = []
            n_area_skip = 0
            n_color_skip = 0
            for m in masks:
                area = m["area"]
                if area < MIN_SEG_AREA_PX or area > MAX_SEG_AREA_PX:
                    n_area_skip += 1
                    continue
                mask = m["segmentation"]
                color = panel_color_score(rgb, mask)
                if not color["looks_panel_like"]:
                    n_color_skip += 1
                    continue
                crop = crop_with_mask(rgb, mask)
                crops.append(crop)
                mask_metas.append((m, mask))
                color_metas.append(color)
            if crops:
                # Embed batch
                batch_size = 8
                scores = []
                for i in range(0, len(crops), batch_size):
                    batch = crops[i : i + batch_size]
                    inputs = proc(images=batch, return_tensors="pt").to(DEVICE)
                    with torch.no_grad():
                        emb = clip.get_image_features(**inputs)
                    emb = emb / emb.norm(dim=-1, keepdim=True)
                    s = clf_lr.predict_proba(emb.cpu().numpy().astype(np.float32))[:, 1]
                    scores.extend(s.tolist())

                if args.debug_scores:
                    s_sorted = sorted(scores, reverse=True)
                    print(
                        f"[seg]   tile_id={tid} candidates={len(crops)} (area_skip={n_area_skip} color_skip={n_color_skip}) clip_top10: {[f'{s:.3f}' for s in s_sorted[:10]]}"
                    )
                for seg_idx, ((m, mask), score, color) in enumerate(zip(mask_metas, scores, color_metas)):
                    # Combined confidence: 0.6 weight on CLIP+LR (semantic),
                    # 0.4 weight on color match (panel signature)
                    combined = 0.6 * float(score) + 0.4 * float(color["color_score"])
                    if combined < args.thresh:
                        continue
                    px_bbox = m["bbox"]
                    lonlat_bbox = pixel_bbox_to_lonlat_bbox(px_bbox, tile_lat, tile_lon)
                    polygon = mask_to_lonlat_polygon(mask, tile_lat, tile_lon)
                    seg_record = {
                        "seg_idx": seg_idx,
                        "score": round(combined, 4),
                        "clip_score": round(float(score), 4),
                        "color_score": color["color_score"],
                        "mean_rgb": color["mean_rgb"],
                        "area_px": int(m["area"]),
                        "px_bbox": [int(v) for v in px_bbox],
                        "lonlat_bbox": lonlat_bbox,
                        "polygon": polygon,
                        "stability_score": round(float(m["stability_score"]), 4),
                        "predicted_iou": round(float(m["predicted_iou"]), 4),
                    }
                    kept_segments.append(seg_record)
                    if args.save_thumbs:
                        td = THUMBS / tid
                        td.mkdir(parents=True, exist_ok=True)
                        crops[seg_idx].save(
                            td / f"seg_{seg_idx:02d}_combined{combined:.2f}_c{color['color_score']:.2f}.jpg",
                            quality=80,
                        )

            n_kept_total += len(kept_segments)
            n_proc += 1
            fout.write(
                json.dumps(
                    {
                        "tile_id": tid,
                        "tile_lat": tile_lat,
                        "tile_lon": tile_lon,
                        "tile_score": tile_score,
                        "n_masks_total": len(masks),
                        "n_segments_kept": len(kept_segments),
                        "segments": kept_segments,
                    }
                )
                + "\n"
            )
            fout.flush()
            if n_proc % 5 == 0 or n_proc == len(high):
                elapsed = time.time() - t0
                rate = n_proc / max(0.1, elapsed)
                print(
                    f"[seg] {n_proc}/{len(high)}  kept={n_kept_total}  rate={rate:.2f}/s  elapsed={elapsed:.0f}s"
                )

    print(f"[seg] DONE: {n_proc} tiles, {n_kept_total} kept segments -> {OUT_JSONL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
