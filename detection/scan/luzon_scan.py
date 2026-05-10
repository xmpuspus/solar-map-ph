"""Nationwide-grade streaming scanner.

Same pipeline as detection/scan/ncr_scan.py with two changes:

  1. Tiles are NOT cached to disk. The Esri JPG bytes are read into memory,
     handed to PIL+CLIP, scored, and discarded. ncr_scan caches every tile
     at ~120 KB each; at Luzon (~1.15 M pre-filtered tiles) the cache would
     be ~140 GB, and at the full PH scale (~2-3 M tiles) it would exceed
     350 GB. Streaming keeps disk usage flat at the JSONL output (~50 MB).

  2. ESA WorldCover 2021 v200 (class 50 = built-up) is used as a pre-filter.
     Centers whose 240m sample window contains less than --builtup-threshold
     (default 5%) built-up pixels are skipped before fetch.

The only on-disk artifact is the JSONL output stream and a .skipped.jsonl
sidecar listing the skipped centers (so we can audit recall on the prefilter).

Output format matches ncr_scan exactly: one JSON object per line with
tile_id, lat, lon, fetch_ok, score (when fetch_ok=True). Resumable via the
same _load_done() pattern.

Usage:

  # smoke test on a small bbox
  python3 detection/scan/luzon_scan.py \\
    --bbox 14.20,120.88,14.85,121.22 \\
    --results-jsonl detection/scan/luzon_smoke.jsonl \\
    --limit 200

  # full Luzon scan (default bbox)
  python3 detection/scan/luzon_scan.py \\
    --results-jsonl detection/scan/luzon_scan_results.jsonl

The CLI matches ncr_scan where possible; --reuse-tiles is intentionally
unsupported (no tile cache).
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import joblib
import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIR = ROOT / "detection" / "scan"
DEFAULT_RESULTS = SCAN_DIR / "luzon_scan_results.jsonl"
CLF_DEFAULT = ROOT / "detection" / "train" / "clf_v4.joblib"

# Reuse the same constants as ncr_scan so tile_ids line up.
ESRI_BASE = (
    "https://services.arcgisonline.com/arcgis/rest/services/"
    "World_Imagery/MapServer/export"
)
TILE_PX = 600
HALF_DEGREE = 0.0011  # ~120m at lat 14.6, gives 240m view
USER_AGENT = "ghost-watts/2.0 (luzon-scan; +https://github.com/xmpuspus/ghost-watts)"

TILE_DEG_LAT = 0.00216
TILE_DEG_LON = 0.00224

# Default bbox: rough Luzon mainland bounds. Excludes Mindoro (islands south)
# and the Batanes group (north). For full PH coverage, point --bbox at a
# wider rectangle and run multiple passes per island group.
LUZON_BBOX = (12.30, 119.70, 18.65, 124.30)

DEVICE = (
    "mps" if torch.backends.mps.is_available()
    else "cuda" if torch.cuda.is_available()
    else "cpu"
)


def grid_centers(bbox: tuple[float, float, float, float]) -> list[tuple[float, float]]:
    s, w, n, e = bbox
    lats = np.arange(s + TILE_DEG_LAT / 2, n, TILE_DEG_LAT)
    lons = np.arange(w + TILE_DEG_LON / 2, e, TILE_DEG_LON)
    out = []
    for la in lats:
        for lo in lons:
            out.append((float(la), float(lo)))
    return out


def fetch_tile_bytes(lon: float, lat: float, max_retries: int = 3) -> bytes | None:
    """Fetch tile JPG bytes from Esri. Returns None on persistent failure."""
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
            return data
        except Exception:
            if attempt < max_retries:
                time.sleep(2 * attempt)
    return None


def _load_done(jsonl_path: Path) -> set[str]:
    if not jsonl_path.exists():
        return set()
    done = set()
    with jsonl_path.open() as f:
        for line in f:
            try:
                done.add(json.loads(line)["tile_id"])
            except Exception:
                continue
    return done


def load_clip():
    from transformers import CLIPModel, CLIPProcessor
    print("[luzon-scan] loading CLIP-ViT-L")
    processor = CLIPProcessor.from_pretrained(
        "openai/clip-vit-large-patch14", use_fast=True
    )
    model = CLIPModel.from_pretrained(
        "openai/clip-vit-large-patch14"
    ).to(DEVICE).eval()
    return processor, model


def embed_batch(processor, model, imgs: list[Image.Image]) -> np.ndarray:
    inputs = processor(images=imgs, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        e = model.get_image_features(**inputs)
    e = e / e.norm(dim=-1, keepdim=True)
    return e.cpu().numpy().astype(np.float32)


# ---- prefilter -----------------------------------------------------------


def _prefilter_centers(
    centers: list[tuple[float, float]], threshold: float
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Return (kept, skipped) by ESA WorldCover built-up fraction. Loads the
    prefilter helper lazily so callers without rasterio installed can still
    run with --no-prefilter."""
    sys.path.insert(0, str(ROOT))
    from detection.scan import built_up_prefilter as bp

    # Group centers by their WorldCover tile so we open each GeoTIFF once
    by_tile: dict[str, list[tuple[float, float]]] = {}
    for lat, lon in centers:
        tlat = math.floor(lat / 3) * 3
        tlon = math.floor(lon / 3) * 3
        name = bp.tile_name(tlat, tlon)
        by_tile.setdefault(name, []).append((lat, lon))

    import rasterio
    kept: list[tuple[float, float]] = []
    skipped: list[tuple[float, float]] = []
    for name, pts in by_tile.items():
        try:
            tif = bp.download_tile(name)
        except Exception as exc:
            print(f"[luzon-scan] prefilter skipped tile {name}: {exc}", file=sys.stderr)
            kept.extend(pts)
            continue
        with rasterio.open(tif) as ds:
            for lat, lon in pts:
                try:
                    frac = bp.built_up_fraction(ds, lat, lon)
                except Exception:
                    frac = 1.0  # be conservative on read errors
                if frac >= threshold:
                    kept.append((lat, lon))
                else:
                    skipped.append((lat, lon))
    return kept, skipped


