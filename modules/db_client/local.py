"""
DbClientLocal — Local implementation that delegates to modules.db.

Used in monolith mode where everything runs in one process.
Each method is a thin wrapper around the corresponding db.py function.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class DbClientLocal:
    """Delegates all database calls to the local modules.db module."""

    def __init__(self):
        # Lazy import to avoid circular imports at module load time
        self._db = None

    @property
    def db(self):
        if self._db is None:
            from modules import db
            self._db = db
        return self._db

    # =========================================================================
    # Image CRUD
    # =========================================================================

    def get_image_details(self, file_path: str) -> Optional[Dict[str, Any]]:
        return self.db.get_image_details(file_path)

    def get_image_by_hash(self, image_hash: str) -> Optional[Dict[str, Any]]:
        return self.db.get_image_by_hash(image_hash)

    def upsert_image(
        self,
        job_id: int,
        result: Dict[str, Any],
        *,
        invalidate_agg: bool = True,
        dirty_folder_ids=None,
    ) -> None:
        self.db.upsert_image(
            job_id,
            result,
            invalidate_agg=invalidate_agg,
            dirty_folder_ids=dirty_folder_ids,
        )

    def delete_image(self, file_path: str) -> None:
        self.db.delete_image(file_path)

    def get_all_images(self, limit: int = -1) -> List[Any]:
        return self.db.get_all_images(limit=limit)

    def get_images_by_folder(self, folder_path: str) -> List[Any]:
        return self.db.get_images_by_folder(folder_path)

    def get_images_with_keyword(
        self, keyword: str, folder_path: Optional[str] = None, limit: int = -1
    ) -> List[Any]:
        return self.db.get_images_with_keyword(keyword, folder_path=folder_path, limit=limit)

    def get_incomplete_records(self) -> List[Any]:
        return self.db.get_incomplete_records()

    def update_image_field(self, image_id: int, field: str, value: Any) -> bool:
        return self.db.update_image_field(image_id, field, value)

    def update_image_fields_batch(self, updates: List[Tuple[int, Dict[str, Any]]]) -> None:
        self.db.update_image_fields_batch(updates)

    def update_image_embeddings_batch(self, updates: List[Any]) -> None:
        self.db.update_image_embeddings_batch(updates)

    def update_image_uuid(self, image_id: int, uuid: str) -> None:
        self.db.update_image_uuid(image_id, uuid)

    def register_image_path(self, image_id: int, path: str) -> None:
        self.db.register_image_path(image_id, path)

    def get_image_embeddings_batch(self, image_ids: List[int]) -> List[Any]:
        return self.db.get_image_embeddings_batch(image_ids)

    def get_images_for_tag_propagation(
        self, folder_path: Optional[str] = None
    ) -> Tuple[List[Any], List[Any]]:
        return self.db.get_images_for_tag_propagation(folder_path=folder_path)

    def get_all_paths(self, image_id: int) -> List[str]:
        return self.db.get_all_paths(image_id)

    def get_resolved_path(self, image_id: int, verified_only: bool = False) -> Optional[str]:
        return self.db.get_resolved_path(image_id, verified_only=verified_only)

    # =========================================================================
    # Phase tracking
    # =========================================================================

    def get_image_phase_statuses(self, image_id: int) -> Dict[str, Any]:
        return self.db.get_image_phase_statuses(image_id)

    def get_image_phase_status(self, image_id: int, phase_code: str) -> Optional[Dict[str, Any]]:
        return self.db.get_image_phase_status(image_id, phase_code)

    def set_image_phase_status(
        self,
        image_id: int,
        phase_code: Any,
        status: Any,
        *,
        app_version: Optional[str] = None,
        executor_version: Optional[str] = None,
        job_id: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        self.db.set_image_phase_status(
            image_id,
            phase_code,
            status,
            app_version=app_version,
            executor_version=executor_version,
            job_id=job_id,
            error=error,
        )

    # =========================================================================
    # Job management
    # =========================================================================

    def create_job(
        self,
        input_path: str,
        job_type: str = "scoring",
        status: str = "queued",
        runner_state: Optional[str] = None,
        **kwargs: Any,
    ) -> int:
        return self.db.create_job(
            input_path, job_type=job_type, status=status, runner_state=runner_state, **kwargs
        )

    def update_job_status(
        self,
        job_id: int,
        status: str,
        log: Optional[str] = None,
        runner_state: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        self.db.update_job_status(job_id, status, log, runner_state=runner_state, **kwargs)

    def get_job_by_id(self, job_id: int) -> Optional[Dict[str, Any]]:
        return self.db.get_job_by_id(job_id)

    def get_job_phases(self, job_id: int) -> List[Dict[str, Any]]:
        return self.db.get_job_phases(job_id)

    def create_job_phases(self, job_id: int, phases: List[Any]) -> None:
        self.db.create_job_phases(job_id, phases)

    def set_job_phase_state(self, job_id: int, phase_code: str, state: str) -> None:
        self.db.set_job_phase_state(job_id, phase_code, state)

    def set_job_execution_cursor(self, job_id: int, cursor: str) -> None:
        self.db.set_job_execution_cursor(job_id, cursor)

    def get_queued_jobs(self) -> List[Dict[str, Any]]:
        return self.db.get_queued_jobs()

    def dequeue_next_job(self) -> Optional[Dict[str, Any]]:
        return self.db.dequeue_next_job()

    def enqueue_job(self, **kwargs: Any) -> int:
        return self.db.enqueue_job(**kwargs)

    def get_interrupted_jobs(self) -> List[Dict[str, Any]]:
        return self.db.get_interrupted_jobs()

    def recover_running_jobs(self) -> None:
        self.db.recover_running_jobs()

    def get_next_running_job_phase(self, job_id: int) -> Optional[Dict[str, Any]]:
        return self.db.get_next_running_job_phase(job_id)

    def get_all_phases(self) -> List[Any]:
        return self.db.get_all_phases()

    # =========================================================================
    # Folder operations
    # =========================================================================

    def get_all_folders(self) -> List[Any]:
        return self.db.get_all_folders()

    def is_folder_scored(self, folder_path: str) -> bool:
        return self.db.is_folder_scored(folder_path)

    def check_and_update_folder_status(self, folder_path: str) -> None:
        self.db.check_and_update_folder_status(folder_path)

    def check_and_update_folder_keywords_status(self, folder_path: str) -> bool:
        return self.db.check_and_update_folder_keywords_status(folder_path)

    def get_or_create_folder(self, folder_path: str) -> int:
        return self.db.get_or_create_folder(folder_path)

    def sync_folder_to_db(self, folder_path: str) -> None:
        self.db.sync_folder_to_db(folder_path)

    def get_folder_phase_summary(self, folder_path: str) -> Dict[str, Any]:
        return self.db.get_folder_phase_summary(folder_path)

    def set_folder_phase_status(self, folder_path: str, phase: str, status: str) -> None:
        self.db.set_folder_phase_status(folder_path, phase, status)

    def get_clustered_folders(self) -> List[Any]:
        return self.db.get_clustered_folders()

    def mark_folder_clustered(self, folder_path: str) -> None:
        self.db.mark_folder_clustered(folder_path)

    # =========================================================================
    # Stacks / clustering
    # =========================================================================

    def get_stack_count(self) -> int:
        return self.db.get_stack_count()

    def get_stack_count_for_folder(self, folder_path: str) -> int:
        return self.db.get_stack_count_for_folder(folder_path)

    def get_stack_ids_for_image_ids(self, image_ids: List[int]) -> Dict[int, int]:
        return self.db.get_stack_ids_for_image_ids(image_ids)

    def create_stacks_batch(self, stacks: List[Any]) -> None:
        self.db.create_stacks_batch(stacks)

    def clear_stacks_in_folder(self, folder_path: str) -> None:
        self.db.clear_stacks_in_folder(folder_path)

    def clear_cluster_progress(self) -> None:
        self.db.clear_cluster_progress()

    # =========================================================================
    # Culling sessions
    # =========================================================================

    def create_culling_session(self, folder_path: str, mode: str) -> Optional[int]:
        return self.db.create_culling_session(folder_path, mode)

    def get_culling_session(self, session_id: int) -> Optional[Dict[str, Any]]:
        return self.db.get_culling_session(session_id)

    def update_culling_session(self, session_id: int, **kwargs: Any) -> None:
        self.db.update_culling_session(session_id, **kwargs)

    def add_images_to_culling_session(
        self, session_id: int, image_ids: List[int], group_assignments: Dict[int, int]
    ) -> bool:
        return self.db.add_images_to_culling_session(session_id, image_ids, group_assignments)

    def get_session_groups(self, session_id: int) -> List[Dict[str, Any]]:
        return self.db.get_session_groups(session_id)

    def get_session_picks(
        self, session_id: int, decision_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return self.db.get_session_picks(session_id, decision_filter=decision_filter)

    def get_session_stats(self, session_id: int) -> Dict[str, Any]:
        return self.db.get_session_stats(session_id)

    def set_pick_decision(
        self, session_id: int, image_id: int, decision: str, auto_suggested: bool = False
    ) -> None:
        self.db.set_pick_decision(session_id, image_id, decision, auto_suggested=auto_suggested)

    def set_best_in_group(self, session_id: int, image_id: int, group_id: int) -> None:
        self.db.set_best_in_group(session_id, image_id, group_id)

    def batch_update_cull_decisions(self, updates: List[Any]) -> None:
        self.db.batch_update_cull_decisions(updates)

    # =========================================================================
    # Utilities
    # =========================================================================

    def backup_database(self) -> None:
        self.db.backup_database()

    def generate_image_uuid(self, metadata: Optional[Dict[str, Any]]) -> str:
        return self.db.generate_image_uuid(metadata)

    def get_db(self) -> Any:
        return self.db.get_db()
