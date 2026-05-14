# Davao City v1.1 cross-domain spot-check findings (2026-05-15)

Visual inspection of the top 5 scored Davao detections from applying the NCR-trained `clf_v4.joblib` to a built-up-prefiltered Davao scan (5,295 tiles after the ESA WorldCover 5% built-up cut, scanned at 240 m grid, 400 px Esri export).

## Per-tile verdicts

| # | Score | Tier | Tile (lat_lon) | Verdict |
|---|---|---|---|---|
| 0 | 0.990 | high | 7.04980_125.58784 | REAL rooftop solar. Massive industrial-scale array covering an entire commercial/mall roof. The largest single installation in this sample. Confirmed. |
| 1 | 0.983 | high | 6.93532_125.46912 | REAL rooftop solar. Industrial complex with full-roof panel coverage. Confirmed. |
| 2 | 0.981 | high | 6.97420_125.48032 | REAL rooftop solar. Multi-bay commercial building with extensive solar arrays. Confirmed. |
| 3 | 0.980 | high | 7.04980_125.59008 | REAL rooftop solar. Diagonal mall roof entirely covered with solar panels. Confirmed. |
| 4 | 0.972 | high | 6.87052_125.44896 | REAL rooftop solar. Industrial complex with multiple panel arrays across paired roofs. Confirmed. |

## Summary

- 5 out of 5 visually verified as **rooftop solar** at the detection location, all at the high-confidence tier (>= 0.85).
- 0 false positives in this top-5 sample.
- Davao City (DLPC franchise) has the largest single-tile installations of any v1.1 cross-domain region. The top tiles include what appear to be major industrial and commercial roof arrays exceeding the scale visible in Cebu or Iloilo's tops.

## Implications for v1.1 publication

- Davao ships as published. 28 high-confidence + 19 candidate detections, all assigned to Davao City (the only LGU polygon we have for this region).
- 100% rooftop precision in the top-5 sample is consistent with NCR's calibrated 95.9% within a small-sample confidence interval. DLPC's franchise area has high industrial-scale rooftop-solar density relative to other regions in the v1.1 set.
- The 28 high-confidence + 19 candidate inventory is the second largest after NCR (130 + 216). Active-learning round on a larger Davao sample queued for v1.2.
