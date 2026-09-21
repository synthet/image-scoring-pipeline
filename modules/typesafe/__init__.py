"""TypeSafe (Jev / System One) integration — experimental, disabled by default.

Text-only typed-decision layer over evidence the vision pipeline produces. See
``modules/typesafe/client.py`` for the entry point and ``rubrics.py`` for the
versioned question registry.
"""

from modules.typesafe.client import TypeSafeClient
from modules.typesafe.normalize import Judgment, evidence_hash, normalize
from modules.typesafe.rubrics import REGISTRY, Rubric, get_rubric

__all__ = [
    "REGISTRY",
    "Judgment",
    "Rubric",
    "TypeSafeClient",
    "evidence_hash",
    "get_rubric",
    "normalize",
]
