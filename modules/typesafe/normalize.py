"""Normalize System One responses into auditable judgments.

Keeps two signals the design doc insists stay separate:

* **model confidence** — how concentrated the answer distribution is. Choice and
  Score answers carry this directly; a Noul returns a single probability in
  ``[0, 1]``, so confidence is its distance from the 0.5 coin-flip, rescaled to
  ``[0, 1]``.
* **evidence completeness** — whether the supplied evidence can support the
  decision at all. This is *not* an API field; it comes from asking the
  ``evidence.sufficiency`` rubric alongside the real question.

A confident answer over incomplete evidence is unsafe, so collapsing the two
into one number would defeat the point.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from modules.typesafe.rubrics import CHOICE, NOUL, SCORE, Rubric

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Judgment:
    """One normalized answer, carrying everything needed to audit it later."""

    key: str
    rubric_version: str
    question_type: str
    value: Any
    model: str | None = None
    probabilities: dict[str, float] | None = None
    confidence: float | None = None
    evidence_completeness: float | None = None
    evidence_hash: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def evidence_hash(state: Any) -> str:
    """Stable SHA-256 over the evidence ``state`` for reproducibility audits.

    Sorts keys so semantically identical state hashes identically regardless of
    dict ordering.
    """
    try:
        payload = json.dumps(state, sort_keys=True, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        payload = repr(state)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def noul_confidence(value: Any) -> float | None:
    """Rescale a Noul probability to a ``[0, 1]`` confidence.

    ``0.5`` (maximum uncertainty) maps to ``0.0``; ``0.0`` and ``1.0`` both map
    to ``1.0``.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return min(1.0, max(0.0, abs(2.0 * v - 1.0)))


def _answer_for(response: Any, rubric: Rubric, answer_key: str) -> Any:
    """Pull the per-type answer object out of a System One response."""
    bucket = {NOUL: "nouls", CHOICE: "choices", SCORE: "scores"}.get(
        rubric.question_type
    )
    if bucket is None:
        return None
    container = getattr(response, bucket, None)
    if container is None:
        return None
    try:
        return container[answer_key]
    except (KeyError, TypeError, IndexError):
        return None


def normalize(
    response: Any,
    rubric: Rubric,
    *,
    completeness: float | None = None,
    state: Any = None,
    answer_key: str | None = None,
) -> Judgment | None:
    """Turn one answer in ``response`` into a :class:`Judgment`.

    ``answer_key`` defaults to ``rubric.key``; pass it when the same rubric was
    asked about several subjects in one call and the question ids are therefore
    suffixed (see :func:`modules.typesafe.rubrics.subject_question_id`).

    Returns ``None`` if the response carries no answer for ``rubric`` — callers
    treat that as "no verdict" rather than an error, so a partial response still
    yields the answers that did arrive.
    """
    key = answer_key or rubric.key
    answer = _answer_for(response, rubric, key)
    if answer is None:
        logger.warning("TypeSafe response carried no answer for %r", key)
        return None

    value = getattr(answer, rubric.question_type, None)
    confidence = getattr(answer, "confidence", None)
    if confidence is None and rubric.question_type == NOUL:
        confidence = noul_confidence(value)

    probabilities = getattr(answer, "probabilities", None)
    if probabilities is not None and not isinstance(probabilities, dict):
        probabilities = None

    return Judgment(
        key=rubric.key,
        rubric_version=rubric.version,
        question_type=rubric.question_type,
        value=value,
        model=getattr(response, "model", None),
        probabilities=probabilities,
        confidence=confidence,
        evidence_completeness=completeness,
        evidence_hash=evidence_hash(state) if state is not None else None,
        raw={"legend": getattr(answer, "legend", None)},
    )
