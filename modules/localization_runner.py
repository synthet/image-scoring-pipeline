"""Background runner for the ``localization`` phase (#387, epic #345 stage 4 slice 1).

Same interface as ``BirdSpeciesRunner`` (``start_batch`` / ``get_status`` / ``stop``).
Per-image work lives in :func:`modules.localization.localize_image`; this module owns the
batch: the enablement guard, detector loading, the ``localization`` phase status, and the
job summary (AC-16).

Shadow isolation (AC-15): the only ``image_phase_status`` rows written here are
``localization`` rows, and the only other tables written are the localization run/region
tables and ``jobs`` bookkeeping.
"""

from __future__ import annotations

import logging
import os
import threading
from collections import Counter
from typing import Any

from modules import db
from modules.localization import (
    LOCALIZATION_RUNNER_VERSION,
    PHASE_STATUS_FOR_RUN,
    ImageOutcome,
    load_detector_context,
    localization_config,
    localize_image,
    max_regions_per_class,
)
from modules.localization_policy import fetch_run_history, repair_state
from modules.phases import PhaseCode, disabled_phase_submission_error
from modules.rendition import source_identity
from modules.scene_route import scene_route_settings

logger = logging.getLogger(__name__)

PHASE_CODE = PhaseCode.LOCALIZATION.value


class BatchMetrics:
    """Accumulates the AC-16 job summary."""

    def __init__(self) -> None:
        self.status_counts: Counter[str] = Counter()
        self.region_counts: Counter[int] = Counter()
        self.unchanged = 0
        self._decode: list[float] = []
        self._inference: list[float] = []

    def add(self, outcome: ImageOutcome) -> None:
        self.status_counts[outcome.status] += 1
        if outcome.unchanged:
            self.unchanged += 1
        elif outcome.status in ("detected", "no_detection"):
            self.region_counts[outcome.regions] += 1
        if outcome.decode_seconds is not None:
            self._decode.append(outcome.decode_seconds)
        if outcome.inference_seconds is not None:
            self._inference.append(outcome.inference_seconds)

    @staticmethod
    def _mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    def summary(self, peak_gpu_mib: float | None) -> dict[str, Any]:
        return {
            "status_counts": dict(self.status_counts),
            "unchanged_skipped": self.unchanged,
            # JSON object keys are strings; sorted so the report reads low -> high.
            "region_count_distribution": {
                str(k): self.region_counts[k] for k in sorted(self.region_counts)
            },
            "mean_decode_seconds": self._mean(self._decode),
            "mean_inference_seconds": self._mean(self._inference),
            "peak_gpu_memory_mib": peak_gpu_mib,
        }


def _reset_gpu_peak() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except Exception:  # noqa: BLE001 — metrics are best-effort
        pass


def _peak_gpu_mib() -> float | None:
    """Peak CUDA memory allocated since :func:`_reset_gpu_peak`, or ``None`` without CUDA."""
    try:
        import torch

        if torch.cuda.is_available():
            return round(torch.cuda.max_memory_allocated() / (1024 * 1024), 1)
    except Exception:  # noqa: BLE001
        pass
    return None


def _save_summary(job_id: int, summary: dict[str, Any]) -> None:
    """Merge the phase summary into ``jobs.report_json`` without dropping other phases."""
    try:
        report = db.get_job_report(job_id) or {}
        report.setdefault("phases", {})[PHASE_CODE] = summary
        db.save_job_report(job_id, report)
    except Exception:
        logger.exception("localization: failed to save job summary for job %s", job_id)


