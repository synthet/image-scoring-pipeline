"""Per-image keyword tagging workflow used by :class:`TaggingRunner`.

The runner keeps batch orchestration and public state; this module owns the
single-image inference, persistence, phase-status, and reporting path.
"""

from __future__ import annotations

import logging
import os
import textwrap
from dataclasses import dataclass
from typing import Any

from modules import db
from modules.events import event_manager
from modules.phases import PhaseCode, PhaseStatus
from modules.typesafe import keyword_shadow

logger = logging.getLogger(__name__)

_RAW_EXTENSIONS = frozenset({".nef", ".nrw", ".arw", ".cr2", ".cr3", ".dng"})


@dataclass(slots=True)
class _InferenceResult:
    tags: list[str]
    caption: str
    title: str
    confidence_map: dict[str, float]
    relevance_map: dict[str, float]


def _processing_path(path: str) -> str:
    if (
        ":" not in path
        or len(path) < 2
        or path[1] != ":"
        or not os.path.exists("/mnt/")
    ):
        return path
    drive = path[0].lower()
    suffix = path[2:].replace("\\", "/")
    return f"/mnt/{drive}{suffix}"


def _inference_path(row: dict[str, Any], processing_path: str) -> str:
    if os.path.splitext(processing_path)[1].lower() not in _RAW_EXTENSIONS:
        return processing_path
    from modules.thumbnails import get_thumb_wsl

    thumbnail = get_thumb_wsl(row)
    return thumbnail if thumbnail and os.path.exists(thumbnail) else processing_path


def _embedding_persistence_flags() -> tuple[bool, bool]:
    from modules import config

    section = config.get_config_section("embeddings") or {}
    return (
        bool(section.get("persist_clip_image", True)),
        bool(section.get("persist_blip_image", True)),
    )


def _run_inference(
    runner,
    row: dict[str, Any],
    *,
    inference_path: str,
    custom_keywords,
    generate_captions: bool,
    write_keyword_relevance: bool,
) -> _InferenceResult:
    persist_clip, persist_blip = _embedding_persistence_flags()
    confidence_map: dict[str, float] = {}
    relevance_map: dict[str, float] = {}

    if runner.tagging_engine is not None:
        tags = runner.tagging_engine.predict_keywords(inference_path, custom_keywords)
        caption = (
            runner.tagging_engine.generate_caption(inference_path)
            if generate_captions
            else ""
        )
    else:
        reuse_embedding = (
            runner._reuse_clip_embedding(row["id"]) if persist_clip else None
        )
        if write_keyword_relevance:
            tags, confidence_map, relevance_map = runner.scorer.predict(
                inference_path,
                keywords=custom_keywords,
                return_scores=True,
                image_embedding=reuse_embedding,
            )
        else:
            tags = runner.scorer.predict(
                inference_path,
                keywords=custom_keywords,
                image_embedding=reuse_embedding,
            )
        caption = (
            runner.captioner.generate(inference_path, extract_embedding=persist_blip)
            if generate_captions
            else ""
        )

    if runner.tagging_engine is None:
        try:
            runner._persist_tagging_embeddings(row["id"], persist_clip, persist_blip)
        except Exception:
            logger.warning(
                "tagging: embedding persist failed for image_id=%s",
                row.get("id"),
                exc_info=True,
            )
    elif (persist_clip or persist_blip) and not getattr(
        runner, "_warned_engine_persist_gap", False
    ):
        logger.warning(
            "tagging: shared tagging_engine path does not yet extract "
            "CLIP/BLIP image embeddings; image_embeddings_512 / "
            "image_embeddings_768 will not populate via this runner. "
            "Set embeddings.persist_clip_image / persist_blip_image to "
            "false to silence this warning, or use TaggingRunner() with "
            "no engine arg."
        )
        runner._warned_engine_persist_gap = True

    cleaned_caption = (caption or "").strip()
    return _InferenceResult(
        tags=[tag.strip() for tag in (tags or []) if tag and tag.strip()],
        caption=cleaned_caption,
        title=(
            textwrap.shorten(cleaned_caption, width=50, placeholder="...")
            if generate_captions
            else ""
        ),
        confidence_map=confidence_map,
        relevance_map=relevance_map,
    )


