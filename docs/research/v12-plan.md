# SolarMap.PH v1.2 plan (gap-closing round)

Status: in progress. Baseline: `main` at `7999514`, v1.1.1 tagged + released.
v1.1 shipped 7 cross-domain regions (177 high + 167 candidate) using NCR-trained
`clf_v4.joblib` with no retraining and no per-region calibration. This round
closes the credibility gap: the live site implies calibrated, quantitative,
gap-revealing numbers; v1.1 delivers none of that for the new franchises.

## Hard sequencing constraint (locked, do not reorder)

```
1  domain-shift measurement        GATES 4. Tells us which regions a pooled
                                    retrain helps vs which are so OOD a pooled
                                    retrain HURTS them.
2  harvest spot-check labels   ->  + bootstrap region positives via OSM
3  per-region holdout splits   ->  from (2). No holdout = no F1, retraining
                                    alone cannot produce one.
4  hard-neg mine + clf_v5      ->  region-stratified (NOT NCR-pooled), per-domain
   recalibration                   Platt/isotonic. New canonical sha256.
5  region OSM cross-match      ->  every region gets new-vs-mapped status
6  LGU attribution fix         ->  served-LGU-name -> OSM relation-ID mapping
7  per-building SAM + kWp      ->  v1.1 regions get capacity numbers
8  docs + release v1.2.0       ->  MODEL_CARD/methodology/PIA, tag, release, deploy
```

Decision locked: retraining alone does NOT calibrate or quantify. Steps 1+3
MUST precede step 4 or we ship a model we still cannot put an F1 on.

## Step 1 — domain-shift measurement (methodology)

### Question this step answers

Before retraining, quantify how far each v1.1 region's tile distribution sits
from the NCR distribution the classifier learned. This decides the step-4
training strategy per region:

- in-distribution -> pooled retrain with region positives helps
- moderate shift   -> must train region-stratified + per-domain recalibration;
                       pooled retrain alone underperforms
- severe OOD       -> pooled retrain may DEGRADE the region (NCR dominates the
                       loss); needs region-up-weighted labels or region-conditioned
                       calibration, and headline precision must be reported
                       per-region, never pooled

### Distributions compared

- Reference R = the NCR distribution the classifier learned:
  `detection/train/dataset_v4.npz` -> `X` (3795 x 768 CLIP-ViT-L/14 features,
  2775 pos / 1020 neg sources). This is, by construction, the training
  distribution clf_v4 was fit on.
- In-domain anchor A = a random sample of NCR scanned tiles
  (`detection/scan/ncr_tiles/*.jpg`), re-embedded with the same CLIP. NCR scan
  tiles are the *operating* distribution in the in-domain region; they are not
  the curated training set, so A-vs-R is the floor: the irreducible shift that
  exists even with zero domain change. Every region number is read relative to
  this floor, not against zero.
- Target T_region = a random sample (n = min(400, n_cached_tiles)) of cached
  tile JPEGs `detection/scan/tiles/<region>/*.jpg`, re-embedded with the same
  `ncr_scan.load_clip()` + `embed_batch()` so the encoder is byte-identical to
  the scan path. Only `fetch_ok` tiles (size > 1000 bytes) are sampled.

Embeddings are L2-normalized before all distance/MMD computation (CLIP image
features are not unit-norm out of `get_image_features`; normalization makes
cosine and Euclidean consistent and bandwidth selection stable). Sampling seed
is fixed (`SEED = 1202`) so the table is reproducible.

### Metrics (per region, all vs reference R)

1. Centroid cosine distance: `1 - cos(mean(R_norm), mean(T_norm))`.
2. Centroid Euclidean distance: `||mean(R_norm) - mean(T_norm)||_2`.
3. MMD^2, RBF kernel, unbiased estimator, bandwidth = median pairwise distance
   over a pooled subsample (median heuristic). Computed on equal-size
   subsamples (n = 400 each) for comparability across regions.
4. Domain-classifier AUC (headline): 5-fold stratified CV of a
   LogisticRegression(C=1.0, max_iter=2000) trained to separate R from
   T_region on the 768-d features. AUC ~= 0.5 means the two distributions are
   linearly indistinguishable (in-domain); AUC -> 1.0 means fully separable
   (severe OOD). This is the most directly actionable number: it is exactly
   the difficulty a pooled classifier faces in not being dominated by NCR.

