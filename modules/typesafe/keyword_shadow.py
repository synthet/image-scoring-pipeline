"""Shadow-mode keyword verification against Jev — report-only, no DB write.

The ``keywords`` phase assigns tags from CLIP similarity and derives a stable
``relevance_weight`` via :func:`modules.keyword_relevance.cosine_to_relevance`.
That transform is local, free and already calibrated. This module asks whether a
text judge does better, by putting the BLIP caption plus the candidate keywords
in front of Jev and recording both verdicts side by side.

Deliberately **report-only**. The design doc defers new DB fields until the
canonical schema sources are reviewed, and its first milestone is an offline
error-analysis report *before* any production endpoint. So verdicts land in a
JSONL file under ``reports/typesafe-keyword-shadow/`` and nothing in the tagging
phase reads them back. Tag assignment and ``relevance_weight`` are untouched.

Off unless **both** ``typesafe.enabled`` and ``typesafe.keyword_shadow.enabled``
are true. Every entry point swallows its own errors: this is an observation-only
side channel and must never fail a tagging run.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from modules import config

logger = logging.getLogger(__name__)

_REPORT_SUBDIR = Path("reports") / "typesafe-keyword-shadow"
_RUBRIC_KEY = "keywords.relevance"
_DEFAULT_MAX_KEYWORDS = 10

# One writer per process; the tagging phase runs a producer-consumer pipeline,
# so appends have to be serialized.
_write_lock = threading.Lock()


def _section() -> dict[str, Any]:
    section = config.get_config_section("typesafe") or {}
    sub = section.get("keyword_shadow")
    return sub if isinstance(sub, dict) else {}


def is_enabled() -> bool:
    """True only when the adapter *and* this shadow channel are both on."""
    try:
        section = config.get_config_section("typesafe") or {}
        if not section.get("enabled", False):
            return False
        return bool(_section().get("enabled", False))
    except Exception:
        logger.exception("typesafe keyword shadow: config read failed")
        return False


def max_keywords() -> int:
    """Cap on keywords judged per image, so one bad image cannot blow the bill."""
    try:
        value = int(_section().get("max_keywords_per_image", _DEFAULT_MAX_KEYWORDS))
    except (TypeError, ValueError):
        return _DEFAULT_MAX_KEYWORDS
    return max(1, value)


def report_path(job_id: int | None = None) -> Path:
    """JSONL destination, one file per job (``unscoped`` when there is no job)."""
    base = Path(getattr(config, "BASE_DIR", ".")) / _REPORT_SUBDIR
    suffix = f"job-{job_id}" if job_id is not None else "unscoped"
    return base / f"{suffix}.jsonl"


def build_state(
    caption: str,
    keywords: list[str],
    *,
    title: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the text evidence Jev will judge.

    Jev is text-only, so everything here has to already be words: the caption
    produced upstream by BLIP, the candidate keywords, and any textual metadata
    the caller wants to add. No pixels reach this function.
    """
    state: dict[str, Any] = {
        "caption": (caption or "").strip(),
        "candidate_keywords": list(keywords),
        "evidence_version": "v1",
    }
    if title:
        state["title"] = title
    if extra:
        state.update(extra)
    return state


def _append(records: list[dict[str, Any]], job_id: int | None) -> int:
    if not records:
        return 0
    path = report_path(job_id)
    try:
        with _write_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as handle:
                for record in records:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("typesafe keyword shadow: failed writing %s", path)
        return 0
    return len(records)


def verify_image(
    image_id: int,
    file_path: str,
    caption: str,
    keywords: list[str],
    relevance_map: dict[str, float] | None = None,
    *,
    title: str | None = None,
    job_id: int | None = None,
    client: Any = None,
) -> int:
    """Record Jev verdicts for one image's keywords beside the CLIP weights.

    Returns the number of verdicts written. Returns ``0`` — never raises — if
    the channel is off, there is nothing to judge, or anything at all fails.
    """
    try:
        if not is_enabled():
            return 0
        subjects = [k for k in (keywords or []) if k][: max_keywords()]
        if not subjects or not (caption or "").strip():
            return 0

        if client is None:
            from modules.typesafe.client import TypeSafeClient

            client = TypeSafeClient()
        if not client.available:
            return 0

        state = build_state(caption, subjects, title=title)
        judgments = client.judge_subjects(state, _RUBRIC_KEY, subjects)
        if not judgments:
            return 0

        weights = relevance_map or {}
        stamp = time.time()
        records = [
            {
                "ts": stamp,
                "job_id": job_id,
                "image_id": image_id,
                "file_path": file_path,
                "keyword": subject,
                "caption": state["caption"],
                # The incumbent: CLIP cosine -> sigmoid, already calibrated.
                "clip_relevance_weight": weights.get(subject),
                # The challenger: Jev's text judgment, in the same (0, 1) space.
                "jev_relevance": judgment.value,
                "jev_confidence": judgment.confidence,
                "evidence_completeness": judgment.evidence_completeness,
                "rubric_version": judgment.rubric_version,
                "model": judgment.model,
                "evidence_hash": judgment.evidence_hash,
            }
            for subject, judgment in judgments.items()
        ]
        return _append(records, job_id)
    except Exception:
        # Observation-only: a failure here must not touch the tagging run.
        logger.exception(
            "typesafe keyword shadow: verification failed for image_id=%s", image_id
        )
        return 0
