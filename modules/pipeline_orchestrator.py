import logging
import threading
from typing import Dict, List, Optional
from modules import db
from modules.phases import PhaseCode

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Manages sequential 'Run All Pending' execution across pipeline phases."""

    # Defines the order of operations for a full pipeline run
    PHASE_ORDER = [PhaseCode.SCORING, PhaseCode.CULLING, PhaseCode.KEYWORDS]

    def __init__(self, scoring_runner, tagging_runner, selection_runner):
        self._runners = {
            PhaseCode.SCORING: scoring_runner,
            PhaseCode.KEYWORDS: tagging_runner,
            PhaseCode.CULLING: selection_runner,
        }
        self.folder_path: Optional[str] = None
        self.pending_phases: List[PhaseCode] = []
        self.current_phase: Optional[PhaseCode] = None
        self._active: bool = False
        self._lock = threading.Lock()

    def start(self, folder_path: str) -> str:
        """Starts the pipeline for the given folder."""
        with self._lock:
            if self._active:
                return "Pipeline is already running."

            self.folder_path = folder_path

            # get_folder_phase_summary returns a LIST of dicts:
            #   [{code, name, sort_order, status, done_count, total_count}, ...]
            summary_list = db.get_folder_phase_summary(folder_path)
            summary_by_code = {item["code"]: item for item in summary_list}

            # Build ordered list of pending (non-done) phases
            self.pending_phases = []
            for phase in self.PHASE_ORDER:
                phase_info = summary_by_code.get(phase.value)
                if phase_info is None or phase_info.get("status") != "done":
                    self.pending_phases.append(phase)

            if not self.pending_phases:
                self.folder_path = None
                return "All phases are already complete."

            self._active = True
            return self._start_next_phase()

    def _start_next_phase(self) -> str:
        """Internal helper to start the next pending phase. Caller must hold self._lock."""
        if not self.pending_phases:
            self._active = False
            self.current_phase = None
            self.folder_path = None
            return "Pipeline run finished."

        self.current_phase = self.pending_phases.pop(0)
        runner = self._runners.get(self.current_phase)

        if not runner:
            self._active = False
            return f"Error: No runner found for phase {self.current_phase}"

        logger.info(f"Pipeline: Starting phase {self.current_phase.value} for folder {self.folder_path}")

        try:
            job_id = db.create_job(self.folder_path, phase_code=self.current_phase.value)
            # All runners use start_batch(input_path, job_id, **kwargs)
            msg = runner.start_batch(self.folder_path, job_id)
            return f"Started {self.current_phase.value}: {msg}"
        except Exception as e:
            self._active = False
            logger.error(f"Pipeline: Failed to start phase {self.current_phase.value}: {e}")
            return f"Failed to start {self.current_phase.value}: {str(e)}"

    def on_tick(self) -> Optional[Dict]:
        """Called by the main UI timer. Checks if current runner finished and starts next."""
        with self._lock:
            if not self._active:
                return None

            if self.current_phase:
                runner = self._runners.get(self.current_phase)
                if runner:
                    is_running, log, msg, current, total = runner.get_status()
                    if not is_running:
                        logger.info(f"Pipeline: Phase {self.current_phase.value} finished.")
                        self._start_next_phase()

            return self.get_status()

    def stop(self) -> str:
        """Stops the current runner and clears the pipeline queue."""
        with self._lock:
            self._active = False
            self.pending_phases.clear()

            if self.current_phase:
                runner = self._runners.get(self.current_phase)
                if runner:
                    runner.stop()
                self.current_phase = None
                self.folder_path = None
                return "Pipeline stopped."

            return "Pipeline wasn't running."

    def is_active(self) -> bool:
        """Returns True if the orchestrator is actively managing a pipeline run."""
        with self._lock:
            return self._active

    def get_status(self) -> Dict:
        """Returns the orchestrator's state. Caller should hold lock or accept stale reads."""
        return {
            "active": self._active,
            "folder_path": self.folder_path,
            "current_phase": self.current_phase.value if self.current_phase else None,
            "pending_phases": [p.value for p in self.pending_phases],
        }
