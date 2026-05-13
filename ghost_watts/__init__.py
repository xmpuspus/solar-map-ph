"""ghost-watts: open-source rooftop solar detection from satellite imagery.

Public API surface (stable):

    from ghost_watts import __version__
    from ghost_watts import score_features            # CLIP-features -> calibrated probability
    from ghost_watts import load_classifier_bundle    # joblib.load wrapper with hash check
    from ghost_watts import grid_centers              # tile-grid generator at arbitrary latitude

Everything else is internal and may change between versions.
"""

from __future__ import annotations

__version__ = "1.0.0"

from .api import (
    grid_centers,
    load_classifier_bundle,
    score_features,
)

__all__ = [
    "__version__",
    "grid_centers",
    "load_classifier_bundle",
    "score_features",
]
