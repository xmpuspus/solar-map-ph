"""Full NCR scan: tile NCR with a 240m grid, classify each tile, output GeoJSON.

Grid:
  NCR bbox = (14.40, 120.92, 14.78, 121.13)   # ~42km N-S x 22km E-W
  Tile size = 240m view (matches our case-study and OSM tile width)
  Stride   = 240m (no overlap; v1 scan trades recall for speed)
  Total tiles ~ 7,000

Pipeline:
  1. Generate grid of tile centers
  2. For each tile: fetch Esri (cache to disk), embed via CLIP, classify
  3. Stream results to JSONL (resumable)
  4. After scan: aggregate JSONL -> GeoJSON of detections at threshold tiers

Resumability: JSONL is append-only. Script skips tiles already in JSONL.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import joblib
import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIR = ROOT / "detection" / "scan"
TILE_DIR = SCAN_DIR / "ncr_tiles"
TILE_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_JSONL = SCAN_DIR / "ncr_scan_results.jsonl"
GEOJSON_OUT = ROOT / "site" / "public" / "data" / "rooftop_solar_ncr.geojson"
CLF_PATH = ROOT / "detection" / "train" / "clf_v2.joblib"

DEVICE = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
ESRI_BASE = (
    "https://services.arcgisonline.com/arcgis/rest/services/"
    "World_Imagery/MapServer/export"
)
TILE_PX = 600
HALF_DEGREE = 0.0011  # ~120m at lat 14.6, gives 240m view
USER_AGENT = "ghost-watts/2.0 (ncr-scan; +https://github.com/xmpuspus/ghost-watts)"

# NCR extent
NCR_BBOX = (14.40, 120.92, 14.78, 121.13)
TILE_DEG_LAT = 0.00216  # ~240m at lat 14.6
TILE_DEG_LON = 0.00224  # ~240m at lat 14.6 (cos(14.6)=0.97)


def grid_centers(bbox: tuple[float, float, float, float]) -> list[tuple[float, float]]:
    """Yield (lat, lon) centers tiling the bbox at 240m stride."""
    s, w, n, e = bbox
    lats = np.arange(s + TILE_DEG_LAT / 2, n, TILE_DEG_LAT)
    lons = np.arange(w + TILE_DEG_LON / 2, e, TILE_DEG_LON)
    out = []
    for la in lats:
        for lo in lons:
            out.append((float(la), float(lo)))
    return out


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
            if attempt < max_retries:
                time.sleep(2 * attempt)
    return False


def _load_done(jsonl_path: Path) -> set[str]:
    """Load tile_ids already classified from a given JSONL (for resume)."""
    if not jsonl_path.exists():
        return set()
    done = set()
    with jsonl_path.open() as f:
        for line in f:
            try:
                rec = json.loads(line)
                done.add(rec["tile_id"])
            except Exception:
                continue
    return done


def load_already_done() -> set[str]:
    """Back-compat: default JSONL."""
    return _load_done(RESULTS_JSONL)


def load_clip():
    from transformers import CLIPModel, CLIPProcessor
    print("[scan] loading CLIP-ViT-L")
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14", use_fast=True)
    model = CLIPModel.from_pretrained("openai/clip-vit-large-patch14").to(DEVICE).eval()
    return processor, model


def embed_batch(processor, model, imgs: list[Image.Image]) -> np.ndarray:
    inputs = processor(images=imgs, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        e = model.get_image_features(**inputs)
    e = e / e.norm(dim=-1, keepdim=True)
    return e.cpu().numpy().astype(np.float32)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="Cap on number of tiles (for testing)")
    ap.add_argument("--bbox", type=str, help="Override bbox: 'south,west,north,east'")
    ap.add_argument("--no-aggregate", action="store_true", help="Skip GeoJSON aggregation")
    ap.add_argument(
        "--clf",
        type=str,
        default=str(CLF_PATH),
        help="Classifier joblib (default: clf_v2.joblib). Use clf_v3.joblib to re-classify with v3.",
    )
    ap.add_argument(
        "--reuse-tiles",
        action="store_true",
        help="Skip fetch entirely; only re-classify already-cached jpgs in ncr_tiles/. "
             "Resets JSONL output (results-only re-classification, ~3min not 13).",
    )
    ap.add_argument(
        "--results-jsonl",
        type=str,
        default=str(RESULTS_JSONL),
        help="JSONL output path (default ncr_scan_results.jsonl). Use a v3-tagged path "
             "to keep v2 results around for delta comparison.",
    )
    args = ap.parse_args()

    bbox = NCR_BBOX
    if args.bbox:
        bbox = tuple(float(x) for x in args.bbox.split(","))
    centers = grid_centers(bbox)
    print(f"[scan] grid: {len(centers)} tile centers in bbox={bbox}")
    if args.limit:
        centers = centers[: args.limit]

    results_jsonl = Path(args.results_jsonl)

    if args.reuse_tiles:
        # Reset JSONL so we re-classify everything; cached JPGs stay
        if results_jsonl.exists():
            backup = results_jsonl.with_suffix(results_jsonl.suffix + ".bak")
            results_jsonl.rename(backup)
            print(f"[scan] reuse-tiles: moved old JSONL to {backup}")
        done: set[str] = set()
    else:
        done = _load_done(results_jsonl)
        print(f"[scan] {len(done)} tiles already classified, will skip")

    clf_path = Path(args.clf)
    bundle = joblib.load(clf_path)
    clf = bundle["clf"]
    print(f"[scan] loaded classifier: {clf_path.name}  encoder={bundle.get('encoder')}  version={bundle.get('version', 'v2')}")
    processor, model = load_clip()

    BATCH = 16
    # Bumped from 12 → 32 for the Meralco-franchise scan; Esri serves at ~1.8s/req
    # round-trip from this Mac, so 32-way parallelism gives ~17 fetches/sec ceiling
    # which is closer to the ~14 t/s embed throughput.
    FETCH_WORKERS = int(os.environ.get("GHOST_WATTS_FETCH_WORKERS", "32"))

    todo: list[tuple[str, float, float, Path]] = []
    for lat, lon in centers:
        tile_id = f"{lat:.5f}_{lon:.5f}"
        if tile_id in done:
            continue
        tile_path = TILE_DIR / f"{tile_id}.jpg"
        if args.reuse_tiles and not (tile_path.exists() and tile_path.stat().st_size > 1000):
            # In reuse mode, skip tiles that don't have cached JPGs
            continue
        todo.append((tile_id, lat, lon, tile_path))
    n_skipped = len(centers) - len(todo)
    print(f"[scan] todo: {len(todo)}  skipping: {n_skipped}")

    n_ok = 0
    n_fail = 0
    t_start = time.time()

    def _fetch_one(item: tuple[str, float, float, Path]) -> tuple[str, float, float, Path, bool]:
        tid, la, lo, p = item
        if args.reuse_tiles:
            # No network: trust cached JPG presence
            return (tid, la, lo, p, p.exists() and p.stat().st_size > 1000)
        ok = fetch_tile(lo, la, p)
        return (tid, la, lo, p, ok)

    with results_jsonl.open("a") as fjsonl:
        # Fetch with thread pool, embed serially (MPS doesn't parallelize well across processes)
        with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
            futures_iter = pool.map(_fetch_one, todo)
            batch: list[tuple[str, float, float, Path]] = []
            for fut_result in futures_iter:
                tid, la, lo, p, ok = fut_result
                if not ok:
                    fjsonl.write(json.dumps({"tile_id": tid, "lat": la, "lon": lo, "fetch_ok": False}) + "\n")
                    n_fail += 1
                    continue
                batch.append((tid, la, lo, p))
                if len(batch) >= BATCH:
                    imgs = [Image.open(it[3]).convert("RGB") for it in batch]
                    X = embed_batch(processor, model, imgs)
                    scores = clf.predict_proba(X)[:, 1]
                    for (t, lat_, lon_, _), sc in zip(batch, scores):
                        fjsonl.write(json.dumps({
                            "tile_id": t, "lat": lat_, "lon": lon_, "fetch_ok": True,
                            "score": float(sc),
                        }) + "\n")
                    fjsonl.flush()
                    n_ok += len(batch)
                    batch = []
                    if n_ok % 160 == 0:
                        elapsed = time.time() - t_start
                        rate = n_ok / max(1, elapsed)
                        remaining = len(todo) - n_ok - n_fail
                        eta = remaining / max(0.1, rate)
                        print(f"[scan] {n_ok}/{len(todo)} ok  fail={n_fail}  rate={rate:.1f}/s  ETA={eta/60:.1f}min")
            # flush remainder
            if batch:
                imgs = [Image.open(it[3]).convert("RGB") for it in batch]
                X = embed_batch(processor, model, imgs)
                scores = clf.predict_proba(X)[:, 1]
                for (t, lat_, lon_, _), sc in zip(batch, scores):
                    fjsonl.write(json.dumps({
                        "tile_id": t, "lat": lat_, "lon": lon_, "fetch_ok": True,
                        "score": float(sc),
                    }) + "\n")
                fjsonl.flush()
                n_ok += len(batch)

    elapsed = time.time() - t_start
    print(f"[scan] complete: {n_ok} new ({n_fail} fail) in {elapsed:.0f}s ({n_skipped} skipped)")

    if not args.no_aggregate:
        aggregate_to_geojson(results_jsonl, clf_label=clf_path.name)
        # Run OSM cross-match if both inputs are available
        try:
            import subprocess
            subprocess.run([sys.executable, str(ROOT / "detection" / "scan" / "match_against_osm.py")], check=False)
            subprocess.run([sys.executable, str(ROOT / "detection" / "scan" / "build_detection_sheet.py")], check=False)
        except Exception as exc:
            print(f"[scan] post-aggregation steps failed: {exc}", file=sys.stderr)
    return 0


def aggregate_to_geojson(results_jsonl: Path = RESULTS_JSONL, clf_label: str = "clf_v2.joblib") -> None:
    """Read JSONL and write GeoJSON of detections at tiered thresholds."""
    HIGH = 0.85
    CAND = 0.70
    HALF = HALF_DEGREE
    feats: list[dict] = []
    n_high = n_cand = n_total = 0
    with results_jsonl.open() as f:
        for line in f:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if not rec.get("fetch_ok"):
                continue
            score = rec.get("score")
            if score is None:
                continue
            n_total += 1
            tier = None
            if score >= HIGH:
                tier = "high"
                n_high += 1
            elif score >= CAND:
                tier = "candidate"
                n_cand += 1
            else:
                continue
            feats.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [rec["lon"], rec["lat"]]},
                "properties": {
                    "tile_id": rec["tile_id"],
                    "score": round(float(score), 3),
                    "tier": tier,
                    "tile_bbox": [rec["lon"] - HALF, rec["lat"] - HALF, rec["lon"] + HALF, rec["lat"] + HALF],
                },
            })
    fc = {
        "type": "FeatureCollection",
        "features": feats,
        "_meta": {
            "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "scan_grid": "240m no-overlap",
            "total_tiles_scanned": n_total,
            "n_high_confidence": n_high,
            "n_candidate": n_cand,
            "thresholds": {"high": HIGH, "candidate": CAND},
            "encoder": "openai/clip-vit-large-patch14",
            "classifier": clf_label,
            "training_set": "see classifier-version manifest",
        },
    }
    GEOJSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    GEOJSON_OUT.write_text(json.dumps(fc, indent=1))
    print(f"[scan] geojson: {GEOJSON_OUT} ({n_high} high + {n_cand} candidate of {n_total} scanned)")


if __name__ == "__main__":
    sys.exit(main())
