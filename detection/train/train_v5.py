"""Step 4b of v1.2: train clf_v5 region-stratified, deterministically, from
the cached dataset_v5.npz (no network) so the canonical sha256 is reproducible.

Region-stratified, not NCR-pooled (step-1 directive). Strata:
  ncr        all inherited dataset_v4 rows (src osm_/gt_/rneg_/case_/v3*)
  <region>   rows tagged regpos_/regfp_/regground_<region>_*

Honest per-region metric = leave-one-region-out (LORO): for each region, train
on every stratum except that region, score the held region's positives +
hard-negatives, report precision/recall/F1 at the deployed t=0.85. This is the
per-domain number v1.1 never had (it only had n=3-8 spot-checks).

The step-3 per-region holdout tiles + the shared hard-negative pool are
excluded from ALL training and from LORO training folds; they are reserved for
the step-4c per-domain calibration so the Platt fit is honest.

Final clf_v5 = LogisticRegression(max_iter=2000, C=1.0,
class_weight="balanced", random_state=42) fit on all non-holdout rows. Same
hyper-params as clf_v3/v4 for comparability and a deterministic artifact.

Outputs:
  detection/train/clf_v5.joblib
  detection/train/clf_v5_metrics.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "detection" / "train" / "dataset_v5.npz"
HOLDOUT = ROOT / "detection" / "train" / "v5_region_holdout" / "holdout_split.json"
CLF = ROOT / "detection" / "train" / "clf_v5.joblib"
METRICS = ROOT / "detection" / "train" / "clf_v5_metrics.json"

DEPLOY_T = 0.85
LR_KW = dict(max_iter=2000, C=1.0, class_weight="balanced", random_state=42)


def stratum(src: str) -> str:
    for pfx in ("regpos_", "regfp_", "regground_"):
        if src.startswith(pfx):
            return src[len(pfx):].rsplit("_", 1)[0]
    return "ncr"


def prf(pos: np.ndarray, neg: np.ndarray, t: float) -> dict:
    tp = int((pos >= t).sum())
    fp = int((neg >= t).sum())
    fn = int((pos < t).sum())
    tn = int((neg < t).sum())
    p = tp / (tp + fp) if (tp + fp) else None
    r = tp / (tp + fn) if (tp + fn) else None
    f1 = (
        2 * p * r / (p + r)
        if (p is not None and r is not None and (p + r) > 0)
        else None
    )
    return {"t": t, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": p, "recall": r, "f1": f1}


def main() -> int:
    if not DS.exists():
        print("[v5-train] missing dataset_v5.npz; run build_dataset_v5.py", file=sys.stderr)
        return 1
    d = np.load(DS, allow_pickle=True)
    X, y, src, tile = d["X"], d["y"], d["src"].astype(str), d["tile"].astype(str)
    strata = np.array([stratum(s) for s in src])
    print(f"[v5-train] X={X.shape}  pos={int((y==1).sum())} neg={int((y==0).sum())}")
    print(f"[v5-train] strata: "
          f"{ {s:int((strata==s).sum()) for s in sorted(set(strata))} }")

    split = json.loads(HOLDOUT.read_text())
    holdout_tiles: set[str] = set()
    for slug, r in split["regions"].items():
        holdout_tiles.update(r["holdout_pos_tile_ids"])
    for hn in split["hard_neg_pool"]:
        holdout_tiles.add(f"{hn['lat']:.5f}_{hn['lon']:.5f}")
    holdout_mask = np.array([t in holdout_tiles and t != "" for t in tile])
    train_pool = ~holdout_mask
    print(f"[v5-train] holdout rows excluded from all training: {int(holdout_mask.sum())}")

    # ----- Leave-one-region-out honest per-region metrics -----
    region_strata = [s for s in sorted(set(strata)) if s != "ncr"]
    per_region = {}
    for reg in region_strata:
        held = (strata == reg) & train_pool
        pos = held & (y == 1)
        neg = held & (y == 0)
        if pos.sum() == 0 and neg.sum() == 0:
            continue
        train_mask = train_pool & (strata != reg)
        clf = LogisticRegression(**LR_KW)
        clf.fit(X[train_mask], y[train_mask])
        pscore = clf.predict_proba(X[pos])[:, 1] if pos.sum() else np.array([])
        nscore = clf.predict_proba(X[neg])[:, 1] if neg.sum() else np.array([])
        m = prf(pscore, nscore, DEPLOY_T)
        m["n_pos"] = int(pos.sum())
        m["n_neg"] = int(neg.sum())
        # Precision is not estimable without enough negatives. Reporting
        # tp/(tp+0)=1.0 when n_neg=0 is a fabricated metric; null it out and
        # flag it instead. Recall only needs positives, so it stays.
        MIN_NEG = 3
        m["precision_estimable"] = m["n_neg"] >= MIN_NEG
        if not m["precision_estimable"]:
            m["precision"] = None
            m["f1"] = None
        cal = split["regions"].get(reg, {}).get("calibration_status", "unknown")
        m["calibration_status"] = cal
        per_region[reg] = m
        pr = f"{m['precision']:.3f}" if m["precision"] is not None else "n/a(neg<3)"
        rc = f"{m['recall']:.3f}" if m["recall"] is not None else "n/a"
        print(f"  LORO {reg:11s} pos={m['n_pos']:3d} neg={m['n_neg']:3d} "
              f"P={pr} R={rc} ({cal})")

    # ----- Final deterministic fit on all non-holdout rows -----
    final = LogisticRegression(**LR_KW)
    final.fit(X[train_pool], y[train_pool])
    bundle = {
        "clf": final,
        "threshold_best_f1": DEPLOY_T,
        "feature_dim": int(X.shape[1]),
        "encoder": "openai/clip-vit-large-patch14",
        "version": "v5",
        "training": "region-stratified; step-3 holdout + hard-neg pool excluded",
        "n_train_rows": int(train_pool.sum()),
    }
    joblib.dump(bundle, CLF)
    print(f"[v5-train] saved -> {CLF.name}  (n_train={int(train_pool.sum())})")

    metrics = {
        "deploy_threshold": DEPLOY_T,
        "n_total": int(len(X)),
        "n_holdout_excluded": int(holdout_mask.sum()),
        "n_train_rows": int(train_pool.sum()),
        "strata": {s: int((strata == s).sum()) for s in sorted(set(strata))},
        "loro_per_region": per_region,
        "note": (
            "loro_per_region = leave-one-region-out recall (and precision only "
            "where n_neg>=3) at the RAW t=0.85 on scan-realistic positives + "
            "hard negatives. The low cross-region recall at raw t=0.85 is the "
            "calibration gap step 1 predicted: NCR-trained raw scores "
            "systematically under-score cross-region rooftops. The fix is the "
            "step-4c per-domain Platt recalibration, not more training. "
            "precision_estimable=false where the labeled negative pool is too "
            "thin to estimate precision. Regions with "
            "calibration_status=uncalibrated_low_n ship as candidate inventory "
            "in step 8 (honest, no fabricated CI)."
        ),
    }
    METRICS.write_text(json.dumps(metrics, indent=2))
    print(f"[v5-train] saved metrics -> {METRICS.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
