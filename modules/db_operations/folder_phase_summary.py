"""Folder phase summary cache, query, and status rollup."""

import datetime
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class FolderPhaseSummaryServices:
    """Current facade collaborators, captured for one summary request."""

    get_or_create_folder: Callable
    should_run_heal: Callable
    heal_stale_phase_flags: Callable
    get_connector: Callable
    sql_bird_species_in_scope: Callable
    sql_bird_bbox_needs_scan: Callable
    get_db_engine: Callable
    is_missing_keywords_column_error: Callable
    pin_keywords_column_absent: Callable
    logger: logging.Logger


def get_folder_phase_summary(
    folder_path, force_refresh=False, *, services: FolderPhaseSummaryServices
):
    """
    Return phase status summary for a folder and descendants.

    Uses folder-level cache (`folders.phase_agg_json`) and recomputes live data
    when `phase_agg_dirty = 1`. Pass force_refresh=True to bypass cache and
    always recompute (e.g. when user selects a folder or clicks Refresh).

    When force_refresh=True, also runs _heal_stale_phase_flags to auto-reset
    any 'done' status flags where actual data (scores, keywords) is missing.
    """
    from modules import utils

    wsl_path = (
        utils.convert_path_to_wsl(folder_path)
        if hasattr(utils, "convert_path_to_wsl")
        else folder_path
    )
    target_path = wsl_path if wsl_path else folder_path
    base_folder_id = services.get_or_create_folder(target_path)
    if not base_folder_id:
        return []

    try:
        if force_refresh and services.should_run_heal(folder_path):
            try:
                services.heal_stale_phase_flags(folder_path)
            except Exception as heal_err:
                services.logger.debug(
                    "_heal_stale_phase_flags non-fatal error for '%s': %s",
                    folder_path,
                    heal_err,
                )

        if not force_refresh:
            cache_row = services.get_connector().query_one(
                "SELECT phase_agg_dirty, phase_agg_json FROM folders WHERE id = ?",
                (base_folder_id,),
            )
            if (
                cache_row
                and (cache_row.get("phase_agg_dirty") or 0) == 0
                and cache_row.get("phase_agg_json")
            ):
                try:
                    return json.loads(cache_row["phase_agg_json"])
                except Exception:
                    pass

        rows = _query_phase_rows(target_path, services)

        result, scoring_done = _rollup_phase_rows(rows)

        # Cache the computed result (non-fatal if this fails)
        try:
            services.get_connector().execute(
                "UPDATE folders SET phase_agg_dirty = 0, phase_agg_updated_at = ?, phase_agg_json = ?, is_fully_scored = ? WHERE id = ?",
                (
                    datetime.datetime.now(),
                    json.dumps(result),
                    1 if scoring_done else 0,
                    base_folder_id,
                ),
            )
        except Exception as cache_err:
            services.logger.debug(
                "get_folder_phase_summary cache write failed for '%s' (non-fatal): %s",
                folder_path,
                cache_err,
            )
        return result
    except Exception as e:
        services.logger.error(
            "get_folder_phase_summary failed for '%s': %s", folder_path, e
        )
        return []


