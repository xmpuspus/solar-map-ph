# SolarMap.PH pipeline targets.
# Targets are ordered so `make all` reproduces clf_v4 + the calibrated
# bundle from a clean checkout; `make train` is the deterministic subset
# that runs from the cached dataset_v4.npz embeddings (no network).

PY := python3
DETECTION := detection
TRAIN := $(DETECTION)/train
SCAN := $(DETECTION)/scan
VERIFY := $(DETECTION)/verify
DATA := site/public/data

# v1.2: clf_v5 is the canonical classifier (region-stratified retrain).
# NCR's published GeoJSON stays clf_v4-scored (v1.2 does not re-scan NCR);
# the NCR scan rule below pins clf_v4 explicitly for that reproduction.
DATASET := $(TRAIN)/dataset_v5.npz
CLF := $(TRAIN)/clf_v5.joblib
CLF_METRICS := $(TRAIN)/clf_v5_metrics.json
CLF_V4 := $(TRAIN)/clf_v4.joblib
CAL_BUNDLE := $(TRAIN)/v5_region_holdout/clf_v5_calibrated.joblib
CAL_JSON := $(TRAIN)/v5_region_holdout/clf_v5_calibration.json
SCAN_RESULTS := $(SCAN)/ncr_scan_results_v3.jsonl
GEOJSON := $(DATA)/rooftop_solar_ncr.geojson

.PHONY: all train calibrate scan aggregate verify-sheets demo hash hash-verify plots status sam test clean help check-region-pii verify-v11 scan-regions

help:
	@echo "SolarMap.PH pipeline targets:"
	@echo "  make all          Full pipeline: dataset to train to calibrate to scan to aggregate"
	@echo "  make train        Train clf_v4 from cached dataset_v4.npz (deterministic, no network)"
	@echo "  make calibrate    Holdout split + Platt sigmoid (+ isotonic comparison)"
	@echo "  make scan         Re-classify cached tiles with clf_v4"
	@echo "  make aggregate    Build GeoJSON + OSM cross-match"
	@echo "  make verify-sheets Rebuild verification 3x3 sheets for next active-learning round"
	@echo "  make demo         Print summary of the calibrated bundle"
	@echo "  make hash         Print sha256 of clf_v4.joblib"
	@echo "  make hash-verify  Assert clf_v4.joblib matches the canonical sha256 ($(EXPECTED_HASH))"
	@echo "  make plots        Render PR + ROC + reliability diagrams to docs/figures/"
	@echo "  make status       Print partial-state inventory (dataset/clf/scan/aggregate timestamps)"
	@echo "  make check-region-pii   Assert every region GeoJSON is point-tile only, no PII fields"
	@echo "  make verify-v11   Run the full v1.1 release-readiness gate runner"
	@echo "  make scan-regions Sequentially scan all v1.1 cross-domain regions"
	@echo "  make sam          Download the SAM ViT-B checkpoint (375 MB)"
	@echo "  make test         Run the pytest suite"
	@echo "  make clean        Remove generated artifacts"

all: $(GEOJSON) $(CAL_BUNDLE)
	@echo
	@echo "[make all] DONE."
	@$(MAKE) -s hash-verify

# ----- training (v1.2: region-stratified clf_v5) -----
# build_dataset_v5 needs region_labels.jsonl (harvested spot-check verdicts) +
# the per-region OSM positives; it adds them to dataset_v4 and embeds.
$(DATASET): $(TRAIN)/build_dataset_v5.py $(TRAIN)/region_labels.jsonl $(TRAIN)/dataset_v4.npz
	$(PY) $(TRAIN)/build_dataset_v5.py

$(TRAIN)/region_labels.jsonl: $(TRAIN)/harvest_spotcheck_labels.py
	$(PY) $(TRAIN)/harvest_spotcheck_labels.py

$(CLF): $(DATASET) $(TRAIN)/train_v5.py $(TRAIN)/v5_region_holdout/holdout_split.json
	$(PY) $(TRAIN)/train_v5.py

train: $(CLF)
	@echo "[make train] $(CLF) ready"

# ----- calibration (v1.2: per-domain, scan-realistic holdout) -----
$(TRAIN)/v5_region_holdout/holdout_split.json: $(TRAIN)/region_labels.jsonl $(TRAIN)/v5_region_holdout/build_region_holdout.py
	$(PY) $(TRAIN)/v5_region_holdout/build_region_holdout.py

$(CAL_BUNDLE): $(TRAIN)/v5_region_holdout/holdout_split.json $(TRAIN)/v5_region_holdout/train_calibrated_v5.py $(CLF)
	$(PY) $(TRAIN)/v5_region_holdout/train_calibrated_v5.py

calibrate: $(CAL_BUNDLE)
	@echo "[make calibrate] $(CAL_BUNDLE) ready"

# ----- scan + aggregate -----
# NCR's published detections are clf_v4-scored; v1.2 does not re-scan NCR.
$(SCAN_RESULTS): $(CLF_V4) $(SCAN)/ncr_scan.py
	$(PY) $(SCAN)/ncr_scan.py --reuse-tiles --clf $(CLF_V4) --results-jsonl $(SCAN_RESULTS) --no-aggregate

