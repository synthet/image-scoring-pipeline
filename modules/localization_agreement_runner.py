"""Persist ``bird_agreement`` runs after the bird run (spec 08, #780).

Shadow only. Behind ``localization.agreement.enabled`` (default false): while it is false nothing here
is loaded. No consumer reads these runs. ``confidence`` on a stored region is the agreement score, and
``provider_class_id`` names the source region, so the limit can change without re-running anything.

Runs are stored unpublished (``is_current`` false, AC-13). Keep-one's subject snapshots take every current
run of an image and require exactly one detected run, so a current ``bird_agreement`` run would make those
frames ambiguous. The newest attempt per image is the live one.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from modules.localization_agreement import (
    AGREEMENT_LIMIT,
    BIRD_CLASS,
    DETECTOR_KEY,
    SCORE_FLOOR,
    agreement_config_hash,
    agreement_score,
    padded_crop,
)
from modules.localization_cascade_runner import _RUN_SQL, DEFAULT_WEIGHTS, _run_row

logger = logging.getLogger(__name__)

_REGIONS_SQL = "SELECT id, rank, x1, y1, x2, y2 FROM image_regions WHERE localization_run_id = ? ORDER BY rank"
_LATEST_SQL = """
    SELECT status, detector_config_hash, rendition_hash, source_hash
    FROM image_localization_runs
    WHERE image_id = ? AND detector_key = ?
    ORDER BY id DESC
    LIMIT 1
"""
_SELECTED_SQL = """
    SELECT s.region_id, r.rendition_hash, g.x1, g.y1, g.x2, g.y2
    FROM image_localization_selections s
    JOIN image_regions g ON g.id = s.region_id
    JOIN image_localization_runs r ON r.id = s.localization_run_id
    WHERE s.image_id = ? AND s.detector_key = ? AND s.revoked_at IS NULL
"""


@dataclass
class AgreementContext:
    rtmdet: Any


def load_agreement_context(cfg: dict[str, Any]) -> AgreementContext | None:
    """``None`` unless ``localization.agreement.enabled`` (AC-1). Never raises."""
    if not (cfg.get("agreement") or {}).get("enabled", False):
        return None
    from modules.detectors.rtmdet import load_rtmdet

    return AgreementContext(rtmdet=load_rtmdet(DEFAULT_WEIGHTS, threshold=SCORE_FLOOR, retry_threshold=None))


def _unchanged(conn: Any, image_id: int, config_hash: str, bird: dict[str, Any]) -> bool:
    latest = conn.query_one(_LATEST_SQL, (int(image_id), DETECTOR_KEY))
    return bool(latest and latest["status"] != "retryable_error"
                and latest["detector_config_hash"] == config_hash
                and latest["rendition_hash"] == bird.get("rendition_hash")
                and latest["source_hash"] == bird.get("source_hash"))


def _region(row: dict[str, Any]) -> tuple[float, float, float, float]:
    return (row["x1"], row["y1"], row["x2"], row["y2"])


def _score(image: Any, region: tuple[float, float, float, float], rtmdet: Any) -> float:
    width, height = image.size
    crop = padded_crop(region, width, height)
    if crop is None:
        return 0.0
    return agreement_score(region, crop, rtmdet.detect(image.crop(crop)), width, height)


def _stored(region: tuple[float, float, float, float], rank: int, score: float, source: str) -> dict[str, Any]:
    return {"rank": rank, "region": region, "conf": score, "object_class": BIRD_CLASS, "provider_class_id": source}


def score_image(image_id: int, file_path: str, actx: AgreementContext, *, job_id: int | None = None,
                force: bool = False, dry_run: bool = False) -> str | None:
    """Write the image's ``bird_agreement`` run. Returns its status.

    ``None`` when there is no detected bird run, or the newest attempt already covers this identity (AC-6).
    A failure becomes a ``retryable_error`` run so a batch can continue (AC-10, AC-11).
    """
    from modules import db
    from modules.localization import decode_for_localization, write_run

    conn = db.get_connector()
    bird = conn.query_one(_RUN_SQL, (int(image_id), "bird"))
    if not bird or bird["status"] != "detected":
        return None
    rt = actx.rtmdet
    config_hash = agreement_config_hash(rt.config_hash, bird["detector_config_hash"])
    if not force and _unchanged(conn, image_id, config_hash, bird):
        return None

    regions = conn.query(_REGIONS_SQL, (int(bird["id"]),)) or []
    selected = conn.query_one(_SELECTED_SQL, (int(image_id), "bird"))
    try:
        decoded = decode_for_localization(file_path)
        rendition = decoded.descriptor.rendition_hash
        if rendition != bird["rendition_hash"]:
            raise RuntimeError("rendition changed since the bird run")
        stored = [_stored(_region(r), r["rank"], _score(decoded.image, _region(r), rt), f"agree:region:{r['id']}")
                  for r in regions]
        if selected and selected["region_id"] not in {r["id"] for r in regions}:
            if selected["rendition_hash"] != rendition:
                raise RuntimeError("selected region is on another rendition")
            rank = max((r["rank"] for r in regions), default=-1) + 1
            stored.append(_stored(_region(selected), rank, _score(decoded.image, _region(selected), rt),
                                  f"agree:selected:{selected['region_id']}"))
        status = "detected"
    except Exception as exc:  # noqa: BLE001 -- one image must not stop the batch (AC-10)
        logger.warning("agreement: image %s failed: %s", image_id, exc)
        stored, status = [], "retryable_error"

    if dry_run:
        return status
    run = _run_row(image_id, job_id, DETECTOR_KEY, f"{DETECTOR_KEY}/{rt.version}", config_hash, bird)
    run["status"] = status
    run["is_current"] = False
    run["is_retryable"] = status == "retryable_error"
    write_run(run, stored, publish=False)
    return status


def summarize_shoots(rows: list[dict[str, Any]], limit: float = AGREEMENT_LIMIT) -> dict[str, dict[str, int]]:
    """Per-shoot counts from ``{"shoot", "score", "eyes"}`` rows. The limit applies here only (AC-8)."""
    table: dict[str, dict[str, int]] = defaultdict(lambda: {"regions": 0, "at_or_above": 0, "below": 0, "eyes": 0,
                                                            "eyes_below": 0})
    for row in rows:
        shoot = table[row["shoot"]]
        below = row["score"] < limit
        shoot["regions"] += 1
        shoot["below" if below else "at_or_above"] += 1
        shoot["eyes"] += row["eyes"]
        shoot["eyes_below"] += row["eyes"] if below else 0
    return dict(table)
