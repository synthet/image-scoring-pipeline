"""On-demand diagnostics: immutable cache identities and shared job subscriptions."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import atexit
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import sys
import threading
import uuid

import numpy as np
from PIL import Image

from modules.visual_evidence.cache import EvidenceCache, LAYERS
from modules.visual_evidence.compute import EXTRACTOR_VERSION, compute_maps, measure_head, peaking_fields
from modules.visual_evidence.context import geometry_matches, load_context
from modules.visual_evidence.providers import mask_provider, segment

logger = logging.getLogger(__name__)


def scoring_busy():
    api = sys.modules.get("modules.api")
    for name in ("_scoring_runner", "_tagging_runner", "_clustering_runner", "_localization_runner", "_bird_species_runner", "_selection_runner", "_indexing_runner"):
        runner = getattr(api, name, None)
        if runner is None:
            continue
        try:
            status = runner.get_status()
            if status.get("is_running", False) if isinstance(status, dict) else status[0]:
                return True
        except Exception:
            return True
    return False


def _png(data):
    output = io.BytesIO()
    Image.fromarray(data).save(output, format="PNG")
    return output.getvalue()


class DiagnosticManager:
    def __init__(self, cache_dir, *, context_loader=load_context, computer=None, gpu_busy=scoring_busy, max_bytes=2 * 1024 ** 3):
        self.cache = EvidenceCache(cache_dir, max_bytes)
        self.context_loader, self.computer, self.gpu_busy = context_loader, computer, gpu_busy
        self._cpu = ThreadPoolExecutor(max_workers=1, thread_name_prefix="evidence-cpu")
        self._gpu = ThreadPoolExecutor(max_workers=1, thread_name_prefix="evidence-model")
        self._lock = threading.RLock()
        self._source_locks = {}
        self._jobs, self._requests = {}, {}
        self._closed = threading.Event()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self._closed.set()
        self._cpu.shutdown(wait=True, cancel_futures=True)
        self._gpu.shutdown(wait=True, cancel_futures=True)

    def _key(self, context):
        identity = {name: context.get(name) for name in ("image_id", "source_hash", "source_hash_version", "region_id", "keypoint_run_id", "region", "region_provenance", "keypoints")}
        identity.update(extractor_version=EXTRACTOR_VERSION, preview_policy="display-jpeg95-v1", mask_provider=mask_provider()["version"] if self.computer is None else "test")
        return hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()

    def _availability(self, context, layer):
        if not context.get("path") or not Path(context["path"]).is_file():
            return "Source pixels are unavailable"
        if self.computer is not None:
            return None
        enabled = os.environ.get("DIAGNOSTICS_ENABLED_LAYERS", ",".join(LAYERS)).split(",")
        if layer not in enabled:
            return "This diagnostic capability is disabled"
        if layer in ("mask", "head") and not context.get("region"):
            return context.get("region_reason") or "No verified primary subject region"
        if layer == "head" and not context.get("keypoints"):
            return "No reliable stored head keypoints"
        if layer == "mask":
            provider = mask_provider()
            if not provider["available"]:
                return provider["reason"]
        return None

    def _manifest(self, context, key):
        image_id = context["image_id"]
        source = self.cache.get(image_id, key, "source")
        result = {"evidence_schema_version": 2, "extractor_version": EXTRACTOR_VERSION,
                  "image_id": image_id, "identity": key, "rendition": source.get("rendition") if source else None, "layers": {}}
        for layer in LAYERS:
            reason = self._availability(context, layer)
            entry = self.cache.get(image_id, key, layer)
            job = self._jobs.get((image_id, key, layer))
            if reason:
                value = {"state": "unavailable", "reason": reason}
            elif job and job["state"] in ("queued", "running"):
                value = {"state": job["state"], "reason": job.get("reason")}
            elif entry:
                value = dict(entry)
            elif job and job["state"] in ("unavailable", "failed"):
                value = {"state": job["state"], "reason": job.get("reason")}
            else:
                value = {"state": "not_requested"}
            result["layers"][layer] = value
        return result

    def manifest(self, image_id):
        context = self.context_loader(image_id)
        with self._lock:
            return self._manifest(context, self._key(context))

    def _retire(self, job_key, job, *, finished=False):
        """Called under the manager lock; never forget another subscriber's work."""
        future = job.get("future")
        if job["subscribers"] or (not finished and future is not None and not future.done()):
            return
        if self._jobs.get(job_key) is job:
            self._jobs.pop(job_key)
        if not any(other[:2] == job_key[:2] for other in self._jobs):
            self._source_locks.pop(job_key[:2], None)

    def request(self, image_id, layers, *, refresh=False):
        if not layers or len(layers) > len(LAYERS) or any(layer not in LAYERS for layer in layers):
            raise ValueError("Select supported diagnostic layers")
        context = self.context_loader(image_id)
        key = self._key(context)
        request_id = uuid.uuid4().hex
        with self._lock:
            # Completed subscriptions are bounded; work is not a durable scoring job.
            if len(self._requests) >= 512:
                expired = [ident for ident, item in self._requests.items() if all(self._jobs.get(job, {}).get("state") not in ("queued", "running") for job in item["jobs"])]
                for ident in expired[:256]:
                    previous = self._requests.pop(ident, None)
                    for job_key in previous["jobs"]:
                        job = self._jobs.get(job_key)
                        if job:
                            job["subscribers"].discard(ident)
                            self._retire(job_key, job)
                if len(self._requests) >= 512:
                    raise RuntimeError("Diagnostic request capacity reached; retry shortly")
            subscription = {"image_id": image_id, "jobs": set()}
            self._requests[request_id] = subscription
            for layer in dict.fromkeys(layers):
                if self._availability(context, layer):
                    continue
                job_key = (image_id, key, layer)
                job = self._jobs.get(job_key)
                if job and job["state"] in ("queued", "running"):
                    job["subscribers"].add(request_id)
                    subscription["jobs"].add(job_key)
                    continue
                if not refresh and self.cache.get(image_id, key, layer):
                    continue
                job = {"state": "queued", "subscribers": {request_id}, "cancel": threading.Event()}
                self._jobs[job_key] = job
                subscription["jobs"].add(job_key)
                executor = self._gpu if layer == "mask" else self._cpu
                job["future"] = executor.submit(self._run, context, key, layer, job)
            result = self._manifest(context, key)
            result["request_id"] = request_id
            return result

    def cancel(self, image_id, request_id):
        with self._lock:
            request = self._requests.get(request_id)
            if request is None or request["image_id"] != image_id:
                return False
            self._requests.pop(request_id)
            for job_key in request["jobs"]:
                job = self._jobs.get(job_key)
                if not job:
                    continue
                job["subscribers"].discard(request_id)
                if not job["subscribers"] and job["state"] in ("queued", "running"):
                    job["cancel"].set()
                    job["state"] = "not_requested"
                self._retire(job_key, job)
            return True

    def _prepare(self, context, key):
        image_id = context["image_id"]
        with self._lock:
            lock = self._source_locks.setdefault((image_id, key), threading.Lock())
        with lock:
            cached = self.cache.get(image_id, key, "source")
            if cached:
                return cached
            from modules.localization import decode_for_localization
            decoded = decode_for_localization(context["path"])
            output = io.BytesIO()
            try:
                decoded.image.save(output, format="JPEG", quality=95, subsampling=0)
                rendition = decoded.descriptor.as_dict()
            finally:
                decoded.image.close()
            data = output.getvalue()
            preview_id = self.cache.write_artifact(image_id, key, data, "jpg")
            # The preview bytes are re-opened by extractors: display and measurement see identical pixels.
            rendition = {name: value for name, value in rendition.items() if name != "source_path"}
            rendition["source_rendition_hash"] = rendition.pop("rendition_hash")
            rendition.update(rendition_hash=hashlib.sha256(data).hexdigest(), preview_artifact=preview_id,
                             source_resolution="reduced" if rendition["decode_route"] in ("raw_magick", "raw_preview") else "decoded_native",
                             pixel_policy="display-jpeg95-v1", coord_space="display_normalized")
            result = {"rendition": rendition, "artifacts": {"preview": preview_id}}
            self.cache.put(image_id, key, "source", result)
            return result

    def _run(self, context, key, layer, job):
        try:
            if layer == "mask":
                while self.gpu_busy() and not self._closed.is_set() and not job["cancel"].is_set():
                    with self._lock:
                        job["reason"] = "Waiting for scoring to release the GPU"
                    self._closed.wait(.25)
            if self._closed.is_set() or job["cancel"].is_set():
                return
            with self._lock:
                job.update(state="running", reason=None)
            with self.cache.pin(context["image_id"], key):
                prepared = self._prepare(context, key)
                value = self.computer(layer, prepared, context) if self.computer else self._compute(layer, prepared, context, key, job)
                if job["cancel"].is_set() or self._key(self.context_loader(context["image_id"])) != key:
                    with self._lock:
                        job.update(state="not_requested", reason="Source or geometry changed")
                    return
                value.setdefault("state", "ready")
                value.setdefault("artifacts", {})
                value["extractor_version"] = EXTRACTOR_VERSION
                self.cache.put(context["image_id"], key, layer, value)
                with self._lock:
                    job.update(state=value["state"], reason=value.get("reason"))
                self.cache.prune()
        except InterruptedError:
            with self._lock:
                job.update(state="not_requested", reason=None)
        except Exception:
            logger.exception("Diagnostic computation failed for image %s, layer %s", context["image_id"], layer)
            with self._lock:
                job.update(state="failed", reason="Diagnostic computation failed; use Refresh to retry")
        finally:
            self.cache.prune()
            with self._lock:
                if job["state"] in ("queued", "running"):
                    job["state"] = "not_requested"
                self._retire((context["image_id"], key, layer), job, finished=True)

    def _compute(self, layer, prepared, context, key, job):
        image_id = context["image_id"]
        rendition = prepared["rendition"]
        with Image.open(self.cache.artifact(image_id, prepared["artifacts"]["preview"])) as image:
            if layer in ("sharpness", "noise"):
                maps = compute_maps(image, cancelled=lambda: job["cancel"].is_set() or self._closed.is_set())
                grid = maps[layer]
                values = [value for value in grid["values"] if value is not None]
                if not values:
                    return {"state": "unavailable", "reason": "Insufficient low-structure pixels for a reliable estimate"}
                measurements = {"mean": float(np.mean(values)), "units": grid["units"], "source_resolution": rendition["source_resolution"],
                                "scope": "display_rendition", "limitations": ["Decoded display pixels; not RAW sensor measurements"]}
                if layer == "sharpness" and geometry_matches(context, rendition):
                    x0, y0, x1, y1 = context["region"]
                    subject, background = [], []
                    width, height = image.size
                    for cy in range(grid["cells_y"]):
                        for cx in range(grid["cells_x"]):
                            value = grid["values"][cy * grid["cells_x"] + cx]
                            if value is None:
                                continue
                            mx = (grid["x_edges"][cx] + grid["x_edges"][cx + 1]) / (2 * width)
                            my = (grid["y_edges"][cy] + grid["y_edges"][cy + 1]) / (2 * height)
                            (subject if x0 <= mx <= x1 and y0 <= my <= y1 else background).append(value)
                    if subject and background and np.mean(background) > 1e-6:
                        measurements["region_background_ratio"] = float(np.mean(subject) / np.mean(background))
                return {"grid": grid, "measurements": measurements}
            if layer == "peaking":
                if rendition["source_resolution"] == "reduced":
                    return {"state": "unavailable", "reason": "A native-resolution rendition is required for focus peaking"}
                fields = peaking_fields(image, cancelled=lambda: job["cancel"].is_set() or self._closed.is_set())
                artifacts = {}
                for mode, field in fields.items():
                    # Neutral white strokes; application design tokens supply the glow.
                    rgba = np.full((*field.shape, 4), 255, np.uint8)
                    rgba[:, :, 3] = field
                    artifacts[mode] = self.cache.write_artifact(image_id, key, _png(rgba), "png")
                return {"artifacts": artifacts, "measurements": {"source_resolution": rendition["source_resolution"], "marks": int(np.count_nonzero(fields["both"]))}}
            if not geometry_matches(context, rendition):
                return {"state": "unavailable", "reason": "Subject coordinates do not match the decoded rendition; regenerate localization"}
            if layer == "head":
                measurement = measure_head(image, context["keypoints"], context["region"])
                return measurement if measurement.get("state") == "unavailable" else {"measurements": measurement}
            while True:
                if job["cancel"].is_set() or self._closed.is_set():
                    raise InterruptedError()
                if self.gpu_busy():
                    job.update(state="queued", reason="Waiting for scoring to release the GPU")
                    self._closed.wait(.25)
                    continue
                job.update(state="running", reason=None)
                outcome = segment(self.cache.artifact(image_id, prepared["artifacts"]["preview"]), context["region"],
                                  cancelled=lambda: job["cancel"].is_set() or self._closed.is_set(), gpu_busy=self.gpu_busy)
                if outcome.get("state") == "cancelled":
                    raise InterruptedError()
                if outcome.get("state") != "deferred":
                    break
            if outcome.get("state") == "unavailable":
                return outcome
            mask = np.asarray(outcome["mask"], dtype=bool)
            if mask.shape != (image.height, image.width) or not mask.any() or mask.all():
                return {"state": "unavailable", "reason": "Segmentation did not produce a usable subject mask"}
            import cv2
            alpha = (mask * 255).astype(np.uint8)
            contour = cv2.morphologyEx(alpha, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
            artifacts = {}
            for name, field in (("mask", alpha), ("background", 255 - alpha), ("contour", contour)):
                rgba = np.full((*field.shape, 4), 255, np.uint8)
                rgba[:, :, 3] = field
                artifacts[name] = self.cache.write_artifact(image_id, key, _png(rgba), "png")
            return {"artifacts": artifacts, "provider_version": outcome["provider_version"],
                    "measurements": {"coverage": float(mask.mean()), "confidence": outcome.get("confidence"), "scope": "primary_subject"}}


_manager = None
_manager_lock = threading.Lock()


def get_manager():
    global _manager
    with _manager_lock:
        if _manager is None:
            directory = os.environ.get("EVIDENCE_CACHE_DIR") or str(Path(__file__).resolve().parents[2] / "thumbnails" / "evidence-v2")
            budget = int(os.environ.get("EVIDENCE_CACHE_MAX_BYTES", str(2 * 1024 ** 3)))
            _manager = DiagnosticManager(directory, max_bytes=budget)
            atexit.register(_manager.close)
        return _manager


def close_manager():
    global _manager
    with _manager_lock:
        current, _manager = _manager, None
    if current is not None:
        current.close()