Reference R is subsampled to n = 400 (same seed) for metrics 3 and 4 so every
region is compared on balanced classes; metrics 1 and 2 use full R mean.

### Decision rule (gates step 4)

Let `dAUC` = domain-classifier AUC, `cos` = centroid cosine distance, and
`floor_*` = the anchor A-vs-R values.

| Verdict | Condition | Step-4 action |
|---|---|---|
| in-distribution | dAUC < 0.70 and cos < floor_cos + 0.05 | pooled retrain w/ region positives is sufficient |
| moderate-shift | 0.70 <= dAUC < 0.88 | region-stratified retrain + per-domain Platt/isotonic recalibration |
| severe-OOD | dAUC >= 0.88 | region-up-weighted labels or region-conditioned calibration; report precision per-region only, never pooled |

The thresholds are deliberately conservative. The locked step-4 decision is
already "region-stratified, per-domain recalibration"; step 1 quantifies which
regions most require it and flags any region severe enough that pooling it into
one classifier is actively harmful (which would change step 4 from "stratified
CV" to "per-region calibration head").

### Outputs

- `detection/train/domain_shift.py` — deterministic, reads cached embeddings
  and cached tiles only, no network. Re-embeds tile samples (CLIP load is the
  only slow part; batched, CPU/MPS).
- `detection/train/domain_shift.json` — machine-readable per-region metrics +
  verdict + the anchor floor.
- `docs/research/v12-domain-shift.md` — the human-readable table and the
  per-region step-4 directive.

This gate must run and be reviewed before any step-4 training code is written.

### Step 1 RESULT (2026-05-15, reviewed, gate PASSED)

Full output: `docs/research/v12-domain-shift.md`, `detection/train/domain_shift.json`.

Verdict: **all 7 regions within-envelope.** Geographic centroid-cosine
(NCR-scan vs region-scan) is 0.038–0.052, at or below the in-domain anchor
floor cos of 0.0547 for every region. Pure geographic shift is no larger than
NCR's own curated-train-vs-natural-scan centroid gap.

Two measurement facts shaped the reading:

1. **Domain-AUC saturates.** The NCR-vs-NCR anchor is already domain-AUC=0.877
   and every scan-vs-scan AUC is ~0.98–0.99 — expected in 768-d with n=400,
   where any two finite samples are linearly separable. AUC is therefore
   ordinal-only (calabarzon nearest 0.976 → legazpi furthest 0.999, ordering
   matches geography), not an absolute OOD measure. Centroid cosine + MMD are
   the magnitude of record.
2. **The calibration gap is the dominant, fixable problem.** The 0.877 anchor
   means clf_v4's published NCR F1 was measured on the curated OSM holdout,
   which is itself ~0.88-separable from the field scan distribution even
   within NCR. So the published cross-region precision is an overestimate
   everywhere, not just in the new franchises.

Step-4 directive (confirmed, applied uniformly to all 7 regions): region-
stratified retrain (folds split by region, not NCR-pooled) + per-domain
recalibration fit on a **scan-realistic holdout** (step-3: OSM-roof +
spot-check), never the curated OSM set. No region is OOD enough to exclude or
to need a region-conditioned head.

## Step 2 — harvest spot-check labels + OSM positive bootstrap

- Parse all `docs/screenshots/qa-2026-05/region-spot-check/<region>_findings.md`
  markdown verdict tables (32 rows total: cebu 8, davao 5, iloilo 5, cdo 5,
  legazpi 1, calabarzon 5, bacolod 3). Verdict text -> label:
  - "REAL rooftop solar" / "Confirmed" -> `rooftop` (positive)
  - "GROUND-MOUNT" -> `ground_mount` (hard negative for rooftop head)
  - "FALSE POSITIVE" / blue-roof -> `blue_roof_fp` (hard negative)
- Emit `detection/train/region_labels.jsonl`: one row per verdict
  `{region, tile_id, lat, lon, score, label, source:"spotcheck", findings_file}`.
- Bootstrap region positives: generalize `fetch_osm_solar.py` to take a region
  bbox from `regions.json`, query Overpass `generator:source=solar` /
  `generator:method=photovoltaic` per region, write
  `detection/bootstrap/osm_solar_<region>.geojson`. These are community-verified
  positives for the holdout and for clf_v5 region-stratified training.

## Step 3 — per-region labeled holdout splits

- From step-2 labels + OSM positives, build
  `detection/train/v5_region_holdout/holdout_split.json` extending the existing
  seeded-source-split discipline (`holdout_split.py`, seed family 42xx) but
  stratified by region. Each region with >= N labels gets its own held-out
  positive + hard-negative sources, never seen in training, used for honest
  per-region precision/recall and per-domain Platt fitting.
- Regions below the minimum label count are flagged "uncalibrated (n too low)"
  and stay reported as candidate inventory, not calibrated — honest is better
  than a fake CI.

## Step 4 — hard-negative mine + clf_v5 + per-domain recalibration

- Hard-negative curation: ground-mount solar farms (the dominant cross-domain
  FP: NCR Valenzuela, Cebu Naga, CDO x2) + blue/monochrome industrial roofs
  (Legazpi stadium). Source from the step-2 `ground_mount`/`blue_roof_fp` rows
  plus targeted OSM `generator:source=solar` + `location=ground` and a curated
  tile pull. Add as new negative sources to a `dataset_v5.npz`.
- Train `clf_v5` region-stratified: CV folds split by region (not NCR-pooled)
  so reported metrics are per-domain. Same LR hyper-params for comparability.
- Recalibrate Platt + isotonic per domain on the step-3 region holdouts.
- Deterministic-hash discipline: produce `clf_v5.joblib`, compute new canonical
  sha256, update `Makefile` (`CLF`, `EXPECTED_HASH`), `scripts/verify_clf.py`
  (`DEFAULT_EXPECTED_PREFIX`), `scripts/verify_v11_release.py`
  (`expected_hash_prefix`, `CLF_PATH`, `MANIFEST_PATH`). `make hash-verify`
  must pass on the new hash.

## Step 5 — region-aware OSM cross-match

- Generalize `match_against_osm.py` to iterate every region: for each
  `rooftop_solar_<region>.geojson` find nearest OSM solar tag from
  `osm_solar_<region>.geojson` (step 2) within 200 m -> set
  `osm_status` per feature and recompute `n_new_high` per city. This is what
  the "X% not on any prior public map" thesis requires for the new franchises.

## Step 6 — LGU city-attribution fix

- Root cause: `aggregate_region.py:assign_city` returns `None` when the served
  LGU's OSM admin polygon uses a non-canonical name (EB Magalona/Bacolod,
  Mandaue/Cebu) so detections silently drop from city tables.
