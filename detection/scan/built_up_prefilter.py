"""ESA WorldCover built-up pre-filter for nationwide scans.

For each 240m grid cell in a bbox, sample the underlying ESA WorldCover 2021
classification (10m resolution) and compute the fraction of pixels classified
as class 50 = "Built-up". Cells with built-up < threshold (default 5%) are
flagged for skipping in downstream classification.

WorldCover tiles are 3°x3°, stored as cloud-optimized GeoTIFFs at:
  https://esa-worldcover.s3.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_<TILE>_Map.tif
where <TILE> is e.g. N12E120 (SW corner lat=12, lon=120).

For PH coverage we need at minimum:
  N12E120  (covers lat 12-15, lon 120-123: Luzon south + metro areas)
  N15E120  (covers lat 15-18, lon 120-123: northern Luzon)
  N09E123  (covers lat 9-12, lon 123-126: Visayas + N Mindanao)
  N06E123  (covers lat 6-9, lon 123-126: central + S Mindanao)
  N03E123  (covers lat 3-6, lon 123-126: Sulu archipelago)
  N12E123  (covers lat 12-15, lon 123-126: Bicol + Samar)
  N09E120  (covers lat 9-12, lon 120-123: Mindoro, Palawan central)
  N06E120  (covers lat 6-9, lon 120-123: Palawan south)

Class 50 reference: https://esa-worldcover.org/en/data-access (v200 legend).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
import rasterio
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[2]
WORLDCOVER_DIR = ROOT / "detection" / "scan" / "worldcover"
WORLDCOVER_DIR.mkdir(parents=True, exist_ok=True)
# Same stride as ncr_scan.py -- must match exactly so tile_ids align with the
# scan grid, otherwise validation against existing detections fails.
TILE_DEG_LAT = 0.00216
TILE_DEG_LON = 0.00224
HALF = 0.0011  # used only for the 240m sample window in WorldCover

WC_BASE = "https://esa-worldcover.s3.amazonaws.com/v200/2021/map"
BUILT_UP_CLASS = 50


def tile_name(lat: int, lon: int) -> str:
    """ESA WorldCover tile name from SW-corner integer coords."""
    lat_str = f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}"
    lon_str = f"{'E' if lon >= 0 else 'W'}{abs(lon):03d}"
    return f"{lat_str}{lon_str}"


def download_tile(name: str) -> Path:
    """Download a WorldCover GeoTIFF if not cached. ~130MB each."""
    out = WORLDCOVER_DIR / f"ESA_WorldCover_10m_2021_v200_{name}_Map.tif"
    if out.exists() and out.stat().st_size > 1_000_000:
        return out
    url = f"{WC_BASE}/ESA_WorldCover_10m_2021_v200_{name}_Map.tif"
    print(f"[wc] downloading {url}")
    req = Request(url, headers={"User-Agent": "solar-map-ph/1.0"})
    with urlopen(req, timeout=300) as r:
        out.write_bytes(r.read())
    print(f"[wc]   -> {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return out


def tiles_covering_bbox(s: float, w: float, n: float, e: float) -> list[str]:
    """Which 3x3 WorldCover tiles cover a bbox?"""
    tiles = []
    lat0 = math.floor(s / 3) * 3
    lat1 = math.ceil(n / 3) * 3
    lon0 = math.floor(w / 3) * 3
    lon1 = math.ceil(e / 3) * 3
    for lat in range(lat0, lat1, 3):
        for lon in range(lon0, lon1, 3):
            tiles.append(tile_name(lat, lon))
    return tiles


def grid_centers(bbox: tuple[float, float, float, float]) -> list[tuple[float, float]]:
    """Same 240m stride as ncr_scan.py -- must match exactly."""
    s, w, n, e = bbox
    lats = np.arange(s + TILE_DEG_LAT / 2, n, TILE_DEG_LAT)
    lons = np.arange(w + TILE_DEG_LON / 2, e, TILE_DEG_LON)
    return [(float(la), float(lo)) for la in lats for lo in lons]


def built_up_fraction(ds, lat: float, lon: float) -> float:
    """Sample the 240m square around (lat, lon) in WorldCover and return class-50 fraction."""
    minlon = lon - HALF
    minlat = lat - HALF
    maxlon = lon + HALF
    maxlat = lat + HALF
    try:
        win = from_bounds(minlon, minlat, maxlon, maxlat, ds.transform)
    except Exception:
        return 0.0
    win = win.round_offsets().round_lengths()
    if win.width <= 0 or win.height <= 0:
        return 0.0
    arr = ds.read(1, window=win)
    if arr.size == 0:
        return 0.0
    return float((arr == BUILT_UP_CLASS).sum()) / float(arr.size)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", required=True, help="south,west,north,east")
    ap.add_argument("--threshold", type=float, default=0.05,
                    help="Min built-up fraction to keep tile (default: 0.05 = 5%%)")
    ap.add_argument("--out", required=True, help="Output JSON: {tile_id: builtup_fraction}")
    ap.add_argument("--validate-against",
                    help="Optional: GeoJSON with high-conf tiles to verify pre-filter doesn't drop them")
    args = ap.parse_args()

    bbox = tuple(float(x) for x in args.bbox.split(","))
    s, w, n, e = bbox

    needed = tiles_covering_bbox(s, w, n, e)
    print(f"[prefilter] WorldCover tiles needed: {needed}")
    paths = [download_tile(t) for t in needed]

    centers = grid_centers(bbox)
    print(f"[prefilter] grid: {len(centers)} 240m cells in bbox={bbox}")

    # Open all tiles; sample each cell from whichever tile covers it.
    datasets = [rasterio.open(p) for p in paths]
    out_map: dict[str, float] = {}
    n_kept = 0
    n_dropped = 0
    for i, (lat, lon) in enumerate(centers):
        # Find the dataset that bounds this point
        ds = None
        for d in datasets:
            b = d.bounds
            if b.left <= lon <= b.right and b.bottom <= lat <= b.top:
                ds = d
                break
        if ds is None:
            continue
        f = built_up_fraction(ds, lat, lon)
        tid = f"{lat:.5f}_{lon:.5f}"
        out_map[tid] = round(f, 4)
        if f >= args.threshold:
            n_kept += 1
        else:
            n_dropped += 1
        if i and i % 5000 == 0:
            print(f"[prefilter]  {i}/{len(centers)}  kept={n_kept}  dropped={n_dropped}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "bbox": bbox,
        "threshold": args.threshold,
        "n_total": len(out_map),
        "n_kept": n_kept,
        "n_dropped": n_dropped,
        "drop_rate": n_dropped / max(1, len(out_map)),
        "by_tile": out_map,
    }, indent=2))
    print(f"[prefilter] wrote {out_path}")
    print(f"[prefilter] kept {n_kept}/{len(out_map)} ({100*n_kept/max(1,len(out_map)):.1f}%) threshold={args.threshold}")

    # Validation: if a high-conf GeoJSON is supplied, ensure none of its tiles are dropped
    if args.validate_against:
        fc = json.loads(Path(args.validate_against).read_text())
        high = [f for f in fc.get("features", []) if f["properties"].get("tier") == "high"]
        dropped_high = []
        for h in high:
            lon = h["geometry"]["coordinates"][0]
            lat = h["geometry"]["coordinates"][1]
            tid = f"{lat:.5f}_{lon:.5f}"
            f_val = out_map.get(tid)
            if f_val is None or f_val < args.threshold:
                dropped_high.append({"tile_id": tid, "lat": lat, "lon": lon,
                                     "score": h["properties"].get("score"),
                                     "builtup": f_val})
        print(f"[prefilter] validation: {len(high)} high-conf tiles checked")
        if dropped_high:
            print(f"[prefilter] DROPPED {len(dropped_high)} high-conf tiles by pre-filter:")
            for d in dropped_high[:10]:
                print(f"  {d}")
            return 1
        else:
            print("[prefilter] OK: no high-conf detections lost by pre-filter")
            return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
