"""Cross-reference v1.1 hotspots against the existing v1.0 labels by spatial
proximity within each city, then compute precision on the labeled subset.

Each v1.1 hotspot inherits the label of the nearest v1.0 hotspot in the same
city if within 500m. Unmatched hotspots are flagged for fresh validation.

Run:
    python aggregate_validation.py --quarter 2026Q2
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent
DATA_DIR = PIPELINE_DIR.parent / "site" / "public" / "data"
GROUNDTRUTH_DIR = PIPELINE_DIR.parent / "docs" / "groundtruth"


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    R = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lat2 - lat1)
    dn = math.radians(lon2 - lon1)
    a = math.sin(dl / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dn / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--quarter", required=True)
    p.add_argument("--match-radius-m", type=float, default=500)
    return p.parse_args()


def main() -> int:
    args = parse_args()

    new_path = DATA_DIR / f"hot_spots_{args.quarter}.geojson"
    with new_path.open() as f:
        new_fc = json.load(f)
    new_features = new_fc.get("features", [])

    labels_path = GROUNDTRUTH_DIR / "labels.json"
    with labels_path.open() as f:
        labels_doc = json.load(f)

    index_path = GROUNDTRUTH_DIR / "index.json"
    with index_path.open() as f:
        idx_doc = json.load(f)
    old_hotspots_by_idx = {h["idx"]: h for h in idx_doc["hotspots"]}
    label_by_idx = {row["idx"]: row for row in labels_doc["labels"]}

    # Build per-city list of old hotspots with coords + label
    by_city: dict[str, list[dict]] = {}
    for old_h in idx_doc["hotspots"]:
        city = old_h["city"]
        label_row = label_by_idx.get(old_h["idx"], {})
        by_city.setdefault(city, []).append(
            {
                "idx": old_h["idx"],
                "lon": old_h["lon"],
                "lat": old_h["lat"],
                "area_m2": old_h.get("area_m2"),
                "label": label_row.get("label", "unknown"),
            }
        )

    enriched: list[dict] = []
    for new_idx, feat in enumerate(new_features):
        coords = feat["geometry"]["coordinates"]
        new_lon, new_lat = coords[0], coords[1]
        city = feat["properties"]["city"]
        candidates = by_city.get(city, [])
        if not candidates:
            best = None
            best_dist = float("inf")
        else:
            best = None
            best_dist = float("inf")
            for c in candidates:
                d = haversine_m(new_lon, new_lat, c["lon"], c["lat"])
                if d < best_dist:
                    best_dist = d
                    best = c
        inherited = None
        if best is not None and best_dist <= args.match_radius_m:
            inherited = best["label"]
        enriched.append(
            {
                "new_idx": new_idx,
                "city": city,
                "lon": new_lon,
                "lat": new_lat,
                "area_m2": feat["properties"].get("area_m2"),
                "kwp_equiv": feat["properties"].get("kwp_equiv"),
                "matched_old_idx": best["idx"] if (best and best_dist <= args.match_radius_m) else None,
                "match_dist_m": round(best_dist, 1) if best_dist != float("inf") else None,
                "inherited_label": inherited,
            }
        )

    # Aggregate
    total = len(enriched)
    labeled = [e for e in enriched if e["inherited_label"] in {"solar", "not_solar", "unclear"}]
    missing = [e for e in enriched if e["inherited_label"] == "missing"]
    unmatched = [e for e in enriched if e["inherited_label"] is None]
    label_counts = {"solar": 0, "not_solar": 0, "unclear": 0, "missing": 0, "unmatched": 0}
    for e in enriched:
        label_counts[e["inherited_label"] or "unmatched"] = (
            label_counts.get(e["inherited_label"] or "unmatched", 0) + 1
        )

    reviewable = label_counts["solar"] + label_counts["not_solar"] + label_counts["unclear"]
    strict = label_counts["solar"] / reviewable if reviewable else 0.0
    lenient = (label_counts["solar"] + label_counts["unclear"]) / reviewable if reviewable else 0.0

    summary = {
        "version": "v1.1_multichannel",
        "quarter": args.quarter,
        "total_v1_1_hotspots": total,
        "label_counts": label_counts,
        "reviewable": reviewable,
        "precision_strict": round(strict, 4),
        "precision_lenient": round(lenient, 4),
        "match_radius_m": args.match_radius_m,
        "v1_0_total": len(idx_doc["hotspots"]),
        "v1_0_solar": sum(1 for r in labels_doc["labels"] if r["label"] == "solar"),
        "delta": {
            "hotspots_kept_pct": round(total / len(idx_doc["hotspots"]), 3),
            "solar_kept_pct": (
                round(
                    label_counts["solar"] / sum(1 for r in labels_doc["labels"] if r["label"] == "solar"), 3
                )
                if sum(1 for r in labels_doc["labels"] if r["label"] == "solar") > 0
                else None
            ),
        },
    }

    out_path = GROUNDTRUTH_DIR / "v1_1_validation.json"
    with out_path.open("w") as f:
        json.dump({"summary": summary, "hotspots": enriched}, f, indent=2)

    print(json.dumps(summary, indent=2))
    print(f"\nWrote per-hotspot detail to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
