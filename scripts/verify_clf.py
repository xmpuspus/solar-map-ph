"""Verify a classifier joblib against the canonical SolarMap.PH sha256.

Wraps `make hash-verify`. Use this before invoking any `joblib.load`-based scan
(detection/scan/ncr_scan.py, luzon_scan.py, sam_panel_segments.py) on a
classifier file you received from a third party. `joblib.load` is built on
pickle and executes arbitrary code during deserialization.

Usage:
    python scripts/verify_clf.py detection/train/clf_v4.joblib
    python scripts/verify_clf.py path/to/some_other_clf.joblib --expect 56900722a8427be4

Exit code 0 = hash matches, 1 = mismatch or file missing.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

DEFAULT_EXPECTED_PREFIX = "5cc0a093c5279fd9"  # canonical clf_v5 (v1.2)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n", maxsplit=1)[0])
    p.add_argument("path", type=Path, help="path to a classifier .joblib file")
    p.add_argument(
        "--expect",
        default=DEFAULT_EXPECTED_PREFIX,
        help=f"sha256 prefix to match (default: {DEFAULT_EXPECTED_PREFIX}, canonical clf_v4)",
    )
    args = p.parse_args(argv)

    if not args.path.exists():
        print(f"[verify_clf] FAIL: {args.path} not found", file=sys.stderr)
        return 1

    digest = sha256_file(args.path)
    short = digest[: len(args.expect)]

    if short.lower() != args.expect.lower():
        print(
            f"[verify_clf] FAIL: hash mismatch for {args.path}",
            file=sys.stderr,
        )
        print(f"  expected prefix: {args.expect}", file=sys.stderr)
        print(f"  observed prefix: {short}", file=sys.stderr)
        print(f"  full sha256:     {digest}", file=sys.stderr)
        print(
            "  DO NOT run joblib.load against this file. Pickle deserialization executes arbitrary code.",
            file=sys.stderr,
        )
        return 1

    print(f"[verify_clf] OK: {args.path}")
    print(f"  sha256 prefix:   {short} (matches {args.expect})")
    print(f"  full sha256:     {digest}")
    print("  Safe to invoke joblib.load on this file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
