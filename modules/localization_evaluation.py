"""Pure localization candidate evaluation; results never authorize publication.

Evaluating the frozen #694 rule does not establish qualification. An accepted
candidate is only a proposed geometry/species input, subject to separate approval,
reservations and application.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
import math
from typing import Any, Literal


R2_RULE_ID = "bird-694-promotion-rule/1"
R2_RULE_SHA256 = "541b17bed8f287482cb485cfb58fae3e144106c1e82b077fa3c5787e588d735a"


@dataclass(frozen=True)
class ArtifactScope:
    """Exact producer combination to evaluate, not a production approval."""

    detector_version: str
    detector_config_hash: str
    rendition_version: str


@dataclass(frozen=True)
class PolicyEvaluation:
    status: Literal["accept", "reject", "abstain", "invalid"]
    reason: str
    region_id: int | None = None
    area_fraction: float | None = None
    band: Literal["small", "medium", "large"] | None = None
    geometry_eligible: bool = False
    species_eligible: bool = False


def _positive_id(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _unit_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float)) and not isinstance(value, bool)
        and 0 <= value <= 1 and math.isfinite(value)
    )


def evaluate_r2(
    run: Mapping[str, Any],
    regions: Sequence[Mapping[str, Any]],
    *,
    bird_tagged: bool,
    has_active_selection: bool,
    scope: ArtifactScope | None,
    rule_id: str = R2_RULE_ID,
    rule_sha256: str = R2_RULE_SHA256,
) -> PolicyEvaluation:
    """Evaluate a complete stored region snapshot without I/O or reranking.

    ``bird_tagged`` must reflect the original cohort predicate (normalized
    keyword LIKE ``bird%``), not a broader discovery or species predicate.
    ``regions`` must include every stored region for this run, across classes.
    ``scope`` identifies the exact producer combination under evaluation;
    matching it does not assert that the combination has passed qualification.
    An accept result cannot bypass reservation checks or grant authority.
    """
    if rule_id != R2_RULE_ID or rule_sha256 != R2_RULE_SHA256:
        return PolicyEvaluation("abstain", "unknown_policy")
    if bird_tagged is not True or has_active_selection is not False:
        return PolicyEvaluation("abstain", "outside_original_population")
    if (run.get("detector_key") != "bird" or run.get("is_current") is not True
            or run.get("status") != "detected"
            or run.get("coord_space") != "display_normalized"):
        return PolicyEvaluation("abstain", "outside_artifact_scope")
    if not _positive_id(run.get("id")) or not _positive_id(run.get("image_id")):
        return PolicyEvaluation("invalid", "invalid_run_identity")
    if scope is None:
        return PolicyEvaluation("abstain", "unknown_producer_scope")
    for key in ("detector_version", "detector_config_hash", "rendition_version"):
        expected = getattr(scope, key)
        if not isinstance(expected, str) or not expected.strip() or run.get(key) != expected:
            return PolicyEvaluation("abstain", "unknown_producer_scope")

    seen = set()
    rank_zero = []
    for row in regions:
        if not _positive_id(row.get("id")):
            return PolicyEvaluation("invalid", "invalid_region_identity")
        if row["id"] in seen:
            return PolicyEvaluation("invalid", "duplicate_region_id")
        seen.add(row["id"])
        if (not _positive_id(row.get("localization_run_id"))
                or row["localization_run_id"] != run["id"]):
            return PolicyEvaluation("invalid", "region_run_mismatch")
        rank = row.get("rank")
        if not isinstance(rank, int) or isinstance(rank, bool) or rank < 0:
            return PolicyEvaluation("invalid", "invalid_region_rank")
        if rank == 0:
            rank_zero.append(row)
    if not rank_zero:
        return PolicyEvaluation("invalid", "missing_rank_zero")
    if len(rank_zero) != 1:
        return PolicyEvaluation("invalid", "ambiguous_rank_zero")
    if not 1 <= len(regions) <= 3:
        return PolicyEvaluation("reject", "region_count_outside_rule")
    candidate = rank_zero[0]
    if candidate.get("object_class") != "bird":
        return PolicyEvaluation("abstain", "unknown_object_class")

    coords = [candidate.get(key) for key in ("x1", "y1", "x2", "y2")]
    if not all(_unit_number(value) for value in coords):
        return PolicyEvaluation("invalid", "invalid_geometry")
    x1, y1, x2, y2 = coords
    area = (x2 - x1) * (y2 - y1)
    if x2 <= x1 or y2 <= y1 or area <= 0:
        return PolicyEvaluation("invalid", "invalid_geometry")
    confidence = candidate.get("confidence")
    if confidence is not None and not _unit_number(confidence):
        return PolicyEvaluation("invalid", "invalid_confidence")
    if confidence is None or confidence < 0.70:
        return PolicyEvaluation("reject", "confidence_below_threshold")

    band = "small" if area < 0.005 else "medium" if area < 0.02 else "large"
    # Preserve frozen R2 float banding and the existing species consumer's
    # decimal comparison. Neither permission may broaden the other's boundary.
    dx1, dy1, dx2, dy2 = (Decimal(str(value)) for value in coords)
    species_eligible = band != "small" and (dx2 - dx1) * (dy2 - dy1) >= Decimal("0.005")
    return PolicyEvaluation(
        "accept", "r2_eligible", region_id=candidate["id"], area_fraction=area,
        band=band, geometry_eligible=True, species_eligible=species_eligible,
    )
