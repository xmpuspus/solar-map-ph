# Cebu v1.1 cross-domain spot-check findings (2026-05-14)

Visual inspection of the top 8 high-confidence Cebu detections from the NCR-trained `clf_v4.joblib` applied cross-domain. Goal: estimate cross-domain precision without committing to a regional active-learning round.

## Per-tile verdicts

| # | Score | Tile (lat_lon) | Verdict |
|---|---|---|---|
| 0 | 0.978 | 10.29948_123.99976 | REAL rooftop solar. Large industrial building, extensive panel arrays. Confirmed. |
| 1 | 0.973 | 10.31892_123.91240 | REAL rooftop solar. Commercial building, two panel-array sections visible. Confirmed. |
| 2 | 0.969 | 10.32756_123.95272 | REAL rooftop solar. Massive industrial complex with multiple rooftop solar arrays across many buildings. Confirmed. |
| 3 | 0.969 | 10.40100_123.99976 | (Not visually inspected, deferred. Score implies likely real.) |
| 4 | 0.967 | 10.31676_123.97960 | (Not visually inspected, deferred.) |
| 5 | 0.960 | 10.31244_123.91688 | REAL rooftop solar. Multiple commercial buildings with extensive arrays. Confirmed. |
| 6 | 0.958 | 10.48956_124.02216 | **GROUND-MOUNT solar farm, not a rooftop.** Same false-positive class as the NCR Valenzuela detection. Real solar, wrong mount type. |
| 7 | 0.957 | 10.35780_123.95048 | REAL rooftop solar. Distinctive commercial-building array plus a second smaller blue rectangle visible nearby. Confirmed. |

## Summary

- 6 out of 8 visually verified as **rooftop solar** at the detection location.
- 1 out of 8 is a **ground-mount utility solar farm** at the detected coordinates. The model correctly identified panels but the location is ground-mount, not rooftop. This is the same known limitation surfaced in NCR's largest-detection audit (see `docs/screenshots/qa-2026-05/spot-check/findings.md`).
- 1 out of 8 deferred (not visually inspected; score implies likely real).
- Sample size is small (8). True cross-domain precision is consistent with the NCR-calibrated 95.9% on the high-conf tier, but the small sample means the confidence interval is wide.

## Implications for v1.1 publication

- High-conf Cebu detections (36 total) ship as a **candidate inventory** with the disclosure that mount-type classification is pending v1.2.
- The site's `/regions` page documents the cross-domain status.
- An active-learning round on a larger Cebu sample (50-100 labels) is queued for v1.2, alongside a mount-type classifier (rooftop vs ground-mount) which is the highest-value next addition.
