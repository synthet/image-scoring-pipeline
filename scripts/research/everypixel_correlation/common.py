"""Shared paths and constants for Everypixel correlation research."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SKILLS_REPO_NAME = "image-scoring-skills"
RESEARCH_SUBDIR = Path("research") / "everypixel-correlation"


def resolve_reports_dir() -> Path:
    """Canonical artifact root (private skills repo when cloned as sibling).

    Override with ``EVERYPIXEL_CORRELATION_DIR``. Otherwise use
    ``IMAGE_SCORING_SKILLS_REPO/research/everypixel-correlation`` when that repo
    exists (default sibling ``../image-scoring-skills``), else backend
    ``reports/everypixel-correlation/`` (gitignored).
    """
    override = os.environ.get("EVERYPIXEL_CORRELATION_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    skills_root = os.environ.get("IMAGE_SCORING_SKILLS_REPO", "").strip()
    if skills_root:
        base = Path(skills_root).expanduser().resolve()
    else:
        base = PROJECT_ROOT.parent / SKILLS_REPO_NAME

    skills_reports = base / RESEARCH_SUBDIR
    if base.is_dir():
        return skills_reports

    return PROJECT_ROOT / "reports" / "everypixel-correlation"


REPORTS_DIR = resolve_reports_dir()
DEFAULT_MANIFEST = REPORTS_DIR / "manifest.json"
DEFAULT_UGC_JSONL = REPORTS_DIR / "everypixel_ugc.jsonl"

CORE_MODEL_NAMES = ("liqe", "spaq", "ava", "topiq", "arniqa")

COMPOSITE_COLUMNS = ("score_general", "score_technical", "score_aesthetic")

EVERYPIXEL_TARGETS = ("ugc_score", "ugc_class")
