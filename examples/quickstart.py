#!/usr/bin/env python3
"""Five-minute quickstart for researchers.

Loads the shipped clf_v4 classifier, scores a few cached training-set rows,
and prints calibrated probabilities. No network, no GPU, no Earth Engine
auth. Runs in under 10 seconds on a laptop.

Usage:

    python examples/quickstart.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ghost_watts


def main() -> int:
    print(f"ghost-watts {ghost_watts.__version__}\n")

    # 1. Load the shipped, hash-verified classifier bundle.
    bundle = ghost_watts.load_classifier_bundle(verify_hash=True)
    print("classifier bundle loaded:")
    print(f"  encoder       = {bundle.get('encoder')}")
    print(f"  feature_dim   = {bundle.get('feature_dim', 768)}")
    print(f"  version       = {bundle.get('version')}")
    print()

    # 2. Grab a handful of real CLIP embeddings from the committed dataset.
    dataset = np.load(ROOT / "detection" / "train" / "dataset_v4.npz", allow_pickle=False)
    X, y, src = dataset["X"], dataset["y"], dataset["src"]
    rng = np.random.default_rng(42)
    sample_idx = rng.choice(np.arange(len(X)), size=10, replace=False)

    # 3. Score them. Calibrated -> [0, 1] probability of "contains rooftop solar".
    scores = ghost_watts.score_features(X[sample_idx], bundle, calibrated=True)

    print("source                              label  calibrated_p   verdict")
    print("-" * 70)
    for i, s in enumerate(sample_idx):
        label = int(y[s])
        prob = float(scores[i])
        verdict = "solar" if prob >= 0.85 else ("candidate" if prob >= 0.70 else "none")
        print(f"{str(src[s])[:32]:<34}    {label}      {prob:.4f}        {verdict}")

    print()
    print("Threshold 0.85 corresponds to the production operating point:")
    print("  Precision 95.9%, Recall 79.7%, F1 0.870 on the honest 20% holdout.")
    print()
    print("Next steps:")
    print("  - examples/run_on_new_region.md to run on a different geography")
    print("  - MODEL_CARD.md for intended use, biases, and ethics")
    print("  - BENCHMARKS.md for the precision-recall sweep and ablation table")
    return 0


if __name__ == "__main__":
    sys.exit(main())
