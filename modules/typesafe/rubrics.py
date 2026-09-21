"""Versioned rubric/question registry for TypeSafe (Jev) System One calls.

Every question the backend asks Jev is declared here with an explicit
``version`` so a recorded judgment can always be traced back to the exact
wording that produced it. Changing ``instructions`` or ``criteria`` for an
existing key **must** come with a version bump — stored judgments from the old
wording are not comparable to the new one.

The seeded entries are the three Phase-1 shadow-mode questions from the design
doc *Jev for Vexlum Scoring and Driftara Gallery*: distinctiveness, redundancy,
and evidence sufficiency.

Jev is text-only: ``state`` must be a string, JSON object, or array of text
values (https://docs.typesafe.ai/concepts/state). Building that state from
images is the caller's job; nothing here touches pixels.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Question types supported by the System One API.
NOUL = "noul"
CHOICE = "choice"
SCORE = "score"


@dataclass(frozen=True)
class Rubric:
    """One versioned question sent to Jev.

    ``criteria`` follows the SDK's per-type shape: ``None`` for a Noul, an
    ordered list of level labels for a Score, and a mapping of option name ->
    description for a Choice.
    """

    key: str
    version: str
    question_type: str
    instructions: str
    criteria: Any = None


_RUBRICS: tuple[Rubric, ...] = (
    Rubric(
        key="culling.distinctiveness",
        version="v1",
        question_type=SCORE,
        instructions=(
            "Judge how photographically distinctive this frame is relative to "
            "the other candidates in the same burst. Consider behaviour, pose, "
            "narrative interest, and subject-background relationship. Judge "
            "only from the supplied evidence; do not infer focus, sharpness, "
            "noise, or exposure."
        ),
        criteria=[
            "ordinary or redundant moment",
            "some visual or behavioural interest",
            "distinctive and engaging moment",
            "exceptional behaviour or storytelling",
        ],
    ),
    Rubric(
        key="culling.redundancy",
        version="v1",
        question_type=NOUL,
        instructions=(
            "Does this candidate add a genuinely distinct moment to the set "
            "already retained, rather than repeating one of them?"
        ),
    ),
    Rubric(
        key="keywords.relevance",
        version="v1",
        question_type=NOUL,
        instructions=(
            "Is the keyword under review genuinely supported by the supplied "
            "caption and metadata for this photograph? Judge only from the "
            "supplied text; do not guess at visual detail that is absent."
        ),
    ),
    Rubric(
        key="evidence.sufficiency",
        version="v1",
        question_type=NOUL,
        instructions=(
            "Is the supplied evidence sufficient to make this judgement "
            "safely, without guessing at visual detail that is absent?"
        ),
    ),
)

REGISTRY: dict[str, Rubric] = {r.key: r for r in _RUBRICS}

# Asked alongside any rubric whose result feeds a recommendation, so model
# confidence and evidence completeness stay separable (design doc: "A confident
# answer based on incomplete evidence is unsafe.").
EVIDENCE_SUFFICIENCY_KEY = "evidence.sufficiency"

# Separates a rubric key from the subject it is being asked about, so the same
# rubric can be asked about many subjects (e.g. every candidate keyword on one
# image) inside a single System One call.
SUBJECT_SEPARATOR = "::"


def subject_question_id(rubric_key: str, subject: str) -> str:
    """Question id addressing ``rubric_key`` at one ``subject``."""
    return f"{rubric_key}{SUBJECT_SEPARATOR}{subject}"


def get_rubric(key: str) -> Rubric:
    """Return the registered rubric for ``key``.

    Raises:
        KeyError: if ``key`` is not registered — callers pass literals from
            this module, so an unknown key is a programming error, not a
            runtime condition to degrade over.
    """
    return REGISTRY[key]


def build_question(rubric: Rubric) -> Any:
    """Build the SDK question object for ``rubric``.

    Imports ``typesafe_sdk`` lazily so the package stays importable (and the
    flag stays inspectable) without the optional dependency installed.
    """
    from typesafe_sdk import Choice, Noul, Score

    if rubric.question_type == NOUL:
        return Noul(instructions=rubric.instructions)
    if rubric.question_type == SCORE:
        return Score(instructions=rubric.instructions, criteria=rubric.criteria)
    if rubric.question_type == CHOICE:
        return Choice(instructions=rubric.instructions, criteria=rubric.criteria)
    raise ValueError(f"Unsupported question type: {rubric.question_type!r}")
