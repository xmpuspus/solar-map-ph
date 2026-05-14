"""Print the top-N highest-scoring tiles for a region so the next human (or
AI) can visually inspect them.

Usage:
    python scripts/dump_top_region_tiles.py --region cebu --n 10
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", required=True)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--min-score", type=float, default=0.0, help="lower bound filter")
    args = ap.parse_args()

    jsonl = REPO / "detection" / "scan" / f"{args.region}_scan_results.jsonl"
    if not jsonl.exists():
        print(f"missing: {jsonl}", file=sys.stderr)
        return 1
    rows = []
    for line in jsonl.read_text().splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("fetch_ok") and r.get("score") is not None and r["score"] >= args.min_score:
            rows.append(r)
    rows.sort(key=lambda r: -r["score"])

    tiles_dir = REPO / "detection" / "scan" / "tiles" / args.region
    print(f"region={args.region}: top {min(args.n, len(rows))} of {len(rows)} scored tiles")
    for r in rows[: args.n]:
        tile_path = tiles_dir / f"{r['tile_id']}.jpg"
        present = "OK " if tile_path.exists() else "MISS"
        print(f"  score={r['score']:.4f}  tile={r['tile_id']:30s}  {present}  {tile_path.relative_to(REPO)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
