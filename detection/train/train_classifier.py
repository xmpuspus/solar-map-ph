"""Train a linear classifier on CLIP-ViT-L embeddings of PH solar tiles.

Validation strategy: GROUP-aware leave-one-out (LOSO) by source. For each
unique source tile, hold out ALL its augmentations as the validation set
and train on the rest. This is the right protocol when your dataset is
heavy on augmentations of a tiny pool of sources -- random shuffle would
leak.

Outputs:
  detection/train/clf.joblib                 the trained logistic regression
  detection/train/clf_metrics.json           per-source val results
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_fscore_support

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "detection" / "train" / "dataset.npz"
CLF_OUT = ROOT / "detection" / "train" / "clf.joblib"
METRICS_OUT = ROOT / "detection" / "train" / "clf_metrics.json"


def main() -> int:
    data = np.load(DS, allow_pickle=False)
    X = data["X"]
    y = data["y"]
    src = data["src"]
    aug = data["aug"]
    print(f"[clf] dataset: X={X.shape} y={y.shape} unique_sources={len(set(src.tolist()))}")

    unique_sources = sorted(set(src.tolist()))
    pos_sources = sorted(set(src[y == 1].tolist()))
    neg_sources = sorted(set(src[y == 0].tolist()))
    print(f"[clf] positive sources: {pos_sources}")
    print(f"[clf] negative sources: {len(neg_sources)} (first 5: {neg_sources[:5]})")

    # Per-source LOSO: hold out a source, train on the rest, predict on held out
    val_rows = []
    for held in unique_sources:
        train_mask = src != held
        val_mask = src == held
        clf = LogisticRegression(max_iter=2000, C=1.0, class_weight="balanced", random_state=42)
        clf.fit(X[train_mask], y[train_mask])
        scores = clf.predict_proba(X[val_mask])[:, 1]
        true_label = int(y[val_mask][0])
        # Aggregate per-source: max score over all augs of that source
        pred_score = float(scores.max())
        val_rows.append({
            "source": held,
            "true_label": true_label,
            "max_score": pred_score,
            "mean_score": float(scores.mean()),
            "n_augs": int(val_mask.sum()),
        })
        print(f"  src={held:30s} true={true_label}  max_score={pred_score:.4f}  mean_score={scores.mean():.4f}")

    # Threshold sweep on per-source max_score
    pos_scores = sorted(r["max_score"] for r in val_rows if r["true_label"] == 1)
    neg_scores = sorted(r["max_score"] for r in val_rows if r["true_label"] == 0)
    print()
    print(f"[clf] LOSO results: {len(pos_scores)} positives, {len(neg_scores)} negatives")
    print(f"  pos max_scores: {[round(s, 3) for s in pos_scores]}")
    print(f"  neg max_scores 5-num: min={min(neg_scores):.3f} q1={neg_scores[len(neg_scores)//4]:.3f} med={neg_scores[len(neg_scores)//2]:.3f} q3={neg_scores[3*len(neg_scores)//4]:.3f} max={max(neg_scores):.3f}")

    # Threshold sweep
    all_scores = sorted(set(pos_scores + neg_scores))
    best = (-1.0, None, 0, 0, 0, 0)
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
        if f1 > best[0]:
            best = (f1, t, tp, fp, fn, tn)
    f1, t, tp, fp, fn, tn = best
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    print()
    print(f"[clf] best LOSO threshold: t={t:.4f}")
    print(f"  TP={tp} FP={fp} FN={fn} TN={tn}")
    print(f"  precision={precision:.3f} recall={recall:.3f} F1={f1:.3f}")

    # Train final classifier on FULL dataset
    final = LogisticRegression(max_iter=2000, C=1.0, class_weight="balanced", random_state=42)
    final.fit(X, y)
    joblib.dump({"clf": final, "threshold": float(t), "feature_dim": int(X.shape[1])}, CLF_OUT)
    print(f"[clf] saved final classifier to {CLF_OUT}")

    metrics = {
        "loso": val_rows,
        "best_threshold": float(t),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "pos_scores": pos_scores,
        "neg_scores_5num": [min(neg_scores), neg_scores[len(neg_scores)//4], neg_scores[len(neg_scores)//2], neg_scores[3*len(neg_scores)//4], max(neg_scores)],
    }
    METRICS_OUT.write_text(json.dumps(metrics, indent=2))
    print(f"[clf] saved metrics to {METRICS_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
