"""Inspect raw Mask2Former outputs to understand why segmentation fills 100%.

Look at class_queries_logits (per-query class probabilities) and
masks_queries_logits (per-query masks) to find a usable threshold.
"""

from __future__ import annotations

import sys
from pathlib import Path

import torch
from PIL import Image
from transformers import (
    AutoImageProcessor,
    Mask2FormerForUniversalSegmentation,
)

ROOT = Path(__file__).resolve().parents[2]
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"

MODEL_ID = "abdulsalama/SV-solar-mask2-swin-large-ade-200-deepsolar-2023060311"

POSITIVES = [
    ROOT / "site/public/case_studies/meycauayan.jpg",
    ROOT / "site/public/case_studies/makati.jpg",
]
NEGATIVES = []
GROUNDTRUTH_TILES = ROOT / "docs/groundtruth/tiles"
import json

with (ROOT / "docs/groundtruth/labels.json").open() as f:
    labels = json.load(f)["labels"]
for it in labels:
    if it.get("label") == "not_solar":
        tiles = list(GROUNDTRUTH_TILES.glob(f"{it['idx']}_*.jpg"))
        if tiles:
            NEGATIVES.append(tiles[0])
        if len(NEGATIVES) >= 4:
            break


def main() -> int:
    processor = AutoImageProcessor.from_pretrained(MODEL_ID, use_fast=True)
    model = Mask2FormerForUniversalSegmentation.from_pretrained(MODEL_ID).to(DEVICE).eval()
    print(f"id2label: {model.config.id2label}")
    print(f"num_labels: {len(model.config.id2label)}")

    for label, paths in [("POSITIVE", POSITIVES), ("NEGATIVE", NEGATIVES[:3])]:
        print(f"\n=== {label} ===")
        for path in paths:
            img = Image.open(path).convert("RGB")
            inputs = processor(images=img, return_tensors="pt").to(DEVICE)
            pv = inputs["pixel_values"]
            if pv.dtype != torch.float32:
                pv = pv.float() / 255.0
                mean = torch.tensor([0.485, 0.456, 0.406], device=pv.device).view(1, 3, 1, 1)
                std = torch.tensor([0.229, 0.224, 0.225], device=pv.device).view(1, 3, 1, 1)
                pv = (pv - mean) / std
                inputs["pixel_values"] = pv
            with torch.no_grad():
                outputs = model(**inputs)

            # Per-query class logits: [batch, num_queries, num_labels+1]
            cls_logits = outputs.class_queries_logits  # [1, Q, num_labels+1]
            cls_probs = cls_logits.softmax(dim=-1)
            # Per-query mask logits: [batch, num_queries, H', W']
            mask_logits = outputs.masks_queries_logits  # [1, Q, H', W']
            mask_probs = mask_logits.sigmoid()

            num_queries = cls_logits.shape[1]
            num_classes = cls_logits.shape[-1] - 1  # last is "no object"

            print(f"\n  {path.name}: queries={num_queries} classes={num_classes}")
            # Probability of "solar" (class 0) per query
            solar_prob_per_query = cls_probs[0, :, 0]  # [Q]
            no_object_prob_per_query = cls_probs[0, :, -1]  # [Q]
            top_solar = torch.topk(solar_prob_per_query, k=10)
            print(f"    top-10 solar prob: {top_solar.values.cpu().numpy().round(3).tolist()}")
            print(
                f"    those queries no-object prob: {no_object_prob_per_query[top_solar.indices].cpu().numpy().round(3).tolist()}"
            )

            # For each high-confidence solar query, what fraction of pixels does its mask cover?
            top_idx = top_solar.indices
            for k in range(min(5, len(top_idx))):
                qi = top_idx[k].item()
                solar_p = solar_prob_per_query[qi].item()
                no_obj_p = no_object_prob_per_query[qi].item()
                m = mask_probs[0, qi]  # [H', W']
                bin_mask = (m > 0.5).float()
                coverage = bin_mask.mean().item()
                print(
                    f"      query #{qi}: p_solar={solar_p:.3f} p_no_obj={no_obj_p:.3f} mask_coverage={coverage:.3f}"
                )
    return 0


if __name__ == "__main__":
    sys.exit(main())
