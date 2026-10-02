"""Production localization selections and the ``images.bird_bbox`` projection (#484, epic #345).

A *selection* is the revocable decision that one stored ``image_regions`` row is the
production answer for an image and detector, with who decided (``selected_by``: rule version
and hash) and why (``evidence``). The region itself stays an immutable localization artifact.

``images.bird_bbox`` remains the legacy read path (gallery, species, crops). For a selected
image it is a projection of the active selection, written here and only here, in the exact
legacy pixel shape. The selection row keeps the projected value and the value it replaced, so:

* ``select_region`` refuses when ``bird_bbox`` no longer holds the value the caller expects;
* ``revoke_selection`` restores the replaced value, and leaves ``bird_bbox`` alone when it
  was changed outside the selection since (the selection is revoked either way).

Both run in one transaction with the ``images`` row locked.
"""

from __future__ import annotations

import json
from typing import Any

DETECTOR_KEY = "bird"

#: ``expect_bird_bbox`` default meaning "do not check the current value".
ANY = object()

_ACTIVE_SQL = """
    SELECT id, localization_run_id, region_id, selected_by, evidence, previous_bird_bbox,
           projected_bird_bbox, selected_at
    FROM image_localization_selections
    WHERE image_id = ? AND detector_key = ? AND revoked_at IS NULL
"""

_REGION_SQL = """
    SELECT r.id, r.confidence, r.x1, r.y1, r.x2, r.y2, run.id AS run_id, run.image_id,
           run.detector_key, run.display_width, run.display_height
    FROM image_regions r
    JOIN image_localization_runs run ON run.id = r.localization_run_id
    WHERE r.id = ?
"""


def _json(value: Any) -> Any:
    if isinstance(value, (str, bytes)):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def legacy_bbox_payload(region: dict[str, Any], width: int, height: int) -> dict[str, Any]:
    """``images.bird_bbox`` value for a normalized region, in ``bird_detection``'s pixel shape."""
    x1, y1, x2, y2 = (float(region[k]) for k in ("x1", "y1", "x2", "y2"))
    conf = region.get("confidence")
    return {
        "x1": int(round(x1 * width)), "y1": int(round(y1 * height)),
        "x2": int(round(x2 * width)), "y2": int(round(y2 * height)),
        "conf": round(float(conf), 4) if conf is not None else None,
        "img_w": int(width), "img_h": int(height),
        "area_frac": round(max(0.0, x2 - x1) * max(0.0, y2 - y1), 6),
    }


def active_selection(image_id: int, detector_key: str = DETECTOR_KEY) -> dict[str, Any] | None:
    from modules import db

    return db.get_connector().query_one(_ACTIVE_SQL, (int(image_id), detector_key))


def select_region(
    image_id: int,
    region_id: int,
    selected_by: str,
    evidence: dict[str, Any] | None = None,
    *,
    detector_key: str = DETECTOR_KEY,
    expect_bird_bbox: Any = ANY,
) -> dict[str, Any]:
    """Select ``region_id`` as the production answer and project it into ``bird_bbox``.

    Returns ``{"status": ...}``; only ``"selected"`` changed anything. Other statuses:
    ``missing_image``, ``region_mismatch`` (wrong image/detector or unknown region),
    ``no_dimensions``, ``already_selected`` (same region), ``other_selection_active``,
    ``production_changed`` (``bird_bbox`` differs from ``expect_bird_bbox``).
    """
    from modules import db

    def _tx(tx) -> dict[str, Any]:
        image = tx.query_one("SELECT bird_bbox FROM images WHERE id = ? FOR UPDATE", (int(image_id),))
        if image is None:
            return {"status": "missing_image"}
        region = tx.query_one(_REGION_SQL, (int(region_id),))
        if region is None or region["image_id"] != int(image_id) or region["detector_key"] != detector_key:
            return {"status": "region_mismatch"}
        if not region["display_width"] or not region["display_height"]:
            return {"status": "no_dimensions"}
        active = tx.query_one(_ACTIVE_SQL, (int(image_id), detector_key))
        if active is not None:
            same = active["region_id"] == int(region_id)
            return {"status": "already_selected" if same else "other_selection_active",
                    "selection_id": active["id"]}
        current = _json(image["bird_bbox"])
        if expect_bird_bbox is not ANY and current != expect_bird_bbox:
            return {"status": "production_changed"}
        payload = legacy_bbox_payload(region, region["display_width"], region["display_height"])
        rows = tx.execute_returning(
            "INSERT INTO image_localization_selections (image_id, detector_key, localization_run_id, "
            "region_id, selected_by, evidence, previous_bird_bbox, projected_bird_bbox) "
            "VALUES (?, ?, ?, ?, ?, ?::jsonb, ?::jsonb, ?::jsonb) RETURNING id",
            (int(image_id), detector_key, region["run_id"], int(region_id), selected_by,
             json.dumps(evidence) if evidence is not None else None,
             json.dumps(current) if current is not None else None, json.dumps(payload)),
        )
        tx.execute("UPDATE images SET bird_bbox = ?::jsonb WHERE id = ?", (json.dumps(payload), int(image_id)))
        return {"status": "selected", "selection_id": int(rows[0]["id"]), "bird_bbox": payload}

    return db.get_connector().run_transaction(_tx)


def revoke_selection(image_id: int, reason: str, *, detector_key: str = DETECTOR_KEY) -> dict[str, Any]:
    """Revoke the active selection and restore the ``bird_bbox`` value it replaced.

    Returns ``{"status": "revoked"}`` when ``bird_bbox`` was restored, ``"revoked_bbox_kept"``
    when ``bird_bbox`` had been changed outside the selection (left untouched), or
    ``"no_active_selection"``.
    """
    from modules import db

    def _tx(tx) -> dict[str, Any]:
        image = tx.query_one("SELECT bird_bbox FROM images WHERE id = ? FOR UPDATE", (int(image_id),))
        active = tx.query_one(_ACTIVE_SQL, (int(image_id), detector_key))
        if image is None or active is None:
            return {"status": "no_active_selection"}
        restored = _json(image["bird_bbox"]) == _json(active["projected_bird_bbox"])
        if restored:
            previous = _json(active["previous_bird_bbox"])
            tx.execute("UPDATE images SET bird_bbox = ?::jsonb WHERE id = ?",
                       (json.dumps(previous) if previous is not None else None, int(image_id)))
        tx.execute("UPDATE image_localization_selections SET revoked_at = CURRENT_TIMESTAMP, "
                   "revoked_reason = ? WHERE id = ?", (reason, active["id"]))
        return {"status": "revoked" if restored else "revoked_bbox_kept", "selection_id": active["id"]}

    return db.get_connector().run_transaction(_tx)
