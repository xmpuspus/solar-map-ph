# ghost-watts

Detect the unmeasured rooftop solar capacity in Meralco's franchise area using free public satellite signals, expose the cross-subsidy and LGU-permit-friction story behind the "guerrilla solar" headlines, and give homeowners a single page to size their own roof against their own LGU's permit cost.

Sibling project to ghostwatch in the civic-tech-PH arc.

## What this is

Three surfaces, two pipelines:

- `/` is a homeowner lookup. Drop an address, find the matching OpenStreetMap building, measure the roof from Esri imagery, run PVGIS-derived solar yield against the current Meralco rate. Surfaces verified case studies and CNN-detected rooftop solar within 1.5 km. All client-side, no backend.
- `/map` aggregates a multi-signal solar-presence index per city/municipality across Meralco's franchise. Built on Sentinel-2, Landsat thermal, VIIRS nightlights, and ESA WorldCover, blended in Google Earth Engine. City-level resolution.
- `detection/` is the per-roof CNN pipeline. Bootstraps a positive set from OpenStreetMap `power=generator + generator:source=solar` tags, trains a logistic-regression head on CLIP-ViT-L image embeddings, then tiles NCR on a 240m grid running the trained classifier. After an active-learning label cleanup pass (4 false-negative random tiles promoted to positives, 2 noisy case studies dropped), **clf_v3 hits F1 = 0.918, 99.1% precision at 70.5% recall** (5-fold group-aware CV, threshold 0.85). Full NCR scan: **114 high-confidence + 280 candidate detections, 79% NEW** (not in OSM). The v2.1 building-level layer (SAM + color signature + clf_v3 + OSM building footprints) outputs one polygon per OSM building with detected panels, with `kwp_estimate` and `panel_area_m2`. See `detection/README.md`.

## What this is not

- Not engineering advice. The homeowner tool is informational. Consult a certified installer.
- Not address-level data. No PII is ingested or published.
- Not a launch event. Per quiet-builder posture, this ships as reference documentation. People who care will find it.

## Quickstart

### Prerequisites

- Python 3.11+
- Node.js 20+ (for the Astro site)
- A Google Earth Engine account with a service account credentials JSON. Sign up at https://earthengine.google.com if you don't have one.

### Run the quarterly pipeline

```bash
cd pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Set EE credentials
export EE_SERVICE_ACCOUNT="your-sa@your-project.iam.gserviceaccount.com"
export EE_KEY_FILE="/path/to/your-key.json"

python pipeline.py --quarter 2026Q2 --baseline 2022
python validate.py --quarter 2026Q2
```

Outputs land in `site/public/data/`:
- `ghost_watts_2026Q2.geojson` (one feature per city)
- `ghost_watts_barangay_2026Q2.geojson` (drilldown for built-up barangays)
- `ghost_watts_summary_2026Q2.json` (franchise totals)

### Run the site locally

```bash
cd site
pnpm install
pnpm dev
```

Open http://localhost:4321.

### Deploy (Vercel)

One-time setup:

```bash
cd site
pnpm install
pnpm vercel link        # create the project, link this directory
pnpm vercel --prod      # first manual deploy
```

When prompted by `vercel link`:

