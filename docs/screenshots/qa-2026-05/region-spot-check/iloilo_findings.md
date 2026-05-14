# Iloilo v1.1 cross-domain spot-check findings (2026-05-14)

Visual inspection of the top 5 scored Iloilo detections from applying the NCR-trained `clf_v4.joblib` to a built-up-prefiltered Iloilo scan (2,456 tiles after the ESA WorldCover 5% built-up cut, scanned at 240 m grid, 400 px Esri export).

## Per-tile verdicts

| # | Score | Tier | Tile (lat_lon) | Verdict |
|---|---|---|---|---|
| 0 | 0.968 | high | 10.70964_122.55328 | REAL rooftop solar. Large commercial building (shopping centre/warehouse) with a prominent solar array covering most of the main roof. Confirmed. |
| 1 | 0.936 | high | 10.72044_122.55776 | REAL rooftop solar. Industrial-scale installation across multiple bay roofs. Easily the largest single installation in this tile sample. Confirmed. |
| 2 | 0.916 | high | 10.69236_122.47040 | REAL rooftop solar. Commercial building rooftop array fronting a road; small array (~30 panels visible). Confirmed. |
| 3 | 0.850 | high | 10.78740_122.63168 | REAL rooftop solar. Industrial building rooftop with paired solar bays. Confirmed. |
| 4 | 0.815 | candidate | 10.69452_122.56672 | REAL rooftop solar. Several commercial rooftops in the same tile show panel arrays; mall/market complex. Confirmed. |

## Summary

- 5 out of 5 visually verified as **rooftop solar** at the detection location (top scoring tiles).
- 0 false positives in this sample.
- Iloilo's sample precision (5/5) is on the high end of what NCR's calibrated 95.9% predicts; the small sample size means the true population precision could be lower.
- 3 of 5 are at the high-confidence tier (>= 0.85). 2 candidate-tier detections also confirmed real.

## Implications for v1.1 publication

- Iloilo (MORE franchise) ships as published. 3 high-confidence + 6 candidate detections across Iloilo City, Pavia, Leganes, and Oton, with the cross-domain disclosure on /regions.
- The MORE franchise area has noticeably higher rooftop-solar density than Legazpi (Iloilo found 9 detections in 2,456 tiles vs Legazpi's 1 in 734 -- 1.5x normalized rate). Consistent with Iloilo being a denser commercial centre.
- No retraining required; cross-domain precision in this top-5 sample is consistent with NCR's calibrated headline. Active-learning round on a larger Iloilo sample queued for v1.2.
