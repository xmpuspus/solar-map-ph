"""Step 4a of v1.2: build dataset_v5.npz = dataset_v4 + region-stratified
additions (scan-realistic positives + targeted hard negatives).

This is the network/embedding stage. train_v5.py then trains clf_v5
deterministically from the cached dataset_v5.npz (no network), preserving the
canonical-hash discipline.

Additions:
  positives  regpos_<region>_NNNN  spot-check `rooftop` tiles (exact cached
             scan JPEGs) + OSM roof-tagged solar in the region bbox
  hard-neg   regfp_<region>_NNNN   spot-check ground_mount + blue_roof_fp
                                   (the dominant cross-domain FP classes)
  hard-neg   regground_<region>_NNNN  OSM ground-mount / utility solar farms
                                   (location!=roof, or power=plant/plant:source
                                   =solar) -> the ground-mount FP class the
                                   README mount-type head targets

Tile resolution is network-free wherever possible: each (lat,lon) snaps to the
nearest cached scan tile in detection/scan/tiles/<region>/ within SNAP_M. The
region scan already fetched every built-up tile, and OSM rooftops sit on
buildings (built-up), so almost all resolve from cache. Only unresolved points
fall back to a capped Esri fetch via region_scan.fetch_tile.

A parallel `tile` array (tile_id for region rows, "" for inherited v4 rows) is
stored so train_v5.py can exclude the step-3 per-region holdout tiles.

Run:
    python detection/train/build_dataset_v5.py
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATASET_V4 = ROOT / "detection" / "train" / "dataset_v4.npz"
DATASET_V5 = ROOT / "detection" / "train" / "dataset_v5.npz"
MANIFEST_V5 = ROOT / "detection" / "train" / "dataset_v5_manifest.json"
REGIONS_JSON = ROOT / "pipeline" / "regions" / "regions.json"
LABELS = ROOT / "detection" / "train" / "region_labels.jsonl"
OSM_DIR = ROOT / "detection" / "bootstrap"
SCAN_DIR = ROOT / "detection" / "scan"
TILES_DIR = SCAN_DIR / "tiles"

SNAP_M = 170.0  # scan grid is 240 m; within ~170 m a cached tile always exists
MAX_FETCH = 60  # cap network fallback fetches (Esri throttle guard)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def index_cached_tiles(slug: str) -> list[tuple[float, float, Path]]:
    d = TILES_DIR / slug
    out = []
    if not d.exists():
        return out
    for p in d.iterdir():
        if p.suffix != ".jpg" or p.stat().st_size <= 1000:
            continue
        try:
            la, lo = p.stem.split("_")
            out.append((float(la), float(lo), p))
        except ValueError:
            continue
    out.sort(key=lambda r: (r[0], r[1]))  # deterministic snap -> reproducible hash
    return out


def snap_to_cached(lat: float, lon: float, cache: list[tuple[float, float, Path]]) -> Path | None:
    best = (float("inf"), None)
    for la, lo, p in cache:
        # Cheap bbox reject before haversine.
        if abs(la - lat) > 0.003 or abs(lo - lon) > 0.003:
            continue
        d = haversine_m(lat, lon, la, lo)
        if d < best[0]:
            best = (d, p)
    return best[1] if best[0] <= SNAP_M else None


def collect_region_rows() -> dict:
    spot = [json.loads(x) for x in LABELS.read_text().splitlines() if x.strip()]
    cfg = json.loads(REGIONS_JSON.read_text())
    slugs = [r["slug"] for r in cfg["regions"]]

    rows = []  # (label_int, src_tag, tile_id, region, path) ; path resolved later
    fetch_jobs = []  # (lat, lon, region, slug) to fetch if not snappable

    for slug in slugs:
        cache = index_cached_tiles(slug)
        pi = ni = gi = 0

        def add(lat, lon, label, kind):
            nonlocal pi, ni, gi
            p = snap_to_cached(lat, lon, cache)
            if label == 1:
                tag = f"regpos_{slug}_{pi:04d}"
                pi += 1
            elif kind == "fp":
                tag = f"regfp_{slug}_{ni:04d}"
                ni += 1
            else:
                tag = f"regground_{slug}_{gi:04d}"
                gi += 1
            tid = f"{lat:.5f}_{lon:.5f}"
            if p is not None:
                rows.append((label, tag, tid, slug, p))
            else:
                fetch_jobs.append((lat, lon, slug, label, tag, tid))

        # spot-check verdicts
        for r in spot:
            if r["region"] != slug:
                continue
            if r["label"] == "rooftop":
                add(r["lat"], r["lon"], 1, "pos")
            elif r["label"] in ("ground_mount", "blue_roof_fp"):
                add(r["lat"], r["lon"], 0, "fp")

        # OSM solar in region
        osm = OSM_DIR / f"osm_solar_{slug}.geojson"
        if osm.exists():
            fc = json.loads(osm.read_text())
            for f in fc.get("features", []):
                lon, lat = f["geometry"]["coordinates"]
                pr = f["properties"]
                loc = pr.get("location")
                tags = pr.get("all_tags") or {}
                is_ground = (
                    loc == "ground"
                    or tags.get("power") == "plant"
                    or tags.get("plant:source") == "solar"
                )
                if loc == "roof":
                    add(lat, lon, 1, "pos")
                elif is_ground:
                    add(lat, lon, 0, "ground")
                # location unspecified & not clearly ground: skip (ambiguous)

    return {"rows": rows, "fetch_jobs": fetch_jobs, "slugs": slugs}


def main() -> int:
    if not DATASET_V4.exists() or not LABELS.exists():
        print("[v5-build] missing dataset_v4.npz or region_labels.jsonl", file=sys.stderr)
        return 1

    t0 = time.time()
    coll = collect_region_rows()
    rows, fetch_jobs = coll["rows"], coll["fetch_jobs"]
    print(f"[v5-build] snapped {len(rows)} region tiles from cache; "
          f"{len(fetch_jobs)} need network fallback (cap {MAX_FETCH})")

    sys.path.insert(0, str(SCAN_DIR))
    from ncr_scan import embed_batch, load_clip
    from region_scan import fetch_tile

    # Network fallback (capped).
    n_fetched = 0
    for lat, lon, slug, label, tag, tid in fetch_jobs:
        if n_fetched >= MAX_FETCH:
            break
        out = TILES_DIR / slug / f"{tid}.jpg"
        if fetch_tile(lon, lat, out):
            rows.append((label, tag, tid, slug, out))
            n_fetched += 1
    print(f"[v5-build] fetched {n_fetched} fallback tiles")

    # Embed.
    from PIL import Image

    processor, model = load_clip()
    X_new, y_new, src_new, tile_new = [], [], [], []
    batch_imgs, batch_meta = [], []

    def flush():
        if not batch_imgs:
            return
        emb = embed_batch(processor, model, batch_imgs)
        for e, (lab, tag, tid) in zip(emb, batch_meta):
            X_new.append(e)
            y_new.append(lab)
            src_new.append(tag)
            tile_new.append(tid)
        batch_imgs.clear()
        batch_meta.clear()

    for label, tag, tid, slug, path in rows:
        try:
            batch_imgs.append(Image.open(path).convert("RGB"))
        except Exception:
            continue
        batch_meta.append((label, tag, tid))
        if len(batch_imgs) >= 16:
            flush()
    flush()

    if not X_new:
        print("[v5-build] no new rows embedded", file=sys.stderr)
        return 1
    Xn = np.vstack(X_new).astype(np.float32)
    yn = np.array(y_new, dtype=np.int8)
    sn = np.array(src_new, dtype=object)
    tn = np.array(tile_new, dtype=object)

    d4 = np.load(DATASET_V4, allow_pickle=False)
    X4, y4, s4 = d4["X"], d4["y"], d4["src"]
    t4 = np.array([""] * len(X4), dtype=object)

    X = np.vstack([X4, Xn]).astype(np.float32)
    y = np.concatenate([y4.astype(np.int8), yn])
    src = np.concatenate([s4.astype(object), sn])
    tile = np.concatenate([t4, tn])

    np.savez(DATASET_V5, X=X, y=y, src=src.astype(str), tile=tile.astype(str))

    n_regpos = int(sum(1 for s in sn if s.startswith("regpos_")))
    n_regfp = int(sum(1 for s in sn if s.startswith("regfp_")))
    n_regground = int(sum(1 for s in sn if s.startswith("regground_")))
    manifest = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base": "dataset_v4.npz",
        "n_rows_v4": int(len(X4)),
        "n_rows_added": int(len(Xn)),
        "n_region_positive": n_regpos,
        "n_region_fp_hardneg": n_regfp,
        "n_region_groundmount_hardneg": n_regground,
        "n_total": int(len(X)),
        "encoder": "openai/clip-vit-large-patch14",
        "feature_dim": int(X.shape[1]),
        "snap_m": SNAP_M,
        "n_network_fetched": n_fetched,
    }
    MANIFEST_V5.write_text(json.dumps(manifest, indent=2))
    print(f"[v5-build] dataset_v5.npz: {X.shape}  "
          f"+{n_regpos} pos +{n_regfp} fp +{n_regground} ground")
    print(f"[v5-build] wrote {DATASET_V5.name} + manifest in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
