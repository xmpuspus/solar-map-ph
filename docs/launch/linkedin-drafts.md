# LinkedIn launch drafts

Three variants, pick one based on audience tilt on launch day. All assume the public URLs are live: github.com/xmpuspus/solar-map-ph, solar-map-ph.vercel.app, huggingface.co/xmpuspus/solar-map-ph-clf-v4. Do NOT post any of these before all three return 200.

Author: Xavier Puspus. Voice: direct, technical, no fluff, no emojis. Hashtags allowed but optional.

---

## Draft 1: Builder voice (machine-learning emphasis)

Open-sourcing SolarMap.PH today.

A computer-vision survey of rooftop solar across Greater Metro Manila plus a free homeowner roof-lookup tool. Frozen CLIP-ViT-L encoder, logistic-regression head, Platt-calibrated, deterministic Docker build, bit-exact reproducible from a 11 MB embeddings cache.

What's in the dataset:
- 515 rooftop solar detections across 41 cities (280 high-confidence)
- 87% of the high-confidence detections are not on any prior public map of solar (200 m proximity threshold, same convention as DeepSolar and SPECTRUM)
- 384 buildings with per-roof panel polygons after SAM segmentation, 69.9 MWp aggregate
- 27 residential roofs aggregated to a count only (no geometry, no addresses) per RA 10173

Calibrated holdout numbers: F1 = 0.870, precision 95.9%, recall 79.7% at threshold 0.85 on an honest 20% source-disjoint split. Encoder ablation against DINOv2-large (-4 pt F1) and Satlas pretrain (-14 pt F1) locks CLIP-ViT-L.

Repo (MIT code, CC-BY-4.0 data): https://github.com/xmpuspus/solar-map-ph
Try the homeowner tool: https://solar-map-ph.vercel.app
Model card on HF: https://huggingface.co/xmpuspus/solar-map-ph-clf-v4

Highest-value contributions, in priority order:
1. Verified false-positive reports on detections in the published per-building dataset
2. LGU permit cost and delay data for cities not already in our friction table
3. Region extensions beyond NCR (Cebu, Davao, Iloilo, Cagayan de Oro)
4. Encoder ablation submissions against Prithvi, SkySense, SatMAE

Civic-tech, open-data, reproducible-from-day-one. Built for the policy debate on the gap between formal net metering and informal rooftop solar.

#opensource #solarenergy #philippines #civictech #remotesensing #computervision

---

## Draft 2: Civic voice (policy emphasis)

ICSC estimates roughly one-third of rooftop solar in Meralco's franchise is unregistered. Senator Gatchalian is pushing streamlining. The DOE's April 2026 circular targets a 3-day LGU permit. Power Philippines documented LGU permit fees ranging from ₱16K to ₱153K for the same 520 kWp commercial install.

Where, exactly?

Here is one answer, computed from public satellite data: SolarMap.PH.

A computer-vision survey across Greater Metro Manila found 515 rooftops with detected solar, 280 above the high-confidence threshold. About 87% of those high-confidence detections are not on any prior public map of solar. 69.9 MWp aggregate installed capacity from 384 buildings the per-roof segmenter localized. Residential roofs are aggregated into counts only, no geometry, no addresses, per the privacy posture documented at /privacy.

This is a civic-tech tool. The data is CC-BY-4.0; the code is MIT. The model card, calibration parameters, training embeddings, and deterministic Docker build are all public. Cite as SolarMap.PH (2026-Q2).

What it's for:
- Journalism and research on the formal-vs-informal solar gap
- LGU-permit-friction comparisons across municipalities
- Public-interest reporting on net-metering policy

What it's not:
- Engineering advice. The homeowner tool is informational; consult a certified installer.
- A permit registry, tax record, or enforcement list. Patterns may have legitimate explanations.

Repo: https://github.com/xmpuspus/solar-map-ph
Site: https://solar-map-ph.vercel.app
Methodology + Privacy Impact Assessment: https://solar-map-ph.vercel.app/methodology and /privacy

Related work credit: ICSC's SPECTRUM (July 2025) is the nationwide solar mapper in this space. SolarMap.PH covers Metro Manila with a published reproducibility chain; the two projects are complementary.

#solarenergy #civictech #philippines #publicinterest #opendata #netmetering

---

## Draft 3: Terse, headline-only

Open-sourced SolarMap.PH today.

515 rooftop solar detections across 41 NCR cities. 87% not on any prior public map. 69.9 MWp aggregate. Calibrated 96% precision on a source-disjoint holdout. MIT code, CC-BY-4.0 data, deterministic build.

https://github.com/xmpuspus/solar-map-ph
https://solar-map-ph.vercel.app

Civic-tech, not engineering advice.

---

## Posting checklist (pre-publish)

- [ ] All three URLs return 200 (gh repo, vercel, hf)
- [ ] OG preview renders correctly when pasting the link into the LinkedIn composer
- [ ] Tag ICSC (related-work credit), if comfortable
- [ ] No PII in any image or text
- [ ] No accusatory language ("ghost," "rogue," "illegal") in the post itself (sources may use these terms; we don't)
- [ ] Schedule for Tuesday-Thursday 9-11am PHT for best reach
