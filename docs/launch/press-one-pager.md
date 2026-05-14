# SolarMap.PH: press one-pager

**What it is:** an open-source computer-vision survey of rooftop solar across Greater Metro Manila, paired with a free homeowner roof-lookup tool. Independent, civic-tech, MIT code, CC-BY-4.0 data.

**Author:** Xavier Puspus (independent researcher). DPO contact: `xpuspus@gmail.com`.

**Launch date:** 2026-05-13 (planned). Pre-launch state is captured in this document and on GitHub at `xmpuspus/solar-map-ph`.

---

## The five-line summary

- Frozen CLIP-ViT-L image encoder plus logistic-regression head; Platt-calibrated; bit-exact reproducible from a committed embeddings cache.
- F1 = 0.870 at threshold 0.85 (precision 95.9%, recall 79.7%) on an honest 20% held-out source-disjoint split.
- 515 rooftop solar detections across 41 cities (280 high-confidence, 235 below-threshold candidates).
- 87% of high-confidence detections (242 of 277 that landed inside a city polygon) are not on any prior public map of solar, using the same 200 m proximity threshold convention as DeepSolar (Stanford, 2018) and SPECTRUM (ICSC, 2025).
- 384 buildings with per-roof panel polygons after SAM segmentation, 69.9 MWp aggregate installed capacity. 27 residential rooftops released as an aggregate count only (no geometry, no addresses) under RA 10173.

## Why it matters

The Philippines is at a turning point on solar policy. Roughly 22 million people live in Meralco's franchise. ICSC estimates one-third of rooftop solar there is unregistered. The DOE's April 2026 circular tries to fix net-metering processing time (10 working days target). LGU permit fees range from ₱16,000 to ₱153,000 for the same 520 kWp project depending on the LGU.

What's been missing is a public, reproducible, methodologically transparent picture of where rooftop solar already is in the franchise. SolarMap.PH fills that gap. It also gives Filipino homeowners a free, no-signup, browser-only tool to size their own roof against the published kWp distribution, their LGU's permit cost where verified, and the current Meralco residential rate.

## What it isn't

- Not engineering advice. The homeowner tool is informational. A certified installer's site survey is still required.
- Not a permit registry, tax record, or code-compliance audit. SolarMap.PH publishes statistical indicators derived from public data. Patterns may have legitimate explanations.
- Not affiliated with Meralco, DOE, NREB, ICSC, or any regulatory body. Independent civic-tech.

## What's published

- Open-source repo: `https://github.com/xmpuspus/solar-map-ph` (MIT code, CC-BY-4.0 data)
- Live homeowner tool + map: `https://solarmap.ph`
- Model and embeddings on Hugging Face: `xmpuspus/solar-map-ph-clf-v4`
- Per-building GeoJSON: `site/public/data/per_building_solar_ncr.geojson`
- Residential aggregate roll-up: `site/public/data/residential_solar_aggregate.json`
- Privacy Impact Assessment: `docs/privacy-impact-assessment.md`
- Methodology: `https://solarmap.ph/methodology`

## Headline numbers, at a glance

| Metric | Value | Source file |
|---|---|---|
| Detections (all tiers) | 515 | `rooftop_solar_ncr.geojson` |
| High-confidence detections (score >= 0.85) | 280 | same |
| Below-threshold candidates (0.70 to 0.85) | 235 | same |
| Cities with at least one detection | 41 | `city_detection_counts.json` |
| High-confidence detections not on prior public map | 242 of 277 (87%) | same |
| Per-building polygons (post-SAM, non-residential) | 384 | `per_building_solar_ncr.geojson` |
| Aggregate identified installed capacity | 69.9 MWp | same |
| Residential rooftops with detected solar (count only) | 27 | `residential_solar_aggregate.json` |
| Holdout F1 at threshold 0.85 | 0.870 | `clf_v4_calibration.json` |
| Holdout precision / recall at t=0.85 | 95.9% / 79.7% | same |
| Tiles scanned (NCR 240 m grid) | 16,544 | `_meta.total_tiles_scanned` |
| Classifier sha256 prefix (reproducibility hash) | `56900722a8427be4` | `make hash-verify` |

## Method, in one paragraph

Two parallel pipelines, two resolutions. The detection pipeline embeds 600x600 px Esri World Imagery tiles with a frozen `openai/clip-vit-large-patch14` encoder, scores them with a logistic-regression head trained on 294 OSM-tagged positives plus four active-learning rounds (Platt-calibrated on a 20% source-disjoint holdout), then routes high-confidence tiles through SAM auto-mask segmentation plus a color-signature filter plus an OSM-building intersection to produce per-roof panel polygons. The Earth Engine pipeline reduces Sentinel-2 NIR/SWIR median, Landsat 8/9 land surface temperature, and VIIRS DNB nightlights to per-city statistics, z-scores them across cities, and weights them (0.4 NIR, 0.3 SWIR, 0.2 LST, 0.1 nightlight) into a composite signal. ESA WorldCover masks vegetation and water; Microsoft GlobalMLBuildingFootprints provides per-city building denominators. The composite signal is correlative, not diagnostic, at city scale.

## Key media-relevant facts

- **The "informal solar" gap is real.** Meralco's public-reports registry: roughly 170 MW formal. ICSC estimate of informal: roughly one-third of installs. Estimated commercial-scale rooftop outside the program: about 370 MW. Total estimated rooftop fleet in the franchise: about 500 MW.
- **The bottleneck is LGU permitting, not Meralco.** Sen. Gatchalian has been pushing streamlining. The DOE April 2026 circular targets a 3-day LGU permit ceiling and deemed-approved on LGU silence. Adoption is uneven.
- **Meralco's technical asks are legitimate.** Anti-islanding compliance, equipment certification, installer accreditation are real engineering concerns. The fight isn't over the engineering; it's over the cost-recovery economics of net metering at full retail rate.
- **The 100 kW net-metering cap is structural.** ERC has been cautious about cap-raise (cross-subsidy concerns). Sen. Grace Poe has pushed cap-raise legislation since 2018.

## Privacy posture (RA 10173)

- Residential roof geometry is not published. Residential buildings tagged `house`, `apartments`, `residential`, etc. are aggregated to counts only.
- Per-building features published only for commercial / industrial / public-purpose roofs. These are institutional subjects, not natural persons.
- Build-time CI gate (`scripts/check_no_residential_leaks.py`) fails if any residential feature reaches the public dataset.
- DPO (self-designated): Xavier Puspus, `xpuspus@gmail.com`. Formal NPC voluntary advisory opinion is in scope for the post-launch quarter.
- Takedown channel: GitHub issue with `takedown` label, or email. Acknowledged within 5 working days; removed within 14 working days at the next quarterly republish.

## Contact

- DPO / data inquiries: `xpuspus@gmail.com`
- Author (Xavier Puspus): same email; LinkedIn `/in/xpuspus`
- Issues, PRs, contributions: GitHub `xmpuspus/solar-map-ph`

## Suggested attribution if you cite

> SolarMap.PH (2026-Q2). Open-source rooftop solar detection from public satellite imagery. https://github.com/xmpuspus/solar-map-ph. CC-BY-4.0.

---

*All data sourced from public records (Esri World Imagery, OpenStreetMap, ESA, Microsoft, NOAA, NASA). SolarMap.PH computes statistical indicators derived from public data. Patterns may have legitimate explanations. The published per-building dataset is for commercial, industrial, and public-purpose rooftops only at sub-building resolution.*
