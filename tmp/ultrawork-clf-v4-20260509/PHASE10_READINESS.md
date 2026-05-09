# Phase 10 — Public Release Readiness (NOT EXECUTED — awaiting `/commit`)

The user explicitly said "no auto-commit; only /commit when Xavier explicitly says". This phase prepares the working tree but does not run `/commit`, `/pr`, `/review --self`, or `/ship`.

## What's ready to commit

19 files changed in working tree. Group by area:

### New (Phase 1-6 work)

| Path | Purpose |
|---|---|
| `requirements.txt` | Pinned ML deps |
| `Dockerfile` | Reproducible build image |
| `Makefile` | Pipeline targets |
| `.dockerignore` | Trim build context |
| `detection/` | Entire CNN detection module (v3 + v4 + calibrated + ablation + prefilter) |
| `tmp/ultrawork-clf-v4-20260509/` | Phase reports + run logs (gitignore candidate) |

### Modified

| Path | Change |
|---|---|
| `.gitignore` | (was modified earlier in the session) |
| `README.md` | Added "Detection pipeline (reproducible)" section with `make` + `docker run` recipes and the locked-encoder rationale |
| `site/src/components/BubongTool.astro` | Earlier session: verdict + autocomplete + bulletproofing |
| `site/src/components/Header.astro` | Earlier session: /safety nav |
| `site/src/components/MapView.astro` | Earlier session: confidence-encoded layers + sat popups |
| `site/src/pages/bubong.astro` | Earlier session |
| `site/src/pages/index.astro` | Earlier session |
| `site/src/pages/methodology.astro` | Earlier session: Mermaid figs |

### New site data (Phase 1 outputs)

| Path | Contents |
|---|---|
| `site/public/data/rooftop_solar_ncr.geojson` | clf_v4 results: 130 high + 216 candidate |
| `site/public/data/per_building_solar_ncr.geojson` | v2.1 SAM building polygons |
| `site/public/data/solar_saturation_ncr.geojson` | Saturation cells (earlier session) |
| `site/public/data/city_solar_saturation.json` | City rollup (earlier session) |
| `site/src/pages/safety.astro` | Safety page (earlier session) |

## Headline numbers

- **Active learning round (Phase 1)**: F1 0.918 → **0.938** (LOSO). Recall 70.5% → 77.2% at t=0.85. **+16 high-confidence detections** in NCR (114 → 130).
- **Honest calibrated holdout (Phase 2)**: P=**95.9%** R=79.7% F1=0.870 at t=0.85, n=59 pos + 39 neg holdout sources, never-trained.
- **Encoder ablation (Phase 3)**: CLIP-ViT-L wins decisively. DINOv2-large -4pt F1, satlas Aerial_SwinB_SI -14pt F1 on calibrated holdout. CLIP locked.
- **Reproducibility (Phase 4)**: Two consecutive `train_v3.py` runs produce identical sha256 `15564df477c961f2`. Deps pinned with ==. `make hash` and `make demo` work.
- **Built-up pre-filter (Phase 6)**: 70% drop on NCR at 5% threshold, 130/130 high-conf preserved.

## Phase 5 + 7-9 status

- **Phase 5** (Meralco extended franchise): partial scan, 1,904 of 29,000 new tiles done before the network bottleneck hit (~1.3 tiles/sec vs the 14 t/s estimate). State preserved in `detection/train/_baselines/scan_v4_partial_franchise_18448.jsonl`. Resume recipe in `PHASE5_REPORT.md`.
- **Phases 7-9** (Luzon, Visayas+Mindanao, per-building SAM nationwide): not run. Recipes in `PHASE7_8_9_RECIPES.md`. Phase 7 needs `detection/scan/luzon_scan.py` wrapper to be written before running (streams JPG fetch → classify → delete to avoid 360GB cap). Estimated 10 days at observed throughput.

## Quality gate

| Check | Status | Notes |
|---|---|---|
| Lints (ruff on new files) | PASS | One harmless warning on a copy-pasted unused `rng` in `encoder_ablation.py` (pre-existing pattern from train_v3.py) |
| Tests | N/A | No unit-test suite in this codebase |
| Determinism | VERIFIED | Two LR retraining runs from same dataset produced identical sha256 |
| Pinned deps | YES | All == |
| Docker smoke test | NOT RUN | Image build not attempted (slow, ~10 min); `docker build && docker run` recipe documented |
| README updated | YES | New "Detection pipeline (reproducible)" section |
| AI-tells / em-dash audit | PARTIAL | Reports use em-dashes; production code does not. Strip em-dashes from `tmp/*.md` if you don't want them tracked |
| Sensitive data | NONE | No env files, secrets, or PII added |

## Suggested commit groupings (when you run `/commit`)

Three logical commits if you want to split:

1. `detection/` — the entire CNN module (v3 dataset/train, v4 calibrated subdir, encoder_ablation, built_up_prefilter, baselines).
2. Reproducibility bundle — `Makefile` + `Dockerfile` + `requirements.txt` + `.dockerignore` + README addition.
3. Site updates (already partially in earlier session).

Or one big commit covering everything from this ultrawork session.

## What to do BEFORE `/commit`

1. **Decide on `tmp/`**: the ultrawork reports + run logs are in `tmp/ultrawork-clf-v4-20260509/`. Currently untracked. Add `tmp/` to `.gitignore` if you want them out of the commit, or `git add tmp/ultrawork-clf-v4-20260509/*.md` if you want the phase reports preserved.
2. **Decide on `detection/scan/worldcover/`** (~30 MB): the WorldCover GeoTIFF download. Probably gitignore — it's regenerable from a public URL.
3. **Decide on `detection/scan/ncr_tiles/`** (~5 GB of cached JPGs) — should already be gitignored; verify.
4. **Decide on `detection/train/_baselines/`** (~20 MB of preserved snapshots): keep small files (jsonl, json) and gitignore the npz / joblib snapshots. Or commit everything for full provenance.
