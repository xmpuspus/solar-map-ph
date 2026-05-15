# Bacolod / Negros Occidental v1.1 cross-domain spot-check findings (2026-05-15)

Visual inspection of the top 3 scored Bacolod detections from applying the NCR-trained `clf_v4.joblib` to a built-up-prefiltered Bacolod scan (2,685 tiles after the ESA WorldCover 5% built-up cut over the CENECO franchise area — Bacolod, Bago, Talisay, Silay, Murcia, Don Salvador Benedicto, EB Magalona — at 240 m grid, 400 px Esri export).

## Per-tile verdicts

| # | Score | Tier | Tile (lat_lon) | LGU | Verdict |
|---|---|---|---|---|---|
| 0 | 0.956 | high | 10.89852_123.06544 | (outside polygon set) | REAL rooftop solar. Large commercial/industrial complex with panel array on the lower-right roof bay. Confirmed. |
| 1 | 0.840 | candidate | 10.64148_122.99600 | Bacolod | REAL rooftop solar. Modest panel array on a warehouse roof; smaller installation than the score implies. Confirmed. |
| 2 | 0.784 | candidate | 10.83372_122.98704 | Silay | REAL rooftop solar. Large warehouse with extensive panel grid covering the left half of the main roof. Confirmed. |

## Summary

- 3 out of 3 visually verified as **rooftop solar** at the detection location.
- 0 false positives in this sample.
- Bacolod's full inventory is **1 high-confidence + 2 candidate detections** across 2,685 built-up tiles. This is the lowest rooftop-solar density in the v1.1 set (after Legazpi's 0+1, which was a false positive). The CENECO franchise area has very low industrial-rooftop-solar density relative to NCR, Calabarzon, or even Cebu / Davao.
- The high-confidence detection (tile 0, score 0.956) falls outside the served-LGU polygon set we currently have for Bacolod (6/7 served LGUs mapped; EB Magalona's OSM admin polygon uses a non-canonical name and is missing). The location is plausibly in EB Magalona based on latitude (~10.90 N).

## Implications for v1.1 publication

- Bacolod ships as a complete scan with 3 real rooftop-solar detections. 100% spot-check precision on the top-3.
- A larger active-learning round on a Bacolod sample is queued for v1.2 alongside expanded LGU polygon coverage (in particular, an OSM relation ID mapping for EB Magalona so the high-confidence detection at 10.90 N gets a proper LGU tag).
- The low detection density is consistent with Negros Occidental's relative scarcity of large industrial complexes vs the Calabarzon belt or NCR.
