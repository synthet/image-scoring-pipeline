"""Shadow localization: decode, detect, and persist provenance-stamped regions.

Stage 4 of the early-localization rollout, slice 1 (#387, epic #345). Runs the existing
bird YOLO detector on an explicitly submitted scope and writes one versioned attempt per
image into the stage 2 tables (``image_localization_runs`` / ``image_regions``).

**Shadow-only.** Nothing downstream reads these rows yet. This module never writes
``images.bird_bbox``, scores, keywords, captions, embeddings, culling data, or any other
phase's ``image_phase_status`` row -- the only phase status it touches is
``localization`` itself (see :mod:`modules.localization_runner`).

Three decisions from #387 shape the code:

* **Decode (AC-18..20).** Detection runs on the best feasible rendition of a RAW: the
  full-size embedded ``JpgFromRaw`` first, and ``rawpy`` rather than a reduced preview
  when no embedded JPEG reaches :data:`MIN_EMBEDDED_LONG_EDGE`. The route and the decoded
  size are stored on every run. ``open_rendition_for_ml`` is deliberately not reused: it
  accepts any preview over 1000 *bytes* and reports ``JpgFromRaw`` and ``PreviewImage`` as
  one route, and changing it would move production BioCLIP inputs.
* **Region cap (AC-6).** Up to ``localization.max_regions_per_class`` boxes (default 10,
  the detector's ``max_det``), ranked by :func:`modules.bird_detection.rank_boxes`.
* **Weights hash (AC-13).** SHA-256 of the weights file, computed once per process and
  cached against the file's path, size and mtime.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modules.localization_legacy import redact_error_detail
from modules.rendition import (
    COORD_SPACE_DISPLAY,
    DecodeRoute,
    RenditionDescriptor,
    build_rendition_descriptor,
)

logger = logging.getLogger(__name__)

#: ``image_phase_status.executor_version`` for the ``localization`` phase.
LOCALIZATION_RUNNER_VERSION = "1.0.0"

#: Same key as the stage 2 legacy import, so a shadow run supersedes an imported row for
#: the same image (AC-12). ``read_bird_bbox`` only prefers normalized rows once
#: ``localization.read_normalized_first`` is enabled, so this changes no read today.
DETECTOR_KEY = "bird"
OBJECT_CLASS = "bird"
PROVIDER_CLASS_ID = "0"

#: An embedded JPEG shorter than this on its long edge is treated as a reduced preview,
#: and the RAW is decoded with ``rawpy`` instead (AC-19). Barely matters for 640 px
#: detection; it sets the pixel quality of the crops later stages cut from these boxes.
MIN_EMBEDDED_LONG_EDGE = 2048

DEFAULT_MAX_REGIONS_PER_CLASS = 10

STATUS_DETECTED = "detected"
STATUS_NO_DETECTION = "no_detection"
STATUS_TERMINAL = "terminal_error"
STATUS_RETRYABLE = "retryable_error"
STATUS_DISABLED = "disabled"

#: Run status -> ``image_phase_status`` value (AC-11).
PHASE_STATUS_FOR_RUN = {
    STATUS_DETECTED: "done",
    STATUS_NO_DETECTION: "done",
    STATUS_TERMINAL: "skipped",
    STATUS_DISABLED: "skipped",
    STATUS_RETRYABLE: "failed",
}

#: Outcomes that are a finished answer for the rendition they describe. Only these let an
#: unchanged image skip detection (AC-14); a retryable error must be allowed to retry.
_REUSABLE_STATUSES = frozenset({STATUS_DETECTED, STATUS_NO_DETECTION})

_RAW_EXTENSIONS = frozenset({".nef", ".nrw", ".cr2", ".dng", ".arw", ".orf", ".cr3", ".rw2"})
_EXIF_ORIENTATION = 0x0112


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def localization_config() -> dict[str, Any]:
    from modules import config

    return config.get_config_section("localization") or {}


def max_regions_per_class(cfg: dict[str, Any]) -> int:
    try:
        return max(0, int(cfg.get("max_regions_per_class", DEFAULT_MAX_REGIONS_PER_CLASS)))
    except (TypeError, ValueError):
        return DEFAULT_MAX_REGIONS_PER_CLASS


def bird_detector_enabled(cfg: dict[str, Any]) -> bool:
    """``localization.detectors.bird.enabled``; defaults to true once the phase is on."""
    bird = ((cfg.get("detectors") or {}).get("bird") or {})
    return bool(bird.get("enabled", True))


# ---------------------------------------------------------------------------
# Detector identity (AC-13)
# ---------------------------------------------------------------------------

_WEIGHTS_HASH_CACHE: dict[tuple[str, int, int], str] = {}


def weights_sha256(path: str) -> str:
    """SHA-256 of a weights file, cached per process on ``(path, size, mtime_ns)``.

    A replaced file changes size or mtime and is re-hashed; an unchanged one costs a stat.
    """
    real = os.path.realpath(path)
    st = os.stat(real)
    key = (real, int(st.st_size), int(st.st_mtime_ns))
    cached = _WEIGHTS_HASH_CACHE.get(key)
    if cached is not None:
        return cached
    h = hashlib.sha256()
    with open(real, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    digest = h.hexdigest()
    _WEIGHTS_HASH_CACHE[key] = digest
    return digest


def detector_config_hash(weights_hash: str, imgsz: int, conf: float, max_det: int) -> str:
    """Digest of everything that decides which boxes the detector returns.

    ``weights_hash`` is the weights SHA-256, or a marker (``disabled`` / ``unavailable``)
    when no weights were resolved. A marker can never equal a real digest, so a skip
    recorded while the detector was off never matches a later real attempt.
    """
    parts = ("v1", str(weights_hash), str(int(imgsz)), f"{float(conf):.6f}", str(int(max_det)))
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


@dataclass
class DetectorContext:
    """The detector for one batch, loaded once, with the identity every run records."""

    enabled: bool
    detector: Any = None
    version: str = ""
    config_hash: str = ""
    #: Set when loading failed; every image then gets ``retryable_error`` (AC-9).
    load_error: str | None = None


def load_detector_context(cfg: dict[str, Any], bird_cfg: dict[str, Any] | None = None) -> DetectorContext:
    """Build the batch's detector. Never raises.

    With ``localization.detectors.bird.enabled`` false the detector is **not** constructed
    or loaded (AC-10).
    """
    from modules.bird_detection import BirdDetector

    if bird_cfg is None:
        from modules import config

        bird_cfg = config.get_config_section("bird_detection") or {}

    # Constructing BirdDetector is cheap (no model load); it is the one place the
    # production defaults for imgsz/conf/max_det are resolved.
    probe = BirdDetector(config=bird_cfg, device="cpu")
    version = f"{probe.model_repo}/{probe.model_file}"
    knobs = (probe.imgsz, probe.confidence, probe.max_det)

    if not bird_detector_enabled(cfg):
        return DetectorContext(
            enabled=False,
            version=version,
            config_hash=detector_config_hash(STATUS_DISABLED, *knobs),
        )

    detector = BirdDetector(config=bird_cfg)
    try:
        weights_path = detector._resolve_weights_path()
        weights_hash = weights_sha256(weights_path)
        detector.load_model()
    except Exception as exc:  # noqa: BLE001 — a load failure is an outcome, not a crash
        logger.warning("localization: bird detector unavailable: %s", exc)
        return DetectorContext(
            enabled=True,
            version=version,
            config_hash=detector_config_hash("unavailable", *knobs),
            load_error=redact_error_detail(f"detector_unavailable: {exc}"),
        )
    return DetectorContext(
        enabled=True,
        detector=detector,
        version=version,
        config_hash=detector_config_hash(weights_hash, *knobs),
    )


# ---------------------------------------------------------------------------
# Decode (AC-18, AC-19, AC-20)
# ---------------------------------------------------------------------------

class DecodeError(Exception):
    """The source could not be turned into pixels. Terminal for this source identity."""


@dataclass
class Decoded:
    image: Any
    descriptor: RenditionDescriptor
    #: Informational: which embedded tag was used, or why an embedded JPEG was rejected.
    notes: dict[str, Any] = field(default_factory=dict)


def _exiftool_jpeg(path: str, tag: str):
    """Decode one embedded JPEG tag via exiftool, or ``None`` if absent/undecodable."""
    from PIL import Image

    try:
        res = subprocess.run(
            ["exiftool", "-b", f"-{tag}", path], capture_output=True, text=False, timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    data = res.stdout or b""
    if res.returncode != 0 or not data.startswith(b"\xff\xd8"):
        return None
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        return img
    except Exception:  # noqa: BLE001 — a corrupt preview is simply not usable
        return None


def _decode_raw(path: str):
    """Return ``(image, route, notes)`` for a RAW file, preferring full-size pixels."""
    from PIL import Image

    notes: dict[str, Any] = {}
    if shutil.which("exiftool"):
        for tag, route in (
            ("JpgFromRaw", DecodeRoute.RAW_JPG_FROM_RAW),
            ("PreviewImage", DecodeRoute.RAW_EMBEDDED_PREVIEW),
        ):
            img = _exiftool_jpeg(path, tag)
            if img is None:
                continue
            long_edge = max(img.size)
            if long_edge >= MIN_EMBEDDED_LONG_EDGE:
                notes["embedded_tag"] = tag
                return img, route, notes
            notes[f"rejected_{tag}_long_edge"] = long_edge

    try:
        import rawpy
    except ImportError as exc:
        raise DecodeError(f"decode_error: rawpy unavailable ({exc})") from exc
    try:
        with rawpy.imread(path) as raw:
            # user_flip=0: orientation is applied below from EXIF, the same way as for the
            # embedded JPEGs, so every route reaches display orientation by one rule.
            rgb = raw.postprocess(use_camera_wb=True, bright=1.0, user_flip=0)
    except Exception as exc:  # noqa: BLE001
        raise DecodeError(f"decode_error: {exc}") from exc
    return Image.fromarray(rgb), DecodeRoute.RAW_RAWPY, notes


def _apply_orientation(img, source_path: str):
    """Transpose ``img`` to display orientation. Returns ``(image, orientation_applied)``.

    Uses the image's own EXIF orientation, falling back to the source file's (exiftool
    extracts and ``rawpy`` output usually carry none) -- the rule ``bake_orientation`` uses.
    """
    from PIL import ImageOps

    from modules.thumbnails import read_orientation

    exif = img.getexif()
    orientation = exif.get(_EXIF_ORIENTATION)
    if orientation in (None, 0, 1):
        source_orientation = read_orientation(source_path)
        if source_orientation is not None and source_orientation >= 2:
            exif[_EXIF_ORIENTATION] = source_orientation
            orientation = source_orientation
    try:
        orientation = int(orientation or 1)
    except (TypeError, ValueError):
        orientation = 1
    if not 1 <= orientation <= 8:
        orientation = 1
    return ImageOps.exif_transpose(img), orientation


def decode_for_localization(path: str) -> Decoded:
    """Decode ``path`` into display-oriented RGB pixels plus their rendition identity.

    Raises :class:`DecodeError` when no route produces pixels.
    """
    from PIL import Image

    path = str(path)
    try:
        if Path(path).suffix.lower() in _RAW_EXTENSIONS:
            img, route, notes = _decode_raw(path)
        else:
            img = Image.open(path)
            img.load()
            route, notes = DecodeRoute.DIRECT, {}
        img, orientation = _apply_orientation(img, path)
        img = img.convert("RGB")
        descriptor = build_rendition_descriptor(path, img, route, orientation)
    except DecodeError:
        raise
    except Exception as exc:  # noqa: BLE001 — anything here means "no usable pixels"
        raise DecodeError(f"decode_error: {exc}") from exc
    return Decoded(image=img, descriptor=descriptor, notes=notes)


# ---------------------------------------------------------------------------
# Persistence (AC-6, AC-7, AC-12, AC-14)
# ---------------------------------------------------------------------------

_CURRENT_RUN_SQL = """
    SELECT id, status, detector_config_hash, source_hash, rendition_hash
    FROM image_localization_runs
    WHERE image_id = ? AND detector_key = ? AND is_current
