"""Stable Python API for ghost-watts.

The repo's training and scan scripts live under `detection/` and are organized
for batch execution. This module gives researchers a single import surface for
the common operations: load the classifier, score features, generate a tile
grid for a new region.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

import numpy as np

EXPECTED_CLF_HASH = "56900722a8427be4"


def grid_centers(
    bbox: tuple[float, float, float, float],
    tile_meters: float = 240.0,
) -> list[tuple[float, float]]:
    """Yield (lat, lon) centers tiling `bbox` at `tile_meters` stride.

    `bbox` is (south, west, north, east) in EPSG:4326 degrees. The tile size is
    converted to degrees-of-latitude using a local-flat approximation, which
    is sub-meter-accurate over any single tile and good enough across a city.

    Use this to extend the scan to a new region without depending on the
    NCR-specific constants in `detection.scan.ncr_scan`.

    Example
    -------
    >>> # 240m grid over a 5km square around downtown Cebu City
    >>> centers = grid_centers((10.295, 123.875, 10.340, 123.925))
    >>> len(centers) > 100
    True
    """
    s, w, n, e = bbox
    if not (s < n and w < e):
        raise ValueError(f"degenerate bbox: {bbox}")
    mean_lat = (s + n) / 2.0
    deg_per_meter_lat = 1.0 / 111_320.0
    deg_per_meter_lon = 1.0 / (111_320.0 * max(0.01, math.cos(math.radians(mean_lat))))
    step_lat = tile_meters * deg_per_meter_lat
    step_lon = tile_meters * deg_per_meter_lon
    lats = np.arange(s + step_lat / 2, n, step_lat)
    lons = np.arange(w + step_lon / 2, e, step_lon)
    return [(float(la), float(lo)) for la in lats for lo in lons]


def load_classifier_bundle(
    path: str | Path | None = None,
    verify_hash: bool = True,
) -> dict[str, Any]:
    """Load the shipped clf_v4 joblib bundle.

    `path` defaults to the in-repo `detection/train/clf_v4.joblib`. If
    `verify_hash` is True (default), the file's sha256 prefix is asserted to
    match `EXPECTED_CLF_HASH`. Set `verify_hash=False` only when loading a
    fork or experimental classifier; arbitrary joblib files execute code
    during deserialization, so unverified loads are a security boundary.
    """
    import joblib

    if path is None:
        path = Path(__file__).resolve().parent.parent / "detection" / "train" / "clf_v4.joblib"
    path = Path(path)

    if verify_hash:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        if digest != EXPECTED_CLF_HASH:
            raise ValueError(
                f"clf hash mismatch: got {digest}, expected {EXPECTED_CLF_HASH}. "
                f"Pass verify_hash=False to bypass (security implication: pickle RCE)."
            )

    return joblib.load(path)


def score_features(
    features: np.ndarray,
    bundle: dict[str, Any] | None = None,
    *,
    calibrated: bool = True,
) -> np.ndarray:
    """Score CLIP-ViT-L embedding rows and return probabilities.

    Parameters
    ----------
    features : np.ndarray, shape (n_rows, 768)
        CLIP-ViT-L image embeddings. See `detection/train/build_dataset_v3.py`
        for the canonical embedding code path.
    bundle : dict, optional
        Output of `load_classifier_bundle`. If omitted, the shipped clf_v4
        bundle is loaded with hash verification.
    calibrated : bool, default True
        If True, apply the Platt sigmoid from `v4_calibrated/clf_v4_calibration.json`.
        If False, return the raw sklearn predict_proba.
    """
    if bundle is None:
        bundle = load_classifier_bundle()

    clf = bundle.get("clf") or bundle.get("base_clf")
    if clf is None:
        raise KeyError("bundle has neither 'clf' nor 'base_clf'")

    if not calibrated:
        return clf.predict_proba(features)[:, 1]

    A = bundle.get("platt_A")
    B = bundle.get("platt_B")
    if A is None or B is None:
        # If the bundle has no Platt parameters, load them from the calibration JSON.
        import json

        calib = (
            Path(__file__).resolve().parent.parent
            / "detection"
            / "train"
            / "v4_calibrated"
            / "clf_v4_calibration.json"
        )
        if not calib.exists():
            return clf.predict_proba(features)[:, 1]
        data = json.loads(calib.read_text())
        A = data["platt"]["A"]
        B = data["platt"]["B"]
    raw = clf.decision_function(features)
    return 1.0 / (1.0 + np.exp(-(A * raw + B)))
