"""Shadow subject keypoints: eye/beak/head points as region-linked artifacts (#426).

Runs the bird head pose model from the sibling model repo (``synthet/eye-pose-v0``,
YOLO pose with six points: beak, left/right eye, head top, left/right shoulder) **top-down**
on a padded crop of a region's box, and writes one versioned attempt per region into
``image_keypoint_runs`` / ``image_region_keypoints``.

**Shadow-only.** Nothing in scoring reads these rows. The gallery may draw them as a
diagnostic overlay.

Coordinates are stored in the parent localization run's display-normalized space (0..1 of
the display-oriented frame), which is also how ``image_regions`` stores boxes. The caller
must therefore pass the *same* decoded rendition the region was detected on (the backfill
checks the rendition hash).

Config ``localization.keypoints.bird_head`` (see ``config.example.json``):
    enabled        master toggle (default false)
    model_repo     HuggingFace repo id (default "synthet/eye-pose-v0")
    model_file     weight filename (default "eye_pose_v0.pt")
    local_path     optional local .pt path, used instead of downloading when present
    imgsz          inference size (default 640)
    confidence     pose box confidence threshold (default 0.25)
    min_kpt_conf   per-point visibility gate (default 0.25, the model repo's default)
    crop_pad       crop padding as a fraction of the region's width/height (default 0.25)
    device         "auto" | "cpu" | "cuda"
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Any

from modules.localization_legacy import redact_error_detail

logger = logging.getLogger(__name__)

PROVIDER_KEY = "bird_head_pose"
PASS_REGION_CROP = "region_crop"

#: The model repo's keypoint order (``eye_quality.localization.keypoint_schema``).
KEYPOINT_NAMES: tuple[str, ...] = (
    "beak", "left_eye", "right_eye", "head_top", "left_shoulder", "right_shoulder",
)

#: Minimum point confidence for a consumer to treat an eye as found (gallery overlay, evidence).
#: ``visible`` in the table is the provider's own permissive gate (``min_kpt_conf``) and is kept
#: for calibration. The 2026-09-27 spot check (docs/reports/eye-keypoint-spot-check-2026-09-27.md)
#: found eyes below 0.8 almost always wrong (90% off the eye) and above it ~74% on or within one
#: eye-width. A starting point to re-fit against owner-checked points.
EYE_CONSUMER_MIN_CONF = 0.8

STATUS_DETECTED = "detected"
STATUS_NO_KEYPOINTS = "no_keypoints"
STATUS_RETRYABLE = "retryable_error"
STATUS_TERMINAL = "terminal_error"

_DEFAULTS = {
    "enabled": False,
    "model_repo": "synthet/eye-pose-v0",
    "model_file": "eye_pose_v0.pt",
    "local_path": "",
    "imgsz": 640,
    "confidence": 0.25,
    "min_kpt_conf": 0.25,
    "crop_pad": 0.25,
    "device": "auto",
}


def keypoints_config(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """``localization.keypoints.bird_head`` merged over the defaults."""
    if cfg is None:
        from modules import config

        cfg = config.get_config_section("localization") or {}
    section = ((cfg.get("keypoints") or {}).get("bird_head") or {})
    return {**_DEFAULTS, **section}


# ---------------------------------------------------------------------------
# Pure geometry (unit-tested without a model)
# ---------------------------------------------------------------------------

def padded_crop_box(region: tuple[float, float, float, float], width: int, height: int,
                    pad: float) -> tuple[int, int, int, int] | None:
    """Pixel crop ``(x1, y1, x2, y2)`` around a normalized region, padded and clamped.

    Returns ``None`` when the clamped crop is empty.
    """
    x1, y1, x2, y2 = region
    bw, bh = (x2 - x1) * width, (y2 - y1) * height
    cx1 = max(0, int(x1 * width - pad * bw))
    cy1 = max(0, int(y1 * height - pad * bh))
    cx2 = min(width, int(round(x2 * width + pad * bw)))
    cy2 = min(height, int(round(y2 * height + pad * bh)))
    if cx2 - cx1 < 2 or cy2 - cy1 < 2:
        return None
    return cx1, cy1, cx2, cy2


def _iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def select_detection(detections: list[dict], target_xyxy: tuple[float, float, float, float]) -> dict | None:
    """Pick the pose detection that belongs to the region.

    ``detections``: ``{"xyxy", "conf", "kpts"}`` in crop pixels. ``target_xyxy``: the
    unpadded region in the same crop pixels. Highest IoU with the region wins, then
    confidence; a detection that does not overlap the region at all is never chosen (the
    padding can bring a neighbouring bird into the crop).
    """
    best, best_key = None, None
    for det in detections:
        iou = _iou(det["xyxy"], target_xyxy)
        if iou <= 0.0:
            continue
        key = (round(iou, 6), float(det["conf"]))
        if best_key is None or key > best_key:
            best, best_key = det, key
    return best


def to_display_normalized(kpts: list[tuple[float, float, float]], crop: tuple[int, int, int, int],
                          width: int, height: int, min_conf: float) -> list[dict]:
    """Map crop-pixel ``(x, y, conf)`` points to display-normalized keypoint rows."""
    cx1, cy1 = crop[0], crop[1]
    rows = []
    for name, (x, y, conf) in zip(KEYPOINT_NAMES, kpts):
        nx = min(1.0, max(0.0, (cx1 + float(x)) / width))
        ny = min(1.0, max(0.0, (cy1 + float(y)) / height))
        c = min(1.0, max(0.0, float(conf)))
        rows.append({"name": name, "x": nx, "y": ny, "confidence": round(c, 4),
                     "visible": c >= min_conf})
    return rows


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

@dataclass
class KeypointContext:
    """The pose model for one batch, loaded once, plus the identity every run records."""

    enabled: bool
    cfg: dict[str, Any]
    model: Any = None
    device: str = "cpu"
    version: str = ""
    config_hash: str = ""
    load_error: str | None = None


def _config_hash(weights_hash: str, cfg: dict[str, Any]) -> str:
    knobs = f"{weights_hash}|{cfg['imgsz']}|{cfg['confidence']}|{cfg['min_kpt_conf']}|{cfg['crop_pad']}"
    return hashlib.sha256(knobs.encode()).hexdigest()[:16]


def load_keypoint_context(cfg: dict[str, Any] | None = None) -> KeypointContext:
    """Build the batch's pose model. Never raises; a load failure becomes ``load_error``."""
    from modules.localization import weights_sha256

    kcfg = keypoints_config(cfg)
    version = f"{kcfg['model_repo']}/{kcfg['model_file']}"
    if not kcfg["enabled"]:
        return KeypointContext(enabled=False, cfg=kcfg, version=version,
                               config_hash=_config_hash("disabled", kcfg))
    device = kcfg["device"]
    if device == "auto":
        try:
            import torch

            device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:  # noqa: BLE001
            device = "cpu"
    try:
        path = kcfg["local_path"]
        if not (path and os.path.exists(path)):
            from huggingface_hub import hf_hub_download

            path = hf_hub_download(repo_id=kcfg["model_repo"], filename=kcfg["model_file"])
        from ultralytics import YOLO

        model = YOLO(path)
        weights_hash = weights_sha256(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("keypoints: pose model unavailable: %s", exc)
        return KeypointContext(enabled=True, cfg=kcfg, version=version,
                               config_hash=_config_hash("unavailable", kcfg),
                               load_error=redact_error_detail(f"provider_unavailable: {exc}"))
    return KeypointContext(enabled=True, cfg=kcfg, model=model, device=device, version=version,
                           config_hash=_config_hash(weights_hash, kcfg))


def _predict(ctx: KeypointContext, crop_img) -> list[dict]:
    results = ctx.model.predict(crop_img, conf=ctx.cfg["confidence"], imgsz=ctx.cfg["imgsz"],
                                verbose=False, device=ctx.device)
    out = []
    for r in results:
        if r.boxes is None or r.keypoints is None:
            continue
        kd = r.keypoints.data.cpu().numpy()  # (n, 6, 3): x, y, conf
        for i, box in enumerate(r.boxes):
            out.append({"xyxy": tuple(box.xyxy[0].tolist()), "conf": float(box.conf[0].item()),
                        "kpts": [tuple(map(float, p)) for p in kd[i]]})
    return out


def infer_region_keypoints(ctx: KeypointContext, image, region: tuple[float, float, float, float]) -> dict:
    """Run the provider on one region of a display-oriented PIL image.

    Returns ``{"status", "keypoints", "error_code", "error_detail"}``; never raises.
    """
    width, height = image.size
    crop = padded_crop_box(region, width, height, float(ctx.cfg["crop_pad"]))
    if crop is None:
        return {"status": STATUS_NO_KEYPOINTS, "keypoints": [], "error_code": "empty_crop",
                "error_detail": None}
    target = (region[0] * width - crop[0], region[1] * height - crop[1],
              region[2] * width - crop[0], region[3] * height - crop[1])
    try:
        dets = _predict(ctx, image.crop(crop))
    except Exception as exc:  # noqa: BLE001 — inference failure is retryable
        return {"status": STATUS_RETRYABLE, "keypoints": [], "error_code": "infer_error",
                "error_detail": redact_error_detail(f"infer_error: {exc}")}
    det = select_detection(dets, target)
    if det is None:
        return {"status": STATUS_NO_KEYPOINTS, "keypoints": [], "error_code": None,
                "error_detail": None}
    kps = to_display_normalized(det["kpts"], crop, width, height, float(ctx.cfg["min_kpt_conf"]))
    return {"status": STATUS_DETECTED, "keypoints": kps, "error_code": None, "error_detail": None}


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

_CURRENT_KP_RUN_SQL = """
    SELECT id, status, provider_config_hash FROM image_keypoint_runs
    WHERE region_id = ? AND provider_key = ? AND is_current
"""


def get_current_keypoint_run(region_id: int) -> dict[str, Any] | None:
    from modules import db

    return db.get_connector().query_one(_CURRENT_KP_RUN_SQL, (int(region_id), PROVIDER_KEY))


def is_unchanged(current: dict[str, Any] | None, config_hash: str) -> bool:
    """True when the region already has a final answer from this exact provider config."""
    return bool(current) and current.get("status") in (STATUS_DETECTED, STATUS_NO_KEYPOINTS) \
        and current.get("provider_config_hash") == config_hash


def write_keypoint_run(region_id: int, ctx: KeypointContext, outcome: dict) -> int:
    """Publish one attempt and its points atomically; the previous current attempt is retired."""
    from modules import db

    def _tx(tx) -> int:
        tx.execute(
            "UPDATE image_keypoint_runs SET is_current = FALSE "
            "WHERE region_id = ? AND provider_key = ? AND is_current",
            (int(region_id), PROVIDER_KEY),
        )
        rows = tx.execute_returning(
            "INSERT INTO image_keypoint_runs (region_id, provider_key, provider_version, "
            "provider_config_hash, pass, status, error_code, error_detail, is_current) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, TRUE) RETURNING id",
            (int(region_id), PROVIDER_KEY, ctx.version, ctx.config_hash, PASS_REGION_CROP,
             outcome["status"], outcome.get("error_code"), outcome.get("error_detail")),
        )
        run_id = int(rows[0]["id"])
        for kp in outcome.get("keypoints") or []:
            tx.execute(
                "INSERT INTO image_region_keypoints (keypoint_run_id, name, x, y, confidence, visible) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, kp["name"], kp["x"], kp["y"], kp["confidence"], bool(kp["visible"])),
            )
        return run_id

    return db.get_connector().run_transaction(_tx)
