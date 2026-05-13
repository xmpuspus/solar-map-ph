"""Sanity-check that the published per-building dataset contains no residential roofs.

Exit code 0 = clean, exit code 1 = leaks found.

Designed for CI: fails the build if a residential roof slips into the published
per-building GeoJSON. Wired into the Makefile (`make check-residential`) and the
release-readiness checklist.

The published dataset is `site/public/data/per_building_solar_ncr.geojson`. Every
feature must have `is_residential: false`. Residential rooftops are aggregated into
a separate roll-up at `site/public/data/residential_solar_aggregate.json` with no
geometry and no addresses, per the public data publication boundary in SECURITY.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PER_BUILDING = REPO / "site" / "public" / "data" / "per_building_solar_ncr.geojson"
RESIDENTIAL_AGG = REPO / "site" / "public" / "data" / "residential_solar_aggregate.json"

RESIDENTIAL_BTYPES = {
    "house",
    "apartments",
    "residential",
    "detached",
    "semidetached_house",
    "terrace",
    "bungalow",
    "dormitory",
    "barracks",
}


def main() -> int:
    if not PER_BUILDING.exists():
        print(f"[check] FAIL: {PER_BUILDING} not found", file=sys.stderr)
        return 1

    with PER_BUILDING.open() as f:
        gj = json.load(f)

    features = gj.get("features", [])
    if not features:
        print(f"[check] FAIL: {PER_BUILDING.name} has no features", file=sys.stderr)
        return 1

    leaks_flag: list[str] = []
    leaks_btype: list[str] = []
    for feat in features:
        props = feat.get("properties", {})
        if props.get("is_residential") is True:
            leaks_flag.append(str(props.get("building_osm_id")))
        bt = (props.get("building_type") or "").strip().lower()
        if bt in RESIDENTIAL_BTYPES:
            leaks_btype.append(f"{props.get('building_osm_id')} ({bt})")

    if leaks_flag or leaks_btype:
        print(
            f"[check] FAIL: {len(leaks_flag) + len(leaks_btype)} residential leak(s) in {PER_BUILDING.name}",
            file=sys.stderr,
        )
        if leaks_flag:
            print(
                f"  is_residential=True on OSM ways: {leaks_flag[:10]}"
                + (" ..." if len(leaks_flag) > 10 else ""),
                file=sys.stderr,
            )
        if leaks_btype:
            print(
                f"  residential building_type on OSM ways: {leaks_btype[:10]}"
                + (" ..." if len(leaks_btype) > 10 else ""),
                file=sys.stderr,
            )
        return 1

    n_total = len(features)
    print(f"[check] OK: {n_total} non-residential features in {PER_BUILDING.name}")

    if RESIDENTIAL_AGG.exists():
        with RESIDENTIAL_AGG.open() as f:
            agg = json.load(f)
        n_res = agg.get("n_residential_buildings_with_solar", 0)
        kwp_res = agg.get("kwp_residential_total", 0)
        print(f"[check] residential aggregate: {n_res} buildings, {kwp_res:.0f} kWp (count-only)")
    else:
        print(
            f"[check] WARN: {RESIDENTIAL_AGG.name} missing; residential roll-up not published",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
