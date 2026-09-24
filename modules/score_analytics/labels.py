"""Ground-truth label sources, provenance audit and leakage guards (read-only).

Verified against the current schema / writers (see docs/technical/DB_SCHEMA.md):

* ``culling_picks.decision`` with ``auto_suggested = 0`` — a human decision in a
  culling session (``modules/culling.py`` writes suggestions with
  ``auto_suggested=True``). **Treated as independent.**
* ``images.pick_status`` with ``cull_policy_version IS NULL`` — flag of unknown
  origin (UI edit, XMP import, …). **Unverified.**
* ``images.pick_status`` with ``cull_policy_version`` set — written by the
  auto-cull policy from scores (``batch_update_cull_decisions``). **Leakage.**
* ``image_xmp.pick_status`` / ``image_xmp.rating`` — sidecar values; may be
  user-set, but the app also writes rating / label / pick into XMP
  (``modules/xmp.py``). **Unverified**; flagged when they mirror score-derived values.
* ``images.rating`` — derived from the general composite
  (``score_normalization.score_to_rating``). **Never ground truth.**

Grades used for culling: pick = 2, keep / neutral / maybe = 1, reject = 0,
unlabelled = -1.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from modules.score_analytics import data

logger = logging.getLogger(__name__)

UNLABELLED = -1
DECISION_GRADE = {"pick": 2, "keep": 1, "maybe": 1, "neutral": 1, "skip": 1, "reject": 0}
PICK_STATUS_GRADE = {1: 2, 0: 1, -1: 0}

CULLING_POLICIES = ("auto", "manual", "unverified", "all")


@dataclass
class LabelBundle:
    """Aligned label vectors for a :class:`data.ScoreMatrix` plus provenance."""

    culling_grades: np.ndarray
    culling_source: str
    culling_independent: bool
    global_label: np.ndarray
    global_source: str | None
    global_independent: bool
    camera: np.ndarray
    audit: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# DB loaders (all read-only)
# ---------------------------------------------------------------------------


def _table_exists(name: str) -> bool:
    return bool(data._select("SELECT to_regclass(%s) IS NOT NULL", (f"public.{name}",))[0][0])


def _column_exists(table: str, column: str) -> bool:
    rows = data._select(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (table, column),
    )
    return bool(rows)


def load_label_rows() -> dict[str, Any]:
    """Raw label rows per source (image_id keyed) with timestamps for the audit."""
    out: dict[str, Any] = {}
    if _table_exists("culling_picks"):
        out["culling_manual"] = data._select(
            """
            SELECT DISTINCT ON (image_id) image_id, LOWER(decision), created_at
            FROM culling_picks
            WHERE COALESCE(auto_suggested, 0) = 0 AND decision IS NOT NULL
            ORDER BY image_id, created_at DESC, id DESC
            """
        )
        out["culling_auto"] = data._select(
            "SELECT COUNT(*), MIN(created_at), MAX(created_at) FROM culling_picks WHERE auto_suggested = 1"
        )[0]
    policy_col = _column_exists("images", "cull_policy_version")
    out["pick_status"] = data._select(
        f"""
        SELECT id, pick_status, {'cull_policy_version' if policy_col else 'NULL'}
        FROM images WHERE pick_status <> 0 {'OR cull_policy_version IS NOT NULL' if policy_col else ''}
        """
    )
    out["score_rating"] = data._select("SELECT id, rating FROM images WHERE rating IS NOT NULL AND rating > 0")
    if _table_exists("image_xmp"):
        out["xmp"] = data._select(
            "SELECT image_id, rating, pick_status, extracted_at FROM image_xmp WHERE rating IS NOT NULL OR pick_status IS NOT NULL"
        )
    if _table_exists("image_exif"):
        out["camera"] = data._select(
            "SELECT image_id, TRIM(CONCAT_WS(' ', make, model)) FROM image_exif WHERE model IS NOT NULL"
        )
    return out


# ---------------------------------------------------------------------------
# assembly + audit (pure given rows — unit-testable)
# ---------------------------------------------------------------------------


def _index(m: data.ScoreMatrix) -> dict[int, int]:
    return {int(i): r for r, i in enumerate(m.image_ids.tolist())}


def _grades_from_flags(m: data.ScoreMatrix, flagged: dict[int, int]) -> np.ndarray:
    """Grade images from pick flags; unflagged members of a flagged stack count as neutral."""
    idx = _index(m)
    g = np.full(m.image_count, UNLABELLED, dtype=np.int8)
    for iid, ps in flagged.items():
        r = idx.get(iid)
        if r is not None:
            g[r] = PICK_STATUS_GRADE.get(int(ps), UNLABELLED)
    touched = np.unique(m.stack_ids[(g >= 0) & (m.stack_ids > 0)])
    fill = np.isin(m.stack_ids, touched) & (g < 0)
    g[fill] = 1
    return g


def _labelled_clusters(m: data.ScoreMatrix, g: np.ndarray) -> int:
    stacked = (m.stack_ids > 0) & (g >= 0)
    if not stacked.any():
        return 0
    ids, counts = np.unique(m.stack_ids[stacked], return_counts=True)
    decisive = 0
    for sid in ids[counts >= 2]:
        gg = g[m.stack_ids == sid]
        gg = gg[gg >= 0]
        decisive += int(gg.max() != gg.min())
    return decisive


def assemble(
    m: data.ScoreMatrix,
    rows: dict[str, Any],
    *,
    culling_policy: str = "auto",
    min_clusters: int = 20,
    trust_xmp_ratings: bool = False,
) -> LabelBundle:
    if culling_policy not in CULLING_POLICIES:
        raise ValueError(f"culling_policy must be one of {CULLING_POLICIES}")
    idx = _index(m)
    audit: dict[str, Any] = {"sources": {}, "notes": []}

    # --- culling candidates -------------------------------------------------
    manual = np.full(m.image_count, UNLABELLED, dtype=np.int8)
    manual_times = []
    for iid, decision, created in rows.get("culling_manual", []):
        r = idx.get(int(iid))
        if r is not None and decision in DECISION_GRADE:
            manual[r] = DECISION_GRADE[decision]
            manual_times.append(created)
    policy_flags, unverified_flags = {}, {}
    for iid, ps, policy_version in rows.get("pick_status", []):
        if ps is None or int(ps) == 0:
            continue
        (policy_flags if policy_version else unverified_flags)[int(iid)] = int(ps)
    xmp_flags = {int(r[0]): int(r[2]) for r in rows.get("xmp", []) if r[2] not in (None, 0)}
    unverified = _grades_from_flags(m, {**xmp_flags, **unverified_flags})
    policy = _grades_from_flags(m, policy_flags)

    candidates = {
        "culling_manual": (manual, True, "culling_picks.decision where auto_suggested = 0 (human session decisions)"),
        "pick_status_unverified": (
            unverified,
            False,
            "images.pick_status without cull_policy_version, plus image_xmp.pick_status (origin unknown)",
        ),
        "pick_status_auto_policy": (
            policy,
            False,
            "images.pick_status written by the auto-cull policy (cull_policy_version set) — score-derived, LEAKAGE",
        ),
    }
    for name, (g, independent, desc) in candidates.items():
        audit["sources"][name] = {
            "description": desc,
            "independent": independent,
            "images": int((g >= 0).sum()),
            "picks": int((g == 2).sum()),
            "rejects": int((g == 0).sum()),
            "decisive_clusters": _labelled_clusters(m, g),
        }
    if manual_times:
        audit["sources"]["culling_manual"]["first"] = str(min(manual_times))
        audit["sources"]["culling_manual"]["last"] = str(max(manual_times))
    auto_row = rows.get("culling_auto")
    if auto_row:
        audit["sources"]["culling_auto_suggestions"] = {
            "description": "culling_picks with auto_suggested = 1 — excluded (score-derived)",
            "independent": False,
            "rows": int(auto_row[0] or 0),
        }

    if culling_policy == "manual":
        chosen = "culling_manual"
    elif culling_policy == "unverified":
        chosen = "pick_status_unverified"
    elif culling_policy == "all":
        chosen = "all"
    else:
        chosen = (
            "culling_manual"
            if audit["sources"]["culling_manual"]["decisive_clusters"] >= min_clusters
            else "pick_status_unverified"
        )
        if chosen != "culling_manual":
            audit["notes"].append(
                f"Fewer than {min_clusters} clusters with manual culling decisions; falling back to UNVERIFIED "
                "pick flags. Culling results are provisional until a human-labelled cohort exists."
            )
    if chosen == "all":
        grades = np.where(manual >= 0, manual, np.where(unverified >= 0, unverified, policy)).astype(np.int8)
        culling_independent = False
        audit["notes"].append("Policy 'all' mixes auto-cull (score-derived) labels — diagnostics only, not evidence.")
    else:
        grades = candidates[chosen][0]
        culling_independent = candidates[chosen][1]

    # --- global label -------------------------------------------------------
    xmp_rating = np.full(m.image_count, np.nan)
    for iid, rating, _ps, _ts in rows.get("xmp", []):
        r = idx.get(int(iid))
        if r is not None and rating is not None and int(rating) > 0:
            xmp_rating[r] = float(rating)
    score_rating = np.full(m.image_count, np.nan)
    for iid, rating in rows.get("score_rating", []):
        r = idx.get(int(iid))
        if r is not None:
            score_rating[r] = float(rating)
    both = np.isfinite(xmp_rating) & np.isfinite(score_rating)
    mirror = float(np.mean(xmp_rating[both] == score_rating[both])) if both.any() else None
    audit["sources"]["xmp_rating"] = {
        "description": "image_xmp.rating (sidecar stars; the app can also write ratings to XMP)",
        "independent": bool(trust_xmp_ratings),
        "images": int(np.isfinite(xmp_rating).sum()),
        "equals_score_rating_pct": None if mirror is None else round(100 * mirror, 2),
    }
    audit["sources"]["images_rating"] = {
        "description": "images.rating — derived from score_general thresholds; never used as ground truth",
        "independent": False,
        "images": int(np.isfinite(score_rating).sum()),
    }
    global_independent = bool(trust_xmp_ratings)
    if mirror is not None and mirror >= 0.8:
        global_independent = False
        audit["notes"].append(
            f"{100 * mirror:.0f}% of XMP ratings equal the score-derived rating — they look written back by the app; "
            "treated as NOT independent."
        )
    elif not trust_xmp_ratings and np.isfinite(xmp_rating).any():
        audit["notes"].append("XMP ratings are unverified; pass trust_xmp_ratings once their origin is confirmed.")
    global_source = "xmp_rating" if np.isfinite(xmp_rating).sum() >= 30 else None
    if global_source is None:
        audit["notes"].append("No usable independent global quality labels (need ≥ 30 rated images); Gⱼ unavailable.")

    camera = np.array([""] * m.image_count, dtype=object)
    for iid, cam in rows.get("camera", []):
        r = idx.get(int(iid))
        if r is not None and cam:
            camera[r] = cam

    audit["culling_source"] = chosen
    audit["culling_independent"] = culling_independent
    audit["global_source"] = global_source
    audit["global_independent"] = global_independent
    audit["not_measurable"] = [
        "Rescoring / cross-run stability: image_model_scores keeps one row per (image, model); prior runs are not retained.",
        "Cluster type (burst / eye focus / macro plane / exposure variant) is not stored; stack size, keyword and camera are used as strata.",
    ]
    return LabelBundle(
        culling_grades=grades,
        culling_source=chosen,
        culling_independent=culling_independent,
        global_label=xmp_rating,
        global_source=global_source,
        global_independent=global_independent,
        camera=camera,
        audit=audit,
    )


def load_data_dictionary() -> list[dict[str, Any]]:
    """Per-model inventory from image_model_scores (all statuses) — read-only."""
    rows = data._select(
        """
        SELECT model_name,
               BOOL_OR(is_shadow),
               COUNT(*),
               COUNT(*) FILTER (WHERE status = 'success'),
               COUNT(*) FILTER (WHERE status = 'failed'),
               COUNT(*) FILTER (WHERE status = 'not_loaded'),
               MIN(raw_score), MAX(raw_score), MIN(normalized), MAX(normalized),
               COUNT(*) FILTER (WHERE normalized IS NULL AND status = 'success'),
               MIN(scored_at), MAX(scored_at),
               COUNT(DISTINCT model_version)
        FROM image_model_scores GROUP BY model_name ORDER BY model_name
        """
    )
    versions = data._select(
        "SELECT model_name, COALESCE(model_version, '(none)'), COUNT(*) FROM image_model_scores GROUP BY 1, 2 ORDER BY 1, 3 DESC"
    )
    by_model: dict[str, list] = {}
    for name, ver, cnt in versions:
        by_model.setdefault(name, []).append({"version": ver, "rows": int(cnt)})
    out = []
    for r in rows:
        out.append(
            {
                "dimension": r[0],
                "score_type": "shadow model" if r[1] else "model",
                "source": "image_model_scores",
                "read_as": "COALESCE(normalized, raw_score)",
                "rows": int(r[2]),
                "success": int(r[3]),
                "failed": int(r[4]),
                "not_loaded": int(r[5]),
                "raw_min": r[6],
                "raw_max": r[7],
                "normalized_min": r[8],
                "normalized_max": r[9],
                "success_without_normalized": int(r[10]),
                "first_scored": str(r[11]) if r[11] else None,
                "last_scored": str(r[12]) if r[12] else None,
                "versions": by_model.get(r[0], []),
            }
        )
    for comp in data.COMPOSITE_KEYS:
        out.append(
            {
                "dimension": comp,
                "score_type": "derived composite",
                "source": f"images.score_{comp}",
                "read_as": f"images.score_{comp} (percentile-rescaled fusion of model scores)",
                "note": "Computed from component models — not independent ground truth.",
            }
        )
    return out


def label_fingerprint() -> str:
    """Cheap change detector for label tables (cache key for suitability reports)."""
    parts: list[Any] = []
    if _table_exists("culling_picks"):
        parts += list(data._select("SELECT COUNT(*), MAX(id), SUM(LENGTH(COALESCE(decision, '')) * id::bigint) FROM culling_picks")[0])
    if _table_exists("image_xmp"):
        parts += list(
            data._select(
                "SELECT COUNT(*), SUM(image_id::bigint * (COALESCE(rating, 0) + 10 * COALESCE(pick_status, 0) + 100)) FROM image_xmp"
            )[0]
        )
    return "|".join(str(p) for p in parts)
