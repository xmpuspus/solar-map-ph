"""ghost-watts quarterly pipeline.

Pulls multi-signal solar-presence indicators from Earth Engine over Meralco's
franchise area and emits a city-level GeoJSON with composite scores.

Run:
    python pipeline.py --quarter 2026Q2 --baseline 2022

Auth: set EE_SERVICE_ACCOUNT and EE_KEY_FILE env vars before running.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import ee  # type: ignore[import-not-found]

PIPELINE_DIR = Path(__file__).parent
SITE_DATA_DIR = PIPELINE_DIR.parent / "site" / "public" / "data"

SIGNAL_WEIGHTS = {
    "nir": 0.40,
    "swir": 0.30,
    "lst": 0.20,
    "nightlight": 0.10,
}

QUARTER_TO_MONTHS = {
    "Q1": (1, 3),
    "Q2": (4, 6),
    "Q3": (7, 9),
    "Q4": (10, 12),
}


@dataclass
class CityResult:
    name: str
    psgc_code: str
    province: str
    geometry: dict[str, Any]
    nir_delta: float | None = None
    swir_delta: float | None = None
    lst_anomaly: float | None = None
    nightlight_delta: float | None = None
    buildings_total: int | None = None
    built_up_km2: float | None = None
    z_scores: dict[str, float] = field(default_factory=dict)
    composite: float | None = None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ghost-watts quarterly pipeline")
    p.add_argument("--quarter", required=True, help="Quarter, e.g. 2026Q2")
    p.add_argument("--baseline", default="2022", help="Baseline year for delta computation")
    p.add_argument("--out-dir", default=str(SITE_DATA_DIR), help="Output directory for GeoJSON")
    p.add_argument(
        "--scratch-dir",
        default=str(PIPELINE_DIR / "scratch"),
        help="Local scratch dir for intermediate artifacts",
    )
    p.add_argument("--dry-run", action="store_true", help="Skip EE auth and emit a stub manifest only")
    return p.parse_args()


def initialize_ee() -> None:
    sa = os.environ.get("EE_SERVICE_ACCOUNT")
    key_file = os.environ.get("EE_KEY_FILE")
    if not sa or not key_file:
        raise SystemExit(
            "Missing EE_SERVICE_ACCOUNT or EE_KEY_FILE. "
            "Sign up at https://earthengine.google.com, create a service account, "
            "and export both env vars before running."
        )
    if not Path(key_file).exists():
        raise SystemExit(f"EE_KEY_FILE does not exist: {key_file}")
    credentials = ee.ServiceAccountCredentials(sa, key_file)
    ee.Initialize(credentials)


def quarter_to_dates(quarter: str) -> tuple[date, date]:
    if len(quarter) != 6 or quarter[4] != "Q":
        raise ValueError(f"Invalid quarter format: {quarter} (expected e.g. 2026Q2)")
    year = int(quarter[:4])
    q = quarter[4:]
    if q not in QUARTER_TO_MONTHS:
        raise ValueError(f"Invalid quarter suffix: {q}")
    start_month, end_month = QUARTER_TO_MONTHS[q]
    start = date(year, start_month, 1)
    if end_month == 12:
        end = date(year, 12, 31)
    else:
        next_month_first = date(year, end_month + 1, 1)
        end = date.fromordinal(next_month_first.toordinal() - 1)
    return start, end


def load_franchise_cities() -> list[dict[str, Any]]:
    path = PIPELINE_DIR / "franchise_cities.json"
    with path.open() as f:
        raw = json.load(f)
    cities: list[dict[str, Any]] = []
    for key, value in raw.items():
        if key.startswith("_"):
            continue
        if isinstance(value, list):
            cities.extend(value)
    return cities


def get_city_geometry(name: str, psgc_code: str) -> ee.Geometry | None:
    """Fetch admin polygon from FAO GAUL or PSA boundary asset.

    Tries multiple known boundary assets. Returns None if no polygon found,
    in which case the caller should skip this city and log.

    The PSA PSGC boundary asset is published in EE under various community uploads.
    Adjust ``boundary_asset`` to a specific asset id you have access to. As a
    fallback we use FAO GAUL level 2 administrative units.
    """
    boundary_asset = os.environ.get(
        "EE_BOUNDARY_ASSET",
        "FAO/GAUL/2015/level2",
    )
    fc = ee.FeatureCollection(boundary_asset)
    if "FAO/GAUL" in boundary_asset:
        feature = (
            fc.filter(ee.Filter.eq("ADM0_NAME", "Philippines"))
            .filter(ee.Filter.eq("ADM2_NAME", name))
            .first()
        )
    else:
        feature = fc.filter(ee.Filter.eq("psgc_code", psgc_code)).first()
    info = feature.getInfo()
    if info is None:
        return None
    return ee.Geometry(info["geometry"])


def median_band(
    collection_id: str,
    band: str,
    start: date,
    end: date,
    geometry: ee.Geometry,
    cloud_mask_fn=None,
) -> ee.Image:
    coll = (
        ee.ImageCollection(collection_id)
        .filterDate(str(start), str(end))
        .filterBounds(geometry)
    )
    if cloud_mask_fn is not None:
        coll = coll.map(cloud_mask_fn)
    return coll.select(band).median()


def s2_cloud_mask(image: ee.Image) -> ee.Image:
    scl = image.select("SCL")
    # Mask out clouds (8, 9), cirrus (10), saturated (1), shadow (3)
    valid = (
        scl.neq(1)
        .And(scl.neq(3))
        .And(scl.neq(8))
        .And(scl.neq(9))
        .And(scl.neq(10))
    )
    return image.updateMask(valid)


def landsat_cloud_mask(image: ee.Image) -> ee.Image:
    qa = image.select("QA_PIXEL")
    cloud_bit = 1 << 3
    shadow_bit = 1 << 4
    mask = qa.bitwiseAnd(cloud_bit).eq(0).And(qa.bitwiseAnd(shadow_bit).eq(0))
    return image.updateMask(mask)


def reduce_mean(image: ee.Image, geometry: ee.Geometry, scale: int) -> float | None:
    try:
        result = image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geometry,
            scale=scale,
            maxPixels=int(1e10),
        ).getInfo()
    except Exception as exc:  # pragma: no cover - EE-specific
        print(f"  reduceRegion failed: {exc}", file=sys.stderr)
        return None
    if not result:
        return None
    values = [v for v in result.values() if v is not None]
    if not values:
        return None
    return float(values[0])


def get_built_up_mask(geometry: ee.Geometry) -> ee.Image:
    worldcover = ee.ImageCollection("ESA/WorldCover/v200").first()
    built = worldcover.eq(50)
    return built.clip(geometry)


def built_up_km2(geometry: ee.Geometry) -> float | None:
    mask = get_built_up_mask(geometry)
    pixel_area = ee.Image.pixelArea().updateMask(mask)
    area_m2 = reduce_mean(pixel_area, geometry, scale=10)
    if area_m2 is None:
        return None
    return area_m2 / 1e6


def compute_signals_for_city(
    city: dict[str, Any],
    quarter_start: date,
    quarter_end: date,
    baseline_year: int,
) -> CityResult | None:
    name = city["name"]
    geom = get_city_geometry(name, city["psgc_code"])
    if geom is None:
        print(f"  no boundary polygon for {name}; skipping", file=sys.stderr)
        return None

    geom_info = geom.getInfo()
    built_mask = get_built_up_mask(geom)

    baseline_start = date(baseline_year, quarter_start.month, 1)
    baseline_end = date(baseline_year, quarter_end.month, quarter_end.day)

    s2_collection = "COPERNICUS/S2_SR_HARMONIZED"
    nir_curr = median_band(s2_collection, "B8", quarter_start, quarter_end, geom, s2_cloud_mask).updateMask(built_mask)
    nir_base = median_band(s2_collection, "B8", baseline_start, baseline_end, geom, s2_cloud_mask).updateMask(built_mask)
    nir_delta_image = nir_curr.subtract(nir_base)

    swir_curr = median_band(s2_collection, "B11", quarter_start, quarter_end, geom, s2_cloud_mask).updateMask(built_mask)
    swir_base = median_band(s2_collection, "B11", baseline_start, baseline_end, geom, s2_cloud_mask).updateMask(built_mask)
    swir_delta_image = swir_curr.subtract(swir_base)

    landsat_collection = "LANDSAT/LC09/C02/T1_L2"
    lst_curr = median_band(landsat_collection, "ST_B10", quarter_start, quarter_end, geom, landsat_cloud_mask).updateMask(built_mask)
    lst_base = median_band(landsat_collection, "ST_B10", baseline_start, baseline_end, geom, landsat_cloud_mask).updateMask(built_mask)
    lst_anomaly_image = lst_curr.subtract(lst_base)

    viirs_collection = "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG"
    viirs_curr = median_band(viirs_collection, "avg_rad", quarter_start, quarter_end, geom)
    viirs_base = median_band(viirs_collection, "avg_rad", baseline_start, baseline_end, geom)
    viirs_delta_image = viirs_curr.subtract(viirs_base)

    nir_delta = reduce_mean(nir_delta_image, geom, scale=10)
    swir_delta = reduce_mean(swir_delta_image, geom, scale=10)
    lst_anomaly = reduce_mean(lst_anomaly_image, geom, scale=30)
    nightlight_delta = reduce_mean(viirs_delta_image, geom, scale=500)
    built_km2 = built_up_km2(geom)

    return CityResult(
        name=name,
        psgc_code=city["psgc_code"],
        province=city["province"],
        geometry=geom_info,
        nir_delta=nir_delta,
        swir_delta=swir_delta,
        lst_anomaly=lst_anomaly,
        nightlight_delta=nightlight_delta,
        built_up_km2=built_km2,
    )


def z_score(values: list[float | None], idx: int) -> float | None:
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return None
    mean = sum(clean) / len(clean)
    var = sum((v - mean) ** 2 for v in clean) / (len(clean) - 1)
    if var <= 0 or math.isclose(var, 0.0):
        return 0.0
    std = math.sqrt(var)
    target = values[idx]
    if target is None:
        return None
    return (target - mean) / std


def compute_z_scores_and_composite(results: list[CityResult]) -> None:
    nir_vals = [r.nir_delta for r in results]
    swir_vals = [r.swir_delta for r in results]
    lst_vals = [r.lst_anomaly for r in results]
    night_vals = [r.nightlight_delta for r in results]

    for i, r in enumerate(results):
        z_nir = z_score(nir_vals, i)
        z_swir = z_score(swir_vals, i)
        z_lst = z_score(lst_vals, i)
        z_night = z_score(night_vals, i)
        r.z_scores = {
            "nir": z_nir if z_nir is not None else 0.0,
            "swir": z_swir if z_swir is not None else 0.0,
            "lst": z_lst if z_lst is not None else 0.0,
            "nightlight": z_night if z_night is not None else 0.0,
        }
        r.composite = (
            -SIGNAL_WEIGHTS["nir"] * r.z_scores["nir"]
            + -SIGNAL_WEIGHTS["swir"] * r.z_scores["swir"]
            + -SIGNAL_WEIGHTS["lst"] * r.z_scores["lst"]
            + SIGNAL_WEIGHTS["nightlight"] * r.z_scores["nightlight"]
        )


def load_lgu_friction() -> dict[str, Any]:
    with (PIPELINE_DIR / "lgu_friction.json").open() as f:
        return json.load(f)


def load_meralco_aggregates() -> dict[str, Any]:
    with (PIPELINE_DIR / "meralco_aggregates.json").open() as f:
        return json.load(f)


def to_geojson_feature(r: CityResult, friction: dict[str, Any]) -> dict[str, Any]:
    verified = friction.get("verified", {})
    permit_fee = None
    permit_days = None
    permit_status = "unverified"
    permit_source: str | None = None
    if r.name in verified:
        row = verified[r.name]
        permit_fee = row.get("permit_fee_php")
        permit_days = row.get("permit_days_p50")
        permit_status = row.get("data_status", "verified")
        permit_source = row.get("source_url")
    return {
        "type": "Feature",
        "geometry": r.geometry,
        "properties": {
            "name": r.name,
            "psgc_code": r.psgc_code,
            "province": r.province,
            "metrics": {
                "s2_nir_delta_zscore": r.z_scores.get("nir") or 0.0,
                "s2_swir_delta_zscore": r.z_scores.get("swir") or 0.0,
                "landsat_lst_anomaly_zscore": r.z_scores.get("lst") or 0.0,
                "viirs_nightlight_delta_zscore": r.z_scores.get("nightlight") or 0.0,
                "composite_solar_signal_score": r.composite or 0.0,
                "buildings_total": r.buildings_total,
                "built_up_km2": r.built_up_km2,
                "raw": {
                    "nir_delta": r.nir_delta,
                    "swir_delta": r.swir_delta,
                    "lst_anomaly": r.lst_anomaly,
                    "nightlight_delta": r.nightlight_delta,
                },
            },
            "policy": {
                "lgu_permit_fee_php": permit_fee,
                "lgu_permit_days_p50": permit_days,
                "permit_data_status": permit_status,
                "permit_data_source": permit_source,
            },
        },
    }


def write_outputs(
    results: list[CityResult],
    quarter: str,
    baseline: str,
    out_dir: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    friction = load_lgu_friction()
    aggregates = load_meralco_aggregates()

    features = [to_geojson_feature(r, friction) for r in results]

    fc = {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "quarter": quarter,
            "baseline_year": baseline,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "weights": SIGNAL_WEIGHTS,
        },
    }
    geojson_path = out_dir / f"ghost_watts_{quarter}.geojson"
    with geojson_path.open("w") as f:
        json.dump(fc, f, indent=2)

    composites = [r.composite for r in results if r.composite is not None]
    summary = {
        "quarter": quarter,
        "baseline_year": baseline,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "city_count": len(results),
        "city_count_with_signal": len(composites),
        "composite_score_franchise_mean": (
            sum(composites) / len(composites) if composites else None
        ),
        "composite_score_max": max(composites) if composites else None,
        "composite_score_min": min(composites) if composites else None,
        "top5_strongest_signal": [
            {"name": r.name, "composite": r.composite}
            for r in sorted(
                (r for r in results if r.composite is not None),
                key=lambda r: r.composite or 0.0,
                reverse=True,
            )[:5]
        ],
        "weights": SIGNAL_WEIGHTS,
        "meralco_aggregates": {
            "registered_installations": aggregates.get("registered_installations"),
            "registered_capacity_mw_aggregate": aggregates.get("registered_capacity_mw_aggregate"),
            "icsc_unregistered_estimate_fraction": aggregates.get("icsc_unregistered_estimate_fraction"),
            "as_of": aggregates.get("as_of"),
        },
    }
    summary_path = out_dir / f"ghost_watts_summary_{quarter}.json"
    with summary_path.open("w") as f:
        json.dump(summary, f, indent=2)

    manifest_path = out_dir / "manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            with manifest_path.open() as f:
                manifest = json.load(f)
        except json.JSONDecodeError:
            manifest = {}
    manifest["latest_quarter"] = quarter
    manifest.setdefault("quarters", [])
    if quarter not in manifest["quarters"]:
        manifest["quarters"].append(quarter)
        manifest["quarters"].sort()
    with manifest_path.open("w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Wrote {geojson_path}")
    print(f"Wrote {summary_path}")
    print(f"Updated {manifest_path}")


def write_dry_run_stub(quarter: str, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    cities = load_franchise_cities()
    fc = {
        "type": "FeatureCollection",
        "features": [],
        "properties": {
            "quarter": quarter,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "dry_run": True,
            "city_count_planned": len(cities),
            "note": "Dry-run output. Run with EE auth to populate features.",
        },
    }
    path = out_dir / f"ghost_watts_{quarter}.geojson"
    with path.open("w") as f:
        json.dump(fc, f, indent=2)
    print(f"Wrote dry-run stub to {path}")


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    if args.dry_run:
        write_dry_run_stub(args.quarter, out_dir)
        return 0

    initialize_ee()
    quarter_start, quarter_end = quarter_to_dates(args.quarter)
    baseline_year = int(args.baseline)
    cities = load_franchise_cities()
    print(f"Processing {len(cities)} cities for {args.quarter} (baseline {args.baseline})")

    results: list[CityResult] = []
    for i, city in enumerate(cities, start=1):
        print(f"[{i}/{len(cities)}] {city['name']}")
        try:
            r = compute_signals_for_city(city, quarter_start, quarter_end, baseline_year)
        except Exception as exc:
            print(f"  failed: {exc}", file=sys.stderr)
            r = None
        if r is not None:
            results.append(r)

    if not results:
        print("No city signals computed; bailing out.", file=sys.stderr)
        return 1

    compute_z_scores_and_composite(results)
    write_outputs(results, args.quarter, args.baseline, out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
