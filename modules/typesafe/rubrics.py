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
        key="culling.action",
        version="v1",
        question_type=CHOICE,
        instructions=(
            "Choose the culling label for the candidate image under this policy. "
            "Use only the supplied scores, captions, concepts, comparison context, "
            "and stated limitations. Pick means promote as a preferred selection. "
            "Keep means intentionally retain as a useful alternate without promotion. "
            "Reject means exclude from the working selection because evidenced "
            "limitations or redundancy outweigh retention value. Do not infer visual "
            "properties that the evidence does not report."
        ),
        criteria={
            "pick": "Promote as a preferred selection for editing or presentation.",
            "keep": "Retain intentionally as a useful alternate without promotion.",
            "reject": "Exclude from the working selection under the stated policy.",
        },
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
    # -- Agent harness decision points (scripts/agent_harness) ------------
    # Per-turn questions a coding-agent harness asks Jev; see
    # docs/technical/JEV_AGENT_HARNESS.md. State is text built from the
    # prompt, command or file metadata — never restricted file contents.
    Rubric(
        key="harness.context.visibility",
        version="v1",
        question_type=CHOICE,
        instructions=(
            "Decide how much of the instruction pack under review the coding "
            "agent should see while handling the supplied request. Judge only "
            "from the request text, recently touched paths, and the pack "
            "summary."
        ),
        criteria={
            "hide": "The pack is irrelevant to this request.",
            "short": "Only the one-line summary is useful as a reminder.",
            "full": "The request directly needs the pack's detailed rules.",
        },
    ),
    Rubric(
        key="harness.bundle.visibility",
        version="v1",
        question_type=CHOICE,
        instructions=(
            "Decide how much of the changed file under review a read-only "
            "reviewer needs to answer the supplied review question. Judge from "
            "the file path and its change summary."
        ),
        criteria={
            "hide": "Irrelevant to the question; list the path only.",
            "short": "The change summary and hunk headers are enough.",
            "full": "The reviewer needs the full diff of this file.",
        },
    ),
    Rubric(
        key="harness.tool.pick",
        version="v1",
        question_type=CHOICE,
        instructions=(
            "Choose the action that best fulfils the agent's stated intent. "
            "Options are candidate actions from a lexical search; prefer "
            "read-only actions when the intent does not ask for a change."
        ),
        # Criteria are the candidate actions, supplied per call.
        criteria=None,
    ),
    Rubric(
        key="harness.permission.exec",
        version="v1",
        question_type=CHOICE,
        instructions=(
            "Decide whether the coding agent should run the supplied command "
            "under the supplied policy. Consider the flagged script excerpt, "
            "whether it touches secrets, sends data off the machine, or "
            "destroys data, and whether the stated task scope justifies it."
        ),
        criteria={
            "allow": "Safe to run without asking the user.",
            "ask": "Plausible for the task but the user should confirm.",
            "deny": "Violates the policy and should not run.",
        },
    ),
    Rubric(
        key="harness.review.sensitivity",
        version="v1",
        # A Choice rather than a Score so the answer is a stable label.
        question_type=CHOICE,
        instructions=(
            "Judge how sensitive the file under review is to send to an "
            "external code-review vendor, from its path and metadata only."
        ),
        criteria={
            "public": "Public documentation or an open-source dependency.",
            "standard": "Ordinary application code.",
            "restricted": "Secrets, credentials, environment or infrastructure config.",
        },
    ),
    Rubric(
        key="harness.route.leave_frontier",
        version="v1",
        question_type=NOUL,
        instructions=(
            "Can this subtask be completed correctly by a smaller model given "
            "only the listed purpose-built context, without the rest of the "
            "session?"
        ),
    ),
    Rubric(
        key="harness.subgoal.duplicate",
        version="v1",
        question_type=NOUL,
        instructions=(
            "Is the new subgoal already covered by the prior subgoal under "
            "review, so launching it would repeat work that is done or in "
            "flight?"
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


def build_question(
    rubric: Rubric, *, subject: str | None = None, criteria: Any = None
) -> Any:
    """Build the SDK question object for ``rubric``.

    Imports ``typesafe_sdk`` lazily so the package stays importable (and the
    flag stays inspectable) without the optional dependency installed.

    ``criteria`` overrides the rubric's criteria for rubrics whose options
    are only known at call time (e.g. ``harness.tool.pick``).

    ``subject`` is included in model-visible instructions. Question mapping
    keys are response correlation IDs and TypeSafe does not send them to the
    model, so a per-subject question must not rely on its key for meaning.
    """
    from typesafe_sdk import Choice, Noul, Score

    instructions: Any = rubric.instructions
    if subject is not None:
        instructions = {
            "judgment": rubric.instructions,
            "subject_under_review": subject,
        }

    chosen = rubric.criteria if criteria is None else criteria
    if rubric.question_type == NOUL:
        return Noul(instructions=instructions)
    if rubric.question_type == SCORE:
        return Score(instructions=instructions, criteria=chosen)
    if rubric.question_type == CHOICE:
        return Choice(instructions=instructions, criteria=chosen)
    raise ValueError(f"Unsupported question type: {rubric.question_type!r}")
