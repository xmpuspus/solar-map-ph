"""Aggregate v3 scan results to GeoJSON and produce v2 vs v3 delta report.

Reads:
  detection/scan/ncr_scan_results_v3.jsonl   (output of --reuse-tiles run)
  detection/scan/ncr_scan_results.jsonl      (the original v2 scan, for comparison)
  detection/bootstrap/osm_solar_ncr_plus.geojson  (OSM ground truth tags)

Writes:
  site/public/data/rooftop_solar_ncr.geojson  (replaces the v2 geojson)
  detection/scan/match_report.json            (v3 OSM cross-match)
  detection/scan/v2_vs_v3_delta.json          (per-tile delta + summary stats)
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V2_JSONL = ROOT / "detection" / "scan" / "ncr_scan_results.jsonl"
V3_JSONL = ROOT / "detection" / "scan" / "ncr_scan_results_v3.jsonl"
GEOJSON_OUT = ROOT / "site" / "public" / "data" / "rooftop_solar_ncr.geojson"
DELTA_OUT = ROOT / "detection" / "scan" / "v2_vs_v3_delta.json"
OSM = ROOT / "detection" / "bootstrap" / "osm_solar_ncr_plus.geojson"
MATCH_OUT = ROOT / "detection" / "scan" / "match_report.json"
PER_BUILDING = ROOT / "site" / "public" / "data" / "per_building_solar_ncr.geojson"

HIGH = 0.85
CAND = 0.70
HALF_DEGREE = 0.0011
DISTANCE_M_CONFIRMED = 200


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def load_scores(jsonl: Path) -> dict[str, dict]:
    out = {}
    with jsonl.open() as f:
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
            out[rec["tile_id"]] = {"lat": rec["lat"], "lon": rec["lon"], "score": float(score)}
    return out


def load_per_building_anchors() -> dict[str, tuple[float, float]]:
    """Map tile_id -> (lat, lon) of the largest matched building's centroid.

    Used to anchor tile-level Points to actual building locations when SAM has
    already found one inside the tile. Falls through to tile center otherwise.
    Where a building was matched to multiple tiles (the panel array spans several
    high-conf cells), each tile_id resolves to the same building centroid -- that's
    fine, all those dots will visually cluster on top of the polygon.
    """
    if not PER_BUILDING.exists():
        return {}
    out: dict[str, tuple[float, float]] = {}
    fc = json.loads(PER_BUILDING.read_text())
    for f in fc.get("features", []):
        geom = f.get("geometry", {})
        if geom.get("type") != "Polygon":
            continue
        ring = geom["coordinates"][0]
        if not ring:
            continue
        # Centroid via mean of exterior ring (good enough for visualization).
        lons = [pt[0] for pt in ring]
        lats = [pt[1] for pt in ring]
        cen_lat = sum(lats) / len(lats)
        cen_lon = sum(lons) / len(lons)
        props = f.get("properties", {})
        tids = props.get("tile_ids") or []
        if not tids and props.get("tile_id"):
            tids = [props["tile_id"]]
        for tid in tids:
            # If multiple buildings match the same tile, prefer the one with the
            # largest panel area (most likely the "true" array for that cell).
            existing = out.get(tid)
            if existing is None:
                out[tid] = (cen_lat, cen_lon, props.get("panel_area_m2", 0))  # type: ignore[assignment]
            else:
                if (props.get("panel_area_m2") or 0) > (existing[2] if len(existing) > 2 else 0):  # type: ignore[index]
                    out[tid] = (cen_lat, cen_lon, props.get("panel_area_m2", 0))  # type: ignore[assignment]
    # Drop the panel_area tiebreaker once decided
    return {tid: (lat, lon) for tid, (lat, lon, _area) in out.items()}


def main() -> int:
    if not V3_JSONL.exists():
        print(f"[agg] v3 jsonl missing: {V3_JSONL}", file=sys.stderr)
        return 1
    v3 = load_scores(V3_JSONL)
    v2 = load_scores(V2_JSONL) if V2_JSONL.exists() else {}
    print(f"[agg] v3 tiles: {len(v3)}    v2 tiles: {len(v2)}")

    # --- v3 GeoJSON ---
    pb_anchors = load_per_building_anchors()
    if pb_anchors:
        print(f"[agg] per-building anchors loaded for {len(pb_anchors)} tile_ids")

    feats = []
    n_high = n_cand = n_anchored = 0
    for tid, rec in v3.items():
        score = rec["score"]
        if score >= HIGH:
            tier = "high"
            n_high += 1
        elif score >= CAND:
            tier = "candidate"
            n_cand += 1
        else:
            continue
        # Anchor the dot to the SAM-matched building centroid when available so
        # the tile-level point sits on top of its per-building polygon. Falls
        # back to tile centroid when SAM didn't match a building.
        anchor = pb_anchors.get(tid)
        if anchor is not None:
            point_lat, point_lon = anchor
            anchored = True
            n_anchored += 1
        else:
            point_lat, point_lon = rec["lat"], rec["lon"]
            anchored = False
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [point_lon, point_lat]},
            "properties": {
                "tile_id": tid,
                "score": round(score, 3),
                "tier": tier,
                "tile_bbox": [
                    rec["lon"] - HALF_DEGREE, rec["lat"] - HALF_DEGREE,
                    rec["lon"] + HALF_DEGREE, rec["lat"] + HALF_DEGREE,
                ],
                "tile_center": [rec["lon"], rec["lat"]],
                "anchored_to_building": anchored,
            },
        })

    # OSM cross-match
    osm_pts = []
    if OSM.exists():
        osm_fc = json.loads(OSM.read_text())
        for f in osm_fc["features"]:
            lon, lat = f["geometry"]["coordinates"]
            osm_pts.append((lat, lon, f["properties"].get("location")))
    print(f"[agg] OSM tags: {len(osm_pts)}")

    match_rows = []
    confirmed_high = new_high = confirmed_cand = new_cand = 0
    for f in feats:
        lon, lat = f["geometry"]["coordinates"]
        tier = f["properties"]["tier"]
        score = f["properties"]["score"]
        best = (float("inf"), None)
        for olat, olon, oloc in osm_pts:
            d = haversine_m(lat, lon, olat, olon)
            if d < best[0]:
                best = (d, oloc)
        nearest_d, nearest_loc = best
        confirmed = nearest_d <= DISTANCE_M_CONFIRMED
        match_rows.append({
            "tile_id": f["properties"]["tile_id"],
            "lat": lat, "lon": lon, "tier": tier, "score": score,
            "nearest_osm_m": round(nearest_d, 1),
            "nearest_osm_location": nearest_loc,
            "status": "confirmed" if confirmed else "new",
        })
        if tier == "high":
            confirmed_high += confirmed
            new_high += not confirmed
        else:
            confirmed_cand += confirmed
            new_cand += not confirmed

    # Write GeoJSON
    fc = {
        "type": "FeatureCollection",
        "features": feats,
        "_meta": {
            "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "scan_grid": "240m no-overlap",
            "total_tiles_scanned": len(v3),
            "n_high_confidence": n_high,
            "n_candidate": n_cand,
            "thresholds": {"high": HIGH, "candidate": CAND},
            "encoder": "openai/clip-vit-large-patch14",
            "classifier": "clf_v4.joblib",
            "training_set": "294 OSM-tagged + 4 case-study + 4 promoted-rneg + 111 v3conf (active-learning round 2) positives, 197 negatives (46 GT + 150 random NCR + 1 v3fp); 2 noisy cases dropped",
            "v4_loso_at_t085": {"precision": 0.988, "recall": 0.772, "f1": 0.867, "from": "5-fold group-aware CV"},
            "v4_calibrated_holdout_at_t085": {
                "precision": 0.959,
                "recall": 0.797,
                "f1": 0.870,
                "from": "20% never-trained OSM holdout, Platt sigmoid calibration",
                "platt": "P = sigmoid(1.2916 * decision_function(x) + 0.1627)",
            },
        },
    }
    GEOJSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    GEOJSON_OUT.write_text(json.dumps(fc, indent=1))
    print(f"[agg] v3 geojson: {n_high} high + {n_cand} candidate ({n_anchored} anchored to buildings) -> {GEOJSON_OUT}")

    # Write match report
    MATCH_OUT.write_text(json.dumps({
        "n_detections": len(match_rows),
        "n_high": n_high,
        "n_candidate": n_cand,
        "confirmed_distance_m": DISTANCE_M_CONFIRMED,
        "summary": {
            "confirmed_high": confirmed_high,
            "new_high": new_high,
            "confirmed_candidate": confirmed_cand,
            "new_candidate": new_cand,
        },
        "rows": match_rows,
    }, indent=2))
    print(f"[agg] v3 OSM cross-match: high={confirmed_high} confirmed + {new_high} new ({100*new_high/max(1,n_high):.0f}% NEW)")
    print(f"[agg]                     cand={confirmed_cand} confirmed + {new_cand} new")

    # --- v2 vs v3 delta ---
    if v2:
        # Categorize each tile by v2 tier and v3 tier
        def tier(s: float) -> str:
            return "high" if s >= HIGH else ("candidate" if s >= CAND else "below")

        all_tids = set(v2.keys()) | set(v3.keys())
        deltas = []
        upgrades_to_high = 0
        downgrades_from_high = 0
        upgrades_cand_to_high = 0
        new_high_total = 0
        lost_high_total = 0
        score_diffs = []
        for tid in all_tids:
            s2 = v2.get(tid, {}).get("score")
            s3 = v3.get(tid, {}).get("score")
            if s2 is None or s3 is None:
                continue
            t2 = tier(s2)
            t3 = tier(s3)
            score_diffs.append(s3 - s2)
            if t2 != "high" and t3 == "high":
                upgrades_to_high += 1
                if t2 == "candidate":
                    upgrades_cand_to_high += 1
                if t2 == "below":
                    new_high_total += 1
            if t2 == "high" and t3 != "high":
                downgrades_from_high += 1
                lost_high_total += 1
            if t2 != t3:
                deltas.append({
                    "tile_id": tid,
                    "lat": v3[tid]["lat"], "lon": v3[tid]["lon"],
                    "v2_score": round(s2, 3), "v3_score": round(s3, 3),
                    "v2_tier": t2, "v3_tier": t3,
                })

        # Top movers
        deltas.sort(key=lambda r: -(r["v3_score"] - r["v2_score"]))

        n2_high = sum(1 for s in v2.values() if s["score"] >= HIGH)
        n2_cand = sum(1 for s in v2.values() if CAND <= s["score"] < HIGH)
        avg_diff = sum(score_diffs) / max(1, len(score_diffs))
        delta_doc = {
            "summary": {
                "v2_high": n2_high,
                "v3_high": n_high,
                "v2_cand": n2_cand,
                "v3_cand": n_cand,
                "tier_changes": len(deltas),
                "upgrades_to_high": upgrades_to_high,
                "  from_below": new_high_total,
                "  from_candidate": upgrades_cand_to_high,
                "downgrades_from_high": downgrades_from_high,
                "mean_score_diff_v3_minus_v2": round(avg_diff, 4),
            },
            "tier_changes": deltas[:60],   # limit to top 60 for readability
        }
        DELTA_OUT.write_text(json.dumps(delta_doc, indent=2))
        print(f"[agg] delta: v2={n2_high}H/{n2_cand}C  ->  v3={n_high}H/{n_cand}C  ({upgrades_to_high} upgraded to H, {downgrades_from_high} lost)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
