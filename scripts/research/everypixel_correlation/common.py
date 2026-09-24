"""Shared paths and constants for Everypixel correlation research."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REPORTS_DIR = PROJECT_ROOT / "reports" / "everypixel-correlation"
DEFAULT_MANIFEST = REPORTS_DIR / "manifest.json"
DEFAULT_UGC_JSONL = REPORTS_DIR / "everypixel_ugc.jsonl"

CORE_MODEL_NAMES = ("liqe", "spaq", "ava", "topiq", "arniqa")

COMPOSITE_COLUMNS = ("score_general", "score_technical", "score_aesthetic")

EVERYPIXEL_TARGETS = ("ugc_score", "ugc_class")
