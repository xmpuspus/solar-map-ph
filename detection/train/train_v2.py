"""V2 classifier: logistic regression on CLIP features with proper LOSO eval.

Improvements over v1:
  - Strong positive set (~300 OSM-tagged sources)
  - Random NCR negatives in addition to GT not_solar
  - Per-source LOSO at source granularity (no leakage)
  - Per-source max-score aggregation
  - Threshold sweep optimized for high precision (we want >>0.7 to be useful)

Outputs:
  detection/train/clf_v2.joblib
  detection/train/clf_v2_metrics.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "detection" / "train" / "dataset_v2.npz"
CLF = ROOT / "detection" / "train" / "clf_v2.joblib"
METRICS = ROOT / "detection" / "train" / "clf_v2_metrics.json"


def main() -> int:
    data = np.load(DS, allow_pickle=False)
    X = data["X"]
    y = data["y"]
    src = data["src"]
    print(f"[v2-train] X={X.shape}  pos={int((y==1).sum())}  neg={int((y==0).sum())}")
    unique_sources = sorted(set(src.tolist()))
    print(f"[v2-train] unique sources: {len(unique_sources)}")

    # SOURCE-AWARE LOSO IS EXPENSIVE (300+ folds) -- use 5-fold group splits instead
    # Group sources into 5 folds randomly. Each fold's sources get held out together.
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

        # Aggregate per-source: max score
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
        print(f"  fold {fold}: train={train_mask.sum()} val={val_mask.sum()} held_pos={n_held_pos} held_neg={n_held_neg}")

    pos_results = [r for r in per_source_results.values() if r["true_label"] == 1]
    neg_results = [r for r in per_source_results.values() if r["true_label"] == 0]
    pos_scores = sorted(r["max_score"] for r in pos_results)
    neg_scores = sorted(r["max_score"] for r in neg_results)
    print()
    print(f"[v2-train] CV pos sources: {len(pos_scores)}  neg sources: {len(neg_scores)}")
    print(f"  pos max_score 5-num: min={min(pos_scores):.3f} q1={pos_scores[len(pos_scores)//4]:.3f} med={pos_scores[len(pos_scores)//2]:.3f} q3={pos_scores[3*len(pos_scores)//4]:.3f} max={max(pos_scores):.3f}")
    print(f"  neg max_score 5-num: min={min(neg_scores):.3f} q1={neg_scores[len(neg_scores)//4]:.3f} med={neg_scores[len(neg_scores)//2]:.3f} q3={neg_scores[3*len(neg_scores)//4]:.3f} max={max(neg_scores):.3f}")

    # Threshold sweep -- find best F1 + best precision-floored thresholds
    all_scores = sorted(set(pos_scores + neg_scores))
    best_f1 = (-1.0, None, 0, 0, 0, 0)
    high_precision_thresh = None
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

    f1, t, tp, fp, fn, tn = best_f1
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    print()
    print(f"[v2-train] BEST F1: t={t:.4f}  TP={tp} FP={fp} FN={fn} TN={tn}  precision={precision:.3f} recall={recall:.3f} F1={f1:.3f}")
    if high_precision_thresh is not None:
        ht, hp, hr, htp, hfp, hfn, htn = high_precision_thresh
        print(f"[v2-train] HIGH-PRECISION (P>=0.9, R>=0.5): t={ht:.4f}  TP={htp} FP={hfp} FN={hfn} TN={htn}  precision={hp:.3f} recall={hr:.3f}")
    else:
        print("[v2-train] no t with precision>=0.9 and recall>=0.5")

    # Train final classifier on all data
    final = LogisticRegression(max_iter=2000, C=1.0, class_weight="balanced", random_state=42)
    final.fit(X, y)
    joblib.dump({
        "clf": final,
        "threshold_best_f1": float(t),
        "threshold_high_precision": float(high_precision_thresh[0]) if high_precision_thresh else None,
        "feature_dim": int(X.shape[1]),
        "encoder": "openai/clip-vit-large-patch14",
    }, CLF)
    print(f"[v2-train] saved -> {CLF}")

    # Worst-flagged negatives (likely OSM noise, missing imagery, or true positives we missed)
    worst_neg = sorted(neg_results, key=lambda r: -r["max_score"])[:15]
    # Worst-missed positives (low scores -- candidates for label-noise check)
    worst_pos = sorted(pos_results, key=lambda r: r["max_score"])[:15]
    print()
    print("[v2-train] highest-scored negatives (potential label noise / missed solar):")
    for r in worst_neg:
        s = [k for k, v in per_source_results.items() if v is r][0] if False else "<?>"
    # Re-pull the source name
    src_to_result = {}
    for s in unique_sources:
        for k, v in per_source_results.items():
            if k == s:
                src_to_result[s] = v
    for s, r in sorted(src_to_result.items(), key=lambda kv: -kv[1]["max_score"])[:15]:
        if r["true_label"] == 0:
            print(f"  NEG {s}: max={r['max_score']:.3f}")
    print("\n[v2-train] lowest-scored positives (potential bad OSM tags):")
    for s, r in sorted(src_to_result.items(), key=lambda kv: kv[1]["max_score"])[:15]:
        if r["true_label"] == 1:
            print(f"  POS {s}: max={r['max_score']:.3f}")

    metrics = {
        "best_f1": {"f1": f1, "threshold": t, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
                    "precision": precision, "recall": recall},
        "high_precision": (
            {"threshold": ht, "precision": hp, "recall": hr, "tp": htp, "fp": hfp, "fn": hfn, "tn": htn}
            if high_precision_thresh else None
        ),
        "n_pos_sources": len(pos_scores),
        "n_neg_sources": len(neg_scores),
        "pos_scores_5num": [min(pos_scores), pos_scores[len(pos_scores)//4], pos_scores[len(pos_scores)//2], pos_scores[3*len(pos_scores)//4], max(pos_scores)],
        "neg_scores_5num": [min(neg_scores), neg_scores[len(neg_scores)//4], neg_scores[len(neg_scores)//2], neg_scores[3*len(neg_scores)//4], max(neg_scores)],
        "per_source": per_source_results,
    }
    METRICS.write_text(json.dumps(metrics, indent=2))
    print(f"[v2-train] saved metrics -> {METRICS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
