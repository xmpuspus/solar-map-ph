"""V3 training dataset: v2 + label cleanup from active-learning verification pass.

Cleanup transformations vs v2:
  1. Move 4 known false-negative rnegs (rneg_0116, rneg_0136, rneg_0074, rneg_0086)
     from negative to positive class. These are real undocumented rooftop solar.
  2. Drop the 2 noisy case studies (case_valenzuela, case_san_mateo) which are
     not actually rooftop solar (frame house and greenhouse roofs respectively).
  3. From detection/verify/tags.json (user-tagged):
       - "true"      -> add the tile as a NEW positive (source: v3conf_<tile_id>)
       - "false"     -> nothing (not in v2 dataset to begin with; just skipped)
       - "ambiguous" -> nothing
       - null        -> nothing (treated as not yet verified)

Outputs:
  detection/train/dataset_v3.npz
  detection/train/dataset_v3_manifest.json   (sources used, rationale)
"""

from __future__ import annotations

import json
import math
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageEnhance

ROOT = Path(__file__).resolve().parents[2]
OSM_TILES = ROOT / "detection" / "bootstrap" / "tiles"
OSM_INDEX = OSM_TILES / "index.json"
GT_TILES = ROOT / "docs" / "groundtruth" / "tiles"
LABELS = ROOT / "docs" / "groundtruth" / "labels.json"
RANDOM_NEG_DIR = ROOT / "detection" / "train" / "random_neg_tiles"
NCR_TILES = ROOT / "detection" / "scan" / "ncr_tiles"
TAGS = ROOT / "detection" / "verify" / "tags.json"
OUT = ROOT / "detection" / "train" / "dataset_v3.npz"
MANIFEST = ROOT / "detection" / "train" / "dataset_v3_manifest.json"

import os

# Device selection.
#
# For the everyday "rebuild embeddings on my laptop" workflow, MPS or CUDA is
# preferred (10-30x faster than CPU on CLIP-ViT-L). For the deterministic-hash
# reproducibility recipe, force CPU because MPS does not yet expose the
# deterministic-algorithms guarantees torch.use_deterministic_algorithms wants.
#
# Override with SOLAR_MAP_PH_DEVICE=cpu | mps | cuda before invoking the script.
_DEVICE_OVERRIDE = os.environ.get("SOLAR_MAP_PH_DEVICE", "").lower()
if _DEVICE_OVERRIDE in {"cpu", "mps", "cuda"}:
    DEVICE = _DEVICE_OVERRIDE
elif torch.backends.mps.is_available():
    DEVICE = "mps"
elif torch.cuda.is_available():
    DEVICE = "cuda"
else:
    DEVICE = "cpu"

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)
# Deterministic mode: same input bytes -> same output bytes, regardless of
# whether torch picks a different cuDNN algorithm or autotune choice. Required
# for the bit-exact dataset_v4.npz reproducibility claim. Combine with
# SOLAR_MAP_PH_DEVICE=cpu for the strongest cross-machine guarantee.
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
os.environ.setdefault("PYTHONHASHSEED", "0")
torch.use_deterministic_algorithms(True, warn_only=True)

# Known false-negatives (rnegs that are actually real solar -- see project memory)
KNOWN_FN_RNEGS = {"rneg_0116", "rneg_0136", "rneg_0074", "rneg_0086"}

# Known noisy case studies (not actually rooftop solar)
NOISY_CASES = {"case_valenzuela", "case_san_mateo"}


def dedupe_by_grid(items: list[dict], precision: int = 4) -> list[dict]:
    seen = set()
    out = []
    for it in items:
        key = (round(it["lat"], precision), round(it["lon"], precision))
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def augment(img: Image.Image, n: int) -> list[Image.Image]:
    # SHA-256 of the image bytes gives a deterministic seed across processes
    # (Python's builtin hash() salts with PYTHONHASHSEED, which differs by run).
    import hashlib
    digest = hashlib.sha256(img.tobytes()).digest()
    seed_int = int.from_bytes(digest[:8], "big") % 1_000_003
    rng = random.Random(SEED + seed_int)
    out: list[Image.Image] = []
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


def load_clip():
    from transformers import CLIPModel, CLIPProcessor
    print("[v3] loading openai/clip-vit-large-patch14")
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14", use_fast=True)
    model = CLIPModel.from_pretrained("openai/clip-vit-large-patch14").to(DEVICE).eval()
    return processor, model


def embed(processor, model, imgs: list[Image.Image], batch_size: int = 8) -> np.ndarray:
    embs = []
    for i in range(0, len(imgs), batch_size):
        batch = imgs[i:i + batch_size]
        inputs = processor(images=batch, return_tensors="pt").to(DEVICE)
        with torch.no_grad():
            e = model.get_image_features(**inputs)
        e = e / e.norm(dim=-1, keepdim=True)
        embs.append(e.cpu().numpy())
    return np.concatenate(embs, axis=0).astype(np.float32)


