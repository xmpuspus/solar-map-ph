# Ultrawork session summary — clf_v4 + calibration + nationwide

10 phases, 6 completed in this session, 3 deferred to user-runnable recipes, 1 (Phase 10 commit) explicitly held back per user instruction.

## Completed (✓)

| Phase | Headline result | Key file |
|---|---|---|
| 1. Active learning loop | F1 0.918 → **0.938**, +16 high-conf NCR detections | `detection/train/clf_v4.joblib` (sha256 `15564df477c961f2`) |
| 2. Holdout + Platt calibration | Honest P=95.9% R=79.7% @ t=0.85 on never-trained 20% holdout | `detection/train/v4_calibrated/clf_v4_calibrated.joblib` |
| 3. Encoder ablation (3-way) | CLIP-ViT-L wins. DINOv2 -4pt F1, satlas -14pt F1. **CLIP locked.** | `detection/train/v4_calibrated/ablation/*/metrics.json` |
| 4. Reproducibility | Pinned deps, deterministic build (verified same sha256 twice) | `Makefile`, `Dockerfile`, `requirements.txt` |
| 6. Built-up pre-filter | 70% drop on NCR at 5%, 130/130 detections preserved | `detection/scan/built_up_prefilter.py`, `detection/scan/prefilter_ncr.json` |

## Phase 5 — completed in continuation pass

| Metric | NCR-only | NCR + Franchise (now) |
|---|---|---|
| High (≥0.85) | 130 | **266** (+105%) |
| Candidate (0.70–0.85) | 216 | **351** (+63%) |
| % NEW vs OSM (high) | 82% | **85%** |

Bbox extended to (14.20, 120.88, 14.85, 121.22). Scan ran 69 min at 10.5 t/s on 32 fetch workers (vs 1.3 t/s on 12 workers — Esri throttling the low-concurrency lane harder). 43,513 ok / 335 fail / 1,904 skipped. Dedupe drops 16,544 new-grid records inside NCR bbox to preserve original grid; final JSONL is 45,752 lines.

Top franchise sites: SJDM Bulacan, Antipolo Rizal, Cavite/Laguna industrial belt.

## Deferred (recipes provided, awaiting user run)

| Phase | Why not finished | Recipe location |
|---|---|---|
| 7. Luzon scan | ~30 hours at observed 10.5 t/s; needs streaming-fetch wrapper not yet written | `PHASE7_8_9_RECIPES.md` |
| 8. Visayas + Mindanao | Same | Same |
| 9. Per-building SAM nationwide | Depends on 7+8 | Same |
| 10. /commit + /pr + /review --self + /ship | User-triggered; not run per "no auto-commit" rule | `PHASE10_READINESS.md` |

## Decisions locked this session

- Encoder: **openai/clip-vit-large-patch14** (won ablation against DINOv2-large + satlas Aerial_SwinB_SI). Don't relitigate without rerunning the ablation harness.
- Threshold: **0.85** mapped via Platt sigmoid `P = sigmoid(1.2916 × decision_function(x) + 0.1627)` to honest 95.9% precision on holdout.
- Holdout split seed: **4242** (deterministic, persisted at `detection/train/v4_calibrated/holdout_split.json`).
- Per-building merge strategy: highest-conf segment polygon, summed area capped at building footprint, kWp = area_m² / 6 (unchanged from v2.1).

## Phase reports

All phase-by-phase details in:
- `tmp/ultrawork-clf-v4-20260509/PHASE1_REPORT.md`
- `tmp/ultrawork-clf-v4-20260509/PHASE2_REPORT.md`
- `tmp/ultrawork-clf-v4-20260509/PHASE3_REPORT.md`
- `tmp/ultrawork-clf-v4-20260509/PHASE4_REPORT.md`
- `tmp/ultrawork-clf-v4-20260509/PHASE5_REPORT.md`
- `tmp/ultrawork-clf-v4-20260509/PHASE7_8_9_RECIPES.md` (covers 7+8+9)
- `tmp/ultrawork-clf-v4-20260509/PHASE10_READINESS.md`

## Notable surprises

- **Thumbnail review under-reports true positives.** First-pass tagging at 480×480 thumbnails called 32/114 high-conf tiles "ambiguous". High-resolution re-inspection found 29 of those 32 were clearly solar (sawtooth roofs, green/blue painted metal roofs that hosted PV arrays, smaller arrays not visible at thumbnail scale). The single FALSE I called (#108) was actually a sawtooth-roof solar installation. Lesson: in the next round, only call AMBIGUOUS for tiles where high-res inspection is genuinely uncertain.
- **One negative isn't enough to teach a pattern.** clf_v4 still scores my single FALSE (#107, blue painted metal roof) at 0.854 in CV. To push the production threshold's precision higher, future rounds need more "blue painted metal" style negatives, not more positives.
- **Network-bound throughput.** Esri serves new tiles at ~1.3 tiles/sec end-to-end on this Mac today. The user's "30 min for 30K tiles" estimate assumed cached imagery. Plan nationwide scans against this rate, or find a faster imagery source.
- **Aerial-pretrained encoder did NOT win.** satlas Aerial_SwinB_SI was specifically trained on aerial imagery yet lost decisively to CLIP-ViT-L on this whole-tile classification task. Massive web-scale pretraining + text grounding > narrow domain pretraining for this kind of binary recognition.

## Working tree state

19 dirty files (8 modified, 11 new). All Phase 1-6 outputs are on disk. clf_v4 hash `15564df477c961f2` is the canonical production model. Ready for `/commit` when you are.
