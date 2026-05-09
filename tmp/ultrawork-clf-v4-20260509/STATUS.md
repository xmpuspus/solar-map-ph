# Ultrawork: clf_v4 + calibration + nationwide

Started: 2026-05-09
Mode: ultrawork "WHATEVER IT TAKES"
Constraints: no auto-commit, local M-series only, CLIP-ViT-L locked unless Phase 3 wins

## Phases

- [ ] Phase 1: Active learning loop — tag 114 v3 high tiles → retrain clf_v4 → /benchmark
- [ ] Phase 2: Holdout split + Platt calibration
- [ ] Phase 3: Encoder ablation (CLIP vs DINOv2 vs SatMAE) — subagent team
- [ ] Phase 4: Reproducibility (pinned deps, Makefile, Dockerfile)
- [ ] Phase 5: Meralco extended franchise (Bulacan/Cavite/Rizal/Laguna)
- [ ] Phase 6: ESA WorldCover built-up pre-filter
- [ ] Phase 7: Luzon scan
- [ ] Phase 8: Visayas + Mindanao scan
- [ ] Phase 9: Nationwide v2.1 per-building (SAM)
- [ ] Phase 10: Public release (/quality-gate, /commit at user signal, /pr, /review --self, /ship)

## Phase 1 sub-state

- 114 tiles in detection/verify/tags.json, ALL UNTAGGED (label: null)
- 23 v3-new tiles in v3_new_tags.json, also untagged
- Sheets: page_00.png .. page_12.png (13 pages × 9 cells = 117 grid slots, 114 actual)
- Tagging cell layout: idx 0..8 = cell 0..8 in 3x3 grid (need to confirm row-major vs col-major)

## Tagging conventions

- "true" — clearly visible rooftop PV array (regular grid of dark/blue panels)
- "false" — no solar (often: reflective roof, dark HVAC, shadow, water, dark roof tile)
- "ambiguous" — could be solar but obscured/single-panel/uncertain

When in doubt, prefer ambiguous over false. Active learning needs CLEAR negatives, not uncertain ones.
