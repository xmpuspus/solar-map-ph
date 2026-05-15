"""Step 4c of v1.2: per-domain calibration of clf_v5.

Step 1 showed clf_v4's published precision came from the curated OSM holdout,
~0.88-separable from the field scan distribution even within NCR. So
calibration must be fit on the operating (scan) distribution.

First attempt used only the 4 labeled hard-negatives (ground-mount solar
farms) as the negative class. Per-instance dump showed those negatives score
ABOVE cross-region rooftop positives on the rooftop classifier (the dominant
cross-domain FP class + the calibration gap), so Platt fit an inverted,
degenerate sigmoid and fabricated P@0.85~1.0. That output was rejected.

Correct negative class for per-domain calibration: a random sample of the
region's scan tiles. The operating distribution is ~97-99% non-solar
(detection rate ~1-3% of built-up tiles), so a uniform random sample is a
high-purity negative proxy. Bounded PU contamination (~1-3% true rooftops mis-
labeled negative) biases the precision estimate conservatively (pessimistic),
which is the safe direction for a civic tool. Negatives within EXCLUDE_M of a
known OSM-solar tag or a spot-check rooftop are dropped to cut the dominant
contamination source without using model score (no circularity). The 4 labeled
ground-mount FPs are added as extra hard negatives.

A degeneracy guard still rejects any region whose fit is non-discriminative
(slope A <= MIN_SLOPE, or calibrated mean(pos) <= mean(neg)); that region is
reported calibration_not_estimable, never fabricated.

Outputs:
  detection/train/v5_region_holdout/clf_v5_calibrated.joblib
  detection/train/v5_region_holdout/clf_v5_calibration.json
  detection/train/v5_region_holdout/clf_v5_holdout_scores.csv
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

ROOT = Path(__file__).resolve().parents[3]
DS = ROOT / "detection" / "train" / "dataset_v5.npz"
HOLDOUT = ROOT / "detection" / "train" / "v5_region_holdout" / "holdout_split.json"
BASE_CLF = ROOT / "detection" / "train" / "clf_v5.joblib"
SCAN_DIR = ROOT / "detection" / "scan"
TILES_DIR = SCAN_DIR / "tiles"
OSM_DIR = ROOT / "detection" / "bootstrap"
OUT_CLF = ROOT / "detection" / "train" / "v5_region_holdout" / "clf_v5_calibrated.joblib"
OUT_JSON = ROOT / "detection" / "train" / "v5_region_holdout" / "clf_v5_calibration.json"
OUT_CSV = ROOT / "detection" / "train" / "v5_region_holdout" / "clf_v5_holdout_scores.csv"

DEPLOY_T = 0.85
SEED = 4244
N_NEG = 300        # random scan-tile negatives per region
EXCLUDE_M = 240.0  # drop negatives within one tile of a known solar location
MIN_SLOPE = 0.05   # Platt slope below this -> non-discriminative, reject


def haversine_m(a, b, c, d):
    R = 6_371_000.0
    p1, p2 = math.radians(a), math.radians(c)
    dlat = math.radians(c - a)
    dlon = math.radians(d - b)
    h = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def fit_platt(raw: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    p = LogisticRegression(C=1e6, solver="lbfgs", max_iter=1000)
    p.fit(raw.reshape(-1, 1), y)
    return float(p.coef_[0, 0]), float(p.intercept_[0])


def known_solar_points(slug: str) -> list[tuple[float, float]]:
    pts = []
    osm = OSM_DIR / f"osm_solar_{slug}.geojson"
    if osm.exists():
        for f in json.loads(osm.read_text()).get("features", []):
            lon, lat = f["geometry"]["coordinates"]
            pts.append((lat, lon))
    return pts


def sample_region_negatives(slug: str, exclude: list[tuple[float, float]],
                            embed_batch, processor, model, rng: random.Random):
    """Uniform random scan tiles as a high-purity negative proxy."""
    jsonl = SCAN_DIR / f"{slug}_scan_results.jsonl"
    rows = []
    for line in jsonl.read_text().splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("fetch_ok") and r.get("score") is not None:
            rows.append((r["tile_id"], r["lat"], r["lon"]))
    rng.shuffle(rows)
    from PIL import Image

    chosen, imgs = [], []
    for tid, lat, lon in rows:
        if len(chosen) >= N_NEG:
            break
        if any(haversine_m(lat, lon, kla, klo) < EXCLUDE_M for kla, klo in exclude):
            continue
        p = TILES_DIR / slug / f"{tid}.jpg"
        if not p.exists() or p.stat().st_size <= 1000:
            continue
        try:
            imgs.append(Image.open(p).convert("RGB"))
        except Exception:
            continue
        chosen.append(tid)
    embs = []
    for i in range(0, len(imgs), 16):
        embs.append(embed_batch(processor, model, imgs[i:i + 16]))
    return (np.vstack(embs) if embs else np.empty((0, 768))), len(chosen)


def main() -> int:
    for f in (DS, HOLDOUT, BASE_CLF):
        if not f.exists():
            print(f"[v5-cal] missing {f}", file=sys.stderr)
            return 1

    d = np.load(DS, allow_pickle=True)
    X, tile = d["X"], d["tile"].astype(str)
    base = joblib.load(BASE_CLF)["clf"]
    split = json.loads(HOLDOUT.read_text())
    t2i = {t: i for i, t in enumerate(tile) if t}

    sys.path.insert(0, str(SCAN_DIR))
    from ncr_scan import embed_batch, load_clip

    processor, model = load_clip()
    rng = random.Random(SEED)

    hn_tiles = [f"{h['lat']:.5f}_{h['lon']:.5f}" for h in split["hard_neg_pool"]]
    hn_idx = [t2i[t] for t in hn_tiles if t in t2i]

    regions_out = {}
    csv_lines = ["region,kind,raw_decision,calibrated_proba"]
    for slug, r in split["regions"].items():
        if r["calibration_status"] != "calibrated":
            regions_out[slug] = {"calibration_status": r["calibration_status"],
                                 "note": "too few labels; ships as candidate inventory"}
            continue
        pos_idx = [t2i[t] for t in r["holdout_pos_tile_ids"] if t in t2i]
        if len(pos_idx) < 5:
            regions_out[slug] = {"calibration_status": "uncalibrated_low_n",
                                 "note": f"resolved holdout pos={len(pos_idx)}"}
            continue
        Xpos = X[pos_idx]
        exclude = known_solar_points(slug) + [
            (split["regions"][slug]["positives"][k]["lat"],
             split["regions"][slug]["positives"][k]["lon"])
            for k in range(len(split["regions"][slug]["positives"]))
        ]
        Xneg_rand, n_neg = sample_region_negatives(
            slug, exclude, embed_batch, processor, model, rng)
        Xneg = np.vstack([Xneg_rand, X[hn_idx]]) if hn_idx else Xneg_rand

        raw_pos = base.decision_function(Xpos)
        raw_neg = base.decision_function(Xneg)
        raw = np.concatenate([raw_pos, raw_neg])
        yy = np.concatenate([np.ones(len(raw_pos)), np.zeros(len(raw_neg))]).astype(int)
        A, B = fit_platt(raw, yy)

        def cal(z):
            return 1.0 / (1.0 + np.exp(-(A * z + B)))

        cpos, cneg = cal(raw_pos), cal(raw_neg)
        degenerate = A <= MIN_SLOPE or cpos.mean() <= cneg.mean()
        if degenerate:
            regions_out[slug] = {
                "calibration_status": "calibration_not_estimable",
                "platt_slope_A": round(A, 4),
                "pos_mean_raw": round(float(raw_pos.mean()), 3),
                "neg_mean_raw": round(float(raw_neg.mean()), 3),
                "reason": (
                    "non-discriminative fit (A<=MIN_SLOPE or mean(pos)<=mean(neg)); "
                    "labeled positives and the available negatives are not "
                    "separable in raw score space. Ships as candidate inventory."
                ),
            }
            print(f"[v5-cal] {slug:11s} REJECTED degenerate A={A:.3f}")
            continue

        tp = int((cpos >= DEPLOY_T).sum())
        fp = int((cneg >= DEPLOY_T).sum())
        fn = int((cpos < DEPLOY_T).sum())
        prec = tp / (tp + fp) if (tp + fp) else None
        rec = tp / (tp + fn) if (tp + fn) else None
        regions_out[slug] = {
            "calibration_status": "calibrated",
            "platt": {"A": A, "B": B, "formula": "P = sigmoid(A*decision_function + B)"},
            "n_holdout_pos": len(pos_idx),
            "n_random_neg": n_neg,
            "n_hardneg_ground": len(hn_idx),
            "brier_calibrated": round(float(brier_score_loss(yy, cal(raw))), 4),
            "at_t085": {"precision": prec, "recall": rec, "tp": tp, "fp": fp, "fn": fn},
            "pu_contamination_caveat": (
                "Negatives are a uniform random scan sample (operating "
                "distribution ~97-99% non-solar). ~1-3% of negatives may be "
                "true rooftops (PU noise), biasing precision conservatively. "
                "Treat as a lower bound, not an exact CI."
            ),
        }
        for z, c in zip(raw_pos, cpos):
            csv_lines.append(f"{slug},pos,{z:.5f},{c:.5f}")
        for z, c in zip(raw_neg, cneg):
            csv_lines.append(f"{slug},neg,{z:.5f},{c:.5f}")
        pr = "n/a" if prec is None else f"{prec:.3f}"
        rc = "n/a" if rec is None else f"{rec:.3f}"
        print(f"[v5-cal] {slug:11s} pos={len(pos_idx)} neg={n_neg}+{len(hn_idx)} "
              f"A={A:.3f} B={B:.3f} P@0.85={pr} R@0.85={rc}")

    bundle = {
        "base_clf": base,
        "encoder": "openai/clip-vit-large-patch14",
        "version": "v5_calibrated",
        "per_region_platt": {s: v["platt"] for s, v in regions_out.items() if "platt" in v},
        "calibration_status": {s: v["calibration_status"] for s, v in regions_out.items()},
    }
    joblib.dump(bundle, OUT_CLF)
    OUT_JSON.write_text(json.dumps(
        {"deploy_threshold": DEPLOY_T, "seed": SEED,
         "negative_class": "uniform random region scan tiles (PU proxy) + 4 labeled ground-mount",
         "regions": regions_out}, indent=2))
    OUT_CSV.write_text("\n".join(csv_lines))
    print(f"[v5-cal] wrote {OUT_CLF.name} + {OUT_JSON.name} + {OUT_CSV.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
