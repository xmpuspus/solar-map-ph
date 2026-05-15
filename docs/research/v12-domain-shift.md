# SolarMap.PH v1.2 step 1 — embedding-space domain shift

Generated 2026-05-15T13:48:20Z. Seed 1202, sample n=400. Encoder `openai/clip-vit-large-patch14`. R = `dataset_v4.npz` X (the distribution clf_v4 trained on). A = NCR scan-tile anchor. T = each region's scan tiles.

## Headline

Domain-AUC saturates and is ordinal-only. The NCR-vs-NCR **anchor floor is domain-AUC=0.8773** and every region's scan-vs-scan AUC is ~0.98-0.99 — expected in 768-d with n=400, where any two finite samples are linearly separable. The trustworthy magnitude is the geographic **centroid cosine**: every region's geo-cos is at or below the anchor floor cos (0.0547), so pure geographic shift is no larger than NCR's own curated-train-vs-natural-scan centroid gap. The dominant fixable problem is the calibration gap that 0.88 floor implies, not geography.

| Region | n | geo cos (A-vs-T) | scan-vs-scan AUC (ordinal) | R-vs-T AUC (confounded) | verdict |
|---|---|---|---|---|---|
| cebu | 400 | **0.0523** | 0.9865 | 0.9912 | within-envelope |
| davao | 400 | **0.0425** | 0.9914 | 0.9932 | within-envelope |
| iloilo | 400 | **0.0468** | 0.9970 | 0.9960 | within-envelope |
| cdo | 400 | **0.0486** | 0.9959 | 0.9944 | within-envelope |
| legazpi | 400 | **0.0515** | 0.9989 | 0.9986 | within-envelope |
| calabarzon | 400 | **0.0378** | 0.9765 | 0.9840 | within-envelope |
| bacolod | 400 | **0.0462** | 0.9948 | 0.9917 | within-envelope |

(anchor floor: geo-cos 0.0547, AUC 0.8773)

## Step-4 directive per region

- **cebu** (within-envelope, geo-cos 0.0523 vs floor 0.0547): region-stratified retrain + per-domain scan-realistic recalibration is sufficient; geographic centroid shift is no larger than NCR's own train-vs-scan gap, so the calibration gap dominates, not geography
- **davao** (within-envelope, geo-cos 0.0425 vs floor 0.0547): region-stratified retrain + per-domain scan-realistic recalibration is sufficient; geographic centroid shift is no larger than NCR's own train-vs-scan gap, so the calibration gap dominates, not geography
- **iloilo** (within-envelope, geo-cos 0.0468 vs floor 0.0547): region-stratified retrain + per-domain scan-realistic recalibration is sufficient; geographic centroid shift is no larger than NCR's own train-vs-scan gap, so the calibration gap dominates, not geography
- **cdo** (within-envelope, geo-cos 0.0486 vs floor 0.0547): region-stratified retrain + per-domain scan-realistic recalibration is sufficient; geographic centroid shift is no larger than NCR's own train-vs-scan gap, so the calibration gap dominates, not geography
- **legazpi** (within-envelope, geo-cos 0.0515 vs floor 0.0547): region-stratified retrain + per-domain scan-realistic recalibration is sufficient; geographic centroid shift is no larger than NCR's own train-vs-scan gap, so the calibration gap dominates, not geography
- **calabarzon** (within-envelope, geo-cos 0.0378 vs floor 0.0547): region-stratified retrain + per-domain scan-realistic recalibration is sufficient; geographic centroid shift is no larger than NCR's own train-vs-scan gap, so the calibration gap dominates, not geography
- **bacolod** (within-envelope, geo-cos 0.0462 vs floor 0.0547): region-stratified retrain + per-domain scan-realistic recalibration is sufficient; geographic centroid shift is no larger than NCR's own train-vs-scan gap, so the calibration gap dominates, not geography

## Decision rule (centroid-relative; AUC is caveated/ordinal)

- within-envelope: geo-cos <= floor_cos + 0.005
- moderate-shift: floor_cos + 0.005 < geo-cos <= floor_cos + 0.03
- severe-OOD: geo-cos > floor_cos + 0.03

## Two findings that gate step 4

1. **Calibration gap (the big one).** The ~0.88 anchor floor means clf_v4's published NCR F1 was measured on the curated OSM holdout, which is itself ~0.88-separable from what the model actually sees in the field — even in NCR. Step-4 per-domain recalibration must use a scan-realistic holdout (step-2 spot-check verdicts + region OSM positives), not the curated OSM set, or the reported precision stays an overestimate everywhere.
2. **Geographic shift (within-envelope, secondary).** Geographic centroid cosine is at or below the in-domain anchor floor for every region — no region is a wild outlier requiring exclusion. This confirms the locked step-4 plan: region-stratified training (folds split by region, not NCR-pooled) + per-domain calibration, applied uniformly to all seven franchises.
