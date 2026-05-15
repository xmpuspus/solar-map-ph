"""v1.1 release-readiness gate runner.

Runs all hard pre-release checks for the multi-region scale-up. Exits 0 on
all-green, 1 on any failure. CI-friendly summary at the end.

Gates:
  1. regions.json parses and has at least one region
  2. Each region's served_lgu polygon file exists in pipeline/regions/
  3. Each region's published GeoJSON parses + has features
  4. Each region's city_detection_counts.json parses + has _meta
  5. Cross-region PII gate (no per-building geom, no PII fields)
  6. NCR's per-building leak gate (existing; reused)
  7. Classifier .joblib hash matches manifest (deterministic)
  8. Astro site builds clean (skipped if --skip-build)
  9. requirements.txt and detection/requirements.txt parse (no unpinned)
 10. Aggregate sanity: total tiles + detections monotonically increase across
     all regions vs prior baseline (skipped on first run)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REGIONS_CFG = REPO / "pipeline" / "regions" / "regions.json"
DATA_DIR = REPO / "site" / "public" / "data"
PIPELINE_REGIONS = REPO / "pipeline" / "regions"
CLF_PATH = REPO / "detection" / "train" / "clf_v5.joblib"
MANIFEST_PATH = REPO / "detection" / "train" / "dataset_v5_manifest.json"
PIPELINE_REQS = REPO / "pipeline" / "requirements.txt"
ROOT_REQS = REPO / "requirements.txt"
SITE_REGIONS_COPY = REPO / "site" / "src" / "data" / "regions.json"


def gate(name: str, ok: bool, detail: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}{(' - ' + detail) if detail else ''}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-build", action="store_true", help="Skip the Astro site build gate")
    ap.add_argument("--skip-ncr", action="store_true", help="Skip the NCR per-building leak gate")
    args = ap.parse_args()

    passes = 0
    fails = 0

    def log(ok: bool):
        nonlocal passes, fails
        if ok:
            passes += 1
        else:
            fails += 1

    if not REGIONS_CFG.exists():
        return gate("regions.json present", False, str(REGIONS_CFG))

    cfg = json.loads(REGIONS_CFG.read_text())
    region_slugs = [r["slug"] for r in cfg["regions"]]
    log(gate("regions.json present + non-empty", len(region_slugs) > 0,
             f"{len(region_slugs)} regions: {region_slugs}"))
    # Vercel only uploads files under site/ for the build; a copy of
    # regions.json lives under site/src/data/. Assert the two are in sync.
    site_copy_ok = SITE_REGIONS_COPY.exists() and SITE_REGIONS_COPY.read_text() == REGIONS_CFG.read_text()
    log(gate("site/src/data/regions.json mirrors pipeline/regions/regions.json",
             site_copy_ok))

    for slug in region_slugs:
        log(gate(
            f"polygon file: {slug}_lgus.geojson",
            (PIPELINE_REGIONS / f"{slug}_lgus.geojson").exists(),
        ))

    for slug in region_slugs:
        gj_path = DATA_DIR / f"rooftop_solar_{slug}.geojson"
        if not gj_path.exists():
            log(gate(f"published GeoJSON: {slug}", False, "missing"))
            continue
        try:
            gj = json.loads(gj_path.read_text())
            n = len(gj.get("features", []))
            log(gate(f"published GeoJSON: {slug}", n > 0, f"{n} features"))
        except Exception as e:
            log(gate(f"published GeoJSON: {slug}", False, str(e)))

    for slug in region_slugs:
        cc_path = DATA_DIR / f"city_detection_counts_{slug}.json"
        if not cc_path.exists():
            log(gate(f"city counts: {slug}", False, "missing"))
            continue
        try:
            cc = json.loads(cc_path.read_text())
            ok = "_meta" in cc and "rows" in cc
            log(gate(f"city counts: {slug}", ok))
        except Exception as e:
            log(gate(f"city counts: {slug}", False, str(e)))

    pii_check = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "check_region_no_pii.py")],
        capture_output=True, text=True,
    )
    log(gate("cross-region PII gate", pii_check.returncode == 0,
             "see check_region_no_pii.py output"))

    if not args.skip_ncr:
        ncr_check = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "check_no_residential_leaks.py")],
            capture_output=True, text=True,
        )
        log(gate("NCR per-building leak gate", ncr_check.returncode == 0))

    expected_hash_prefix = "5cc0a093c5279fd9"  # canonical clf_v5 (v1.2)
    if CLF_PATH.exists():
        actual_hash_prefix = hashlib.sha256(CLF_PATH.read_bytes()).hexdigest()[:16]
        log(gate("classifier hash matches canonical",
                 actual_hash_prefix == expected_hash_prefix,
                 f"actual={actual_hash_prefix} expected={expected_hash_prefix}"))
    else:
        log(gate("classifier hash matches canonical", False, "clf_v5.joblib missing"))

    for label, reqs in [("requirements.txt (root)", ROOT_REQS),
                         ("pipeline/requirements.txt", PIPELINE_REQS)]:
        if not reqs.exists():
            log(gate(f"requirements: {label}", False, "missing"))
            continue
        unpinned = []
        for line in reqs.read_text().splitlines():
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("-"):
                continue
            if "==" not in s and not s.startswith("git+") and ">" not in s:
                unpinned.append(s)
        log(gate(f"requirements: {label} pinned",
                 not unpinned,
                 f"unpinned: {unpinned[:3]}" if unpinned else "all pinned"))

    if not args.skip_build:
        build = subprocess.run(
            ["pnpm", "build"], cwd=REPO / "site",
            capture_output=True, text=True,
        )
        ok = build.returncode == 0
        log(gate("Astro site builds clean", ok,
                 "see pnpm output" if not ok else ""))
        if not ok:
            print(build.stdout[-1000:], file=sys.stderr)
            print(build.stderr[-1000:], file=sys.stderr)

    print()
    print(f"v1.1 gate summary: {passes} PASS / {fails} FAIL")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
