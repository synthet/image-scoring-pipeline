"""
DbClientHttp — HTTP-based implementation for microservice mode.

Calls a remote DB API service instead of accessing the database directly.
Used when scoring/pipeline runs as a separate service from the database.

Configuration:
    config.json → database.api_url (e.g., "http://localhost:7861")
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# Default timeout for HTTP requests (seconds)
_DEFAULT_TIMEOUT = 30
_LONG_TIMEOUT = 120  # For batch operations


class DbClientHttp:
    """Calls a remote DB API service for all database operations."""

    def __init__(self, base_url: str = "http://localhost:7861"):
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})
        logger.info("DbClientHttp initialized: %s", self.base_url)

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _get(self, path: str, params: Optional[dict] = None, timeout: int = _DEFAULT_TIMEOUT) -> Any:
        resp = self._session.get(self._url(path), params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: Any = None, timeout: int = _DEFAULT_TIMEOUT) -> Any:
        resp = self._session.post(self._url(path), json=data, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def _patch(self, path: str, data: Any = None, timeout: int = _DEFAULT_TIMEOUT) -> Any:
        resp = self._session.patch(self._url(path), json=data, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def _put(self, path: str, data: Any = None, timeout: int = _DEFAULT_TIMEOUT) -> Any:
        resp = self._session.put(self._url(path), json=data, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def _delete(self, path: str, params: Optional[dict] = None, timeout: int = _DEFAULT_TIMEOUT) -> Any:
        resp = self._session.delete(self._url(path), params=params, timeout=timeout)
        resp.raise_for_status()
        if resp.content:
            return resp.json()
        return None

    # =========================================================================
    # Image CRUD
    # =========================================================================

    def get_image_details(self, file_path: str) -> Optional[Dict[str, Any]]:
        try:
            return self._get("/api/db/images/by-path", params={"file_path": file_path})
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            raise

    def get_image_by_hash(self, image_hash: str) -> Optional[Dict[str, Any]]:
        try:
            return self._get(f"/api/db/images/by-hash/{image_hash}")
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            raise

    def upsert_image(self, job_id: int, result: Dict[str, Any], **kwargs) -> None:
        body: Dict[str, Any] = {"job_id": job_id, "result": result}
        if "invalidate_agg" in kwargs:
            body["invalidate_agg"] = kwargs["invalidate_agg"]
        self._post("/api/db/images/upsert", body)

    def delete_image(self, file_path: str) -> None:
        self._delete("/api/db/images/by-path", params={"file_path": file_path}, timeout=_DEFAULT_TIMEOUT)

    def get_all_images(self, limit: int = -1) -> List[Any]:
        return self._get("/api/db/images", params={"limit": limit})

    def get_images_by_folder(self, folder_path: str) -> List[Any]:
        return self._get("/api/db/images", params={"folder_path": folder_path})

    def get_images_with_keyword(
        self, keyword: str, folder_path: Optional[str] = None, limit: int = -1
    ) -> List[Any]:
        params: dict = {"keyword": keyword, "limit": limit}
        if folder_path:
            params["folder_path"] = folder_path
        return self._get("/api/db/images", params=params)

    def get_incomplete_records(self) -> List[Any]:
        return self._get("/api/db/images/incomplete")

    def update_image_field(self, image_id: int, field: str, value: Any) -> bool:
        result = self._patch(f"/api/db/images/{image_id}", {field: value})
        return result.get("success", True)

    def update_image_fields_batch(self, updates: List[Tuple[int, Dict[str, Any]]]) -> None:
        self._post("/api/db/images/batch-update", {"updates": [
            {"image_id": uid, "fields": fields} for uid, fields in updates
        ]}, timeout=_LONG_TIMEOUT)

    def update_image_embeddings_batch(self, updates: List[Any]) -> None:
        self._post("/api/db/images/batch-embeddings", {"updates": updates}, timeout=_LONG_TIMEOUT)

    def update_image_uuid(self, image_id: int, uuid: str) -> None:
        self._patch(f"/api/db/images/{image_id}", {"image_uuid": uuid})

    def register_image_path(self, image_id: int, path: str) -> None:
        self._post(f"/api/db/images/{image_id}/paths", {"path": path})

    def get_image_embeddings_batch(self, image_ids: List[int]) -> List[Any]:
        return self._post("/api/db/images/embeddings", {"image_ids": image_ids}, timeout=_LONG_TIMEOUT)

    def get_images_for_tag_propagation(
        self, folder_path: Optional[str] = None
    ) -> Tuple[List[Any], List[Any]]:
        params = {"folder_path": folder_path} if folder_path else {}
        result = self._get("/api/db/images/tag-propagation", params=params)
        return result.get("untagged", []), result.get("tagged", [])

    def get_all_paths(self, image_id: int) -> List[str]:
        return self._get(f"/api/db/images/{image_id}/paths")

    def get_resolved_path(self, image_id: int, verified_only: bool = False) -> Optional[str]:
        result = self._get(f"/api/db/images/{image_id}/resolved-path",
                           params={"verified_only": verified_only})
        return result.get("path")

    # =========================================================================
    # Phase tracking
    # =========================================================================

    def get_image_phase_statuses(self, image_id: int) -> Dict[str, Any]:
        return self._get(f"/api/db/images/{image_id}/phases")

    def get_image_phase_status(self, image_id: int, phase_code: str) -> Optional[Dict[str, Any]]:
        try:
            return self._get(f"/api/db/images/{image_id}/phases/{phase_code}")
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            raise

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
        code = phase_code.value if hasattr(phase_code, "value") else str(phase_code)
        st = status.value if hasattr(status, "value") else str(status)
        self._put(f"/api/db/images/{image_id}/phases/{code}", {
            "status": st,
            "app_version": app_version,
            "executor_version": executor_version,
            "job_id": job_id,
            "error": error,
        })

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
        payload = {"input_path": input_path, "job_type": job_type, "status": status}
        if runner_state:
            payload["runner_state"] = runner_state
        payload.update(kwargs)
        result = self._post("/api/db/jobs", payload)
        return result["job_id"]

    def update_job_status(
        self,
        job_id: int,
        status: str,
        log: Optional[str] = None,
        runner_state: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        payload: dict = {"status": status}
        if log is not None:
            payload["log"] = log
        if runner_state is not None:
            payload["runner_state"] = runner_state
        payload.update(kwargs)
        self._patch(f"/api/db/jobs/{job_id}", payload)

    def get_job_by_id(self, job_id: int) -> Optional[Dict[str, Any]]:
        try:
            return self._get(f"/api/db/jobs/{job_id}")
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            raise

    def get_job_phases(self, job_id: int) -> List[Dict[str, Any]]:
        return self._get(f"/api/db/jobs/{job_id}/phases")

    def create_job_phases(self, job_id: int, phases: List[Any]) -> None:
        self._post(f"/api/db/jobs/{job_id}/phases", {"phases": phases})

    def set_job_phase_state(self, job_id: int, phase_code: str, state: str) -> None:
        self._put(f"/api/db/jobs/{job_id}/phases/{phase_code}", {"state": state})

    def set_job_execution_cursor(self, job_id: int, cursor: str) -> None:
        self._patch(f"/api/db/jobs/{job_id}", {"execution_cursor": cursor})

    def get_queued_jobs(self) -> List[Dict[str, Any]]:
        return self._get("/api/db/jobs", params={"status": "queued"})

    def dequeue_next_job(self) -> Optional[Dict[str, Any]]:
        result = self._post("/api/db/jobs/dequeue")
        return result if result else None

    def enqueue_job(self, **kwargs: Any) -> int:
        result = self._post("/api/db/jobs/enqueue", kwargs)
        return result["job_id"]

    def get_interrupted_jobs(self) -> List[Dict[str, Any]]:
        return self._get("/api/db/jobs", params={"status": "interrupted"})

    def recover_running_jobs(self) -> None:
        self._post("/api/db/jobs/recover")

    def get_next_running_job_phase(self, job_id: int) -> Optional[Dict[str, Any]]:
        try:
            return self._get(f"/api/db/jobs/{job_id}/next-phase")
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            raise

    def get_all_phases(self) -> List[Any]:
        return self._get("/api/db/phases")

    # =========================================================================
    # Folder operations
    # =========================================================================

    def get_all_folders(self) -> List[Any]:
        return self._get("/api/db/folders")

    def is_folder_scored(self, folder_path: str) -> bool:
        result = self._get("/api/db/folders/scored", params={"folder_path": folder_path})
        return result.get("scored", False)

    def check_and_update_folder_status(self, folder_path: str) -> None:
        self._post("/api/db/folders/update-status", {"folder_path": folder_path})

    def check_and_update_folder_keywords_status(self, folder_path: str) -> bool:
        result = self._post("/api/db/folders/update-keywords-status", {"folder_path": folder_path})
        return result.get("updated", False)

    def get_or_create_folder(self, folder_path: str) -> int:
        result = self._post("/api/db/folders/get-or-create", {"folder_path": folder_path})
        return result["folder_id"]

    def sync_folder_to_db(self, folder_path: str) -> None:
        self._post("/api/db/folders/sync", {"folder_path": folder_path})

    def get_folder_phase_summary(self, folder_path: str) -> Dict[str, Any]:
        return self._get("/api/db/folders/phase-summary", params={"folder_path": folder_path})

    def set_folder_phase_status(self, folder_path: str, phase: str, status: str) -> None:
        self._put("/api/db/folders/phase-status", {
            "folder_path": folder_path, "phase": phase, "status": status
        })

    def get_clustered_folders(self) -> List[Any]:
        return self._get("/api/db/folders/clustered")

    def mark_folder_clustered(self, folder_path: str) -> None:
        self._post("/api/db/folders/mark-clustered", {"folder_path": folder_path})

    # =========================================================================
    # Stacks / clustering
    # =========================================================================

    def get_stack_count(self) -> int:
        result = self._get("/api/db/stacks/count")
        return result.get("count", 0)

    def get_stack_count_for_folder(self, folder_path: str) -> int:
        result = self._get("/api/db/stacks/count", params={"folder_path": folder_path})
        return result.get("count", 0)

    def get_stack_ids_for_image_ids(self, image_ids: List[int]) -> Dict[int, int]:
        result = self._post("/api/db/stacks/by-image-ids", {"image_ids": image_ids})
        # JSON keys are strings; convert back to int
        return {int(k): v for k, v in result.items()}

    def create_stacks_batch(self, stacks: List[Any]) -> None:
        self._post("/api/db/stacks/batch-create", {"stacks": stacks}, timeout=_LONG_TIMEOUT)

    def clear_stacks_in_folder(self, folder_path: str) -> None:
        self._post("/api/db/stacks/clear", {"folder_path": folder_path})

    def clear_cluster_progress(self) -> None:
        self._post("/api/db/stacks/clear-progress")

    # =========================================================================
    # Culling sessions
    # =========================================================================

    def create_culling_session(self, folder_path: str, mode: str) -> Optional[int]:
        result = self._post("/api/db/culling/sessions", {"folder_path": folder_path, "mode": mode})
        return result.get("session_id")

    def get_culling_session(self, session_id: int) -> Optional[Dict[str, Any]]:
        try:
            return self._get(f"/api/db/culling/sessions/{session_id}")
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            raise

    def update_culling_session(self, session_id: int, **kwargs: Any) -> None:
        self._patch(f"/api/db/culling/sessions/{session_id}", kwargs)

    def add_images_to_culling_session(
        self, session_id: int, image_ids: List[int], group_assignments: Dict[int, int]
    ) -> bool:
        # JSON keys must be strings
        ga = {str(k): v for k, v in group_assignments.items()}
        result = self._post(f"/api/db/culling/sessions/{session_id}/images", {
            "image_ids": image_ids, "group_assignments": ga,
        })
        return result.get("success", True)

    def get_session_groups(self, session_id: int) -> List[Dict[str, Any]]:
        return self._get(f"/api/db/culling/sessions/{session_id}/groups")

    def get_session_picks(
        self, session_id: int, decision_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        params = {}
        if decision_filter:
            params["decision_filter"] = decision_filter
        return self._get(f"/api/db/culling/sessions/{session_id}/picks", params=params)

    def get_session_stats(self, session_id: int) -> Dict[str, Any]:
        return self._get(f"/api/db/culling/sessions/{session_id}/stats")

    def set_pick_decision(
        self, session_id: int, image_id: int, decision: str, auto_suggested: bool = False
    ) -> None:
        self._put(f"/api/db/culling/sessions/{session_id}/images/{image_id}/decision", {
            "decision": decision, "auto_suggested": auto_suggested,
        })

    def set_best_in_group(self, session_id: int, image_id: int, group_id: int) -> None:
        self._put(f"/api/db/culling/sessions/{session_id}/groups/{group_id}/best", {
            "image_id": image_id,
        })

    def batch_update_cull_decisions(self, updates: List[Any]) -> None:
        self._post("/api/db/culling/batch-decisions", {"updates": updates})

    # =========================================================================
    # Utilities
    # =========================================================================

    def backup_database(self) -> None:
        self._post("/api/db/backup")

    def generate_image_uuid(self, metadata: Optional[Dict[str, Any]]) -> str:
        result = self._post("/api/db/utils/generate-uuid", {"metadata": metadata or {}})
        return result["uuid"]

    def get_db(self) -> Any:
        raise NotImplementedError(
            "get_db() is not available in HTTP mode. "
            "Use higher-level DbClient methods instead of raw connections."
        )
