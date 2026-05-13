#!/usr/bin/env python3
"""Publish the clf_v4 calibrated bundle + dataset to HuggingFace Hub.

Run once per public release. Requires:

    pip install huggingface-hub
    huggingface-cli login

Usage:

    python scripts/publish_to_huggingface.py --repo xmpuspus/ghost-watts-clf-v4

The repo on HF gets four files plus the MODEL_CARD.md:
    clf_v4.joblib
    clf_v4_calibrated.joblib
    clf_v4_calibration.json
    dataset_v4.npz

After uploading, the assets are available via:

    from huggingface_hub import hf_hub_download
    path = hf_hub_download("xmpuspus/ghost-watts-clf-v4", "clf_v4.joblib")
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = [
    ROOT / "detection" / "train" / "clf_v4.joblib",
    ROOT / "detection" / "train" / "clf_v4_metrics.json",
    ROOT / "detection" / "train" / "dataset_v4.npz",
    ROOT / "detection" / "train" / "v4_calibrated" / "clf_v4_calibrated.joblib",
    ROOT / "detection" / "train" / "v4_calibrated" / "clf_v4_calibration.json",
    ROOT / "MODEL_CARD.md",
]
EXPECTED_CLF_HASH = "56900722a8427be4"


def verify_hashes() -> None:
    clf = ROOT / "detection" / "train" / "clf_v4.joblib"
    digest = hashlib.sha256(clf.read_bytes()).hexdigest()[:16]
    if digest != EXPECTED_CLF_HASH:
        sys.exit(
            f"refusing to publish: clf_v4.joblib hash is {digest}, expected {EXPECTED_CLF_HASH}. "
            f"Run `make hash-verify` to diagnose."
        )
    print(f"[publish] hash OK: {digest}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="HuggingFace repo id, e.g. xmpuspus/ghost-watts-clf-v4")
    ap.add_argument("--private", action="store_true", help="Create the repo private (default: public)")
    args = ap.parse_args()

    verify_hashes()
    for art in ARTIFACTS:
        if not art.exists():
            sys.exit(f"missing artifact: {art.relative_to(ROOT)}")

    try:
        from huggingface_hub import HfApi
    except ImportError:
        sys.exit("pip install huggingface-hub first, then `huggingface-cli login`")

    api = HfApi()
    api.create_repo(repo_id=args.repo, repo_type="model", exist_ok=True, private=args.private)
    for art in ARTIFACTS:
        print(f"[publish] uploading {art.relative_to(ROOT)} -> {args.repo}")
        api.upload_file(
            path_or_fileobj=str(art),
            path_in_repo=art.name,
            repo_id=args.repo,
            repo_type="model",
        )

    print(f"[publish] done. View at https://huggingface.co/{args.repo}")
    print("[publish] downstream consumers can now run:")
    print(f"  from huggingface_hub import hf_hub_download")
    print(f"  hf_hub_download('{args.repo}', 'clf_v4.joblib')")
    return 0


if __name__ == "__main__":
    sys.exit(main())