# ---- main loop -----------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--bbox", type=str,
        help=f"south,west,north,east. Default Luzon mainland: {LUZON_BBOX}",
    )
    ap.add_argument("--limit", type=int, help="Cap on number of tiles (smoke test)")
    ap.add_argument(
        "--clf", type=str, default=str(CLF_DEFAULT),
        help="Classifier joblib (default clf_v4.joblib)",
    )
    ap.add_argument(
        "--results-jsonl", type=str, default=str(DEFAULT_RESULTS),
        help="Streaming JSONL output (resumable)",
    )
    ap.add_argument(
        "--score-floor", type=float, default=0.50,
        help="Only emit JSONL records with score >= this floor. Below-floor "
             "tiles still consume an embed but the output stays compact. "
             "(For Luzon, 0.50 is roughly 1.5%% of tiles -> ~17K rows out of 1.15M scanned.)",
    )
    ap.add_argument(
        "--builtup-threshold", type=float, default=0.05,
        help="ESA WorldCover built-up fraction floor for prefilter (0-1).",
    )
    ap.add_argument(
        "--no-prefilter", action="store_true",
        help="Skip the WorldCover prefilter entirely (run on every grid cell).",
    )
    ap.add_argument(
        "--workers", type=int,
        default=int(os.environ.get("GHOST_WATTS_FETCH_WORKERS", "32")),
        help="Concurrent fetch workers. 32 is the sweet spot against Esri.",
    )
    args = ap.parse_args()

    bbox = tuple(float(x) for x in args.bbox.split(",")) if args.bbox else LUZON_BBOX
    centers_all = grid_centers(bbox)
    print(f"[luzon-scan] grid: {len(centers_all)} cells in bbox={bbox}")

    if args.no_prefilter:
        centers = centers_all
        skipped_prefilter: list[tuple[float, float]] = []
    else:
        print("[luzon-scan] applying WorldCover built-up prefilter "
              f"(threshold={args.builtup_threshold})")
        t0 = time.time()
        centers, skipped_prefilter = _prefilter_centers(centers_all, args.builtup_threshold)
        print(
            f"[luzon-scan] prefilter kept {len(centers)}/{len(centers_all)} "
            f"({100*len(centers)/max(1,len(centers_all)):.1f}%) "
            f"in {time.time()-t0:.0f}s"
        )

    if args.limit:
        centers = centers[: args.limit]
        print(f"[luzon-scan] --limit applied: {len(centers)} cells")

    results_jsonl = Path(args.results_jsonl)
    skipped_jsonl = results_jsonl.with_suffix(results_jsonl.suffix + ".skipped")
    done = _load_done(results_jsonl)
    print(f"[luzon-scan] {len(done)} cells already in JSONL, skipping")

    # Persist prefilter-skipped centers so we can audit recall later.
    if skipped_prefilter and not skipped_jsonl.exists():
        with skipped_jsonl.open("w") as f:
            for lat, lon in skipped_prefilter:
                f.write(json.dumps({
                    "tile_id": f"{lat:.5f}_{lon:.5f}", "lat": lat, "lon": lon,
                    "skipped_reason": "builtup_below_threshold",
                }) + "\n")
        print(f"[luzon-scan] wrote {len(skipped_prefilter)} prefilter skips -> {skipped_jsonl.name}")

    bundle = joblib.load(Path(args.clf))
    clf = bundle["clf"]
    print(
        f"[luzon-scan] loaded classifier: {Path(args.clf).name}  "
        f"encoder={bundle.get('encoder')}  version={bundle.get('version', 'v?')}"
    )
    processor, model = load_clip()

    todo: list[tuple[str, float, float]] = []
    for lat, lon in centers:
        tid = f"{lat:.5f}_{lon:.5f}"
        if tid in done:
            continue
        todo.append((tid, lat, lon))
    print(f"[luzon-scan] todo: {len(todo)}")

    BATCH = 16
    n_ok = n_fail = n_emit = 0
    t_start = time.time()

    def _fetch_one(item: tuple[str, float, float]):
        tid, la, lo = item
        data = fetch_tile_bytes(lo, la)
        if data is None:
            return (tid, la, lo, None)
        try:
            img = Image.open(io.BytesIO(data)).convert("RGB")
        except Exception:
            return (tid, la, lo, None)
        return (tid, la, lo, img)

    with results_jsonl.open("a") as fout:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            batch: list[tuple[str, float, float, Image.Image]] = []
            for tid, la, lo, img in pool.map(_fetch_one, todo):
                if img is None:
                    fout.write(json.dumps({
                        "tile_id": tid, "lat": la, "lon": lo, "fetch_ok": False,
                    }) + "\n")
                    n_fail += 1
                    continue
                batch.append((tid, la, lo, img))
                if len(batch) >= BATCH:
                    imgs = [b[3] for b in batch]
                    X = embed_batch(processor, model, imgs)
                    scores = clf.predict_proba(X)[:, 1]
                    for (t, lat_, lon_, _), sc in zip(batch, scores):
                        sc = float(sc)
                        if sc >= args.score_floor:
                            fout.write(json.dumps({
                                "tile_id": t, "lat": lat_, "lon": lon_,
                                "fetch_ok": True, "score": sc,
                            }) + "\n")
                            n_emit += 1
                    fout.flush()
                    n_ok += len(batch)
                    batch = []
                    if n_ok % 320 == 0:
                        elapsed = time.time() - t_start
                        rate = n_ok / max(1, elapsed)
                        remaining = len(todo) - n_ok - n_fail
                        eta = remaining / max(0.1, rate)
                        print(
                            f"[luzon-scan] {n_ok}/{len(todo)} ok  fail={n_fail}  "
                            f"emit={n_emit}  rate={rate:.1f}/s  ETA={eta/60:.1f}min"
                        )
            if batch:
                imgs = [b[3] for b in batch]
                X = embed_batch(processor, model, imgs)
                scores = clf.predict_proba(X)[:, 1]
                for (t, lat_, lon_, _), sc in zip(batch, scores):
                    sc = float(sc)
                    if sc >= args.score_floor:
                        fout.write(json.dumps({
                            "tile_id": t, "lat": lat_, "lon": lon_,
                            "fetch_ok": True, "score": sc,
                        }) + "\n")
                        n_emit += 1
                fout.flush()
                n_ok += len(batch)

    elapsed = time.time() - t_start
    print(
        f"[luzon-scan] complete: {n_ok} ok, {n_fail} fail, {n_emit} above floor "
        f"in {elapsed/60:.1f}min "
        f"({n_ok/max(1,elapsed):.1f} t/s)"
    )
    print(f"[luzon-scan] results -> {results_jsonl}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
