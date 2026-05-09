"""Round 2: re-tag after high-resolution inspection of every AMBIGUOUS and the 1 FALSE.

Findings: thumbnail review at 480x480 missed many real solar arrays. High-res
inspection of all 32 originally-ambiguous tiles found 29 were clearly solar,
1 (#107) was blue painted metal, and 2 (#070, #080) remain genuinely ambiguous.
The single FALSE I called (#108) at high res turned out to be a sawtooth roof
with PV panels on south-facing slopes — corrected to TRUE.

Net: 111 TRUE, 1 FALSE, 2 AMBIGUOUS.
"""

import json
from pathlib import Path

TAGS = Path("/Users/xavier/Desktop/ghost-watts/detection/verify/tags.json")

# idx -> label, after high-res inspection of every uncertain case.
LABELS = {
    # Page 00 (idx 0-8) — top scores 0.979-0.990
    0: "true", 1: "true", 2: "true", 3: "true", 4: "true",   # #1: green roof had clear panels at high-res
    5: "true", 6: "true", 7: "true", 8: "true",
    # Page 01 (9-17)
    9: "true", 10: "true", 11: "true", 12: "true", 13: "true",
    14: "true", 15: "true", 16: "true", 17: "true",   # #16: clear PV on left building
    # Page 02 (18-26)
    18: "true", 19: "true", 20: "true", 21: "true", 22: "true",   # #18: SM mall mass solar; #22: dark PV center
    23: "true", 24: "true", 25: "true", 26: "true",
    # Page 03 (27-35)
    27: "true", 28: "true", 29: "true", 30: "true", 31: "true",
    32: "true", 33: "true", 34: "true", 35: "true",
    # Page 04 (36-44)
    36: "true", 37: "true", 38: "true", 39: "true", 40: "true",
    41: "true", 42: "true", 43: "true", 44: "true",   # all confirmed at high-res
    # Page 05 (45-53)
    45: "true", 46: "true", 47: "true", 48: "true", 49: "true",
    50: "true", 51: "true", 52: "true", 53: "true",   # #51 sawtooth solar; #52 massive solar farm
    # Page 06 (54-62)
    54: "true", 55: "true", 56: "true", 57: "true", 58: "true",
    59: "true", 60: "true", 61: "true", 62: "true",
    # Page 07 (63-71)
    63: "true", 64: "true", 65: "true", 66: "true", 67: "true",   # #63: PV on right; #67: PV multiple sections
    68: "true", 69: "true", 70: "ambiguous", 71: "true",   # #70: container-sized features, OSM 1814m
    # Page 08 (72-80)
    72: "true", 73: "true", 74: "true", 75: "true", 76: "true",   # #76: PV on right buildings
    77: "true", 78: "true", 79: "true", 80: "ambiguous",   # #78: PV; #80: pool dominant, unclear
    # Page 09 (81-89)
    81: "true", 82: "true", 83: "true", 84: "true", 85: "true",   # #84: clear PV
    86: "true", 87: "true", 88: "true", 89: "true",   # #87: SM mass solar; #88: clear PV
    # Page 10 (90-98)
    90: "true", 91: "true", 92: "true", 93: "true", 94: "true",   # #92: clear PV; #93: huge solar
    95: "true", 96: "true", 97: "true", 98: "true",   # all confirmed at high-res
    # Page 11 (99-107)
    99: "true", 100: "true", 101: "true", 102: "true", 103: "true",
    104: "true", 105: "true", 106: "true", 107: "false",   # #107: blue painted metal, no PV structure
    # Page 12 (108-113)
    108: "true", 109: "true", 110: "true", 111: "true",   # #108: sawtooth solar (was wrongly FALSE)
    112: "true", 113: "true",
}

assert len(LABELS) == 114

t = sum(1 for v in LABELS.values() if v == "true")
f = sum(1 for v in LABELS.values() if v == "false")
a = sum(1 for v in LABELS.values() if v == "ambiguous")
print(f"Round 2 labels: {t} true, {f} false, {a} ambiguous")

rows = json.loads(TAGS.read_text())
for r in rows:
    r["label"] = LABELS[r["idx"]]
TAGS.write_text(json.dumps(rows, indent=2))
print(f"Wrote {len(rows)} rows")
