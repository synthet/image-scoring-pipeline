"""
SelectionRunner - Run/stop/status interface for the Selection tab.

Matches Scoring/Keywords runner contract for polling-based UI integration.
"""

import threading
from modules.selection import SelectionService, SelectionConfig
from modules import db
from modules.events import event_manager
from modules.phases import PhaseCode, PhaseStatus
from modules.phases_policy import explain_phase_run_decision
from modules.version import APP_VERSION


class SelectionRunner:
    """
    Runs Selection workflow in a background thread.
    Contract: start_batch, stop, get_status (running, log, status_msg, cur, tot)
    """

    def __init__(self):
        self._service = SelectionService()
        self._lock = threading.Lock()
        self._is_running = False
        self._log_history: list[str] = []
        self._status_message = "Idle"
        self._current_count = 0
        self._total_count = 0
        self._thread: threading.Thread | None = None

    def get_status(self) -> tuple[bool, str, str, int, int]:
        """Returns (is_running, log_text, status_message, current, total)."""
        with self._lock:
            log_text = "\n".join(self._log_history)
            return (
                self._is_running,
                log_text,
                self._status_message,
                self._current_count,
                self._total_count,
            )

    def start_batch(self, input_path: str, job_id: int = None, force_rescan: bool = False) -> str:
        """Starts Selection in a background thread. Non-blocking."""
        with self._lock:
            if self._is_running:
                return "Error: Already running."

            self._is_running = True
            self._log_history = []
            self._status_message = "Starting..."
            self._current_count = 0
            self._total_count = 0

        if job_id is None:
            job_id = db.create_job(input_path or "ALL_IMAGES_SELECTION")

        def target():
            self._run_internal(input_path, force_rescan, job_id=job_id)
            with self._lock:
                self._is_running = False

        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()
        return "Started"

    def _run_internal(self, input_path: str, force_rescan: bool, job_id: int = None):
        
        def log(msg: str):
            with self._lock:
                self._log_history.append(msg)

        def progress_cb(pct: float, msg: str):
            with self._lock:
                self._status_message = msg
                self._total_count = 100
                self._current_count = int(pct * 100)
                
            if job_id:
                event_manager.broadcast_threadsafe("job_progress", {
                    "job_id": job_id,
                    "current": self._current_count,
                    "total": 100,
                    "message": msg
                })

        log("Starting Selection workflow...")
        log(f"Input: {input_path}")
        log("-" * 20)
        
        # Notify job started
        if job_id:
            db.update_job_status(job_id, "running")
            event_manager.broadcast_threadsafe("job_started", {
                "job_id": job_id, 
                "job_type": "selection", 
                "input_path": input_path
            })

        images = []
        images_for_phase = []
        try:
            images = db.get_images_by_folder(input_path)
            if images:
                for img in images:
                    decision = explain_phase_run_decision(
                        img['id'],
                        PhaseCode.CULLING,
                        current_executor_version="1.0.0",
                        force_run=force_rescan,
                    )
                    if decision['should_run']:
                        images_for_phase.append(img)
                        db.set_image_phase_status(
                            img['id'],
                            PhaseCode.CULLING,
                            PhaseStatus.RUNNING,
                            app_version=APP_VERSION,
                            executor_version="1.0.0",
                            job_id=job_id,
                        )
        except Exception as pe:
            log(f"Phase status pre-run update error: {pe}")

        skipped_by_policy = max(0, len(images) - len(images_for_phase))
        if skipped_by_policy:
            log(f"Policy gated {len(images_for_phase)} image(s); {skipped_by_policy} remain unchanged.")

        cfg = SelectionConfig(force_rescan=force_rescan)
        try:
            # SelectionService operates at folder scope; phase status updates are limited
            # to policy-eligible images tracked in images_for_phase.
            summary = self._service.run(input_path, cfg=cfg, progress_cb=progress_cb)

            # Phase D (Culling) — mark attempted images in the processed folder as done
            try:
                for img in images_for_phase:
                    db.set_image_phase_status(
                        img['id'],
                        PhaseCode.CULLING,
                        PhaseStatus.DONE,
                        app_version=APP_VERSION,
                        executor_version="1.0.0",
                        job_id=job_id,
                    )
            except Exception as pe:
                log(f"Phase status update error: {pe}")
        except Exception as e:
            for img in images_for_phase:
                db.set_image_phase_status(
                    img['id'],
                    PhaseCode.CULLING,
                    PhaseStatus.FAILED,
                    app_version=APP_VERSION,
                    executor_version="1.0.0",
                    job_id=job_id,
                    error=str(e),
                )
            raise

        with self._lock:
            self._status_message = summary.status
            self._current_count = 100
            self._total_count = 100
            
        if job_id:
            db.update_job_status(job_id, "completed")
            event_manager.broadcast_threadsafe("job_completed", {
                "job_id": job_id, 
                "status": "completed"
            })

        log(f"Total images: {summary.total_images}")
        log(f"Total stacks: {summary.total_stacks}")
        if summary.total_images:
            pct_pick = summary.picked / summary.total_images * 100
            pct_rej = summary.rejected / summary.total_images * 100
            log(f"Picked: {summary.picked} ({pct_pick:.1f}%)")
            log(f"Rejected: {summary.rejected} ({pct_rej:.1f}%)")
        else:
            log("Picked: 0, Rejected: 0")
        log(f"Neutral: {summary.neutral}")
        log(f"Sidecar written: {summary.sidecar_written}, errors: {summary.sidecar_errors}")
        log(f"Status: {summary.status}")

    def stop(self) -> None:
        """Request stop. Checked between stages."""
        self._service.stop()
