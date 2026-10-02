"""Pydantic-shaped evidence payload (clean-room; not vendor JSON layout)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# Bump when response fields or semantics change.
EVIDENCE_SCHEMA_VERSION = 1
# Bump when grid cell math, noise estimator, or mask downsample changes.
EVIDENCE_EXTRACTOR_VERSION = "visual_evidence_extractors_v1"

CriterionCode = Literal["focus", "eye", "exposure", "composition", "noise", "context"]
BandCode = str
LimitationCode = Literal[
    "no_region",
    "mask_low_confidence",
    "keypoints_heuristic",
    "small_subject_second_pass",
]


class EvidenceGrid(BaseModel):
    cells_x: int = Field(ge=1)
    cells_y: int = Field(ge=1)
    cell_size_px: int = Field(ge=1, description="Starting point; re-fit on corpus.")
    values: list[float]
    values_normalized: list[float] | None = None


class EvidenceMaskRle(BaseModel):
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    counts: list[int]
    max_dim: int = Field(default=256, description="Downsample cap starting point.")


class EvidenceSeparation(BaseModel):
    subject_sharpness_mean: float | None = None
    background_sharpness_mean: float | None = None
    ratio: float | None = None
    noise_sigma_mean: float | None = None
    mask_label: str = "subject_mask"


class CriterionBand(BaseModel):
    criterion: CriterionCode
    band: BandCode
    sub_score: int | None = Field(default=None, ge=0, le=100)
    confidence_evidence: float | None = Field(default=None, ge=0, le=1)


class EvidenceDisplayGates(BaseModel):
    region: bool = False
    mask: bool = False
    keypoints: bool = False
    focus_grid: bool = False
    noise_grid: bool = False


class EvidencePayload(BaseModel):
    evidence_schema_version: int = EVIDENCE_SCHEMA_VERSION
    extractor_version: str = EVIDENCE_EXTRACTOR_VERSION
    image_id: int
    display_width: int
    display_height: int
    rendition_hash: str | None = None
    gates: EvidenceDisplayGates
    limitations: list[LimitationCode] = Field(default_factory=list)
    criteria: list[CriterionBand] = Field(default_factory=list)
    focus_grid: EvidenceGrid | None = None
    noise_grid: EvidenceGrid | None = None
    mask_rle: EvidenceMaskRle | None = None
    separation: EvidenceSeparation | None = None
    region_bbox: dict[str, Any] | None = None
    keypoints: list[dict[str, Any]] | None = None
    burst: dict[str, Any] | None = Field(
        default=None,
        description="Optional best_frame / nearly_tied hooks for explainability §1.",
    )
