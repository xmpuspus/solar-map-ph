"""Cross-region PII gate for v1.1 (and later) regional detection GeoJSONs.

NCR has its own per-building leak check (check_no_residential_leaks.py) because
NCR ships per-building polygons. The v1.1 cross-domain regions (Cebu, Davao,
Iloilo, CDO, Legazpi, Calabarzon) ship only TILE-CENTER points, not building
polygons. This script asserts that property: no per-building geometry, no PII
fields, no addresses.

Exit code 0 = clean, exit code 1 = a region file violates the published
data-publication boundary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REGIONS_CFG = REPO / "pipeline" / "regions" / "regions.json"
DATA_DIR = REPO / "site" / "public" / "data"

FORBIDDEN_PROPERTY_KEYS = {
    "is_residential",
    "building_osm_id",
    "address",
    "addr:street",
    "addr:housenumber",
    "owner",
    "owner_name",
    "occupant",
}


def check_one(path: Path) -> list[str]:
    issues: list[str] = []
    try:
        gj = json.loads(path.read_text())
    except Exception as e:
        return [f"{path.name}: cannot parse: {e}"]
    feats = gj.get("features", [])
    if not feats:
        return [f"{path.name}: 0 features (suspicious; aggregator output should be non-empty)"]
    for i, f in enumerate(feats):
        geom = f.get("geometry", {}) or {}
        if geom.get("type") != "Point":
            issues.append(f"{path.name}[{i}]: geometry type is {geom.get('type')!r}, expected Point")
        props = f.get("properties", {}) or {}
        for k in props:
            if k in FORBIDDEN_PROPERTY_KEYS:
                issues.append(f"{path.name}[{i}]: forbidden property key {k!r}")
        if i >= 5 and issues:
            issues.append(f"{path.name}: ... (further issues suppressed)")
            break
    return issues


def main() -> int:
    cfg = json.loads(REGIONS_CFG.read_text())
    region_slugs = [r["slug"] for r in cfg["regions"]]
    print(f"[check-region] regions to check: {region_slugs}")

    any_issues = False
    for slug in region_slugs:
        path = DATA_DIR / f"rooftop_solar_{slug}.geojson"
        if not path.exists():
            print(f"[check-region] {slug}: SKIP (no published GeoJSON yet)")
            continue
        issues = check_one(path)
        if issues:
            any_issues = True
            print(f"[check-region] FAIL {slug}:", file=sys.stderr)
            for line in issues:
                print(f"  {line}", file=sys.stderr)
        else:
            try:
                gj = json.loads(path.read_text())
                n = len(gj.get("features", []))
                print(f"[check-region] OK {slug}: {n} point-tile features, no PII fields")
            except Exception:
                pass

    return 1 if any_issues else 0


if __name__ == "__main__":
    sys.exit(main())
