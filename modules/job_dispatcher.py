import json
import logging
import threading
from typing import Any, Dict, Optional

from modules import db

logger = logging.getLogger(__name__)


class JobDispatcher:
    """Dispatches queued jobs and ensures only one active job starts at a time."""

    def __init__(
        self,
        scoring_runner=None,
        tagging_runner=None,
        clustering_runner=None,
        selection_runner=None,
        poll_interval: float = 1.0,
    ):
        self.scoring_runner = scoring_runner
        self.tagging_runner = tagging_runner
        self.clustering_runner = clustering_runner
        self.selection_runner = selection_runner
        self.poll_interval = max(0.2, float(poll_interval or 1.0))
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._dispatch_lock = threading.Lock()

    def set_runners(self, scoring_runner=None, tagging_runner=None, clustering_runner=None, selection_runner=None):
        self.scoring_runner = scoring_runner
        self.tagging_runner = tagging_runner
        self.clustering_runner = clustering_runner
        self.selection_runner = selection_runner

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="job-dispatcher", daemon=True)
        self._thread.start()
        logger.info("JobDispatcher started")

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        logger.info("JobDispatcher stopped")

    def get_state(self) -> Dict[str, Any]:
        queue = db.get_queued_jobs(limit=200)
        active = self._get_active_runner()
        return {
            "queue": queue,
            "queue_size": len(queue),
            "active_runner": active,
            "is_dispatcher_running": bool(self._thread and self._thread.is_alive()),
        }

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as exc:
                logger.exception("JobDispatcher tick failed: %s", exc)
            self._stop_event.wait(self.poll_interval)

    def _tick(self):
        if self._any_runner_busy():
            return

        with self._dispatch_lock:
            if self._any_runner_busy():
                return
            job = db.dequeue_next_job()
            if not job:
                return

            payload = {}
            raw_payload = job.get("queue_payload")
            if raw_payload:
                try:
                    payload = json.loads(raw_payload)
                except Exception:
                    logger.warning("Invalid queue payload for job %s", job.get("id"))

            started = self._start_job(job, payload)
            if not started:
                db.update_job_status(job["id"], "failed", "Dispatcher failed to start job")

    def _start_job(self, job: Dict[str, Any], payload: Dict[str, Any]) -> bool:
        phase = (job.get("job_type") or "").lower()
        job_id = int(job["id"])
        input_path = job.get("input_path")

        if phase in ("score", "scoring"):
            if not self.scoring_runner:
                return False
            skip_existing = bool(payload.get("skip_existing", True))
            resolved_image_ids = payload.get("resolved_image_ids")
            target_phases = payload.get("target_phases")
            return self.scoring_runner.start_batch(
                payload.get("input_path", input_path),
                job_id,
                skip_existing,
                resolved_image_ids=resolved_image_ids,
                target_phases=target_phases,
            ) == "Started"

        if phase in ("tag", "tagging", "keywords"):
            if not self.tagging_runner:
                return False
            return self.tagging_runner.start_batch(
                payload.get("input_path", input_path),
                job_id=job_id,
                custom_keywords=payload.get("custom_keywords"),
                overwrite=bool(payload.get("overwrite", False)),
                generate_captions=bool(payload.get("generate_captions", False)),
                resolved_image_ids=payload.get("resolved_image_ids"),
            ) == "Started"

        if phase in ("cluster", "clustering"):
            if not self.clustering_runner:
                return False
            return self.clustering_runner.start_batch(
                payload.get("input_path", input_path),
                threshold=payload.get("threshold"),
                time_gap=payload.get("time_gap"),
                force_rescan=bool(payload.get("force_rescan", False)),
                job_id=job_id,
                resolved_image_ids=payload.get("resolved_image_ids"),
            ) == "Started"

        if phase in ("selection", "culling"):
            if not self.selection_runner:
                return False
            return self.selection_runner.start_batch(
                payload.get("input_path", input_path),
                job_id=job_id,
                force_rescan=bool(payload.get("force_rescan", False)),
            ) == "Started"

        logger.warning("Unknown queued job_type=%s for job_id=%s", phase, job_id)
        return False

    def _runner_busy(self, runner) -> bool:
        return bool(runner and getattr(runner, "is_running", False))

    def _any_runner_busy(self) -> bool:
        return any([
            self._runner_busy(self.scoring_runner),
            self._runner_busy(self.tagging_runner),
            self._runner_busy(self.clustering_runner),
            self._runner_busy(self.selection_runner),
        ])

    def _get_active_runner(self) -> Optional[str]:
        if self._runner_busy(self.scoring_runner):
            return "scoring"
        if self._runner_busy(self.tagging_runner):
            return "tagging"
        if self._runner_busy(self.clustering_runner):
            return "clustering"
        if self._runner_busy(self.selection_runner):
            return "selection"
        return None
