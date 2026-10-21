"""Real PostgreSQL interleavings for legacy bbox writes and region promotion (#646)."""
from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from modules import db, db_postgres
from modules.db_connector.postgres import PostgresConnector
from modules.localization_selection import select_region
from modules.test_db_constants import POSTGRES_TEST_DB

pytestmark = pytest.mark.postgres
DETECTED = {"x1": 1, "y1": 1, "x2": 99, "y2": 99,
            "img_w": 100, "img_h": 100, "conf": 0.9, "area_frac": 0.9604}


class PausedCommit:
    """Hold a real transaction's locks at its commit boundary."""

    def __init__(self, connection, ready, release):
        self.connection = connection
        self.ready = ready
        self.release = release

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def commit(self):
        self.ready.set()
        assert self.release.wait(10), "test did not release the held transaction"
        self.connection.commit()


@pytest.fixture
def isolated_schema(monkeypatch, request):
    marker = request.config.getoption("-m") or ""
    if os.environ.get("RUN_POSTGRES_TESTS") != "1" and not (
        "postgres" in marker and "not postgres" not in marker
    ):
        pytest.skip("PostgreSQL tests require RUN_POSTGRES_TESTS=1 or -m postgres")
    psycopg2 = pytest.importorskip("psycopg2")
    from psycopg2 import sql

    cfg = db_postgres.get_pg_config()
    assert cfg["dbname"] == POSTGRES_TEST_DB, "only the isolated test database is allowed"
    admin = psycopg2.connect(**cfg, connect_timeout=5)
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute("SELECT current_database()")
        assert cur.fetchone()[0] == POSTGRES_TEST_DB
    schema = "bbox_ownership_" + uuid.uuid4().hex
    with admin.cursor() as cur:
        cur.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        cur.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        # Only this disposable schema is used; no app table is truncated or migrated.
        cur.execute("""
            CREATE TABLE images (id integer PRIMARY KEY, folder_id integer, bird_bbox jsonb);
            CREATE TABLE image_localization_runs (
                id integer PRIMARY KEY, image_id integer REFERENCES images,
                detector_key text, display_width integer, display_height integer);
            CREATE TABLE image_regions (
                id integer PRIMARY KEY, localization_run_id integer REFERENCES image_localization_runs,
                confidence double precision, x1 double precision, y1 double precision,
                x2 double precision, y2 double precision);
            CREATE TABLE image_localization_selections (
                id bigserial PRIMARY KEY, image_id integer REFERENCES images, detector_key text,
                localization_run_id integer REFERENCES image_localization_runs,
                region_id integer REFERENCES image_regions, selected_by text, evidence jsonb,
                previous_bird_bbox jsonb, projected_bird_bbox jsonb,
                selected_at timestamp DEFAULT CURRENT_TIMESTAMP, revoked_at timestamp, revoked_reason text);
            CREATE UNIQUE INDEX active_selection ON image_localization_selections(image_id, detector_key)
                WHERE revoked_at IS NULL;
            INSERT INTO images VALUES (3, 8, NULL);
            INSERT INTO image_localization_runs VALUES (7, 3, 'bird', 100, 100);
            INSERT INTO image_regions VALUES (9, 7, 0.8, 0.2, 0.2, 0.6, 0.6);
        """)
    role = threading.local()
    pids = {}
    held = threading.Event()
    release = threading.Event()
    waiting = threading.Event()
    invalidations = []

    def connect():
        connection = psycopg2.connect(
            **cfg, connect_timeout=5,
            options=f"-c search_path={schema} -c statement_timeout=15000 -c lock_timeout=12000",
        )
        worker_role = getattr(role, "value", None)
        if worker_role:
            pids[worker_role] = connection.get_backend_pid()
        if worker_role == "held":
            return PausedCommit(connection, held, release)
        if worker_role == "waiting":
            waiting.set()
        return connection

    monkeypatch.setattr(db_postgres, "get_pg_connection", connect)
    monkeypatch.setattr(db_postgres, "release_pg_connection", lambda connection: connection.close())
    monkeypatch.setattr(db, "get_connector", PostgresConnector)
    monkeypatch.setattr(db, "invalidate_folder_phase_aggregates", lambda **kw: invalidations.append(kw))

    def run(worker_role, callback):
        role.value = worker_role
        try:
            return callback()
        finally:
            del role.value

    def assert_blocked(future):
        assert waiting.wait(5), "waiting transaction never connected"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with admin.cursor() as cur:
                cur.execute("SELECT pg_blocking_pids(%s)", (pids["waiting"],))
                if pids["held"] in cur.fetchone()[0]:
                    return
            assert not future.done(), "second operation finished without waiting for the image lock"
            time.sleep(0.01)
        pytest.fail("PostgreSQL did not report the expected lock dependency")

    try:
        yield run, held, release, assert_blocked, invalidations
    finally:
        release.set()
        with admin.cursor() as cur:
            cur.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        admin.close()


@pytest.mark.parametrize("bbox", [DETECTED, None], ids=["write", "clear"])
def test_promotion_holding_image_lock_suppresses_later_bbox_write(isolated_schema, bbox):
    run, held, release, assert_blocked, invalidations = isolated_schema
    # The backfill has already observed a NULL candidate before detection starts.
    assert db.get_connector().query_one("SELECT bird_bbox FROM images WHERE id = ?", (3,))["bird_bbox"] is None
    with ThreadPoolExecutor(max_workers=2) as executor:
        promotion = executor.submit(run, "held", lambda: select_region(3, 9, "test/646", expect_bird_bbox=None))
        try:
            assert held.wait(5), "promotion never reached its commit boundary"
            writer = executor.submit(run, "waiting", lambda: db.update_image_bird_bbox(3, bbox))
            assert_blocked(writer)
        finally:
            release.set()
        promoted = promotion.result(timeout=5)
        assert promoted["status"] == "selected"
        assert writer.result(timeout=5) is False
    row = db.get_connector().query_one("SELECT bird_bbox FROM images WHERE id = ?", (3,))
    assert row["bird_bbox"] == promoted["bird_bbox"]
    assert invalidations == []


def test_prior_bbox_write_rejects_promotion_with_stale_expected_value(isolated_schema):
    run, held, release, assert_blocked, invalidations = isolated_schema
    with ThreadPoolExecutor(max_workers=2) as executor:
        writer = executor.submit(run, "held", lambda: db.update_image_bird_bbox(3, DETECTED))
        try:
            assert held.wait(5), "bbox writer never reached its commit boundary"
            promotion = executor.submit(run, "waiting", lambda: select_region(3, 9, "test/646", expect_bird_bbox=None))
            assert_blocked(promotion)
        finally:
            release.set()
        assert writer.result(timeout=5) is True
        assert promotion.result(timeout=5)["status"] == "production_changed"
    assert db.get_connector().query_one("SELECT bird_bbox FROM images WHERE id = ?", (3,))["bird_bbox"] == DETECTED
    assert db.get_connector().query("SELECT id FROM image_localization_selections") == []
    assert invalidations == [{"folder_id": 8}]
