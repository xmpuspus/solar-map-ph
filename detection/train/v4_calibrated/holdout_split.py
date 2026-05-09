"""Phase-2 honest holdout split for clf_v4 calibration.

Splits 20% of OSM positive sources and 20% of negative sources into a never-trained
holdout used only for Platt scaling and honest precision reporting. The split is
deterministic via fixed seed so subsequent retrain runs are reproducible.

Holdout strategy:
  - 20% of `osm_NNNN` positive sources -> holdout pos
  - 20% of `gt_*` + `rneg_*` negative sources -> holdout neg
  - All case_* / v3promo_* / v3conf_* / v3fp_* stay in TRAIN (they are signal-rich
    sources we want to keep in training; v3conf_* are user-confirmed positives,
    v3fp_* is the user-confirmed negative)

Why exclude active-learning tiles from the holdout: those tiles came from the
high-conf scan of NCR. Including them in the calibration holdout would let the
classifier "remember" the labels it derived from itself. The honest holdout
should be the OSM ground-truth subset that the model never trained on.

Outputs:
  detection/train/v4_calibrated/holdout_split.json
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
DATASET = ROOT / "detection" / "train" / "dataset_v4.npz"
OUT = ROOT / "detection" / "train" / "v4_calibrated" / "holdout_split.json"
SEED = 4242  # Phase 2 calibration seed; never reuse

HOLDOUT_FRAC = 0.20


def main() -> int:
    d = np.load(DATASET, allow_pickle=False)
    sources = sorted(set(d["src"].tolist()))

    osm_pos = sorted(s for s in sources if s.startswith("osm_"))
    gt_neg = sorted(s for s in sources if s.startswith("gt_"))
    rneg = sorted(s for s in sources if s.startswith("rneg_"))

    rng = random.Random(SEED)
    rng.shuffle(osm_pos)
    rng.shuffle(gt_neg)
    rng.shuffle(rneg)

    n_pos_holdout = int(round(len(osm_pos) * HOLDOUT_FRAC))
    n_gt_holdout = int(round(len(gt_neg) * HOLDOUT_FRAC))
    n_rneg_holdout = int(round(len(rneg) * HOLDOUT_FRAC))

    holdout_pos = sorted(osm_pos[:n_pos_holdout])
    holdout_neg = sorted(gt_neg[:n_gt_holdout] + rneg[:n_rneg_holdout])
    train_pos_osm = sorted(osm_pos[n_pos_holdout:])
    train_neg_from_pool = sorted(gt_neg[n_gt_holdout:] + rneg[n_rneg_holdout:])

    # All non-OSM sources stay in train (active-learning + case studies + promoted).
    other_train_pos = sorted([s for s in sources if s.startswith(("case_", "v3promo_", "v3conf_"))])
    other_train_neg = sorted([s for s in sources if s.startswith("v3fp_")])

    split = {
        "seed": SEED,
        "holdout_frac_osm": HOLDOUT_FRAC,
        "holdout_pos_sources": holdout_pos,
        "holdout_neg_sources": holdout_neg,
        "train_pos_sources": sorted(train_pos_osm + other_train_pos),
        "train_neg_sources": sorted(train_neg_from_pool + other_train_neg),
        "n_holdout_pos": len(holdout_pos),
        "n_holdout_neg": len(holdout_neg),
        "n_train_pos": len(train_pos_osm) + len(other_train_pos),
        "n_train_neg": len(train_neg_from_pool) + len(other_train_neg),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(split, indent=2))
    print(f"holdout pos: {split['n_holdout_pos']} / train pos: {split['n_train_pos']}")
    print(f"holdout neg: {split['n_holdout_neg']} / train neg: {split['n_train_neg']}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
