"""RTMDet-tiny (COCO) animal detector through onnxruntime: the cascade's fallback provider.

Spec 03 (#408), slice 1. Weights are the image-scoring-model export of the upstream Apache-2.0
OpenMMLab checkpoint (``training/teacher/export_rtmdet_onnx.py`` there), shipped with a manifest
that records the ONNX SHA-256 and the exact preprocessing. The export outputs raw per-prior
predictions -- ``boxes (1, 8400, 4)`` x1y1x2y2 in letterbox pixels and ``scores (1, 8400, 80)``
sigmoid -- so class filtering and NMS happen here.

Policy (spec 03):

* **AC-2** the weights must match the manifest's ``onnx_sha256`` or the provider is disabled with
  ``weights_mismatch``; a missing onnxruntime or file gives ``provider_unavailable``.
* **AC-3** letterbox to 640 (uniform scale, centred, pad 114), BGR, mean/std from the manifest,
  normalized in float64 then cast (the parity lesson from the ONNX feasibility notes).
* **AC-4** only COCO animal classes are kept; ``person`` and everything else is discarded.
* **AC-5** threshold 0.4; the optional retry threshold (spec: 0.25) is off by default, see
  ``DEFAULT_RETRY_THRESHOLD``.

Nothing here writes to the database.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

#: COCO class index -> name for the animal classes (AC-4). Indices follow the 80-class order.
ANIMAL_CLASSES: dict[int, str] = {
    14: "bird", 15: "cat", 16: "dog", 17: "horse", 18: "sheep", 19: "cow",
    20: "elephant", 21: "bear", 22: "zebra", 23: "giraffe",
}
DEFAULT_THRESHOLD = 0.4
#: AC-5's 0.25 retry is off by default: on the #377 independent strata it raised false positives
#: from 4% to 15% (fails AC-18's 10% gate) for +9 points recall. See the 2026-09-27 cascade benchmark.
DEFAULT_RETRY_THRESHOLD: float | None = None
NMS_IOU = 0.65
MAX_DET = 10
INPUT_SIZE = 640
PAD_VALUE = 114

ERROR_WEIGHTS_MISMATCH = "weights_mismatch"
ERROR_UNAVAILABLE = "provider_unavailable"


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def letterbox(image: Any, mean, std, size: int = INPUT_SIZE):
    """PIL RGB -> (NCHW float32 BGR tensor, scale, pad_x, pad_y) as the export expects."""
    import numpy as np
    from PIL import Image

    w, h = image.size
    scale = size / max(w, h)
    nw, nh = round(w * scale), round(h * scale)
    resized = np.asarray(image.convert("RGB").resize((nw, nh), Image.BILINEAR))
    canvas = np.full((size, size, 3), PAD_VALUE, np.uint8)
    px, py = (size - nw) // 2, (size - nh) // 2
    canvas[py:py + nh, px:px + nw] = resized
    x = canvas[..., ::-1].astype(np.float64)
    x = (x - np.asarray(mean, np.float64)) / np.asarray(std, np.float64)
    return np.ascontiguousarray(x.transpose(2, 0, 1)[None]).astype(np.float32), scale, px, py


def nms(boxes, scores, iou: float):
    """Greedy NMS over ``(n, 4)`` x1y1x2y2 arrays; returns kept indices, best first."""
    import numpy as np

    order = np.argsort(-scores, kind="stable")
    keep = []
    while order.size:
        i = order[0]
        keep.append(int(i))
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(boxes[i, 0], boxes[rest, 0])
        yy1 = np.maximum(boxes[i, 1], boxes[rest, 1])
        xx2 = np.minimum(boxes[i, 2], boxes[rest, 2])
        yy2 = np.minimum(boxes[i, 3], boxes[rest, 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        area_i = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
        area_r = (boxes[rest, 2] - boxes[rest, 0]) * (boxes[rest, 3] - boxes[rest, 1])
        union = area_i + area_r - inter
        overlap = np.where(union > 0, inter / np.maximum(union, 1e-12), 0.0)
        order = rest[overlap < iou]
    return keep


def select_animal_boxes(boxes, scores, image_w: int, image_h: int, *, threshold: float = DEFAULT_THRESHOLD,
                        retry_threshold: float | None = DEFAULT_RETRY_THRESHOLD, max_det: int = MAX_DET) -> list[dict]:
    """Class filter (AC-4), threshold with retry (AC-5), per-class NMS and ranking.

    ``boxes``: ``(n, 4)`` in image pixels; ``scores``: ``(n, 80)``. Returns ranked dicts with
    ``rank``, ``region`` (normalized), ``conf``, ``cls`` and ``area_frac``; invalid geometry is
    dropped, never clamped (same rule as ``bird_detection.rank_boxes``).
    """
    import numpy as np

    from modules.rendition import area_frac, normalize_pixel_box

    boxes = np.asarray(boxes, np.float64)
    scores = np.asarray(scores, np.float64)

    def pick(thr: float) -> list[tuple[float, str, tuple[float, float, float, float]]]:
        found = []
        for idx, name in ANIMAL_CLASSES.items():
            s = scores[:, idx]
            m = s >= thr
            if not m.any():
                continue
            b, sc = boxes[m], s[m]
            for k in nms(b, sc, NMS_IOU):
                region = normalize_pixel_box(tuple(b[k]), image_w, image_h)
                if region is not None:
                    found.append((float(sc[k]), name, region))
        return found

    found = pick(threshold) or (pick(retry_threshold) if retry_threshold is not None else [])
    found.sort(key=lambda f: (-f[0], f[2][1], f[2][0], f[2][3], f[2][2]))
    return [{"rank": r, "region": reg, "conf": round(conf, 4), "cls": name, "area_frac": round(area_frac(reg), 6)}
            for r, (conf, name, reg) in enumerate(found[:max_det])]


@dataclass
class RTMDetProvider:
    """Loaded session plus the identity every run records. Build with :func:`load_rtmdet`."""

    enabled: bool
    version: str
    config_hash: str
    session: Any = None
    mean: tuple = (103.53, 116.28, 123.675)
    std: tuple = (57.375, 57.12, 58.395)
    threshold: float = DEFAULT_THRESHOLD
    retry_threshold: float | None = DEFAULT_RETRY_THRESHOLD
    error_code: str | None = None
    error_detail: str | None = None
    manifest: dict = field(default_factory=dict)

    def detect(self, image: Any) -> list[dict]:
        """Ranked animal boxes for a display-oriented PIL image."""
        import numpy as np

        x, scale, px, py = letterbox(image, self.mean, self.std)
        outs = self.session.run(None, {self.session.get_inputs()[0].name: x})
        boxes, scores = np.asarray(outs[0])[0].astype(np.float64), np.asarray(outs[1])[0]
        boxes = (boxes - np.array([px, py, px, py], np.float64)) / scale
        w, h = image.size
        boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, w)
        boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, h)
        return select_animal_boxes(boxes, scores, w, h, threshold=self.threshold,
                                   retry_threshold=self.retry_threshold)


def _config_hash(weights_hash: str, threshold: float, retry: float | None) -> str:
    parts = ("rtmdet-v1", weights_hash, f"{threshold:.4f}", "none" if retry is None else f"{retry:.4f}", str(NMS_IOU), str(MAX_DET),
             ",".join(ANIMAL_CLASSES.values()))
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def load_rtmdet(weights_path: str, manifest_path: str | None = None, *, threshold: float = DEFAULT_THRESHOLD,
                retry_threshold: float | None = DEFAULT_RETRY_THRESHOLD, providers: list[str] | None = None) -> RTMDetProvider:
    """Load and verify the export. Never raises: failures become a disabled provider (AC-2)."""
    manifest_path = manifest_path or os.path.splitext(weights_path)[0] + ".manifest.json"
    version = f"rtmdet_tiny_coco/{os.path.basename(weights_path)}"

    def disabled(code: str, detail: str) -> RTMDetProvider:
        logger.warning("rtmdet provider disabled (%s): %s", code, detail)
        return RTMDetProvider(enabled=False, version=version, config_hash=_config_hash(code, threshold, retry_threshold),
                              error_code=code, error_detail=detail[:200])

    try:
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        return disabled(ERROR_UNAVAILABLE, f"manifest: {exc}")
    try:
        digest = _sha256(weights_path)
    except OSError as exc:
        return disabled(ERROR_UNAVAILABLE, f"weights: {exc}")
    if digest != manifest.get("onnx_sha256"):
        return disabled(ERROR_WEIGHTS_MISMATCH, f"sha256 {digest[:12]} != manifest {str(manifest.get('onnx_sha256'))[:12]}")
    try:
        import onnxruntime as ort

        session = ort.InferenceSession(weights_path, providers=providers or ["CPUExecutionProvider"])
    except Exception as exc:  # noqa: BLE001 -- optional dependency / broken runtime
        return disabled(ERROR_UNAVAILABLE, f"onnxruntime: {exc}")
    inp = manifest.get("input") or {}
    return RTMDetProvider(enabled=True, version=version, config_hash=_config_hash(digest, threshold, retry_threshold),
                          session=session, mean=tuple(inp.get("mean", RTMDetProvider.mean)),
                          std=tuple(inp.get("std", RTMDetProvider.std)), threshold=threshold,
                          retry_threshold=retry_threshold, manifest=manifest)
