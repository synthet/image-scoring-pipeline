"""
Selection Service Module

Unified orchestrator for stack creation + pick/reject assignment.
Replaces separate Stacks and Culling workflows with a single run/stop/status flow.
"""

import logging
import os
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Optional

from modules import db, clustering, utils
from modules.selection_policy import classify_sorted_ids, POLICY_VERSION
from modules.selection_metadata import write_selection_metadata

logger = logging.getLogger(__name__)

ProgressCb = Callable[[float, str], None]

# Fixed time gap for Selection workflow - do NOT use config default (per plan)
SELECTION_TIME_GAP_SECONDS = 120


@dataclass
class SelectionConfig:
    score_field: str = "score_general"
    pick_fraction: float = 0.33
    reject_fraction: float = 0.33
    force_rescan: bool = False
    write_stack_ids: bool = True
    write_pick_reject: bool = True
    verify_sidecar_write: bool = False


@dataclass
class SelectionSummary:
    total_images: int
    total_stacks: int
    picked: int
    rejected: int
    neutral: int
    sidecar_written: int
    sidecar_errors: int
    status: str


class SelectionService:
    """
    Orchestrates the full Selection pipeline: cluster -> assign pick/reject -> persist.
    """

    def __init__(self):
        self._stop_requested = threading.Event()
        self._cluster_engine = clustering.ClusteringEngine()

    def _progress(self, progress_cb: Optional[ProgressCb], pct: float, msg: str):
        if progress_cb:
            try:
                progress_cb(pct, msg)
            except Exception:
                pass

    def _check_stop(self) -> bool:
        return self._stop_requested.is_set()

    def stop(self) -> None:
        self._stop_requested.set()

    def run(
        self,
        input_path: str,
        cfg: Optional[SelectionConfig] = None,
        progress_cb: Optional[ProgressCb] = None,
    ) -> SelectionSummary:
        cfg = cfg or SelectionConfig()
        self._stop_requested.clear()

        # Normalize path
        input_path = (input_path or "").strip()
        if not input_path:
            return SelectionSummary(
                0, 0, 0, 0, 0, 0, 0,
                status="error",
            )

        # Convert to local path (WSL support)
        local_path = utils.convert_path_to_local(input_path)
        if not os.path.exists(local_path):
            return SelectionSummary(
                0, 0, 0, 0, 0, 0, 0,
                status=f"error: Path not found: {input_path}",
            )

        try:
            # Stage 1: Resolve images from DB
            self._progress(progress_cb, 0.02, "Scanning images...")
            images = db.get_images_by_folder(local_path)
            if not images:
                return SelectionSummary(
                    0, 0, 0, 0, 0, 0, 0,
                    status="No scored images found in folder. Run Scoring first.",
                )

            n_images = len(images)
            self._progress(progress_cb, 0.05, f"Found {n_images} images. Clustering stacks...")

            # Stage 2-3: Create/refresh stacks (clustering)
            # Use fixed time_gap - do NOT read default_time_gap from config
            for _ in self._cluster_engine.cluster_images(
                distance_threshold=0.15,
                time_gap_seconds=SELECTION_TIME_GAP_SECONDS,
                force_rescan=cfg.force_rescan,
                target_folder=local_path,
            ):
                if self._check_stop():
                    return SelectionSummary(
                        n_images, 0, 0, 0, 0, 0, 0,
                        status="stopped",
                    )

            if self._check_stop():
                return SelectionSummary(n_images, 0, 0, 0, 0, 0, 0, status="stopped")

            # Re-fetch images (now with stack_id)
            images = db.get_images_by_folder(local_path)
            if not images:
                return SelectionSummary(0, 0, 0, 0, 0, 0, 0, status="No images after clustering")

            # Stage 4-5: Group by stack, sort, apply policy
            self._progress(progress_cb, 0.4, "Assigning pick/reject bands...")
            by_stack = defaultdict(list)
            for img in images:
                sid = img.get("stack_id")
                by_stack[sid].append(img)

            # Tie-break: score_field DESC, created_at ASC, id ASC
            score_col = cfg.score_field
            def sort_key(img):
                s = img.get(score_col) or 0
                c = img.get("created_at") or ""
                i = img.get("id") or 0
                return (-float(s) if s else 0, str(c), int(i))

            all_decisions: list[tuple[int, str, str]] = []  # (image_id, decision, file_path)
            for stack_id, group in by_stack.items():
                if self._check_stop():
                    break
                sorted_group = sorted(group, key=sort_key)
                sorted_ids = [img["id"] for img in sorted_group]
                path_by_id = {img["id"]: img.get("file_path") or "" for img in sorted_group}
                classifications = classify_sorted_ids(sorted_ids, frac=cfg.pick_fraction)
                for img_id, decision in classifications.items():
                    path = path_by_id.get(img_id, "")
                    all_decisions.append((img_id, decision, path))

            # Stage 6: Persist to DB
            self._progress(progress_cb, 0.6, "Writing decisions to database...")
            db.batch_update_cull_decisions(all_decisions, policy_version=POLICY_VERSION)

            # Stage 7: Write to sidecars
            self._progress(progress_cb, 0.7, "Writing metadata...")
            sidecar_written = 0
            sidecar_errors = 0
            stack_id_by_img = {img["id"]: img.get("stack_id") for img in images}

            for img_id, decision, file_path in all_decisions:
                if self._check_stop():
                    break
                if not file_path:
                    continue
                try:
                    sid = stack_id_by_img.get(img_id)
                    stack_ok, pr_ok = write_selection_metadata(file_path, sid, decision)
                    if stack_ok and pr_ok:
                        sidecar_written += 1
                    else:
                        sidecar_errors += 1
                except Exception as e:
                    logger.warning("Sidecar write failed for %s: %s", file_path, e)
                    sidecar_errors += 1

            # Stage 8-9: Summary
            picked = sum(1 for _, d, _ in all_decisions if d == "pick")
            rejected = sum(1 for _, d, _ in all_decisions if d == "reject")
            neutral = sum(1 for _, d, _ in all_decisions if d == "neutral")
            n_stacks = len(by_stack)

            status = "completed"
            if self._check_stop():
                status = "stopped"

            return SelectionSummary(
                total_images=n_images,
                total_stacks=n_stacks,
                picked=picked,
                rejected=rejected,
                neutral=neutral,
                sidecar_written=sidecar_written,
                sidecar_errors=sidecar_errors,
                status=status,
            )

        except Exception as e:
            logger.exception("Selection run failed: %s", e)
            return SelectionSummary(
                0, 0, 0, 0, 0, 0, 0,
                status=f"error: {e}",
            )