- Set up and deploy: `Y`
- Link to existing project: `N` (first time)
- Project name: `ghost-watts`
- In which directory is your code located: `./` (you're already inside `site/`)
- Framework preset: Astro (auto-detected)

After link, the `.vercel/` directory is created locally and gitignored. Subsequent deploys are automatic on push to `main`. Configure the GitHub integration in the Vercel dashboard so PR previews are also auto-built.

Headers, caching, and CSP are in `site/vercel.json`. The pipeline data files (`/data/*.geojson`, `/data/*.json`) get a permissive CORS header so anyone can fetch them as a public dataset.

CI (`/.github/workflows/ci.yml`) runs on every push and PR: type-check, build, pipeline syntax check, dry-run validation. Vercel handles the actual deploy on merge to `main`.

### Detection pipeline (reproducible)

The CNN detection pipeline (CLIP-ViT-L embeddings + logistic regression head + Platt calibration) ships with a Makefile, a Dockerfile, and pinned Python deps so the trained classifier is bit-exactly reproducible from the cached embeddings.

```bash
# Requires Python 3.11+ and the deps in requirements.txt at repo root.
pip install -r requirements.txt

# Train, calibrate, and verify deterministic hash from cached dataset_v4.npz
make train
make calibrate
make hash    # should print: clf_v4.joblib sha256: 15564df477c961f2

# Score a single tile through the calibrated bundle
make demo

# Full pipeline including the NCR scan (requires cached imagery in detection/scan/ncr_tiles/)
make all
```

**Docker smoke test** — `docker build -t ghost-watts:latest . && docker run ghost-watts:latest` should print the same `15564df477c961f2` sha256 for `clf_v4.joblib`. The image bundles `dataset_v4.npz` (the CLIP-embedded training set, ~8 MB) but not the raw imagery; mount `detection/scan/ncr_tiles/` as a volume to re-run the NCR scan.

```bash
docker build -t ghost-watts:latest .
docker run --rm ghost-watts:latest                        # prints classifier hash
docker run --rm -v $(pwd)/detection/scan/ncr_tiles:/app/detection/scan/ncr_tiles \
    ghost-watts:latest make scan aggregate                # re-classify cached tiles
```

Encoder is locked to `openai/clip-vit-large-patch14` after a Phase 3 ablation against `facebook/dinov2-large` and `satlas:Aerial_SwinB_SI` — both lost decisively (DINOv2 -4 pt F1, satlas -14 pt F1 on the calibrated holdout).

## Project layout

```
ghost-watts/
├── pipeline/
│   ├── pipeline.py             # Earth Engine driver, multi-signal band math
│   ├── validate.py             # Schema and sanity checks for quarterly outputs
│   ├── scrape_meralco.py       # Public-page scraper with manual fallback
│   ├── lgu_friction.json       # Hand-curated LGU permit cost and delay table
│   ├── meralco_aggregates.json # Quarterly Meralco/DOE registered counts (sourced)
│   ├── franchise_cities.json   # 50 cities/municipalities in Meralco's franchise
│   └── requirements.txt
├── site/                       # Astro static site, MapLibre + OSM
│   ├── public/data/            # Quarterly GeoJSON drops
│   └── src/
│       ├── layouts/
│       ├── pages/
│       │   ├── index.astro
│       │   ├── map.astro
│       │   ├── me.astro
│       │   ├── methodology.astro
│       │   └── post/
│       └── components/
├── docs/
│   ├── superpowers/specs/
│   │   └── 2026-05-08-ghost-watts-design.md   # The locked design spec
│   └── research/
│       └── policy-context.md   # Source material for the writeup
├── LICENSE                     # MIT for code, CC-BY-4.0 for data
└── README.md
```

## Quarterly refresh cadence

Roughly six hours of work per quarter. Annual LGU table refresh adds three hours once a year.

| Step | Time | Notes |
|---|---|---|
| 1. EE pipeline | 30m | `python pipeline.py --quarter YYYYQN --baseline 2022` |
| 2. Update Meralco aggregates | 30m | Refresh `meralco_aggregates.json` from public reports |
| 3. Validate | 30m | `python validate.py`, spot-check three cities visually |
| 4. Move data into site | 15m | Copy outputs to `site/public/data/`, bump `manifest.json` |
| 5. Write quarterly post | 1-3h | Optional. Skip if no story this quarter |
| 6. Methodology review | 15m | Add new caveats if surfaced |
| 7. Commit + deploy | 5m | `git push origin main`, Vercel auto-deploys. Tag release `ghost-watts-YYYYQN` |
| 8. Distribution | 15m | Optional LinkedIn share, optional DM to ICSC. Skip HN/Reddit/X |

## Methodology in one paragraph

Every quarter, Earth Engine pulls Sentinel-2 NIR/SWIR median, Landsat 8/9 land surface temperature, and VIIRS DNB nightlights over the Meralco franchise polygon. Each signal is reduced to per-city statistics, z-scored across cities, and weighted (0.4 NIR, 0.3 SWIR, 0.2 LST, 0.1 nightlight) into a composite score. ESA WorldCover masks vegetation and water. Microsoft GlobalMLBuildingFootprints provides per-city building counts as a denominator. The composite score correlates with rooftop PV adoption but does not prove it; we are explicit that the signal is suggestive, not diagnostic, at city scale. See `/methodology` on the site for the full algorithm and caveats.

## License

Code: MIT. Data products in `site/public/data/`: CC-BY-4.0. Cite as "ghost-watts (YYYY-QN), https://github.com/xmpuspus/ghost-watts."

## Contributing

The LGU friction table is the highest-value contribution. If you have verified permit cost and delay data for a city or municipality in Meralco's franchise, open a PR against `pipeline/lgu_friction.json` with a source URL. See `pipeline/lgu_friction.json` for current coverage and gaps.

## References

- Manila Times, "A brewing solar controversy" (2026-05-07): https://www.manilatimes.net/2026/05/07/opinion/columns/a-brewing-solar-controversy/2337415
- CleanTechnica, "Guerilla Solar Installations Discovered" (2026-05-04): https://cleantechnica.com/2026/05/04/guerilla-solar-installations-discovered-need-to-be-controlled-says-philippine-power-distributor/
- Tribune, "Meralco Seeks Crackdown" (2026-05-07): https://tribune.net.ph/2026/05/07/meralco-seeks-crackdown-on-guerrilla-solar-installations
- Inquirer Opinion, "Guerrilla solar installers in summer of discontent": https://opinion.inquirer.net/191526/guerrilla-solar-installers-in-summer-of-discontent
- pv-magazine, "Philippines accelerates permits for solar net-metering" (2026-02-04): https://www.pv-magazine.com/2026/02/04/philippines-accelerates-permits-for-solar-net-metering/
- Power Philippines, "Inconsistent LGU Permits Stalling Rooftop Solar Growth": https://powerphilippines.com/inconsistent-lgu-permits-stalling-rooftop-solar-growth-expert-warns/
- Power Philippines (2019), "Meralco junks bid for full-rate compensation": https://powerphilippines.com/meralco-junks-bid-for-full-rate-compensation-to-net-metering-customers-warns-of-higher-generation-cost-to-other-end-users/
- DeepSolar (Stanford), the methodology precedent: https://www.sciencedirect.com/science/article/pii/S2542435118305701
- ICSC (Institute for Climate and Sustainable Cities): https://icsc.ngo
