# Privacy Impact Assessment: SolarMap.PH

**Project:** SolarMap.PH (https://github.com/xmpuspus/solar-map-ph)
**Author / Self-designated DPO:** Xavier Puspus (`xpuspus@gmail.com`)
**Assessment date:** 2026-05-13
**Applicable law:** Republic Act 10173 (Data Privacy Act of 2012), implementing rules, NPC circulars in force as of 2026-05-13 (including NPC Circular 2024-02 on CCTV).
**Status:** Self-conducted PIA. Formal NPC voluntary advisory opinion is in scope for the post-launch quarter.

---

## 1. Purpose of processing

SolarMap.PH applies a frozen CLIP-ViT-L image encoder and a logistic-regression classifier to publicly licensed Esri World Imagery tiles over Greater Metro Manila to detect rooftop solar PV installations. Detection outputs are intersected with public OpenStreetMap building footprints and Earth Engine land cover masks to produce two outputs: (a) per-building polygons for commercial / industrial / public-purpose roofs, and (b) aggregated counts and capacities for residential roofs.

The intended use is civic-tech research on the gap between informal ("guerrilla") rooftop solar and the formal net-metering registry, supporting public-interest reporting and policy discussion on solar adoption in the Philippines.

---

## 2. Categories of information processed

| Category | Source | Identifiability | Disposition |
|---|---|---|---|
| Satellite tile imagery (RGB raster, 256-1024 px) | Esri World Imagery | Indirect: buildings visible | Not republished. Used as model input only. |
| Building footprint polygons | OpenStreetMap (ODbL) | Indirect: buildings on a public map | Used for spatial intersection. Republished only for non-residential. |
| Building tags (`building=*`) | OpenStreetMap | Categorical: public OSM crowd-sourced | Used to filter out residential. Tag values published only for non-residential. |
| Classifier scores | Computed locally | None (a probability number) | Published per-tile, per-building. |
| LGU / city name | Boundary join | None (administrative) | Published. |
| Tile coordinates / building OSM way id | Computed | Indirect (joining to OSM exposes the same data already on osm.org) | Published only for non-residential. |
| Capacity estimate (kWp) | Computed from segmented panel area | None | Published only for non-residential; residential summed only. |

No direct identifiers are collected: no names, no email, no phone, no national ID, no electric-meter serial, no tax declaration number.

---

## 3. RA 10173 §3 analysis

### §3(g) "personal information"

> "any information ... from which the identity of an individual is apparent or can be reasonably and directly ascertained ... or when put together with other information would directly and certainly identify an individual."

- A latitude/longitude pair plus "solar=yes" alone does not name a person.
- The "put together with other information" clause is the legal exposure: combining a coordinate with a barangay registry, a tax declaration, or an electric-meter address could re-identify a household.
- **Mitigation:** Residential rooftops are aggregated into counts only; no geometry, no coordinates, no addresses, no OSM way id at residential resolution. Only commercial / industrial / public-purpose features are released at sub-building resolution, where the data subject is institutional, not natural.

### §3(c) "consent"

Public satellite imagery and public OSM tagging do not require subject consent under the public-records doctrine inherent to RA 10173's coverage. NPC Circular 2024-02 (CCTV) treats public-space image capture as DPA processing; we do not capture, store, or republish raw imagery; we only publish derived model outputs. The publication boundary (residential aggregation, takedown channel, attribution chain) is the responsibility-shifting mechanism in lieu of per-subject consent.

### §11 "general data privacy principles"

- **Transparency:** This PIA, `/privacy`, and `SECURITY.md` document scope, purpose, and recipients.
- **Legitimate purpose:** Civic-tech research on a policy debate of public interest (net-metering gap, LGU permit variance).
- **Proportionality:** Only roof polygons necessary for the research question are processed; residential is aggregated.

---

## 4. Risks and mitigations

| Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|
| Residential roof leaks into per-building dataset | Medium without controls; **Low** with `check_no_residential_leaks.py` CI gate | High | Automated CI script + reviewer sign-off; failure halts the build. |
| Re-identification by combining lat/lon with external public data | Medium for non-residential, Low for residential (no residential geometry published) | Medium | Residential aggregated; commercial features are institutional, not individual. |
| Misuse as a "ghost solar" enforcement list | Low (Meralco / LGU don't need our data, they already have the meter registry) | Medium | Conservative language across copy ("flagged for review", "warrants further investigation"). Disclaimer block on every analytics surface. Takedown channel published. |
| Detection error harming a specific party | Medium | Low-Medium (we publish confidence, calibration, methodology; readers can verify) | Public confidence scores, per-feature OSM link, "report false positive" CTA on every detection card. |
| Esri ToS / OSM ODbL non-compliance | Low (attribution-only) | Medium | Attribution section in README, MapView corner credit, MODEL_CARD intended-use section. |
| Vulnerability in joblib deserialization | Low | High | SECURITY.md flags `joblib.load`. Classifier hash verifiable via `make hash-verify`. `verify_clf.py` helper. |
| Inability to delete a feature once published | Low | Medium | Quarterly republish cadence; takedown channel; git history preserves audit trail; CC-BY-4.0 license requires attribution of derivatives. |

---

## 5. Data lifecycle

| Stage | Location | Retention | Notes |
|---|---|---|---|
| Imagery cache (training) | Local disk, `detection/scan/ncr_tiles/` | Indefinite for reproducibility; not committed to git (.gitignore) | Not republished. |
| Training embeddings | `detection/train/dataset_v4.npz` | Committed to repo, ~11 MB | Encoded features, not raw pixels. |
| Trained classifier | `detection/train/clf_v4.joblib` | Committed; hash-verifiable | Public artifact under MIT. |
| Per-building output | `site/public/data/per_building_solar_ncr.geojson` | Quarterly republish | Subject to residential-leak CI gate. |
| Residential aggregate | `site/public/data/residential_solar_aggregate.json` | Quarterly republish | Counts only. |
| Takedown requests | GitHub issues, email | Public audit trail in issue history | Personal info in email redacted before any public response. |

---

## 6. Recipients

- Public web (CC-BY-4.0): aggregated maps, per-building polygons for non-residential.
- Researchers / press / public-interest organizations: same as public web.
- LGUs, DOE, NREB, NPC, ICSC, UPD CEEPRRE: same as public web; no privileged channel.
- Third-party geocoders (Photon, Nominatim, Overpass, PVGIS): see the address typed into the homeowner roof-lookup tool only; SolarMap.PH retains no log of these queries.

---

## 7. DPO and accountability

- **DPO (self-designated):** Xavier Puspus, `xpuspus@gmail.com`.
- **Formal NPC registration:** scoped for post-launch quarter, deferrable contingent on traffic and feedback.
- **Review cadence:** PIA re-reviewed at each quarterly republish.
- **Last reviewed:** 2026-05-13.

---

## 8. Conclusion

SolarMap.PH publishes statistical indicators derived from public satellite imagery and public OSM tagging. The publication boundary (residential aggregation, conservative language, takedown channel, CSP-enforced third-party endpoints, hash-verified classifier) is, in the author's good-faith judgment, sufficient to satisfy the proportionality and transparency principles of RA 10173 for an inaugural launch. The PIA will be re-reviewed each quarter, and a formal NPC advisory opinion will be sought in the post-launch quarter as scale or scope warrants.
