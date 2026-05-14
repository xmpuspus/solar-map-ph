# Cagayan de Oro v1.1 cross-domain spot-check findings (2026-05-14)

Visual inspection of the top 5 scored CDO detections from applying the NCR-trained `clf_v4.joblib` to a built-up-prefiltered CDO scan (2,704 tiles after the ESA WorldCover 5% built-up cut, scanned at 240 m grid, 400 px Esri export).

## Per-tile verdicts

| # | Score | Tier | Tile (lat_lon) | Verdict |
|---|---|---|---|---|
| 0 | 0.920 | high | 8.57788_124.77216 | REAL rooftop solar. Large industrial complex with full-roof panel coverage. Confirmed. |
| 1 | 0.913 | high | 8.57788_124.77440 | REAL rooftop solar. Adjacent tile from the same industrial complex; same rooftop array. Confirmed. |
| 2 | 0.881 | high | 8.43532_124.66016 | **GROUND-MOUNT solar farm.** Utility-scale solar farm on open ground; the model fires correctly but the detection is not a rooftop. Same FP class as the NCR Valenzuela and Cebu Naga detections. |
| 3 | 0.836 | candidate | 8.55628_124.78784 | **GROUND-MOUNT solar farm.** Large utility array filling the entire tile. Not rooftop. |
| 4 | 0.828 | candidate | 8.49364_124.63328 | REAL rooftop solar. Commercial building (auto dealership / hotel) with panel array on the main white roof. Confirmed. |

## Summary

- 3 out of 5 visually verified as **rooftop solar** at the detection location.
- 2 out of 5 are **ground-mount utility solar farms.** Same FP class as NCR and Cebu; CEPALCO franchise area has more visible solar-farm infrastructure than the Visayan or Bicol regions.
- 60% rooftop precision in the top-5 sample. Lower than Iloilo (5/5) and Cebu (7/8) because CDO has more ground-mount installations in the scan footprint.

## Implications for v1.1 publication

- CDO (CEPALCO franchise) ships as published with the cross-domain disclosure. 3 high-confidence + 6 candidate detections.
- The ground-mount false-positive rate motivates the v1.2 mount-type classifier (rooftop vs ground-mount) which is the highest-value next addition for CEPALCO area in particular.
- Active-learning round on a larger CDO sample queued for v1.2.
