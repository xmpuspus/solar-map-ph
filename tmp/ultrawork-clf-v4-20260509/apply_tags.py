"""Apply active-learning labels for clf_v4 round.

Decisions made by reviewing detection/verify/sheets/page_*.png at 480x480 thumbnail
resolution. Conservative AMBIGUOUS for unclear cases (likely painted metal roofs,
small arrays not visible at thumbnail scale, mixed-urban tiles where solar location
can't be pinpointed). Single FALSE for #108: ribbed metal roof with vertical-only
stripe pattern, no 2D panel grid.
"""

import json
from pathlib import Path

TAGS = Path("/Users/xavier/Desktop/ghost-watts/detection/verify/tags.json")

# idx -> label. Ambiguous = excluded from training. False positives become negatives.
LABELS = {
    # Page 00 (idx 0-8) — top scores 0.979-0.990
    0: "true", 1: "ambiguous", 2: "true", 3: "true", 4: "true",
    5: "true", 6: "true", 7: "true", 8: "true",
    # Page 01 (9-17)
    9: "true", 10: "true", 11: "true", 12: "true", 13: "true",
    14: "true", 15: "true", 16: "ambiguous", 17: "true",
    # Page 02 (18-26)
    18: "ambiguous", 19: "true", 20: "true", 21: "true", 22: "ambiguous",
    23: "true", 24: "true", 25: "true", 26: "true",
    # Page 03 (27-35)
    27: "true", 28: "true", 29: "true", 30: "true", 31: "true",
    32: "true", 33: "true", 34: "true", 35: "true",
    # Page 04 (36-44)
    36: "true", 37: "true", 38: "true", 39: "true", 40: "true",
    41: "ambiguous", 42: "true", 43: "ambiguous", 44: "ambiguous",
    # Page 05 (45-53)
    45: "true", 46: "true", 47: "true", 48: "true", 49: "true",
    50: "true", 51: "ambiguous", 52: "ambiguous", 53: "true",
    # Page 06 (54-62)
    54: "true", 55: "true", 56: "true", 57: "true", 58: "true",
    59: "true", 60: "true", 61: "true", 62: "true",
    # Page 07 (63-71)
    63: "ambiguous", 64: "true", 65: "true", 66: "true", 67: "ambiguous",
    68: "true", 69: "true", 70: "ambiguous", 71: "true",
    # Page 08 (72-80)
    72: "true", 73: "true", 74: "true", 75: "true", 76: "ambiguous",
    77: "true", 78: "ambiguous", 79: "true", 80: "ambiguous",
    # Page 09 (81-89)
    81: "true", 82: "true", 83: "true", 84: "ambiguous", 85: "true",
    86: "true", 87: "ambiguous", 88: "ambiguous", 89: "true",
    # Page 10 (90-98)
    90: "true", 91: "true", 92: "ambiguous", 93: "ambiguous", 94: "true",
    95: "ambiguous", 96: "ambiguous", 97: "ambiguous", 98: "ambiguous",
    # Page 11 (99-107)
    99: "true", 100: "ambiguous", 101: "ambiguous", 102: "true", 103: "true",
    104: "ambiguous", 105: "ambiguous", 106: "true", 107: "ambiguous",
    # Page 12 (108-113, only 6)
    108: "false", 109: "ambiguous", 110: "ambiguous", 111: "true",
    112: "ambiguous", 113: "true",
}

assert len(LABELS) == 114, f"Expected 114 labels, got {len(LABELS)}"

t_count = sum(1 for v in LABELS.values() if v == "true")
f_count = sum(1 for v in LABELS.values() if v == "false")
a_count = sum(1 for v in LABELS.values() if v == "ambiguous")
print(f"Labels: {t_count} true, {f_count} false, {a_count} ambiguous (total {len(LABELS)})")

rows = json.loads(TAGS.read_text())
assert len(rows) == 114, f"Expected 114 rows in tags.json, got {len(rows)}"

for r in rows:
    idx = r["idx"]
    if idx not in LABELS:
        raise KeyError(f"idx {idx} not in LABELS")
    r["label"] = LABELS[idx]

TAGS.write_text(json.dumps(rows, indent=2))
print(f"Wrote {len(rows)} rows to {TAGS}")

# Sanity recount from disk
recount = json.loads(TAGS.read_text())
disk_t = sum(1 for r in recount if r.get("label") == "true")
disk_f = sum(1 for r in recount if r.get("label") == "false")
disk_a = sum(1 for r in recount if r.get("label") == "ambiguous")
disk_n = sum(1 for r in recount if r.get("label") is None)
print(f"Recount from disk: true={disk_t} false={disk_f} ambiguous={disk_a} null={disk_n}")
