# ghost-watts: Design Spec

Date: 2026-05-08
Status: Locked v1
Author: Xavier Puspus

## Goal

Make visible the hidden growth of rooftop solar in Meralco's franchise area at city/municipality resolution, frame it against the actual policy fight (cross-subsidy direction, LGU permit-friction variance, the 100kW cap, ERC's caution), and give a homeowner a one-page lookup of their roof's potential and their LGU's permit cost. Headline statistic, aggregate framing only:

> "We see signal consistent with ~N MW of detectable rooftop solar growth across Meralco's franchise from 2022 to YYYY-QN. Meralco reports ~M MW registered in net metering. The gap aligns with ICSC's 1/3 unregistered estimate."

## Why this exists

The current public discourse frames the policy fight as "Meralco blocks solar." The research shows it is more layered:

- Meralco asks for tighter equipment standards and installer accreditation. Officially: safety. Quietly: distribution-charge revenue erosion plus net-metering cross-subsidy concerns.
- DOE plus Sen. Sherwin Gatchalian are the streamliners, not the blockers. April 2026 circular cut approval to 10 working days.
- ERC has been structurally cautious: opposed cap-raise above 100kW, opposed full-retail compensation in 2019.
- LGUs are the silent blocker. Same 520 kWp project: ₱153K permit fees in Rizal vs ₱16K in Laguna.
- Households route around it. ICSC estimate: ~1/3 of rooftop solar in Meralco territory is unregistered.

What is missing from public discourse: any visualization of where the unregistered installs concentrate, how much the LGU permit gap actually varies, and what the duck-curve impact looks like in Luzon WESM data. ghost-watts fills the city/municipality-level visibility gap without making any address-level claim and without GPU-based individual-rooftop detection.

## Decisions locked

