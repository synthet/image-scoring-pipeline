"""Persist ``coco`` and ``subject_cascade`` localization runs after the bird run (spec 03 slice 2, #408).

Shadow only. Behind ``localization.cascade.enabled`` (default false): while it is false nothing here is
loaded and no ``coco`` / ``subject_cascade`` run is created (AC-15). No consumer reads these runs;
making the cascade a region source needs its own selection gate (AC-18).

Per image, after :func:`modules.localization.localize_image` wrote the current ``bird`` run:

* ``detected`` bird run -> the cascade adopts YOLO's boxes (AC-8); RTMDet does not run.
* ``no_detection`` -> decode the same rendition, run RTMDet, persist its ``coco`` run (AC-6), refine
  small boxes with YOLO on a padded crop (AC-10/11), persist the combination (AC-9).
* any other bird status -> the cascade records the matching non-detection status (AC-13/14).
"""

from __future__ import annotations

import datetime
import logging
import os
from dataclasses import dataclass
from typing import Any

from modules.localization_cascade import (
    COCO_DETECTOR_KEY,
    DEFAULT_REFINE_AREA_FRAC,
    DETECTOR_KEY,
    REFINE_PAD_FRAC,
    ChildOutcome,
    combine,
    refine_crop,
)

logger = logging.getLogger(__name__)

#: COCO fallback operating point re-fitted against bird_detect_v1 (cascade-benchmark-2026-09-27:
#: 83% recall at 7% false positives on the independent strata; 0.40 sits at AC-18's 10% limit).
DEFAULT_FALLBACK_THRESHOLD = 0.60
DEFAULT_WEIGHTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models",
                               "rtmdet_tiny_coco.onnx")

_RUN_SQL = """
    SELECT id, status, detector_config_hash, source_hash, source_hash_version, rendition_hash,
           rendition_version, orientation, display_width, display_height, decode_route
    FROM image_localization_runs
    WHERE image_id = ? AND detector_key = ? AND is_current
"""
_REGIONS_SQL = "SELECT rank, x1, y1, x2, y2, confidence FROM image_regions WHERE localization_run_id = ? ORDER BY rank"


def cascade_enabled(cfg: dict[str, Any]) -> bool:
    return bool((cfg.get("cascade") or {}).get("enabled", False))


@dataclass
class CascadeContext:
    rtmdet: Any
    yolo: Any
    yolo_config_hash: str
    refine_area_frac: float


def load_cascade_context(cfg: dict[str, Any], bird_ctx) -> CascadeContext | None:
    """``None`` unless ``localization.cascade.enabled`` (AC-15). Never raises."""
    if not cascade_enabled(cfg) or bird_ctx is None or not bird_ctx.enabled or bird_ctx.load_error:
        return None
    from modules.detectors.rtmdet import load_rtmdet

    c = cfg.get("cascade") or {}
    rt = load_rtmdet(DEFAULT_WEIGHTS, threshold=DEFAULT_FALLBACK_THRESHOLD, retry_threshold=None)
    return CascadeContext(rtmdet=rt, yolo=bird_ctx.detector, yolo_config_hash=bird_ctx.config_hash,
                          refine_area_frac=float(c.get("refine_area_frac", DEFAULT_REFINE_AREA_FRAC)))


def _run_row(image_id: int, job_id: int | None, key: str, version: str, config_hash: str,
             bird: dict[str, Any]) -> dict[str, Any]:
    from modules.localization import COORD_SPACE_DISPLAY

    now = datetime.datetime.now()
    return {"image_id": int(image_id), "job_id": job_id, "detector_key": key, "detector_version": version,
            "detector_config_hash": config_hash, "coord_space": COORD_SPACE_DISPLAY, "is_current": True,
            "is_retryable": False, "started_at": now, "completed_at": now,
            **{k: bird.get(k) for k in ("source_hash", "source_hash_version", "rendition_hash", "rendition_version",
                                         "orientation", "display_width", "display_height", "decode_route")}}


