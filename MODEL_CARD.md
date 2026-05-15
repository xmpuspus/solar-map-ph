# Model card: SolarMap.PH clf_v5 (cross-domain, region-stratified)

| Field | Value |
|---|---|
| Model name | `clf_v5` (+ `clf_v5_calibrated` per-domain bundle) |
| Released | 2026-05-15 (v1.2.0) |
| Supersedes | `clf_v4_calibrated` (v1.0/v1.1, NCR-only calibration) |
| License | MIT |
| Reproducibility | Bit-exact, sha256 prefix `5cc0a093c5279fd9` |
| Encoder | `openai/clip-vit-large-patch14` (frozen, 768-dim image embeddings) |
| Classifier head | `sklearn.linear_model.LogisticRegression(C=1.0, class_weight="balanced", max_iter=2000, random_state=42)` |
| Training | Region-stratified (folds split by region, not NCR-pooled); step-3 per-region holdout + hard-negative pool excluded |
| Calibrator | Per-domain Platt sigmoid on a scan-realistic holdout; only where estimable (see Performance) |
| Decision threshold | 0.85 |

## What changed in v1.2 and why

v1.1 shipped seven cross-domain franchises by applying the NCR-trained
`clf_v4` with no retraining and no per-region calibration. The headline NCR
F1 (0.870) was measured on a curated OSM holdout. The v1.2 round began with a
domain-shift measurement (`docs/research/v12-domain-shift.md`) that found two
things:

1. **Geographic shift is within-envelope.** The pure geographic centroid
   cosine (NCR scan vs each region scan) is 0.038–0.052 for all seven regions,
   at or below the in-domain anchor floor of 0.0547 (NCR's own curated-train
   vs natural-scan gap). No region is out-of-distribution enough to exclude or
   to need a region-specific model. (The domain-classifier AUC saturates near
   1.0 in 768-d with n=400 and is reported only as an ordinal diagnostic, not
   an absolute OOD measure.)
2. **A calibration gap dominates.** A linear probe separates the curated
   `dataset_v4` from the natural scan distribution at AUC≈0.88 *even within
   NCR, same city*. So `clf_v4`'s published precision was measured on a
   distribution ~0.88-separable from what the model actually sees in the
   field. The cross-region precision implied on the live site was an
   overestimate everywhere, not only in the new franchises.

`clf_v5` is the response: region-stratified retraining that adds the
cross-domain positives and the observed false-positive classes, plus
per-domain recalibration fit on the operating (scan) distribution rather than
the curated OSM set.

## Training data

- Inherited `dataset_v4`: 3,795 embedding rows (2,775 pos / 1,020 neg),
  NCR OSM positives + ground-truth + random/hard negatives.
- **+210 region positives**: spot-check-confirmed cross-domain rooftops +
  OSM `location=roof` solar tags in the seven region bboxes.
- **+4 region false-positive hard negatives**: the spot-check-confirmed
  ground-mount + blue-roof FPs (the dominant cross-domain failure classes:
  NCR Valenzuela, Cebu Naga, CDO ×2, Legazpi stadium).
- **+3 OSM ground-mount hard negatives** (`location=ground` / `power=plant`).

Total `dataset_v5`: 4,012 rows. Training excludes the step-3 per-region
holdout tiles and the shared hard-negative pool (56 rows) so the holdout
calibration is honest. `clf_v5` is fit on 3,956 rows.

## Performance

### Honest per-region calibration (scan-realistic holdout)

Per-domain Platt is fit on each region's held-out positives (OSM-roof +
spot-check) against a uniform random sample of that region's scan tiles
(the operating distribution is ~97–99% non-solar, so this is a high-purity
negative proxy; ~1–3% PU contamination biases precision *conservatively*).
A degeneracy guard rejects any non-discriminative fit.

| Region | Calibration | Platt | P@0.85 | R@0.85 | n_pos / n_neg |
|---|---|---|---|---|---|
| cebu | calibrated | A=1.24 B=−2.49 | 1.00 | 0.29 | 21 / 300 |
| iloilo | calibrated | A=1.50 B=−2.43 | 0.80 | 0.27 | 15 / 300 |
| calabarzon | calibrated | A=1.21 B=−2.09 | 0.67 | 0.13 | 16 / 300 |
| davao | uncalibrated (low n) | — | — | — | candidate inventory |
| cdo | uncalibrated (low n) | — | — | — | candidate inventory |
| bacolod | uncalibrated (low n) | — | — | — | candidate inventory |
| legazpi | uncalibrated (low n) | — | — | — | candidate inventory |