def main() -> int:
    # ===== POSITIVES =====
    pos_paths: list[tuple[str, Path]] = []

    # OSM positives (deduped, same as v2)
    osm_index = json.loads(OSM_INDEX.read_text())
    osm_index = [it for it in osm_index if it.get("fetch_ok")]
    osm_dedup = dedupe_by_grid(osm_index, precision=4)
    print(f"[v3] OSM tiles after 10m dedup: {len(osm_dedup)}")
    for it in osm_dedup:
        tile = OSM_TILES / f"{it['idx']:04d}.jpg"
        if tile.exists():
            pos_paths.append((f"osm_{it['idx']:04d}", tile))

    # Case studies, EXCLUDING the 2 noisy ones
    cases_dir = ROOT / "site" / "public" / "case_studies"
    n_cases = 0
    n_dropped_cases = 0
    for p in sorted(cases_dir.glob("*.jpg")):
        src = f"case_{p.stem}"
        if src in NOISY_CASES:
            n_dropped_cases += 1
            print(f"[v3]   DROP noisy case: {src}")
            continue
        pos_paths.append((src, p))
        n_cases += 1
    print(f"[v3] case studies: {n_cases} kept, {n_dropped_cases} dropped")

    # 4 known false-negative rnegs -> moved to positives
    n_promoted_rnegs = 0
    for name in sorted(KNOWN_FN_RNEGS):
        p = RANDOM_NEG_DIR / f"{name}.jpg"
        if not p.exists():
            print(f"[v3] WARN: {p} not found", file=sys.stderr)
            continue
        # Source name encodes the promotion
        pos_paths.append((f"v3promo_{name}", p))
        n_promoted_rnegs += 1
    print(f"[v3] promoted rnegs to positive: {n_promoted_rnegs}")

    # User-tagged high-confidence tiles labeled "true" -> new positives
    n_user_true = 0
    if TAGS.exists():
        tag_rows = json.loads(TAGS.read_text())
        for r in tag_rows:
            if r.get("label") != "true":
                continue
            tid = r["tile_id"]
            p = NCR_TILES / f"{tid}.jpg"
            if not p.exists():
                print(f"[v3] WARN: tagged-true tile missing: {p}", file=sys.stderr)
                continue
            pos_paths.append((f"v3conf_{tid}", p))
            n_user_true += 1
        print(f"[v3] user-tagged TRUE high-conf tiles added: {n_user_true}")
    else:
        print(f"[v3] NOTE: {TAGS} not yet present; running without user tags (cleanup-only run)")

    # ===== NEGATIVES =====
    neg_paths: list[tuple[str, Path]] = []

    # GT not_solar (same as v2)
    n_gt_neg = 0
    with LABELS.open() as f:
        labels = json.load(f)["labels"]
    for it in labels:
        if it.get("label") == "not_solar":
            tiles = list(GT_TILES.glob(f"{it['idx']}_*.jpg"))
            if tiles:
                neg_paths.append((f"gt_{it['idx']}", tiles[0]))
                n_gt_neg += 1
    print(f"[v3] GT not_solar negatives: {n_gt_neg}")

    # Random NCR negatives, MINUS the 4 promoted ones
    n_rneg = 0
    n_rneg_skipped = 0
    for p in sorted(RANDOM_NEG_DIR.glob("rneg_*.jpg")):
        if p.stem in KNOWN_FN_RNEGS:
            n_rneg_skipped += 1
            continue
        neg_paths.append((f"rneg_{p.stem}", p))
        n_rneg += 1
    print(f"[v3] random NCR negatives: {n_rneg} ({n_rneg_skipped} promoted -> excluded)")

    # User-tagged high-conf tiles labeled "false" -> add as negatives
    # (These are tiles the v2 model flagged high but the user says aren't solar.)
    n_user_false = 0
    if TAGS.exists():
        tag_rows = json.loads(TAGS.read_text())
        for r in tag_rows:
            if r.get("label") != "false":
                continue
            tid = r["tile_id"]
            p = NCR_TILES / f"{tid}.jpg"
            if not p.exists():
                continue
            neg_paths.append((f"v3fp_{tid}", p))
            n_user_false += 1
        print(f"[v3] user-tagged FALSE high-conf tiles added as negatives: {n_user_false}")

    print()
    print(f"[v3] total positive sources: {len(pos_paths)}")
    print(f"[v3] total negative sources: {len(neg_paths)}")

    # Aug budget: same as v2
    POS_AUG = 4
    NEG_AUG = 4

    print(f"[v3] aug: pos {POS_AUG}/src, neg {NEG_AUG}/src")
    rows = []
    for src, path in pos_paths:
        try:
            img = Image.open(path).convert("RGB")
        except Exception as exc:
            print(f"  pos load fail {path}: {exc}")
            continue
        rows.append((img.copy(), 1, src))
        for aug_img in augment(img, POS_AUG):
            rows.append((aug_img, 1, src))

    for src, path in neg_paths:
        try:
            img = Image.open(path).convert("RGB")
        except Exception as exc:
            print(f"  neg load fail {path}: {exc}")
            continue
        rows.append((img.copy(), 0, src))
        for aug_img in augment(img, NEG_AUG):
            rows.append((aug_img, 0, src))

    n_pos = sum(1 for r in rows if r[1] == 1)
    n_neg = sum(1 for r in rows if r[1] == 0)
    print(f"[v3] total rows: {len(rows)} (pos={n_pos} neg={n_neg})")

    processor, model = load_clip()
    imgs = [r[0] for r in rows]
    print(f"[v3] embedding {len(imgs)} tiles...")
    X = embed(processor, model, imgs, batch_size=8)
    y = np.array([r[1] for r in rows], dtype=np.int8)
    src = np.array([r[2] for r in rows])

    np.savez_compressed(OUT, X=X, y=y, src=src)
    print(f"[v3] wrote {OUT}: X.shape={X.shape}")

    manifest = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_pos_sources": len(pos_paths),
        "n_neg_sources": len(neg_paths),
        "n_rows_pos": n_pos,
        "n_rows_neg": n_neg,
        "promoted_rnegs": sorted(KNOWN_FN_RNEGS),
        "dropped_cases": sorted(NOISY_CASES),
        "user_tagged_true": n_user_true,
        "user_tagged_false": n_user_false,
        "encoder": "openai/clip-vit-large-patch14",
        "feature_dim": int(X.shape[1]),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2))
    print(f"[v3] manifest -> {MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
