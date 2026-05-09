# ghost-watts pipeline targets.
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

.PHONY: all train calibrate scan aggregate verify-sheets demo hash clean help

help:
	@echo "Ghost-watts pipeline targets:"
	@echo "  make all          Full pipeline: dataset → train → calibrate → scan → aggregate"
	@echo "  make train        Train clf_v4 from existing dataset_v4.npz (deterministic, no network)"
	@echo "  make calibrate    Holdout split + Platt sigmoid"
	@echo "  make scan         Re-classify cached NCR tiles with clf_v4"
	@echo "  make aggregate    Build GeoJSON + OSM cross-match"
	@echo "  make verify-sheets Rebuild verification 3x3 sheets for next active-learning round"
	@echo "  make demo         Score one tile through clf_v4_calibrated and print result"
	@echo "  make hash         Print sha256 of clf_v4.joblib (smoke-test invariant)"
	@echo "  make clean        Remove generated artifacts"

all: $(GEOJSON) $(CAL_BUNDLE)
	@echo
	@echo "[make all] DONE."
	@$(MAKE) -s hash

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
hash:
	@$(PY) -c "import hashlib; print('clf_v4.joblib sha256:', hashlib.sha256(open('$(CLF)','rb').read()).hexdigest()[:16])"

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
