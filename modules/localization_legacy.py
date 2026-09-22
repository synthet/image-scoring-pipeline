"""Read ``images.bird_bbox`` as normalized localization artifacts.

Stage 2 of the early-localization rollout (#370, epic #345). Two jobs:

1. **Classify** a legacy payload into the normalized status vocabulary, and project its
   geometry into normalized coordinates -- pure functions, no database.
2. **Import** the existing column into ``image_localization_runs`` / ``image_regions``
   without running any inference.

Nothing here writes ``images.bird_bbox``. That column stays the sole authority until
``localization.read_normalized_first`` is enabled, and it participates in live
bird-species work selection, so a dual-write would change production behaviour.

Retryability is **not** re-derived here: :data:`modules.bird_detection.RETRYABLE_BBOX_ERRORS`
is the single source of truth for which scan failures are worth retrying, and this module
defers to it. Duplicating that set is how the two would drift.

Imported rows carry ``legacy_unversioned`` detector and rendition provenance because the
historical detector version, decode route and EXIF orientation genuinely cannot be
recovered -- and must not be guessed from the *current* ``images`` row, which may describe
a file that changed since the scan.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from modules.bird_detection import RETRYABLE_BBOX_ERRORS

logger = logging.getLogger(__name__)

#: Provenance marker for rows imported from ``images.bird_bbox``. Detector version, config
#: hash and rendition identity were never recorded, so they cannot be reconstructed.
LEGACY_PROVENANCE = "legacy_unversioned"

#: The detector that produced every legacy box (``synthet/bird-detect-v0``).
LEGACY_DETECTOR_KEY = "bird"

#: Object class for a legacy box. The legacy column only ever held birds.
LEGACY_OBJECT_CLASS = "bird"

#: Legacy geometry is normalized against the ``img_w``/``img_h`` recorded *in the payload
#: itself*, not against the current image row. Its EXIF orientation was never stored, so
#: this is explicitly **not** the verified ``display_normalized`` space: a consumer must
#: verify dimensions and orientation before cropping from it.
LEGACY_COORD_SPACE = "legacy_unverified"

_STATUS_DETECTED = "detected"
_STATUS_NO_DETECTION = "no_detection"
_STATUS_RETRYABLE = "retryable_error"
_STATUS_TERMINAL = "terminal_error"

#: Error details carry absolute filesystem paths (``decode_error: cannot identify or decode
#: RAW image file '/mnt/d/Photos/...'``). Keep the code, drop the path.
_PATH_RE = re.compile(r"""['"]?(?:[A-Za-z]:)?[/\\][^\s'"]{2,}['"]?""")


def redact_error_detail(detail: str | None, *, max_len: int = 200) -> str | None:
    """Strip filesystem paths from a legacy error string.

    The verbatim original is preserved in ``image_localization_runs.legacy_payload`` for
    exact compatibility output; this is the form meant for logs, diagnostics and support
    bundles, where a full library path is noise at best.
    """
    if not detail:
        return None
    return _PATH_RE.sub("<path>", str(detail)).strip()[:max_len] or None


def _coerce_payload(raw: Any) -> Any:
    """Accept parsed JSONB, a JSON string, or bytes; return whatever it decodes to."""
    if isinstance(raw, (str, bytes)):
        text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        if not text.strip():
            return None
        try:
            return json.loads(text)
        except ValueError:
            # A payload that will not parse is still a real historical outcome. Report it
            # as terminal rather than dropping the row.
            return {"__unparseable__": text}
    return raw


def classify_legacy_bbox(raw: Any) -> dict[str, Any] | None:
    """Map one ``images.bird_bbox`` value onto the normalized run vocabulary.

    Returns ``None`` for ``NULL`` -- never attempted, so no run row exists. Otherwise a
    dict of ``status``, ``is_retryable``, ``error_code`` and ``error_detail``.

    The four shapes the column can hold (see ``migrations/versions/0033_image_bird_bbox.py``
    and ``modules/bird_detection.py:50-66``):

    ============================================  ==================
    payload                                       status
    ============================================  ==================
    ``NULL``                                      (no row)
    xyxy object                                   ``detected``
    ``{"detected": false}``                       ``no_detection``
    ``{"detected": false, "error": <retryable>}`` ``retryable_error``
    ``{"detected": false, "error": <other>}``     ``terminal_error``
    ============================================  ==================

    Anything unrecognised -- a non-object, an unparseable string, an object with neither
    geometry nor ``detected`` -- is ``terminal_error`` with code ``malformed_payload``.
    Guessing would be worse: a bad row must stay visible, not silently become
    "no detection".
    """
    payload = _coerce_payload(raw)
    if payload is None:
        return None

    if not isinstance(payload, dict):
        return {
            "status": _STATUS_TERMINAL,
            "is_retryable": False,
            "error_code": "malformed_payload",
            "error_detail": f"expected object, got {type(payload).__name__}",
        }

    if "__unparseable__" in payload:
        return {
            "status": _STATUS_TERMINAL,
            "is_retryable": False,
            "error_code": "malformed_payload",
            "error_detail": "payload is not valid JSON",
        }

    error = payload.get("error")
    if error:
        error_text = str(error)
        # `error` is stored as "<code>: <message>" by bbox_scan_failed(); the retryable set
        # is keyed on the bare code.
        code = error_text.split(":", 1)[0].strip()
        retryable = error_text in RETRYABLE_BBOX_ERRORS or code in RETRYABLE_BBOX_ERRORS
        return {
            "status": _STATUS_RETRYABLE if retryable else _STATUS_TERMINAL,
            "is_retryable": retryable,
            "error_code": code or "scan_failed",
            "error_detail": redact_error_detail(error_text),
        }

    if _has_geometry(payload):
        return {
            "status": _STATUS_DETECTED,
            "is_retryable": False,
            "error_code": None,
            "error_detail": None,
        }

    if payload.get("detected") is False:
        return {
            "status": _STATUS_NO_DETECTION,
            "is_retryable": False,
            "error_code": None,
            "error_detail": None,
        }

    return {
        "status": _STATUS_TERMINAL,
        "is_retryable": False,
        "error_code": "malformed_payload",
        "error_detail": f"no geometry and no detected flag; keys={sorted(payload)[:8]}",
    }


def _has_geometry(payload: dict) -> bool:
    return all(k in payload for k in ("x1", "y1", "x2", "y2"))


def normalized_region_from_legacy(raw: Any) -> dict[str, Any] | None:
    """Project a legacy pixel box into normalized 0..1 coordinates.

    Returns ``None`` when the payload has no usable geometry -- including a box whose
    ``img_w``/``img_h`` are missing or non-positive, or whose coordinates fall outside the
    frame or invert. Such a row still gets a ``detected`` run row (the detection is a
    historical fact) but no region, because a region that violates the schema's range and
    ordering constraints cannot be stored, and clamping it would invent data.

    Dimensions come from the payload's own ``img_w``/``img_h``, never from the current
    ``images`` row: the file may have changed since the scan.
    """
    payload = _coerce_payload(raw)
    if not isinstance(payload, dict) or not _has_geometry(payload):
        return None
    try:
        w = float(payload["img_w"])
        h = float(payload["img_h"])
        x1, y1 = float(payload["x1"]), float(payload["y1"])
        x2, y2 = float(payload["x2"]), float(payload["y2"])
    except (KeyError, TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None

    nx1, ny1, nx2, ny2 = x1 / w, y1 / h, x2 / w, y2 / h
    if not (0.0 <= nx1 < nx2 <= 1.0 and 0.0 <= ny1 < ny2 <= 1.0):
        return None

    conf = payload.get("conf")
    try:
        conf = float(conf) if conf is not None else None
    except (TypeError, ValueError):
        conf = None
    if conf is not None and not (0.0 <= conf <= 1.0):
        conf = None

    return {
        "object_class": LEGACY_OBJECT_CLASS,
        "rank": 0,
        "x1": nx1,
        "y1": ny1,
        "x2": nx2,
        "y2": ny2,
        "confidence": conf,
        "display_width": int(w),
        "display_height": int(h),
    }


def legacy_payload_from_normalized(run: dict[str, Any], regions: list[dict[str, Any]]) -> Any:
    """Rebuild the ``images.bird_bbox`` representation from normalized rows.

    This is the compatibility projection the rollout's stage 8 needs, and the check that
    the import lost nothing. For an imported row it returns the stored ``legacy_payload``
    verbatim -- byte-for-byte, malformed shapes included -- because that is the only way
    to guarantee the pre-migration API representation is reproducible.

    For a natively-written run (no ``legacy_payload``) it synthesizes the legacy shape
    from the normalized data.
    """
    stored = run.get("legacy_payload")
    if stored is not None:
        return stored

    status = run.get("status")
    if status == _STATUS_DETECTED and regions:
        best = min(regions, key=lambda r: r.get("rank", 0))
        w = run.get("display_width")
        h = run.get("display_height")
        if not w or not h:
            return {"detected": False}
        box: dict[str, Any] = {
            "x1": int(round(float(best["x1"]) * w)),
            "y1": int(round(float(best["y1"]) * h)),
            "x2": int(round(float(best["x2"]) * w)),
            "y2": int(round(float(best["y2"]) * h)),
            "img_w": int(w),
            "img_h": int(h),
        }
        if best.get("confidence") is not None:
            box["conf"] = float(best["confidence"])
        box["area_frac"] = (
            (float(best["x2"]) - float(best["x1"])) * (float(best["y2"]) - float(best["y1"]))
        )
        return box

    if status in (_STATUS_RETRYABLE, _STATUS_TERMINAL):
        return {"detected": False, "error": run.get("error_code") or "scan_failed"}

    return {"detected": False}


# ---------------------------------------------------------------------------
# Import — populate the normalized tables from images.bird_bbox
# ---------------------------------------------------------------------------

#: Columns written for every imported run. ``is_current`` is TRUE because an imported
#: attempt *is* the current artifact for its image until a real detector run supersedes it.
_RUN_COLUMNS = (
    "image_id", "detector_key", "detector_version", "detector_config_hash",
    "coord_space", "display_width", "display_height",
    "status", "is_retryable", "error_code", "error_detail",
    "is_current", "legacy_payload", "completed_at",
)


def import_legacy_bird_bbox(
    conn,
    *,
    batch_size: int = 2000,
    dry_run: bool = True,
    limit: int | None = None,
) -> dict[str, int]:
    """Copy ``images.bird_bbox`` into the normalized tables. Runs no inference.

    Idempotent by construction: the insert targets the partial unique index
    ``ux_ilr_current_image_detector`` with ``ON CONFLICT DO NOTHING``, so an image that
    already has a current ``bird`` run is skipped rather than duplicated. Re-running
    therefore preserves counts.

    Each batch commits its runs and their regions together, so an interrupted import
    leaves whole attempts behind, never a run without the regions it claimed to have.

    ``dry_run=True`` (the default) classifies everything and reports the counts without
    writing. Returns per-status counts plus ``regions``, ``skipped_existing`` and
    ``detected_without_region``.
    """
    from psycopg2.extras import execute_values

    counts: dict[str, int] = {
        "scanned": 0, "detected": 0, "no_detection": 0,
        "retryable_error": 0, "terminal_error": 0,
        "regions": 0, "skipped_existing": 0, "detected_without_region": 0,
    }

    # Keyset pagination rather than a server-side named cursor: each batch commits, and a
    # commit invalidates a named cursor. Paging by ``id`` also makes an interrupted import
    # resumable -- rows already imported are skipped by the ON CONFLICT below.
    read_sql = """
        SELECT id, bird_bbox FROM images
        WHERE bird_bbox IS NOT NULL AND id > %s
        ORDER BY id
        LIMIT %s
    """

    write_cur = conn.cursor()
    batch: list[tuple] = []
    regions_by_image: dict[int, dict] = {}

    def _flush() -> None:
        if not batch:
            return
        if dry_run:
            batch.clear()
            regions_by_image.clear()
            return
        rows = execute_values(
            write_cur,
            f"""INSERT INTO image_localization_runs ({', '.join(_RUN_COLUMNS)})
                VALUES %s
                ON CONFLICT (image_id, detector_key) WHERE is_current DO NOTHING
                RETURNING id, image_id""",
            batch,
            fetch=True,
        )
        counts["skipped_existing"] += len(batch) - len(rows)
        region_rows = []
        for run_id, image_id in rows:
            region = regions_by_image.get(image_id)
            if region:
                region_rows.append((
                    run_id, region["object_class"], region["rank"],
                    region["x1"], region["y1"], region["x2"], region["y2"],
                    region["confidence"],
                ))
        if region_rows:
            execute_values(
                write_cur,
                """INSERT INTO image_regions
                   (localization_run_id, object_class, rank, x1, y1, x2, y2, confidence)
                   VALUES %s""",
                region_rows,
            )
            counts["regions"] += len(region_rows)
        conn.commit()
        batch.clear()
        regions_by_image.clear()

    last_id = 0
    remaining = limit
    try:
        while True:
            page = batch_size if remaining is None else min(batch_size, remaining)
            if page <= 0:
                break
            with conn.cursor() as read_cur:
                read_cur.execute(read_sql, (last_id, page))
                page_rows = read_cur.fetchall()
            if not page_rows:
                break
            if remaining is not None:
                remaining -= len(page_rows)

            for image_id, raw in page_rows:
                last_id = image_id
                counts["scanned"] += 1
                verdict = classify_legacy_bbox(raw)
                if verdict is None:
                    continue
                counts[verdict["status"]] = counts.get(verdict["status"], 0) + 1

                region = normalized_region_from_legacy(raw)
                if verdict["status"] == _STATUS_DETECTED:
                    if region:
                        regions_by_image[image_id] = region
                        if dry_run:
                            counts["regions"] += 1
                    else:
                        # The detection happened; only its geometry is unusable. Keep the
                        # run row so the attempt stays visible rather than un-scanned.
                        counts["detected_without_region"] += 1

                batch.append((
                    image_id,
                    LEGACY_DETECTOR_KEY,
                    LEGACY_PROVENANCE,
                    LEGACY_PROVENANCE,
                    LEGACY_COORD_SPACE,
                    region["display_width"] if region else None,
                    region["display_height"] if region else None,
                    verdict["status"],
                    verdict["is_retryable"],
                    verdict["error_code"],
                    verdict["error_detail"],
                    True,
                    json.dumps(raw) if not isinstance(raw, (str, bytes)) else raw,
                    None,
                ))
            _flush()
    finally:
        write_cur.close()

    return counts
