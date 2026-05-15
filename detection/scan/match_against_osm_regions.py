"""Step 5 of v1.2: region-aware OSM cross-match.

Generalizes match_against_osm.py (NCR-only) to every v1.1 region. For each
detection in site/public/data/rooftop_solar_<slug>.geojson, find the nearest
OSM-tagged solar installation in detection/bootstrap/osm_solar_<slug>.geojson
(produced by fetch_osm_solar_region.py). Within DISTANCE_M_CONFIRMED it is
"confirmed" (the model rediscovered a known installation); otherwise "new"
(the model proposes solar no prior public map has tagged).

This is what the "X% not on any prior public map" thesis requires for the new
franchises. v1.1 shipped every region with osm_status hardcoded to "new" and
n_new_high == n_high; this pass replaces those placeholders with the real
cross-match and recomputes the per-city new-high counts.

Mutations are confined to the `osm_status` feature property and the
`n_new_high` city count. Geometry stays Point, no PII keys added, so
check_region_no_pii.py still passes.

Run:
    python detection/scan/match_against_osm_regions.py            # all regions
    python detection/scan/match_against_osm_regions.py --region cebu
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGIONS_JSON = ROOT / "pipeline" / "regions" / "regions.json"
DATA_DIR = ROOT / "site" / "public" / "data"
OSM_DIR = ROOT / "detection" / "bootstrap"
REPORT_DIR = ROOT / "detection" / "scan"

DISTANCE_M_CONFIRMED = 200  # tile is 240 m wide; match within 200 m is a hit


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def process_region(slug: str) -> dict | None:
    gj_path = DATA_DIR / f"rooftop_solar_{slug}.geojson"
    osm_path = OSM_DIR / f"osm_solar_{slug}.geojson"
    if not gj_path.exists():
        print(f"[match-region] {slug}: no published GeoJSON, skip", file=sys.stderr)
        return None
    gj = json.loads(gj_path.read_text())

    osm_pts: list[tuple[float, float]] = []
    osm_meta = "missing"
    if osm_path.exists():
        osm_fc = json.loads(osm_path.read_text())
        for f in osm_fc.get("features", []):
            lon, lat = f["geometry"]["coordinates"]
            osm_pts.append((lat, lon))
        osm_meta = f"{len(osm_pts)} OSM tags"
    else:
        print(
            f"[match-region] {slug}: no osm_solar_{slug}.geojson; all detections "
            f"stay 'new' (no prior public map to match against)",
            file=sys.stderr,
        )

    confirmed = {"high": 0, "candidate": 0}
    new = {"high": 0, "candidate": 0}
    # Reset per-city new-high before recomputing.
    city_new_high: dict[str, int] = {}

    for feat in gj.get("features", []):
        lon, lat = feat["geometry"]["coordinates"]
        tier = feat["properties"].get("tier", "candidate")
        best = float("inf")
        for olat, olon in osm_pts:
            d = haversine_m(lat, lon, olat, olon)
            if d < best:
                best = d
                if best <= DISTANCE_M_CONFIRMED:
                    break
        is_confirmed = best <= DISTANCE_M_CONFIRMED
        status = "confirmed" if is_confirmed else "new"
        feat["properties"]["osm_status"] = status
        feat["properties"]["nearest_osm_m"] = (
            round(best, 1) if best != float("inf") else None
        )
        bucket = "high" if tier == "high" else "candidate"
        if is_confirmed:
            confirmed[bucket] += 1
        else:
            new[bucket] += 1
            if tier == "high":
                city = feat["properties"].get("lgu_name")
                if city:
                    city_new_high[city] = city_new_high.get(city, 0) + 1

    n_high = confirmed["high"] + new["high"]
    n_cand = confirmed["candidate"] + new["candidate"]
    gj.setdefault("_meta", {})["osm_cross_match"] = {
        "osm_source": osm_meta,
        "distance_m_confirmed": DISTANCE_M_CONFIRMED,
        "high": {"confirmed": confirmed["high"], "new": new["high"]},
        "candidate": {"confirmed": confirmed["candidate"], "new": new["candidate"]},
    }
    gj_path.write_text(json.dumps(gj))

    # Recompute n_new_high in the city counts file.
    cc_path = DATA_DIR / f"city_detection_counts_{slug}.json"
    if cc_path.exists():
        cc = json.loads(cc_path.read_text())
        for row in cc.get("rows", []):
            row["n_new_high"] = city_new_high.get(row["name"], 0)
        cc.setdefault("_meta", {})["n_new_high_total"] = sum(city_new_high.values())
        cc_path.write_text(json.dumps(cc, indent=1))

    report = {
        "region": slug,
        "osm_source": osm_meta,
        "distance_m_confirmed": DISTANCE_M_CONFIRMED,
        "n_high": n_high,
        "n_candidate": n_cand,
        "high": {"confirmed": confirmed["high"], "new": new["high"]},
        "candidate": {"confirmed": confirmed["candidate"], "new": new["candidate"]},
        "pct_new_high": round(100 * new["high"] / max(1, n_high), 1),
    }
    (REPORT_DIR / f"match_report_{slug}.json").write_text(json.dumps(report, indent=2))
    print(
        f"[match-region] {slug:11s} {osm_meta:14s}  high {new['high']}/{n_high} new "
        f"({report['pct_new_high']}%)  cand {new['candidate']}/{n_cand} new"
    )
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", help="single region slug (default: all)")
    args = ap.parse_args()

    cfg = json.loads(REGIONS_JSON.read_text())
    slugs = [r["slug"] for r in cfg["regions"]]
    if args.region:
        slugs = [s for s in slugs if s == args.region]

    reports = []
    for slug in slugs:
        r = process_region(slug)
        if r:
            reports.append(r)
    print(f"\n[match-region] cross-matched {len(reports)} regions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
