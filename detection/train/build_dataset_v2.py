"""V2 training dataset: OSM-bootstrapped positives + GT negatives + random NCR negatives.

Improvements over v1:
  - Positives expanded from 9 sources to ~200-300 unique OSM-tagged rooftop solar
    locations (deduped by ~10m clustering)
  - Negatives expanded by sampling random NCR coordinates (likely no solar)
  - Heavier per-source augmentation budget when positives are uneven density
  - Embeds with CLIP-ViT-L (768-dim)

Outputs:
  detection/train/dataset_v2.npz
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import torch
from PIL import Image, ImageEnhance

ROOT = Path(__file__).resolve().parents[2]
OSM_TILES = ROOT / "detection" / "bootstrap" / "tiles"
OSM_INDEX = OSM_TILES / "index.json"
GT_TILES = ROOT / "docs" / "groundtruth" / "tiles"
LABELS = ROOT / "docs" / "groundtruth" / "labels.json"
RANDOM_NEG_DIR = ROOT / "detection" / "train" / "random_neg_tiles"
RANDOM_NEG_DIR.mkdir(parents=True, exist_ok=True)
OUT = ROOT / "detection" / "train" / "dataset_v2.npz"

DEVICE = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
SEED = 42
random.seed(SEED)
np.random.seed(SEED)

ESRI_BASE = "https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/export"
TILE_PX = 600
HALF_DEGREE = 0.0011  # ~120m at lat 14.6, gives a ~240m view
USER_AGENT = "solar-map-ph/2.0 (random-neg-tiles; +https://github.com/xmpuspus/solar-map-ph)"

# NCR bounding box (rough)
NCR_BBOX = (14.4, 120.92, 14.78, 121.13)


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
            print(f"  fail {lon:.5f},{lat:.5f}: {exc}", file=sys.stderr)
            if attempt < max_retries:
                time.sleep(2 * attempt)
    return False


def dedupe_by_grid(items: list[dict], precision: int = 4) -> list[dict]:
    """Drop items that hash to the same lat/lon at given precision."""
    seen = set()
    out = []
    for it in items:
        key = (round(it["lat"], precision), round(it["lon"], precision))
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def fetch_random_negatives(n: int) -> list[Path]:
    """Sample random points within NCR bbox and fetch tiles. Most won't have solar."""
    rng = random.Random(SEED)
    paths = []
    last_t = 0.0
    rate_limit_s = 1.0 / 5
    i = 0
    while len(paths) < n:
        lat = rng.uniform(NCR_BBOX[0], NCR_BBOX[2])
        lon = rng.uniform(NCR_BBOX[1], NCR_BBOX[3])
        out_path = RANDOM_NEG_DIR / f"rneg_{i:04d}.jpg"
        wait = rate_limit_s - (time.time() - last_t)
        if wait > 0:
            time.sleep(wait)
        last_t = time.time()
        ok = fetch_tile(lon, lat, out_path)
        if ok:
            paths.append(out_path)
            if len(paths) % 25 == 0:
                print(f"[neg] fetched {len(paths)}/{n}")
        i += 1
        if i > n * 3:
            break
    return paths


def augment(img: Image.Image, n: int) -> list[Image.Image]:
    """Return n augmented copies (rotation, flip, mild brightness/color jitter)."""
    rng = random.Random(SEED + hash(img.tobytes()) % 10000)
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

    print("[v2] loading openai/clip-vit-large-patch14")
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14", use_fast=True)
    model = CLIPModel.from_pretrained("openai/clip-vit-large-patch14").to(DEVICE).eval()
    return processor, model


def embed(processor, model, imgs: list[Image.Image], batch_size: int = 8) -> np.ndarray:
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
    # POSITIVES: OSM-tagged rooftop solar, deduped to ~10m grid
    osm_index = json.loads(OSM_INDEX.read_text())
    osm_index = [it for it in osm_index if it.get("fetch_ok")]
    print(f"[v2] OSM tiles fetched: {len(osm_index)}")
    osm_dedup = dedupe_by_grid(osm_index, precision=4)  # ~10m clusters
    print(f"[v2] OSM tiles after 10m dedup: {len(osm_dedup)}")

    pos_paths: list[tuple[str, Path]] = []
    for it in osm_dedup:
        tile = OSM_TILES / f"{it['idx']:04d}.jpg"
        if tile.exists():
            pos_paths.append((f"osm_{it['idx']:04d}", tile))
    # Add the 6 case studies as additional positives
    cases_dir = ROOT / "site" / "public" / "case_studies"
    for p in sorted(cases_dir.glob("*.jpg")):
        pos_paths.append((f"case_{p.stem}", p))
    print(f"[v2] total positive sources: {len(pos_paths)}")

    # NEGATIVES: GT not_solar (~46) + sample random NCR tiles (target 200 total)
    neg_paths: list[tuple[str, Path]] = []
    with LABELS.open() as f:
        labels = json.load(f)["labels"]
    for it in labels:
        if it.get("label") == "not_solar":
            tiles = list(GT_TILES.glob(f"{it['idx']}_*.jpg"))
            if tiles:
                neg_paths.append((f"gt_{it['idx']}", tiles[0]))

    n_random_neg = max(0, 200 - len(neg_paths))
    if n_random_neg > 0:
        print(f"[v2] fetching {n_random_neg} random NCR negative tiles")
        rand_paths = fetch_random_negatives(n_random_neg)
        for p in rand_paths:
            neg_paths.append((f"rneg_{p.stem}", p))
    print(f"[v2] total negative sources: {len(neg_paths)}")

    # Aug budget: positives get fewer aug copies because we now have many sources
    POS_AUG = 4  # per source -> ~200*5 = 1000 positive rows
    NEG_AUG = 4  # per source -> ~200*5 = 1000 negative rows

    print(f"[v2] aug: pos {POS_AUG}/src, neg {NEG_AUG}/src")
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
    print(f"[v2] total rows: {len(rows)} (pos={n_pos} neg={n_neg})")

    processor, model = load_clip()
    imgs = [r[0] for r in rows]
    print(f"[v2] embedding {len(imgs)} tiles...")
    X = embed(processor, model, imgs, batch_size=8)
    y = np.array([r[1] for r in rows], dtype=np.int8)
    src = np.array([r[2] for r in rows])

    np.savez_compressed(OUT, X=X, y=y, src=src)
    print(f"[v2] wrote {OUT}: X.shape={X.shape}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
