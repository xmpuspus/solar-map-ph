---
library_name: scikit-learn
license: mit
tags:
- rooftop-solar
- remote-sensing
- satellite-imagery
- clip
- logistic-regression
- philippines
- civic-tech
language: en
pipeline_tag: image-classification
datasets:
- esri-world-imagery
- openstreetmap
base_model: openai/clip-vit-large-patch14
model-index:
- name: solar-map-ph-clf-v4
  results:
  - task:
      type: image-classification
    dataset:
      type: custom
      name: SolarMap.PH held-out 20% source-disjoint split
    metrics:
    - type: f1
      value: 0.870
      name: F1 at t=0.85
    - type: precision
      value: 0.959
      name: Precision at t=0.85
    - type: recall
      value: 0.797
      name: Recall at t=0.85
---

# SolarMap.PH classifier (clf_v4)

Frozen `openai/clip-vit-large-patch14` image encoder plus a scikit-learn `LogisticRegression` head, Platt-calibrated on a held-out 20% source-disjoint split. Trained to detect rooftop solar PV installations from 600x600 px Esri World Imagery tiles over Greater Metro Manila, Philippines.

**Reproducibility hash:** `sha256:56900722a8427be404883d5f5bee8850f1f5ed837e150df4c4b1cc991d062609` (prefix `56900722a8427be4`).

The classifier is bit-exact reproducible from the committed `dataset_v4.npz` embeddings cache in the project repo. Verify locally with:

```bash
python3 scripts/verify_clf.py detection/train/clf_v4.joblib
# or
make hash-verify
```

## Intended use

Public-interest research on the gap between informal rooftop solar and the formal net-metering registry in the Philippines. The model is calibrated on Esri World Imagery over Greater Metro Manila; out-of-domain performance is not characterized.

Appropriate use cases:
- Civic-tech research, journalism, and public-policy reporting on rooftop solar adoption.
- Academic encoder-ablation comparisons.
- Region extensions to other Philippine geographies (Cebu, Davao, Iloilo, Cagayan de Oro) with explicit re-validation.

Out-of-scope:
- Per-household enforcement, permit verification, tax records, or any individual-identifying decision.
- Engineering or financial advice for specific installations.
- Adversarial or off-distribution imagery (different satellite source, drone, or composite imagery).

## Model architecture

- Encoder: `openai/clip-vit-large-patch14`, frozen, image projection head, 768-dim embedding.
- Classifier head: `sklearn.linear_model.LogisticRegression`, class-balanced weights, C=1.0, 2000 max iterations.
- Calibration: Platt sigmoid `P = sigmoid(1.2916 * decision_function(x) + 0.1627)` fit on the held-out 20% source-disjoint subset.
- Production threshold: 0.85.

## Training data

- 294 OSM-tagged positives (`generator:source=solar` AND `location=roof`) within the Meralco franchise bounding box, deduplicated to unique buildings.
- 4 case-study positives, 4 promoted random-negative positives surfaced during active learning, 111 v3-confident positives (active-learning round 2).
- 197 negatives: 46 hand-labeled `not_solar` tiles + 150 random tiles drawn from the NCR bounding box + 1 v3 false positive.
- 2 noisy cases dropped.
- 4x augmentation (rotation, flip, color jitter) per source.
- Group-aware 5-fold cross-validation.

## Evaluation

| Metric | Value | Notes |
|---|---|---|
| F1 at t=0.85 (calibrated holdout) | 0.870 | TP=47, FP=2, FN=12, TN=37 |
| Precision at t=0.85 | 0.959 | |
| Recall at t=0.85 | 0.797 | |
| F1 at t=0.85 (5-fold group-aware CV) | 0.867 | TP=271, FP=27, FN=29, TN=173 |

Encoder ablation on the same head and same Platt holdout:
- `openai/clip-vit-large-patch14`: F1 = 0.870, P = 0.959
- `facebook/dinov2-large`: F1 = 0.830 (-4 pt), P = 0.936
- `satlas Aerial_SwinB_SI`: F1 = 0.727 (-14 pt), P = 0.900

## Limitations and biases

- **Imagery vintage.** Esri PH imagery is typically 1-3 years stale. Recent installs (2024-2026) may be missed.
- **Domain shift.** Calibrated on Esri World Imagery over Metro Manila. Performance on other satellite sources or other regions is not characterized.
- **False positives.** Highly reflective non-PV surfaces (skylights, polished metal, water tanks, blue painted metal roofs) score above 0.85 occasionally. Calibration precision is 95.9% on holdout; expect 1 in 25 high-confidence detections to be incorrect.
- **Mount-type confusion.** The model detects panels in imagery regardless of mount type. The largest detection in the production scan (2370 kWp) turned out to be a ground-mount utility-scale solar farm rather than a rooftop install (see `docs/screenshots/qa-2026-05/spot-check/findings.md`). Mount-type classification is a queued post-launch feature.
- **SAM over-segmentation.** Per-roof panel polygons can be fragmented across multiple OSM building footprints, especially on large contiguous installations. The aggregate kWp is conservatively correct; per-building kWp values for the smallest entries (<10 kWp on small OSM ways) may under-allocate the visible array.
- **Class imbalance at deployment.** Even with 95.9% calibrated precision, scanning 16,544 tiles at low base-rate (about 1-2% prevalence) produces a non-trivial false-positive count. The candidate tier (0.70-0.85) is a review surface, not a verified inventory.

## How to use

```python
import joblib
import torch
from PIL import Image
from transformers import CLIPProcessor, CLIPModel

# 1. Verify the hash before loading. joblib.load executes pickle.
import hashlib
EXPECTED = "56900722a8427be4"
with open("clf_v4.joblib", "rb") as f:
    digest = hashlib.sha256(f.read()).hexdigest()
assert digest.startswith(EXPECTED), f"hash mismatch: {digest[:16]}"

# 2. Load CLIP encoder.
device = "cuda" if torch.cuda.is_available() else "cpu"
proc = CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14")
clip = CLIPModel.from_pretrained("openai/clip-vit-large-patch14").to(device).eval()

# 3. Load classifier + calibration.
clf = joblib.load("clf_v4.joblib")
calib = joblib.load("clf_v4_calibrated.joblib")  # contains Platt A/B

def score(img_path):
    img = Image.open(img_path).convert("RGB")
    inputs = proc(images=img, return_tensors="pt").to(device)
    with torch.no_grad():
        feats = clip.get_image_features(**inputs).cpu().numpy()
    raw = clf.decision_function(feats)[0]
    return 1 / (1 + 2.718281828 ** -(calib["platt_A"] * raw + calib["platt_B"]))
```

## Citation

> SolarMap.PH (2026-Q2). Open-source rooftop solar detection from public satellite imagery. https://github.com/xmpuspus/solar-map-ph. CC-BY-4.0.

See `CITATION.cff` in the project repo for the canonical citation format.

## License

- Model weights: MIT (this Hugging Face artifact)
- Dataset embeddings (`dataset_v4.npz` in repo): CC-BY-4.0
- Code in the project repo: MIT
- Per-building GeoJSON published with the project: CC-BY-4.0

## Contact

Author and self-designated Data Protection Officer: Xavier Puspus, `solarmap.ph@gmail.com`. Open issues at https://github.com/xmpuspus/solar-map-ph/issues.

## Related work

See `docs/research/related-work.md` in the project repo. Closest sibling project in the Philippine rooftop-solar mapping space is ICSC's SPECTRUM (July 2025): nationwide coverage, complementary scope. DeepSolar (Stanford, 2018) is the methodological precedent.