class SceneRouter:
    """Scene route ahead of detection (spec 05 AC-7/AC-8, #412); used only when ``scene_route.enabled``.

    Decodes each image once, classifies the rendition, saves the scene label, then either runs the
    bird detector on the same pixels or records a ``scene_route`` skip so consumers use the full
    frame. Classifier failures fail open to detection.
    """

    def __init__(self, settings: dict[str, Any]) -> None:
        from modules.scene_route import SceneClassifier

        self.backend = settings["backend"]
        self.thresholds = settings["run_thresholds"]
        from modules.remote_gpu.client import phase_is_remote

        if phase_is_remote(PHASE_CODE):
            # Scene routing is localization GPU work too; only the towers go remote.
            from modules.remote_gpu.client import get_client
            from modules.remote_gpu.proxies import RemoteSceneClassifier

            self.classifier = RemoteSceneClassifier(get_client(), self.backend)
        else:
            self.classifier = SceneClassifier(self.backend)

    def localize(self, image_id: int, file_path: str, ctx, *, max_regions: int, job_id: int) -> ImageOutcome:
        from modules.localization import DecodeError, decode_for_localization, record_scene_skip
        from modules.scene_route import detectors_to_run, save_scene_label

        def detect(decoded=None) -> ImageOutcome:
            return localize_image(image_id, file_path, ctx, max_regions=max_regions, job_id=job_id, decoded=decoded)

        if not file_path or not os.path.exists(file_path):
            return detect()  # records file_missing
        try:
            decoded = decode_for_localization(file_path)
        except DecodeError:
            return detect()  # records the decode failure the usual way
        try:
            result = self.classifier.classify(decoded.image)
            save_scene_label(image_id, result, backend=self.backend,
                             rendition_hash=decoded.descriptor.rendition_hash, job_id=job_id)
            detectors = detectors_to_run(result, self.thresholds)
        except Exception:  # noqa: BLE001 -- routing must never cost an image its detection
            logger.warning("scene_route: classification failed for image %s; running detection", image_id,
                           exc_info=True)
            return detect(decoded)
        if "bird" in detectors:
            return detect(decoded)
        return record_scene_skip(image_id, ctx, decoded, scene_version=result.version,
                                 top_label=result.top_label, job_id=job_id)


