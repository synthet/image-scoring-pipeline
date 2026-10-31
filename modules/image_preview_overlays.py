"""Read cached camera AF and diagnostic eye points for the image inspector."""

from __future__ import annotations

import math

from modules.keypoints import EYE_CONSUMER_MIN_CONF


def get_image_preview_overlays(database, image_id: int) -> dict:
    """Return display-normalized artifacts without running inference or writing data."""
    exif = database.get_image_exif(image_id) or {}
    af = exif.get("af_metadata")
    result = {"af_metadata": af if isinstance(af, dict) else None, "eye_keypoints": None}
    try:
        rows = database.get_connector().query(
            """
            SELECT r.display_width, r.display_height, k.name, k.x, k.y, k.confidence
            FROM image_localization_selections s
            JOIN image_localization_runs r ON r.id = s.localization_run_id AND r.image_id = s.image_id
            JOIN image_keypoint_runs kr ON kr.region_id = s.region_id AND kr.is_current AND kr.status = 'detected'
            JOIN image_region_keypoints k ON k.keypoint_run_id = kr.id
            WHERE s.image_id = ? AND s.detector_key = 'bird' AND s.revoked_at IS NULL
              AND localization_selection_is_fresh(s.id)
              AND r.display_width > 0 AND r.display_height > 0
              AND k.visible AND k.confidence >= ? AND k.name IN ('left_eye', 'right_eye')
            """,
            (image_id, EYE_CONSUMER_MIN_CONF),
        )
    except Exception as exc:
        if getattr(exc, "pgcode", None) == "42P01":
            return result
        raise

    points = []
    dimensions = None
    for row in rows:
        try:
            x, y, confidence = float(row["x"]), float(row["y"]), float(row["confidence"])
            width, height = int(row["display_width"]), int(row["display_height"])
            if not all(math.isfinite(value) for value in (x, y, confidence)):
                continue
            if not (0 <= x <= 1 and 0 <= y <= 1 and EYE_CONSUMER_MIN_CONF <= confidence <= 1):
                continue
            if width <= 0 or height <= 0 or row["name"] not in ("left_eye", "right_eye"):
                continue
            if dimensions is not None and dimensions != (width, height):
                continue
            dimensions = (width, height)
            points.append({"name": row["name"], "x": x, "y": y, "confidence": confidence})
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    if points:
        result["eye_keypoints"] = {"display_width": dimensions[0], "display_height": dimensions[1], "points": points}
    return result
