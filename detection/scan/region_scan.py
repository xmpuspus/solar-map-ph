"""Region-aware classifier scan for SolarMap.PH v1.1+ multi-region expansion.

Wraps the primitives in ncr_scan.py (grid_centers, fetch_tile, load_clip,
embed_batch) but takes a --region slug that reads bbox + output paths from
pipeline/regions/regions.json. Pre-filters tiles by ESA WorldCover
built-up fraction before fetching, so we don't burn Esri quota on ocean
and forest cells.

Pipeline per region:
    1. Load region config (bbox, slug)
    2. ESA WorldCover prefilter: keep only cells with built_up_fraction >= threshold
    3. Fetch each kept tile from Esri, cache to detection/scan/tiles/<slug>/
    4. CLIP embed + LR score, append to detection/scan/<slug>_scan_results.jsonl
    5. Resumable: skip already-scored tiles on restart

Run:
    python detection/scan/region_scan.py --region cebu --clf detection/train/clf_v4.joblib
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np

# Make sibling modules importable regardless of cwd
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIR = ROOT / "detection" / "scan"
REGIONS_JSON = ROOT / "pipeline" / "regions" / "regions.json"

ESRI_BASE = "https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/export"
# NCR's scanner uses 600 px because Esri's World Imagery has full coverage at
# that pixel density across Metro Manila. The v1.1 cross-domain regions
# (Iloilo, Legazpi, Calabarzon) return HTTP 500 at 600 px because their
# underlying imagery layer has a lower max zoom. 400 px works for every
# Philippine region we ship and still gives CLIP-ViT-L/14 plenty of detail
# (it downsamples to 224 internally). Override via env if needed.
TILE_PX = int(os.environ.get("SOLAR_MAP_PH_TILE_PX", "400"))
HALF_DEGREE = 0.0011  # ~120m at lat 10-14, gives 240m view
USER_AGENT = "solar-map-ph/1.1 (region-scan; +https://github.com/xmpuspus/solar-map-ph)"

# Same stride as ncr_scan.py
TILE_DEG_LAT = 0.00216
TILE_DEG_LON = 0.00224


def load_region(slug: str) -> dict:
    with REGIONS_JSON.open() as f:
        cfg = json.load(f)
    for r in cfg["regions"]:
        if r["slug"] == slug:
            return r
    raise SystemExit(f"region not found: {slug}. available: {[r['slug'] for r in cfg['regions']]}")


def grid_centers(bbox: tuple[float, float, float, float]) -> list[tuple[float, float]]:
    """Yield (lat, lon) tile centers tiling the bbox at 240m stride.

    bbox is [min_lat, min_lon, max_lat, max_lon].
    """
    s, w, n, e = bbox
    lats = np.arange(s + TILE_DEG_LAT / 2, n, TILE_DEG_LAT)
    lons = np.arange(w + TILE_DEG_LON / 2, e, TILE_DEG_LON)
    return [(float(la), float(lo)) for la in lats for lo in lons]


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
        except Exception:
            if attempt < max_retries:
                time.sleep(2 * attempt)
    return False


def load_done(jsonl_path: Path) -> set[str]:
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", required=True, help="region slug from regions.json")
    ap.add_argument("--clf", default=str(ROOT / "detection" / "train" / "clf_v4.joblib"))
    ap.add_argument("--limit", type=int, help="cap on tiles (for smoke testing)")
    ap.add_argument("--built-up-threshold", type=float, default=0.05,
                    help="min built-up fraction per tile (default 0.05 = 5%%)")
    ap.add_argument("--skip-prefilter", action="store_true",
                    help="scan all tiles in bbox (slow, lots of ocean)")
    args = ap.parse_args()

    region = load_region(args.region)
    print(f"[region-scan] region={region['slug']} bbox={region['bbox']}")

    tile_dir = SCAN_DIR / "tiles" / region["slug"]
    tile_dir.mkdir(parents=True, exist_ok=True)
    results_jsonl = SCAN_DIR / f"{region['slug']}_scan_results.jsonl"

    s, w, n, ee = region["bbox"]
    centers = grid_centers((s, w, n, ee))
    print(f"[region-scan] {len(centers)} grid centers in bbox")
    if args.limit:
        centers = centers[: args.limit]

    # Pre-filter by built-up fraction (skip ocean / forest)
    if not args.skip_prefilter:
        try:
            import rasterio  # noqa: F401
            from built_up_prefilter import built_up_fraction, download_tile, tiles_covering_bbox
        except ImportError as e:
            print(f"[region-scan] WARN: built_up_prefilter unavailable ({e}), scanning all tiles")
            args.skip_prefilter = True

    if not args.skip_prefilter:
        prefilter_path = SCAN_DIR / f"prefilter_{region['slug']}.json"
        if prefilter_path.exists():
            print(f"[region-scan] loading cached prefilter from {prefilter_path.name}")
            prefilter = json.loads(prefilter_path.read_text())
        else:
            print(f"[region-scan] computing built-up prefilter (threshold {args.built_up_threshold})")
            wc_tiles = tiles_covering_bbox(s, w, n, ee)
            print(f"[region-scan] WorldCover tiles needed: {wc_tiles}")
            paths = [download_tile(t) for t in wc_tiles]
            datasets = [rasterio.open(p) for p in paths]
            prefilter = {}
            for i, (la, lo) in enumerate(centers):
                # Try each WorldCover tile until one covers this point
                frac = 0.0
                for ds in datasets:
                    try:
                        frac = built_up_fraction(ds, la, lo)
                        if frac > 0:
                            break
                    except Exception:
                        continue
                tile_id = f"{la:.5f}_{lo:.5f}"
                prefilter[tile_id] = round(frac, 4)
                if (i + 1) % 1000 == 0:
                    kept = sum(1 for v in prefilter.values() if v >= args.built_up_threshold)
                    print(f"  prefilter {i + 1}/{len(centers)}  built-up kept so far: {kept}")
            prefilter_path.write_text(json.dumps(prefilter))
            print(f"[region-scan] prefilter saved: {prefilter_path.name}")

        kept_centers = [(la, lo) for (la, lo) in centers
                        if prefilter.get(f"{la:.5f}_{lo:.5f}", 0.0) >= args.built_up_threshold]
        print(f"[region-scan] after prefilter: {len(kept_centers)} of {len(centers)} centers kept "
              f"({100 * len(kept_centers) / max(1, len(centers)):.1f}%)")
        centers = kept_centers

    done = load_done(results_jsonl)
    print(f"[region-scan] {len(done)} tiles already scored, will skip")

    # Load classifier + CLIP
    import joblib  # noqa: E402
    from PIL import Image  # noqa: E402

    bundle = joblib.load(args.clf)
    clf = bundle["clf"]
    print(f"[region-scan] classifier: {Path(args.clf).name}  encoder={bundle.get('encoder')}")

    from ncr_scan import embed_batch, load_clip  # noqa: E402
    processor, model = load_clip()

    todo = []
    for la, lo in centers:
        tile_id = f"{la:.5f}_{lo:.5f}"
        if tile_id in done:
            continue
        tile_path = tile_dir / f"{tile_id}.jpg"
        todo.append((tile_id, la, lo, tile_path))
    print(f"[region-scan] todo: {len(todo)}")

    FETCH_WORKERS = int(os.environ.get("SOLAR_MAP_PH_FETCH_WORKERS", "16"))
    BATCH = 16
    n_ok = 0
    n_fail = 0
    t_start = time.time()

    def _fetch(item):
        tid, la, lo, p = item
        return (tid, la, lo, p, fetch_tile(lo, la, p))

    with results_jsonl.open("a") as fjsonl:
        with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
            batch = []
            for tid, la, lo, p, ok in pool.map(_fetch, todo):
                if not ok:
                    fjsonl.write(json.dumps({
                        "tile_id": tid, "lat": la, "lon": lo, "fetch_ok": False,
                        "error": "fetch_failed", "region": region["slug"],
                    }) + "\n")
                    n_fail += 1
                    continue
                batch.append((tid, la, lo, p))
                if len(batch) >= BATCH:
                    imgs = [Image.open(it[3]).convert("RGB") for it in batch]
                    X = embed_batch(processor, model, imgs)
                    scores = clf.predict_proba(X)[:, 1]
                    for (t, la_, lo_, _), sc in zip(batch, scores):
                        fjsonl.write(json.dumps({
                            "tile_id": t, "lat": la_, "lon": lo_, "fetch_ok": True,
                            "score": float(sc), "region": region["slug"],
                        }) + "\n")
                    fjsonl.flush()
                    os.fsync(fjsonl.fileno())
                    n_ok += len(batch)
                    batch = []
                    if n_ok % 160 == 0:
                        elapsed = time.time() - t_start
                        rate = n_ok / max(1, elapsed)
                        eta = (len(todo) - n_ok - n_fail) / max(0.1, rate)
                        print(f"[region-scan] {n_ok}/{len(todo)} ok  fail={n_fail}  "
                              f"rate={rate:.1f}/s  ETA={eta / 60:.1f}min")
            if batch:
                imgs = [Image.open(it[3]).convert("RGB") for it in batch]
                X = embed_batch(processor, model, imgs)
                scores = clf.predict_proba(X)[:, 1]
                for (t, la_, lo_, _), sc in zip(batch, scores):
                    fjsonl.write(json.dumps({
                        "tile_id": t, "lat": la_, "lon": lo_, "fetch_ok": True,
                        "score": float(sc), "region": region["slug"],
                    }) + "\n")
                n_ok += len(batch)

    elapsed = time.time() - t_start
    print(f"[region-scan] DONE region={region['slug']}: {n_ok} scored, {n_fail} failed, "
          f"{elapsed / 60:.1f} min, output={results_jsonl.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
