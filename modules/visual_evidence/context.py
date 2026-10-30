"""Read-only provenance for one requested image; legacy geometry is never guessed."""
from __future__ import annotations

import os

from modules.rendition import source_identity


def load_context(image_id):
    from modules import db
    from modules.paths import resolve_to_existing
    connector = db.get_connector()
    row = connector.query_one("SELECT id, file_path FROM images WHERE id = ?", (image_id,))
    if not row:
        raise KeyError(image_id)
    path = resolve_to_existing(db.get_resolved_path(image_id, verified_only=False) or "") or resolve_to_existing(row["file_path"] or "")
    result = {"image_id": image_id, "path": path, "region": None, "keypoints": [],
              "region_id": None, "keypoint_run_id": None, "region_reason": "No verified primary subject region"}
    if not path or not os.path.isfile(path):
        result.update(source_hash="missing", source_hash_version="missing")
        return result
    identity, version = source_identity(path)
    result.update(source_hash=identity, source_hash_version=version)
    try:
        # The selected region is the production answer; the current run is often an
        # unpromoted shadow run, and freshness hides revoked or superseded selections (#714).
        region = connector.query_one(
            """SELECT g.id AS region_id, g.x1, g.y1, g.x2, g.y2, r.source_hash,
                      r.source_hash_version, r.rendition_hash, r.coord_space, r.orientation,
                      r.display_width, r.display_height, r.decode_route,
                      localization_selection_is_fresh(s.id) AS selection_fresh
               FROM image_localization_selections s
               JOIN image_regions g ON g.id = s.region_id
               JOIN image_localization_runs r ON r.id = s.localization_run_id AND r.image_id = s.image_id
               WHERE s.image_id = ? AND s.detector_key = 'bird' AND s.revoked_at IS NULL""", (image_id,))
        if not region:
            result["region_reason"] = "No authoritative bird selection"
            return result
        if region["selection_fresh"] is not True:
            result["region_reason"] = "Bird selection is stale for this source or policy"
            return result
        region.pop("selection_fresh")
        result["region_id"] = int(region["region_id"])
        if region["coord_space"] != "display_normalized" or region["source_hash"] != identity or region["source_hash_version"] != version:
            result["region_reason"] = "Subject coordinates need regeneration for this source rendition"
            return result
        coordinates = tuple(float(region[name]) for name in ("x1", "y1", "x2", "y2"))
        if not (0 <= coordinates[0] < coordinates[2] <= 1 and 0 <= coordinates[1] < coordinates[3] <= 1):
            return result
        result.update(region=list(coordinates), region_provenance=dict(region), region_reason=None)
        points = connector.query(
            """SELECT kr.id AS run_id, k.name, k.x, k.y, k.confidence, k.visible
               FROM image_keypoint_runs kr JOIN image_region_keypoints k ON k.keypoint_run_id = kr.id
               WHERE kr.region_id = ? AND kr.is_current AND kr.status = 'detected'
                 AND kr.provider_key = 'bird_head_pose' AND k.visible""", (result["region_id"],))
        for point in points:
            result["keypoint_run_id"] = int(point["run_id"])
            result["keypoints"].append({"name": point["name"], "x": float(point["x"]), "y": float(point["y"]),
                                        "confidence": float(point["confidence"] or 0), "visible": bool(point["visible"])})
    except Exception as exc:
        if getattr(exc, "pgcode", None) != "42P01":
            raise
    return result


def geometry_matches(context, rendition):
    provenance = context.get("region_provenance")
    if not context.get("region") or not provenance:
        return False
    if not provenance.get("rendition_hash") or provenance["rendition_hash"] != rendition.get("source_rendition_hash"):
        return False
    if provenance.get("orientation") != rendition.get("orientation") or provenance.get("decode_route") != rendition.get("decode_route"):
        return False
    width, height = provenance.get("display_width"), provenance.get("display_height")
    if not width or not height:
        return False
    # Accept rounding from a resized rendition, never an incompatible crop/aspect ratio.
    expected = float(width) / float(height)
    actual = rendition["display_width"] / rendition["display_height"]
    return abs(expected - actual) <= 2 / min(float(height), rendition["display_height"])
