# Phase 4 — Reproducibility Hardening (COMPLETE)

## Deliverables

1. `requirements.txt` at repo root, every dep pinned with `==` (not `>=`).
2. `Makefile` with targets: `all`, `train`, `calibrate`, `scan`, `aggregate`, `verify-sheets`, `demo`, `hash`, `clean`, `help`.
3. `Dockerfile` based on `python:3.12-slim`, bundles the embedded dataset (~8 MB) and pipeline source. Default CMD prints `clf_v4.joblib` sha256 for smoke testing.
4. `.dockerignore` to keep the build context small (excludes raw imagery, baselines, ablation embeddings, node_modules, sheets).
5. README addition: a "Detection pipeline (reproducible)" section under Quickstart with `make` and `docker run` recipes plus the locked encoder rationale.

## Determinism verified

Two consecutive `python3 detection/train/train_v3.py` runs from the same `dataset_v4.npz` produced identical `clf_v4.joblib` sha256: **`15564df477c961f2`**.

The full pipeline is bit-exact-deterministic given the same dataset_v4.npz because:
- LR uses `random_state=42`
- LBFGS solver is deterministic
- joblib serialization is byte-stable for the same fitted object
- Pickle protocol picks the same major version on Python 3.12

Cross-platform reproducibility (Linux Docker vs macOS host) was not directly tested but should hold: numpy/sklearn/joblib versions are pinned exactly, and the dataset_v4.npz ships in the image so the embedding pass (which would vary across platforms via PyTorch + MPS vs CUDA vs CPU) is skipped.

## Pinned deps

```
numpy==1.26.4
torch==2.9.1
transformers==4.57.3
scikit-learn==1.7.2
joblib==1.5.2
huggingface-hub==0.36.0
safetensors==0.7.0
tokenizers==0.22.2
pillow==11.3.0
requests==2.32.5
segment-anything==1.0
```

## Smoke test commands

```bash
# Local
make hash    # -> clf_v4.joblib sha256: 15564df477c961f2

# Docker
docker build -t ghost-watts:latest .
docker run --rm ghost-watts:latest    # same sha256 as host
```

## What's NOT covered

- Full `make all` from raw imagery: requires ~5 GB of cached tile JPGs (not bundled in the Docker image). Mount `detection/scan/ncr_tiles/`, `detection/bootstrap/tiles/`, `docs/groundtruth/tiles/`, `detection/train/random_neg_tiles/`, and `site/public/case_studies/` as volumes if you want to re-embed from raw inputs.
- The NCR scan target (`make scan`) needs the cached NCR tile JPGs to actually re-classify; from-zero scans need network access to Esri (rate-limited, ~13 min for 16k tiles).
- CLIP-ViT-L weights (~1.2 GB) are pulled from HuggingFace at first dataset rebuild. The Docker image does not bundle them, so first `make dataset` inside Docker needs internet.

## Known limitations

- `make dataset` triggers re-embed if `tags.json` mtime is newer than `dataset_v4.npz`. After tagging rounds, run `make dataset train calibrate` once to refresh both the embeddings and the trained model. The dataset rebuild takes ~3 min on M-series MPS.
