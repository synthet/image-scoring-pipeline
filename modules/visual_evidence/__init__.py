"""Visual evidence artifacts: grids, mask RLE, schema versioning (#423)."""

from modules.visual_evidence.schema import (
    EVIDENCE_EXTRACTOR_VERSION,
    EVIDENCE_SCHEMA_VERSION,
    EvidenceGrid,
    EvidenceMaskRle,
    EvidencePayload,
    EvidenceSeparation,
)
from modules.visual_evidence.service import build_evidence_for_image

__all__ = [
    "EVIDENCE_EXTRACTOR_VERSION",
    "EVIDENCE_SCHEMA_VERSION",
    "EvidenceGrid",
    "EvidenceMaskRle",
    "EvidencePayload",
    "EvidenceSeparation",
    "build_evidence_for_image",
]
