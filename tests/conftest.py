"""Shared pytest fixtures and path setup.

Adds the repo root to sys.path so tests can `import solar_map_ph` and reach
into `detection/` and `pipeline/` directly without requiring an editable
install.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
