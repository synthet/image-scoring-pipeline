import logging
import threading
from typing import Dict, List, Optional
from modules import db, config
from modules.phases import PhaseCode

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Manages sequential execution across pipeline phases using persisted job phase plans."""

    PHASE_ORDER = [PhaseCode.SCORING, PhaseCode.CULLING, PhaseCode.KEYWORDS]

    def __init__(self, scoring_runner, tagging_runner, selection_runner):
        self._runners = {
            PhaseCode.SCORING.value: scoring_runner,
            PhaseCode.KEYWORDS.value: tagging_runner,
            PhaseCode.CULLING.value: selection_runner,
        }
        self.folder_path: Optional[str] = None
        self.root_job_id: Optional[int] = None
        self.current_phase: Optional[str] = None
        self.current_phase_job_id: Optional[int] = None
        self._active: bool = False
        self._lock = threading.Lock()
        self._resume_policy: bool = bool(config.get_config_value("pipeline.auto_resume_interrupted", False))
        self._last_recovery_info: Dict = {}

    def start(self, folder_path: str) -> str:
        """Starts the pipeline for the given folder and persists phase plan."""
        with self._lock:
            if self._active:
                return "Pipeline is already running."

            self.folder_path = folder_path
            summary_list = db.get_folder_phase_summary(folder_path)
            summary_by_code = {item["code"]: item for item in summary_list}

            phase_plan: List[str] = []
            for phase in self.PHASE_ORDER:
                phase_info = summary_by_code.get(phase.value)
                if phase_info is None or phase_info.get("status") != "done":
                    phase_plan.append(phase.value)

            if not phase_plan:
                self.folder_path = None
                return "All phases are already complete."

            self.root_job_id = db.create_job(
                folder_path,
                job_type="pipeline",
                status="running",
                current_phase=None,
                next_phase_index=0,
                runner_state="running",
            )
            db.create_job_phases(self.root_job_id, phase_plan)
            self._active = True
            return self._start_next_phase()

    def _start_next_phase(self) -> str:
        """Start the current running phase from persisted job_phases."""
        if not self.root_job_id:
            self._active = False
            return "Pipeline is not initialized."

        next_phase = db.get_next_running_job_phase(self.root_job_id)
        if not next_phase:
            self._active = False
            self.current_phase = None
            self.current_phase_job_id = None
            if self.root_job_id:
                db.update_job_status(
                    self.root_job_id,
                    "completed",
                    runner_state="completed",
                    current_phase=None,
                    next_phase_index=len(self.PHASE_ORDER),
                )
            self.folder_path = None
            return "Pipeline run finished."

        self.current_phase = next_phase
        runner = self._runners.get(next_phase)
        if not runner:
            self._active = False
            db.set_job_phase_state(self.root_job_id, next_phase, "failed", error_message=f"No runner for phase '{next_phase}'")
            if self.root_job_id:
                db.update_job_status(self.root_job_id, "failed", runner_state="failed")
            return f"Error: No runner found for phase {next_phase}"

        logger.info("Pipeline: Starting phase %s for folder %s", next_phase, self.folder_path)
        try:
            phases = db.get_job_phases(self.root_job_id) or []
            phase_codes = [p.get("phase_code") for p in phases if p.get("phase_code")]
            if not phase_codes:
                phase_codes = [p.value for p in self.PHASE_ORDER]
            next_phase_index = next(
                (i for i, pc in enumerate(phase_codes) if pc == next_phase),
                len(phase_codes),
            )
            if self.root_job_id:
                db.set_job_execution_cursor(
                    self.root_job_id,
                    current_phase=next_phase,
                    next_phase_index=next_phase_index,
                    runner_state="running",
                )
            self.current_phase_job_id = db.create_job(
                self.folder_path,
                phase_code=next_phase,
                job_type=next_phase,
                status="running",
                current_phase=next_phase,
                next_phase_index=next_phase_index,
                runner_state="running",
            )
            msg = runner.start_batch(self.folder_path, self.current_phase_job_id)
            return f"Started {next_phase}: {msg}"
        except Exception as e:
            self._active = False
            db.set_job_phase_state(self.root_job_id, next_phase, "failed", error_message=str(e))
            if self.root_job_id:
                db.update_job_status(self.root_job_id, "failed", str(e), runner_state="failed")
            logger.error("Pipeline: Failed to start phase %s: %s", next_phase, e)
            return f"Failed to start {next_phase}: {str(e)}"

    def on_tick(self) -> Optional[Dict]:
        """Checks if current runner finished and advances to the next phase."""
        with self._lock:
            if not self._active:
                return None

            if self.current_phase:
                runner = self._runners.get(self.current_phase)
                if runner:
                    is_running, log, msg, current, total = runner.get_status()
                    if not is_running:
                        phase_job = db.get_job_by_id(self.current_phase_job_id) if self.current_phase_job_id else None
                        if phase_job and phase_job.get("status") == "failed":
                            db.set_job_phase_state(self.root_job_id, self.current_phase, "failed", error_message=phase_job.get("log"))
                            self._active = False
                        else:
                            db.set_job_phase_state(self.root_job_id, self.current_phase, "completed")
                            self._start_next_phase()

            return self.get_status()

    def stop(self) -> str:
        """Stops the current runner and marks active phase as failed."""
        with self._lock:
            self._active = False
            if self.current_phase:
                runner = self._runners.get(self.current_phase)
                if runner:
                    runner.stop()
                if self.root_job_id:
                    db.set_job_phase_state(self.root_job_id, self.current_phase, "failed", error_message="Pipeline stopped")
                    db.update_job_status(
                        self.root_job_id,
                        "canceled",
                        runner_state="canceled",
                        current_phase=self.current_phase,
                    )
                self.current_phase = None
                self.folder_path = None
                return "Pipeline stopped."

            return "Pipeline wasn't running."


    def recover_interrupted_jobs(self) -> Dict:
        """Recover stale running jobs and optionally auto-resume the pipeline."""
        folder_to_resume = None
        resumed_job_id = None

        with self._lock:
            recovered_job_ids = db.recover_running_jobs(mark_as="interrupted")
            interrupted = db.get_interrupted_jobs(job_type="pipeline", limit=1)

            auto_resumed = False
            if self._resume_policy and interrupted and not self._active:
                job = interrupted[0]
                folder = job.get("input_path")
                if folder:
                    logger.info("Pipeline: Auto-resume interrupted orchestrator job %s for %s", job.get("id"), folder)
                    auto_resumed = True
                    resumed_job_id = job.get("id")
                    folder_to_resume = folder

            info = {
                "recovered_running_jobs": recovered_job_ids,
                "interrupted_pipeline_jobs": [j.get("id") for j in interrupted],
                "auto_resume_enabled": self._resume_policy,
                "auto_resumed": auto_resumed,
                "resumed_from_job_id": resumed_job_id,
            }
            self._last_recovery_info = info

        if folder_to_resume:
            # Start a fresh run from folder summary state; keep historical interrupted row.
            self.start(folder_to_resume)

        return info

    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def get_status(self) -> Dict:
        phases = db.get_job_phases(self.root_job_id) if self.root_job_id else []
        return {
            "active": self._active,
            "job_id": self.root_job_id,
            "folder_path": self.folder_path,
            "current_phase": self.current_phase,
            "phases": phases,
            "pending_phases": [p["phase_code"] for p in phases if p.get("state") == "pending"],
            "resume_policy_enabled": self._resume_policy,
            "recovery": self._last_recovery_info,
        }