- Build `pipeline/regions/served_lgu_osm_map.json`: served-LGU-name ->
  OSM relation ID, fetch the missing polygons via Overpass relation query, add
  to `<region>_lgus.geojson`. Re-aggregate; verify zero `lgu_name: null` for
  in-bbox detections (or an explicit documented out-of-franchise bucket).

## Step 7 — per-building SAM + kWp for v1.1 regions

- Reuse `sam_panel_segments.py` per region. Output per-building geometry +
  `kwp_estimate`, but the published region GeoJSON stays point-tile only until
  this step; SAM output must pass `check_region_no_pii.py` (Point geometry,
  no PII keys) — capacity is attached as a tile property, not a building
  polygon, to preserve the privacy boundary.

## Step 8 — docs + release v1.2.0

- Update `MODEL_CARD.md` (cross-domain regime, per-region calibration table,
  domain-shift caveat), site `/methodology` page, the PIA.
- `make verify-v11` (now clf_v5 hash) must be N PASS / 0 FAIL.
- Bump `solar_map_ph/__init__.py` + `pyproject.toml` to 1.2.0, CHANGELOG.
- Tag `v1.2.0`, push, `gh release create` (Zenodo auto-archives).
- Manual `cd site && vercel deploy --prod --yes` (git auto-deploy is broken;
  Vercel root is `site/`, mirror `regions.json` into `site/src/data/`).
- Playwright-verify the live site serves the new `_meta`.

## Privacy boundary (unchanged)

v1.1 regions stay tile-granularity until step 7 adds SAM. SAM output must pass
`check_region_no_pii` / no residential geometry. Conservative civic language on
all computed analytics; disclaimer on every analytics surface.
