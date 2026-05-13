"""Phase-3 encoder ablation: same training set, same head, same CV split.

Parametric encoder runner. Reproduces the build_dataset_v3.py source list
exactly, embeds every (image, label, source) row through the chosen encoder,
trains the same LR on the same 80% set, and applies Platt calibration on the
same 20% holdout. Reports calibrated metrics directly comparable to clf_v4
calibrated holdout from Phase 2.

Usage:
  python3 encoder_ablation.py --encoder openai/clip-vit-large-patch14
  python3 encoder_ablation.py --encoder facebook/dinov2-large
  python3 encoder_ablation.py --encoder allenai/satlas-pretrain  # if available

Outputs (under detection/train/v4_calibrated/ablation/<encoder_slug>/):
  embeddings.npz       (X, y, src)
  clf.joblib           (base + Platt)
  metrics.json         (LOSO + calibrated holdout summary)
"""

from __future__ import annotations

import argparse
import json
import random
import re
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageEnhance
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[3]
OSM_TILES = ROOT / "detection" / "bootstrap" / "tiles"
OSM_INDEX = OSM_TILES / "index.json"
GT_TILES = ROOT / "docs" / "groundtruth" / "tiles"
LABELS = ROOT / "docs" / "groundtruth" / "labels.json"
RANDOM_NEG_DIR = ROOT / "detection" / "train" / "random_neg_tiles"
NCR_TILES = ROOT / "detection" / "scan" / "ncr_tiles"
TAGS = ROOT / "detection" / "verify" / "tags.json"
SPLIT = ROOT / "detection" / "train" / "v4_calibrated" / "holdout_split.json"
ABLATION_ROOT = ROOT / "detection" / "train" / "v4_calibrated" / "ablation"

DEVICE = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
KNOWN_FN_RNEGS = {"rneg_0116", "rneg_0136", "rneg_0074", "rneg_0086"}
NOISY_CASES = {"case_valenzuela", "case_san_mateo"}


