# Legazpi v1.1 cross-domain spot-check findings (2026-05-14)

Visual inspection of the single candidate detection produced by applying the NCR-trained `clf_v4.joblib` to a built-up-prefiltered Legazpi scan (734 tiles after the ESA WorldCover 5% built-up cut, scanned at 240 m grid, 400 px Esri export). High-confidence threshold (>= 0.85) was not reached by any tile in this region.

## Per-tile verdicts

| # | Score | Tile (lat_lon) | Verdict |
|---|---|---|---|
| 0 | 0.813 | 13.14428_123.74968 | **FALSE POSITIVE.** Large blue stadium roof, not a rooftop solar array. Same false-positive class as monochrome-blue commercial roofs in NCR. |

## Summary

- 0 of 1 detection is real rooftop solar at the candidate tier; 1 of 1 is a false positive (blue stadium/arena roof).
- No tile scored at the high-confidence tier (>= 0.85).
- Legazpi has very low rooftop-solar penetration in this scan area, consistent with the size of the city (population ~210k) and the rural Albay franchise area.

## Implications for v1.1 publication

- Legazpi ships as published with the single candidate detection clearly tagged at the candidate tier on the /regions page. The cross-domain calibration disclosure applies.
- A larger active-learning round in Bicol regions would be required before SolarMap.PH could claim a calibrated inventory for ALECO's franchise area. Queued for v1.2.
- The blue-roof false-positive pattern is shared with NCR's known limitations; not a region-specific bug.
