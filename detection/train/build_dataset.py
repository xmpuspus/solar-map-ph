"""Build PH solar training dataset from case studies + ground-truth labels.

Outputs:
  detection/train/dataset.npz with keys:
    X (N, D) float32: CLIP-ViT-L image embeddings
    y (N,) int8:      1=solar, 0=not_solar
    src (N,) str:     source image (for diagnostics)
    aug (N,) str:     augmentation tag

Sources:
  positives = 6 case studies (600x600, ~0.4 m/px), augmented 32x each
  negatives = available GT not_solar tiles (~50, 512x512, ~0.5 m/px), augmented 4x each

Augmentations: rotation (0/90/180/270), horizontal flip, mild color jitter.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageEnhance

ROOT = Path(__file__).resolve().parents[2]
CASE_STUDIES = ROOT / "site" / "public" / "case_studies"
GROUNDTRUTH_TILES = ROOT / "docs" / "groundtruth" / "tiles"
LABELS = ROOT / "docs" / "groundtruth" / "labels.json"
OUT = ROOT / "detection" / "train" / "dataset.npz"
OUT.parent.mkdir(parents=True, exist_ok=True)

DEVICE = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
SEED = 42
random.seed(SEED)
np.random.seed(SEED)


def augment(img: Image.Image, n: int) -> list[tuple[Image.Image, str]]:
    """Return n augmented copies with deterministic-ish tag strings."""
    rng = random.Random(SEED + hash(img.tobytes()) % 10000)
    out: list[tuple[Image.Image, str]] = []
    seen_tags: set[str] = set()
    while len(out) < n:
        rot = rng.choice([0, 90, 180, 270])
        flip = rng.choice([False, True])
        bri = round(rng.uniform(0.85, 1.15), 2)
        col = round(rng.uniform(0.9, 1.1), 2)
        tag = f"r{rot}_f{int(flip)}_b{bri}_c{col}"
        if tag in seen_tags and len(seen_tags) < n * 2:
            continue
        seen_tags.add(tag)
        x = img.rotate(rot)
        if flip:
            x = x.transpose(Image.FLIP_LEFT_RIGHT)
        x = ImageEnhance.Brightness(x).enhance(bri)
        x = ImageEnhance.Color(x).enhance(col)
        out.append((x, tag))
    return out


def load_clip():
    from transformers import CLIPModel, CLIPProcessor

    print("[ds] loading openai/clip-vit-large-patch14")
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14", use_fast=True)
    model = CLIPModel.from_pretrained("openai/clip-vit-large-patch14").to(DEVICE).eval()
    return processor, model


def embed(processor, model, imgs: list[Image.Image], batch_size: int = 16) -> np.ndarray:
    embs = []
    for i in range(0, len(imgs), batch_size):
        batch = imgs[i : i + batch_size]
        inputs = processor(images=batch, return_tensors="pt").to(DEVICE)
        with torch.no_grad():
            e = model.get_image_features(**inputs)
        e = e / e.norm(dim=-1, keepdim=True)
        embs.append(e.cpu().numpy())
    return np.concatenate(embs, axis=0).astype(np.float32)


def main() -> int:
    processor, model = load_clip()

    # POSITIVES: 6 case studies + the 3 GT solar tiles that have files
    pos_paths: list[tuple[str, Path]] = []
    for p in sorted(CASE_STUDIES.glob("*.jpg")):
        pos_paths.append((f"case_{p.stem}", p))
    with LABELS.open() as f:
        labels = json.load(f)["labels"]
    for it in labels:
        if it.get("label") == "solar":
            tiles = list(GROUNDTRUTH_TILES.glob(f"{it['idx']}_*.jpg"))
            if tiles:
                pos_paths.append((f"gt_{it['idx']}", tiles[0]))
    print(f"[ds] positives: {len(pos_paths)} unique source tiles")

    neg_paths: list[tuple[str, Path]] = []
    for it in labels:
        if it.get("label") == "not_solar":
            tiles = list(GROUNDTRUTH_TILES.glob(f"{it['idx']}_*.jpg"))
            if tiles:
                neg_paths.append((f"gt_{it['idx']}", tiles[0]))
    print(f"[ds] negatives: {len(neg_paths)} unique source tiles")

    # POS_AUG_PER_SOURCE positives per source, NEG_AUG_PER_SOURCE per negative.
    # Want roughly balanced classes.
    POS_AUG_PER_SOURCE = 32
    NEG_AUG_PER_SOURCE = max(1, len(pos_paths) * POS_AUG_PER_SOURCE // max(1, len(neg_paths)))
    print(f"[ds] aug ratios: pos={POS_AUG_PER_SOURCE}/src  neg={NEG_AUG_PER_SOURCE}/src")

    rows = []  # list of (image_PIL, label, src, aug)
    for src, path in pos_paths:
        img = Image.open(path).convert("RGB")
        # also add the un-augmented original
        rows.append((img.copy(), 1, src, "orig"))
        for aug_img, tag in augment(img, POS_AUG_PER_SOURCE):
            rows.append((aug_img, 1, src, tag))

    for src, path in neg_paths:
        img = Image.open(path).convert("RGB")
        rows.append((img.copy(), 0, src, "orig"))
        for aug_img, tag in augment(img, NEG_AUG_PER_SOURCE):
            rows.append((aug_img, 0, src, tag))

    print(
        f"[ds] total rows: {len(rows)} (pos={sum(1 for r in rows if r[1] == 1)} neg={sum(1 for r in rows if r[1] == 0)})"
    )

    imgs = [r[0] for r in rows]
    print(f"[ds] embedding {len(imgs)} tiles via CLIP-ViT-L...")
    X = embed(processor, model, imgs, batch_size=8)
    y = np.array([r[1] for r in rows], dtype=np.int8)
    src = np.array([r[2] for r in rows])
    aug_tags = np.array([r[3] for r in rows])

    np.savez_compressed(OUT, X=X, y=y, src=src, aug=aug_tags)
    print(f"[ds] wrote {OUT}: X.shape={X.shape} y.shape={y.shape}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
