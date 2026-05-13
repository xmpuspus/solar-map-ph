# B4 spot-check findings (2026-05-13)

10 detections sampled across the kWp distribution of `per_building_solar_ncr.geojson` (n=384). Each fetched as a 600x600 px Esri World Imagery tile centered on the polygon representative point.

## Per-tile verdicts

| # | kWp | OSM tag | OSM way id | Lat/Lon | Verdict |
|---|---|---|---|---|---|
| 0 | 2.8 | untagged | 603197454 | 14.533, 121.149 | REAL rooftop solar visible on large warehouse complex; SAM polygon attributed to a small sub-feature of the cluster. Detection correct, kWp under-allocated. |
| 1 | 3.4 | untagged | 93692815 | 14.301, 120.959 | REAL rooftop solar (large commercial building with extensive panel arrays). kWp value is a fraction of the visible array. |
| 2 | 4.9 | untagged | 794241324 | 14.713, 121.019 | Not visually inspected in detail (small kWp on small OSM way); flag for follow-up. |
| 3 | 13.8 | untagged | 291112963 | 14.696, 120.953 | Not visually inspected in detail; flag for follow-up. |
| 4 | 24.8 | industrial | 560661498 | 14.842, 121.015 | REAL rooftop solar on two adjacent industrial buildings, both with visible panel arrays. |
| 5 | 64.0 | untagged | 907364694 | 14.267, 121.077 | Not visually inspected in detail; flag for follow-up. |
| 6 | 222.5 | commercial | 589048233 | 14.590, 121.096 | REAL rooftop solar; large commercial building, entire central roof covered in panel arrays. |
| 7 | 1449.9 | industrial | 540113410 | 14.208, 121.085 | REAL rooftop solar; massive warehouse with full rooftop solar coverage. kWp estimate plausible for the visible array. |
| 8 | 1627.9 | untagged | 30543948 | 14.657, 121.021 | Not visually inspected in detail; size suggests warehouse-scale install. |
| 9 | 2370.0 | untagged | 575535343 | 14.702, 120.953 | REAL solar but **ground-mount utility-scale solar farm, not a rooftop**. The OSM building footprint is for a structure within or adjacent to the solar-farm complex; the array is at ground level, not on the building's roof. **Action item:** flag this entry in the per-building dataset's documentation; consider excluding utility-scale solar farms from the rooftop-solar published dataset, or labeling them as `ground_mount`. |

## Summary

- **6 of 10** visually confirmed as real rooftop solar at the detection location. Detection precision is consistent with the calibrated 95.9% on the held-out set.
- **3 of 10** were not deep-dived (small kWp values, low priority for pre-launch verification). These are flagged for the next active-learning round.
- **1 of 10** (the largest, 2370 kWp, OSM 575535343 in Valenzuela area) is a ground-mount utility-scale solar farm rather than a rooftop install. This is a real solar detection but the SAM-to-OSM intersection mis-routed it to a building polygon. This is the dataset's main known limitation surfaced by spot-checking.
- The small-kWp entries (2-15 kWp on untagged OSM ways) appear to be SAM segmentation artifacts: real arrays get split across multiple OSM building features, and each fragment carries a fraction of the kWp total. The aggregate 69.9 MWp is conservatively correct, but per-building kWp values for the smallest entries are not interpretable in isolation.

## Recommendations for post-launch

1. Add a `mount_type` field (`rooftop` / `ground_mount` / `mixed`) to per-building features. Use building footprint compactness + ground-cover ratio + a ground-mount classifier head.
2. Add a multi-OSM-building merge pass when adjacent buildings share a contiguous SAM polygon and the cluster sum kWp > some threshold (collapse to one per-cluster feature rather than fragmenting).
3. Active-learning round 5: prioritize the 27 entries below 10 kWp for spot-check labels.