"""

_RUN_COLUMNS = (
    "image_id", "job_id", "detector_key", "detector_version", "detector_config_hash",
    "source_hash", "source_hash_version", "rendition_hash", "rendition_version",
    "coord_space", "orientation", "display_width", "display_height", "decode_route",
    "status", "is_retryable", "error_code", "error_detail", "is_current",
    "started_at", "completed_at",
)


def get_current_run(image_id: int) -> dict[str, Any] | None:
    from modules import db

    return db.get_connector().query_one(_CURRENT_RUN_SQL, (int(image_id), DETECTOR_KEY))


def is_unchanged(current: dict[str, Any] | None, config_hash: str, descriptor: RenditionDescriptor) -> bool:
    """True when ``current`` already answers this exact detector + source + rendition (AC-14)."""
    if not current or current.get("status") not in _REUSABLE_STATUSES:
        return False
    return (
        current.get("detector_config_hash") == config_hash
        and current.get("source_hash") == descriptor.source_hash
        and current.get("rendition_hash") == descriptor.rendition_hash
    )


def write_run(run: dict[str, Any], regions: list[dict[str, Any]]) -> int:
    """Publish one attempt and its regions atomically. Returns the new run id.

    The previous current run for the same (image, detector) loses ``is_current`` in the
    same transaction (AC-12), so readers never see zero or two current attempts.
    """
    from modules import db

    values = [run.get(col) for col in _RUN_COLUMNS]
    placeholders = ", ".join("?" for _ in _RUN_COLUMNS)

    def _tx(tx) -> int:
        tx.execute(
            "UPDATE image_localization_runs SET is_current = FALSE, updated_at = CURRENT_TIMESTAMP "
            "WHERE image_id = ? AND detector_key = ? AND is_current",
            (run["image_id"], run["detector_key"]),
        )
        rows = tx.execute_returning(
            f"INSERT INTO image_localization_runs ({', '.join(_RUN_COLUMNS)}) "
            f"VALUES ({placeholders}) RETURNING id",
            values,
        )
        run_id = int(rows[0]["id"])
        for region in regions:
            tx.execute(
                "INSERT INTO image_regions (localization_run_id, object_class, provider_class_id, "
                "confidence, rank, x1, y1, x2, y2) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id, OBJECT_CLASS, PROVIDER_CLASS_ID, region["conf"], region["rank"],
                    *region["region"],
                ),
            )
        return run_id

    return db.get_connector().run_transaction(_tx)


# ---------------------------------------------------------------------------
# One image
# ---------------------------------------------------------------------------

@dataclass
class ImageOutcome:
    status: str
    regions: int = 0
    #: True when AC-14 left the existing current run in place.
    unchanged: bool = False
    decode_seconds: float | None = None
    inference_seconds: float | None = None
    error_detail: str | None = None


def _base_run(image_id: int, job_id: int | None, ctx: DetectorContext) -> dict[str, Any]:
    import datetime

    return {
        "image_id": int(image_id),
        "job_id": job_id,
        "detector_key": DETECTOR_KEY,
        "detector_version": ctx.version,
        "detector_config_hash": ctx.config_hash,
        "coord_space": COORD_SPACE_DISPLAY,
        "is_current": True,
        "is_retryable": False,
        "started_at": datetime.datetime.now(),
    }


def _finish(run: dict[str, Any], regions: list[dict[str, Any]]) -> None:
    import datetime

    run["completed_at"] = datetime.datetime.now()
    write_run(run, regions)


def localize_image(
    image_id: int,
    file_path: str,
    ctx: DetectorContext,
    *,
    max_regions: int,
    job_id: int | None = None,
) -> ImageOutcome:
    """Run one image through decode + detection and persist the attempt.

    Every path writes exactly one current run, except AC-14's unchanged skip, which
    writes nothing. Database errors propagate to the caller.
    """
    import time

    run = _base_run(image_id, job_id, ctx)

    if not ctx.enabled:
        run["status"] = STATUS_DISABLED
        _finish(run, [])
        return ImageOutcome(status=STATUS_DISABLED)

    if ctx.load_error:
        run.update(status=STATUS_RETRYABLE, is_retryable=True,
                   error_code="detector_unavailable", error_detail=ctx.load_error)
        _finish(run, [])
        return ImageOutcome(status=STATUS_RETRYABLE, error_detail=ctx.load_error)

    if not file_path or not os.path.exists(file_path):
        run.update(status=STATUS_TERMINAL, error_code="file_missing",
                   error_detail="file_missing")
        _finish(run, [])
        return ImageOutcome(status=STATUS_TERMINAL, error_detail="file_missing")

    t0 = time.perf_counter()
    try:
        decoded = decode_for_localization(file_path)
    except DecodeError as exc:
        detail = redact_error_detail(str(exc))
        run.update(status=STATUS_TERMINAL, error_code="decode_error", error_detail=detail)
        _finish(run, [])
        return ImageOutcome(status=STATUS_TERMINAL, error_detail=detail,
                            decode_seconds=time.perf_counter() - t0)
    decode_seconds = time.perf_counter() - t0

    d = decoded.descriptor
    run.update(
        source_hash=d.source_hash,
        source_hash_version=d.source_hash_version,
        rendition_hash=d.rendition_hash,
        rendition_version=d.descriptor_version,
        orientation=d.orientation,
        display_width=d.display_width,
        display_height=d.display_height,
        decode_route=d.decode_route.value,
    )

    current = get_current_run(image_id)
    if current is not None and is_unchanged(current, ctx.config_hash, d):
        return ImageOutcome(status=current["status"], unchanged=True, decode_seconds=decode_seconds)

    t1 = time.perf_counter()
    try:
        boxes = ctx.detector.detect_boxes(decoded.image)
    except Exception as exc:  # noqa: BLE001 — inference failure is retryable (AC-9)
        detail = redact_error_detail(f"detect_error: {exc}")
        run.update(status=STATUS_RETRYABLE, is_retryable=True,
                   error_code="detect_error", error_detail=detail)
        _finish(run, [])
        return ImageOutcome(status=STATUS_RETRYABLE, error_detail=detail,
                            decode_seconds=decode_seconds,
                            inference_seconds=time.perf_counter() - t1)
    inference_seconds = time.perf_counter() - t1

    regions = boxes[:max_regions]
    run["status"] = STATUS_DETECTED if regions else STATUS_NO_DETECTION
    _finish(run, regions)
    return ImageOutcome(
        status=run["status"],
        regions=len(regions),
        decode_seconds=decode_seconds,
        inference_seconds=inference_seconds,
    )
