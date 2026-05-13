"""SolarMap.PH output validator.

Reads the GeoJSON and summary written by pipeline.py for a given quarter and
checks invariants. Exits non-zero on any failure.

Run:
    python validate.py --quarter 2026Q2
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent
SITE_DATA_DIR = PIPELINE_DIR.parent / "site" / "public" / "data"

REQUIRED_METRIC_FIELDS = [
    "s2_nir_delta_zscore",
    "s2_swir_delta_zscore",
    "landsat_lst_anomaly_zscore",
    "viirs_nightlight_delta_zscore",
    "composite_solar_signal_score",
]

Z_SCORE_BOUND = 5.0  # Anything beyond is suspicious


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SolarMap.PH validator")
    p.add_argument("--quarter", required=True)
    p.add_argument("--data-dir", default=str(SITE_DATA_DIR))
    return p.parse_args()


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


def warn(msg: str) -> None:
    print(f"WARN: {msg}", file=sys.stderr)


def main() -> int:
    args = parse_args()
    data_dir = Path(args.data_dir)
    geojson_path = data_dir / f"solar_map_ph_{args.quarter}.geojson"
    summary_path = data_dir / f"solar_map_ph_summary_{args.quarter}.json"

    failures: list[str] = []

    if not geojson_path.exists():
        failures.append(f"missing {geojson_path}")
        for m in failures:
            fail(m)
        return 1

    with geojson_path.open() as f:
        fc = json.load(f)

    if fc.get("type") != "FeatureCollection":
        failures.append("not a FeatureCollection")

    features = fc.get("features", [])
    if not features:
        failures.append("zero features in collection")

    for i, feat in enumerate(features):
        props = feat.get("properties") or {}
        if not props.get("name"):
            failures.append(f"feature {i}: missing name")
            continue
        metrics = props.get("metrics") or {}
        for field_name in REQUIRED_METRIC_FIELDS:
            if field_name not in metrics:
                failures.append(f"{props['name']}: missing metric {field_name}")
                continue
            v = metrics[field_name]
            if v is None:
                continue
            if isinstance(v, (int, float)) and (math.isnan(v) or math.isinf(v)):
                failures.append(f"{props['name']}.{field_name} is NaN or Inf")
            if isinstance(v, (int, float)) and abs(v) > Z_SCORE_BOUND:
                warn(f"{props['name']}.{field_name} = {v} exceeds |{Z_SCORE_BOUND}|; check for outlier")

    if summary_path.exists():
        with summary_path.open() as f:
            summary = json.load(f)
        city_count = summary.get("city_count")
        if city_count is None or city_count <= 0:
            failures.append("summary.city_count is missing or non-positive")
        if summary.get("quarter") != args.quarter:
            failures.append("summary quarter does not match requested quarter")
    else:
        failures.append(f"missing {summary_path}")

    if failures:
        print(f"\nValidation failed with {len(failures)} issue(s):", file=sys.stderr)
        for m in failures:
            fail(m)
        return 1

    print(f"OK: {len(features)} features, {args.quarter}, validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
