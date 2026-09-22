"""E2E: import ``images.bird_bbox`` into the normalized localization tables (issue #370).

Covers the properties that only a real database can show: idempotence under the partial
unique index, the 1:1 run-per-non-null-row guarantee, and byte-for-byte reproduction of
the legacy payload. The classification logic itself is unit-tested in
``tests/test_localization_legacy.py``.

``pytest.mark.postgres``.
"""

from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.postgres]

from modules.localization_legacy import (  # noqa: E402
    import_legacy_bird_bbox,
    legacy_payload_from_normalized,
)

REAL_BOX = {
    "x1": 4460, "x2": 7709, "y1": 934, "y2": 3959,
    "conf": 0.6913, "img_h": 5504, "img_w": 8256, "area_frac": 0.216283,
}

#: One of every shape the column can hold, including the malformed ones the live library
#: does not currently contain but the importer must still survive.
PAYLOADS = [
    REAL_BOX,
    {"x1": 100, "y1": 100, "x2": 900, "y2": 700, "conf": 0.42, "img_w": 1000, "img_h": 800},
    {"detected": False},
    {"detected": False},
    {"detected": False, "error": "detector_unavailable"},
    {"detected": False, "error": "decode_error: cannot decode '/mnt/d/Photos/a.NEF'"},
    {"weird": 1},
    {"x1": 10, "y1": 10, "x2": 5, "y2": 50, "img_w": 100, "img_h": 100},   # inverted
    {"x1": 10, "y1": 10, "x2": 50, "y2": 50},                              # no dimensions
    None,                                                                   # never scanned
    None,
]

EXPECTED_STATUS_COUNTS = {
    "detected": 4,          # 2 usable boxes + inverted + dimensionless
    "no_detection": 2,
    "retryable_error": 1,
    "terminal_error": 2,    # decode_error + malformed
}
EXPECTED_REGIONS = 2        # only the two usable boxes
EXPECTED_RUNS = sum(EXPECTED_STATUS_COUNTS.values())

_SEED_PREFIX = "/tmp/loc-import-"


@pytest.fixture(autouse=True)
def _postgres_clean(postgres_test_session, clean_postgres):
    yield


@pytest.fixture
def postgres_conn(postgres_test_session):
    """Raw psycopg2 connection to the test database.

    The importer takes a connection rather than going through the pool so a caller can
    control transaction boundaries -- it commits per batch.
    """
    import psycopg2

    from modules import db_postgres

    cfg = db_postgres.get_pg_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"], dbname=cfg["dbname"],
        user=cfg["user"], password=cfg["password"],
    )
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def seeded(postgres_conn):
    """Insert one image per payload, on a connection this module owns.

    Cleans up after itself rather than relying on ``clean_postgres``: that fixture
    truncates through the pool, while this test drives a separate connection, and the
    two orderings are not guaranteed to interleave the way the rows need.
    """
    cur = postgres_conn.cursor()
    cur.execute("DELETE FROM image_regions")
    cur.execute("DELETE FROM image_localization_runs")
    cur.execute("DELETE FROM images WHERE file_path LIKE %s", (_SEED_PREFIX + "%",))
    postgres_conn.commit()
    image_ids = []
    for i, payload in enumerate(PAYLOADS):
        cur.execute(
            "INSERT INTO images (file_path, bird_bbox) VALUES (%s, %s) RETURNING id",
            (f"{_SEED_PREFIX}{i}.jpg", json.dumps(payload) if payload is not None else None),
        )
        image_ids.append(cur.fetchone()[0])
    postgres_conn.commit()
    cur.close()
    yield image_ids
    cleanup = postgres_conn.cursor()
    cleanup.execute("DELETE FROM image_regions")
    cleanup.execute("DELETE FROM image_localization_runs")
    cleanup.execute("DELETE FROM images WHERE file_path LIKE %s", (_SEED_PREFIX + "%",))
    postgres_conn.commit()
    cleanup.close()


def _status_counts(conn):
    cur = conn.cursor()
    cur.execute("SELECT status, count(*) FROM image_localization_runs GROUP BY 1")
    out = dict(cur.fetchall())
    cur.close()
    return out


def test_dry_run_writes_nothing(postgres_conn, seeded):
    counts = import_legacy_bird_bbox(postgres_conn, dry_run=True, batch_size=3)
    assert counts["scanned"] == len([p for p in PAYLOADS if p is not None])
    cur = postgres_conn.cursor()
    cur.execute("SELECT count(*) FROM image_localization_runs")
    assert cur.fetchone()[0] == 0
    cur.close()


def test_import_maps_every_legacy_shape(postgres_conn, seeded):
    counts = import_legacy_bird_bbox(postgres_conn, dry_run=False, batch_size=3)

    for status, expected in EXPECTED_STATUS_COUNTS.items():
        assert counts[status] == expected, f"{status}: {counts}"
    assert _status_counts(postgres_conn) == EXPECTED_STATUS_COUNTS
    assert counts["regions"] == EXPECTED_REGIONS
    # Two `detected` rows carry geometry that cannot be normalized; they keep their run.
    assert counts["detected_without_region"] == 2


