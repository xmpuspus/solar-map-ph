"""Region-aware aggregator. Turns a {region}_scan_results.jsonl into a
rooftop_solar_{region}.geojson FeatureCollection ready for the site.

Mirrors the schema of rooftop_solar_ncr.geojson so the site can load it
through the same code path. Cross-matches each detection against the
served-LGU polygons in pipeline/regions/{region}_lgus.geojson to assign
each detection a city name.

Run:
    python detection/scan/aggregate_region.py --region cebu
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIR = ROOT / "detection" / "scan"
REGIONS_DIR = ROOT / "pipeline" / "regions"
DATA_DIR = ROOT / "site" / "public" / "data"

HIGH = 0.85
CAND = 0.70
HALF_DEGREE = 0.0011
# Region bboxes are rectangular and extend past the served-LGU franchise
# polygons (e.g. Calabarzon). Detections that fall outside every served
# polygon are bucketed here explicitly instead of silently dropped as
# lgu_name:None, so the city table and the published total reconcile.
OUT_OF_FRANCHISE = "(outside mapped franchise LGUs)"


def load_region(slug: str) -> dict:
    cfg = json.loads((REGIONS_DIR / "regions.json").read_text())
    for r in cfg["regions"]:
        if r["slug"] == slug:
            return r
    raise SystemExit(f"region not found: {slug}")


def point_in_polygon(point: tuple[float, float], polygon: list[list[float]]) -> bool:
    """Ray-casting test. polygon is list of [lon, lat] coordinates."""
    lon, lat = point
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        loni, lati = polygon[i]
        lonj, latj = polygon[j]
        if ((lati > lat) != (latj > lat)) and (lon < (lonj - loni) * (lat - lati) / (latj - lati + 1e-12) + loni):
            inside = not inside
        j = i
    return inside


def assign_city(lat: float, lon: float, lgus_fc: dict) -> str | None:
    for feat in lgus_fc.get("features", []):
        geom = feat["geometry"]
        polygons = (
            geom["coordinates"]
            if geom["type"] == "MultiPolygon"
            else [geom["coordinates"]]
        )
        for poly in polygons:
            if point_in_polygon((lon, lat), poly[0]):
                return feat["properties"]["name"]
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", required=True)
    args = ap.parse_args()

    region = load_region(args.region)
    slug = region["slug"]
    print(f"[aggregate] region={slug}")

    jsonl_path = SCAN_DIR / f"{slug}_scan_results.jsonl"
    if not jsonl_path.exists():
        sys.exit(f"missing scan results: {jsonl_path}")

    lgus_path = REGIONS_DIR / f"{slug}_lgus.geojson"
    if lgus_path.exists():
        lgus_fc = json.loads(lgus_path.read_text())
        print(f"[aggregate] loaded {len(lgus_fc.get('features', []))} LGU polygons")
    else:
        lgus_fc = {"features": []}
        print("[aggregate] no LGU polygons; cities won't be assigned")

    # Read scan results
    rows = []
    with jsonl_path.open() as f:
        for line in f:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("fetch_ok") and rec.get("score") is not None:
                rows.append(rec)
    print(f"[aggregate] scored tiles: {len(rows)}")

    # Filter to high+cand tiers
    detections = [r for r in rows if r["score"] >= CAND]
    print(f"[aggregate] high(>={HIGH}): {sum(1 for r in detections if r['score'] >= HIGH)}, "
          f"candidate({CAND}-{HIGH}): {sum(1 for r in detections if r['score'] < HIGH)}, "
          f"total scored: {len(rows)}, scanned: {len(rows)}")

    # Assemble GeoJSON
    features = []
    cities_with_detections: dict[str, dict] = {}
    n_high = 0
    n_cand = 0
    for r in detections:
        tier = "high" if r["score"] >= HIGH else "candidate"
        if tier == "high":
            n_high += 1
        else:
            n_cand += 1
        city = assign_city(r["lat"], r["lon"], lgus_fc) or OUT_OF_FRANCHISE
        # Tile bbox
        tile_bbox = [
            r["lon"] - HALF_DEGREE,
            r["lat"] - HALF_DEGREE,
            r["lon"] + HALF_DEGREE,
            r["lat"] + HALF_DEGREE,
        ]
        feat = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
            "properties": {
                "tile_id": r["tile_id"],
                "score": round(r["score"], 4),
                "tier": tier,
                "tile_bbox": tile_bbox,
                "tile_center": [r["lon"], r["lat"]],
                "anchored_to_building": False,  # set by per_building pass
                "osm_status": "new",  # populated by cross-match pass; default to new
                "kwp_estimate": None,  # populated by per_building pass
                "lgu_name": city,
                "province": region.get("province"),
                "region": slug,
            },
        }
        features.append(feat)
        if city:
            c = cities_with_detections.setdefault(city, {
                "name": city,
                "province": region.get("province"),
                "n_high": 0,
                "n_candidate": 0,
                "n_new_high": 0,
                "sum_kwp_high": 0.0,
            })
            if tier == "high":
                c["n_high"] += 1
                c["n_new_high"] += 1  # initial assumption (no OSM cross-match in v1.1)
            else:
                c["n_candidate"] += 1

    geojson = {
        "type": "FeatureCollection",
        "_meta": {
            "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "scan_grid": "240m no-overlap",
            "region": slug,
            "region_display": region["display_name"],
            "franchise": region["franchise"],
            "total_tiles_scanned": len(rows),
            "n_high_confidence": n_high,
            "n_candidate": n_cand,
            "thresholds": {"high": HIGH, "candidate": CAND},
            "encoder": "openai/clip-vit-large-patch14",
            "classifier": "clf_v4.joblib",
            "calibration": "Platt sigmoid (NCR-trained, applied cross-region without retraining)",
            "calibration_note": (
                "This classifier was trained on NCR OSM-tagged positives. Cross-region precision "
                "is not yet independently calibrated. Treat detections as candidates pending "
                "regional active-learning rounds."
            ),
        },
        "features": features,
    }

    out_path = DATA_DIR / f"rooftop_solar_{slug}.geojson"
    out_path.write_text(json.dumps(geojson))
    print(f"[aggregate] wrote {out_path.relative_to(ROOT)}  ({len(features)} features)")

    # City-level counts (mirror city_detection_counts.json shape)
    rows_list = sorted(cities_with_detections.values(), key=lambda c: -c["n_high"])
    city_counts = {
        "_meta": {
            "n_cities_with_detections": len(rows_list),
            "n_total_high": n_high,
            "n_total_candidate": n_cand,
            "region": slug,
        },
        "rows": rows_list,
    }
    cc_path = DATA_DIR / f"city_detection_counts_{slug}.json"
    cc_path.write_text(json.dumps(city_counts, indent=1))
    print(f"[aggregate] wrote {cc_path.relative_to(ROOT)}")

    print(f"\n[summary] {slug}: {n_high} high-conf + {n_cand} candidate across {len(rows_list)} cities")
    return 0


if __name__ == "__main__":
    sys.exit(main())