class LocalizationRunner:
    job_type = PHASE_CODE

    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.is_running = False
        self.log_history: list[str] = []
        self.status_message = "Idle"
        self._thread: threading.Thread | None = None
        self.current_count = 0
        self.total_count = 0

    def get_status(self):
        """Return (is_running, log_text, status_message, current_count, total_count)."""
        return self.is_running, "\n".join(self.log_history), self.status_message, self.current_count, self.total_count

    def stop(self):
        self.stop_event.set()

    def start_batch(
        self,
        input_path: str,
        job_id: int | None = None,
        resolved_image_ids: list[int] | None = None,
        report_collector=None,
        repair_limited: bool = False,
    ) -> str:
        """Start localization in a background thread. Returns 'Started' or an error string.

        ``repair_limited`` applies the bounded-repair limit (#527): images whose retryable
        attempts are exhausted or still cooling down are left for later. Explicit
        submissions leave it off; they are the explicit retry.
        """
        if self.is_running:
            return "Error: Already running."
        disabled = disabled_phase_submission_error([PHASE_CODE])
        if disabled:
            return f"Error: {disabled}"

        self.is_running = True
        self.log_history = []
        self.status_message = "Starting..."
        self.current_count = 0
        self.total_count = 0

        if job_id is None:
            job_id = db.create_job(input_path or "LOCALIZATION")

        def target():
            from modules.pipeline import safe_runner_thread

            def target_wrapper():
                try:
                    self._run_batch_internal(input_path, job_id, resolved_image_ids, report_collector,
                                             repair_limited=repair_limited)
                except Exception:
                    self.status_message = "Failed"
                    raise

            safe_runner_thread(self, job_id, target_wrapper)

        self._thread = threading.Thread(target=target, name="localization-runner", daemon=True)
        self._thread.start()
        return "Started"

    def _rows(self, input_path: str, resolved_image_ids: list[int] | None) -> list[dict[str, Any]]:
        ids = resolved_image_ids
        if ids is None:
            ids = db._query_image_ids_by_condition_for_scope([input_path], "1=1") if input_path else []
        ids = [int(i) for i in ids or []]
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        return db.get_connector().query(
            f"SELECT id, file_path FROM images WHERE id IN ({placeholders}) ORDER BY id",
            tuple(ids),
        ) or []

    def _run_batch_internal(self, input_path, job_id, resolved_image_ids, report_collector,
                            repair_limited: bool = False):
        from modules.events import event_manager
        from modules.run_log import runner_emit

        def log(msg: str, level: str = "INFO") -> None:
            runner_emit(self.log_history, job_id, msg, level, phase=PHASE_CODE)

        self.stop_event.clear()
        self.status_message = "Running..."
        db.update_job_status(job_id, "running")
        event_manager.broadcast_threadsafe("job_started", {
            "job_id": job_id, "job_type": PHASE_CODE, "input_path": input_path,
        })

        cfg = localization_config()
        max_regions = max_regions_per_class(cfg)
        rows = self._rows(input_path, resolved_image_ids)
        self.total_count = len(rows)
        log(f"Localization (shadow) on {len(rows)} images, up to {max_regions} regions each.")

        metrics = BatchMetrics()
        _reset_gpu_peak()
        ctx = load_detector_context(cfg) if rows else None
        scene = scene_route_settings()
        router = SceneRouter(scene) if rows and scene["enabled"] else None
        if router is not None:
            log(f"Scene route on ({router.backend}, thresholds {router.thresholds or 'none: detector always runs'}).")
        if ctx is not None and not ctx.enabled:
            log("Bird detector disabled (localization.detectors.bird.enabled=false); recording 'disabled'.",
                "WARNING")
        elif ctx is not None and ctx.load_error:
            log(f"Bird detector unavailable: {ctx.load_error}", "ERROR")
        history = fetch_run_history([int(r["id"]) for r in rows]) if repair_limited and rows else {}
        deferred: Counter[str] = Counter()

        for row in rows:
            if self.stop_event.is_set():
                log("Stopped by user.", "WARNING")
                break
            if db.job_should_stop_processing(job_id):
                self.stop_event.set()
                log("Paused (job status).", "WARNING")
                break

            image_id = int(row["id"])
            file_path = row.get("file_path") or ""
            if history.get(image_id):
                reason = self._repair_deferral(history[image_id], file_path, ctx)
                if reason:
                    deferred[reason] += 1
                    if report_collector is not None:
                        try:
                            report_collector.record_skip(image_id, reason)
                        except Exception:
                            logger.debug("localization: report record failed for image %s", image_id,
                                         exc_info=True)
                    self.current_count += 1
                    continue
            try:
                # Retries must re-enter running before their terminal outcome;
                # failed/skipped -> done is rejected by strict phase transitions.
                # Deferred repair rows above are left untouched.
                db.set_image_phase_status(
                    image_id, PHASE_CODE, "running", job_id=job_id,
                    executor_version=LOCALIZATION_RUNNER_VERSION,
                )
                if router is not None:
                    outcome = router.localize(image_id, file_path, ctx, max_regions=max_regions, job_id=job_id)
                else:
                    outcome = localize_image(image_id, file_path, ctx, max_regions=max_regions, job_id=job_id)
            except Exception as exc:  # noqa: BLE001 — a DB fault on one image must not end the batch
                logger.exception("localization: persisting image %s failed", image_id)
                outcome = ImageOutcome(status="retryable_error", error_detail=f"persist_error: {exc}")
                db.set_image_phase_status(
                    image_id, PHASE_CODE, "failed", job_id=job_id,
                    error=str(exc)[:500], executor_version=LOCALIZATION_RUNNER_VERSION,
                )
            else:
                self._record_phase_status(image_id, outcome, job_id)
            metrics.add(outcome)
            self._record_report(report_collector, image_id, outcome)
            if outcome.error_detail:
                log(f"{os.path.basename(file_path)}: {outcome.status} ({outcome.error_detail})", "WARNING")

            self.current_count += 1
            if self.current_count % 20 == 0:
                event_manager.broadcast_threadsafe("job_progress", {
                    "job_id": job_id, "job_type": PHASE_CODE,
                    "current": self.current_count, "total": self.total_count,
                })

        summary = metrics.summary(_peak_gpu_mib())
        if repair_limited:
            summary["repair_deferred"] = dict(deferred)
        if report_collector is not None:
            try:
                summary = {**report_collector.finalize(), **summary}
            except Exception:
                logger.exception("localization: report collector finalize failed for job %s", job_id)
        _save_summary(job_id, summary)
        log(f"Done. {summary['status_counts']} regions={summary['region_count_distribution']} "
            f"unchanged={summary['unchanged_skipped']}")
        self.status_message = "Done"
        self._finish_job(job_id)

    @staticmethod
    def _repair_deferral(history: list[dict[str, Any]], file_path: str, ctx) -> str | None:
        """``exhausted`` / ``cooling_down`` when bounded repair holds this image back, else None.

        Compared against the identity the next attempt would have, so a changed source or
        detector configuration starts a fresh count (#527).
        """
        try:
            source = source_identity(file_path)
        except OSError:
            source = (None, None)
        state = repair_state(history, (ctx.config_hash if ctx is not None else None, *source))
        if state.exhausted:
            return "exhausted"
        if state.blocked:
            return "cooling_down"
        return None

    @staticmethod
    def _record_phase_status(image_id: int, outcome: ImageOutcome, job_id: int) -> None:
        """AC-11: done / skipped / failed from the run outcome."""
        ips = PHASE_STATUS_FOR_RUN[outcome.status]
        kwargs: dict[str, Any] = {"job_id": job_id, "executor_version": LOCALIZATION_RUNNER_VERSION}
        if ips == "skipped":
            kwargs.update(skip_reason=outcome.status, skipped_by="localization_runner")
        elif ips == "failed":
            kwargs["error"] = outcome.error_detail
        db.set_image_phase_status(image_id, PHASE_CODE, ips, **kwargs)

    @staticmethod
    def _record_report(collector, image_id: int, outcome: ImageOutcome) -> None:
        if collector is None:
            return
        try:
            if outcome.unchanged:
                collector.record_skip(image_id, "unchanged")
            elif PHASE_STATUS_FOR_RUN.get(outcome.status) == "done":
                collector.record_after(image_id, {"status": outcome.status, "regions": outcome.regions})
            elif PHASE_STATUS_FOR_RUN.get(outcome.status) == "skipped":
                collector.record_skip(image_id, outcome.status)
            else:
                collector.record_failure(image_id, outcome.error_detail or outcome.status)
        except Exception:
            logger.debug("localization: report record failed for image %s", image_id, exc_info=True)

    def _finish_job(self, job_id: int) -> None:
        from modules.events import event_manager

        if self.stop_event.is_set() or db.job_should_stop_processing(job_id):
            try:
                db.reconcile_stale_running_phases_for_jobs(
                    [job_id], error_message=db.GRACEFUL_PAUSE_MSG, in_flight_to="not_started",
                )
            except Exception:
                logger.exception("localization: reconcile after stop failed (job_id=%s)", job_id)
            j = db.get_job(job_id)
            if j and (j.get("status") or "").strip().lower() == "running":
                try:
                    db.update_job_status(job_id, "paused", "\n".join(self.log_history))
                except Exception:
                    pass
            event_manager.broadcast_threadsafe(
                "job_completed", {"job_id": job_id, "status": (j or {}).get("status") or "paused"},
            )
            return
        db.update_job_status(job_id, "completed")
        event_manager.broadcast_threadsafe("job_completed", {"job_id": job_id, "status": "completed"})
