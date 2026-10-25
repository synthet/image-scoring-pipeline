"""
EXIF metadata extraction for caching in IMAGE_EXIF table.

Uses exiftool -j (JSON output) to extract standard tags. Maps ExifTool tag names
to IMAGE_EXIF column names. Requires exiftool in PATH.
"""

import json
import logging
import math
import os
import subprocess
from collections.abc import Callable
from typing import Any

from modules import utils

logger = logging.getLogger(__name__)

_EXIFTOOL_PATH = None


def _get_exiftool_path():
    global _EXIFTOOL_PATH
    if _EXIFTOOL_PATH is None:
        _EXIFTOOL_PATH = __import__("shutil").which("exiftool")
    return _EXIFTOOL_PATH


def get_exiftool_path():
    """Return path to exiftool binary, or None if not on PATH."""
    return _get_exiftool_path()


def get_exiftool_timeout_seconds(*, write: bool = False) -> int:
    """
    Subprocess timeout for exiftool. Writes (especially large RAW on slow mounts)
    need more time than read-only JSON extraction.
    Override via config: exif.exiftool_read_timeout_seconds / exif.exiftool_write_timeout_seconds.
    """
    from modules.config import get_config_value

    key = "exif.exiftool_write_timeout_seconds" if write else "exif.exiftool_read_timeout_seconds"
    default = 120 if write else 30
    raw = get_config_value(key, default)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return default
    return max(5, min(n, 3600))


# ExifTool tag names -> our IMAGE_EXIF column names
_EXIF_TAG_MAP = {
    "Make": "make",
    "Model": "model",
    "LensModel": "lens_model",
    "Lens": "lens_model",  # fallback
    "LensID": "lens_model",
    "LensType": "lens_model",
    "FocalLength": "focal_length",
    "FocalLengthIn35mmFormat": "focal_length_35mm",
    "DateTimeOriginal": "date_time_original",
    "CreateDate": "create_date",
    "ExposureTime": "exposure_time",
    "FNumber": "f_number",
    "ISO": "iso",
    "ExposureCompensation": "exposure_compensation",
    "ImageWidth": "image_width",
    "ImageHeight": "image_height",
    "Orientation": "orientation",
    "Flash": "flash",
    "ImageUniqueID": "image_unique_id",
    "ShutterCount": "shutter_count",
    "SubSecTimeOriginal": "sub_sec_time_original",
    "GPSLatitude": "gps_latitude",
    "GPSLongitude": "gps_longitude",
    "GPSAltitude": "gps_altitude",
}


_NIKON_AF_AREA_MODES = {
    0: "Pinpoint",
    1: "Single",
    2: "Dynamic Area",
    3: "Wide (S)",
    4: "Wide (L)",
    5: "Auto",
    6: "3D-tracking",
    7: "Group-area",
    128: "Single",
    129: "Auto (41 points)",
    192: "Pinpoint",
    193: "Single",
    194: "Dynamic Area",
    195: "Wide (S)",
    196: "Wide (L)",
    197: "Auto",
    204: "Dynamic Area (S)",
    205: "Dynamic Area (M)",
    206: "Dynamic Area (L)",
    207: "3D-tracking",
    208: "Wide (C1/C2)",
}