scan: $(SCAN_RESULTS)
	@echo "[make scan] $(SCAN_RESULTS) ready"

$(GEOJSON): $(SCAN_RESULTS) $(SCAN)/aggregate_and_compare.py
	$(PY) $(SCAN)/aggregate_and_compare.py

aggregate: $(GEOJSON)
	@echo "[make aggregate] $(GEOJSON) ready"

verify-sheets: $(GEOJSON)
	$(PY) $(VERIFY)/build_verification_sheets.py

# ----- smoke -----
EXPECTED_HASH := 5cc0a093c5279fd9

hash:
	@$(PY) -c "import hashlib; print('clf_v5.joblib sha256:', hashlib.sha256(open('$(CLF)','rb').read()).hexdigest()[:16])"

hash-verify: $(CLF)
	@actual=$$($(PY) -c "import hashlib; print(hashlib.sha256(open('$(CLF)','rb').read()).hexdigest()[:16])"); \
	if [ "$$actual" = "$(EXPECTED_HASH)" ]; then \
	  echo "[hash-verify] OK: clf_v5.joblib sha256 = $$actual"; \
	else \
	  echo "[hash-verify] FAIL: clf_v5.joblib sha256 = $$actual (expected $(EXPECTED_HASH))"; \
	  echo "[hash-verify] Likely cause: dependency version drift. Verify requirements.txt pins are honored."; \
	  exit 1; \
	fi

# Regenerate the precision-recall, ROC, and reliability diagrams.
plots: $(CAL_JSON)
	$(PY) scripts/plot_pr_curve.py

demo: $(CAL_BUNDLE)
	@$(PY) -c "import joblib, json; \
b = joblib.load('$(CAL_BUNDLE)'); \
m = json.load(open('$(CAL_JSON)')); \
print('clf_v5_calibrated bundle:'); \
print('  encoder:', b['encoder']); \
print('  per-region calibration status:', b['calibration_status']); \
[print('  {}: P@0.85={} R@0.85={} (n_pos={})'.format(s, v.get('at_t085',{}).get('precision'), v.get('at_t085',{}).get('recall'), v.get('n_holdout_pos'))) for s,v in m['regions'].items() if v.get('calibration_status')=='calibrated']"

clean:
	rm -f $(DATASET) $(CLF) $(CLF_METRICS) $(CAL_BUNDLE) $(CAL_JSON)
	rm -rf $(TRAIN)/v4_calibrated/ablation

# Inventory of partial state. Useful after a crash to see what's pending.
SAM_CKPT := $(SCAN)/sam_checkpoints/sam_vit_b_01ec64.pth
status:
	@echo "SolarMap.PH state inventory"
	@echo "  dataset_v5.npz       : $$(test -f $(DATASET) && stat -f '%Sm %z' -t '%Y-%m-%dT%H:%MZ' $(DATASET) 2>/dev/null || echo 'missing')"
	@echo "  clf_v5.joblib        : $$(test -f $(CLF) && stat -f '%Sm %z' -t '%Y-%m-%dT%H:%MZ' $(CLF) 2>/dev/null || echo 'missing')"
	@echo "  clf_v5 sha256        : $$(test -f $(CLF) && $(PY) -c "import hashlib; print(hashlib.sha256(open('$(CLF)','rb').read()).hexdigest()[:16])" 2>/dev/null || echo 'missing')"
	@echo "  calibrated bundle    : $$(test -f $(CAL_BUNDLE) && stat -f '%Sm' -t '%Y-%m-%dT%H:%MZ' $(CAL_BUNDLE) 2>/dev/null || echo 'missing')"
	@echo "  scan results jsonl   : $$(test -f $(SCAN_RESULTS) && echo "$$(wc -l < $(SCAN_RESULTS)) tiles" || echo 'missing')"
	@echo "  rooftop geojson      : $$(test -f $(GEOJSON) && stat -f '%Sm' -t '%Y-%m-%dT%H:%MZ' $(GEOJSON) 2>/dev/null || echo 'missing')"
	@echo "  SAM checkpoint       : $$(test -f $(SAM_CKPT) && echo 'present' || echo 'missing (run: make sam)')"

# Download the SAM ViT-B checkpoint. Required by `make sam-segments` only.
sam: $(SAM_CKPT)

$(SAM_CKPT):
	mkdir -p $(SCAN)/sam_checkpoints
	curl -L --fail -o $(SAM_CKPT) https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth
	@echo "[sam] downloaded $$(du -h $(SAM_CKPT) | awk '{print $$1}') to $(SAM_CKPT)"

test:
	pytest tests/ -q

# ----- v1.1 multi-region release gates -----
check-region-pii:
	$(PY) scripts/check_region_no_pii.py

verify-v11:
	$(PY) scripts/verify_v11_release.py --skip-build

scan-regions:
	bash scripts/run_all_v11_regions.sh