| Decision | Choice | Notes |
|---|---|---|
| Posture | Hybrid: transparency map (A) + homeowner tool (B) | Same dataset serves both surfaces |
| Geographic scope | Meralco franchise area | NCR plus parts of Bulacan, Cavite, Laguna, Rizal, Batangas, Quezon. ~9,300 km², ~50 cities/municipalities |
| Build cadence | Static dataset + quarterly refresh | ~1 working day per quarter |
| Registry data | Aggregate framing only | No FOI for address-level. Use Meralco public counts + DOE LGU aggregates + ICSC's 1/3 estimate |
| Detection approach | Multi-signal band math in Earth Engine | Sentinel-2 NIR/SWIR, Landsat thermal, VIIRS nightlights, ESA WorldCover. No GPU. Laptop runs orchestration only |
| Imagery for display | OSM basemap | Detected-signal choropleth overlaid. No commercial-imagery republication risk |
| Compute | Earth Engine free tier | Vendor risk acknowledged. Algorithm portable to rasterio + STAC if needed |
| Aggregation unit | City/municipality | Barangay drilldown only where built-up area > 1 km² |
| Frontend stack | Astro + MapLibre GL JS + OSM raster + Observable Plot + Tailwind | No backend. No vendor token. Vercel hosting (matches Xavier's existing landas-ph deploy pattern) |
| Name | ghost-watts | Riffs on ghostwatch parent project. Reads as "capacity that exists but isn't on any meter" |
| Distribution posture | Quiet-builder | Reference doc, not launch event. Optional LinkedIn share, optional DM to ICSC and Gatchalian's office. Skip HN/Reddit/X |

## Architecture

```
quarterly refresh (laptop, ~1 day work)
  ├── Earth Engine pipeline (multi-signal band math)
  │     ├── Sentinel-2: NIR (B8) + SWIR (B11) median delta vs 2022 baseline
  │     ├── Landsat 8/9: midday LST anomaly (Band 10)
  │     ├── VIIRS DNB: nightlight monthly delta as load-shape proxy
  │     └── ESA WorldCover 2021: built-up mask (denominator)
  ├── Public data joiners
  │     ├── Microsoft GlobalMLBuildingFootprints (PH subset)
  │     ├── PSA/PSGC barangay and city polygons
  │     ├── Meralco aggregate registry counts (scraped)
  │     ├── DOE LGU-level net-metering counts
  │     ├── ICSC 1/3 estimate (citation)
  │     └── LGU permit cost + delay table (hand-curated)
  └── Output: ghost_watts_YYYYQN.geojson + summary

static frontend (Astro, deployed to Vercel)
  ├── /map  (A-mode: city choropleth, time slider, drilldown)
  ├── /me   (B-mode: address → barangay stats + roof PVGIS + LGU friction)
  └── /post (quarterly writeup)
```

## Data pipeline detail

### Earth Engine signals

| Signal | EE collection | Bands | Aggregation | Weight |
|---|---|---|---|---|
| NIR delta | `COPERNICUS/S2_SR_HARMONIZED` | B8 | Median(quarter) - Median(2022 baseline) per city | 0.40 |
| SWIR delta | `COPERNICUS/S2_SR_HARMONIZED` | B11 | Same | 0.30 |
| LST anomaly | `LANDSAT/LC08/C02/T1_L2`, `LC09/...` | ST_B10 | Median midday LST per city minus regional baseline | 0.20 |
| Nightlight delta | `NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG` | avg_rad | Quarter mean minus 2022 mean | 0.10 |

Cloud masking: Sentinel-2 SCL band classes 8-10 (clouds), Landsat QA_PIXEL bits 3-4 (cloud + shadow), VIIRS uses QF1 quality flag.

Built-up mask: ESA WorldCover 2021 class 50 (built-up). Reduces vegetation/water noise.

### Composite score

```
for each city in franchise:
  z_nir       = (city.nir_delta - mean_nir_delta) / std_nir_delta
  z_swir      = (city.swir_delta - mean_swir_delta) / std_swir_delta
  z_lst       = (city.lst_anomaly - mean_lst_anomaly) / std_lst_anomaly
  z_nightlight = (city.nightlight_delta - mean) / std
  composite = -0.40*z_nir + -0.30*z_swir + -0.20*z_lst + 0.10*z_nightlight
  # Negative z scores on darker NIR/SWIR/cooler LST = stronger solar signal
  # Composite is positive when all three indicate more solar
```

Initial weights are v1 priors based on PV remote sensing literature (NIR is the most direct PV signature, SWIR is confirmatory, LST is noisier, nightlight is least specific). Weights documented as v1, eligible for refinement when ground-truth labels are available.

### Aggregation unit

City/municipality is the headline scale (~50 polygons in franchise). Barangay is drilldown only where `built_up_km2 > 1` (signal robustness threshold; below this, NIR median is too noisy). PSA/PSGC dataset provides polygons.

### Joiners

- Microsoft GlobalMLBuildingFootprints: free, ~30M PH buildings, used as denominator for "panels per 1000 buildings" framings
- Meralco aggregate counts: manually scraped from `company.meralco.com.ph` quarterly, ~10 minutes
- DOE LGU-level counts: pulled where DOE publishes them
- LGU permit cost + delay table: hand-curated, refresh annually
- PVGIS solar potential: client-side fetch on B-mode, public API, no auth

### Output schema

`ghost_watts_YYYYQN.geojson`:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "Polygon", "coordinates": [...] },
      "properties": {
        "name": "Quezon City",
        "psgc_code": "1380400000",
        "province": "Metro Manila",
        "metrics": {
          "s2_nir_delta_zscore": -1.2,
          "s2_swir_delta_zscore": -1.5,
          "landsat_lst_anomaly_zscore": -0.8,
          "viirs_nightlight_delta_zscore": 0.05,
          "composite_solar_signal_score": 1.16,
          "buildings_total": 350210,
          "built_up_km2": 165.3
        },
        "registry": {
          "meralco_aggregate_attribution": "city share estimate; see methodology",
          "doe_lgu_count": null
        },
        "policy": {
          "lgu_permit_fee_php": 28000,
          "lgu_permit_days_p50": 21,
          "permit_data_status": "verified",
          "permit_data_source": "...",
          "permit_data_collected": "2026-04-15"
        }
      }
    }
  ],
  "properties": {
    "quarter": "2026Q2",
    "baseline": "2022",
    "generated": "2026-05-08T...",
    "ee_pipeline_commit": "<git sha>"
  }
}
```

`ghost_watts_summary_YYYYQN.json`: franchise-level aggregates for the quarterly post.

### Reproducibility

Single `pipeline.py`. EE auth via service account JSON. Runs end-to-end in one command. Quarterly cadence: first week of Q1, Q2, Q3, Q4.

## A-mode frontend (the map)

Page: `/map`

Layout:

```
┌──────────────────────────────────────────────────────────┐
│ ghost-watts    2026-Q2    methodology  github  rss       │
├──────────────────────────────────────────────────────────┤
│ ┌─ Sidebar (right) ────┐                                  │
│ │ Click a city to load │   [MAP]                          │
│ │ NIR/SWIR/LST z-scores│   choropleth: composite score    │
│ │ Composite signal     │   per city. Diverging palette.   │
│ │ Buildings, density   │                                  │
│ │ Estimated registered │   OSM solar tags as small dots   │
│ │ LGU permit fee/days  │   for ground truth overlay       │
│ │ Link → /me           │                                  │
│ └──────────────────────┘   Time slider 2022Q1 → current   │
├──────────────────────────────────────────────────────────┤
│ Franchise composite signal over time (Observable Plot)   │
│ Top 5 strongest cities | Top 5 LGU friction              │
├──────────────────────────────────────────────────────────┤
│ Methodology + limitations callout (always visible)       │
└──────────────────────────────────────────────────────────┘
```

What gets rendered:

- Choropleth fill: composite score per city, diverging palette (steel-blue strong signal, neutral baseline)
- Click city populates the right sidebar with that city's full row
- OSM `generator:source=solar` points overlaid (hover shows tag metadata)
- Time slider scrubs quarterly snapshots

Performance: city-level GeoJSON ~50 features at ~1 KB each (~50 KB). Barangay drilldown (~600 features) lazy-loaded on zoom-in. First paint <2s on PH 4G.

Always-visible footer banner: "Signals are correlative. Aggregate only. Cannot identify individual rooftops or addresses."

## B-mode frontend (the homeowner tool)

Page: `/me`

Static, client-side. Shareable URL: `/me?city=qc&bill=15000&roof=80`.

Inputs:

- Address or pin drop on small map. Geocoder: Nominatim (free, OSM, 1 req/sec, cached client-side).
- Approximate roof area in m² (slider, default 80).
- Monthly Meralco bill in ₱ (slider, default 8,000).

Three cards rendered on submit:

### Card 1 - Your barangay's signal

- Composite signal score and rank within franchise
- Estimated detectable solar density (panels per 1000 buildings) from `ghost_watts_barangay_YYYYQN.geojson`
- Registered Meralco count for the parent city
- One-line interpretation: "You're in the Nth strongest-signal barangay in [city]"

### Card 2 - Your roof's potential (PVGIS)

- Suggested system size: `roof_area_m2 × 0.15 ≈ kWp`
- PVGIS-derived annual kWh/yr at exact lat/lon (free API)
- Annual ₱ savings at current Meralco rate (12.5 ₱/kWh as of Q2 2026)
- Years to payback: `install_cost / annual_savings`, install at ₱65K/kWp (PH market rate)
- 25-year lifetime net value

### Card 3 - Your LGU's friction

Side-by-side path comparison:

| | Registered path | Guerrilla path |
|---|---|---|
| Total upfront | install + permits | install only |
| Net-metering credits | Yes (full retail) | Never |
| Time to first kWh exported | weeks-months | days |
| Anti-islanding compliance | utility-verified | your responsibility |
| Legality | RA 9513 compliant | Civil + criminal exposure |
| Worker safety risk | DU-monitored | Yours |

Inline link to net-metering application steps for that LGU.

## Quarterly refresh runbook

| Step | Time | What |
|---|---|---|
| 1. Run EE pipeline | 30m | `python pipeline.py --quarter YYYYQN --baseline 2022` |
| 2. Update Meralco/DOE aggregates | 30m | Refresh `meralco_aggregates.json` from public reports |
| 3. Validate | 30m | `python validate.py`, spot-check three cities visually |
| 4. Move data into site | 15m | Copy outputs to `site/public/data/`, bump `manifest.json` |
| 5. Write quarterly post | 1-3h | Optional, skip if nothing newsworthy |
| 6. Methodology review | 15m | Add new caveats |
| 7. Commit + deploy | 5m | `git push origin main`. Vercel auto-deploys. Tag `ghost-watts-YYYYQN` |
| 8. Distribution | 15m | Optional LinkedIn share or DM. Skip HN/Reddit/X |

Failure-mode handling baked in:

- EE quota → script retries with smaller AOI tiles, falls back to per-city batch
- Heavy cloud cover quarter → script broadens date window to 4-month median
- Meralco redesigns public reports page → scraper falls back to manual entry prompt; no silent broken value
- ESA WorldCover stale → annual refresh of built-up mask, document version

## Launch post (inaugural quarter)

Post structure (~1,500-2,500 words at `/post/2026-q2.mdx`):

1. Hook: "Meralco says one-third of rooftop solar in its franchise is unregistered. Where, exactly?" Then: "Here is one answer, computed from public satellite data."
2. Aggregate finding: headline stat from inaugural EE run. Stated cautiously: "consistent with," not "proves."
3. Five takeaways:
   - Top 3 cities by composite signal strength
   - LGU permit friction outliers (Rizal vs Laguna 10x gap)
   - Duck-curve note for Luzon WESM
   - Cross-subsidy direction: net metering at full retail = non-solar customers cross-subsidize solar exporters. Structural, not malicious.
   - "Guerrilla" framing nuance: Meralco's safety asks are technically legitimate. The bottleneck is LGU permitting variance.
4. Methodology summary with link to full page.
5. Limitations, prominently placed.
6. What you can do with this: use `/map`, use `/me`, cite the data CC-BY, open issues/PRs.
7. Citations: ICSC, Manila Times, Inquirer, CleanTechnica, Tribune, pv-magazine, Power Philippines, DOE, Meralco.
8. Cross-links to civic-tech-PH arc siblings.

Distribution rules:

- Post lives on the site
- Optional LinkedIn share, link only, no thread
- Optional DMs to ICSC, Gatchalian's energy staffer, IEEFA-PH researcher
- Skip HN/Reddit/X per quiet-builder posture
- Re-post each quarter only when there is news

Style guardrails:

- No em-dashes
- No AI jargon ("delve", "land", "tuned to", "leverages", "seamlessly", "robust" filler)
- Direct technical tone

## Honest limitations

- 10m Sentinel-2 resolution caps inference at city/barangay aggregation
- Composite weights are v1 priors, not validated against ground truth
- Cloud-heavy quarters introduce noise; broadening the date window helps but does not eliminate
- Baseline 2022 means we miss installs prior to 2022
- Aggregate Meralco counts are public-report estimates, not audited
- LGU friction table is hand-curated, ~30 LGUs, not exhaustive
- Algorithm correlates with PV adoption but does not prove it; signal could also reflect roof reconstruction, paint changes, or sensor drift

## Out of scope for v1

- Address-level claims (would need FOI to Meralco; PII concerns)
- Individual-rooftop detection (would need GPU and labeled training data)
- Building footprint auto-detect on B-mode (deferred; user inputs roof area for now)
- Provincial/Luzon-wide expansion (franchise scope only)
- Live duck-curve dashboard (separate sibling project; ghost-watts only references WESM)

## Reviewer notes for future-me

- Validate the pipeline against an externally-known solar farm (e.g. a documented utility-scale installation in Bulacan) on the first run. If composite score does not light up there, weights need rework before publication.
- The cross-subsidy framing is technically accurate but politically loaded. Stick to math, not advocacy.
- The /me page must never imply guerrilla solar is recommended. The comparison table is descriptive, not prescriptive.
- If Meralco changes its public reporting format, the scraper falls back to manual entry. Do not silently zero out the registered count.
