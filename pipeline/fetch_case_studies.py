"""Fetch hi-res tiles for the 6 hand-verified solar installations from the
2026Q2 ground-truth pass, save under site/public/case_studies/.

These six locations were the only hotspots out of 169 reviewable v1.0
candidates whose Esri hi-res imagery showed a visibly distinct rooftop solar
panel array. They become the on-site "notable confirmed installations"
sidebar that replaces the speculative pin layer.

Run:
    python fetch_case_studies.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PIPELINE_DIR = Path(__file__).parent
OUT_DIR = PIPELINE_DIR.parent / "site" / "public" / "case_studies"
OUT_INDEX = PIPELINE_DIR.parent / "site" / "public" / "data" / "case_studies.json"

ESRI_BASE = (
    "https://services.arcgisonline.com/arcgis/rest/services/"
    "World_Imagery/MapServer/export"
)
TILE_PX = 600
HALF_DEGREE = 0.0011  # ~120m at lat 14.6, gives a ~240m view
USER_AGENT = "ghost-watts/1.0 (case-studies; +https://github.com/xmpuspus/ghost-watts)"

CASES = [
    {
        "id": "makati",
        "city": "Makati",
        "province": "Metro Manila",
        "lat": 14.5472,
        "lon": 121.0398,
        "area_m2": 39404,
        "kwp_equiv": 5911,
        "note": "rooftop panel grid in dense urban Makati; verified against Esri 2022 hi-res",
        "v0_hotspot_idx": "007",
    },
    {
        "id": "valenzuela",
        "city": "Valenzuela",
        "province": "Metro Manila",
        "lat": 14.7194,
        "lon": 120.9349,
        "area_m2": 74114,
        "kwp_equiv": 11117,
        "note": "warehouse-scale dark gridded array in northern Valenzuela",
        "v0_hotspot_idx": "047",
    },
    {
        "id": "meycauayan",
        "city": "Meycauayan",
        "province": "Bulacan",
        "lat": 14.7504,
        "lon": 120.9549,
        "area_m2": 79892,
        "kwp_equiv": 11984,
        "note": "Bulacan industrial belt; warehouse rooftop with dark panel grid",
        "v0_hotspot_idx": "052",
    },
    {
        "id": "san_mateo",
        "city": "San Mateo",
        "province": "Rizal",
        "lat": 14.6945,
        "lon": 121.1405,
        "area_m2": 61382,
        "kwp_equiv": 9207,
        "note": "industrial warehouse with dark gridded roof on Rizal side",
        "v0_hotspot_idx": "077",
    },
    {
        "id": "dasmarinas",
        "city": "Dasmariñas",
        "province": "Cavite",
        "lat": 14.3113,
        "lon": 120.9532,
        "area_m2": 78891,
        "kwp_equiv": 11834,
        "note": "Cavite industrial roof with dark gridded sections; one of the largest detected",
        "v0_hotspot_idx": "116",
    },
    {
        "id": "carmona",
        "city": "Carmona",
        "province": "Cavite",
        "lat": 14.2845,
        "lon": 121.0177,
        "area_m2": 66524,
        "kwp_equiv": 9979,
        "note": "Carmona industrial complex; visible solar panel array on warehouse roof",
        "v0_hotspot_idx": "137",
    },
]


def fetch_tile(lon: float, lat: float, out_path: Path) -> bool:
    bbox = f"{lon - HALF_DEGREE},{lat - HALF_DEGREE},{lon + HALF_DEGREE},{lat + HALF_DEGREE}"
    params = {
        "bbox": bbox,
        "bboxSR": "4326",
        "size": f"{TILE_PX},{TILE_PX}",
        "imageSR": "3857",
        "format": "jpg",
        "f": "image",
    }
    url = f"{ESRI_BASE}?{urlencode(params)}"
    for attempt in range(1, 4):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=30) as resp:
                data = resp.read()
            if len(data) < 1000:
                raise RuntimeError(f"tiny response: {len(data)} bytes")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(data)
            return True
        except Exception as exc:
            print(f"    attempt {attempt} failed: {exc}", file=sys.stderr)
            if attempt < 3:
                time.sleep(2)
    return False


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_INDEX.parent.mkdir(parents=True, exist_ok=True)
    enriched: list[dict] = []
    for case in CASES:
        out = OUT_DIR / f"{case['id']}.jpg"
        ok = fetch_tile(case["lon"], case["lat"], out)
        case["image_path"] = f"/case_studies/{case['id']}.jpg"
        case["image_ok"] = ok
        enriched.append(case)
        print(f"{case['city']}: {'ok' if ok else 'FAILED'}")
        time.sleep(0.6)

    doc = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "validation_methodology": "Hand-checked against Esri World Imagery (~1-3 yr vintage in PH). Each location showed a visibly distinct rooftop solar panel array at the centered lat/lon. Six confirmed of 169 reviewable hot-spots in the 2026Q2 v1.0 release. See docs/groundtruth/labels.json for the full validation pass.",
        "cases": enriched,
    }
    with OUT_INDEX.open("w") as f:
        json.dump(doc, f, indent=2)
    print(f"\nWrote {OUT_INDEX}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
