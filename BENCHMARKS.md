# Benchmarks

SolarMap.PH publishes one canonical operating point and a precision-recall sweep on an honest 20% held-out source-disjoint split. This page tracks how the shipped classifier compares to alternatives and to other published rooftop solar detectors.

## Headline (clf_v4 calibrated)

| Split | Threshold | Precision | Recall | F1 |
|---|---|---|---|---|
| Honest 20% holdout, source-disjoint | 0.85 | 0.959 | 0.797 | 0.870 |
| Honest 20% holdout, source-disjoint | best-F1 (~0.5) | ~0.91 | ~0.91 | ~0.91 |

Brier scores on the same holdout: uncalibrated 0.0794, Platt 0.0743, isotonic 0.0670. PR / ROC / reliability diagrams are in `docs/figures/` (regenerate with `make plots`).

5-fold group-aware CV on the training set scored higher (F1 ~0.94 best-F1, ~0.90 at t=0.85). The held-out split is the conservative read; LOSO leaks via shared augmentations.

## Encoder ablation

All rows run through the same training pipeline, same logistic-regression head, same Platt calibration, same honest 20% holdout.

| Encoder | F1 at t=0.85 | Notes |
|---|---|---|
| `openai/clip-vit-large-patch14` | 0.870 | shipped |
| `facebook/dinov2-large` | 0.830 | self-supervised, 4 pt lower |
| `allenai/satlas-pretrain` (Aerial_SwinB_SI) | 0.727 | tuned for segmentation, not classification |

Encoders **not yet tested** (PRs welcome):

- `ibm-nasa-geospatial/Prithvi-100M` (NASA-IBM, 2023)
- Meta SkySense (2024)
- SatMAE (Cong et al., 2023)
- CLIPSeg (CIDAS, 2022)
- RemoteCLIP (Liu et al., 2024)
- GeoCLIP (CISIP, 2024)

To run an encoder against the calibrated holdout, see `detection/train/v4_calibrated/encoder_ablation.py` and the methodology in `MODEL_CARD.md`.

## Cross-method comparison (sketch)

This section is a placeholder for community-driven cross-method comparison. The benchmarks below have not yet been run head-to-head against `clf_v4`; they are listed so that a researcher comparing against SolarMap.PH knows where the rigorous comparison sits.

| Method | Region | Reported F1 | Test set | Notes |
|---|---|---|---|---|
| SolarMap.PH clf_v4 (this work) | Greater Metro Manila | 0.870 | 98-source honest holdout | this README |
| Stanford DeepSolar (2018) | California, USA | ~0.94 | 5,000-image curated test | rooftop + ground-mount mixed, different imagery |
| Microsoft Planetary Computer solar | global | (research, no single F1) | various | open methodology |
| Google Sunroof (2015) | USA | (product, not research) | proprietary | no public test set |
| IGN-French-PV (2024) | France | 0.90+ | open benchmark | uses ground truth from net-metering database |

**How to add a row:** open a PR with the head-to-head numbers on a shared test set. If the test set is private, document a leave-one-region-out evaluation on a public test image collection.

## Honest holdout construction

- 20% of sources (both positive and negative classes) reserved before any active-learning rounds.
- Split seed `4242`, deterministic via `holdout_split.py`.
- Every augmentation of a held-out source stays in the holdout; no leakage from the augmentation distribution.
- Active-learning additions (`v3conf_*`, `v3promo_*`, `v3fp_*`) intentionally stay in TRAIN so the holdout remains an out-of-distribution check against the original OSM/GT pool. This is documented in `MODEL_CARD.md` under known biases.

## What we have not measured (yet)

- **Spatial-block CV.** The shipped CV is source-disjoint (each OSM tag is one group). Spatially adjacent OSM tags on the same building still go to the same group, but spatially adjacent tags on different OSM tags can cross folds. A 500 m or 1 km block CV would tighten the upper bound on real recall; PRs welcome.
- **120 m stride pass.** The production scan uses 240 m no-overlap stride. A 120 m pass over a 5 km x 5 km test patch would quantify recall loss at array boundaries; we have not run this yet.
- **Confusion analysis vs solar water heaters, skylights, white-painted reflective roofs.** Listed as the biggest reviewer concern; an `error_analysis.md` will follow with 50 hand-labeled FPs.
- **Multi-temporal trend.** Esri vintage in PH is 1-3 years stale; we cannot reliably measure year-over-year deltas with the current imagery source.

## Reproducing these numbers

```bash
pip install -r requirements.txt
make train          # trains from cached embeddings, deterministic
make calibrate      # produces clf_v4_calibration.json with the sweep + Brier scores
make plots          # renders docs/figures/{pr,roc,reliability}_curve.{svg,png}
```

If your numbers differ, run `make hash-verify` first to confirm you have the canonical classifier (sha256 `56900722a8427be4`). If the hash differs, your pinned versions probably drifted; reinstall from `requirements.txt`.
