"""Injectable model/engine abstractions for tests and alternate backends."""

from modules.engines.base import (
    IScoringEngine,
    ILiqeScorer,
    ITaggingEngine,
    IClusteringEngine,
)
from modules.engines.mock import (
    MockScoringEngine,
    MockLiqeScorer,
    MockTaggingEngine,
    MockClusteringEngine,
)

__all__ = [
    "IScoringEngine",
    "ILiqeScorer",
    "ITaggingEngine",
    "IClusteringEngine",
    "MockScoringEngine",
    "MockLiqeScorer",
    "MockTaggingEngine",
    "MockClusteringEngine",
]
