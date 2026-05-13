"""V3 classifier: same shape as v2 but trained on the cleaned-label dataset.

Outputs:
  detection/train/clf_v3.joblib
  detection/train/clf_v3_metrics.json

Reads detection/train/dataset_v3.npz produced by build_dataset_v3.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "detection" / "train" / "dataset_v3.npz"
CLF = ROOT / "detection" / "train" / "clf_v3.joblib"
METRICS = ROOT / "detection" / "train" / "clf_v3_metrics.json"


def main() -> int:
    data = np.load(DS, allow_pickle=False)
    X = data["X"]
    y = data["y"]
    src = data["src"]
    print(f"[v3-train] X={X.shape}  pos={int((y == 1).sum())}  neg={int((y == 0).sum())}")
    unique_sources = sorted(set(src.tolist()))
    print(f"[v3-train] unique sources: {len(unique_sources)}")

    rng = np.random.default_rng(42)
    pos_sources = sorted(set(src[y == 1].tolist()))
    neg_sources = sorted(set(src[y == 0].tolist()))
    rng.shuffle(np.array(pos_sources))
    rng.shuffle(np.array(neg_sources))
    K = 5
    pos_folds = [pos_sources[i::K] for i in range(K)]
    neg_folds = [neg_sources[i::K] for i in range(K)]

    per_source_results: dict[str, dict] = {}
    for fold in range(K):
        held_pos = set(pos_folds[fold])
        held_neg = set(neg_folds[fold])
        held = held_pos | held_neg
        train_mask = np.array([s not in held for s in src])
        val_mask = np.array([s in held for s in src])

        clf = LogisticRegression(max_iter=2000, C=1.0, class_weight="balanced", random_state=42)
        clf.fit(X[train_mask], y[train_mask])
        scores = clf.predict_proba(X[val_mask])[:, 1]
        val_src = src[val_mask]
        val_y = y[val_mask]

        for s in held:
            mask = val_src == s
            if not mask.any():
                continue
            true_label = int(val_y[mask][0])
            sc = scores[mask]
            per_source_results[s] = {
                "fold": fold,
                "true_label": true_label,
                "max_score": float(sc.max()),
                "mean_score": float(sc.mean()),
                "n": int(mask.sum()),
            }

        n_held_pos = sum(1 for s in held if y[src == s][0] == 1)
        n_held_neg = sum(1 for s in held if y[src == s][0] == 0)
        print(
            f"  fold {fold}: train={train_mask.sum()} val={val_mask.sum()} held_pos={n_held_pos} held_neg={n_held_neg}"
        )

    pos_results = [r for r in per_source_results.values() if r["true_label"] == 1]
    neg_results = [r for r in per_source_results.values() if r["true_label"] == 0]
    pos_scores = sorted(r["max_score"] for r in pos_results)
    neg_scores = sorted(r["max_score"] for r in neg_results)
    print()
    print(f"[v3-train] CV pos sources: {len(pos_scores)}  neg sources: {len(neg_scores)}")
    if pos_scores:
        print(
            f"  pos max_score 5-num: min={min(pos_scores):.3f} q1={pos_scores[len(pos_scores) // 4]:.3f} med={pos_scores[len(pos_scores) // 2]:.3f} q3={pos_scores[3 * len(pos_scores) // 4]:.3f} max={max(pos_scores):.3f}"
        )
    if neg_scores:
        print(
            f"  neg max_score 5-num: min={min(neg_scores):.3f} q1={neg_scores[len(neg_scores) // 4]:.3f} med={neg_scores[len(neg_scores) // 2]:.3f} q3={neg_scores[3 * len(neg_scores) // 4]:.3f} max={max(neg_scores):.3f}"
        )

    all_scores = sorted(set(pos_scores + neg_scores))
    best_f1 = (-1.0, None, 0, 0, 0, 0)
    high_precision_thresh = None
    # Also report metrics @ t=0.85 specifically (the deployed threshold) for v2/v3 comparability
    fixed_t = 0.85
    fixed_metrics = None
    for t in all_scores:
        tp = sum(1 for s in pos_scores if s >= t)
        fp = sum(1 for s in neg_scores if s >= t)
        fn = sum(1 for s in pos_scores if s < t)
        tn = sum(1 for s in neg_scores if s < t)
        if tp + fp == 0:
            continue
        precision = tp / (tp + fp)
        recall = tp / max(1, tp + fn)
        f1 = 2 * precision * recall / max(1e-9, precision + recall)
        if f1 > best_f1[0]:
            best_f1 = (f1, t, tp, fp, fn, tn)
        if precision >= 0.9 and recall >= 0.5 and high_precision_thresh is None:
            high_precision_thresh = (t, precision, recall, tp, fp, fn, tn)

    # Compute fixed-threshold metrics (any t passing through 0.85 in score list)
    tp = sum(1 for s in pos_scores if s >= fixed_t)
    fp = sum(1 for s in neg_scores if s >= fixed_t)
    fn = sum(1 for s in pos_scores if s < fixed_t)
    tn = sum(1 for s in neg_scores if s < fixed_t)
    if tp + fp > 0:
        p_85 = tp / (tp + fp)
        r_85 = tp / max(1, tp + fn)
        f_85 = 2 * p_85 * r_85 / max(1e-9, p_85 + r_85)
        fixed_metrics = {
            "threshold": fixed_t,
            "precision": p_85,
            "recall": r_85,
            "f1": f_85,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
        }

    f1, t, tp, fp, fn, tn = best_f1
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    print()
    print(
        f"[v3-train] BEST F1: t={t:.4f}  TP={tp} FP={fp} FN={fn} TN={tn}  precision={precision:.3f} recall={recall:.3f} F1={f1:.3f}"
    )
    if fixed_metrics is not None:
        print(
            f"[v3-train] @ t=0.85: P={fixed_metrics['precision']:.3f} R={fixed_metrics['recall']:.3f} F1={fixed_metrics['f1']:.3f}"
        )
    if high_precision_thresh is not None:
        ht, hp, hr, htp, hfp, hfn, htn = high_precision_thresh
        print(f"[v3-train] HIGH-PRECISION (P>=0.9, R>=0.5): t={ht:.4f}  precision={hp:.3f} recall={hr:.3f}")

    final = LogisticRegression(max_iter=2000, C=1.0, class_weight="balanced", random_state=42)
    final.fit(X, y)
    joblib.dump(
        {
            "clf": final,
            "threshold_best_f1": float(t) if t else None,
            "threshold_high_precision": float(high_precision_thresh[0]) if high_precision_thresh else None,
            "feature_dim": int(X.shape[1]),
            "encoder": "openai/clip-vit-large-patch14",
            "version": "v3",
        },
        CLF,
    )
    print(f"[v3-train] saved -> {CLF}")

    metrics = {
        "best_f1": {
            "f1": f1,
            "threshold": t,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": precision,
            "recall": recall,
        },
        "at_threshold_0p85": fixed_metrics,
        "high_precision": (
            {
                "threshold": high_precision_thresh[0],
                "precision": high_precision_thresh[1],
                "recall": high_precision_thresh[2],
            }
            if high_precision_thresh
            else None
        ),
        "n_pos_sources": len(pos_scores),
        "n_neg_sources": len(neg_scores),
        "per_source": per_source_results,
    }
    METRICS.write_text(json.dumps(metrics, indent=2))
    print(f"[v3-train] saved metrics -> {METRICS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
