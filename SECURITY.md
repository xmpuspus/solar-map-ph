# Security Policy

## Reporting a vulnerability

Open a private security advisory via the GitHub Security tab:
https://github.com/xmpuspus/solar-map-ph/security/advisories/new

Do not open a public issue. Acknowledged within 5 working days.

## In scope

- Code execution via crafted inputs to any script in `detection/` or `pipeline/`.
- Cross-site scripting on `solar-map-ph.vercel.app` or any deployed preview.
- CSP bypass on the homeowner roof-lookup tool.
- Path traversal in the tile-cache lookup paths.
- Supply-chain issues against the pinned dependencies in `requirements.txt` and `pipeline/requirements.txt`.

## Out of scope

- Vulnerabilities in third-party services we call (Photon, Overpass, Nominatim, Esri World Imagery, PVGIS, Earth Engine). Report to the upstream operator.
- Social engineering, phishing, physical attacks.

## Known-safe-by-design surfaces

- The homeowner tool runs entirely client-side. No server keeps a log of looked-up addresses.
- The Earth Engine pipeline runs locally with a service-account key. The key never leaves your machine, never enters Vercel, never enters git history. `.gitignore` blocks the common naming patterns; `.dockerignore` blocks the same.

## joblib / pickle deserialization

`detection/scan/ncr_scan.py`, `luzon_scan.py`, and `sam_panel_segments.py` accept a `--clf` argument that is passed directly to `joblib.load`. `joblib.load` is built on Python's pickle module, which executes arbitrary code during deserialization.

**Only run `joblib.load` against classifier files you trust.** The shipped `detection/train/clf_v4.joblib` is verifiable via `make hash-verify` (sha256 prefix `56900722a8427be4`). If you fork the repo and someone sends you a classifier file, verify its sha256 against a known-good source before invoking any `make` target that loads it.

The published model is also released on HuggingFace as `xmpuspus/solar-map-ph-clf-v4`; the HF release uses signed model cards with the same hash for cross-verification.

## Data publication boundaries

The published per-building solar dataset suppresses all residential roofs (buildings tagged `house`, `apartments`, `residential`, etc.) before publication. Only commercial, industrial, and public-purpose roofs are released at sub-building resolution. The residential count is aggregated into `site/public/data/residential_solar_aggregate.json` with no geometry and no addresses.

If you observe a feature in the published dataset that looks like it identifies a private residence, open an advisory immediately.
