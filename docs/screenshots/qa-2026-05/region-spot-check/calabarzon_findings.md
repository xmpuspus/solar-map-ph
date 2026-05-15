# Calabarzon v1.1 cross-domain spot-check findings (2026-05-15, full scan)

Visual inspection of the top 5 scored Calabarzon detections from applying the NCR-trained `clf_v4.joblib` to a built-up-prefiltered Calabarzon scan (18,695 tiles after the ESA WorldCover 5% built-up cut over a 94,213-grid bbox covering the BATELEC, FLECO, QUEZELCO, and LUELCO franchise areas south of Meralco, scanned at 240 m grid, 400 px Esri export).

The scan was completed in two passes: a partial first pass (1,776 tiles, 9.5%) that was throttled by Esri's tile service and shipped with v1.1.0 marked `scan_status: "partial"`, then a resume after the throttle cleared that completed the remaining 16,919 tiles in roughly 2 hours.

## Per-tile verdicts

| # | Score | Tier | Tile (lat_lon) | Verdict |
|---|---|---|---|---|
| 0 | 0.984 | high | 14.24292_121.13336 | REAL rooftop solar. Industrial complex with a prominent panel array on the main bay roof. Confirmed. |
| 1 | 0.984 | high | 14.03340_121.14232 | REAL rooftop solar. Massive multi-roof industrial complex with panels covering every bay. The largest single Calabarzon installation in this sample. Confirmed. |
| 2 | 0.984 | high | 14.28180_120.86456 | REAL rooftop solar. Large mall/commercial complex with a helipad and full-roof panel array. Confirmed. |
| 3 | 0.979 | high | 14.20620_121.09080 | REAL rooftop solar. Industrial estate with two adjacent bay roofs entirely covered in panels. Confirmed. |
| 4 | 0.978 | high | 14.21268_120.96760 | REAL rooftop solar. Large blue commercial roof with a panel grid covering most of the surface. Confirmed. |

## Summary

- 5 out of 5 visually verified as **rooftop solar** at the detection location, all at the high-confidence tier (>= 0.85).
- 0 false positives in this top-5 sample.
- Calabarzon's full scan (18,695 built-up tiles, 19.8% prefilter keep rate) produced **106 high-confidence + 80 candidate detections** across 10 LGUs (Calamba 15+19, Tanauan 12+3, Santo Tomas 9+5, Santa Rosa 6+10, Lipa 5+1, etc.).
- This is the second largest detection inventory in the v1.1 cross-domain set (after NCR's 280 high + 235 candidate). The Calabarzon industrial belt south of Meralco's franchise — Lipa / Calamba / Santo Tomas / Tanauan / Santa Rosa — has the highest industrial-scale rooftop-solar density we've seen outside NCR proper.

## Implications for v1.1 publication

- Calabarzon ships at the v1.1.1 follow-up with `scan_status: "complete"` overriding the partial metadata that shipped with v1.1.0.
- The 100% rooftop precision in the top-5 sample is consistent with NCR's calibrated 95.9%. The industrial concentration in the BATELEC and FLECO franchise areas drives a substantially larger inventory than the Visayan or Bicol regions.
- The combined v1.1 cross-domain total now stands at **176 high-confidence + 165 candidate detections** across 18 LGUs (Cebu 1, Davao 1, Iloilo 4, CDO 1, Legazpi 1, Calabarzon 10), pending Bacolod.
- Active-learning round queued for v1.2 with priority on Calabarzon given the size of the inventory.