def _unchanged(image_id: int, key: str, config_hash: str, bird: dict[str, Any]) -> bool:
    from modules import db

    cur = db.get_connector().query_one(_RUN_SQL, (int(image_id), key))
    return bool(cur and cur["status"] != "retryable_error"
                and cur["detector_config_hash"] == config_hash
                and cur["rendition_hash"] == bird.get("rendition_hash")
                and cur["source_hash"] == bird.get("source_hash"))


def _refiner(image, yolo):
    w, h = image.size

    def refine(region):
        c = refine_crop(region, REFINE_PAD_FRAC)
        crop = image.crop((int(c[0] * w), int(c[1] * h), int(c[2] * w), int(c[3] * h)))
        cw, ch = crop.size
        return [{"region": (c[0] + r["region"][0] * cw / w, c[1] + r["region"][1] * ch / h,
                            c[0] + r["region"][2] * cw / w, c[1] + r["region"][3] * ch / h), "conf": r["conf"]}
                for r in yolo.detect_boxes(crop)]
    return refine


def localize_cascade(image_id: int, file_path: str, cctx: CascadeContext, *, max_regions: int,
                     job_id: int | None = None) -> str | None:
    """Write the image's ``subject_cascade`` run (and ``coco`` run when RTMDet ran). Returns its status.

    ``None`` when the bird run is missing or the cascade run is already current for this identity.
    """
    from modules import db
    from modules.localization import decode_for_localization, write_run
    from modules.localization_cascade import cascade_config_hash

    conn = db.get_connector()
    bird = conn.query_one(_RUN_SQL, (int(image_id), "bird"))
    if not bird:
        return None
    rt = cctx.rtmdet
    config_hash = cascade_config_hash(cctx.yolo_config_hash, rt.config_hash, cctx.refine_area_frac)
    if _unchanged(image_id, DETECTOR_KEY, config_hash, bird):
        return None
    version = f"subject_cascade/{rt.version}"

    yolo = ChildOutcome(bird["status"], cctx.yolo_config_hash)
    if bird["status"] == "detected":
        yolo.boxes = [{"region": (r["x1"], r["y1"], r["x2"], r["y2"]), "conf": r["confidence"]}
                      for r in conn.query(_REGIONS_SQL, (int(bird["id"]),)) or []]
    coco = ChildOutcome("disabled" if not rt.enabled else "no_detection", rt.config_hash)
    refine = None
    if bird["status"] == "no_detection" and rt.enabled:
        try:
            decoded = decode_for_localization(file_path)
            if decoded.descriptor.rendition_hash != bird["rendition_hash"]:
                raise RuntimeError("rendition changed since the bird run")
            boxes = rt.detect(decoded.image)[:max_regions]
            coco = ChildOutcome("detected" if boxes else "no_detection", rt.config_hash, boxes)
            refine = _refiner(decoded.image, cctx.yolo)
        except Exception as exc:  # noqa: BLE001 -- a child failure is an outcome (AC-14)
            logger.warning("cascade: coco child failed for image %s: %s", image_id, exc)
            coco = ChildOutcome("retryable_error", rt.config_hash)
        if coco.status in ("detected", "no_detection"):
            coco_run = _run_row(image_id, job_id, COCO_DETECTOR_KEY, rt.version, rt.config_hash, bird)
            coco_run["status"] = coco.status
            write_run(coco_run, [{"rank": i, "region": tuple(b["region"]), "conf": b["conf"], "object_class": "animal",
                                  "provider_class_id": f"coco:{b['cls']}"} for i, b in enumerate(coco.boxes)])

    result = combine(yolo, coco, refine=refine, refine_area_frac=cctx.refine_area_frac)
    run = _run_row(image_id, job_id, DETECTOR_KEY, version, config_hash, bird)
    run["status"] = result.status
    run["is_retryable"] = result.status == "retryable_error"
    write_run(run, result.regions[:max_regions])
    return result.status
