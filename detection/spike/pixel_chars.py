"""Characterize solar-panel pixel distributions in the case study tiles.

Goal: figure out a defensible color + texture rule that separates panel pixels
from rooftop/parking/road pixels in PH aerial imagery.

For each case study, identify the panel region by hand-coordinates (rough),
extract pixel values, and compare against:
  - other rooftop pixels (non-panel)
  - vegetation pixels
  - road/concrete pixels

Reports HSV / Lab / RGB distributions per region.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "site" / "public" / "case_studies"
OUT = ROOT / "detection" / "spike" / "out" / "pixel_chars.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

# Hand-picked panel regions per 600x600 case study tile.
# Coords are (x0, y0, x1, y1) bounding the dominant panel array.
# Eyeballed from inspection.
PANEL_REGIONS = {
    "meycauayan": (10, 320, 230, 540),     # panel array on left of warehouse
    "carmona":    (180, 220, 380, 420),    # panel grid mid-frame
    "dasmarinas": (200, 280, 460, 480),    # solar array on industrial roof
    "makati":     (430, 320, 570, 460),    # blue-roof region (might be panel or paint)
    "san_mateo":  (220, 240, 440, 440),    # roof with array
    "valenzuela": (160, 240, 480, 460),    # warehouse panel region
}


def rgb_to_hsv(rgb: np.ndarray) -> np.ndarray:
    """Vectorized HSV conversion. rgb: (H, W, 3) uint8 -> (H, W, 3) float."""
    rgb = rgb.astype(np.float32) / 255.0
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    cmax = rgb.max(axis=-1)
    cmin = rgb.min(axis=-1)
    delta = cmax - cmin
    h = np.zeros_like(cmax)
    mask = delta > 1e-6
    rmax = (cmax == r) & mask
    gmax = (cmax == g) & mask
    bmax = (cmax == b) & mask
    h[rmax] = ((g[rmax] - b[rmax]) / delta[rmax]) % 6
    h[gmax] = (b[gmax] - r[gmax]) / delta[gmax] + 2
    h[bmax] = (r[bmax] - g[bmax]) / delta[bmax] + 4
    h = (h / 6.0) * 360.0
    s = np.where(cmax > 1e-6, delta / cmax, 0.0)
    v = cmax
    return np.stack([h, s, v], axis=-1)


def stats(arr: np.ndarray) -> dict:
    return {
        "mean": [round(float(x), 3) for x in arr.mean(axis=0)],
        "std": [round(float(x), 3) for x in arr.std(axis=0)],
        "p10": [round(float(x), 3) for x in np.percentile(arr, 10, axis=0)],
        "p50": [round(float(x), 3) for x in np.percentile(arr, 50, axis=0)],
        "p90": [round(float(x), 3) for x in np.percentile(arr, 90, axis=0)],
    }


def main() -> int:
    out: dict = {}
    for case_id in sorted(PANEL_REGIONS.keys()):
        path = CASES / f"{case_id}.jpg"
        img = np.array(Image.open(path).convert("RGB"))
        H, W = img.shape[:2]
        x0, y0, x1, y1 = PANEL_REGIONS[case_id]
        panel_rgb = img[y0:y1, x0:x1].reshape(-1, 3)
        # Background = full image minus panel region
        mask = np.ones((H, W), dtype=bool)
        mask[y0:y1, x0:x1] = False
        bg_rgb = img[mask].reshape(-1, 3)
        # HSV
        panel_hsv = rgb_to_hsv(img[y0:y1, x0:x1]).reshape(-1, 3)
        bg_hsv = rgb_to_hsv(img.copy())
        bg_hsv = bg_hsv[mask].reshape(-1, 3)
        out[case_id] = {
            "panel_n": int(panel_rgb.shape[0]),
            "bg_n": int(bg_rgb.shape[0]),
            "panel_rgb": stats(panel_rgb),
            "bg_rgb": stats(bg_rgb),
            "panel_hsv": stats(panel_hsv),
            "bg_hsv": stats(bg_hsv),
        }
        print(f"\n{case_id}:")
        print(f"  panel rgb mean: {out[case_id]['panel_rgb']['mean']}  std: {out[case_id]['panel_rgb']['std']}")
        print(f"  bg    rgb mean: {out[case_id]['bg_rgb']['mean']}  std: {out[case_id]['bg_rgb']['std']}")
        print(f"  panel hsv mean: H={out[case_id]['panel_hsv']['mean'][0]:.1f}  S={out[case_id]['panel_hsv']['mean'][1]:.3f}  V={out[case_id]['panel_hsv']['mean'][2]:.3f}")
        print(f"  bg    hsv mean: H={out[case_id]['bg_hsv']['mean'][0]:.1f}  S={out[case_id]['bg_hsv']['mean'][1]:.3f}  V={out[case_id]['bg_hsv']['mean'][2]:.3f}")

    OUT.write_text(json.dumps(out, indent=2))
    print(f"\n[chars] wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
