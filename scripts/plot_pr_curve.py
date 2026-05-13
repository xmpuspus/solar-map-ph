#!/usr/bin/env python3
"""Plot the precision-recall curve, ROC, and reliability diagram for clf_v4.

Reads the calibration sweep produced by `train_calibrated.py` and emits
publication-quality SVG + PNG figures into `docs/figures/`. Run after every
recalibration:

    python scripts/plot_pr_curve.py

Inputs:
    detection/train/v4_calibrated/clf_v4_calibration.json
        (sweep over thresholds 0.00..1.00, plus the operating-point summary)
    detection/train/v4_calibrated/clf_v4_holdout_scores.csv  (optional)
        (per-source calibrated probabilities for the reliability diagram)

Outputs:
    docs/figures/pr_curve.svg + .png
    docs/figures/roc_curve.svg + .png
    docs/figures/reliability_diagram.svg + .png (if holdout-scores CSV present)
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
CALIB = ROOT / "detection" / "train" / "v4_calibrated" / "clf_v4_calibration.json"
SCORES_CSV = ROOT / "detection" / "train" / "v4_calibrated" / "clf_v4_holdout_scores.csv"
FIG_DIR = ROOT / "docs" / "figures"


def _save(fig: plt.Figure, name: str) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for ext in ("svg", "png"):
        out = FIG_DIR / f"{name}.{ext}"
        fig.savefig(out, dpi=160, bbox_inches="tight")
        print(f"[plot] -> {out.relative_to(ROOT)}")
    plt.close(fig)


def plot_pr_curve(sweep: list[dict], op: dict) -> None:
    # At very high thresholds, precision becomes undefined (tp+fp==0). Drop
    # those rows for matplotlib; they would otherwise pollute the line with
    # gaps and break fill_between.
    keep = [row for row in sweep if row["precision"] is not None]
    p = [row["precision"] for row in keep]
    r = [row["recall"] for row in keep]
    f1 = [row["f1"] for row in keep]

    fig, ax = plt.subplots(figsize=(6.0, 5.4))
    ax.plot(r, p, color="#0b3b58", lw=2.2, label="clf_v4 calibrated")
    ax.fill_between(r, p, 0, color="#0b3b58", alpha=0.05)
    ax.scatter(
        [op["recall"]],
        [op["precision"]],
        color="#c84630",
        s=80,
        zorder=5,
        edgecolor="white",
        linewidth=1.5,
        label=f"t=0.85 (production)  F1={op['f1']:.3f}",
    )

    best_idx = max(range(len(keep)), key=lambda i: f1[i])
    best = keep[best_idx]
    ax.scatter(
        [best["recall"]],
        [best["precision"]],
        color="#2c5f2d",
        s=70,
        zorder=5,
        edgecolor="white",
        linewidth=1.2,
        marker="^",
        label=f"best F1 t={best['threshold']:.2f}  F1={best['f1']:.3f}",
    )

    ax.set_xlabel("Recall", fontsize=11)
    ax.set_ylabel("Precision", fontsize=11)
    ax.set_xlim(0, 1.02)
    ax.set_ylim(0, 1.02)
    ax.grid(True, linestyle=":", linewidth=0.6, color="#bbbbbb")
    ax.set_title(
        "Precision-Recall  -  clf_v4 calibrated holdout\n"
        f"n_pos_sources={op.get('tp', 0) + op.get('fn', 0)},  "
        f"n_neg_sources={op.get('fp', 0) + op.get('tn', 0)}",
        fontsize=10.5,
    )
    ax.legend(loc="lower left", fontsize=9, frameon=False)
    _save(fig, "pr_curve")


def plot_roc(sweep: list[dict]) -> None:
    # ROC needs FPR vs TPR at each threshold (sweep already has tp/fp/fn/tn)
    tprs = []
    fprs = []
    for r in sweep:
        tp, fp, fn, tn = r["tp"], r["fp"], r["fn"], r["tn"]
        tpr = tp / (tp + fn) if (tp + fn) else 0.0
        fpr = fp / (fp + tn) if (fp + tn) else 0.0
        tprs.append(tpr)
        fprs.append(fpr)

    # Compute AUC by trapezoid (need sorted by FPR)
    pts = sorted(zip(fprs, tprs))
    auc = 0.0
    for i in range(1, len(pts)):
        x0, y0 = pts[i - 1]
        x1, y1 = pts[i]
        auc += (x1 - x0) * (y0 + y1) / 2.0

    fig, ax = plt.subplots(figsize=(6.0, 5.4))
    ax.plot([f for f, _ in pts], [t for _, t in pts], color="#0b3b58", lw=2.2)
    ax.plot([0, 1], [0, 1], color="#bbbbbb", lw=1, linestyle="--")
    ax.set_xlabel("False Positive Rate", fontsize=11)
    ax.set_ylabel("True Positive Rate", fontsize=11)
    ax.set_xlim(0, 1.02)
    ax.set_ylim(0, 1.02)
    ax.set_title(f"ROC  -  clf_v4 calibrated  -  AUC = {auc:.3f}", fontsize=11)
    ax.grid(True, linestyle=":", linewidth=0.6, color="#bbbbbb")
    _save(fig, "roc_curve")


def plot_reliability(scores_csv: Path, n_bins: int = 10) -> None:
    """Per-bin observed-positive-rate vs predicted-probability."""
    rows: list[tuple[float, int]] = []
    with scores_csv.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            # heuristic: any column whose name has 'prob' or 'calibrated'
            score_keys = [k for k in row if "prob" in k.lower() or "calibrat" in k.lower()]
            if not score_keys:
                # fall back: column 1 is source name, column 2 is score, column 3 is label
                cols = list(row.values())
                if len(cols) >= 3:
                    rows.append((float(cols[1]), int(float(cols[2]) > 0.5)))
                continue
            label_key = next((k for k in row if k.lower() in {"label", "y", "truth"}), None)
            if label_key is None:
                continue
            rows.append((float(row[score_keys[0]]), int(float(row[label_key]))))

    if not rows:
        print(f"[plot] WARN: reliability diagram skipped (no usable rows in {scores_csv.name})")
        return

    bin_pred: list[list[float]] = [[] for _ in range(n_bins)]
    bin_true: list[list[int]] = [[] for _ in range(n_bins)]
    for s, y in rows:
        b = min(int(s * n_bins), n_bins - 1)
        bin_pred[b].append(s)
        bin_true[b].append(y)

    xs = []
    ys = []
    sizes = []
    for i in range(n_bins):
        if not bin_pred[i]:
            continue
        xs.append(sum(bin_pred[i]) / len(bin_pred[i]))
        ys.append(sum(bin_true[i]) / len(bin_true[i]))
        sizes.append(len(bin_pred[i]))

    fig, ax = plt.subplots(figsize=(6.0, 5.4))
    ax.plot([0, 1], [0, 1], color="#bbbbbb", lw=1, linestyle="--", label="perfect calibration")
    ax.plot(xs, ys, color="#0b3b58", lw=1.8, marker="o", markersize=5, label="clf_v4")
    for x, y, n in zip(xs, ys, sizes):
        ax.annotate(f"n={n}", (x, y), fontsize=8, color="#666666", xytext=(4, 4), textcoords="offset points")
    ax.set_xlabel("Predicted probability (binned mean)", fontsize=11)
    ax.set_ylabel("Observed positive rate", fontsize=11)
    ax.set_xlim(0, 1.02)
    ax.set_ylim(0, 1.02)
    ax.set_title("Reliability diagram  -  clf_v4 calibrated", fontsize=11)
    ax.grid(True, linestyle=":", linewidth=0.6, color="#bbbbbb")
    ax.legend(loc="upper left", fontsize=9, frameon=False)
    _save(fig, "reliability_diagram")


def main() -> int:
    if not CALIB.exists():
        print(f"[plot] ERROR: {CALIB} not found. Run `make calibrate` first.", file=sys.stderr)
        return 1
    data = json.loads(CALIB.read_text())
    sweep = data.get("sweep") or []
    op = data.get("at_calibrated_t085") or {}
    if not sweep:
        print("[plot] ERROR: calibration JSON has no sweep data", file=sys.stderr)
        return 1
    plot_pr_curve(sweep, op)
    plot_roc(sweep)
    if SCORES_CSV.exists():
        plot_reliability(SCORES_CSV)
    else:
        print(f"[plot] reliability diagram skipped: {SCORES_CSV.name} not present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
