"""
DbClientProtocol — defines the abstract interface for all database operations
used by scoring/pipeline/tagging/clustering/culling modules.

This is a typing.Protocol (structural subtyping) so implementations don't need
to inherit from it; they just need to have matching method signatures.

Grouped by domain:
    - Image CRUD
    - Phase tracking
    - Job management
    - Folder operations
    - Stacks / clustering
    - Culling sessions
    - Selection / embeddings
    - Utilities (backup, UUID generation)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable


@runtime_checkable
class DbClientProtocol(Protocol):
    """Structural protocol for database client implementations."""

    # =========================================================================
    # Image CRUD
    # =========================================================================

    def get_image_details(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get full image record by file_path."""
        ...

    def get_image_by_hash(self, image_hash: str) -> Optional[Dict[str, Any]]:
        """Get image record by content hash."""
        ...

    def upsert_image(
        self,
        job_id: int,
        result: Dict[str, Any],
        *,
        invalidate_agg: bool = True,
        dirty_folder_ids: Any = None,
    ) -> None:
        """Insert or update an image record from scoring results."""
        ...

    def delete_image(self, file_path: str) -> None:
        """Remove an image record by file_path."""
        ...

    def get_all_images(self, limit: int = -1) -> List[Any]:
        """Get all image records, optionally limited."""
        ...

    def get_images_by_folder(self, folder_path: str) -> List[Any]:
        """Get image records belonging to a folder."""
        ...

    def get_images_with_keyword(
        self, keyword: str, folder_path: Optional[str] = None, limit: int = -1
    ) -> List[Any]:
        """Get images that have a specific keyword."""
        ...

    def get_incomplete_records(self) -> List[Any]:
        """Get image records with missing scores."""
        ...

    def update_image_field(self, image_id: int, field: str, value: Any) -> bool:
        """Update a single field on an image record."""
        ...

    def update_image_fields_batch(self, updates: List[Tuple[int, Dict[str, Any]]]) -> None:
        """Batch-update multiple fields on multiple image records."""
        ...

    def update_image_embeddings_batch(self, updates: List[Any]) -> None:
        """Batch-update image embeddings."""
        ...

    def update_image_uuid(self, image_id: int, uuid: str) -> None:
        """Set the UUID for an image."""
        ...

    def register_image_path(self, image_id: int, path: str) -> None:
        """Register an additional file path for an image."""
        ...

    def get_image_embeddings_batch(self, image_ids: List[int]) -> List[Any]:
        """Get embeddings for a batch of image IDs."""
        ...

    def get_images_for_tag_propagation(
        self, folder_path: Optional[str] = None
    ) -> Tuple[List[Any], List[Any]]:
        """Get untagged and tagged images for tag propagation."""
        ...

    def get_all_paths(self, image_id: int) -> List[str]:
        """Get all file paths associated with an image."""
        ...

    def get_resolved_path(self, image_id: int, verified_only: bool = False) -> Optional[str]:
        """Get the best resolved file path for an image."""
        ...

    # =========================================================================
    # Phase tracking
    # =========================================================================

    def get_image_phase_statuses(self, image_id: int) -> Dict[str, Any]:
        """Get all phase statuses for an image."""
        ...

    def get_image_phase_status(self, image_id: int, phase_code: str) -> Optional[Dict[str, Any]]:
        """Get status for a specific phase on an image."""
        ...

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
        """Set phase status for an image."""
        ...

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
        """Create a new job record. Returns job ID."""
        ...

    def update_job_status(
        self,
        job_id: int,
        status: str,
        log: Optional[str] = None,
        runner_state: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Update job status."""
        ...

    def get_job_by_id(self, job_id: int) -> Optional[Dict[str, Any]]:
        """Get a job record by ID."""
        ...

    def get_job_phases(self, job_id: int) -> List[Dict[str, Any]]:
        """Get phase records for a job."""
        ...

    def create_job_phases(self, job_id: int, phases: List[Any]) -> None:
        """Create phase records for a job."""
        ...

    def set_job_phase_state(self, job_id: int, phase_code: str, state: str) -> None:
        """Update the state of a specific job phase."""
        ...

    def set_job_execution_cursor(self, job_id: int, cursor: str) -> None:
        """Set the execution cursor for a job."""
        ...

    def get_queued_jobs(self) -> List[Dict[str, Any]]:
        """Get all queued jobs."""
        ...

    def dequeue_next_job(self) -> Optional[Dict[str, Any]]:
        """Dequeue the next job to run."""
        ...

    def enqueue_job(self, **kwargs: Any) -> int:
        """Enqueue a new job. Returns job ID."""
        ...

    def get_interrupted_jobs(self) -> List[Dict[str, Any]]:
        """Get jobs that were interrupted."""
        ...

    def recover_running_jobs(self) -> None:
        """Recover jobs that were left in running state."""
        ...

    def get_next_running_job_phase(self, job_id: int) -> Optional[Dict[str, Any]]:
        """Get the next phase to execute for a running job."""
        ...

    def get_all_phases(self) -> List[Any]:
        """Get all phase definitions."""
        ...

    # =========================================================================
    # Folder operations
    # =========================================================================

    def get_all_folders(self) -> List[Any]:
        """Get all folder records."""
        ...

    def is_folder_scored(self, folder_path: str) -> bool:
        """Check if a folder has been fully scored."""
        ...

    def check_and_update_folder_status(self, folder_path: str) -> None:
        """Check and update folder completion status."""
        ...

    def check_and_update_folder_keywords_status(self, folder_path: str) -> bool:
        """Check and update folder keywords completion status."""
        ...

    def get_or_create_folder(self, folder_path: str) -> int:
        """Get or create a folder record. Returns folder ID."""
        ...

    def sync_folder_to_db(self, folder_path: str) -> None:
        """Sync a folder's contents to the database."""
        ...

    def get_folder_phase_summary(self, folder_path: str) -> Dict[str, Any]:
        """Get phase status summary for a folder."""
        ...

    def set_folder_phase_status(self, folder_path: str, phase: str, status: str) -> None:
        """Set phase status for a folder."""
        ...

    def get_clustered_folders(self) -> List[Any]:
        """Get folders that have been clustered."""
        ...

    def mark_folder_clustered(self, folder_path: str) -> None:
        """Mark a folder as clustered."""
        ...

    # =========================================================================
    # Stacks / clustering
    # =========================================================================

    def get_stack_count(self) -> int:
        """Get total stack count."""
        ...

    def get_stack_count_for_folder(self, folder_path: str) -> int:
        """Get stack count for a specific folder."""
        ...

    def get_stack_ids_for_image_ids(self, image_ids: List[int]) -> Dict[int, int]:
        """Get stack ID assignments for a list of image IDs."""
        ...

    def create_stacks_batch(self, stacks: List[Any]) -> None:
        """Create multiple stacks in batch."""
        ...

    def clear_stacks_in_folder(self, folder_path: str) -> None:
        """Remove all stacks in a folder."""
        ...

    def clear_cluster_progress(self) -> None:
        """Clear clustering progress state."""
        ...

    # =========================================================================
    # Culling sessions
    # =========================================================================

    def create_culling_session(self, folder_path: str, mode: str) -> Optional[int]:
        """Create a new culling session. Returns session ID."""
        ...

    def get_culling_session(self, session_id: int) -> Optional[Dict[str, Any]]:
        """Get a culling session by ID."""
        ...

    def update_culling_session(self, session_id: int, **kwargs: Any) -> None:
        """Update culling session attributes."""
        ...

    def add_images_to_culling_session(
        self, session_id: int, image_ids: List[int], group_assignments: Dict[int, int]
    ) -> bool:
        """Add images to a culling session with group assignments."""
        ...

    def get_session_groups(self, session_id: int) -> List[Dict[str, Any]]:
        """Get groups in a culling session."""
        ...

    def get_session_picks(
        self, session_id: int, decision_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get pick decisions for a culling session."""
        ...

    def get_session_stats(self, session_id: int) -> Dict[str, Any]:
        """Get statistics for a culling session."""
        ...

    def set_pick_decision(
        self, session_id: int, image_id: int, decision: str, auto_suggested: bool = False
    ) -> None:
        """Set pick/reject decision for an image in a culling session."""
        ...

    def set_best_in_group(self, session_id: int, image_id: int, group_id: int) -> None:
        """Mark an image as the best in its group."""
        ...

    def batch_update_cull_decisions(self, updates: List[Any]) -> None:
        """Batch-update culling decisions."""
        ...

    # =========================================================================
    # Utilities
    # =========================================================================

    def backup_database(self) -> None:
        """Create a database backup."""
        ...

    def generate_image_uuid(self, metadata: Optional[Dict[str, Any]]) -> str:
        """Generate a UUID for an image based on metadata."""
        ...

    def get_db(self) -> Any:
        """Get a raw database connection.

        Only available in local mode. HTTP mode should raise NotImplementedError.
        Callers using this must be prepared to handle the exception or should
        be refactored to use higher-level methods.
        """
        ...
