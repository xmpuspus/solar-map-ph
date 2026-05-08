"""Generate per-city satellite imagery and hot-spot clusters.

For each city in the franchise, exports:
    site/public/imagery/{psgc_code}_baseline.jpg   (RGB true-color, baseline year)
    site/public/imagery/{psgc_code}_current.jpg    (RGB true-color, current quarter)
    site/public/imagery/{psgc_code}_diff.png       (NIR delta, white-to-coral ramp)

Plus aggregates the top-K darkened-pixel clusters across all cities into:
    site/public/data/hot_spots_{quarter}.geojson

Run after pipeline.py:
    python imagery_export.py --quarter 2026Q2 --baseline 2022

Auth via the same EE_SERVICE_ACCOUNT and EE_KEY_FILE env vars.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import ee  # type: ignore[import-not-found]

PIPELINE_DIR = Path(__file__).parent
IMAGERY_DIR = PIPELINE_DIR.parent / "site" / "public" / "imagery"
DATA_DIR = PIPELINE_DIR.parent / "site" / "public" / "data"
BOUNDARIES_PATH = PIPELINE_DIR / "boundaries" / "franchise_cities_polygons.geojson"

QUARTER_TO_MONTHS = {
    "Q1": (1, 3),
    "Q2": (4, 6),
    "Q3": (7, 9),
    "Q4": (10, 12),
}

# Visualization parameters
RGB_VIS = {"min": 0, "max": 3000, "bands": ["B4", "B3", "B2"], "gamma": 1.4}
# Multi-channel solar fingerprint: pixels where NIR AND SWIR both dropped
# significantly. NIR-only is too permissive (catches reroofing, paint, shadows).
# AND-ing with SWIR enforces a silicon-style spectral signature.
SOLAR_FINGERPRINT_NIR_DROP = -250
SOLAR_FINGERPRINT_SWIR_DROP = -250
FINGERPRINT_PALETTE = ["#ffffff", "#d97757"]
THUMB_DIM = 600

# Hot-spot extraction.
# v1.1 strategy: require BOTH NIR and SWIR co-darkening (multi-channel
# fingerprint, same as the diff visualization), drop the speckle via
# morphological opening, then connected-component vectorization. Size caps
# reject neighborhood-scale drift and pixel-scale noise. Top 1 per city
# (not 3) to keep precision high.
HOTSPOT_LOCAL_RADIUS_M = 200      # focal mean radius for local-anomaly baseline
HOTSPOT_NIR_DROP = -250           # NIR scaled units; multi-channel AND threshold
HOTSPOT_SWIR_DROP = -250          # SWIR scaled units; multi-channel AND threshold
HOTSPOT_LOCAL_ANOMALY_THRESHOLD = -150  # local-anomaly threshold on the AND mask
HOTSPOT_MORPH_RADIUS_M = 30       # erode+dilate radius
HOTSPOT_MIN_AREA_M2 = 2_000       # warehouse-scale floor
HOTSPOT_MAX_AREA_M2 = 200_000     # 20 hectares; the v1.0 solar were 4-8 ha clusters, keep them
HOTSPOT_TOP_K_PER_CITY = 1        # top 1 per city for higher per-pin confidence


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ghost-watts imagery + hot-spot exporter")
    p.add_argument("--quarter", required=True, help="Quarter, e.g. 2026Q2")
    p.add_argument("--baseline", default="2022", help="Baseline year")
    p.add_argument("--only", help="Only export this PSGC code (for testing)")
    p.add_argument("--limit", type=int, help="Process at most N cities (for testing)")
    p.add_argument("--skip-imagery", action="store_true", help="Skip image export, just hot spots")
    p.add_argument("--skip-hotspots", action="store_true", help="Skip hot-spot extraction")
    p.add_argument("--diff-only", action="store_true", help="Only regenerate diff PNGs (skip baseline+current RGB)")
    return p.parse_args()


def initialize_ee() -> None:
    sa = os.environ.get("EE_SERVICE_ACCOUNT")
    key_file = os.environ.get("EE_KEY_FILE")
    if not sa or not key_file:
        raise SystemExit("Missing EE_SERVICE_ACCOUNT or EE_KEY_FILE.")
    credentials = ee.ServiceAccountCredentials(sa, key_file)
    ee.Initialize(credentials)


def quarter_to_dates(quarter: str) -> tuple[date, date]:
    if len(quarter) != 6 or quarter[4] != "Q":
        raise ValueError(f"Invalid quarter: {quarter}")
    year = int(quarter[:4])
    sm, em = QUARTER_TO_MONTHS[quarter[4:]]
    start = date(year, sm, 1)
    end = (
        date(year, 12, 31)
        if em == 12
        else date.fromordinal(date(year, em + 1, 1).toordinal() - 1)
    )
    return start, end


def s2_cloud_mask(image: ee.Image) -> ee.Image:
    scl = image.select("SCL")
    valid = (
        scl.neq(1)
        .And(scl.neq(3))
        .And(scl.neq(8))
        .And(scl.neq(9))
        .And(scl.neq(10))
    )
    return image.updateMask(valid)


def load_boundaries() -> list[dict[str, Any]]:
    with BOUNDARIES_PATH.open() as f:
        fc = json.load(f)
    return fc.get("features", [])


def median_s2(start: date, end: date, geom: ee.Geometry) -> ee.Image:
    return (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterDate(str(start), str(end))
        .filterBounds(geom)
        .map(s2_cloud_mask)
        .median()
    )


def download(url: str, out_path: Path, max_retries: int = 3) -> bool:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, max_retries + 1):
        try:
            req = Request(url, headers={"User-Agent": "ghost-watts/1.0"})
            with urlopen(req, timeout=120) as resp:
                data = resp.read()
            out_path.write_bytes(data)
            return True
        except Exception as exc:
            print(f"    download attempt {attempt} failed: {exc}", file=sys.stderr)
            if attempt < max_retries:
                time.sleep(3 * attempt)
    return False


def export_city_imagery(
    psgc_code: str,
    geom: ee.Geometry,
    quarter_start: date,
    quarter_end: date,
    baseline_year: int,
) -> dict[str, bool]:
    baseline_start = date(baseline_year, quarter_start.month, 1)
    baseline_end = date(baseline_year, quarter_end.month, quarter_end.day)

    s2_baseline = median_s2(baseline_start, baseline_end, geom)
    s2_current = median_s2(quarter_start, quarter_end, geom)

    worldcover = ee.ImageCollection("ESA/WorldCover/v200").first()
    built_mask = worldcover.eq(50).clip(geom)

    nir_diff = s2_current.select("B8").subtract(s2_baseline.select("B8"))
    swir_diff = s2_current.select("B11").subtract(s2_baseline.select("B11"))
    # Solar fingerprint: BOTH NIR and SWIR dropped meaningfully, on built-up area.
    # Single-channel NIR drop catches reroofing, paint, shadows; AND-ing with
    # SWIR drop enforces a silicon-style spectral response.
    fingerprint = (
        nir_diff.lt(SOLAR_FINGERPRINT_NIR_DROP)
        .And(swir_diff.lt(SOLAR_FINGERPRINT_SWIR_DROP))
        .updateMask(built_mask)
    )

    out = {
        "baseline": IMAGERY_DIR / f"{psgc_code}_baseline.jpg",
        "current": IMAGERY_DIR / f"{psgc_code}_current.jpg",
        "diff": IMAGERY_DIR / f"{psgc_code}_diff.png",
    }
    results: dict[str, bool] = {}

    if not getattr(export_city_imagery, "_diff_only", False):
        try:
            url_baseline = s2_baseline.clip(geom).getThumbURL(
                {**RGB_VIS, "region": geom, "dimensions": THUMB_DIM, "format": "jpg"}
            )
            results["baseline"] = download(url_baseline, out["baseline"])
        except Exception as exc:
            print(f"    baseline failed: {exc}", file=sys.stderr)
            results["baseline"] = False

        try:
            url_current = s2_current.clip(geom).getThumbURL(
                {**RGB_VIS, "region": geom, "dimensions": THUMB_DIM, "format": "jpg"}
            )
            results["current"] = download(url_current, out["current"])
        except Exception as exc:
            print(f"    current failed: {exc}", file=sys.stderr)
            results["current"] = False
    else:
        results["baseline"] = out["baseline"].exists()
        results["current"] = out["current"].exists()

    try:
        url_diff = fingerprint.getThumbURL(
            {
                "min": 0, "max": 1,
                "palette": FINGERPRINT_PALETTE,
                "region": geom,
                "dimensions": THUMB_DIM,
                "format": "png",
            }
        )
        results["diff"] = download(url_diff, out["diff"])
    except Exception as exc:
        print(f"    diff failed: {exc}", file=sys.stderr)
        results["diff"] = False

    return results


def extract_hotspots(
    city_props: dict[str, Any],
    geom: ee.Geometry,
    quarter_start: date,
    quarter_end: date,
    baseline_year: int,
) -> list[dict[str, Any]]:
    baseline_start = date(baseline_year, quarter_start.month, 1)
    baseline_end = date(baseline_year, quarter_end.month, quarter_end.day)

    s2_baseline = median_s2(baseline_start, baseline_end, geom)
    s2_current = median_s2(quarter_start, quarter_end, geom)

    worldcover = ee.ImageCollection("ESA/WorldCover/v200").first()
    built_mask = worldcover.eq(50).clip(geom)
    nir_diff = (
        s2_current.select("B8")
        .subtract(s2_baseline.select("B8"))
        .updateMask(built_mask)
    )
    swir_diff = (
        s2_current.select("B11")
        .subtract(s2_baseline.select("B11"))
        .updateMask(built_mask)
    )

    # v1.1: multi-channel AND. A pixel must drop in BOTH NIR and SWIR to count.
    # Solar panels do both; reroofing/paint/shadows usually don't trip both.
    co_darkened_strength = nir_diff.add(swir_diff).divide(2)  # avg drop magnitude where AND holds
    multi_mask = nir_diff.lt(HOTSPOT_NIR_DROP).And(swir_diff.lt(HOTSPOT_SWIR_DROP))
    co_darkened = co_darkened_strength.updateMask(multi_mask)

    # Local-anomaly on the AND signal: this pixel dropped MORE than its
    # neighborhood on the multi-channel measure.
    local_mean = co_darkened.unmask(0).focal_mean(radius=HOTSPOT_LOCAL_RADIUS_M, units="meters")
    local_anomaly = co_darkened.subtract(local_mean)

    darkened = local_anomaly.lt(HOTSPOT_LOCAL_ANOMALY_THRESHOLD).selfMask()
    # Morphological opening: erode then dilate to drop pixel-scale speckle.
    opened = (
        darkened.focal_min(radius=HOTSPOT_MORPH_RADIUS_M, units="meters")
        .focal_max(radius=HOTSPOT_MORPH_RADIUS_M, units="meters")
        .rename("dark")
    )

    try:
        patches = opened.reduceToVectors(
            geometry=geom,
            scale=20,
            geometryType="polygon",
            eightConnected=True,
            maxPixels=int(1e9),
            bestEffort=True,
            tileScale=4,
        )
        patches_with_area = patches.map(
            lambda f: f.set("area_m2", f.geometry().area(maxError=10))
        )
        filtered = patches_with_area.filter(
            ee.Filter.And(
                ee.Filter.gt("area_m2", HOTSPOT_MIN_AREA_M2),
                ee.Filter.lt("area_m2", HOTSPOT_MAX_AREA_M2),
            )
        )
        top = filtered.sort("area_m2", False).limit(HOTSPOT_TOP_K_PER_CITY)
        info = top.getInfo()
    except Exception as exc:
        print(f"    hotspot extraction failed: {exc}", file=sys.stderr)
        return []

    out: list[dict[str, Any]] = []
    for feat in info.get("features", []):
        try:
            poly = feat.get("geometry")
            if not poly or not poly.get("coordinates"):
                continue
            ring = poly["coordinates"][0]
            if not ring:
                continue
            xs = [pt[0] for pt in ring]
            ys = [pt[1] for pt in ring]
            cx = sum(xs) / len(xs)
            cy = sum(ys) / len(ys)
            area_m2 = float(feat.get("properties", {}).get("area_m2", 0))
            kwp_equiv = round(area_m2 * 0.15, 1)
            out.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [cx, cy]},
                    "properties": {
                        "city": city_props["name"],
                        "psgc_code": city_props["psgc_code"],
                        "province": city_props["province"],
                        "area_m2": round(area_m2, 1),
                        "kwp_equiv": kwp_equiv,
                    },
                }
            )
        except Exception as exc:
            print(f"    hotspot parse failed: {exc}", file=sys.stderr)
    return out


def main() -> int:
    args = parse_args()
    initialize_ee()
    quarter_start, quarter_end = quarter_to_dates(args.quarter)
    baseline_year = int(args.baseline)
    boundaries = load_boundaries()
    if args.only:
        boundaries = [b for b in boundaries if b["properties"].get("psgc_code") == args.only]
    if args.limit:
        boundaries = boundaries[: args.limit]

    print(f"Processing {len(boundaries)} city/cities for {args.quarter}")
    IMAGERY_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    all_hotspots: list[dict[str, Any]] = []
    failed_imagery: list[str] = []

    for i, feat in enumerate(boundaries, start=1):
        props = feat["properties"]
        psgc = props["psgc_code"]
        name = props["name"]
        print(f"[{i}/{len(boundaries)}] {name} ({psgc})")
        try:
            geom = ee.Geometry(feat["geometry"], geodesic=False)
        except Exception as exc:
            print(f"    geom failed: {exc}", file=sys.stderr)
            continue

        if not args.skip_imagery:
            export_city_imagery._diff_only = args.diff_only  # type: ignore[attr-defined]
            results = export_city_imagery(psgc, geom, quarter_start, quarter_end, baseline_year)
            if not all(results.values()):
                failed_imagery.append(name)
                print(f"    imagery partial: {results}")
            else:
                print(f"    imagery ok")

        if not args.skip_hotspots:
            hotspots = extract_hotspots(props, geom, quarter_start, quarter_end, baseline_year)
            print(f"    hotspots: {len(hotspots)}")
            all_hotspots.extend(hotspots)

    if not args.skip_hotspots:
        out_path = DATA_DIR / f"hot_spots_{args.quarter}.geojson"
        fc = {
            "type": "FeatureCollection",
            "features": all_hotspots,
            "properties": {
                "quarter": args.quarter,
                "baseline_year": str(baseline_year),
                "generated_utc": datetime.now(timezone.utc).isoformat(),
                "version": "v1.1_multichannel",
                "nir_drop_threshold": HOTSPOT_NIR_DROP,
                "swir_drop_threshold": HOTSPOT_SWIR_DROP,
                "local_anomaly_threshold": HOTSPOT_LOCAL_ANOMALY_THRESHOLD,
                "local_radius_m": HOTSPOT_LOCAL_RADIUS_M,
                "morph_radius_m": HOTSPOT_MORPH_RADIUS_M,
                "min_area_m2": HOTSPOT_MIN_AREA_M2,
                "max_area_m2": HOTSPOT_MAX_AREA_M2,
                "top_k_per_city": HOTSPOT_TOP_K_PER_CITY,
                "city_count": len({h["properties"]["psgc_code"] for h in all_hotspots}),
                "total_hotspots": len(all_hotspots),
            },
        }
        with out_path.open("w") as f:
            json.dump(fc, f, indent=2)
        print(f"\nWrote {len(all_hotspots)} hot-spots from {fc['properties']['city_count']} cities -> {out_path}")

    if failed_imagery:
        print(f"\nImagery missing/partial for: {', '.join(failed_imagery)}", file=sys.stderr)

    # Update manifest with imagery quarter pointer
    manifest_path = DATA_DIR / "manifest.json"
    if manifest_path.exists():
        with manifest_path.open() as f:
            manifest = json.load(f)
    else:
        manifest = {}
    if not args.skip_imagery:
        manifest["imagery_quarter"] = args.quarter
    if not args.skip_hotspots:
        manifest["hotspots_quarter"] = args.quarter
    with manifest_path.open("w") as f:
        json.dump(manifest, f, indent=2)

    return 0


if __name__ == "__main__":
    sys.exit(main())
