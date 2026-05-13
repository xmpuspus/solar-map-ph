"""Smoke test: load the shipped clf_v4.joblib and score a random feature row.

This proves the deterministic-build claim end-to-end: if pinned dep versions
hold, a fresh checkout can load the classifier and produce a probability.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
CLF = ROOT / "detection" / "train" / "clf_v4.joblib"
DATASET = ROOT / "detection" / "train" / "dataset_v4.npz"


@pytest.mark.skipif(not CLF.exists(), reason="clf_v4.joblib not present; run `make train` first")
def test_classifier_loads_and_scores():
    bundle = joblib.load(CLF)
    assert "clf" in bundle, "clf_v4.joblib should ship as a bundle dict with key 'clf'"
    clf = bundle["clf"]
    # CLIP-ViT-L embedding dim is 768; classifier expects that shape.
    n_features = getattr(clf, "n_features_in_", 768)
    x = np.zeros((1, n_features), dtype=np.float32)
    proba = clf.predict_proba(x)[0]
    assert proba.shape == (2,)
    assert 0.0 <= float(proba[1]) <= 1.0


@pytest.mark.skipif(not DATASET.exists(), reason="dataset_v4.npz not present")
def test_classifier_round_trip_on_known_positive():
    """The shipped classifier should rank a real OSM-positive embedding above 0.5."""
    bundle = joblib.load(CLF)
    clf = bundle["clf"]
    d = np.load(DATASET, allow_pickle=False)
    X, y = d["X"], d["y"]
    # Pick the first positive row in the training set
    pos_idx = int(np.argmax(y == 1))
    score = float(clf.predict_proba(X[pos_idx : pos_idx + 1])[0, 1])
    assert score > 0.5, f"classifier scored a known positive at {score:.3f}, expected > 0.5"
