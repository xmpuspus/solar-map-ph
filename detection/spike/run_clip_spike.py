"""CLIP zero-shot spike: classify rooftop tiles as solar vs not_solar.

CLIP-ViT-L/14 has shown solid zero-shot transfer on aerial imagery.
We compare the cosine similarity between the image embedding and a small
ensemble of text prompts for each class.

Discriminator: similarity_solar - similarity_not_solar (margin).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
CASE_STUDIES = ROOT / "site" / "public" / "case_studies"
GROUNDTRUTH_TILES = ROOT / "docs" / "groundtruth" / "tiles"
LABELS = ROOT / "docs" / "groundtruth" / "labels.json"
OUT_DIR = ROOT / "detection" / "spike" / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DEVICE = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
print(f"[clip] device={DEVICE}")

SOLAR_PROMPTS = [
    "a satellite image of a rooftop with dark blue solar panels arranged in a grid",
    "an aerial photograph of solar photovoltaic panels on a rooftop",
    "a satellite photo showing rectangular solar panels installed on a building roof",
    "an aerial view of dark gridded solar panels on top of a warehouse",
    "a top-down satellite image of a flat roof covered with solar panels",
]
NOT_SOLAR_PROMPTS = [
    "a satellite image of a rooftop without solar panels",
    "an aerial photograph of a residential neighborhood with red and gray rooftops",
    "a top-down satellite view of warehouses with plain metal roofs",
    "an aerial image of buildings with no solar installations",
    "a satellite image of an urban area with concrete and asphalt rooftops",
]


def load_clip():
    from transformers import CLIPModel, CLIPProcessor
    model_id = "openai/clip-vit-large-patch14"
    print(f"[clip] loading {model_id}")
    processor = CLIPProcessor.from_pretrained(model_id)
    model = CLIPModel.from_pretrained(model_id).to(DEVICE).eval()
    return processor, model


def encode_text_prompts(processor, model, prompts: list[str]) -> torch.Tensor:
    inputs = processor(text=prompts, return_tensors="pt", padding=True).to(DEVICE)
    with torch.no_grad():
        text_emb = model.get_text_features(**inputs)
    text_emb = text_emb / text_emb.norm(dim=-1, keepdim=True)
    return text_emb.mean(dim=0, keepdim=True)  # [1, D] - average across the prompt ensemble


def score_image(processor, model, img: Image.Image, solar_emb: torch.Tensor, not_solar_emb: torch.Tensor) -> dict:
    inputs = processor(images=img, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        img_emb = model.get_image_features(**inputs)
    img_emb = img_emb / img_emb.norm(dim=-1, keepdim=True)
    sim_solar = (img_emb @ solar_emb.T).item()
    sim_not_solar = (img_emb @ not_solar_emb.T).item()
    return {"sim_solar": sim_solar, "sim_not_solar": sim_not_solar, "margin": sim_solar - sim_not_solar}


def crop_tiles(img: Image.Image, n: int = 3) -> list[Image.Image]:
    """Slice an image into a 3x3 grid (default n=3) so we can score per-region.

    A 600x600 image at ~0.4 m/px covers ~240m. 3x3 sub-tiles each cover ~80m,
    closer to the size of a single rooftop. CLIP scoring per sub-tile gives
    a much stronger positive signal when only one rooftop has panels.
    """
    out = []
    w, h = img.size
    sw = w // n
    sh = h // n
    for i in range(n):
        for j in range(n):
            box = (j * sw, i * sh, (j + 1) * sw, (i + 1) * sh)
            out.append(img.crop(box))
    return out


def main() -> int:
    processor, model = load_clip()
    solar_emb = encode_text_prompts(processor, model, SOLAR_PROMPTS)
    not_solar_emb = encode_text_prompts(processor, model, NOT_SOLAR_PROMPTS)
    print(f"[clip] solar prompt ensemble: {len(SOLAR_PROMPTS)}")
    print(f"[clip] not_solar prompt ensemble: {len(NOT_SOLAR_PROMPTS)}")

    targets = []
    # case studies: 6 verified positives
    for p in sorted(CASE_STUDIES.glob("*.jpg")):
        targets.append(("case", "solar", p.stem, p))
    # ground truth from labels.json
    with LABELS.open() as f:
        labels = json.load(f)["labels"]
    pos_count = 0
    neg_count = 0
    for it in labels:
        lbl = it.get("label")
        if lbl not in {"solar", "not_solar"}:
            continue
        tiles = list(GROUNDTRUTH_TILES.glob(f"{it['idx']}_*.jpg"))
        if not tiles:
            continue
        if lbl == "solar":
            targets.append(("gt", "solar", it["idx"], tiles[0]))
            pos_count += 1
        elif lbl == "not_solar" and neg_count < 30:
            targets.append(("gt", "not_solar", it["idx"], tiles[0]))
            neg_count += 1
    print(f"[clip] targets: {len(targets)} (cases=6, pos={pos_count}, neg={neg_count})")

    # Score full tile + max sub-tile
    rows = []
    for source, label, idx, path in targets:
        img = Image.open(path).convert("RGB")
        full = score_image(processor, model, img, solar_emb, not_solar_emb)
        sub_scores = [score_image(processor, model, sub, solar_emb, not_solar_emb)
                      for sub in crop_tiles(img, n=3)]
        max_sub_margin = max(s["margin"] for s in sub_scores)
        max_sub_solar = max(s["sim_solar"] for s in sub_scores)
        rows.append({
            "source": source,
            "label": label,
            "idx": idx,
            "file": path.name,
            "full_sim_solar": full["sim_solar"],
            "full_margin": full["margin"],
            "max_sub_margin": max_sub_margin,
            "max_sub_solar": max_sub_solar,
        })
        print(f"  [{source}/{label}] {idx:14s} full_margin={full['margin']:+.4f} max_sub_margin={max_sub_margin:+.4f}")

    # Find best threshold on full_margin and max_sub_margin
    pos_rows = [r for r in rows if r["label"] == "solar"]
    neg_rows = [r for r in rows if r["label"] == "not_solar"]
    print(f"\n[clip] positives: {len(pos_rows)}  negatives: {len(neg_rows)}")

    for metric in ("full_margin", "max_sub_margin", "max_sub_solar"):
        vals_p = sorted(r[metric] for r in pos_rows)
        vals_n = sorted(r[metric] for r in neg_rows)
        # try thresholds at every unique value, pick max F1
        best = (-1.0, None, 0, 0, 0)
        all_vals = sorted(set(vals_p + vals_n))
        for t in all_vals:
            tp = sum(1 for v in vals_p if v >= t)
            fp = sum(1 for v in vals_n if v >= t)
            fn = sum(1 for v in vals_p if v < t)
            if tp + fp == 0:
                continue
            precision = tp / (tp + fp)
            recall = tp / max(1, tp + fn)
            f1 = 2 * precision * recall / max(1e-9, precision + recall)
            if f1 > best[0]:
                best = (f1, t, tp, fp, fn)
        f1, t, tp, fp, fn = best
        precision = tp / max(1, tp + fp)
        recall = tp / max(1, tp + fn)
        print(f"\n  metric={metric}: best F1={f1:.3f} at threshold={t:+.4f}")
        print(f"    TP={tp} FP={fp} FN={fn}  precision={precision:.3f} recall={recall:.3f}")
        print(f"    pos values: min={min(vals_p):+.4f} med={vals_p[len(vals_p)//2]:+.4f} max={max(vals_p):+.4f}")
        print(f"    neg values: min={min(vals_n):+.4f} med={vals_n[len(vals_n)//2]:+.4f} max={max(vals_n):+.4f}")

    out_path = OUT_DIR / "clip_spike_results.json"
    with out_path.open("w") as f:
        json.dump({"rows": rows}, f, indent=2)
    print(f"\n[clip] wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