These precision figures are conservative lower bounds, not exact CIs: the
holdouts are small (15–21 positives) and the negative class carries bounded
PU noise. They are the first honest per-domain numbers the project has had;
they replace the implied transfer of NCR's 0.959 precision. Recall at the
calibrated 0.85 threshold is deliberately low — the calibrated high-confidence
tier favours precision, the correct bias for a civic tool (fewer false
attributions). The four low-n regions ship as **candidate inventory** with no
precision claim; an honest "uncalibrated" beats a fabricated CI.

### Leave-one-region-out (LORO)

`clf_v5_metrics.json` reports leave-one-region-out recall at the raw 0.85
threshold: 0.13–0.63 across regions. The low raw recall is the calibration
gap made visible (NCR-trained raw scores under-score cross-region rooftops);
it is what per-domain recalibration corrects. LORO precision is not estimable
(the labeled negative pool per held region is <3) and is reported as such,
never as a fabricated 1.0.

### NCR reference (unchanged, clf_v4)

NCR's published detections remain `clf_v4`-scored; v1.2 does not re-scan NCR.
`clf_v4`'s honest 20%-holdout numbers (P=0.959, R=0.797, F1=0.870 at t=0.85)
stand for NCR, now with the documented caveat that this holdout is the
curated OSM split, not the field scan distribution.

## Intended use / out-of-scope

Unchanged from v1.1. Aggregate, city/regional analysis of rooftop solar
adoption from public imagery. **Not** for permit, tax, enforcement, or any
decision adversely affecting an individual building owner. **Not** a
structural/electrical survey. **Not** address-level for residential roofs
(suppressed). The seven cross-domain franchises ship as a candidate inventory;
only cebu/iloilo/calabarzon carry a (conservative) per-domain precision.

## kWp estimates (v1.2)

Per-detection capacity is estimated with SAM (vit_b) panel-mask area within
the detection tile, converted via a deliberately conservative
`KWP_PER_M2 = 0.15` (~6.7 m²/kWp crystalline-Si). It is attached as the
scalar `kwp_estimate` / `panel_area_m2` properties on the existing
point-tile feature — no building polygons, so the privacy boundary and
`scripts/check_region_no_pii.py` are unchanged. Each candidate mask is
verified by the same two-stage filter as the NCR per-building pipeline
(area + colour gate, then a CLIP + clf_v5 semantic check at combined ≥ 0.70)
before its area is counted, so whole dark roofs are not mistaken for panels.
Aggregate across the seven cross-domain regions: **~174 MWp** (Calabarzon
~92, Cebu ~49, Davao ~24, plus Iloilo/CDO/Bacolod ~3–4 each). Legazpi's lone
detection — a known blue-stadium-roof false positive — correctly estimates
**0 kWp** after verification, a sanity check on the method. kWp is a rough
planning estimate, not a metered figure; a civic tool should under- not
over-state.

## Known biases

All v1.1 biases carry over (commercial/warehouse skew, urban-NCR training
skew, imagery vintage, solar-water-heater confound, ~5–10% OSM label noise).
New in v1.2: per-region precision is calibrated for only three of seven
franchises and is a conservative lower bound there; the ground-mount FP class
is in training but not separately reported (a rooftop-vs-ground-mount head
remains the highest-value future addition).

## Ethics and privacy

Unchanged. Residential roofs suppressed. Region GeoJSONs are point-tile only.
Conservative civic language; analytics surfaces carry the standard
disclaimer. The project is not affiliated with any named utility.

## How to load

```python
import joblib, numpy as np

bundle = joblib.load("detection/train/v5_region_holdout/clf_v5_calibrated.joblib")
base = bundle["base_clf"]
platt = bundle["per_region_platt"]  # {region: {"A":..., "B":...}}; may be empty

def calibrated_probability(features_768d, region):
    raw = base.decision_function(features_768d)
    if region in platt:
        A, B = platt[region]["A"], platt[region]["B"]
        return 1.0 / (1.0 + np.exp(-(A * raw + B)))
    return base.predict_proba(features_768d)[:, 1]  # uncalibrated; candidate only
```

## Reproducibility

```bash
pip install -r requirements.txt
make train          # build_dataset_v5 -> train_v5 (deterministic)
make hash-verify    # asserts sha256 5cc0a093c5279fd9
make calibrate      # per-domain Platt on the scan-realistic holdout
```

Pinned deps (`scikit-learn==1.7.2`, `joblib==1.5.2`, `numpy==1.26.4`) make the
joblib bytes deterministic. Update `EXPECTED_HASH` in the `Makefile` when
intentionally upgrading dependencies.

## Citation

```bibtex
@software{puspus_solar_map_ph_2026,
  author = {Puspus, Xavier},
  title  = {SolarMap.PH: open-source rooftop solar detection from satellite imagery},
  year   = 2026,
  url    = {https://github.com/xmpuspus/solar-map-ph},
}
```
