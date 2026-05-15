"""Step 3 of v1.2: build per-region labeled holdout splits.

Step 1 showed the dominant problem is a calibration gap: clf_v4's NCR F1 was
measured on the curated OSM holdout, which is ~0.88-separable from the field
scan distribution even within NCR. So the per-region honest holdout must be
scan-realistic, not curated-OSM-style.

Scan-realistic positives per region:
  - OSM roof-tagged solar (community-verified real rooftops in the region
    bbox), from detection/bootstrap/osm_solar_<region>.geojson
  - spot-check `rooftop` verdicts (the scanner's own top detections, visually
    confirmed), from detection/train/region_labels.jsonl

Hard negatives (shared cross-region pool; only 4 exist so a per-region split
is infeasible):
  - spot-check `ground_mount` + `blue_roof_fp` verdicts

Region-stratified: each region with at least MIN_POS_CALIBRATE positives gets
a seeded held-out positive subset, used only for per-domain Platt/isotonic
fitting and honest per-region precision in step 4. Regions below the threshold
are flagged `uncalibrated_low_n` and stay reported as candidate inventory in
step 8 — an honest "uncalibrated" beats a fabricated confidence interval.

Tile-id convention `{lat:.5f}_{lon:.5f}` matches the scan-results convention so
step 4 can join OSM positives to the scanner's score.

Seed 4243 (family of holdout_split.py's 4242; never reuse a calibration seed).

Outputs:
  detection/train/v5_region_holdout/holdout_split.json
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REGIONS_JSON = ROOT / "pipeline" / "regions" / "regions.json"
LABELS = ROOT / "detection" / "train" / "region_labels.jsonl"
OSM_DIR = ROOT / "detection" / "bootstrap"
OUT = ROOT / "detection" / "train" / "v5_region_holdout" / "holdout_split.json"

SEED = 4243
HOLDOUT_FRAC = 0.30
MIN_POS_CALIBRATE = 20  # below this a region cannot get an honest CI


def tile_id(lat: float, lon: float) -> str:
    return f"{lat:.5f}_{lon:.5f}"


def main() -> int:
    if not LABELS.exists():
        print(f"[region-holdout] missing {LABELS}; run harvest_spotcheck_labels.py", file=sys.stderr)
        return 1

    spot = [json.loads(line) for line in LABELS.read_text().splitlines() if line.strip()]
    cfg = json.loads(REGIONS_JSON.read_text())
    region_slugs = [r["slug"] for r in cfg["regions"]]

    rng = random.Random(SEED)

    # Shared hard-negative pool (region-tagged but pooled for calibration).
    hard_neg = [
        {
            "region": r["region"],
            "tile_id": r["tile_id"],
            "lat": r["lat"],
            "lon": r["lon"],
            "label": r["label"],
            "source": "spotcheck",
        }
        for r in spot
        if r["label"] in ("ground_mount", "blue_roof_fp")
    ]

    regions_out = {}
    for slug in region_slugs:
        pos: list[dict] = []
        # spot-check confirmed rooftops (scanner's own detections, verified)
        for r in spot:
            if r["region"] == slug and r["label"] == "rooftop":
                pos.append(
                    {
                        "tile_id": r["tile_id"],
                        "lat": r["lat"],
                        "lon": r["lon"],
                        "origin": "spotcheck_rooftop",
                    }
                )
        # OSM roof-tagged solar in the region bbox
        osm_path = OSM_DIR / f"osm_solar_{slug}.geojson"
        if osm_path.exists():
            fc = json.loads(osm_path.read_text())
            for f in fc.get("features", []):
                if f["properties"].get("location") != "roof":
                    continue
                lon, lat = f["geometry"]["coordinates"]
                pos.append(
                    {
                        "tile_id": tile_id(lat, lon),
                        "lat": lat,
                        "lon": lon,
                        "origin": "osm_roof",
                        "osm_id": f["properties"].get("osm_id"),
                    }
                )
        # Dedup by tile_id (an OSM roof tag may coincide with a spot-check tile).
        seen = set()
        uniq = []
        for p in pos:
            if p["tile_id"] in seen:
                continue
            seen.add(p["tile_id"])
            uniq.append(p)
        pos = uniq

        rng.shuffle(pos)
        n_pos = len(pos)
        calibrate = n_pos >= MIN_POS_CALIBRATE
        n_hold = int(round(n_pos * HOLDOUT_FRAC)) if calibrate else 0
        holdout_pos = sorted(p["tile_id"] for p in pos[:n_hold])
        train_pos = sorted(p["tile_id"] for p in pos[n_hold:])

        regions_out[slug] = {
            "n_pos_total": n_pos,
            "n_pos_holdout": len(holdout_pos),
            "n_pos_train": len(train_pos),
            "calibration_status": "calibrated" if calibrate else "uncalibrated_low_n",
            "holdout_pos_tile_ids": holdout_pos,
            "train_pos_tile_ids": train_pos,
            "positives": pos,
        }

    split = {
        "seed": SEED,
        "holdout_frac": HOLDOUT_FRAC,
        "min_pos_calibrate": MIN_POS_CALIBRATE,
        "note": (
            "Scan-realistic per-region holdout (OSM roof + spot-check rooftop). "
            "Hard negatives are a shared cross-region pool (only 4 labeled). "
            "Regions with calibration_status=uncalibrated_low_n must ship as "
            "candidate inventory without a precision CI."
        ),
        "hard_neg_pool": hard_neg,
        "n_hard_neg": len(hard_neg),
        "regions": regions_out,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(split, indent=2))

    print(f"[region-holdout] seed={SEED} hard_neg_pool={len(hard_neg)}")
    for slug, r in regions_out.items():
        print(
            f"  {slug:11s} pos={r['n_pos_total']:3d} "
            f"holdout={r['n_pos_holdout']:2d} train={r['n_pos_train']:3d} "
            f"-> {r['calibration_status']}"
        )
    print(f"[region-holdout] wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
