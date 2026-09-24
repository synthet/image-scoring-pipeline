"""Load the image × score-dimension matrix from PostgreSQL and cache derived results.

One matrix row per image; one column per score dimension:

* composites stored on ``images`` (``general``, ``technical``, ``aesthetic``)
* every ``image_model_scores.model_name`` with successful rows, including shadow
  models, read as ``COALESCE(normalized, raw_score)``

Per-image attributes used by the stack / culling layer ride along
(``stack_id``, ``pick_status``) plus ``stacks.best_image_id``.

The matrix, its serialized payloads and any derived statistics are cached in
process and rebuilt when a cheap DB fingerprint changes. The fingerprint is
re-checked at most every ``FINGERPRINT_TTL_S`` seconds.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np

from modules import config

logger = logging.getLogger(__name__)

COMPOSITE_KEYS = ("general", "technical", "aesthetic")
FINGERPRINT_TTL_S = 10.0
DERIVED_CACHE_SIZE = 32


@dataclass
class ScoreMatrix:
    image_ids: np.ndarray
    keys: list[str]
    series: dict[str, np.ndarray]
    meta: dict[str, dict[str, Any]]
    fingerprint: str
    generated_at: str
    stack_ids: np.ndarray  # 0 = not stacked
    pick_status: np.ndarray  # 1 pick, -1 reject, 0 neutral
    best_image_by_stack: dict[int, int] = field(default_factory=dict)
    scope: dict[str, Any] = field(default_factory=lambda: {"kind": "library"})

    @property
    def image_count(self) -> int:
        return int(self.image_ids.size)

    def subset(self, mask: np.ndarray, scope: dict[str, Any]) -> ScoreMatrix:
        """Rows selected by ``mask``; dimensions with no values in scope are dropped."""
        series = {k: v[mask] for k, v in self.series.items()}
        n = int(mask.sum())
        keys = [k for k in self.keys if np.isfinite(series[k]).any()]
        meta = {
            k: {
                "kind": self.meta[k]["kind"],
                "count": int(np.isfinite(series[k]).sum()),
                "coverage_pct": round(100.0 * np.isfinite(series[k]).sum() / n, 2) if n else 0.0,
            }
            for k in keys
        }
        return ScoreMatrix(
            image_ids=self.image_ids[mask],
            keys=keys,
            series={k: series[k] for k in keys},
            meta=meta,
            fingerprint=self.fingerprint,
            generated_at=self.generated_at,
            stack_ids=self.stack_ids[mask],
            pick_status=self.pick_status[mask],
            best_image_by_stack=self.best_image_by_stack,
            scope=scope,
        )


@dataclass
class _CacheState:
    fingerprint: str | None = None
    checked_at: float = 0.0
    matrix: ScoreMatrix | None = None
    derived: OrderedDict = field(default_factory=OrderedDict)


_lock = threading.RLock()
_state = _CacheState()


class ScoreAnalyticsUnavailable(ValueError):
    """Raised when the configured database engine cannot serve score analytics."""


def require_postgres() -> None:
    if config.get_database_engine() != "postgres":
        raise ScoreAnalyticsUnavailable("Score analytics requires PostgreSQL (database.engine=postgres).")


def normalize_keyword(keyword: str | None) -> str | None:
    """Same normalization as ``keywords_dim.keyword_norm`` lookups (strip + lower)."""
    if keyword is None:
        return None
    norm = keyword.strip().lower()
    return norm or None


def _select(sql: str, params: tuple | None = None) -> list[tuple]:
    from modules.db_postgres import PGConnectionManager

    with PGConnectionManager() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _query_fingerprint() -> str:
    # Composite recomputes and cull decisions do not always bump
    # images.updated_at, so score sums and id-weighted pick/stack sums are part
    # of the fingerprint. Float sums are cast to numeric: parallel aggregation
    # makes double-precision sums differ in the last digits between runs.
    rows = _select(
        """
        SELECT
          (SELECT COUNT(*) FROM images),
          (SELECT MAX(updated_at) FROM images),
          (SELECT SUM((COALESCE(score_general, 0) + COALESCE(score_technical, 0)
                      + COALESCE(score_aesthetic, 0))::numeric) FROM images),
          (SELECT SUM(id::bigint * (pick_status + 2)) FROM images),
          (SELECT SUM(id::bigint * COALESCE(stack_id, 0)) FROM images),
          (SELECT SUM(id::bigint * COALESCE(best_image_id, 0)) FROM stacks),
          (SELECT COUNT(*) FROM image_model_scores),
          (SELECT MAX(scored_at) FROM image_model_scores),
          (SELECT SUM(COALESCE(normalized, raw_score, 0)::numeric) FROM image_model_scores
            WHERE status = 'success'),
          (SELECT COUNT(*) FROM image_keywords),
          (SELECT SUM(image_id::bigint * keyword_id) FROM image_keywords)
        """
    )
    raw = "|".join(str(v) for v in rows[0])
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _load_from_db(fingerprint: str) -> ScoreMatrix:
    image_rows = _select(
        """
        SELECT id, score_general, score_technical, score_aesthetic, stack_id, pick_status
        FROM images ORDER BY id
        """
    )
    score_rows = _select(
        """
        SELECT image_id, model_name, COALESCE(normalized, raw_score), is_shadow
        FROM image_model_scores
        WHERE status = 'success' AND COALESCE(normalized, raw_score) IS NOT NULL
        """
    )
    best_rows = _select("SELECT id, best_image_id FROM stacks WHERE best_image_id IS NOT NULL")
    return build_matrix(image_rows, score_rows, fingerprint, best_rows)


def load_matrix() -> ScoreMatrix:
    """Uncached load straight from the DB (for batch scripts)."""
    require_postgres()
    return _load_from_db(_query_fingerprint())


def keyword_image_ids(keyword: str) -> np.ndarray:
    rows = _select(
        """
        SELECT ik.image_id FROM image_keywords ik
        JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id
        WHERE kd.keyword_norm = %s
        """,
        (keyword,),
    )
    return np.fromiter((r[0] for r in rows), dtype=np.int64, count=len(rows))


def top_keywords(limit: int, min_images: int = 1) -> list[tuple[str, int]]:
    """Most frequent normalized keywords as ``(keyword_norm, image_count)``."""
    rows = _select(
        """
        SELECT kd.keyword_norm, COUNT(DISTINCT ik.image_id) AS n
        FROM image_keywords ik
        JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id
        GROUP BY kd.keyword_norm
        HAVING COUNT(DISTINCT ik.image_id) >= %s
        ORDER BY n DESC, kd.keyword_norm
        LIMIT %s
        """,
        (int(min_images), int(limit)),
    )
    return [(str(r[0]), int(r[1])) for r in rows]


def build_matrix(
    image_rows: list[tuple],
    score_rows: list[tuple],
    fingerprint: str,
    best_rows: list[tuple] | None = None,
) -> ScoreMatrix:
    """Pivot DB rows into a column-per-dimension matrix (NaN = missing).

    ``image_rows``: ``(id, general, technical, aesthetic, stack_id, pick_status)``.
    """
    n = len(image_rows)
    image_ids = np.fromiter((r[0] for r in image_rows), dtype=np.int64, count=n)
    series: dict[str, np.ndarray] = {}
    for c, key in enumerate(COMPOSITE_KEYS, start=1):
        series[key] = np.array(
            [np.nan if r[c] is None else float(r[c]) for r in image_rows], dtype=np.float64
        )
    stack_ids = np.fromiter((r[4] or 0 for r in image_rows), dtype=np.int64, count=n)
    pick_status = np.fromiter((r[5] or 0 for r in image_rows), dtype=np.int8, count=n)

    index = {int(iid): i for i, iid in enumerate(image_ids.tolist())}
    shadow: dict[str, bool] = {}
    model_cols: dict[str, np.ndarray] = {}
    for image_id, model_name, value, is_shadow in score_rows:
        row = index.get(int(image_id))
        if row is None:
            continue
        col = model_cols.get(model_name)
        if col is None:
            col = model_cols[model_name] = np.full(n, np.nan, dtype=np.float64)
        col[row] = float(value)
        shadow[model_name] = shadow.get(model_name, False) or bool(is_shadow)

    meta: dict[str, dict[str, Any]] = {}
    keys: list[str] = []
    for key in COMPOSITE_KEYS:
        count = int(np.isfinite(series[key]).sum())
        if count:
            keys.append(key)
            meta[key] = {"kind": "composite", "count": count}
    for kind in ("model", "shadow"):
        for name in sorted(model_cols):
            if (kind == "shadow") != shadow[name]:
                continue
            series[name] = model_cols[name]
            keys.append(name)
            meta[name] = {"kind": kind, "count": int(np.isfinite(model_cols[name]).sum())}
    for key in keys:
        meta[key]["coverage_pct"] = round(100.0 * meta[key]["count"] / n, 2) if n else 0.0

    return ScoreMatrix(
        image_ids=image_ids,
        keys=keys,
        series={k: series[k] for k in keys},
        meta=meta,
        fingerprint=fingerprint,
        generated_at=datetime.now(timezone.utc).isoformat(),
        stack_ids=stack_ids,
        pick_status=pick_status,
        best_image_by_stack={int(s): int(b) for s, b in (best_rows or [])},
    )


def _column_json(values: np.ndarray) -> list[float | None]:
    rounded = np.round(values, 3).tolist()
    return [None if v != v else v for v in rounded]


def serialize_matrix(m: ScoreMatrix) -> bytes:
    payload = {
        "fingerprint": m.fingerprint,
        "generated_at": m.generated_at,
        "scope": m.scope,
        "image_count": m.image_count,
        "image_ids": m.image_ids.tolist(),
        "keys": m.keys,
        "meta": m.meta,
        "series": {k: _column_json(m.series[k]) for k in m.keys},
    }
    return json.dumps(payload, separators=(",", ":")).encode()


def _refresh_locked() -> ScoreMatrix:
    now = time.monotonic()
    if _state.matrix is not None and now - _state.checked_at < FINGERPRINT_TTL_S:
        return _state.matrix
    fingerprint = _query_fingerprint()
    _state.checked_at = now
    if _state.matrix is None or fingerprint != _state.fingerprint:
        started = time.perf_counter()
        _state.matrix = _load_from_db(fingerprint)
        _state.fingerprint = fingerprint
        _state.derived.clear()
        logger.info(
            "score analytics matrix rebuilt: %d images × %d dims in %.2fs",
            _state.matrix.image_count,
            len(_state.matrix.keys),
            time.perf_counter() - started,
        )
    return _state.matrix


def get_matrix() -> ScoreMatrix:
    require_postgres()
    with _lock:
        return _refresh_locked()


def cached(key: tuple, compute: Callable[[ScoreMatrix], Any]) -> Any:
    """Memoize ``compute(matrix)`` until the matrix fingerprint changes (LRU)."""
    require_postgres()
    with _lock:
        m = _refresh_locked()
        if key in _state.derived:
            _state.derived.move_to_end(key)
            return _state.derived[key]
        value = compute(m)
        _state.derived[key] = value
        while len(_state.derived) > DERIVED_CACHE_SIZE:
            _state.derived.popitem(last=False)
        return value


def scope_matrix(m: ScoreMatrix, keyword: str | None, ids: np.ndarray | None = None) -> ScoreMatrix:
    """Restrict ``m`` to images tagged with ``keyword`` (``ids`` override the DB lookup)."""
    if keyword is None:
        return m
    if ids is None:
        ids = keyword_image_ids(keyword)
    return m.subset(np.isin(m.image_ids, ids), {"kind": "keyword", "keyword": keyword})


def get_scoped(keyword: str | None) -> ScoreMatrix:
    """Full-library matrix or its keyword subset (cached per fingerprint)."""
    keyword = normalize_keyword(keyword)
    if keyword is None:
        return get_matrix()
    return cached(("scope", keyword), lambda m: scope_matrix(m, keyword))


def get_matrix_payload(keyword: str | None = None) -> tuple[bytes, str]:
    """Gzipped JSON payload for the matrix endpoint and its ETag."""
    keyword = normalize_keyword(keyword)
    scoped = get_scoped(keyword)

    def build(_m: ScoreMatrix) -> bytes:
        return gzip.compress(serialize_matrix(scoped), compresslevel=5)

    body = cached(("matrix_gz", keyword), build)
    tag = scoped.fingerprint
    if keyword:
        tag += "-" + hashlib.sha1(keyword.encode()).hexdigest()[:8]
    return body, f'"{tag}"'


def reset_cache() -> None:
    with _lock:
        _state.fingerprint = None
        _state.checked_at = 0.0
        _state.matrix = None
        _state.derived.clear()