def _accessibility_metadata(
    runner,
    row: dict[str, Any],
    *,
    original_path: str,
    tags: list[str],
    overwrite: bool,
    log,
) -> tuple[str | None, str | None]:
    from modules import clip_accessibility

    result = clip_accessibility.describe_from_clip(
        image_id=row["id"],
        image_path=original_path,
        keywords=tags,
        scorer=runner.scorer if runner.tagging_engine is None else None,
        overwrite=overwrite,
    )
    if result.get("error"):
        return None, None
    if result.get("skipped"):
        log(
            f"Accessibility skipped image_id={row['id']}: {result.get('reason')}",
            "DEBUG",
            image_id=row["id"],
        )
    return (
        (result.get("alt_text") or "").strip() or None,
        (result.get("extended_description") or "").strip() or None,
    )


def _record_report(
    report_collector,
    method: str,
    *args,
    image_id: Any,
    **kwargs,
) -> None:
    if report_collector is None:
        return
    try:
        getattr(report_collector, method)(*args, **kwargs)
    except Exception:
        logger.debug(
            "tagging: %s failed for image_id=%s",
            method,
            image_id,
            exc_info=True,
        )


def _set_phase_status(
    image_id: int,
    status: PhaseStatus,
    *,
    app_version: str,
    tagger_version: str,
    job_id,
    **kwargs,
) -> None:
    db.set_image_phase_status(
        image_id,
        PhaseCode.KEYWORDS,
        status,
        app_version=app_version,
        executor_version=tagger_version,
        job_id=job_id,
        **kwargs,
    )


def _write_outputs(
    runner,
    row: dict[str, Any],
    result: _InferenceResult,
    *,
    processing_path: str,
    original_path: str,
    alt_text: str | None,
    extended_description: str | None,
    write_keyword_relevance: bool,
    job_id,
) -> str:
    tags_csv = ",".join(result.tags)
    use_scored_keywords = bool(
        result.tags
        and write_keyword_relevance
        and (result.confidence_map or result.relevance_map)
    )
    field_updates = {
        "title": result.title if result.title else row.get("title"),
        "description": result.caption if result.caption else row.get("description"),
    }
    if not use_scored_keywords:
        field_updates["keywords"] = tags_csv
    db.update_image_fields_batch([(row["id"], field_updates)])

    if use_scored_keywords:
        db.update_image_keywords_for_image(
            row["id"],
            tags_csv,
            source="auto",
            confidence_map=result.confidence_map,
            relevance_map=result.relevance_map,
        )
        keyword_shadow.verify_image(
            int(row["id"]),
            processing_path,
            result.caption,
            result.tags,
            result.relevance_map,
            title=result.title,
            job_id=job_id,
        )
    if alt_text or extended_description:
        db.upsert_image_xmp(
            row["id"],
            {"alt_text": alt_text, "extended_description": extended_description},
        )
    runner.write_metadata(
        original_path,
        result.tags,
        result.title,
        result.caption,
        alt_text=alt_text or "",
        extended_description=extended_description or "",
    )
    return tags_csv


def _persist_result(
    runner,
    row: dict[str, Any],
    result: _InferenceResult,
    *,
    processing_path: str,
    original_path: str,
    folder: str,
    alt_text: str | None,
    extended_description: str | None,
    write_keyword_relevance: bool,
    app_version: str,
    tagger_version: str,
    job_id,
    report_collector,
    processed_folders,
) -> bool:
    keywords_produced = bool(result.tags)
    metadata_produced = bool(result.caption or alt_text or extended_description)
    if not keywords_produced and not metadata_produced:
        _set_phase_status(
            row["id"],
            PhaseStatus.SKIPPED,
            app_version=app_version,
            tagger_version=tagger_version,
            job_id=job_id,
            skip_reason="no tags produced",
            skipped_by="tagging",
        )
        _record_report(
            report_collector,
            "record_skip",
            int(row["id"]),
            "no tags produced",
            image_id=row.get("id"),
        )
        return False

    tags_csv = _write_outputs(
        runner,
        row,
        result,
        processing_path=processing_path,
        original_path=original_path,
        alt_text=alt_text,
        extended_description=extended_description,
        write_keyword_relevance=write_keyword_relevance,
        job_id=job_id,
    )

    if keywords_produced:
        processed_folders.add(folder)
        _set_phase_status(
            row["id"],
            PhaseStatus.DONE,
            app_version=app_version,
            tagger_version=tagger_version,
            job_id=job_id,
        )
        _record_report(
            report_collector,
            "record_after",
            int(row["id"]),
            {
                "keywords": tags_csv,
                "title": result.title or None,
                "description": result.caption or None,
            },
            action="processed",
            image_id=row.get("id"),
        )
        return True

    _set_phase_status(
        row["id"],
        PhaseStatus.SKIPPED,
        app_version=app_version,
        tagger_version=tagger_version,
        job_id=job_id,
        skip_reason="caption_only_no_keywords",
        skipped_by="tagging",
    )
    _record_report(
        report_collector,
        "record_skip",
        int(row["id"]),
        "caption_only_no_keywords",
        image_id=row.get("id"),
    )
    return False


