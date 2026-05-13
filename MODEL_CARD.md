# Model card: ghost-watts clf_v4 calibrated

| Field | Value |
|---|---|
| Model name | `clf_v4_calibrated` |
| Released | 2026-05-12 |
| Version | 1.0.0 |
| License | MIT |
| Reproducibility | Bit-exact, sha256 prefix `56900722a8427be4` |
| Encoder | `openai/clip-vit-large-patch14` (frozen, 768-dim image embeddings) |
| Classifier head | `sklearn.linear_model.LogisticRegression(C=1.0, class_weight="balanced", max_iter=2000, random_state=42)` |
| Calibrator | Platt sigmoid `P = sigmoid(A * decision_function(x) + B)` with `A=1.2544`, `B=0.4527` |
| Decision threshold (deployed) | 0.85 on calibrated probability |

## Intended use

- Aggregate, city-scale or regional analysis of rooftop solar adoption from public satellite imagery.
- Building-level detection where the goal is research, planning, or open data.
- A starting checkpoint for fine-tuning on a new region.

## Out-of-scope use

- **Not** for permit revocation, tax assessment, code enforcement, or any decision that adversely affects an individual building owner.
- **Not** a substitute for a structural or electrical engineering survey.
- **Not** address-level for residential buildings (residential roofs are intentionally suppressed in published outputs).
- **Not** real-time. Esri World Imagery is 1-3 years stale in the Philippines; installations from 2024-2026 may not yet be visible.

## Performance

Headline numbers below are on an honest 20% held-out source-disjoint split (n = 59 positive sources, 39 negative sources, 490 tiles after augmentation):

| Threshold | Precision | Recall | F1 |
|---|---|---|---|
| 0.85 (deployed) | 0.959 | 0.797 | 0.870 |
| 0.50 (best-F1)  | best F1 region | high recall | 0.91+ |

The 5-fold group-aware cross-validation on the training set scored higher (F1 ~ 0.94 best-F1, ~0.90 at t=0.85). LOSO is a lower bound on test-set performance because shared augmentations of the same source are kept in the same fold; the honest holdout above is the conservative read.

Brier scores on the holdout: uncalibrated 0.0794, Platt 0.0743, isotonic 0.0670. Isotonic wins by ~10% relative; Platt is shipped for smoothness and parameter count, with the isotonic comparison published in `clf_v4_calibration.json` for transparency.

PR / ROC / reliability diagrams are in `docs/figures/`. Regenerate with `make plots`.

## Training data

- **312 OSM-tagged positive locations** in the Meralco franchise area (sources with `power=generator + generator:source=solar` as of 2026-Q2).
- **200 ground-truth negative sources** sampled from non-rooftop-solar imagery (parking lots, plain roofs, vegetation, water).
- **154 random NCR tiles** as putative negatives, four of which were promoted to positives during active-learning rounds when human review revealed undocumented rooftop solar.
- **4-augmented per source** (rotation, flip, brightness, color jitter). Deterministic seeds, see `build_dataset_v3.py:augment`.

Total: 3,795 embedding rows across 555 positive sources and 204 negative sources after augmentation and active-learning cleanup.

Training tiles are Esri World Imagery at 600x600 px (~240 m view, ~0.4 m/px). Imagery vintage in PH is 1-3 years stale.

## Known biases

- **Skews commercial / warehouse-scale.** OSM tags large industrial arrays more reliably than residential 5-10 kWp installs. Recall on small residential systems is lower than the headline; the active-learning rounds shifted this somewhat but the bias is structural.
- **Skews urban Metro Manila.** Training imagery is from NCR; the model has not seen Mindanao roofs, rural roofs, or roofs in different vegetation contexts. Recall is lower outside the training distribution.
- **Day/season skew.** Esri imagery is captured at a single time-of-day per pass; lighting variation across the year was approximated via augmentation, not represented in raw data.
- **Confounds we did not formally test:** solar water heaters (different physical structure but similar texture from above), large skylights, white-painted reflective roofs.
- **Mislabeled OSM positives.** Single-pass community tagging has noise; we estimate 5-10% of the 312 OSM positives may not be visually solar in the Esri tile (because the install was removed, the imagery vintage predates the install, or the tag is misplaced). The active-learning loop catches the most egregious cases.

## Ethics and privacy

- Published per-building dataset suppresses residential roofs. Only commercial, industrial, public, and unclassified buildings are released as polygons. See `SECURITY.md`.
- The Meralco franchise area is named in the dataset because the dataset describes that geography. The project is not affiliated with Manila Electric Company.
- Citation: `ghost-watts (YYYY-QN), https://github.com/xmpuspus/ghost-watts`. See `CITATION.cff`.

## Encoder ablation

Decision: stick with `openai/clip-vit-large-patch14`.

| Encoder | Calibrated holdout F1 at t=0.85 | Notes |
|---|---|---|
| `openai/clip-vit-large-patch14` | 0.870 | shipped |
| `facebook/dinov2-large` | 0.830 | self-supervised, 4 pt lower |
| `allenai/satlas-pretrain` (Aerial_SwinB_SI) | 0.727 | tuned for segmentation, not classification |

Encoders **not yet** tested (work-welcome PRs): `ibm-nasa-geospatial/Prithvi-100M`, Meta SkySense, SatMAE, CLIPSeg, RemoteCLIP, GeoCLIP.

## How to load

```python
import joblib

bundle = joblib.load("detection/train/v4_calibrated/clf_v4_calibrated.joblib")
base = bundle["base_clf"]
A, B = bundle["platt_A"], bundle["platt_B"]

import numpy as np
def calibrated_probability(features_768d: np.ndarray) -> np.ndarray:
    raw = base.decision_function(features_768d)
    return 1.0 / (1.0 + np.exp(-(A * raw + B)))
```

`features_768d` must be CLIP-ViT-L embeddings of 600x600 px Esri tiles (or equivalent ~240 m hi-res aerial views). See `detection/train/build_dataset_v3.py:embed` for the canonical embedding path.

## Reproducibility

```bash
pip install -r requirements.txt
make train
make hash-verify   # asserts sha256 56900722a8427be4
```

Pinned dependencies (`scikit-learn==1.7.2`, `joblib==1.5.2`, `numpy==1.26.4`) make the joblib bytes deterministic across Linux and macOS. Different sklearn versions will produce a different joblib hash; update `EXPECTED_HASH` in the `Makefile` when intentionally upgrading.

## Citation

If you use this model, please cite:

```bibtex
@software{puspus_ghost_watts_2026,
  author       = {Puspus, Xavier},
  title        = {ghost-watts: open-source rooftop solar detection from satellite imagery},
  year         = 2026,
  url          = {https://github.com/xmpuspus/ghost-watts},
}
```
