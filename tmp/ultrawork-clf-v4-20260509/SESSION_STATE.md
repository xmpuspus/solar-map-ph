# Session state (2026-05-09 ~16:30)

## Active scan
- Process: PID 28303 (`ncr_scan.py --bbox 14.20,120.88,14.85,121.22 --clf clf_v4.joblib --results-jsonl ncr_scan_results_v3.jsonl --no-aggregate`)
- Started: 16:20
- ETA: ~17:00 (41 min from this snapshot)
- Rate: 13.8 tiles/sec (32 fetch workers)
- Progress: 9920 of 43848 todo
- Total target: ~62K JSONL lines after completion

## Current JSONL state
- detection/scan/ncr_scan_results_v3.jsonl: 28400 lines (growing)
  - 16544 original NCR-grid records (clf_v4 classified)
  - 1904 partial-franchise from prior attempt
  - ~10K new from this scan run

## Post-scan recipe (run when scan finishes)

```bash
cd ~/Desktop/ghost-watts
bash detection/scan/finalize_franchise_scan.sh
```

This:
1. Snapshots raw JSONL to baselines
2. Dedupes (drops new-grid records inside NCR bbox - keeps original NCR grid)
3. Re-aggregates GeoJSON
4. Rebuilds verify sheets
5. Prints per-area summary

## Files modified this session
- `detection/scan/ncr_scan.py` — `FETCH_WORKERS` env-var controllable, default 32
- `detection/scan/aggregate_and_compare.py` — _meta updated to v4 + calibrated metrics
- `detection/scan/dedupe_jsonl.py` — drops new-grid NCR overlap, keeps original
- `detection/scan/finalize_franchise_scan.sh` — chained dedupe+aggregate+sheets+summary
- `detection/scan/per_area_summary.py` — NCR vs franchise breakdown
- `site/src/pages/methodology.astro` — v4 active learning + calibration + encoder ablation sections
- `tmp/ultrawork-clf-v4-20260509/PHASE5_REPORT.md` — partial-state report (will rewrite final)

## Projected final state
- NCR (clf_v4, original grid): 130 high + 216 candidate (unchanged)
- Franchise add: ~240 high + ~230 candidate (extrapolating partial)
- Total combined: ~370 high + ~450 candidate
- Scan adds Cavite (lat 14.20-14.40), Bulacan (lat 14.78-14.85), Rizal/Laguna eastern strip
- Aggregate run will update site/public/data/rooftop_solar_ncr.geojson with combined data

## What's left to do this session after scan completes
1. Run finalize_franchise_scan.sh
2. Verify per-area summary numbers
3. Update PHASE5_REPORT.md with final numbers
4. Update SUMMARY.md
5. Update project memory file (project_ghost_watts_clf_v4.md)
6. Update methodology.astro with final franchise detection counts
