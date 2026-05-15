"""Step 2a of v1.2: harvest the v1.1 spot-check verdicts from the per-region
findings markdown into structured label rows.

The 32 verdicts in docs/screenshots/qa-2026-05/region-spot-check/*_findings.md
are the seed for the step-3 per-region holdouts and the step-4 clf_v5
hard-negative set. They are currently stranded as prose; this turns them into
detection/train/region_labels.jsonl.

The findings tables vary in column layout across regions:
  cebu / legazpi   : # | Score | Tile (lat_lon) | Verdict
  davao/iloilo/cdo : # | Score | Tier | Tile (lat_lon) | Verdict
  calabarzon       : # | Score | Tier | Tile (lat_lon) | Verdict
  bacolod          : # | Score | Tier | Tile (lat_lon) | LGU | Verdict
so the parser keys off the header cells, not column position.

Verdict text -> label:
  "GROUND-MOUNT"                         -> ground_mount  (hard negative)
  "FALSE POSITIVE" / blue-roof-not-real  -> blue_roof_fp  (hard negative)
  "REAL rooftop solar" / "Confirmed"     -> rooftop       (positive)
  anything else                          -> unknown       (flagged, not guessed)

Run:
    python detection/train/harvest_spotcheck_labels.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FINDINGS_DIR = ROOT / "docs" / "screenshots" / "qa-2026-05" / "region-spot-check"
OUT = ROOT / "detection" / "train" / "region_labels.jsonl"

TILE_RE = re.compile(r"(-?\d+\.\d+)_(-?\d+\.\d+)")


def classify(verdict: str) -> str:
    v = verdict.lower()
    if "ground-mount" in v or "ground mount" in v:
        return "ground_mount"
    if "false positive" in v:
        return "blue_roof_fp"
    if "real rooftop solar" in v or "confirmed" in v:
        return "rooftop"
    # A "blue ... roof" that is explicitly not real solar is the blue-roof FP
    # class even when the words "false positive" are absent.
    if "blue" in v and "roof" in v and "real rooftop" not in v:
        return "blue_roof_fp"
    return "unknown"


def split_row(line: str) -> list[str]:
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return cells


def parse_findings(path: Path) -> list[dict]:
    region = path.stem.replace("_findings", "")
    lines = path.read_text().splitlines()
    rows: list[dict] = []
    header: list[str] | None = None
    col: dict[str, int] = {}
    for ln in lines:
        if not ln.strip().startswith("|"):
            header = None
            continue
        cells = split_row(ln)
        # Header detection: a row whose cells include "Score" and a tile column.
        joined = " ".join(c.lower() for c in cells)
        if header is None:
            if "score" in joined and ("tile" in joined or "lat_lon" in joined):
                header = cells
                col = {}
                for i, c in enumerate(cells):
                    cl = c.lower()
                    if cl.startswith("score"):
                        col["score"] = i
                    elif cl.startswith("tile"):
                        col["tile"] = i
                    elif cl.startswith("verdict"):
                        col["verdict"] = i
                    elif cl.startswith("tier"):
                        col["tier"] = i
            continue
        # Separator row like |---|---|
        if set("".join(cells)) <= {"-", ":", " "}:
            continue
        if "score" not in col or "tile" not in col or "verdict" not in col:
            continue
        if max(col["score"], col["tile"], col["verdict"]) >= len(cells):
            continue
        tile_cell = cells[col["tile"]]
        m = TILE_RE.search(tile_cell)
        if not m:
            continue
        lat, lon = float(m.group(1)), float(m.group(2))
        tile_id = f"{lat:.5f}_{lon:.5f}"
        try:
            score = float(re.search(r"-?\d+\.\d+", cells[col["score"]]).group(0))
        except (AttributeError, ValueError):
            score = None
        verdict = cells[col["verdict"]]
        tier = cells[col["tier"]].lower() if "tier" in col and col["tier"] < len(cells) else None
        label = classify(verdict)
        rows.append(
            {
                "region": region,
                "tile_id": tile_id,
                "lat": lat,
                "lon": lon,
                "score": score,
                "tier": tier,
                "label": label,
                "source": "spotcheck",
                "findings_file": str(path.relative_to(ROOT)),
                "verdict_text": verdict,
            }
        )
    return rows


def main() -> int:
    if not FINDINGS_DIR.exists():
        print(f"[harvest] missing {FINDINGS_DIR}", file=sys.stderr)
        return 1
    all_rows: list[dict] = []
    for path in sorted(FINDINGS_DIR.glob("*_findings.md")):
        rows = parse_findings(path)
        print(f"[harvest] {path.name}: {len(rows)} verdicts")
        all_rows.extend(rows)

    OUT.write_text("\n".join(json.dumps(r) for r in all_rows) + "\n")

    by_label: dict[str, int] = {}
    by_region: dict[str, int] = {}
    unknowns = []
    for r in all_rows:
        by_label[r["label"]] = by_label.get(r["label"], 0) + 1
        by_region[r["region"]] = by_region.get(r["region"], 0) + 1
        if r["label"] == "unknown":
            unknowns.append((r["region"], r["tile_id"], r["verdict_text"][:60]))

    print(f"\n[harvest] total verdicts: {len(all_rows)}")
    print(f"[harvest] by label: {by_label}")
    print(f"[harvest] by region: {by_region}")
    if unknowns:
        print(f"[harvest] WARNING {len(unknowns)} unknown verdicts (not guessed):")
        for u in unknowns:
            print(f"  {u}")
    print(f"[harvest] wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
