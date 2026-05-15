# SolarMap.PH

[![CI](https://github.com/xmpuspus/solar-map-ph/actions/workflows/ci.yml/badge.svg)](https://github.com/xmpuspus/solar-map-ph/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)
[![Data: CC-BY-4.0](https://img.shields.io/badge/data-CC--BY--4.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Reproducible build](https://img.shields.io/badge/build-deterministic%20sha256%2056900722-success.svg)](#detection-pipeline-reproducible)
[![F1 0.87](https://img.shields.io/badge/F1-0.87%20%40%20t%3D0.85-success.svg)](MODEL_CARD.md)
[![DOI](https://zenodo.org/badge/1238545684.svg)](https://doi.org/10.5281/zenodo.20178050)


> SolarMap.PH: open-source rooftop solar detection from public satellite imagery. **v1.0** ships Greater Metro Manila as the calibrated reference region (F1 = 0.870, precision 95.9%, recall 79.7% at threshold 0.85 on an honest 20% source-disjoint holdout). **v1.1** extends cross-domain coverage to seven additional Philippine distribution-utility franchise areas — Cebu (VECO), Davao (DLPC), Iloilo (MORE), Cagayan de Oro (CEPALCO), Legazpi (ALECO), the Calabarzon belt south of Meralco, and Bacolod (CENECO) — applying the same `clf_v4.joblib` (sha256 prefix `56900722a8427be4`) without retraining. A frozen CLIP-ViT-L encoder, a sklearn logistic-regression head, Platt sigmoid calibration, and a bit-exact reproducible Docker build.

![SolarMap.PH map of detected rooftop solar across the Philippines](docs/screenshots/map-hero.gif)

<sub>Real recording of the `/map` page (NCR view). (1) Survey of 515 NCR rooftops across 41 cities (280 high-confidence, 235 below threshold, 87% of high-confidence detections absent from any prior public map of solar [footnote on methodology below], 69.9 MWp aggregate from the 384 buildings the per-roof segmenter localized). (2) Click into Quezon City and the sidebar surfaces 36 high-confidence detections, 27 newly identified, 15.6 MWp installed, plus thumbnails of the three largest installations the model found. (3) Zoom in further and click a single roof: per-building card returns kWp estimate, panel area, classifier confidence, OSM way id, and the link to confirm against the building footprint. v1.1 cross-domain detections (Cebu, Davao, Iloilo, CDO, Legazpi, Calabarzon, Bacolod) appear as steel-blue dots on the same map; zoom out for the country-wide view or use `/map?region=cebu` to deep-link. The roof-lookup tool runs entirely in your browser; the address you type is sent to third-party geocoders directly (Photon, Nominatim, Overpass, Esri tiles, PVGIS) and never to a server we control.</sub>

## What's in this repo

- **`detection/`**: the CNN detection pipeline. Bootstraps positives from OpenStreetMap, embeds Esri World Imagery tiles with CLIP-ViT-L (600 px for NCR, 400 px for v1.1 regions because Esri's max-zoom is region-dependent), trains a logistic-regression head with 5-fold group-aware CV, calibrates with Platt sigmoid on an honest 20% holdout, and tiles 16,544 cells across NCR plus 18,000-93,000 cells per v1.1 region on a 240 m grid (after an ESA WorldCover 5% built-up prefilter that drops ocean/forest/farmland). Four rounds of active learning on high-confidence false positives. Outputs per-building polygons for NCR via a SAM auto-mask + color-signature filter + OSM building intersection; v1.1 regions ship at tile granularity (per-building SAM stage queued for v1.2).
- **`pipeline/`**: the Earth Engine quarterly batch + multi-region scaffolding. `pipeline.py` and `validate.py` pull Sentinel-2 NIR/SWIR median, Landsat thermal, and VIIRS nightlights over a region polygon, z-score per signal across cities, blend into a composite, and emit a per-city GeoJSON. `pipeline/regions/regions.json` is the source-of-truth for the v1.1 region config (bbox + franchise + served LGUs); `pipeline/regions/fetch_region_polygons.py` queries OSM Overpass and stitches admin-boundary segments via `shapely.polygonize`.
- **`site/`**: the Astro static site. Pages: homeowner roof-lookup tool (runs in your browser, reaches third-party geocoders directly), an interactive `/map` of all detections (NCR layers + v1.1 cross-domain overlay), `/regions` (per-region status and detection counts), `/methodology`, `/faq`, `/privacy`, `/safety`.
- **`scripts/plot_pr_curve.py`**: regenerates PR + ROC + reliability diagrams from the calibration sweep. Run after every recalibration.
- **`scripts/check_no_residential_leaks.py`**: CI gate that no residential roofs leak into the NCR per-building dataset.
- **`scripts/check_region_no_pii.py`**: CI gate that every v1.1 region GeoJSON is point-tile only — no per-building geometry, no PII fields.
- **`scripts/verify_v11_release.py`**: pre-release gate runner. Asserts every region GeoJSON parses, PII gates pass, classifier hash matches canonical, requirements are pinned, and `site/src/data/regions.json` mirrors `pipeline/regions/regions.json`.
- **`scripts/verify_clf.py`**: hash-verify a classifier `.joblib` before running `joblib.load` on it. Use this on any classifier file received from a third party.
- **`scripts/run_all_v11_regions.sh`**: sequential scanner for the v1.1 cross-domain regions; auto-resumes from cached JSONL.
- **`scripts/dump_top_region_tiles.py`**: print the top-N highest-scoring tiles per region for visual audit.
- **`tests/`**: pytest suite (11 tests) covering grid math, polygon helpers, quarter-to-date logic, and a classifier smoke test.

## What this is not

- Not engineering advice. The homeowner tool is informational. Consult a certified installer.
- Not address-level data. NCR polygons for buildings tagged `is_residential` are suppressed from the published per-building dataset; only commercial, industrial, and public-purpose roofs are released at sub-building resolution. The v1.1 cross-domain regions ship at 240 m tile granularity only — no per-building geometry, so there is no individual-building exposure surface. The homeowner tool runs entirely in your browser; we run no server that logs the address you type.
- Not a calibrated registry for v1.1 regions. NCR is calibrated against a held-out validation split; the v1.1 cross-domain regions are not yet calibrated per region. Treat v1.1 detections as a candidate inventory pending per-region active-learning rounds queued for v1.2.
- Not affiliated with Manila Electric Company, VECO, DLPC, MORE, CEPALCO, ALECO, CENECO, or any other Philippine distribution utility. Franchise names are referenced as the regulatory geography covered by each region scan.
- Not a permit registry, tax record, or code-compliance audit. SolarMap.PH publishes statistical indicators derived from public data. Patterns may have legitimate explanations.

## Privacy and responsible use

SolarMap.PH is a civic-tech research artifact. Inputs are publicly licensed (Esri World Imagery, OpenStreetMap, ESA, Microsoft, NOAA, NASA). Outputs are intended to inform public-interest reporting on the gap between informal rooftop solar and the formal net-metering registry.

The publication boundary:

- City-level aggregates: detection counts, density per km², kWp totals, composite scores. No individual identification.
- Per-building polygons for commercial, industrial, and public-purpose roofs only. Institutional subjects, not natural persons.
- Aggregated counts for residential rooftops: how many, by tag, summed kWp. No geometry, no addresses, no OSM way id.

Residential leaks are blocked at build time by [`scripts/check_no_residential_leaks.py`](scripts/check_no_residential_leaks.py) (NCR per-building) and [`scripts/check_region_no_pii.py`](scripts/check_region_no_pii.py) (v1.1 regions). The build fails if any feature with `is_residential=true` or a residential `building=*` tag reaches `site/public/data/per_building_solar_ncr.geojson`, or if any v1.1 region GeoJSON ships per-building geometry, addresses, or PII-adjacent property keys.

Under RA 10173 (Data Privacy Act of 2012) §3(g), personal information is data that "directly and certainly" identifies a person, alone or "put together with other information." A satellite-derived rooftop polygon alone does not name anyone; the "put together with other information" exposure is the reason residential geometry is withheld entirely. The full posture is documented in [`docs/privacy-impact-assessment.md`](docs/privacy-impact-assessment.md).

- **DPO (self-designated):** Xavier Puspus, `xpuspus@gmail.com`. Formal NPC registration is in scope for the post-launch quarter.
- **Takedown channel:** Open a [GitHub issue with the `takedown` label](https://github.com/xmpuspus/solar-map-ph/issues/new?labels=takedown&template=takedown.md) (preferred, public audit trail) or email `xpuspus@gmail.com` with subject *Takedown request*. Acknowledged within 5 working days; feature removed within 14 working days at the next quarterly republish. For active doxxing concerns, use the [private security advisory](https://github.com/xmpuspus/solar-map-ph/security/advisories/new) form.

> All data sourced from public records (Esri World Imagery, OpenStreetMap, ESA, Microsoft, NOAA, NASA). SolarMap.PH computes statistical indicators only. Specific allegations, if any, require independent investigation and corroboration.

## Quickstart for researchers

The fastest path from `git clone` to a working classifier is under 5 minutes if you already have Python 3.11 and pip:

```bash
git clone https://github.com/xmpuspus/solar-map-ph
cd solar-map-ph

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Train clf_v4 from the committed dataset_v4.npz embeddings.
# Deterministic, no network, no GPU required. About 30 seconds on a laptop.
make train
make hash-verify        # asserts sha256 56900722a8427be4
make calibrate          # fits Platt + isotonic, writes calibration.json
make demo               # prints calibrated bundle summary
pytest tests/ -q        # 11 tests, ~1 second
```

To render PR / ROC / reliability figures:

```bash
pip install matplotlib
make plots              # writes to docs/figures/
```

To run all release-readiness gates (residential leak check, cross-region PII, classifier hash, requirements pinning, site/data sync):

```bash
make verify-v11         # runs scripts/verify_v11_release.py end-to-end
```

To scan a v1.1 cross-domain region from scratch (or resume one):

```bash
# All seven v1.1 regions, sequentially; auto-resumes from cached JSONL
make scan-regions

# Or one region at a time
python3 detection/scan/region_scan.py --region cebu --built-up-threshold 0.05
python3 detection/scan/aggregate_region.py --region cebu
```

## Quickstart for the site

```bash
cd site
pnpm install
pnpm dev                # http://localhost:4321
pnpm typecheck
pnpm build              # production build
```

## Detection pipeline (reproducible)

The CNN detection pipeline (CLIP-ViT-L embeddings + logistic regression + Platt calibration) ships with a Makefile, a Dockerfile, and pinned Python dependencies. The trained classifier is bit-exact reproducible from the committed `detection/train/dataset_v4.npz` embeddings (~11 MB, in git).

```bash
# Local
pip install -r requirements.txt
make train
make hash-verify        # asserts clf_v4.joblib sha256 prefix 56900722a8427be4

# Docker
docker build -t solar-map-ph:latest .
docker run --rm solar-map-ph:latest                     # default: make hash
docker run --rm solar-map-ph:latest make hash-verify    # asserts the prefix
docker run --rm -v $(pwd)/detection/scan/ncr_tiles:/app/detection/scan/ncr_tiles \
    solar-map-ph:latest make scan aggregate             # re-classify cached tiles
```

The image bundles `dataset_v4.npz` but not the raw NCR tile cache (~6.6 GB). Mount the cache as a volume for `make scan` and `make all`. See `Makefile` for every target.

Encoder is locked to `openai/clip-vit-large-patch14` after an ablation against `facebook/dinov2-large` (4 pt F1 lower) and `allenai/satlas-pretrain` (14 pt F1 lower). See `MODEL_CARD.md` for the full table.

Calibration is Platt sigmoid in production. Isotonic regression is run alongside and reported in `clf_v4_calibration.json` for comparison (isotonic has slightly lower Brier score; Platt wins on monotonicity and parameter count).

If someone sends you a classifier `.joblib` file, hash-verify it before invoking `joblib.load`. Pickle deserialization executes arbitrary code:

```bash
python3 scripts/verify_clf.py path/to/their_clf.joblib
```

## Earth Engine pipeline (quarterly)

Quarterly batch that emits a per-city composite signal. Independent from the detection pipeline and only needed for the city-scale `/map` choropleth.

```bash
cd pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Set EE credentials (see .env.example)
export EE_SERVICE_ACCOUNT="your-sa@your-project.iam.gserviceaccount.com"
export EE_KEY_FILE="/path/to/your-key.json"

python pipeline.py --quarter 2026Q2 --baseline 2022
python validate.py --quarter 2026Q2
```

Outputs land in `site/public/data/`:
- `solar_map_ph_2026Q2.geojson` (one feature per city)
- `solar_map_ph_barangay_2026Q2.geojson` (drilldown for built-up barangays)
- `solar_map_ph_summary_2026Q2.json` (franchise totals)

See `site/public/data/SCHEMA.md` for the field-by-field schema and units.

## Multi-region coverage (v1.1)

v1.0 ships NCR as the calibrated reference region (F1 = 0.870 on 20% holdout). v1.1 applies the same `clf_v4.joblib` cross-domain (without retraining) to seven additional Philippine distribution-utility franchise areas:

| Region | Franchise | Detections (high + cand) | Built-up tiles | Spot-check | Status |
|---|---|---|---|---|---|
| Cebu Metro | VECO | 36 + 53 | 4,142 | 7/8 rooftop, 1/8 ground-mount | shipped |
| Davao City | DLPC | 28 + 19 | 5,295 | 5/5 rooftop | shipped |
| Iloilo Metro | MORE | 3 + 6 | 2,456 | 5/5 rooftop | shipped |
| Cagayan de Oro | CEPALCO | 3 + 6 | 2,704 | 3/5 rooftop, 2/5 ground-mount | shipped |
| Legazpi (Albay) | ALECO | 0 + 1 | 734 | 1/1 false-positive (blue stadium) | shipped |
| Calabarzon (south of Meralco) | BATELEC / FLECO / QUEZELCO / LUELCO | 106 + 80 | 18,695 | 5/5 rooftop | shipped (v1.1.1) |
| Bacolod / Negros Occidental | CENECO | 1 + 2 | 2,685 | 3/3 rooftop | shipped (v1.1.1) |

**Combined v1.1 cross-domain total: 177 high-confidence + 167 candidate detections across all seven regions.** The spot-check sample (32 top-scoring tiles inspected across all regions) confirmed 28 real rooftop solar (87.5%), 3 ground-mount solar farms (same FP class observed in NCR's Valenzuela audit), and 1 blue-roof false positive (Legazpi). The mount-type classifier queued for v1.2 will close the ground-mount gap.

See [`/regions`](https://solarmap.ph/regions) for the live status and per-region detection counts, and [`/map`](https://solarmap.ph/map) for the unified detection map (NCR detections appear orange / green, v1.1 cross-domain detections appear steel blue). Cross-domain precision is not yet calibrated per region; treat detections as a candidate inventory pending v1.2 active-learning rounds.

To extend coverage to another Philippine region or any geography worldwide, supply a region polygon GeoJSON. See [`examples/run_on_new_region.md`](examples/run_on_new_region.md) for the generic recipe, or `pipeline/regions/regions.json` + `detection/scan/region_scan.py` for the v1.1 multi-region scaffolding.

### What's new in v1.1

- Cross-domain detection scans for VECO (Cebu), DLPC (Davao), MORE (Iloilo), CEPALCO (Cagayan de Oro), ALECO (Legazpi), the Calabarzon belt south of Meralco (BATELEC / FLECO / QUEZELCO et al), and CENECO (Bacolod / Negros Occidental). No retraining: same `clf_v4.joblib` (sha256 prefix `56900722a8427be4`) applied across all regions.
- New `/regions` page with per-region detection counts loaded client-side from `/data/city_detection_counts_<slug>.json`.
- New `/map` overlay: v1.1 detections render in steel blue alongside the calibrated NCR orange / green / gray layers. `/map?region=<slug>` deep-links to any v1.1 region's bbox.
- `pipeline/regions/regions.json` is now the source of truth for region bbox + franchise + served-LGU config.
- `pipeline/regions/fetch_region_polygons.py` queries OSM Overpass for each served LGU and stitches admin-boundary segments into closed rings via `shapely.polygonize`.
- `detection/scan/region_scan.py` and `detection/scan/aggregate_region.py`: region-aware scanner + aggregator. Tile pixel size defaults to 400 outside NCR (Esri's World Imagery has region-dependent max-zoom; 600 px returns HTTP 500 in some areas).
- `scripts/check_region_no_pii.py`: CI gate asserting every published region GeoJSON is point-tile only, no per-building polygons, no PII fields.
- `scripts/verify_v11_release.py`: pre-release gate runner (regions GeoJSONs valid, PII clean, classifier hash matches canonical, requirements pinned, site/src/data/regions.json mirrors pipeline/regions/regions.json).
- Visual spot-check archive at [`docs/screenshots/qa-2026-05/region-spot-check/`](docs/screenshots/qa-2026-05/region-spot-check/) with top-scoring tile thumbnails and per-region findings markdown for all seven cross-domain regions.

## Headline numbers, with footnotes

### NCR (v1.0, calibrated)

- **515 rooftops detected across 41 cities** in Greater Metro Manila (NCR plus adjacent cities in Bulacan, Cavite, Rizal, Laguna), of which **280 are high-confidence** (model score >= 0.85) and 235 are below-threshold candidates included for review.
- **87% of the high-confidence detections (242 of 277)** were not already on a public map of solar at the time of the scan. "Public map" here means OpenStreetMap features tagged with `generator:source=solar` or similar within 200 m of the detected tile centroid; this is the same proximity threshold used in DeepSolar (Stanford, 2018) and SPECTRUM (ICSC, 2025). Of the 280 high-confidence detections, 277 land inside a city polygon and are counted; 3 fall on LGU borders.
- **69.9 MWp aggregate installed capacity** from the 384 buildings the SAM auto-mask successfully localized to an OSM building footprint. Capacity per building is computed as (segmented panel area in m²) / 6 m² per kWp, capped at the building footprint area.
- **27 residential rooftops** with detected solar are released as an aggregate count only (no geometry, no addresses). The breakdown by OSM `building=*` tag and the summed residential kWp are in [`site/public/data/residential_solar_aggregate.json`](site/public/data/residential_solar_aggregate.json).
- Calibrated **precision 96%, recall 80% at threshold 0.85** on an honest 20% held-out source-disjoint split. Expect roughly 1 in 25 NCR high-confidence detections to be a false positive.

### v1.1 cross-domain (uncalibrated)

- **177 high-confidence + 167 candidate detections** across all seven v1.1 regions (Cebu 36+53, Davao 28+19, Iloilo 3+6, CDO 3+6, Legazpi 0+1, Calabarzon 106+80, Bacolod 1+2). Calabarzon and Bacolod completed in the v1.1.1 follow-up round.
- **87.5% rooftop precision** in the cross-domain spot-check sample (28/32 top-scoring tiles confirmed real rooftop solar). 3/32 are ground-mount utility solar farms (the dominant cross-domain failure mode, shared with NCR's Valenzuela detection); 1/32 is a blue stadium-roof false positive in Legazpi.
- **Largest cross-domain inventory: Calabarzon (106 high + 80 candidate)** across 10 LGUs in the BATELEC / FLECO / QUEZELCO franchise belt — the industrial corridor south of Meralco (Calamba, Tanauan, Santo Tomas, Santa Rosa, Lipa) has the highest industrial-rooftop-solar density outside NCR. **Lowest: Bacolod (1 high + 2 candidate)** — CENECO's franchise area in Negros Occidental has very sparse industrial rooftop solar.
- **Tile granularity (240 m, no per-building geometry yet)**: v1.1 regions ship as point-feature GeoJSONs at `site/public/data/rooftop_solar_<slug>.geojson`. The SAM per-building stage that produces NCR's per-roof polygons is queued for v1.2 alongside the per-region calibration round.
- **No residential-leak risk** in v1.1 outputs by construction: tile centers are 240 m grid points that do not name buildings, and the `scripts/check_region_no_pii.py` gate asserts every region GeoJSON is point-only with no per-building geometry or PII fields.

## Policy context

This dataset only matters because the policy context is contested. SolarMap.PH was designed around the gap between an estimated ~170 MW of formally net-metered rooftop solar in Meralco's franchise and the ~370 MW of estimated commercial rooftop solar outside the program, plus the residential "guerrilla solar" gap ICSC estimates at roughly one-third of the total franchise rooftop fleet. v1.1 extends the same lens to seven additional franchise areas — VECO, DLPC, MORE, CEPALCO, ALECO, the Calabarzon coops, and CENECO — where the net-metering gap is plausibly wider because the franchise jurisdictions are smaller, the LGU permit-data infrastructure is thinner, and the public-mapping baseline (OSM solar tags) is sparser than in NCR. The full five-actor map (Meralco, DOE / Sen. Gatchalian, ERC, LGUs, households) is in [`docs/research/policy-context.md`](docs/research/policy-context.md). Related work and prior tooling in the same space (DeepSolar, PV_Pipeline, SPECTRUM, Global Solar Atlas, REMap) is in [`docs/research/related-work.md`](docs/research/related-work.md).

## Project layout

```
solar-map-ph/
|-- detection/
|   |-- bootstrap/          # OSM Overpass + Esri tile fetch
|   |-- buildings/          # Overpass building-lookup helper
|   |-- train/              # CLIP embedding + LogisticRegression head
|   |   `-- v4_calibrated/  # Honest 20% holdout + Platt + isotonic
|   |-- scan/               # 240m-grid classifier + SAM segmentation
|   |   |-- ncr_scan.py             # NCR scanner (600 px tiles)
|   |   |-- region_scan.py          # v1.1 region scanner (400 px tiles + WorldCover prefilter)
|   |   |-- aggregate_region.py     # v1.1 aggregator: scan JSONL -> GeoJSON
|   |   |-- assemble_per_building.py # NCR SAM + OSM intersection
|   |   `-- worldcover/             # Cached ESA WorldCover GeoTIFFs (gitignored)
|   |-- verify/             # Active-learning UI scaffolding
|   `-- README.md
|-- pipeline/               # Earth Engine quarterly batch + multi-region scaffolding
|   |-- pipeline.py
|   |-- validate.py
|   |-- scrape_meralco.py
|   |-- lgu_friction.json
|   |-- franchise_cities.json
|   |-- boundaries/
|   |-- regions/                    # v1.1 multi-region config
|   |   |-- regions.json            # Source-of-truth: bbox + franchise + LGUs per region
|   |   |-- fetch_region_polygons.py # OSM Overpass -> stitched admin polygons
|   |   `-- <slug>_lgus.geojson     # Per-region LGU polygon collection (one per region)
|   `-- requirements.txt
|-- site/                   # Astro static site, MapLibre + OSM
|   |-- public/data/        # Quarterly GeoJSON drops + per-building polygons
|   |   |-- rooftop_solar_ncr.geojson
|   |   |-- rooftop_solar_<slug>.geojson  # one per v1.1 region
|   |   |-- city_detection_counts_<slug>.json
|   |   |-- per_building_solar_ncr.geojson
|   |   |-- residential_solar_aggregate.json
|   |   `-- SCHEMA.md       # Schema for every published file
|   |-- src/
|   |   |-- components/     # RoofLookup (roof tool), MapView, Header, Footer
|   |   |-- data/regions.json       # Mirrored from pipeline/regions/regions.json (Vercel boundary)
|   |   `-- pages/          # index, map, regions, methodology, safety, faq, privacy, post/
|   `-- vercel.json         # CSP, headers, redirects
|-- scripts/
|   |-- plot_pr_curve.py              # PR + ROC + reliability figures
|   |-- check_no_residential_leaks.py # CI gate on NCR per-building dataset
|   |-- check_region_no_pii.py        # CI gate on v1.1 region GeoJSONs (no PII fields)
|   |-- verify_v11_release.py         # Full pre-release gate runner (24+ checks)
|   |-- run_all_v11_regions.sh        # Sequential scanner for all v1.1 regions
|   |-- dump_top_region_tiles.py      # Print top-N scoring tiles for visual audit
|   |-- publish_to_huggingface.py     # Push trained classifier to HF Hub
|   `-- verify_clf.py                 # Hash-verify a classifier joblib
|-- tests/                  # pytest suite (11 tests, no network)
|-- docs/
|   |-- figures/            # Regenerated by `make plots`
|   |-- screenshots/        # README hero
|   |   `-- qa-2026-05/region-spot-check/  # Per-region top-N tile thumbnails + findings.md
|   |-- privacy-impact-assessment.md # RA 10173 posture
|   `-- research/           # Source material for the writeup
|       |-- policy-context.md
|       `-- related-work.md
|-- examples/
|   `-- run_on_new_region.md
|-- MODEL_CARD.md           # Intended use, biases, ethics, citation
|-- CITATION.cff
|-- CHANGELOG.md
|-- CONTRIBUTING.md
|-- CODE_OF_CONDUCT.md
|-- SECURITY.md
|-- Makefile                # train / calibrate / scan / aggregate / hash-verify / plots / verify-v11 / scan-regions
|-- Dockerfile              # Deterministic build, ships dataset_v4.npz
|-- requirements.txt        # Detection pipeline deps (== pinned)
|-- LICENSE                 # MIT (code) + CC-BY-4.0 (data)
|-- .zenodo.json            # Auto-archive config (Zenodo webhook on GitHub releases)
`-- README.md
```

## Quarterly refresh cadence

About six hours per quarter for the calibrated NCR refresh, plus 2-3 hours per v1.1 region scan (mostly idle wait while the Esri tile fetch and CLIP embedding loop run; ~2 hours for the largest region, Calabarzon). Annual LGU table refresh adds three hours once a year.

| Step | Time | Notes |
|---|---|---|
| 1. EE pipeline | 30m | `python pipeline.py --quarter YYYYQN --baseline 2022` |
| 2. Update Meralco aggregates | 30m | Refresh `meralco_aggregates.json` from public reports |
| 3. Validate | 30m | `python validate.py`, spot-check three cities visually |
| 4. Move data into site | 15m | Copy outputs to `site/public/data/`, bump `manifest.json` |
| 5. NCR per-building leak check | 5m | `python scripts/check_no_residential_leaks.py` |
| 6. v1.1 region rescans (optional) | 2-3h per region | `bash scripts/run_all_v11_regions.sh` (auto-resumes from cached JSONL). Wait several hours between rescans to avoid Esri tile-service throttling |
| 7. v1.1 pre-release gate | 5m | `make verify-v11` (24+ checks: PII gates, classifier hash, requirements pinning, regions.json mirror) |
| 8. Write quarterly post | 1-3h | Optional. Skip if no story this quarter |
| 9. Methodology review | 15m | Add new caveats if surfaced |
| 10. Commit + deploy | 5m | `git push origin main`, Vercel auto-deploys. Tag release `vX.Y.Z` to trigger Zenodo auto-archive |
| 11. Distribution | 15m | Optional LinkedIn share, optional issue/PR routing. Skip HN/Reddit/X |

## Methodology in one paragraph

Two pipelines, two granularities. **Detection pipeline** (per-tile, per-rooftop): a frozen CLIP-ViT-L/14 encoder converts each 240 m Esri imagery tile into a 768-dim embedding; a sklearn LogisticRegression head trained on 294 OSM-tagged NCR positives plus 200 negatives turns embeddings into a tile-level solar probability; Platt sigmoid calibration on a 20% source-disjoint holdout converts that probability into a calibrated score. For NCR only, a SAM auto-mask + OSM building intersection turns each high-confidence tile into a per-building panel polygon. v1.1 cross-domain regions ship at tile granularity. **Quarterly EE pipeline** (per-city composite): Earth Engine pulls Sentinel-2 NIR/SWIR median, Landsat 8/9 land surface temperature, and VIIRS DNB nightlights over the region polygon; each signal is reduced to per-city statistics, z-scored across cities, and weighted (0.4 NIR, 0.3 SWIR, 0.2 LST, 0.1 nightlight) into a composite. ESA WorldCover masks vegetation and water. Microsoft GlobalMLBuildingFootprints provides per-city building counts as a denominator. The composite score correlates with rooftop PV adoption but does not prove it; we are explicit that the signal is suggestive, not diagnostic, at city scale. See `/methodology` on the site for the full algorithm and caveats.

## Data attribution

SolarMap.PH inputs come from publicly licensed third parties. Cite the upstream sources when reusing derivatives:

- **Esri World Imagery**: training imagery and homeowner-tool satellite tiles, via the publicly documented `World_Imagery` REST endpoint. Attribution: *Esri, Maxar, Earthstar Geographics, and the GIS User Community*. Esri's posture on this layer is broadly permissive for academic and non-commercial use with attribution; Esri publishes its own pretrained solar-detection models on the same imagery base.
- **OpenStreetMap** (ODbL): building footprints and `building=*` tags. Attribution: *© OpenStreetMap contributors*.
- **ESA WorldCover v200** (CC-BY-4.0): land cover masking for vegetation and water exclusion.
- **Microsoft GlobalMLBuildingFootprints** (ODbL-equivalent): per-city building-count denominators.
- **Sentinel-2** (ESA Copernicus, public domain): NIR/SWIR median.
- **Landsat 8/9** (NASA/USGS, public domain): land surface temperature.
- **VIIRS Day/Night Band** (NOAA, public domain): nightlight component.
- **Segment Anything Model** (Meta, Apache 2.0): rooftop panel segmentation.
- **CLIP-ViT-L** (OpenAI, MIT): image encoder.
- **Photon / Komoot**, **Nominatim / OpenStreetMap**, **Overpass API**: geocoding and building-tag lookup in the homeowner tool.
- **PVGIS** (European Commission JRC): solar irradiance for the payback calculator.

## License

Code: MIT. Data products in `site/public/data/`: CC-BY-4.0. Cite as `SolarMap.PH (YYYY-QN), https://github.com/xmpuspus/solar-map-ph`. See `CITATION.cff` for the canonical citation, `MODEL_CARD.md` for intended use and biases, and `SECURITY.md` for the threat model.

Author: Xavier Puspus.

## Contributing

Highest-value contributions, in priority order:

1. **Verified false-positive reports** on any detection in the published datasets (NCR per-building or v1.1 cross-domain tile-level). Use the `false-positive` issue label and include the tile_id or building_osm_id plus a screenshot.
2. **Per-region active-learning labels** for the v1.1 cross-domain regions (Cebu, Davao, Iloilo, CDO, Legazpi, Calabarzon, Bacolod). Labelled positives + negatives from these regions will drive the per-region recalibration queued for v1.2.
3. **Mount-type labels** (rooftop vs ground-mount) for top-scoring tiles. Ground-mount is the dominant cross-domain failure mode and motivates the v1.2 mount-type classifier head.
4. **LGU polygon coverage** improvements for the v1.1 region polygon sets in `pipeline/regions/<slug>_lgus.geojson`. Several served LGUs are missing from the current set because the OSM admin polygon uses a non-canonical name (e.g. "Mandaue City" vs "Mandaue"). PRs to map served-LGU names to OSM relation IDs are welcome.
5. **LGU permit cost and delay data** for cities not in `pipeline/lgu_friction.json`.
6. **Region extensions** beyond the seven v1.1 areas (e.g. NORECO, PRESCO, PELCO, SUKELCO).
7. **Encoder ablation submissions** against Prithvi, SkySense, SatMAE, CLIPSeg.
8. **Code review and bug fixes**.

See `CONTRIBUTING.md` for the full dev setup and PR conventions, and `.github/ISSUE_TEMPLATE/` for issue templates.

## References

- DeepSolar (Stanford), Joule 2018: https://www.sciencedirect.com/science/article/pii/S2542435118305701
- SPECTRUM (ICSC, 2025): https://icsc.ngo/solar-mapper/
- ESA WorldCover v200: https://esa-worldcover.org
- PVGIS, European Commission JRC: https://re.jrc.ec.europa.eu/pvg_tools/en/
- Segment Anything (Meta, 2023): https://segment-anything.com
- CLIP (OpenAI, 2021): https://openai.com/research/clip
- Full bibliography: [`docs/research/related-work.md`](docs/research/related-work.md)
