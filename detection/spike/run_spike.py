"""Spike: run a pretrained solar-panel segmenter against the 6 PH case studies
and a sample of negative ground-truth tiles.

Decision criterion:
  - Catches all 6 case studies (recall on positives) -> use as-is
  - Catches 4-5 / 6 -> calibrate threshold + light fine-tune
  - Catches <=3 -> domain shift, fine-tune from PH labels

The case studies are 600x600 ~0.4 m/pixel Esri tiles, 240m view across.
Ground-truth tiles are 512x512 ~0.5 m/pixel Esri tiles, also ~240m view.

Models tried, in order:
  1. abdulsalama/SV-solar-mask2-swin-large-ade-200-deepsolar-2023060311
  2. abdulsalama/solar-mask2-swin-small-ade-200-deepsolar-2023060210
  3. finloop/yolov8s-seg-solar-panels (fallback)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
CASE_STUDIES = ROOT / "site" / "public" / "case_studies"
GROUNDTRUTH_TILES = ROOT / "docs" / "groundtruth" / "tiles"
LABELS = ROOT / "docs" / "groundtruth" / "labels.json"
SPIKE_OUT = ROOT / "detection" / "spike" / "out"
SPIKE_OUT.mkdir(parents=True, exist_ok=True)

DEVICE = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
print(f"[spike] device={DEVICE}")


def load_case_studies() -> list[tuple[str, Path]]:
    """Return [(case_id, path), ...] for the 6 hand-verified positives."""
    out = []
    for p in sorted(CASE_STUDIES.glob("*.jpg")):
        out.append((p.stem, p))
    return out


def load_groundtruth_negatives(n: int = 30) -> list[tuple[str, Path]]:
    """Return [(label_idx, path), ...] for the first n labeled not_solar tiles."""
    with LABELS.open() as f:
        data = json.load(f)
    negatives = []
    for item in data["labels"]:
        if item.get("label") == "not_solar":
            tiles = list(GROUNDTRUTH_TILES.glob(f"{item['idx']}_*.jpg"))
            if tiles:
                negatives.append((item["idx"], tiles[0]))
            if len(negatives) >= n:
                break
    return negatives


def load_groundtruth_positives() -> list[tuple[str, Path]]:
    """Return [(label_idx, path), ...] for the 6 labeled solar tiles."""
    with LABELS.open() as f:
        data = json.load(f)
    out = []
    for item in data["labels"]:
        if item.get("label") == "solar":
            tiles = list(GROUNDTRUTH_TILES.glob(f"{item['idx']}_*.jpg"))
            if tiles:
                out.append((item["idx"], tiles[0]))
    return out


def try_mask2former_swin_large() -> Any:
    """Attempt to load the DeepSolar-trained Mask2Former-Swin-Large model."""
    from transformers import (
        AutoImageProcessor,
        Mask2FormerForUniversalSegmentation,
    )

    model_id = "abdulsalama/SV-solar-mask2-swin-large-ade-200-deepsolar-2023060311"
    print(f"[spike] loading {model_id}")
    processor = AutoImageProcessor.from_pretrained(model_id, use_fast=True)
    model = Mask2FormerForUniversalSegmentation.from_pretrained(model_id).to(DEVICE).eval()
    return ("mask2former-swin-large", processor, model)


def try_mask2former_swin_small() -> Any:
    from transformers import (
        AutoImageProcessor,
        Mask2FormerForUniversalSegmentation,
    )

    model_id = "abdulsalama/solar-mask2-swin-small-ade-200-deepsolar-2023060210"
    print(f"[spike] loading {model_id}")
    processor = AutoImageProcessor.from_pretrained(model_id, use_fast=True)
    model = Mask2FormerForUniversalSegmentation.from_pretrained(model_id).to(DEVICE).eval()
    return ("mask2former-swin-small", processor, model)


def _normalize_inputs(inputs: dict) -> dict:
    """Ensure pixel_values is float and on DEVICE.

    Slow image processors return uint8 tensors normalized later by float ops, but
    on Apple MPS the conv layers refuse uint8 input. Cast and re-normalize.
    """
    pv = inputs["pixel_values"]
    if pv.dtype != torch.float32:
        # uint8 -> [0, 1] float, then ImageNet-style normalize
        pv = pv.float() / 255.0
        mean = torch.tensor([0.485, 0.456, 0.406], device=pv.device).view(1, 3, 1, 1)
        std = torch.tensor([0.229, 0.224, 0.225], device=pv.device).view(1, 3, 1, 1)
        pv = (pv - mean) / std
        inputs["pixel_values"] = pv
    return inputs


def infer_mask2former(model_tuple, image_path: Path) -> dict:
    """Run Mask2Former on one tile, return aggregate stats."""
    name, processor, model = model_tuple
    img = Image.open(image_path).convert("RGB")
    inputs = processor(images=img, return_tensors="pt").to(DEVICE)
    inputs = _normalize_inputs(inputs)
    with torch.no_grad():
        outputs = model(**inputs)
    # Mask2Former: post-process panoptic or semantic
    target_size = [(img.height, img.width)]
    try:
        result = processor.post_process_panoptic_segmentation(outputs, target_sizes=target_size)[0]
    except Exception:
        result = processor.post_process_semantic_segmentation(outputs, target_sizes=target_size)[0]

    # Try to find a "solar" label
    id2label = model.config.id2label
    seg = result["segmentation"] if isinstance(result, dict) else result
    seg_np = seg.cpu().numpy() if hasattr(seg, "cpu") else np.asarray(seg)

    # Sum per-class pixel counts
    if isinstance(result, dict) and "segments_info" in result:
        # Panoptic
        info = result["segments_info"]
        solar_pixels = 0
        max_score = 0.0
        for s in info:
            label = id2label.get(s["label_id"], str(s["label_id"]))
            if "solar" in label.lower() or "panel" in label.lower():
                solar_pixels += int((seg_np == s["id"]).sum())
                max_score = max(max_score, s.get("score", 1.0))
        total_px = seg_np.size
        coverage = solar_pixels / total_px
        return {
            "model": name,
            "image": str(image_path.name),
            "total_pixels": total_px,
            "solar_pixels": solar_pixels,
            "coverage": coverage,
            "max_score": max_score,
            "id2label": id2label,
        }
    else:
        # Semantic
        unique, counts = np.unique(seg_np, return_counts=True)
        per_class = {int(u): int(c) for u, c in zip(unique, counts)}
        solar_pixels = 0
        for cid, cnt in per_class.items():
            label = id2label.get(cid, str(cid))
            if "solar" in label.lower() or "panel" in label.lower():
                solar_pixels += cnt
        total_px = seg_np.size
        return {
            "model": name,
            "image": str(image_path.name),
            "total_pixels": total_px,
            "solar_pixels": solar_pixels,
            "coverage": solar_pixels / total_px,
            "per_class": {id2label.get(k, str(k)): v for k, v in per_class.items()},
            "id2label": id2label,
        }


def save_overlay(image_path: Path, model_tuple, out_path: Path) -> None:
    """Render seg mask overlaid on the source image."""
    name, processor, model = model_tuple
    img = Image.open(image_path).convert("RGB")
    inputs = processor(images=img, return_tensors="pt").to(DEVICE)
    inputs = _normalize_inputs(inputs)
    with torch.no_grad():
        outputs = model(**inputs)
    target_size = [(img.height, img.width)]
    try:
        result = processor.post_process_panoptic_segmentation(outputs, target_sizes=target_size)[0]
        seg = result["segmentation"].cpu().numpy()
        info = result["segments_info"]
        id2label = model.config.id2label
        mask = np.zeros((img.height, img.width), dtype=np.uint8)
        for s in info:
            label = id2label.get(s["label_id"], str(s["label_id"]))
            if "solar" in label.lower() or "panel" in label.lower():
                mask[seg == s["id"]] = 255
    except Exception:
        seg = processor.post_process_semantic_segmentation(outputs, target_sizes=target_size)[0]
        seg_np = seg.cpu().numpy() if hasattr(seg, "cpu") else np.asarray(seg)
        id2label = model.config.id2label
        mask = np.zeros_like(seg_np, dtype=np.uint8)
        for cid in np.unique(seg_np):
            label = id2label.get(int(cid), str(cid))
            if "solar" in label.lower() or "panel" in label.lower():
                mask[seg_np == cid] = 255
    overlay = img.copy()
    red = Image.new("RGB", img.size, (217, 119, 87))
    overlay.paste(red, mask=Image.fromarray(mask))
    blended = Image.blend(img, overlay, 0.45)
    blended.save(out_path, quality=85)


def main() -> int:
    # Try Mask2Former Swin-Large first
    model_tuple = None
    for loader in (try_mask2former_swin_large, try_mask2former_swin_small):
        try:
            model_tuple = loader()
            break
        except Exception as exc:
            print(f"[spike] loader failed: {exc}", file=sys.stderr)

    if model_tuple is None:
        print("[spike] all model loaders failed", file=sys.stderr)
        return 1

    name, processor, model = model_tuple
    print(f"[spike] using model: {name}")
    print(f"[spike] id2label: {model.config.id2label}")

    cases = load_case_studies()
    pos_gt = load_groundtruth_positives()
    neg_gt = load_groundtruth_negatives(n=30)

    print(f"[spike] case studies (n={len(cases)})")
    print(f"[spike] gt positives (n={len(pos_gt)})")
    print(f"[spike] gt negatives (n={len(neg_gt)})")

    results = {"model": name, "case_studies": [], "gt_positives": [], "gt_negatives": []}

    for cid, path in cases:
        t0 = time.time()
        r = infer_mask2former(model_tuple, path)
        r["case_id"] = cid
        r["expected"] = "solar"
        r["latency_ms"] = int((time.time() - t0) * 1000)
        # Drop id2label per-row to keep output compact
        r.pop("id2label", None)
        results["case_studies"].append(r)
        print(
            f"  case {cid:14s} cov={r['coverage']:.4f} solar_px={r['solar_pixels']:6d} t={r['latency_ms']}ms"
        )
        save_overlay(path, model_tuple, SPIKE_OUT / f"case_{cid}_overlay.jpg")

    for idx, path in pos_gt:
        r = infer_mask2former(model_tuple, path)
        r["gt_idx"] = idx
        r["expected"] = "solar"
        r.pop("id2label", None)
        results["gt_positives"].append(r)
        print(f"  pos  {idx:14s} cov={r['coverage']:.4f} solar_px={r['solar_pixels']:6d}")
        save_overlay(path, model_tuple, SPIKE_OUT / f"pos_{idx}_overlay.jpg")

    for idx, path in neg_gt[:15]:
        r = infer_mask2former(model_tuple, path)
        r["gt_idx"] = idx
        r["expected"] = "not_solar"
        r.pop("id2label", None)
        results["gt_negatives"].append(r)
        print(f"  neg  {idx:14s} cov={r['coverage']:.4f} solar_px={r['solar_pixels']:6d}")

    # Aggregate metrics
    THRESH_PIXELS = 100
    case_pos = sum(1 for r in results["case_studies"] if r["solar_pixels"] >= THRESH_PIXELS)
    pos_pos = sum(1 for r in results["gt_positives"] if r["solar_pixels"] >= THRESH_PIXELS)
    neg_pos = sum(1 for r in results["gt_negatives"] if r["solar_pixels"] >= THRESH_PIXELS)

    n_cases = len(results["case_studies"])
    n_pos = len(results["gt_positives"])
    n_neg = len(results["gt_negatives"])

    print()
    print(f"[spike] === AGGREGATE (threshold = {THRESH_PIXELS} solar px) ===")
    print(
        f"  case studies (verified pos): {case_pos}/{n_cases} flagged ({case_pos / max(1, n_cases) * 100:.0f}%)"
    )
    print(f"  gt positives (labels.json):  {pos_pos}/{n_pos} flagged ({pos_pos / max(1, n_pos) * 100:.0f}%)")
    print(f"  gt negatives (labels.json):  {neg_pos}/{n_neg} flagged ({neg_pos / max(1, n_neg) * 100:.0f}%)")
    total_pos = case_pos + pos_pos
    total_pos_n = n_cases + n_pos
    if total_pos + neg_pos > 0:
        precision = total_pos / (total_pos + neg_pos)
        print(f"  combined precision: {precision:.3f}")
    print(f"  combined recall (pos): {total_pos / max(1, total_pos_n):.3f}")

    out_path = SPIKE_OUT / "spike_results.json"
    with out_path.open("w") as f:
        json.dump(results, f, indent=2)
    print(f"[spike] wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