def _record_failure(
    row: dict[str, Any],
    error: Exception,
    *,
    app_version: str,
    tagger_version: str,
    job_id,
    report_collector,
) -> None:
    message = str(error)[:1024]
    try:
        _set_phase_status(
            row["id"],
            PhaseStatus.FAILED,
            app_version=app_version,
            tagger_version=tagger_version,
            job_id=job_id,
            error=message,
        )
    except Exception:
        logger.exception(
            "tagging: failed to record FAILED phase status for image_id=%s",
            row.get("id"),
        )
    _record_report(
        report_collector,
        "record_failure",
        int(row["id"]),
        message,
        image_id=row.get("id"),
    )


def _broadcast_progress(runner, job_id) -> None:
    runner.current_count += 1
    if runner.current_count % 5 != 0:
        return
    event_manager.broadcast_threadsafe(
        "job_progress",
        {
            "job_id": job_id,
            "job_type": "tagging",
            "phase_code": "keywords",
            "current": runner.current_count,
            "total": runner.total_count,
        },
    )


def process_tagging_image_row(
    runner,
    row,
    *,
    app_version: str,
    tagger_version: str,
    custom_keywords,
    overwrite,
    generate_captions,
    generate_accessibility,
    job_id,
    report_collector,
    write_keyword_relevance,
    log,
    processed_count,
    skipped_count,
    processed_folders,
):
    """Process one image while keeping batch state on the owning runner."""
    original_path = row["file_path"]
    folder = os.path.dirname(original_path)
    processing_path = _processing_path(original_path)
    _set_phase_status(
        row["id"],
        PhaseStatus.RUNNING,
        app_version=app_version,
        tagger_version=tagger_version,
        job_id=job_id,
    )

    try:
        log(
            f"Tagging image_id={row['id']}: {processing_path}",
            "DEBUG",
            image_id=row["id"],
        )
        result = _run_inference(
            runner,
            row,
            inference_path=_inference_path(row, processing_path),
            custom_keywords=custom_keywords,
            generate_captions=generate_captions,
            write_keyword_relevance=write_keyword_relevance,
        )
        alt_text = extended_description = None
        if generate_accessibility:
            alt_text, extended_description = _accessibility_metadata(
                runner,
                row,
                original_path=original_path,
                tags=result.tags,
                overwrite=overwrite,
                log=log,
            )
        processed = _persist_result(
            runner,
            row,
            result,
            processing_path=processing_path,
            original_path=original_path,
            folder=folder,
            alt_text=alt_text,
            extended_description=extended_description,
            write_keyword_relevance=write_keyword_relevance,
            app_version=app_version,
            tagger_version=tagger_version,
            job_id=job_id,
            report_collector=report_collector,
            processed_folders=processed_folders,
        )
        if processed:
            processed_count += 1
        else:
            skipped_count += 1
    except Exception as error:
        log(
            f"Error processing {processing_path}: {error}",
            "ERROR",
            image_id=row["id"],
        )
        skipped_count += 1
        _record_failure(
            row,
            error,
            app_version=app_version,
            tagger_version=tagger_version,
            job_id=job_id,
            report_collector=report_collector,
        )

    _broadcast_progress(runner, job_id)
    return processed_count, skipped_count
