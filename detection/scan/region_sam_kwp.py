"""Step 7 of v1.2: per-detection SAM panel-area + kWp estimate for the v1.1
cross-domain regions.

Privacy boundary (unchanged): the published region GeoJSON stays point-tile
only. SAM is used to estimate panel area WITHIN a detection tile; the result
is written back as the scalar properties `panel_area_m2` and `kwp_estimate`
on the EXISTING Point feature. No building polygons, no PII keys are added,
so scripts/check_region_no_pii.py still passes.

Method per detection tile (high + candidate):
  1. SAM AutomaticMaskGenerator (vit_b) on the cached 400 px region tile
  2. two-stage panel verification (the proven NCR sam_panel_segments filter):
     stage 1 = area band + panel_color_score gate; stage 2 = CLIP crop +
     clf_v5 score, keep if combined 0.6*clip+0.4*color >= 0.70. Without the
     semantic check SAM counts whole dark/blue roofs as panels and kWp blows
     up (the v1.2 first-pass bug, since fixed).
  3. panel_area_px = sum of VERIFIED-mask pixel areas
  4. m_per_px from the tile's geographic width at its latitude
     (width_m = 2*HALF_DEGREE*111320*cos(lat); m_per_px = width_m/TILE_PX)
  5. panel_area_m2 = panel_area_px * m_per_px^2
  6. kwp_estimate = panel_area_m2 * KWP_PER_M2

KWP_PER_M2 = 0.15 kWp/m^2 (~6.7 m^2/kWp): a deliberately conservative
crystalline-Si rooftop figure. A civic tool should under- not over-state
installed capacity. Documented in MODEL_CARD / methodology.

Resumable: a per-region sidecar detection/scan/sam_kwp_<region>.jsonl records
processed tile_ids (tile_id + areas + score only; no PII).

Run:
    python detection/scan/region_sam_kwp.py            # all regions
    python detection/scan/region_sam_kwp.py --region cebu --limit 5
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
REGIONS_JSON = ROOT / "pipeline" / "regions" / "regions.json"
DATA_DIR = ROOT / "site" / "public" / "data"
TILES_DIR = ROOT / "detection" / "scan" / "tiles"
SAM_CKPT = ROOT / "detection" / "scan" / "sam_checkpoints" / "sam_vit_b_01ec64.pth"
SCAN_DIR = ROOT / "detection" / "scan"

DEVICE = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
TILE_PX = 400  # region scans use 400 px (esri-throttle-tilepx memory)
HALF_DEGREE = 0.0011
M_PER_DEG = 111_320.0

MIN_SEG_AREA_PX = 250
# A single SAM mask covering >18% of a 240 m tile is almost always a whole
# roof, not a panel sub-array (real arrays segment into many smaller masks).
# v1.2 fix: the earlier 0.45 cap let entire dark/blue roofs through, which is
# why the first pass produced physically implausible MWp totals.
MAX_SEG_AREA_PX = 0.18 * TILE_PX * TILE_PX
KWP_PER_M2 = 0.15  # conservative crystalline-Si rooftop density
SEG_KEEP_THRESH = 0.70  # combined 0.6*clip+0.4*color, matches NCR pipeline


def m_per_px(lat: float) -> float:
    width_m = 2 * HALF_DEGREE * M_PER_DEG * math.cos(math.radians(lat))
    return width_m / TILE_PX


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", help="single region slug (default: all)")
    ap.add_argument("--limit", type=int, help="cap detections per region (testing)")
    args = ap.parse_args()

    if not SAM_CKPT.exists():
        print(f"[sam-kwp] missing SAM checkpoint {SAM_CKPT} (run: make sam)", file=sys.stderr)
        return 1

    cfg = json.loads(REGIONS_JSON.read_text())
    slugs = [r["slug"] for r in cfg["regions"]]
    if args.region:
        slugs = [s for s in slugs if s == args.region]

    import joblib
    from sam_panel_segments import crop_with_mask, panel_color_score
    from segment_anything import SamAutomaticMaskGenerator, sam_model_registry
    from transformers import CLIPModel, CLIPProcessor

    sam_device = "cpu" if DEVICE == "mps" else DEVICE  # some SAM ops crash MPS
    print(f"[sam-kwp] loading SAM vit_b on {sam_device}")
    sam = sam_model_registry["vit_b"](checkpoint=str(SAM_CKPT)).to(sam_device).eval()
    mask_gen = SamAutomaticMaskGenerator(
        sam,
        points_per_side=16,
        pred_iou_thresh=0.85,
        stability_score_thresh=0.92,
        min_mask_region_area=MIN_SEG_AREA_PX,
    )
    # Per-mask verification: a candidate mask only counts toward panel area if
    # it passes the color gate AND CLIP+clf_v5 confirm it is a panel array.
    # Without this, SAM segments whole dark/blue roofs as one mask and the
    # kWp blows up (the v1.2 first-pass bug).
    clip_proc = CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14", use_fast=True)
    clip = CLIPModel.from_pretrained("openai/clip-vit-large-patch14").to(DEVICE).eval()
    clf_lr = joblib.load(ROOT / "detection" / "train" / "clf_v5.joblib")["clf"]

    for slug in slugs:
        gj_path = DATA_DIR / f"rooftop_solar_{slug}.geojson"
        if not gj_path.exists():
            print(f"[sam-kwp] {slug}: no GeoJSON, skip", file=sys.stderr)
            continue
        gj = json.loads(gj_path.read_text())
        feats = gj.get("features", [])
        if args.limit:
            feats = sorted(feats, key=lambda f: -f["properties"]["score"])[: args.limit]

        sidecar = SCAN_DIR / f"sam_kwp_{slug}.jsonl"
        done = {}
        if sidecar.exists():
            for line in sidecar.read_text().splitlines():
                try:
                    r = json.loads(line)
                    done[r["tile_id"]] = r
                except Exception:
                    continue

        t0 = time.time()
        n_proc = 0
        with sidecar.open("a") as fout:
            for f in feats:
                tid = f["properties"]["tile_id"]
                lat = f["geometry"]["coordinates"][1]
                if tid in done:
                    rec = done[tid]
                else:
                    tile_path = TILES_DIR / slug / f"{tid}.jpg"
                    if not tile_path.exists() or tile_path.stat().st_size <= 1000:
                        continue
                    rgb = np.asarray(Image.open(tile_path).convert("RGB"))
                    try:
                        masks = mask_gen.generate(rgb)
                    except Exception as exc:
                        print(f"[sam-kwp] {slug} {tid}: SAM error {exc}", file=sys.stderr)
                        masks = []
                    # Stage 1: cheap area + panel-color gate.
                    cand = []
                    for m in masks:
                        a = m["area"]
                        if a < MIN_SEG_AREA_PX or a > MAX_SEG_AREA_PX:
                            continue
                        col = panel_color_score(rgb, m["segmentation"])
                        if col["looks_panel_like"]:
                            cand.append((m, col))
                    # Stage 2: CLIP + clf_v5 semantic check on the mask crop.
                    panel_px = 0
                    if cand:
                        crops = [crop_with_mask(rgb, m["segmentation"]) for m, _ in cand]
                        scores = []
                        for i in range(0, len(crops), 8):
                            inp = clip_proc(images=crops[i:i + 8], return_tensors="pt").to(DEVICE)
                            with torch.no_grad():
                                emb = clip.get_image_features(**inp)
                            emb = emb / emb.norm(dim=-1, keepdim=True)
                            scores.extend(
                                clf_lr.predict_proba(emb.cpu().numpy().astype(np.float32))[:, 1].tolist()
                            )
                        for (m, col), sc in zip(cand, scores):
                            combined = 0.6 * float(sc) + 0.4 * float(col["color_score"])
                            if combined >= SEG_KEEP_THRESH:
                                panel_px += int(m["area"])
                    mpp = m_per_px(lat)
                    area_m2 = round(panel_px * mpp * mpp, 1)
                    kwp = round(area_m2 * KWP_PER_M2, 1)
                    rec = {"tile_id": tid, "panel_area_m2": area_m2,
                           "kwp_estimate": kwp, "score": f["properties"]["score"]}
                    fout.write(json.dumps(rec) + "\n")
                    fout.flush()
                    n_proc += 1
                f["properties"]["panel_area_m2"] = rec["panel_area_m2"]
                f["properties"]["kwp_estimate"] = rec["kwp_estimate"]

        total_kwp = round(sum(
            (f["properties"].get("kwp_estimate") or 0.0) for f in gj["features"]
        ), 1)
        gj.setdefault("_meta", {})["sam_kwp"] = {
            "kwp_per_m2": KWP_PER_M2,
            "method": "SAM vit_b panel-mask area within detection tile; conservative",
            "total_kwp_estimate": total_kwp,
            "tile_px": TILE_PX,
        }
        gj_path.write_text(json.dumps(gj))
        print(f"[sam-kwp] {slug}: processed {n_proc} new / {len(gj['features'])} feats "
              f"total~{total_kwp} kWp  {(time.time() - t0) / 60:.1f}min")

    return 0


if __name__ == "__main__":
    sys.exit(main())
