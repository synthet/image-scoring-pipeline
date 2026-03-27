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
        bird_species_runner=None,
        indexing_runner=None,
        metadata_runner=None,
        poll_interval: float = 1.0,
    ):
        self.scoring_runner = scoring_runner
        self.tagging_runner = tagging_runner
        self.clustering_runner = clustering_runner
        self.selection_runner = selection_runner
        self.bird_species_runner = bird_species_runner
        self.indexing_runner = indexing_runner
        self.metadata_runner = metadata_runner
        self.poll_interval = max(0.2, float(poll_interval or 1.0))
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._dispatch_lock = threading.Lock()

    def set_runners(self, scoring_runner=None, tagging_runner=None, clustering_runner=None, selection_runner=None, bird_species_runner=None, indexing_runner=None, metadata_runner=None):
        self.scoring_runner = scoring_runner
        self.tagging_runner = tagging_runner
        self.clustering_runner = clustering_runner
        self.selection_runner = selection_runner
        self.bird_species_runner = bird_species_runner
        self.indexing_runner = indexing_runner
        self.metadata_runner = metadata_runner

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

    def tick_for_tests(self) -> None:
        """Single dispatch iteration for unit tests (does not require start())."""
        self._tick()

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
                    parsed = json.loads(raw_payload)
                    # Handle double-encoded JSON (string wrapped in extra quotes)
                    if isinstance(parsed, str):
                        parsed = json.loads(parsed)
                    payload = parsed if isinstance(parsed, dict) else {}
                except Exception:
                    logger.warning("Invalid queue payload for job %s", job.get("id"))

            started, err = self._start_job(job, payload)
            if not started:
                reason = err or "Dispatcher failed to start job (unknown reason)"
                logger.warning("Dispatcher: job %s failed to start: %s", job.get("id"), reason)
                db.update_job_status(job["id"], "failed", reason)

    def _start_job(self, job: Dict[str, Any], payload: Dict[str, Any]) -> tuple:
        """Try to start the job. Returns (success: bool, error_msg: str|None)."""
        phase = (job.get("job_type") or "").lower()
        job_id = int(job["id"])
        input_path = job.get("input_path")

        runner_map = {
            "indexing": ("indexing_runner", self.indexing_runner),
            "metadata": ("metadata_runner", self.metadata_runner),
            "score": ("scoring_runner", self.scoring_runner),
            "scoring": ("scoring_runner", self.scoring_runner),
            "tag": ("tagging_runner", self.tagging_runner),
            "tagging": ("tagging_runner", self.tagging_runner),
            "keywords": ("tagging_runner", self.tagging_runner),
            "cluster": ("clustering_runner", self.clustering_runner),
            "clustering": ("clustering_runner", self.clustering_runner),
            "selection": ("selection_runner", self.selection_runner),
            "culling": ("selection_runner", self.selection_runner),
            "bird_species": ("bird_species_runner", self.bird_species_runner),
            "bird-species": ("bird_species_runner", self.bird_species_runner),
        }

        entry = runner_map.get(phase)
        if entry is None:
            logger.warning("Unknown queued job_type=%s for job_id=%s", phase, job_id)
            return False, f"Unknown job type: {phase}"

        runner_name, runner = entry
        if not runner:
            return False, f"No runner available for '{phase}' (runner '{runner_name}' is not initialized)"

        try:
            result = self._dispatch_to_runner(phase, runner, job_id, input_path, payload)
        except Exception as exc:
            logger.exception("Runner %s raised during start for job %s", runner_name, job_id)
            return False, f"Runner '{runner_name}' raised: {exc}"

        if result == "Started":
            return True, None
        return False, f"Runner '{runner_name}' returned: {result}"

    def _dispatch_to_runner(self, phase: str, runner, job_id: int, input_path: str, payload: Dict[str, Any]) -> str:
        """Call the appropriate start_batch method on the runner. Returns the result string."""
        if phase == "indexing":
            return runner.start_batch(
                payload.get("input_path", input_path),
                job_id=job_id,
                skip_existing=bool(payload.get("skip_existing", True)),
                resolved_image_ids=payload.get("resolved_image_ids"),
            )

        if phase == "metadata":
            return runner.start_batch(
                payload.get("input_path", input_path),
                job_id=job_id,
                skip_existing=bool(payload.get("skip_existing", True)),
                resolved_image_ids=payload.get("resolved_image_ids"),
            )

        if phase in ("score", "scoring"):
            return runner.start_batch(
                payload.get("input_path", input_path),
                job_id,
                bool(payload.get("skip_existing", True)),
                resolved_image_ids=payload.get("resolved_image_ids"),
                target_phases=payload.get("target_phases"),
            )

        if phase in ("tag", "tagging", "keywords"):
            return runner.start_batch(
                payload.get("input_path", input_path),
                job_id=job_id,
                custom_keywords=payload.get("custom_keywords"),
                overwrite=bool(payload.get("overwrite", False)),
                generate_captions=bool(payload.get("generate_captions", False)),
                resolved_image_ids=payload.get("resolved_image_ids"),
            )

        if phase in ("cluster", "clustering"):
            return runner.start_batch(
                payload.get("input_path", input_path),
                threshold=payload.get("threshold"),
                time_gap=payload.get("time_gap"),
                force_rescan=bool(payload.get("force_rescan", False)),
                job_id=job_id,
                resolved_image_ids=payload.get("resolved_image_ids"),
            )

        if phase in ("selection", "culling"):
            return runner.start_batch(
                payload.get("input_path", input_path),
                job_id=job_id,
                force_rescan=bool(payload.get("force_rescan", False)),
            )

        if phase in ("bird_species", "bird-species"):
            return runner.start_batch(
                payload.get("input_path", input_path),
                job_id=job_id,
                candidate_species=payload.get("candidate_species"),
                threshold=float(payload.get("threshold", 0.1)),
                top_k=int(payload.get("top_k", 3)),
                overwrite=bool(payload.get("overwrite", False)),
                resolved_image_ids=payload.get("resolved_image_ids"),
            )

        return f"No dispatch handler for phase '{phase}'"

    def _runner_busy(self, runner) -> bool:
        return bool(runner and getattr(runner, "is_running", False))

    def _any_runner_busy(self) -> bool:
        return any([
            self._runner_busy(self.indexing_runner),
            self._runner_busy(self.metadata_runner),
            self._runner_busy(self.scoring_runner),
            self._runner_busy(self.tagging_runner),
            self._runner_busy(self.clustering_runner),
            self._runner_busy(self.selection_runner),
            self._runner_busy(self.bird_species_runner),
        ])

    def _get_active_runner(self) -> Optional[str]:
        if self._runner_busy(self.indexing_runner):
            return "indexing"
        if self._runner_busy(self.metadata_runner):
            return "metadata"
        if self._runner_busy(self.scoring_runner):
            return "scoring"
        if self._runner_busy(self.tagging_runner):
            return "tagging"
        if self._runner_busy(self.clustering_runner):
            return "clustering"
        if self._runner_busy(self.selection_runner):
            return "selection"
        if self._runner_busy(self.bird_species_runner):
            return "bird_species"
        return None