def test_null_rows_get_no_run(postgres_conn, seeded):
    """NULL means never attempted, so it must not produce a run row."""
    import_legacy_bird_bbox(postgres_conn, dry_run=False, batch_size=3)
    cur = postgres_conn.cursor()
    cur.execute(
        """SELECT count(*) FROM image_localization_runs r
           JOIN images i ON i.id = r.image_id WHERE i.bird_bbox IS NULL"""
    )
    assert cur.fetchone()[0] == 0
    cur.close()


def test_one_run_per_non_null_row(postgres_conn, seeded):
    import_legacy_bird_bbox(postgres_conn, dry_run=False, batch_size=3)
    cur = postgres_conn.cursor()
    cur.execute("SELECT count(*), count(DISTINCT image_id) FROM image_localization_runs")
    total, distinct = cur.fetchone()
    assert total == distinct == EXPECTED_RUNS
    cur.close()


def test_import_is_idempotent(postgres_conn, seeded):
    """Re-running preserves counts -- the partial unique index absorbs the second pass."""
    first = import_legacy_bird_bbox(postgres_conn, dry_run=False, batch_size=3)
    before = _status_counts(postgres_conn)

    second = import_legacy_bird_bbox(postgres_conn, dry_run=False, batch_size=3)

    assert _status_counts(postgres_conn) == before
    # `scanned` counts only non-NULL rows (the read query filters them), so every one
    # of them is skipped on the second pass.
    assert first["scanned"] == EXPECTED_RUNS
    assert second["skipped_existing"] == EXPECTED_RUNS
    assert second["regions"] == 0
    cur = postgres_conn.cursor()
    cur.execute("SELECT count(*) FROM image_regions")
    assert cur.fetchone()[0] == EXPECTED_REGIONS
    cur.close()


def test_legacy_payload_round_trips_byte_for_byte(postgres_conn, seeded):
    """Stage 8 retires the column behind this projection, so it must be exact."""
    import_legacy_bird_bbox(postgres_conn, dry_run=False, batch_size=3)
    cur = postgres_conn.cursor()
    cur.execute(
        """SELECT i.bird_bbox, r.id, r.status, r.legacy_payload,
                  r.display_width, r.display_height, r.error_code
           FROM images i JOIN image_localization_runs r
             ON r.image_id = i.id AND r.is_current
           WHERE i.bird_bbox IS NOT NULL"""
    )
    rows = cur.fetchall()
    assert len(rows) == EXPECTED_RUNS

    for original, run_id, status, payload, w, h, code in rows:
        cur.execute(
            "SELECT object_class, rank, x1, y1, x2, y2, confidence "
            "FROM image_regions WHERE localization_run_id = %s ORDER BY rank",
            (run_id,),
        )
        regions = [
            dict(zip(("object_class", "rank", "x1", "y1", "x2", "y2", "confidence"), r))
            for r in cur.fetchall()
        ]
        rebuilt = legacy_payload_from_normalized(
            {"status": status, "legacy_payload": payload,
             "display_width": w, "display_height": h, "error_code": code},
            regions,
        )
        assert rebuilt == original, f"run {run_id}: {rebuilt!r} != {original!r}"
    cur.close()


def test_error_detail_is_redacted_but_payload_is_not(postgres_conn, seeded):
    """The searchable/loggable column drops paths; the verbatim payload keeps them.

    Redacting the payload too would break byte-for-byte reproduction above.
    """
    import_legacy_bird_bbox(postgres_conn, dry_run=False, batch_size=3)
    cur = postgres_conn.cursor()
    cur.execute(
        "SELECT error_detail, legacy_payload FROM image_localization_runs "
        "WHERE error_code = 'decode_error'"
    )
    detail, payload = cur.fetchone()
    assert "/mnt/d/Photos" not in detail
    assert "<path>" in detail
    assert "/mnt/d/Photos" in payload["error"]
    cur.close()


def test_regions_are_normalized_against_payload_dimensions(postgres_conn, seeded):
    import_legacy_bird_bbox(postgres_conn, dry_run=False, batch_size=3)
    cur = postgres_conn.cursor()
    cur.execute(
        """SELECT x1, y1, x2, y2, confidence FROM image_regions g
           JOIN image_localization_runs r ON r.id = g.localization_run_id
           WHERE r.display_width = 8256"""
    )
    x1, y1, x2, y2, conf = cur.fetchone()
    assert x1 == pytest.approx(4460 / 8256)
    assert y2 == pytest.approx(3959 / 5504)
    assert conf == pytest.approx(0.6913)
    cur.close()


def test_limit_stops_early(postgres_conn, seeded):
    counts = import_legacy_bird_bbox(postgres_conn, dry_run=False, batch_size=2, limit=4)
    assert counts["scanned"] == 4
    cur = postgres_conn.cursor()
    cur.execute("SELECT count(*) FROM image_localization_runs")
    assert cur.fetchone()[0] <= 4
    cur.close()
