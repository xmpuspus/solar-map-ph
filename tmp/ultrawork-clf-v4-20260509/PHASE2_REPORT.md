# Phase 2 — Held-out Test Set + Platt Calibration (COMPLETE)

## What was done

1. Deterministic 20% holdout split of OSM positive sources (59 sources held, 354 in training).
2. Proportional 20% holdout of negative sources (39 held, 158 in training).
3. Trained base LR on the 80% set with the same hyper-parameters as clf_v4.
4. Fit Platt sigmoid on the 20% holdout: P = sigmoid(1.2916 × raw + 0.1627).
5. Swept thresholds 0.00–1.00 in 0.01 steps and recorded TP/FP/FN/TN/P/R/F1.
6. Saved calibrated bundle, calibration JSON, per-source holdout CSV.

Holdout split was generated from a fixed seed (`SEED=4242`) and persisted to `holdout_split.json`. Re-running on the same dataset_v4.npz reproduces the same split.

## Calibration vs LOSO comparison

LOSO CV is biased upward: augmented variants of the same source can leak into validation. The honest holdout is the OSM ground-truth subset the base classifier never trained on.

| Metric | clf_v4 LOSO | clf_v4 calibrated holdout |
|---|---|---|
| @ t=0.85: precision | 0.988 | **0.959** |
| @ t=0.85: recall | 0.772 | **0.797** |
| @ t=0.85: F1 | 0.867 | **0.870** |
| @ t=0.85: TP / FP | 319 / 4 | 47 / 2 |
| First t with P≥0.99 R≥0.5 | t=0.85 (the deployed threshold) | t=0.97 |

The honest precision at the deployed t=0.85 is 95.9%. To hit 99% precision on honest holdout, the threshold needs to climb to t=0.97 (which costs 14 percentage points of recall).

The gap between LOSO (98.8%) and honest holdout (95.9%) is real signal leakage. Use the calibrated number for any public claim.

## Calibration sweep — key reference rows

| Calibrated t | TP | FP | FN | TN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|
| 0.50 | 56 | 11 | 3 | 28 | 0.836 | 0.949 | 0.889 |
| 0.70 | 53 | 6 | 6 | 33 | 0.898 | 0.898 | 0.898 |
| 0.85 | 47 | 2 | 12 | 37 | **0.959** | **0.797** | 0.870 |
| 0.90 | 45 | 1 | 14 | 38 | 0.978 | 0.763 | 0.857 |
| 0.95 | 41 | 0 | 18 | 39 | 1.000 | 0.695 | 0.820 |
| 0.97 | 39 | 0 | 20 | 39 | 1.000 | 0.661 | 0.796 |

(Computed from `clf_v4_calibration.json["sweep"]`.)

## Production usage

The calibrated bundle wraps the base classifier:

```python
import joblib, numpy as np
b = joblib.load("detection/train/v4_calibrated/clf_v4_calibrated.joblib")
A, B = b["platt_A"], b["platt_B"]
raw = b["base_clf"].decision_function(X)
calibrated_proba = 1 / (1 + np.exp(-(A * raw + B)))
```

For the existing `ncr_scan.py` (which expects a scikit-learn model with `predict_proba`), a thin wrapper class is needed in Phase 4 reproducibility hardening.

## Site copy update

`/methodology` page should be updated to cite **calibrated holdout** numbers when reporting precision (P=95.9% at t=0.85 on a never-trained 20% OSM holdout), not the LOSO 98.8% figure. Phase 4 will handle.

## Artifacts

| Path | Purpose |
|---|---|
| `detection/train/v4_calibrated/holdout_split.py` | Generates the deterministic split |
| `detection/train/v4_calibrated/holdout_split.json` | The split itself (reproducible) |
| `detection/train/v4_calibrated/train_calibrated.py` | Train base + fit Platt + sweep |
| `detection/train/v4_calibrated/clf_v4_calibrated.joblib` | Bundled base + Platt parameters |
| `detection/train/v4_calibrated/clf_v4_calibration.json` | Calibration sweep table + Platt A,B |
| `detection/train/v4_calibrated/clf_v4_holdout_scores.csv` | Per-source raw + calibrated scores |
