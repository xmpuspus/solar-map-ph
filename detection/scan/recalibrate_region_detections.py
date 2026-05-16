"""Apply the v1.2 per-domain calibration to the ALREADY-PUBLISHED region
detections (no re-scan, no re-fetch — cached tiles only).

v1.2 computed a per-domain Platt fit for cebu/iloilo/calabarzon but never
applied it to the published GeoJSONs, so the live map still showed the
uncalibrated clf_v4 scores. This closes that: for each calibrated region it
re-embeds the cached detection tiles, runs clf_v5.decision_function, applies
that region's Platt sigmoid, and writes a calibrated probability + a
recomputed tier back onto the existing point features.

Honest scope: this calibrates the SCORES of the existing clf_v4-selected
detection set. It does not change which roofs were found — only a full
clf_v5 re-scan would change recall. Calibrated precision, clf_v4-bounded
recall. Documented as such.

Per feature (calibrated regions only):
  score             kept as-is (raw clf_v4 proba, provenance)
  score_calibrated  sigmoid(A*clf_v5_decision_function + B), per-region A,B
  calibrated        true
  tier              recomputed from score_calibrated:
                      >=0.85 high, >=0.70 candidate, else low_confidence

Uncalibrated regions (davao/cdo/legazpi/bacolod) are left untouched
(calibrated:false stays implicit; they remain honest candidate inventory).

Run:
    python detection/scan/recalibrate_region_detections.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "site" / "public" / "data"
TILES_DIR = ROOT / "detection" / "scan" / "tiles"
SCAN_DIR = ROOT / "detection" / "scan"
CLF_V5 = ROOT / "detection" / "train" / "clf_v5.joblib"
CALIB = ROOT / "detection" / "train" / "v5_region_holdout" / "clf_v5_calibration.json"

HIGH = 0.85
CAND = 0.70


def main() -> int:
    calib = json.loads(CALIB.read_text())
    platt = {
        s: v["platt"]
        for s, v in calib["regions"].items()
        if v.get("calibration_status") == "calibrated"
    }
    if not platt:
        print("[recal] no calibrated regions in clf_v5_calibration.json", file=sys.stderr)
        return 1
    print(f"[recal] calibrated regions: {sorted(platt)}")

    import joblib

    sys.path.insert(0, str(SCAN_DIR))
    from ncr_scan import embed_batch, load_clip
    from PIL import Image

    base = joblib.load(CLF_V5)["clf"]
    processor, model = load_clip()

    summary = {}
    for slug, ab in platt.items():
        A, B = float(ab["A"]), float(ab["B"])
        gj_path = DATA_DIR / f"rooftop_solar_{slug}.geojson"
        gj = json.loads(gj_path.read_text())
        feats = gj["features"]

        # Embed cached detection tiles in batches, preserving order.
        idx_with_tile, imgs = [], []
        cal_scores: dict[int, float] = {}
        for i, f in enumerate(feats):
            tid = f["properties"]["tile_id"]
            p = TILES_DIR / slug / f"{tid}.jpg"
            if not p.exists() or p.stat().st_size <= 1000:
                continue
            try:
                imgs.append(Image.open(p).convert("RGB"))
                idx_with_tile.append(i)
            except Exception:
                continue
            if len(imgs) >= 16:
                emb = embed_batch(processor, model, imgs)
                df = base.decision_function(emb)
                pc = 1.0 / (1.0 + np.exp(-(A * df + B)))
                for j, fi in enumerate(idx_with_tile):
                    cal_scores[fi] = float(pc[j])
                idx_with_tile, imgs = [], []
        if imgs:
            emb = embed_batch(processor, model, imgs)
            df = base.decision_function(emb)
            pc = 1.0 / (1.0 + np.exp(-(A * df + B)))
            for j, fi in enumerate(idx_with_tile):
                cal_scores[fi] = float(pc[j])

        tiers = {"high": 0, "candidate": 0, "low_confidence": 0}
        for i, f in enumerate(feats):
            if i not in cal_scores:
                # Tile missing from cache: cannot calibrate honestly; mark it.
                f["properties"]["calibrated"] = False
                continue
            sc = round(cal_scores[i], 4)
            f["properties"]["score_calibrated"] = sc
            f["properties"]["calibrated"] = True
            tier = "high" if sc >= HIGH else ("candidate" if sc >= CAND else "low_confidence")
            f["properties"]["tier"] = tier
            tiers[tier] += 1

        gj["_meta"]["calibration"] = (
            f"Per-domain Platt (clf_v5, scan-realistic holdout): "
            f"P = sigmoid({A:.3f}*decision_function + {B:.3f}). "
            f"Calibrated scores on the clf_v4-selected detection set "
            f"(precision calibrated; recall clf_v4-bounded, no re-scan)."
        )
        gj["_meta"]["calibrated"] = True
        gj["_meta"]["n_high_confidence"] = tiers["high"]
        gj["_meta"]["n_candidate"] = tiers["candidate"]
        gj["_meta"]["n_low_confidence"] = tiers["low_confidence"]
        gj_path.write_text(json.dumps(gj))

        # Recompute city counts on the calibrated tier.
        cc_path = DATA_DIR / f"city_detection_counts_{slug}.json"
        if cc_path.exists():
            cc = json.loads(cc_path.read_text())
            per_city: dict[str, dict] = {}
            for f in feats:
                pr = f["properties"]
                city = pr.get("lgu_name")
                if not city:
                    continue
                c = per_city.setdefault(city, {"name": city, "province": pr.get("province"),
                                                "n_high": 0, "n_candidate": 0,
                                                "n_low_confidence": 0, "n_new_high": 0,
                                                "sum_kwp_high": 0.0})
                t = pr.get("tier")
                if t == "high":
                    c["n_high"] += 1
                    if pr.get("osm_status") == "new":
                        c["n_new_high"] += 1
                elif t == "candidate":
                    c["n_candidate"] += 1
                else:
                    c["n_low_confidence"] += 1
            rows = sorted(per_city.values(), key=lambda r: -r["n_high"])
            cc["rows"] = rows
            cc["_meta"]["n_total_high"] = tiers["high"]
            cc["_meta"]["n_total_candidate"] = tiers["candidate"]
            cc["_meta"]["n_total_low_confidence"] = tiers["low_confidence"]
            cc["_meta"]["n_cities_with_detections"] = len(rows)
            cc["_meta"]["calibrated"] = True
            cc_path.write_text(json.dumps(cc, indent=1))

        summary[slug] = tiers
        print(f"[recal] {slug:11s} calibrated: high={tiers['high']} "
              f"candidate={tiers['candidate']} low_confidence={tiers['low_confidence']} "
              f"(was clf_v4-tiered)")

    print(f"\n[recal] done: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