def _finite_af_number(value: Any) -> float | None:
    """Read a numeric AF tag without admitting booleans, NaN or infinity."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _parse_crop_area(val: Any) -> list[int] | None:
    if not val:
        return None
    parts = val if isinstance(val, (list, tuple)) else str(val).replace(",", " ").split()
    if len(parts) != 4:
        return None
    numbers = [_finite_af_number(value) for value in parts]
    if any(value is None or not value.is_integer() for value in numbers):
        return None
    return [int(value) for value in numbers]


def _parse_af_metadata(raw: dict) -> dict | None:
    """Parse autofocus MakerNote metadata (Nikon AFInfo2 tag 0x00B7, CropArea, and lock state)."""
    if "AFCoordinatesAvailable" in raw and _finite_af_number(raw["AFCoordinatesAvailable"]) != 1:
        return None

    af_img_w = raw.get("AFImageWidth")
    af_img_h = raw.get("AFImageHeight")
    area_x = raw.get("AFAreaXPosition")
    area_y = raw.get("AFAreaYPosition")
    area_w = raw.get("AFAreaWidth")
    area_h = raw.get("AFAreaHeight")

    if not (af_img_w and af_img_h and area_x is not None and area_y is not None and area_w and area_h):
        return None

    values = [_finite_af_number(value) for value in
              (af_img_w, af_img_h, area_x, area_y, area_w, area_h)]
    if any(value is None for value in values):
        return None
    af_img_w_f, af_img_h_f, area_x_f, area_y_f, area_w_f, area_h_f = values

    dimensions = (af_img_w_f, af_img_h_f, area_w_f, area_h_f)
    if any(value <= 0 or not value.is_integer() for value in dimensions):
        return None

    norm_left = (area_x_f - area_w_f / 2.0) / af_img_w_f
    norm_top = (area_y_f - area_h_f / 2.0) / af_img_h_f
    norm_width = area_w_f / af_img_w_f
    norm_height = area_h_f / af_img_h_f
    if not all(math.isfinite(value) for value in (norm_left, norm_top, norm_width, norm_height)):
        return None

    mode_val = raw.get("AFAreaMode")
    mode_code = None
    if isinstance(mode_val, str) and not mode_val.isdigit():
        mode_str = mode_val
        mode_code = mode_val
    elif isinstance(mode_val, (int, float, str)):
        number = _finite_af_number(mode_val)
        if number is None:
            mode_str = "Unknown"
        else:
            code = int(number)
            mode_str = _NIKON_AF_AREA_MODES.get(code, f"Mode {code}")
            mode_code = mode_val if isinstance(mode_val, (int, str)) else None
    else:
        mode_str = "Unknown"

    focus_res = raw.get("FocusResult")
    if focus_res is None:
        focus_res = raw.get("ContrastDetectAFInFocus")
    in_focus = (focus_res == 1 or str(focus_res).strip().lower() in ("focus", "in focus", "true", "1"))

    crop_area = _parse_crop_area(raw.get("CropArea"))

    focus_dist = _finite_af_number(raw.get("FocusDistance"))
    if focus_dist is not None and focus_dist < 0:
        focus_dist = None

    out = {
        "version": str(raw.get("AFInfo2Version") or ""),
        "mode": mode_str,
        "mode_code": mode_code,
        "in_focus": in_focus,
        "focus_distance_m": focus_dist,
        "area_x": int(area_x_f),
        "area_y": int(area_y_f),
        "area_w": int(area_w_f),
        "area_h": int(area_h_f),
        "af_image_w": int(af_img_w_f),
        "af_image_h": int(af_img_h_f),
        "crop_area": crop_area,
        "box": {
            "left": round(norm_left, 5),
            "top": round(norm_top, 5),
            "width": round(norm_width, 5),
            "height": round(norm_height, 5),
            "center_x": round(area_x_f / af_img_w_f, 5),
            "center_y": round(area_y_f / af_img_h_f, 5),
        },
    }

    if crop_area and len(crop_area) == 4:
        cx0, cy0, cw, ch = crop_area
        if cw > 0 and ch > 0 and (cw < af_img_w_f * 0.95 or ch < af_img_h_f * 0.95):
            crop_left = (area_x_f - area_w_f / 2.0 - cx0) / float(cw)
            crop_top = (area_y_f - area_h_f / 2.0 - cy0) / float(ch)
            crop_width = area_w_f / float(cw)
            crop_height = area_h_f / float(ch)
            out["crop_box"] = {
                "left": round(crop_left, 5),
                "top": round(crop_top, 5),
                "width": round(crop_width, 5),
                "height": round(crop_height, 5),
                "center_x": round((area_x_f - cx0) / float(cw), 5),
                "center_y": round((area_y_f - cy0) / float(ch), 5),
            }

    return out


def extract_exif(image_path: str, image_id: int = None) -> dict | None:
    """
    Extract EXIF metadata from an image file using exiftool.

    Args:
        image_path: Path to the image file (or XMP sidecar's base path)
        image_id: Optional image_id for resolve_file_path batch cache

    Returns:
        Dict with keys matching IMAGE_EXIF columns, or None on failure.
        Lens fallback: LensModel > Lens > LensID > LensType
    """
    exiftool = _get_exiftool_path()
    if not exiftool:
        logger.debug("exiftool not found in PATH")
        return None

    resolved = utils.resolve_file_path(image_path, image_id)
    if not resolved:
        resolved = utils.convert_path_to_local(image_path)
    if not resolved or not os.path.exists(resolved):
        logger.debug("File not found: %s", image_path)
        return None

    tags_to_fetch = [
        "Make", "Model", "LensModel", "Lens", "LensID", "LensType",
        "FocalLength", "FocalLengthIn35mmFormat",
        "DateTimeOriginal", "CreateDate",
        "ExposureTime", "FNumber", "ISO", "ExposureCompensation",
        "ImageWidth", "ImageHeight", "Orientation", "Flash",
        "ImageUniqueID", "ShutterCount", "SubSecTimeOriginal",
        "GPSLatitude", "GPSLongitude", "GPSAltitude",
        "AFInfo2Version", "AFCoordinatesAvailable", "AFAreaMode",
        "AFAreaXPosition", "AFAreaYPosition", "AFAreaWidth", "AFAreaHeight",
        "AFImageWidth", "AFImageHeight", "CropArea",
        "FocusResult", "ContrastDetectAFInFocus", "FocusDistance",
    ]

    try:
        # -n: print numeric values (e.g. decimal degrees for GPS)
        cmd = [exiftool, "-j", "-s", "-n", "-ee"] + [f"-{t}" for t in tags_to_fetch] + [resolved]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=get_exiftool_timeout_seconds(write=False)
        )
        if result.returncode != 0:
            logger.debug("exiftool failed for %s: %s", image_path, result.stderr)
            return None

        data = json.loads(result.stdout)
        if not data or not isinstance(data, list):
            return None

        raw = data[0]
        out = {}

        for exif_tag, our_col in _EXIF_TAG_MAP.items():
            val = raw.get(exif_tag)
            if val is None or (isinstance(val, str) and val.strip() in ("-", "")):
                continue
            if our_col in ("gps_latitude", "gps_longitude", "gps_altitude"):
                if isinstance(val, (int, float)):
                    if our_col not in out:
                        out[our_col] = float(val)
                else:
                    try:
                        f = float(str(val).replace(",", ".").strip())
                        if our_col not in out:
                            out[our_col] = f
                    except (ValueError, TypeError):
                        pass
            else:
                # Only set if not already set (first wins for lens fallbacks)
                if our_col not in out:
                    out[our_col] = val

        if any(k in out for k in ("gps_latitude", "gps_longitude")):
            out["gps_position_source"] = "exif"

        # Lens fallback order: LensModel > Lens > LensID > LensType
        if "lens_model" not in out:
            for tag in ("LensModel", "Lens", "LensID", "LensType"):
                v = raw.get(tag)
                if v and str(v).strip() not in ("-", ""):
                    out["lens_model"] = v
                    break

        af_meta = _parse_af_metadata(raw)
        af_tags_present = any(tag in raw for tag in (
            "AFInfo2Version", "AFCoordinatesAvailable", "AFImageWidth", "AFImageHeight",
            "AFAreaXPosition", "AFAreaYPosition", "AFAreaWidth", "AFAreaHeight",
        ))
        if af_meta is not None or af_tags_present:
            # Explicitly invalidate cached geometry; omission means an unrelated partial update.
            out["af_metadata"] = af_meta

        return out if out else None

    except subprocess.TimeoutExpired:
        logger.warning("exiftool timeout for %s", image_path)
        return None
    except json.JSONDecodeError as e:
        logger.warning("exiftool JSON parse error for %s: %s", image_path, e)
        return None
    except Exception as e:
        logger.warning("extract_exif failed for %s: %s", image_path, e)
        return None


def extract_and_upsert_exif(image_path: str, image_id: int) -> bool:
    """
    Extract EXIF from image and upsert into IMAGE_EXIF.

    Returns True if extraction and upsert succeeded.
    """
    from modules import db

    data = extract_exif(image_path, image_id)
    if not data:
        return False
    existing = db.get_image_exif(image_id) or {}
    merged = _merge_exif_for_upsert(existing, data)
    return db.upsert_image_exif(image_id, merged)


def backfill_exif_dates(
    limit: int | None = None,
    *,
    on_progress: Callable[[int, int, dict], Any] | None = None,
) -> dict:
    """
    Refresh EXIF + XMP caches for images that still have no effective capture date.

    Selects rows where COALESCE(ex.date_time_original, ex.create_date, xm.create_date)
    is NULL, then re-reads XMP sidecar and exiftool (-ee for embedded RAW metadata).

    Args:
        limit: Optional max rows per call (use for batching large libraries). Candidates are
            ordered randomly each run so batches spread across the library instead of always
            starting at the lowest ``image_id``.
        on_progress: Optional callback ``(done_checked, total_candidates, stats_copy)`` for
            batched UI/logs (``done_checked==0`` is a pre-loop banner when ``total_candidates>0``).

    Returns:
        dict: checked, updated, skipped_no_file, skipped_no_date, errors.
    """
    from modules import db
    from modules import xmp as xmp_mod

    limit_clause = f" LIMIT {int(limit)}" if limit else ""
    rows = db.get_connector().query(
        f"""SELECT i.id AS image_id, i.file_path
            FROM images i
            LEFT JOIN image_exif ex ON ex.image_id = i.id
            LEFT JOIN image_xmp xm ON xm.image_id = i.id
            WHERE COALESCE(ex.date_time_original, ex.create_date, xm.create_date) IS NULL
            ORDER BY RAND(){limit_clause}"""
    )

    stats = {"checked": 0, "updated": 0, "skipped_no_file": 0, "skipped_no_date": 0, "errors": 0}
    total = len(rows)
    if on_progress is not None:
        on_progress(0, total, dict(stats))

    def _maybe_progress_after_row() -> None:
        if on_progress is None:
            return
        c = stats["checked"]
        if total == 0 or c % 75 == 0 or c >= total:
            on_progress(c, total, dict(stats))

    for row in rows:
        stats["checked"] += 1
        image_id = row["image_id"]
        file_path = row["file_path"]
        try:
            resolved = utils.resolve_file_path(file_path, image_id)
            if not resolved:
                resolved = utils.convert_path_to_local(file_path)
            if not resolved or not os.path.exists(resolved):
                stats["skipped_no_file"] += 1
                logger.debug("backfill skip image_id=%s: file not found (%s)", image_id, file_path)
                _maybe_progress_after_row()
                continue
            xmp_mod.extract_and_upsert_xmp(resolved, image_id)
            data = extract_exif(resolved, image_id)
            if data:
                existing = db.get_image_exif(image_id) or {}
                merged = _merge_exif_for_upsert(existing, data)
                if not db.upsert_image_exif(image_id, merged):
                    stats["errors"] += 1
                    _maybe_progress_after_row()
                    continue
            exif_row = db.get_image_exif(image_id) or {}
            xmp_row = db.get_image_xmp(image_id) or {}
            if (
                exif_row.get("date_time_original")
                or exif_row.get("create_date")
                or xmp_row.get("create_date")
            ):
                stats["updated"] += 1
            else:
                stats["skipped_no_date"] += 1
                logger.debug(
                    "backfill skip image_id=%s: no capture date in EXIF or XMP (%s)",
                    image_id,
                    file_path,
                )
        except Exception as e:
            logger.warning("backfill_exif_dates failed for image_id %s: %s", image_id, e)
            stats["errors"] += 1
        _maybe_progress_after_row()

    logger.info("backfill_exif_dates: %s", stats)
    return stats


# Keys accepted by db.upsert_image_exif (excluding image_id / extracted_at).
_IMAGE_EXIF_UPSERT_KEYS = (
    "make",
    "model",
    "lens_model",
    "focal_length",
    "focal_length_35mm",
    "date_time_original",
    "create_date",
    "exposure_time",
    "f_number",
    "iso",
    "exposure_compensation",
    "image_width",
    "image_height",
    "orientation",
    "flash",
    "image_unique_id",
    "shutter_count",
    "sub_sec_time_original",
    "gps_latitude",
    "gps_longitude",
    "gps_altitude",
    "gps_position_source",
    "location_resolved",
    "geocoded_at",
    "geocode_provider",
    "af_metadata",
)


def _merge_exif_for_upsert(existing: dict | None, fresh: dict) -> dict:
    """Merge a full EXIF row with a fresh exiftool dict so partial extractions do not wipe columns."""
    merged: dict = {}
    if existing:
        for k in _IMAGE_EXIF_UPSERT_KEYS:
            if k in existing:
                merged[k] = existing[k]
    merged.update(fresh)
    return merged


def _exif_row_has_camera_and_lens(ex_row: dict | None) -> bool:
    if not ex_row:
        return False
    cam = (str(ex_row.get("model") or "").strip() or str(ex_row.get("make") or "").strip())
    lens = str(ex_row.get("lens_model") or "").strip()
    return bool(cam and lens)


def _exif_row_has_gps_coords(ex_row: dict | None) -> bool:
    if not ex_row:
        return False
    lat, lon = ex_row.get("gps_latitude"), ex_row.get("gps_longitude")
    if lat is None or lon is None:
        return False
    try:
        float(lat)
        float(lon)
    except (TypeError, ValueError):
        return False
    return True


def backfill_exif_camera_lens(
    limit: int | None = None,
    *,
    path_like: str | None = None,
    on_progress: Callable[[int, int, dict], Any] | None = None,
    tool_key: str | None = None,
) -> dict:
    """
    Re-extract EXIF from disk for rows missing camera and/or lens (image_exif.make/model or lens_model).

    Used when gallery backup/sync skips files because ``exif_model`` / ``exif_lens_model`` are empty.
    Requires ``exiftool`` on PATH. Merges with existing ``image_exif`` so partial tags do not NULL out
    other cached columns.

    Args:
        limit: Optional max rows per call (random order each run; see :func:`backfill_exif_dates`).
        path_like: Optional SQL ``LIKE`` pattern on ``images.file_path`` (e.g. ``%/Photos/Z6ii/%``).
        on_progress: Optional ``(done_checked, total_candidates, stats_copy)`` for UI milestones.
        tool_key: When set on Postgres, order candidates by Pipeline Tools folder round-robin
            (least recently touched folders first) instead of ``ORDER BY RAND()``.

    Returns:
        dict: checked, updated, skipped_no_file, skipped_no_exif, skipped_still_missing, errors.
    """
    from modules import db
    from modules.db_legacy import _get_db_engine

    path_clause = ""
    params_list: list[Any] = []
    if path_like:
        path_clause = " AND i.file_path LIKE ?"
        params_list.append(path_like)

    use_rr = bool(tool_key) and _get_db_engine() == "postgres"
    limit_clause = f" LIMIT {int(limit)}" if limit else ""
    if use_rr:
        join_sql = """
            JOIN folders f ON f.id = i.folder_id
            LEFT JOIN pipeline_tool_folder_last_touch pt ON pt.folder_id = f.id AND pt.tool_key = ?
        """
        select_cols = "i.id AS image_id, i.file_path, i.folder_id AS folder_id"
        order_sql = "ORDER BY pt.last_touched_at NULLS FIRST, i.id"
        q_params = (tool_key,) + tuple(params_list)
        rows = db.get_connector().query(
            f"""SELECT {select_cols}
            FROM images i
            {join_sql}
            LEFT JOIN image_exif ex ON ex.image_id = i.id
            WHERE (
                ex.image_id IS NULL
                OR COALESCE(
                    NULLIF(TRIM(COALESCE(ex.model, '')), ''),
                    NULLIF(TRIM(COALESCE(ex.make, '')), '')
                ) IS NULL
                OR NULLIF(TRIM(COALESCE(ex.lens_model, '')), '') IS NULL
            ){path_clause}
            {order_sql}{limit_clause}""",
            q_params if q_params else None,
        )
    else:
        rows = db.get_connector().query(
            f"""SELECT i.id AS image_id, i.file_path
            FROM images i
            LEFT JOIN image_exif ex ON ex.image_id = i.id
            WHERE (
                ex.image_id IS NULL
                OR COALESCE(
                    NULLIF(TRIM(COALESCE(ex.model, '')), ''),
                    NULLIF(TRIM(COALESCE(ex.make, '')), '')
                ) IS NULL
                OR NULLIF(TRIM(COALESCE(ex.lens_model, '')), '') IS NULL
            ){path_clause}
            ORDER BY RAND(){limit_clause}""",
            tuple(params_list) if params_list else None,
        )

    stats = {
        "checked": 0,
        "updated": 0,
        "skipped_no_file": 0,
        "skipped_no_exif": 0,
        "skipped_still_missing": 0,
        "errors": 0,
    }
    total = len(rows)
    if on_progress is not None:
        on_progress(0, total, dict(stats))

    def _maybe_progress_after_row() -> None:
        if on_progress is None:
            return
        c = stats["checked"]
        if total == 0 or c % 75 == 0 or c >= total:
            on_progress(c, total, dict(stats))

    for row in rows:
        stats["checked"] += 1
        image_id = row["image_id"]
        file_path = row["file_path"]
        try:
            resolved = utils.resolve_file_path(file_path, image_id)
            if not resolved:
                resolved = utils.convert_path_to_local(file_path)
            if not resolved or not os.path.exists(resolved):
                stats["skipped_no_file"] += 1
                logger.debug("backfill_exif_camera_lens skip image_id=%s: file not found (%s)", image_id, file_path)
                _maybe_progress_after_row()
                continue

            existing = db.get_image_exif(image_id)
            fresh = extract_exif(resolved, image_id)
            if not fresh:
                stats["skipped_no_exif"] += 1
                logger.debug(
                    "backfill_exif_camera_lens skip image_id=%s: no EXIF from exiftool (%s)",
                    image_id,
                    file_path,
                )
                _maybe_progress_after_row()
                continue

            merged = _merge_exif_for_upsert(existing, fresh)
            if not db.upsert_image_exif(image_id, merged):
                stats["errors"] += 1
                _maybe_progress_after_row()
                continue

            exif_row = db.get_image_exif(image_id) or {}
            if _exif_row_has_camera_and_lens(exif_row):
                stats["updated"] += 1
                if use_rr:
                    fid = row.get("folder_id")
                    if fid is not None:
                        from modules.pipeline_tool_folder_touch import (
                            upsert_pipeline_tool_folder_touch,
                        )

                        upsert_pipeline_tool_folder_touch(tool_key, int(fid))
            else:
                stats["skipped_still_missing"] += 1
                logger.debug(
                    "backfill_exif_camera_lens still missing camera/lens after upsert image_id=%s (%s)",
                    image_id,
                    file_path,
                )
        except Exception as e:
            logger.warning("backfill_exif_camera_lens failed for image_id %s: %s", image_id, e)
            stats["errors"] += 1
        _maybe_progress_after_row()

    logger.info("backfill_exif_camera_lens: %s", stats)
    return stats


def backfill_exif_gps(
    limit: int | None = None,
    *,
    path_like: str | None = None,
    on_progress: Callable[[int, int, dict], Any] | None = None,
    tool_key: str | None = None,
) -> dict:
    """
    Re-extract EXIF from disk for rows missing ``gps_latitude`` / ``gps_longitude`` in ``image_exif``.

    Fills GPS from embedded/sidecar metadata where present. Requires ``exiftool`` on PATH.
    Merges with existing ``image_exif`` so reverse-geocode fields are not wiped when fresh EXIF lacks them.

    Args:
        limit: Optional max rows per call (random order each run; see :func:`backfill_exif_dates`).
        path_like: Optional SQL ``LIKE`` pattern on ``images.file_path``.
        on_progress: Optional ``(done_checked, total_candidates, stats_copy)`` for UI milestones.
        tool_key: When set on Postgres, order by Pipeline Tools folder round-robin instead of ``RAND()``.

    Returns:
        dict: checked, updated, skipped_no_file, skipped_no_exif, skipped_still_missing, errors.
    """
    from modules import db
    from modules.db_legacy import _get_db_engine

    path_clause = ""
    params_list: list[Any] = []
    if path_like:
        path_clause = " AND i.file_path LIKE ?"
        params_list.append(path_like)

    use_rr = bool(tool_key) and _get_db_engine() == "postgres"
    limit_clause = f" LIMIT {int(limit)}" if limit else ""
    if use_rr:
        join_sql = """
            JOIN folders f ON f.id = i.folder_id
            LEFT JOIN pipeline_tool_folder_last_touch pt ON pt.folder_id = f.id AND pt.tool_key = ?
        """
        select_cols = "i.id AS image_id, i.file_path, i.folder_id AS folder_id"
        order_sql = "ORDER BY pt.last_touched_at NULLS FIRST, i.id"
        q_params = (tool_key,) + tuple(params_list)
        rows = db.get_connector().query(
            f"""SELECT {select_cols}
            FROM images i
            {join_sql}
            LEFT JOIN image_exif ex ON ex.image_id = i.id
            WHERE (
                ex.image_id IS NULL
                OR ex.gps_latitude IS NULL
                OR ex.gps_longitude IS NULL
            ){path_clause}
            {order_sql}{limit_clause}""",
            q_params if q_params else None,
        )
    else:
        rows = db.get_connector().query(
            f"""SELECT i.id AS image_id, i.file_path
            FROM images i
            LEFT JOIN image_exif ex ON ex.image_id = i.id
            WHERE (
                ex.image_id IS NULL
                OR ex.gps_latitude IS NULL
                OR ex.gps_longitude IS NULL
            ){path_clause}
            ORDER BY RAND(){limit_clause}""",
            tuple(params_list) if params_list else None,
        )

    stats = {
        "checked": 0,
        "updated": 0,
        "skipped_no_file": 0,
        "skipped_no_exif": 0,
        "skipped_still_missing": 0,
        "errors": 0,
    }
    total = len(rows)
    if on_progress is not None:
        on_progress(0, total, dict(stats))

    def _maybe_progress_after_row() -> None:
        if on_progress is None:
            return
        c = stats["checked"]
        if total == 0 or c % 75 == 0 or c >= total:
            on_progress(c, total, dict(stats))

    for row in rows:
        stats["checked"] += 1
        image_id = row["image_id"]
        file_path = row["file_path"]
        try:
            resolved = utils.resolve_file_path(file_path, image_id)
            if not resolved:
                resolved = utils.convert_path_to_local(file_path)
            if not resolved or not os.path.exists(resolved):
                stats["skipped_no_file"] += 1
                logger.debug("backfill_exif_gps skip image_id=%s: file not found (%s)", image_id, file_path)
                _maybe_progress_after_row()
                continue

            existing = db.get_image_exif(image_id)
            fresh = extract_exif(resolved, image_id)
            if not fresh:
                stats["skipped_no_exif"] += 1
                logger.debug(
                    "backfill_exif_gps skip image_id=%s: no EXIF from exiftool (%s)",
                    image_id,
                    file_path,
                )
                _maybe_progress_after_row()
                continue

            merged = _merge_exif_for_upsert(existing, fresh)
            if not db.upsert_image_exif(image_id, merged):
                stats["errors"] += 1
                _maybe_progress_after_row()
                continue

            exif_row = db.get_image_exif(image_id) or {}
            if _exif_row_has_gps_coords(exif_row):
                stats["updated"] += 1
                if use_rr:
                    fid = row.get("folder_id")
                    if fid is not None:
                        from modules.pipeline_tool_folder_touch import (
                            upsert_pipeline_tool_folder_touch,
                        )

                        upsert_pipeline_tool_folder_touch(tool_key, int(fid))
            else:
                stats["skipped_still_missing"] += 1
                logger.debug(
                    "backfill_exif_gps still no GPS after upsert image_id=%s (%s)",
                    image_id,
                    file_path,
                )
        except Exception as e:
            logger.warning("backfill_exif_gps failed for image_id %s: %s", image_id, e)
            stats["errors"] += 1
        _maybe_progress_after_row()

    logger.info("backfill_exif_gps: %s", stats)
    return stats


def write_image_unique_id(image_path: str, uuid_str: str) -> bool:
    """
    Write ImageUniqueID to EXIF using exiftool.
    This modifies the original file.
    """
    exiftool = _get_exiftool_path()
    if not exiftool:
        return False

    local_path = utils.convert_path_to_local(image_path)
    if not os.path.exists(local_path):
        return False

    try:
        # -overwrite_original avoids creating .original backup files
        # ImageUniqueID is a standard EXIF tag
        cmd = [exiftool, "-overwrite_original", f"-ImageUniqueID={uuid_str}", local_path]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=get_exiftool_timeout_seconds(write=True)
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Failed to write ImageUniqueID to {image_path}: {e}")
        return False


def ensure_image_unique_id(image_path: str, provided_uuid: str = None) -> str | None:
    """
    Check if image has an ImageUniqueID. If not, write the provided one or generate a new one.
    
    Args:
        image_path: Local or remote path to image
        provided_uuid: Optional UUID to write if missing
        
    Returns:
        The existing or newly written UUID, or None on failure.
    """
    # 1. Check existing
    data = extract_exif(image_path)
    if data and data.get("image_unique_id"):
        return data["image_unique_id"]

    # 2. Need to write
    if not provided_uuid:
        from modules import db
        # We need some context for deterministic UUID if possible, but extract_exif 
        # already gave us most of it or we can just use random fallback via db utility
        provided_uuid = db.generate_image_uuid(data)

    if write_image_unique_id(image_path, provided_uuid):
        return provided_uuid

    return None
