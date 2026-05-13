# Changelog

All notable changes to SolarMap.PH are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Rebranded from `ghost-watts` to `SolarMap.PH`. Python package renamed `ghost_watts` -> `solar_map_ph`. Repo slug, Docker image tag, and HuggingFace artifact moved to `solar-map-ph`. Data product filenames renamed (`solar_map_ph_2026Q2.geojson`, `solar_map_ph_summary_2026Q2.json`). No model changes: classifier `clf_v4.joblib` sha256 prefix `56900722a8427be4` is preserved.
- Tagline now includes explicit coverage caveat: "Current coverage: Greater Metro Manila." Quarterly releases will expand to additional Philippine distribution-utility franchises (VECO, DLPC, MORE, CEPALCO).
- README, `/map`, `/methodology`, and `/safety` now reconcile to the canonical scan numbers (515 detections, 280 high-confidence, 384 per-building polygons, 69.9 MWp aggregate, 41 cities). The "87% absent from prior public map" claim now carries an explicit 200 m proximity-threshold footnote referencing DeepSolar (Stanford, 2018) and SPECTRUM (ICSC, 2025).
- Homeowner-tool privacy posture restated to be honest about third-party geocoder visibility: address queries reach Photon, Nominatim, Overpass, Esri, and PVGIS directly from the browser. No server operated by SolarMap.PH logs the address; the CSP enumerates the only endpoints the browser can reach.
- Ruff configuration adds `per-file-ignores` for research/scripts directories (`detection/**`, `pipeline/**`, `scripts/**`, `examples/**`, `site/scripts/**`) to keep the lint-strictness floor on library code while tolerating stylistic nits in one-off research scripts.

### Added

- `/privacy` page documenting publication boundary, RA 10173 §3(g) posture, DPO (self-designated), takedown channel (5 working days ack, 14 working days removal), CSP-enumerated third-party endpoints, and a no-telemetry statement.
- `docs/privacy-impact-assessment.md`: full Privacy Impact Assessment under RA 10173 with risk/mitigation table, data lifecycle, and review cadence. Self-conducted PIA; formal NPC voluntary advisory opinion deferred to the post-launch quarter.
- `/faq` page with 13 plain-language questions covering accuracy, error sources, residential-exclusion policy, RA 10173 posture, imagery licensing, homeowner-tool data flow, contribution paths, takedown.
- `.github/ISSUE_TEMPLATE/takedown.md` for structured takedown requests with a public audit trail.
- `scripts/check_no_residential_leaks.py`: build-time sanity check that no residential roofs leak into `per_building_solar_ncr.geojson`. Exits non-zero on any leak.
- `scripts/verify_clf.py`: hash-verify a classifier `.joblib` before invoking `joblib.load`. Recommended for any classifier file received from a third party.
- `docs/research/related-work.md`: credit and context for related projects in the same space, including SPECTRUM (ICSC, July 2025), DeepSolar (Stanford, 2018), PV_Pipeline, Global Solar Atlas, REMap (DOE/NREB), and the input/encoder dependency chain.
- Footer privacy-and-takedown panel and public-records disclaimer block. Header now exposes `/faq` and `/privacy` routes.
- MapView corner attribution credit line ("Imagery © Esri, Maxar, Earthstar Geographics. Buildings © OpenStreetMap contributors.").
- `site/public/robots.txt` (allow all).
- Self-designated DPO contact: `xpuspus@gmail.com`.

## [1.0.0] - 2026-05-12 - inaugural public release

### Added

- Open-source release on GitHub under MIT (code) + CC-BY-4.0 (data).
- Deterministic Docker build: `make hash-verify` asserts `clf_v4.joblib` sha256 `56900722a8427be4` from cached `dataset_v4.npz` embeddings.
- Isotonic-regression alternative to Platt calibration plus Brier scores for both methods, written into `clf_v4_calibration.json`.
- `scripts/plot_pr_curve.py` and `make plots` produce publication-quality PR, ROC, and reliability-diagram figures into `docs/figures/`.
- Privacy boundary: published per-building dataset suppresses residential roofs and emits a privacy-safe `residential_solar_aggregate.json` with counts and total kWp only.
- CI gates: site typecheck, site build, pipeline dry-run, classifier hash-verify, pytest suite.
- Community files: `CITATION.cff`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, GitHub issue templates, PR template, Dependabot config.
- Documentation: `MODEL_CARD.md`, `BENCHMARKS.md`, `site/public/data/SCHEMA.md`, active-learning protocol in `detection/active_learning.md`.
- Generic-region support: `--region-polygon` flag on `pipeline.py` and `ncr_scan.py` for running the pipeline outside Metro Manila. See `examples/run_on_new_region.md`.

### Changed

- `clf_v4` calibrated headline reported as F1 = 0.870, precision 95.9%, recall 79.7% at threshold 0.85 on the honest 20% held-out source-disjoint split. README, detection/README, site copy, and methodology page all reference the same number.
- Production Content Security Policy widened to allow Photon (Komoot), Overpass-API, and Esri World Imagery, which the homeowner tool needs at runtime.
- Mermaid diagram library bundled via npm instead of jsDelivr CDN.
- `pipeline/requirements.txt` pinned to `==` versions and pruned of unused dependencies (`geopandas`, `pandas`, `pyarrow`, `shapely`).
- `build_dataset_v3.py` augment seeds now derived via `hashlib.sha256` instead of Python's salted `hash()`, so seeded augmentations are stable across process restarts and `PYTHONHASHSEED` values.
- The homeowner roof-lookup component renamed from `BubongTool.astro` to `RoofLookup.astro`; the `/bubong` route now permanent-redirects to `/`.
- Per-tile fetch errors are now logged with an `error` field in the JSONL output (previously just `fetch_ok: false`).
- JSONL writes during scan now `fsync` after each flush.
- `--reuse-tiles` backup files now timestamped so consecutive runs don't overwrite the previous backup.
- Overpass rate limit raised to 1.1 s per call (was 0.05 s) to respect the upstream guideline; cache hits do not sleep.
- `pipeline.py` fails loud if more than 20% of cities fail, instead of silently shipping a sparse GeoJSON.
- `scrape_meralco.py` persists partial extractions instead of treating "one of two fields missing" as a total failure.

### Fixed

- Leap-year crash in `pipeline.py` when a Q1 quarter end-day was applied to a non-leap baseline year.
- `circle-stroke-dasharray` removed from the orphan-detections MapLibre layer (not a valid circle-layer property and was silently ignored).
- Pre-existing TypeScript errors in `site/src/components/MapView.astro` (GeoJSON cast, `d3-scale-chromatic` declaration file).

### Removed

- The `tmp/ultrawork-clf-v4-20260509/` directory of internal session logs and the `docs/superpowers/specs/` design-spec scaffolding (never intended for public release).
- The duplicate `/bubong` route.
- The 27 residential roof polygons that the prior `per_building_solar_ncr.geojson` revealed at sub-meter precision.

### Security

- Hardcoded personal email removed from `pipeline/fetch_boundaries.py` User-Agent string.
- The `joblib.load` pickle-RCE surface documented in `SECURITY.md` for downstream forks.
- CSP `connect-src` and `img-src` audited and reconciled against runtime fetches.
