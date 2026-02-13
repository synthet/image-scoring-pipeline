"""
SelectionRunner - Run/stop/status interface for the Selection tab.

Matches Scoring/Keywords runner contract for polling-based UI integration.
"""

import threading
from modules.selection import SelectionService, SelectionConfig


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

    def start_batch(self, input_path: str, force_rescan: bool = False) -> str:
        """Starts Selection in a background thread. Non-blocking."""
        with self._lock:
            if self._is_running:
                return "Error: Already running."

            self._is_running = True
            self._log_history = []
            self._status_message = "Starting..."
            self._current_count = 0
            self._total_count = 0

        def target():
            self._run_internal(input_path, force_rescan)
            with self._lock:
                self._is_running = False

        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()
        return "Started"

    def _run_internal(self, input_path: str, force_rescan: bool):
        def log(msg: str):
            with self._lock:
                self._log_history.append(msg)

        def progress_cb(pct: float, msg: str):
            with self._lock:
                self._status_message = msg
                self._total_count = 100
                self._current_count = int(pct * 100)

        log("Starting Selection workflow...")
        log(f"Input: {input_path}")
        log("-" * 20)

        cfg = SelectionConfig(force_rescan=force_rescan)
        summary = self._service.run(input_path, cfg=cfg, progress_cb=progress_cb)

        with self._lock:
            self._status_message = summary.status
            self._current_count = 100
            self._total_count = 100

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
