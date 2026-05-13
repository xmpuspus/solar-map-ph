"""Phase-2 clf_v4_calibrated: train base LR on 80% set, fit Platt sigmoid on 20% holdout.

Pipeline:
  1. Load dataset_v4.npz (already CLIP-embedded by build_dataset_v3.py)
  2. Apply train/holdout split from v4_calibrated/holdout_split.json
  3. Train base LogisticRegression on the 80% set (same hyper-params as clf_v3/v4)
  4. Score the 20% holdout with the base classifier
  5. Fit Platt scaling: P_calibrated = sigmoid(A * decision_function(x) + B)
  6. Sweep thresholds on the calibrated scores; record observed precision/recall/F1
     at every threshold from 0.0 to 1.0 in 0.01 increments + key reference points.
  7. Save calibrated artifact + calibration table.

The calibrated classifier is structured as: base_lr -> Platt sigmoid. Use it via
the `score_calibrated()` helper or the saved `clf_v4_calibrated.joblib` bundle.

Outputs:
  detection/train/v4_calibrated/clf_v4_calibrated.joblib
  detection/train/v4_calibrated/clf_v4_calibration.json
  detection/train/v4_calibrated/clf_v4_holdout_scores.csv
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

ROOT = Path(__file__).resolve().parents[3]
DATASET = ROOT / "detection" / "train" / "dataset_v4.npz"
SPLIT = ROOT / "detection" / "train" / "v4_calibrated" / "holdout_split.json"
CLF_OUT = ROOT / "detection" / "train" / "v4_calibrated" / "clf_v4_calibrated.joblib"
CALIB_OUT = ROOT / "detection" / "train" / "v4_calibrated" / "clf_v4_calibration.json"
SCORES_CSV = ROOT / "detection" / "train" / "v4_calibrated" / "clf_v4_holdout_scores.csv"


def main() -> int:
    d = np.load(DATASET, allow_pickle=False)
    X, y, src = d["X"], d["y"], d["src"]
    split = json.loads(SPLIT.read_text())
    holdout_pos = set(split["holdout_pos_sources"])
    holdout_neg = set(split["holdout_neg_sources"])
    holdout = holdout_pos | holdout_neg
    holdout_mask = np.array([s in holdout for s in src])
    train_mask = ~holdout_mask
    print(f"train rows: {train_mask.sum()}  holdout rows: {holdout_mask.sum()}")
    print(f"  holdout pos rows: {(y[holdout_mask] == 1).sum()}  holdout neg rows: {(y[holdout_mask] == 0).sum()}")

    # ===== 1. Train base LR on 80% =====
    base = LogisticRegression(max_iter=2000, C=1.0, class_weight="balanced", random_state=42)
    base.fit(X[train_mask], y[train_mask])

    # ===== 2. Score holdout (raw decision function and uncalibrated proba) =====
    raw_holdout = base.decision_function(X[holdout_mask])
    uncal_holdout = base.predict_proba(X[holdout_mask])[:, 1]
    y_holdout = y[holdout_mask]
    src_holdout = src[holdout_mask]

    # ===== 3. Fit Platt sigmoid on holdout =====
    # Platt: y = sigmoid(A * raw + B); fit via LR on the 1D raw scores
    platt = LogisticRegression(C=1e6, solver="lbfgs", max_iter=1000)
    platt.fit(raw_holdout.reshape(-1, 1), y_holdout)
    A = float(platt.coef_[0, 0])
    B = float(platt.intercept_[0])
    print(f"Platt sigmoid: P = sigmoid({A:.4f} * raw + {B:.4f})")

    def calibrate(raw: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-(A * raw + B)))

    cal_holdout = calibrate(raw_holdout)

    # ===== 3b. Alternative: isotonic regression, for comparison =====
    # Isotonic is non-parametric and often beats Platt when the decision
    # function distribution isn't sigmoidal. We fit on the holdout and report
    # Brier score for both methods. Production stays on Platt for now (smooth,
    # monotone, fewer parameters), but the comparison is here to justify it.
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(raw_holdout, y_holdout)
    iso_holdout = iso.predict(raw_holdout)
    brier_platt = float(brier_score_loss(y_holdout, cal_holdout))
    brier_iso = float(brier_score_loss(y_holdout, iso_holdout))
    brier_uncal = float(brier_score_loss(y_holdout, uncal_holdout))
    print(f"Brier score (lower=better): "
          f"uncalibrated={brier_uncal:.4f}  Platt={brier_platt:.4f}  isotonic={brier_iso:.4f}")

    # ===== 4. Source-level holdout: max calibrated score per source =====
    src_max_cal = {}
    src_max_uncal = {}
    src_label = {}
    for s, lab, c, u in zip(src_holdout, y_holdout, cal_holdout, uncal_holdout):
        if s not in src_max_cal or c > src_max_cal[s]:
            src_max_cal[s] = float(c)
            src_max_uncal[s] = float(u)
            src_label[s] = int(lab)

    # ===== 5. Sweep thresholds on calibrated scores =====
    pos_cal = sorted([src_max_cal[s] for s in src_max_cal if src_label[s] == 1])
    neg_cal = sorted([src_max_cal[s] for s in src_max_cal if src_label[s] == 0])
    print(f"holdout pos sources: {len(pos_cal)}  neg sources: {len(neg_cal)}")
    if pos_cal:
        print(f"  pos cal 5-num: min={min(pos_cal):.3f} med={pos_cal[len(pos_cal)//2]:.3f} max={max(pos_cal):.3f}")
    if neg_cal:
        print(f"  neg cal 5-num: min={min(neg_cal):.3f} med={neg_cal[len(neg_cal)//2]:.3f} max={max(neg_cal):.3f}")

    sweep = []
    for t in [round(x * 0.01, 2) for x in range(0, 101)]:
        tp = sum(1 for s in pos_cal if s >= t)
        fp = sum(1 for s in neg_cal if s >= t)
        fn = sum(1 for s in pos_cal if s < t)
        tn = sum(1 for s in neg_cal if s < t)
        if tp + fp == 0:
            p = None
        else:
            p = tp / (tp + fp)
        r = tp / max(1, tp + fn)
        f1 = 2 * (p or 0) * r / max(1e-9, (p or 0) + r) if p is not None else 0.0
        sweep.append({"threshold": t, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
                      "precision": p, "recall": r, "f1": f1})

    # Find threshold that yields >=0.99 precision (closest to user's 99.5% target)
    high_p_target = None
    for row in sweep:
        if row["precision"] is not None and row["precision"] >= 0.99 and row["recall"] >= 0.5:
            high_p_target = row
            break
    # And the row at threshold 0.85 (the deployed threshold)
    row_t085 = next((r for r in sweep if abs(r["threshold"] - 0.85) < 1e-9), None)

    print()
    print(f"Holdout @ calibrated t=0.85: {row_t085}")
    if high_p_target:
        print(f"First t with P>=0.99 R>=0.5: {high_p_target}")

    # ===== 6. Save calibrated artifact =====
    bundle = {
        "base_clf": base,
        "platt_A": A,
        "platt_B": B,
        "feature_dim": int(X.shape[1]),
        "encoder": "openai/clip-vit-large-patch14",
        "version": "v4_calibrated",
        "calibration_seed": int(json.loads(SPLIT.read_text())["seed"]),
        "n_train_rows": int(train_mask.sum()),
        "n_holdout_rows": int(holdout_mask.sum()),
    }
    joblib.dump(bundle, CLF_OUT)
    print(f"saved -> {CLF_OUT}")

    calib_summary = {
        "platt": {"A": A, "B": B, "formula": "P = sigmoid(A * decision_function(x) + B)"},
        "brier_scores": {
            "uncalibrated": brier_uncal,
            "platt": brier_platt,
            "isotonic": brier_iso,
            "note": "Lower is better. Platt is shipped; isotonic shown for comparison.",
        },
        "split_seed": json.loads(SPLIT.read_text())["seed"],
        "n_holdout_pos_sources": len(pos_cal),
        "n_holdout_neg_sources": len(neg_cal),
        "n_train_rows": int(train_mask.sum()),
        "n_holdout_rows": int(holdout_mask.sum()),
        "at_calibrated_t085": row_t085,
        "first_t_p_ge_099_r_ge_05": high_p_target,
        "sweep": sweep,
    }
    CALIB_OUT.write_text(json.dumps(calib_summary, indent=2))
    print(f"saved -> {CALIB_OUT}")

    # ===== 7. Per-source CSV for transparency =====
    lines = ["source,label,raw_decision,uncalibrated_proba,calibrated_proba"]
    for s in sorted(src_max_cal):
        lab = src_label[s]
        # find one representative row
        idx = list(src_holdout).index(s)
        lines.append(f"{s},{lab},{raw_holdout[idx]:.6f},{uncal_holdout[idx]:.6f},{cal_holdout[idx]:.6f}")
    SCORES_CSV.write_text("\n".join(lines))
    print(f"saved -> {SCORES_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
