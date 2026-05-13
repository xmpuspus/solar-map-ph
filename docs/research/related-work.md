# Related projects

Other tools and research efforts working in the same space as SolarMap.PH. Credit and context, not competitive ranking. If you've shipped something in PH solar mapping that isn't here, please open a PR.

## PH-focused

### SPECTRUM (ICSC, July 2025)

- Organization: Institute for Climate and Sustainable Cities
- Reference: https://icsc.ngo/solar-mapper/ ; SolarQuarter coverage: https://solarquarter.com/2025/07/17/icsc-unveils-ai-powered-spectrum-platform-to-map-rooftop-solar-systems-nationwide/
- Scope: nationwide PH, 174+ cities at launch, expanding to 400. AI-powered rooftop solar detection plus capacity estimation. Reported accuracies: 87.6% residential / 87.1% commercial / 98.5% utility-scale.
- Relationship to SolarMap.PH: closest sibling project. SPECTRUM has broader geographic coverage (nationwide); SolarMap.PH currently covers Greater Metro Manila with a published reproducibility chain (open weights, open training embeddings, deterministic build). The projects are complementary: SPECTRUM's coverage gives nationwide priors, SolarMap.PH's open chain gives a verifiable workflow.

### REMap (DOE / NREB)

- Reference: https://www.doe.gov.ph (subsite varies). REMap is the National Renewable Energy Board's national renewable energy resource map.
- Scope: irradiance and resource potential (mostly LiDAR + irradiance models), not rooftop panel detection.
- Relationship: complementary. REMap answers "where could solar go," SolarMap.PH answers "where did it actually go."

### Global Solar Atlas (with PH layers)

- Reference: https://globalsolaratlas.info
- Operator: World Bank Group + Solargis
- Scope: solar resource (irradiance, PV potential) for almost every country including PH.
- Relationship: complementary. Resource not installation.

## International rooftop-solar detection precedents

### DeepSolar (Stanford, 2018)

- Yu et al., Joule 2018: https://www.sciencedirect.com/science/article/pii/S2542435118305701
- Scope: US-wide rooftop solar detection from satellite imagery via CNN.
- Relationship: methodological prior art. SolarMap.PH borrows the broad framing (CNN on aerial imagery, per-region inference, public release of detections) but uses a CLIP-ViT-L frozen encoder + logistic regression head rather than DeepSolar's end-to-end fine-tuned VGG / Inception architecture. The newer encoder choice is more sample-efficient for the small-PH-positive regime.

### PV_Pipeline (helioml, 2019)

- Reference: https://github.com/yourplacelab/PV_Pipeline
- Scope: open-source pipeline for detecting rooftop PV in aerial imagery, primarily focused on US datasets.
- Relationship: prior open-source pipeline. SolarMap.PH adopts a similar two-stage approach (tile classifier + segmentation) but with SAM auto-mask in place of pixel-level supervised segmentation, and with a public-OSM-footprint join in place of parcel data.

### Esri ArcGIS rooftop solar pretrained models

- Reference: https://www.arcgis.com/home/group.html?id=a4ddcd9bd96b4f0993e6cd2c2dd31370 (ArcGIS Living Atlas, solar models)
- Scope: Esri ships pretrained solar-panel detection models for ArcGIS users.
- Relationship: Esri's own usage of its World Imagery for solar detection sets the precedent for our attribution-only fair-use posture on the training imagery.

### Microsoft GlobalMLBuildingFootprints

- Reference: https://github.com/microsoft/GlobalMLBuildingFootprints
- Scope: machine-learning-generated building footprints worldwide.
- Relationship: SolarMap.PH uses Microsoft GlobalMLBuildingFootprints as the per-city building-count denominator in the Earth Engine quarterly pipeline.

### Segment Anything (Meta, 2023)

- Reference: https://segment-anything.com
- Scope: foundation model for image segmentation.
- Relationship: SolarMap.PH uses the SAM auto-mask generator to convert tile-level positive detections into panel-area polygons. Auto-mask + color-signature filter + OSM-building intersection is the segmentation stack.

### CLIP (OpenAI, 2021)

- Reference: https://openai.com/research/clip
- Scope: contrastive vision-language pretraining.
- Relationship: SolarMap.PH's encoder is `openai/clip-vit-large-patch14`. Encoder ablation against `facebook/dinov2-large` and `allenai/satlas-pretrain` favored CLIP by 4 pt and 14 pt F1 respectively. See `MODEL_CARD.md` for the full table.

## Earth-observation infrastructure

### ESA WorldCover

- Reference: https://esa-worldcover.org
- License: CC-BY-4.0.
- Use: vegetation and water masking for the EE quarterly pipeline.

### Sentinel-2 and Landsat 8/9

- Operators: ESA Copernicus; NASA/USGS.
- License: public domain.
- Use: NIR/SWIR median (Sentinel-2) and land surface temperature (Landsat) for the EE quarterly composite signal.

### VIIRS Day/Night Band

- Operator: NOAA.
- License: public domain.
- Use: nightlight component of the EE quarterly composite signal.

### Photon / Komoot

- Reference: https://photon.komoot.io
- License: BSD on the geocoder; OSM tile data ODbL.
- Use: homeowner roof-lookup tool autocomplete + fallback geocoding.

### Nominatim / OpenStreetMap

- Reference: https://nominatim.openstreetmap.org
- License: ODbL.
- Use: homeowner tool geocoding fallback; building tagging.

### Overpass API

- Reference: https://overpass-api.de
- License: ODbL on the queried data.
- Use: building-footprint and tag lookup for the homeowner tool and the per-building pipeline.

### PVGIS (European Commission JRC)

- Reference: https://re.jrc.ec.europa.eu/pvg_tools/en/
- License: free for use with attribution.
- Use: solar irradiance lookup for payback computation in the homeowner tool.

## Civic-tech and policy precedents in the PH solar conversation

- ICSC reporting on the informal-solar / "guerrilla solar" gap.
- Sen. Sherwin Gatchalian's streamlining advocacy (Senate Energy committee).
- DOE April 2026 circular on net-metering approval (10 working days, deemed-approved on LGU silence, 3-day electrical permit).
- ERC's structurally cautious posture on net-metering cap-raise and full-rate compensation.
- Power Philippines reporting on LGU permit fee variance (₱16K-153K for the same project across LGUs).

See `docs/research/policy-context.md` for the full five-actor map.
