"""Cross-reference CNN detections against OSM-tagged solar locations.

For each CNN detection in rooftop_solar_ncr.geojson, find the nearest OSM
solar tag in osm_solar_ncr_plus.geojson. If within DISTANCE_M, it's a
"confirmed" detection (model rediscovers known solar). Otherwise it's a
"new" discovery (model proposes solar OSM hasn't tagged).

Outputs:
  detection/scan/match_report.json  (per-detection {nearest_osm_dist_m, status})
  prints summary stats
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DETECTIONS = ROOT / "site" / "public" / "data" / "rooftop_solar_ncr.geojson"
OSM = ROOT / "detection" / "bootstrap" / "osm_solar_ncr_plus.geojson"
OUT = ROOT / "detection" / "scan" / "match_report.json"

DISTANCE_M_CONFIRMED = 200  # CNN tile is 240m wide; matching to OSM within 200m is a hit


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def main() -> int:
    if not DETECTIONS.exists() or not OSM.exists():
        print("[match] missing inputs", file=sys.stderr)
        return 1
    det_fc = json.loads(DETECTIONS.read_text())
    osm_fc = json.loads(OSM.read_text())
    osm_pts = []
    for f in osm_fc["features"]:
        lon, lat = f["geometry"]["coordinates"]
        osm_pts.append((lat, lon, f["properties"].get("location")))
    print(f"[match] OSM solar tags: {len(osm_pts)}")
    print(f"[match] CNN detections: {len(det_fc['features'])}")

    rows = []
    confirmed_high = confirmed_cand = 0
    new_high = new_cand = 0
    for f in det_fc["features"]:
        lon, lat = f["geometry"]["coordinates"]
        tier = f["properties"]["tier"]
        score = f["properties"]["score"]
        # Find nearest OSM tag
        best = (float("inf"), None)
        for olat, olon, oloc in osm_pts:
            d = haversine_m(lat, lon, olat, olon)
            if d < best[0]:
                best = (d, oloc)
        nearest_d_m, nearest_loc = best
        confirmed = nearest_d_m <= DISTANCE_M_CONFIRMED
        rows.append({
            "lat": lat, "lon": lon, "tier": tier, "score": score,
            "nearest_osm_m": round(nearest_d_m, 1),
            "nearest_osm_location": nearest_loc,
            "status": "confirmed" if confirmed else "new",
        })
        if tier == "high":
            confirmed_high += confirmed
            new_high += not confirmed
        else:
            confirmed_cand += confirmed
            new_cand += not confirmed

    n_high = sum(1 for f in det_fc["features"] if f["properties"]["tier"] == "high")
    n_cand = sum(1 for f in det_fc["features"] if f["properties"]["tier"] == "candidate")

    print()
    print(f"[match] HIGH-CONFIDENCE TIER ({n_high} detections):")
    print(f"  confirmed by OSM (<= {DISTANCE_M_CONFIRMED} m): {confirmed_high} ({100*confirmed_high/max(1,n_high):.0f}%)")
    print(f"  new discoveries (>  {DISTANCE_M_CONFIRMED} m): {new_high} ({100*new_high/max(1,n_high):.0f}%)")
    print()
    print(f"[match] CANDIDATE TIER ({n_cand} detections):")
    print(f"  confirmed by OSM: {confirmed_cand} ({100*confirmed_cand/max(1,n_cand):.0f}%)")
    print(f"  new discoveries:  {new_cand} ({100*new_cand/max(1,n_cand):.0f}%)")

    # Sort new discoveries by score (the most interesting positives the model found alone)
    new_high_rows = sorted([r for r in rows if r["tier"] == "high" and r["status"] == "new"],
                            key=lambda r: -r["score"])
    print()
    print(f"[match] Top 10 NEW high-confidence discoveries (model finds, OSM doesn't have):")
    for r in new_high_rows[:10]:
        print(f"  score={r['score']:.3f}  lat={r['lat']:.5f} lon={r['lon']:.5f}  nearest_osm={r['nearest_osm_m']:.0f}m")

    OUT.write_text(json.dumps({
        "n_detections": len(rows),
        "n_high": n_high,
        "n_candidate": n_cand,
        "confirmed_distance_m": DISTANCE_M_CONFIRMED,
        "summary": {
            "high": {"confirmed": confirmed_high, "new": new_high},
            "candidate": {"confirmed": confirmed_cand, "new": new_cand},
        },
        "rows": rows,
    }, indent=2))
    print(f"\n[match] wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