def slug(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_")


def dedupe_by_grid(items, precision=4):
    seen = set()
    out = []
    for it in items:
        key = (round(it["lat"], precision), round(it["lon"], precision))
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def augment(img: Image.Image, n: int):
    rng = random.Random(SEED + hash(img.tobytes()) % 10000)
    out = []
    seen = set()
    while len(out) < n:
        rot = rng.choice([0, 90, 180, 270])
        flip = rng.choice([False, True])
        bri = round(rng.uniform(0.85, 1.15), 2)
        col = round(rng.uniform(0.9, 1.1), 2)
        tag = (rot, flip, bri, col)
        if tag in seen and len(seen) < n * 2:
            continue
        seen.add(tag)
        x = img.rotate(rot)
        if flip:
            x = x.transpose(Image.FLIP_LEFT_RIGHT)
        x = ImageEnhance.Brightness(x).enhance(bri)
        x = ImageEnhance.Color(x).enhance(col)
        out.append(x)
    return out


def collect_sources():
    """Same source assembly logic as build_dataset_v3.py."""
    pos_paths = []
    neg_paths = []

    osm_index = json.loads(OSM_INDEX.read_text())
    osm_index = [it for it in osm_index if it.get("fetch_ok")]
    osm_dedup = dedupe_by_grid(osm_index, 4)
    for it in osm_dedup:
        tile = OSM_TILES / f"{it['idx']:04d}.jpg"
        if tile.exists():
            pos_paths.append((f"osm_{it['idx']:04d}", tile))

    cases_dir = ROOT / "site" / "public" / "case_studies"
    for p in sorted(cases_dir.glob("*.jpg")):
        src = f"case_{p.stem}"
        if src in NOISY_CASES:
            continue
        pos_paths.append((src, p))

    for name in sorted(KNOWN_FN_RNEGS):
        p = RANDOM_NEG_DIR / f"{name}.jpg"
        if p.exists():
            pos_paths.append((f"v3promo_{name}", p))

    if TAGS.exists():
        for r in json.loads(TAGS.read_text()):
            if r.get("label") != "true":
                continue
            tid = r["tile_id"]
            p = NCR_TILES / f"{tid}.jpg"
            if p.exists():
                pos_paths.append((f"v3conf_{tid}", p))

    with LABELS.open() as f:
        gt = json.load(f)["labels"]
    for it in gt:
        if it.get("label") == "not_solar":
            tiles = list(GT_TILES.glob(f"{it['idx']}_*.jpg"))
            if tiles:
                neg_paths.append((f"gt_{it['idx']}", tiles[0]))

    for p in sorted(RANDOM_NEG_DIR.glob("rneg_*.jpg")):
        if p.stem in KNOWN_FN_RNEGS:
            continue
        neg_paths.append((f"rneg_{p.stem}", p))

    if TAGS.exists():
        for r in json.loads(TAGS.read_text()):
            if r.get("label") != "false":
                continue
            tid = r["tile_id"]
            p = NCR_TILES / f"{tid}.jpg"
            if p.exists():
                neg_paths.append((f"v3fp_{tid}", p))

    return pos_paths, neg_paths


def load_encoder(name: str):
    """Return (preprocess_fn, embed_fn(images_list)->np.ndarray) for the given HF model."""
    print(f"[ablation] loading encoder {name} on {DEVICE}")
    if name.startswith("openai/clip"):
        from transformers import CLIPModel, CLIPProcessor

        proc = CLIPProcessor.from_pretrained(name, use_fast=True)
        model = CLIPModel.from_pretrained(name).to(DEVICE).eval()

        def embed(imgs, batch_size=8):
            embs = []
            for i in range(0, len(imgs), batch_size):
                batch = imgs[i : i + batch_size]
                inputs = proc(images=batch, return_tensors="pt").to(DEVICE)
                with torch.no_grad():
                    e = model.get_image_features(**inputs)
                e = e / e.norm(dim=-1, keepdim=True)
                embs.append(e.cpu().numpy())
            return np.concatenate(embs, axis=0).astype(np.float32)

        return embed
    if name.startswith("facebook/dinov2"):
        from transformers import AutoImageProcessor, AutoModel

        proc = AutoImageProcessor.from_pretrained(name, use_fast=True)
        model = AutoModel.from_pretrained(name).to(DEVICE).eval()

        def embed(imgs, batch_size=8):
            embs = []
            for i in range(0, len(imgs), batch_size):
                batch = imgs[i : i + batch_size]
                inputs = proc(images=batch, return_tensors="pt").to(DEVICE)
                with torch.no_grad():
                    out = model(**inputs)
                # DINOv2 returns last_hidden_state; use CLS token (index 0) or pooled
                cls = out.last_hidden_state[:, 0]
                cls = cls / cls.norm(dim=-1, keepdim=True)
                embs.append(cls.cpu().numpy())
            return np.concatenate(embs, axis=0).astype(np.float32)

        return embed
    if name.startswith("satlas:"):
        # name format: "satlas:Aerial_SwinB_SI"
        import satlaspretrain_models
        from torchvision import transforms

        identifier = name.split(":", 1)[1]
        wm = satlaspretrain_models.Weights()
        # Library hardcodes device='cuda' default; pass 'cpu' so map_location works on
        # CUDA-less hosts (M-series Mac), then move to MPS afterwards.
        model = wm.get_pretrained_model(model_identifier=identifier, fpn=False, head=False, device="cpu")
        model = model.to(DEVICE).eval()

        # Aerial Swin-B expects 512x512 RGB normalized to [0,1] then to ImageNet mean/std.
        # Per satlas docs the input range is 0-255 cast to float and divided by 255.
        # The Swin model returns a list of feature maps from multiple stages; final
        # stage is index 3. We mean-pool that to a single vector per image.
        prep = transforms.Compose(
            [
                transforms.Resize((512, 512)),
                transforms.ToTensor(),  # 0-1 float
            ]
        )

        def embed(imgs, batch_size=4):
            embs = []
            for i in range(0, len(imgs), batch_size):
                batch = imgs[i : i + batch_size]
                tensors = torch.stack([prep(img) for img in batch]).to(DEVICE)
                with torch.no_grad():
                    out = model(tensors)
                # Swin backbone (no head/fpn) returns list of 4 multi-scale feature maps
                # [B, C, H, W]. Use the deepest stage; mean-pool spatial dims.
                feat = out[-1].mean(dim=[2, 3])
                feat = feat / feat.norm(dim=-1, keepdim=True)
                embs.append(feat.cpu().numpy())
            return np.concatenate(embs, axis=0).astype(np.float32)

        return embed
    raise ValueError(f"unsupported encoder: {name}")


def evaluate_loso(X, y, src):
    """5-fold group-aware CV identical to train_v3.py."""
    rng = np.random.default_rng(42)
    pos_sources = sorted(set(src[y == 1].tolist()))
    neg_sources = sorted(set(src[y == 0].tolist()))
    K = 5
    pos_folds = [pos_sources[i::K] for i in range(K)]
    neg_folds = [neg_sources[i::K] for i in range(K)]
    per_source = {}
    for fold in range(K):
        held = set(pos_folds[fold]) | set(neg_folds[fold])
        train_mask = np.array([s not in held for s in src])
        val_mask = np.array([s in held for s in src])
        clf = LogisticRegression(max_iter=2000, C=1.0, class_weight="balanced", random_state=42)
        clf.fit(X[train_mask], y[train_mask])
        scores = clf.predict_proba(X[val_mask])[:, 1]
        val_src = src[val_mask]
        val_y = y[val_mask]
        for s in held:
            mask = val_src == s
            if not mask.any():
                continue
            per_source[s] = {"true_label": int(val_y[mask][0]), "max_score": float(scores[mask].max())}
    pos_scores = sorted(r["max_score"] for r in per_source.values() if r["true_label"] == 1)
    neg_scores = sorted(r["max_score"] for r in per_source.values() if r["true_label"] == 0)

    best = (-1.0, None, 0, 0, 0, 0)
    fixed_t = 0.85
    fixed = None
    all_t = sorted(set(pos_scores + neg_scores))
    for t in all_t:
        tp = sum(1 for s in pos_scores if s >= t)
        fp = sum(1 for s in neg_scores if s >= t)
        fn = sum(1 for s in pos_scores if s < t)
        tn = sum(1 for s in neg_scores if s < t)
        if tp + fp == 0:
            continue
        p = tp / (tp + fp)
        r = tp / max(1, tp + fn)
        f1 = 2 * p * r / max(1e-9, p + r)
        if f1 > best[0]:
            best = (f1, t, tp, fp, fn, tn)
    tp = sum(1 for s in pos_scores if s >= fixed_t)
    fp = sum(1 for s in neg_scores if s >= fixed_t)
    fn = sum(1 for s in pos_scores if s < fixed_t)
    tn = sum(1 for s in neg_scores if s < fixed_t)
    if tp + fp > 0:
        fixed = {
            "threshold": fixed_t,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": tp / (tp + fp),
            "recall": tp / max(1, tp + fn),
            "f1": 2
            * (tp / (tp + fp))
            * (tp / max(1, tp + fn))
            / max(1e-9, tp / (tp + fp) + tp / max(1, tp + fn)),
        }
    f1, t, tp, fp, fn, tn = best
    return {
        "best_f1": {
            "f1": f1,
            "threshold": t,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": tp / max(1, tp + fp),
            "recall": tp / max(1, tp + fn),
        },
        "at_threshold_0p85": fixed,
    }


def evaluate_calibrated(X, y, src, split):
    """Train on 80% per holdout_split.json, fit Platt on 20% holdout, sweep thresholds."""
    holdout_pos = set(split["holdout_pos_sources"])
    holdout_neg = set(split["holdout_neg_sources"])
    holdout_set = holdout_pos | holdout_neg
    holdout_mask = np.array([s in holdout_set for s in src])
    train_mask = ~holdout_mask
    base = LogisticRegression(max_iter=2000, C=1.0, class_weight="balanced", random_state=42)
    base.fit(X[train_mask], y[train_mask])
    raw = base.decision_function(X[holdout_mask])
    y_h = y[holdout_mask]
    src_h = src[holdout_mask]
    platt = LogisticRegression(C=1e6, solver="lbfgs", max_iter=1000)
    platt.fit(raw.reshape(-1, 1), y_h)
    A = float(platt.coef_[0, 0])
    B = float(platt.intercept_[0])
    cal = 1.0 / (1.0 + np.exp(-(A * raw + B)))
    src_max = {}
    src_lab = {}
    for s, lab, c in zip(src_h, y_h, cal):
        if s not in src_max or c > src_max[s]:
            src_max[s] = float(c)
            src_lab[s] = int(lab)
    pos_cal = sorted(src_max[s] for s in src_max if src_lab[s] == 1)
    neg_cal = sorted(src_max[s] for s in src_max if src_lab[s] == 0)

    # @ t=0.85
    t = 0.85
    tp = sum(1 for s in pos_cal if s >= t)
    fp = sum(1 for s in neg_cal if s >= t)
    fn = sum(1 for s in pos_cal if s < t)
    tn = sum(1 for s in neg_cal if s < t)
    p085 = tp / (tp + fp) if (tp + fp) else None
    r085 = tp / max(1, tp + fn)
    f1085 = 2 * (p085 or 0) * r085 / max(1e-9, (p085 or 0) + r085) if p085 else 0.0
    return {
        "platt_A": A,
        "platt_B": B,
        "n_holdout_pos_sources": len(pos_cal),
        "n_holdout_neg_sources": len(neg_cal),
        "at_calibrated_t085": {
            "threshold": 0.85,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": p085,
            "recall": r085,
            "f1": f1085,
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--encoder", required=True, help="HuggingFace model id")
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--pos-aug", type=int, default=4)
    ap.add_argument("--neg-aug", type=int, default=4)
    args = ap.parse_args()

    out_dir = ABLATION_ROOT / slug(args.encoder)
    out_dir.mkdir(parents=True, exist_ok=True)

    pos_paths, neg_paths = collect_sources()
    print(f"[ablation] {len(pos_paths)} pos sources, {len(neg_paths)} neg sources")

    rows = []
    t0 = time.time()
    for src_name, path in pos_paths:
        try:
            img = Image.open(path).convert("RGB")
        except Exception as e:
            print(f"  load fail {path}: {e}")
            continue
        rows.append((img.copy(), 1, src_name))
        for a in augment(img, args.pos_aug):
            rows.append((a, 1, src_name))
    for src_name, path in neg_paths:
        try:
            img = Image.open(path).convert("RGB")
        except Exception as e:
            print(f"  load fail {path}: {e}")
            continue
        rows.append((img.copy(), 0, src_name))
        for a in augment(img, args.neg_aug):
            rows.append((a, 0, src_name))
    print(f"[ablation] {len(rows)} total rows assembled in {time.time() - t0:.1f}s")

    embed = load_encoder(args.encoder)
    imgs = [r[0] for r in rows]
    print(f"[ablation] embedding {len(imgs)} images...")
    t0 = time.time()
    X = embed(imgs, batch_size=args.batch_size)
    print(f"[ablation] embed time: {time.time() - t0:.1f}s; X.shape={X.shape}")
    y = np.array([r[1] for r in rows], dtype=np.int8)
    src = np.array([r[2] for r in rows])

    np.savez_compressed(out_dir / "embeddings.npz", X=X, y=y, src=src)

    loso = evaluate_loso(X, y, src)
    print(f"[ablation] LOSO best F1: {loso['best_f1']}")
    print(f"[ablation] LOSO @t=0.85: {loso['at_threshold_0p85']}")

    split = json.loads(SPLIT.read_text())
    cal = evaluate_calibrated(X, y, src, split)
    print(f"[ablation] calibrated @t=0.85: {cal['at_calibrated_t085']}")

    metrics = {
        "encoder": args.encoder,
        "feature_dim": int(X.shape[1]),
        "n_rows": len(rows),
        "n_pos_sources": len(pos_paths),
        "n_neg_sources": len(neg_paths),
        "device": DEVICE,
        "loso": loso,
        "calibrated_holdout": cal,
    }
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"[ablation] saved -> {out_dir / 'metrics.json'}")


if __name__ == "__main__":
    main()
