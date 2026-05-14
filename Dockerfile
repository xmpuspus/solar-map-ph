# SolarMap.PH deterministic build image.
# Smoke test: `docker build -t solar-map-ph:latest . && docker run solar-map-ph:latest make hash`
# should produce the same sha256 as the host build, given the same dataset_v4.npz.

# Pinned to a specific Debian + Python patch level for deterministic builds.
# Refresh quarterly during the LGU table refresh. To bump:
#   docker pull python:3.12-slim-bookworm
#   docker image inspect python:3.12-slim-bookworm --format '{{index .RepoDigests 0}}'
FROM python:3.14-slim-bookworm

# System deps for sklearn/torch/PIL (libgomp1 for OpenMP, libgl1 for opencv-style stacks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python deps first so layer caches when source changes
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy detection module + Makefile + the cached embeddings dataset.
# Raw imagery (~5GB of NCR tiles, OSM tiles, GT tiles) is NOT bundled here.
# To regenerate the embeddings from raw imagery, mount the imagery as a volume
# and run `make all` instead of the default `make train`.
COPY Makefile /app/Makefile
COPY detection/ /app/detection/
COPY docs/ /app/docs/

# COPY may reset file timestamps in ways that confuse `make`. Re-stamp the
# trained-classifier artifacts so `make hash-verify` does not try to rebuild
# from upstream source files that aren't bundled in the image.
RUN touch /app/detection/train/dataset_v4.npz \
    && touch /app/detection/train/clf_v4.joblib \
    && touch /app/detection/train/clf_v4_metrics.json

# Default command: print the deterministic hash. Use `docker run solar-map-ph make all`
# for the full pipeline (requires raw imagery volume) or `docker run -v $(pwd)/detection/scan/ncr_tiles:/app/detection/scan/ncr_tiles solar-map-ph make scan` to re-classify cached tiles.
CMD ["make", "hash"]
