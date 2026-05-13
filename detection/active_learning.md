# Active-learning protocol

ghost-watts ran four rounds of active learning between `clf_v2` and `clf_v4`. This page documents the protocol so a researcher running on a new region can apply the same recipe.

## Protocol

For each round:

1. **Score candidates.** Run the current classifier across the candidate pool (in NCR's case: 16,544 tiles on the 240m grid).
2. **Sample two strata.** From the highest-confidence predictions, sample two strata for human review:
   - **High-confidence positives** (score >= 0.85): expected mostly true positives, but the residual false-positive rate at this threshold is the most actionable signal.
   - **High-confidence negatives near the boundary** (0.70 <= score < 0.85): expected to contain a mix of marginal real solar (false negatives the model has under-confidence in) and confounders (skylights, white roofs).
3. **Render verification sheets.** `detection/verify/build_verification_sheets.py` stitches each candidate into a 3x3 PNG with crosshair, plus a tag template (`tags.json`).
4. **Human label.** Each candidate gets one of three tags: `true`, `false`, `ambiguous`. The labeler must consult a higher-resolution view (zoomable Esri tile, Google Maps street view, current Bing Maps) before tagging anything as `false`, because Esri vintage in PH can be 1-3 years stale.
5. **Update training pool.**
   - `true` on a high-confidence positive: confirms the label, no training-data change.
   - `true` on a candidate (0.70-0.85): promote to positive in next training pool.
   - `false` on a high-confidence positive: this is a real false positive. Add as hard negative to the next training pool.
   - `ambiguous`: drop from training pool to reduce label noise.
6. **Retrain and recalibrate.** Rebuild the dataset, retrain the LR head, refit Platt on the same 20% holdout (the holdout is fixed at split seed 4242 across all rounds, so it remains a stable out-of-distribution check).
7. **Stopping criterion.** Stop when the new-positive rate among high-confidence detections falls below 5%, OR the calibrated holdout F1 plateaus across two consecutive rounds, whichever comes first.

## Rounds run so far

| Round | New positives added | New negatives added | F1 delta (calibrated holdout, t=0.85) |
|---|---|---|---|
| 0 (initial) | 312 OSM-tagged | 154 random NCR + 46 GT not_solar | baseline |
| 1 | 4 false-negative rnegs promoted | 2 noisy case studies dropped | +0.02 |
| 2 | 18 from v3conf | 31 from v3fp | +0.04 |
| 3 | 154 new from active-learning batch | 0 | +0.02 |
| 4 | (queued in `detection/verify/round4_queue.json`) | (queued) | (not yet shipped) |

After round 3, the new-positive rate among high-confidence detections is roughly 4.5%, below our 5% threshold. Round 4 is queued mostly as a final audit before public release.

## What we don't do (and why)

- **No uncertainty-based query strategy.** We sample by confidence band, not by entropy. Confidence sampling is simpler to label and the labeler's time is the bottleneck; on a binary task with reasonable separation, uncertainty sampling rarely beats confidence sampling.
- **No automatic relabeling of "ambiguous".** Marginal cases (cloud-shadow on dark roof, panel-shaped HVAC unit, plastic roof sheet) are dropped, not reclassified. Wrong labels cost more than missing labels.
- **No reinforcement-from-deployment.** User-reported false positives from the issue tracker are reviewed manually; we don't auto-update the training pool from them.

## How to run a round on a new region

```bash
# 1. Score
python detection/scan/ncr_scan.py --bbox "..."

# 2. Build verification sheets from the latest scan
python detection/verify/build_verification_sheets.py

# 3. Tag (edit detection/verify/tags.json by hand)

# 4. Rebuild dataset + retrain
python detection/train/build_dataset_v3.py
python detection/train/train_v3.py

# 5. Recalibrate
python detection/train/v4_calibrated/train_calibrated.py
python scripts/plot_pr_curve.py

# 6. Verify deterministic hash
make hash-verify
```

If your hash legitimately moves (new positives in the training pool change the joblib bytes), update `EXPECTED_HASH` in the `Makefile` and bump the `clf_v4` minor version.
