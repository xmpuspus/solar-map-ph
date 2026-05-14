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

DATASET := $(TRAIN)/dataset_v4.npz
CLF := $(TRAIN)/clf_v4.joblib
CLF_METRICS := $(TRAIN)/clf_v4_metrics.json
CAL_BUNDLE := $(TRAIN)/v4_calibrated/clf_v4_calibrated.joblib
CAL_JSON := $(TRAIN)/v4_calibrated/clf_v4_calibration.json
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

# ----- training -----
$(DATASET): $(TRAIN)/build_dataset_v3.py $(VERIFY)/tags.json
	$(PY) $(TRAIN)/build_dataset_v3.py
	cp $(TRAIN)/dataset_v3.npz $(DATASET)
	cp $(TRAIN)/dataset_v3_manifest.json $(TRAIN)/dataset_v4_manifest.json

$(CLF): $(DATASET) $(TRAIN)/train_v3.py
	$(PY) $(TRAIN)/train_v3.py
	cp $(TRAIN)/clf_v3.joblib $(CLF)
	cp $(TRAIN)/clf_v3_metrics.json $(CLF_METRICS)

train: $(CLF)
	@echo "[make train] $(CLF) ready"

# ----- calibration -----
$(TRAIN)/v4_calibrated/holdout_split.json: $(DATASET) $(TRAIN)/v4_calibrated/holdout_split.py
	$(PY) $(TRAIN)/v4_calibrated/holdout_split.py

$(CAL_BUNDLE): $(TRAIN)/v4_calibrated/holdout_split.json $(TRAIN)/v4_calibrated/train_calibrated.py $(DATASET)
	$(PY) $(TRAIN)/v4_calibrated/train_calibrated.py

calibrate: $(CAL_BUNDLE)
	@echo "[make calibrate] $(CAL_BUNDLE) ready"

# ----- scan + aggregate -----
$(SCAN_RESULTS): $(CLF) $(SCAN)/ncr_scan.py
	$(PY) $(SCAN)/ncr_scan.py --reuse-tiles --clf $(CLF) --results-jsonl $(SCAN_RESULTS) --no-aggregate

scan: $(SCAN_RESULTS)
	@echo "[make scan] $(SCAN_RESULTS) ready"

$(GEOJSON): $(SCAN_RESULTS) $(SCAN)/aggregate_and_compare.py
	$(PY) $(SCAN)/aggregate_and_compare.py

aggregate: $(GEOJSON)
	@echo "[make aggregate] $(GEOJSON) ready"

verify-sheets: $(GEOJSON)
	$(PY) $(VERIFY)/build_verification_sheets.py

# ----- smoke -----
EXPECTED_HASH := 56900722a8427be4

hash:
	@$(PY) -c "import hashlib; print('clf_v4.joblib sha256:', hashlib.sha256(open('$(CLF)','rb').read()).hexdigest()[:16])"

hash-verify: $(CLF)
	@actual=$$($(PY) -c "import hashlib; print(hashlib.sha256(open('$(CLF)','rb').read()).hexdigest()[:16])"); \
	if [ "$$actual" = "$(EXPECTED_HASH)" ]; then \
	  echo "[hash-verify] OK: clf_v4.joblib sha256 = $$actual"; \
	else \
	  echo "[hash-verify] FAIL: clf_v4.joblib sha256 = $$actual (expected $(EXPECTED_HASH))"; \
	  echo "[hash-verify] Likely cause: dependency version drift. Verify requirements.txt pins are honored."; \
	  exit 1; \
	fi

# Regenerate the precision-recall, ROC, and reliability diagrams.
plots: $(CAL_JSON)
	$(PY) scripts/plot_pr_curve.py

demo: $(CAL_BUNDLE)
	@$(PY) -c "import joblib, numpy as np, json, sys; \
b = joblib.load('$(CAL_BUNDLE)'); \
m = json.load(open('$(CAL_JSON)')); \
print('clf_v4_calibrated bundle:'); \
print('  feature_dim:', b['feature_dim']); \
print('  encoder:', b['encoder']); \
print('  Platt: P = sigmoid({:.4f} * decision_function(x) + {:.4f})'.format(b['platt_A'], b['platt_B'])); \
print('  Calibrated holdout @ t=0.85:'); \
print('   ', m['at_calibrated_t085'])"

clean:
	rm -f $(DATASET) $(CLF) $(CLF_METRICS) $(CAL_BUNDLE) $(CAL_JSON)
	rm -rf $(TRAIN)/v4_calibrated/ablation

# Inventory of partial state. Useful after a crash to see what's pending.
SAM_CKPT := $(SCAN)/sam_checkpoints/sam_vit_b_01ec64.pth
status:
	@echo "SolarMap.PH state inventory"
	@echo "  dataset_v4.npz       : $$(test -f $(DATASET) && stat -f '%Sm %z' -t '%Y-%m-%dT%H:%MZ' $(DATASET) 2>/dev/null || echo 'missing')"
	@echo "  clf_v4.joblib        : $$(test -f $(CLF) && stat -f '%Sm %z' -t '%Y-%m-%dT%H:%MZ' $(CLF) 2>/dev/null || echo 'missing')"
	@echo "  clf_v4 sha256        : $$(test -f $(CLF) && $(PY) -c "import hashlib; print(hashlib.sha256(open('$(CLF)','rb').read()).hexdigest()[:16])" 2>/dev/null || echo 'missing')"
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