def _query_phase_rows(target_path, services: FolderPhaseSummaryServices):
    path_like_unix = target_path + "/%"
    path_like_win = target_path + "\\%"
    query_params = (target_path, path_like_unix, path_like_win)

    rows = None
    for attempt in range(2):
        birds_scope = services.sql_bird_species_in_scope("i")
        agg_scope = f"(LOWER(TRIM(pp.code)) <> 'bird_species' OR ({birds_scope}))"
        # Phantom-folder guard: a bird image that already carries a ``species:*``
        # keyword is classified, but legacy/import tagging may never have written an
        # ``image_phase_status`` row for it. Without a row it counts as in-scope but
        # not done, pinning the folder in ``awaiting_bird_species`` (auto-drive then
        # churns ``nothing_to_queue`` on it). Count such rowless-but-classified images
        # as done-equivalent. Gated on ``ips.status IS NULL`` so real running/failed/
        # skipped rows are never overridden, and on bird_species only.
        bs_classified = """EXISTS (
                SELECT 1 FROM image_keywords ik_s
                JOIN keywords_dim kd_s ON kd_s.keyword_id = ik_s.keyword_id
                WHERE ik_s.image_id = i.id AND LOWER(kd_s.keyword_norm) LIKE 'species:%'
            )"""
        bs_done_extra = f"(LOWER(TRIM(pp.code)) = 'bird_species' AND ips.status IS NULL AND {bs_classified})"
        # ``bird_bbox`` is a product of the bird_species phase, so an image still
        # missing its box has not finished the phase even when IPS says ``done`` or
        # ``skipped``. Excluding it from both terminal counts is what lets the folder
        # rollup — and therefore the Dashboard bucket and auto-drive — see the gap.
        # Mirrors ``get_phase_incomplete_sql('bird_species')``.
        bbox_needs_scan_sql = services.sql_bird_bbox_needs_scan("i")
        if bbox_needs_scan_sql == "1=0":
            bs_bbox_gap = "1=0"
            agg_image_cols = "id"
        else:
            bs_bbox_gap = (
                f"(LOWER(TRIM(pp.code)) = 'bird_species' AND ({bbox_needs_scan_sql}))"
            )
            agg_image_cols = "id, bird_bbox"
        try:
            rows = services.get_connector().query(
                f"""
                    SELECT
                        pp.code,
                        pp.name,
                        pp.sort_order,
                        COUNT(CASE WHEN {agg_scope} THEN i.id END) as total_images,
                        COALESCE(SUM(CASE WHEN {agg_scope} AND NOT ({bs_bbox_gap}) AND (ips.status = 'done' OR {bs_done_extra}) THEN 1 ELSE 0 END), 0) as done_count,
                        COALESCE(SUM(CASE WHEN {agg_scope} AND ips.status = 'failed' THEN 1 ELSE 0 END), 0) as failed_count,
                        COALESCE(SUM(CASE WHEN {agg_scope} AND ips.status = 'running' THEN 1 ELSE 0 END), 0) as running_count,
                        COALESCE(SUM(CASE WHEN {agg_scope} AND ips.status = 'queued' THEN 1 ELSE 0 END), 0) as queued_count,
                        COALESCE(SUM(CASE WHEN {agg_scope} AND ips.status = 'paused' THEN 1 ELSE 0 END), 0) as paused_count,
                        COALESCE(SUM(CASE WHEN {agg_scope} AND ips.status = 'cancel_requested' THEN 1 ELSE 0 END), 0) as cancel_requested_count,
                        COALESCE(SUM(CASE WHEN {agg_scope} AND ips.status = 'restarting' THEN 1 ELSE 0 END), 0) as restarting_count,
                        COALESCE(SUM(CASE WHEN {agg_scope} AND NOT ({bs_bbox_gap}) AND ips.status = 'skipped' THEN 1 ELSE 0 END), 0) as skipped_count,
                        pp.optional
                    FROM pipeline_phases pp
                    CROSS JOIN (
                        SELECT {agg_image_cols} FROM images
                        WHERE folder_id IN (
                            SELECT id FROM folders
                            WHERE path = ? OR path LIKE ? OR path LIKE ?
                        )
                    ) i
                    LEFT JOIN image_phase_status ips
                        ON ips.image_id = i.id AND ips.phase_id = pp.id
                    WHERE pp.enabled = 1
                    GROUP BY pp.code, pp.name, pp.sort_order, pp.optional
                    ORDER BY pp.sort_order
                    """,
                query_params,
            )
            break
        except Exception as query_err:
            if (
                attempt == 0
                and services.get_db_engine() == "postgres"
                and services.is_missing_keywords_column_error(query_err)
            ):
                services.pin_keywords_column_absent()
                services.logger.info(
                    "get_folder_phase_summary: legacy images.keywords missing; "
                    "retrying with normalized keyword tables only"
                )
                continue
            raise
    return rows


def _rollup_phase_rows(rows):
    result = []
    scoring_done = False
    for row in rows:
        code = row["code"].strip() if isinstance(row["code"], str) else row["code"]
        name = row["name"].strip() if isinstance(row["name"], str) else row["name"]
        sort_order = row["sort_order"]
        total = row["total_images"] or 0
        done = row["done_count"] or 0
        failed = row["failed_count"] or 0
        running = row["running_count"] or 0
        queued = row["queued_count"] or 0
        paused = row["paused_count"] or 0
        cancel_requested = row["cancel_requested_count"] or 0
        restarting = row["restarting_count"] or 0
        skipped = row["skipped_count"] or 0
        is_optional = bool(row["optional"])

        # ``skipped`` is a terminal state (already_done_* / not_applicable).
        # Treat it as advance-ready for required phases too — without this,
        # fully-processed folders read as ``partial`` indefinitely (e.g.
        # an indexing run that emits ``already_indexed`` for every image).
        advance_ready = done + skipped
        if total == 0:
            if code == "bird_species" and is_optional:
                status = "skipped"
            else:
                status = "not_started"
        elif done == total:
            status = "done"
        elif skipped == total and is_optional:
            status = "skipped"
        elif advance_ready == total and failed == 0:
            # done+skipped covers every image and nothing failed — folder is finished
            # for this phase regardless of optional/required.
            status = "done"
        elif running > 0:
            status = "running"
        elif paused > 0:
            status = "paused"
        elif queued > 0:
            status = "queued"
        elif restarting > 0:
            status = "restarting"
        elif cancel_requested > 0:
            status = "cancel_requested"
        elif done > 0 or skipped > 0:
            status = "partial"
        elif failed > 0:
            # Minority failures among mostly un-attempted images are partial,
            # not folder-fatal — avoids a red "failed" rollup when 13/674 failed.
            status = "failed" if failed >= total else "partial"
        else:
            status = "not_started"

        if code == "scoring" and status == "done":
            scoring_done = True

        result.append(
            {
                "code": code,
                "name": name,
                "sort_order": sort_order,
                "status": status,
                "done_count": done,
                "failed_count": failed,
                "running_count": running,
                "queued_count": queued,
                "paused_count": paused,
                "cancel_requested_count": cancel_requested,
                "restarting_count": restarting,
                "skipped_count": skipped,
                "total_count": total,
                "optional": is_optional,
                "advance_ready": advance_ready == total if total > 0 else False,
            }
        )
    return result, scoring_done
