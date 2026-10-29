"""Real PostgreSQL proofs for observational authority metadata; no models."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest

from modules import db
from modules.localization_authority_store import AuthorityStore
from modules.localization_evaluation import ArtifactScope

pytestmark = pytest.mark.postgres
SCOPE = ArtifactScope("test-bird/1", "test-config", "test-rendition/1")
RULE = Path(__file__).resolve().parents[1] / "fixtures/localization/rule-frozen-20261026.json"
SOURCE = {"status": "available", "hash": "source", "version": "v1"}


@pytest.fixture(autouse=True)
def _clean(postgres_test_session, clean_postgres):
    yield


def policy(store):
    return store.register_policy(RULE.read_bytes(), SCOPE)


def image_run(*, confidence=0.8, tagged=True):
    conn = db.get_connector()
    image_id = conn.execute_returning(
        "INSERT INTO images (file_path) VALUES (?) RETURNING id", (f"/test-{uuid4().hex}.jpg",),
    )[0]["id"]
    run_id = conn.execute_returning(
        "INSERT INTO image_localization_runs "
        "(image_id, detector_key, detector_version, detector_config_hash, rendition_version, "
        "source_hash, source_hash_version, rendition_hash, status, is_current, coord_space) "
        "VALUES (?, 'bird', ?, ?, ?, 'source', 'v1', 'rendition', 'detected', TRUE, "
        "'display_normalized') RETURNING id",
        (image_id, SCOPE.detector_version, SCOPE.detector_config_hash, SCOPE.rendition_version),
    )[0]["id"]
    conn.execute(
        "INSERT INTO image_regions (localization_run_id, object_class, rank, confidence, x1,y1,x2,y2) "
        "VALUES (?, 'bird', 0, ?, 0,0,1,0.02)", (run_id, confidence),
    )
    if tagged:
        existing = conn.query_one("SELECT keyword_id FROM keywords_dim WHERE keyword_norm='birds'")
        key = existing["keyword_id"] if existing else conn.execute_returning(
            "INSERT INTO keywords_dim (keyword_norm) VALUES ('birds') RETURNING keyword_id",
        )[0]["keyword_id"]
        conn.execute("INSERT INTO image_keywords (image_id,keyword_id,source) VALUES (?,?,'user')",
                     (image_id, key))
    return image_id, run_id


def test_exact_policy_registration_is_idempotent_and_validated():
    store = AuthorityStore()
    first = policy(store)
    assert isinstance(first, str) and len(first) == 64
    assert policy(store) == first
    with pytest.raises(ValueError, match="hash mismatch"):
        store.register_policy(b"changed", SCOPE)
    assert len(store.conn.query("SELECT * FROM localization_authority_policies")) == 1


def setup_work(*, confidence=0.8):
    store = AuthorityStore()
    store.set_mode("shadow")
    key = policy(store)
    image_id, run_id = image_run(confidence=confidence)
    observed = store.observe(image_id, key, source_observation=SOURCE)
    return store, image_id, key, observed


@pytest.mark.parametrize("confidence,outcome", [(0.8, "accept"), (0.4, "reject")])
def test_evaluations_and_terminal_attempts_are_cached(confidence, outcome):
    store, image_id, key, first = setup_work(confidence=confidence)
    second = store.observe(image_id, key, source_observation=SOURCE)
    assert first == second
    assert first["outcome"] == outcome
    claim = store.claim_next()
    assert store.complete(claim, source_observation=SOURCE)
    assert store.claim_next() is None
    third = store.observe(image_id, key, source_observation=SOURCE)
    assert third["attempt_id"] == first["attempt_id"]
    assert store.claim_next() is None


def test_changed_mode_or_observation_reopens_application_not_evaluation():
    store, image_id, key, first = setup_work()
    assert store.complete(store.claim_next(), source_observation=SOURCE)
    store.set_mode("off")
    assert store.observe(image_id, key, source_observation=SOURCE) is None
    store.set_mode("shadow")
    second = store.observe(image_id, key, source_observation=SOURCE)
    assert second["evaluation_id"] == first["evaluation_id"]
    assert second["attempt_id"] != first["attempt_id"]
    store.conn.execute("UPDATE images SET bird_bbox = '{\"external\":true}'::jsonb WHERE id=?", (image_id,))
    third = store.observe(image_id, key, source_observation=SOURCE)
    assert third["evaluation_id"] == first["evaluation_id"]
    assert third["attempt_id"] != second["attempt_id"]


def test_expired_worker_cannot_renew_or_publish_after_reassignment():
    store, *_ = setup_work()
    old = store.claim_next()
    store.conn.execute("UPDATE localization_authority_attempts SET lease_until=clock_timestamp()-interval '1 second'")
    assert not store.renew(old)
    fresh = store.claim_next()
    assert fresh["id"] == old["id"] and fresh["fencing_token"] > old["fencing_token"]
    assert not store.complete(old, source_observation=SOURCE)
    assert store.renew(fresh)
    assert store.complete(fresh, source_observation=SOURCE)


def test_competing_claimers_have_one_winner():
    store, *_ = setup_work()
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: AuthorityStore().claim_next(), range(2)))
    assert sum(claim is not None for claim in claims) == 1
    winner = next(claim for claim in claims if claim)
    assert store.complete(winner, source_observation=SOURCE)


def test_mode_change_and_source_change_fence_publication():
    store, image_id, key, _ = setup_work()
    claim = store.claim_next()
    store.set_mode("off")
    assert not store.complete(claim, source_observation=SOURCE)
    store.set_mode("shadow")
    store.observe(image_id, key, source_observation=SOURCE)
    assert not store.complete(store.claim_next(), source_observation={**SOURCE, "hash": "changed"})
    assert store.conn.query_one("SELECT count(*) AS n FROM localization_authority_lineage")["n"] == 0


def test_unknown_inventory_and_image_reservations_are_visible_in_proposals():
    store, image_id, key, _ = setup_work()
    assert store.complete(store.claim_next(), source_observation=SOURCE)
    row = store.conn.query_one("SELECT proposal FROM localization_authority_attempts")
    assert row["proposal"]["application_blocked"] == "reservation_inventory_unverified"
    store.conn.execute(
        "INSERT INTO localization_authority_reservations "
        "(inventory_sha256,image_id,original_run_id,original_region_id,evidence) "
        "VALUES (?, ?, 10, 20, '{}'::jsonb)", ("a" * 64, image_id),
    )
    store.observe(image_id, key, source_observation=SOURCE)
    assert store.complete(store.claim_next(), source_observation=SOURCE)
    row = store.conn.query_one("SELECT proposal FROM localization_authority_attempts ORDER BY id DESC LIMIT 1")
    assert row["proposal"]["application_blocked"] == "image_reserved"


def test_shadow_metadata_never_changes_production_state_or_phase_work():
    store, image_id, key, _ = setup_work()
    tables = ("images", "image_keywords", "image_embeddings", "image_localization_selections",
              "image_phase_status", "image_phase_work_claims", "jobs")
    before = {table: store.conn.query(f"SELECT * FROM {table}") for table in tables}
    assert store.complete(store.claim_next(), source_observation=SOURCE)
    assert {table: store.conn.query(f"SELECT * FROM {table}") for table in tables} == before
    assert store.conn.query_one("SELECT outputs_protected FROM localization_authority_lineage")["outputs_protected"]
    with pytest.raises(ValueError, match="off or shadow"):
        store.set_mode("active")


def test_crashed_work_has_bounded_recovery_and_never_reopens_after_exhaustion():
    store, *_ = setup_work()
    for _ in range(3):
        assert store.claim_next()
        store.conn.execute("UPDATE localization_authority_attempts SET lease_until=clock_timestamp()-interval '1 second'")
    assert store.claim_next() is None
    row = store.conn.query_one("SELECT status,disposition FROM localization_authority_attempts")
    assert row == {"status": "completed", "disposition": "retry_exhausted"}


def test_policy_registration_does_not_grant_approval():
    store = AuthorityStore()
    key = policy(store)
    assert store.conn.query_one(
        "SELECT approval_revision FROM localization_authority_policies WHERE policy_hash=?", (key,),
    )["approval_revision"] == 0


def test_observed_revision_round_trip_still_rejects_old_worker():
    store, image_id, key, _ = setup_work()
    old = store.claim_next()
    changed = {**SOURCE, "hash": "intermediate"}
    store.observe(image_id, key, source_observation=changed)
    store.observe(image_id, key, source_observation=SOURCE)
    assert not store.complete(old, source_observation=SOURCE)


def test_reservations_survive_changed_artifacts_and_preserve_original_evidence(monkeypatch):
    from modules import localization_authority_reservations as reservations

    store, image_id, key, _ = setup_work()
    monkeypatch.setattr(reservations, "read_frozen_inventory", lambda _: (
        "a" * 64, [{"image_id": image_id, "run_id": 10, "region_id": 20}],
    ))
    first = reservations.import_frozen_reservations(store, "synthetic-test-fixture")
    revision = store.control()["revision"]
    assert reservations.import_frozen_reservations(store, "synthetic-test-fixture") == first
    assert store.control()["revision"] == revision
    store.conn.execute("UPDATE image_localization_runs SET rendition_hash='new' WHERE image_id=?", (image_id,))
    store.observe(image_id, key, source_observation=SOURCE)
    claim = store.claim_next()
    assert not store.complete(claim, source_observation=SOURCE)  # obsolete context
    claim = store.claim_next()
    assert store.complete(claim, source_observation=SOURCE)
    row = store.conn.query_one("SELECT proposal FROM localization_authority_attempts ORDER BY id DESC LIMIT 1")
    assert row["proposal"]["application_blocked"] == "image_reserved"
    evidence = store.conn.query_one("SELECT original_run_id,original_region_id FROM localization_authority_reservations")
    assert evidence == {"original_run_id": 10, "original_region_id": 20}


def test_retry_backoff_is_durable_and_expired_worker_cannot_schedule_retry():
    store, *_ = setup_work()
    claim = store.claim_next()
    assert store.fail(claim, "synthetic_fault")
    assert store.claim_next() is None
    row = store.conn.query_one("SELECT last_error,status,available_at>clock_timestamp() AS delayed FROM localization_authority_attempts")
    assert row == {"last_error": "synthetic_fault", "status": "queued", "delayed": True}
    assert not store.fail(claim, "stale_fault")


def test_forward_migration_creates_tables_in_a_disposable_schema():
    from modules import db_postgres
    from psycopg2 import sql
    from types import SimpleNamespace

    path = Path(__file__).resolve().parents[2] / "migrations/versions/0045_localization_authority.py"
    spec = importlib.util.spec_from_file_location("authority_migration_pg", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    schema = "authority_test_" + uuid4().hex
    # All DDL rolls back on context exit; no shared application table is altered.
    with db_postgres.PGConnectionManager(commit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            cur.execute(sql.SQL("SET LOCAL search_path TO {}, public").format(sql.Identifier(schema)))
            cur.execute("CREATE TABLE images (id INTEGER PRIMARY KEY)")
            cur.execute("CREATE TABLE image_localization_runs (id BIGINT PRIMARY KEY)")
            migration.op = SimpleNamespace(execute=cur.execute)
            migration.upgrade()
            cur.execute("SELECT mode FROM localization_authority_control WHERE id=1")
            assert cur.fetchone() == ("off",)
            cur.execute("SELECT count(*) FROM pg_tables WHERE schemaname=%s AND tablename LIKE 'localization_authority_%%'", (schema,))
            assert cur.fetchone()[0] == 8


def test_policies_and_evaluations_cannot_be_rewritten():
    store, *_ = setup_work()
    with pytest.raises(Exception, match="immutable"):
        store.conn.execute("UPDATE localization_authority_evaluations SET reason='rewritten'")
    with pytest.raises(Exception, match="immutable"):
        store.conn.execute("UPDATE localization_authority_policies SET scope='{}'::jsonb")


def test_worker_restart_and_finite_sweeps_preserve_scan_progress():
    from modules.localization_authority_worker import ShadowAuthorityWorker

    store = AuthorityStore()
    store.set_mode("shadow")
    policy(store)
    for _ in range(3):
        image_run()
    worker = ShadowAuthorityWorker(store, batch_size=1)
    worker.poll_once()
    first = store.control()
    assert first["scan_cursor"] == 1 and first["scan_upper_bound"] == 3
    image_run()  # arrives after this sweep's captured upper bound
    restarted = ShadowAuthorityWorker(AuthorityStore(), batch_size=1)
    restarted.poll_once()
    restarted.poll_once()
    assert store.control()["scan_cursor"] == 0
    assert store.conn.query_one("SELECT count(*) AS n FROM localization_authority_evaluations")["n"] == 3
    for _ in range(4):
        restarted.poll_once()
    assert store.conn.query_one("SELECT count(*) AS n FROM localization_authority_evaluations")["n"] == 4
    assert store.conn.query_one("SELECT count(*) AS n FROM localization_authority_attempts")["n"] == 4


def test_worker_scan_fault_budget_survives_restart(monkeypatch):
    from modules.localization_authority_worker import ShadowAuthorityWorker

    store, image_id, key, _ = setup_work()
    calls = []

    def faulty(*args, **kwargs):
        calls.append(1)
        raise ValueError("synthetic scan fault")
    monkeypatch.setattr(store, "observe", faulty)
    worker = ShadowAuthorityWorker(store)
    for _ in range(3):
        worker.poll_once()
        worker.poll_once()  # durable backoff prevents immediate retries
        store.conn.execute("UPDATE localization_authority_scan_faults SET retry_at=clock_timestamp()-interval '1 second'")
    assert len(calls) == 3
    ShadowAuthorityWorker(store).poll_once()
    assert len(calls) == 3
    row = store.conn.query_one("SELECT attempts,status,error_code FROM localization_authority_scan_faults")
    assert row == {"attempts": 3, "status": "exhausted", "error_code": "ValueError"}


def test_worker_reads_source_outside_transactions_and_only_writes_metadata(tmp_path):
    from modules.localization_authority_worker import ShadowAuthorityWorker, observe_source

    store = AuthorityStore()
    store.set_mode("shadow")
    policy(store)
    image_id, _ = image_run()
    path = tmp_path / "source.bin"
    path.write_bytes(b"synthetic image bytes; no decoder or model should be called")
    source = observe_source(str(path))
    store.conn.execute("UPDATE images SET file_path=? WHERE id=?", (str(path), image_id))
    store.conn.execute("UPDATE image_localization_runs SET source_hash=?,source_hash_version=? WHERE image_id=?",
                       (source["hash"], source["version"], image_id))
    tables = ("images", "image_keywords", "image_embeddings", "image_localization_selections", "jobs",
              "image_phase_status", "image_phase_work_claims")
    before = {table: store.conn.query(f"SELECT * FROM {table}") for table in tables}
    assert ShadowAuthorityWorker(store).poll_once() == 1
    assert {table: store.conn.query(f"SELECT * FROM {table}") for table in tables} == before
    proposal = store.conn.query_one("SELECT proposal FROM localization_authority_attempts")["proposal"]
    assert proposal["source_current"] and proposal["propose_selection"]
    assert proposal["geometry_action"] == "propose_selection"
    assert "policy_unqualified" in proposal["application_blockers"]
    assert not proposal["authority_granted"]
    diagnostic = store.diagnostics()
    assert diagnostic["mode"] == "shadow" and diagnostic["pending"] == 0
    assert diagnostic["proposed_actions"] == {"classify": 1}


def test_competing_observers_deduplicate_evaluations_and_attempts():
    store = AuthorityStore()
    store.set_mode("shadow")
    key = policy(store)
    image_id, _ = image_run()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: AuthorityStore().observe(image_id, key, source_observation=SOURCE), range(2)))
    assert results[0] == results[1]
    assert store.conn.query_one("SELECT count(*) AS n FROM localization_authority_evaluations")["n"] == 1
    assert store.conn.query_one("SELECT count(*) AS n FROM localization_authority_attempts")["n"] == 1


def test_mode_change_serializes_after_inflight_metadata_publication(monkeypatch):
    from concurrent.futures import TimeoutError
    import threading
    from modules import localization_authority_store as implementation

    store, *_ = setup_work()
    claim = store.claim_next()
    entered, release, changing = threading.Event(), threading.Event(), threading.Event()
    original = implementation.load_inputs

    def paused(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    def turn_off():
        changing.set()
        AuthorityStore().set_mode("off")

    monkeypatch.setattr(implementation, "load_inputs", paused)
    with ThreadPoolExecutor(max_workers=2) as pool:
        publication = pool.submit(store.complete, claim, source_observation=SOURCE)
        assert entered.wait(5)
        mode_change = pool.submit(turn_off)
        assert changing.wait(5)
        try:
            with pytest.raises(TimeoutError):
                mode_change.result(timeout=0.1)
        finally:
            release.set()
        assert publication.result(timeout=5)
        mode_change.result(timeout=5)
    assert store.control()["mode"] == "off"


def test_unreadable_source_proposes_artifact_refresh_without_scheduling_work():
    store, *_ = setup_work()
    row = store.conn.query_one("SELECT image_id FROM localization_authority_evaluations")
    key = policy(store)
    store.observe(row["image_id"], key, source_observation={"status": "unreadable"})
    assert not store.complete(store.claim_next(), source_observation={"status": "unreadable"})
    assert store.complete(store.claim_next(), source_observation={"status": "unreadable"})
    proposal = store.conn.query_one("SELECT proposal FROM localization_authority_attempts ORDER BY id DESC LIMIT 1")["proposal"]
    assert proposal["geometry_action"] == "refresh_artifact" and not proposal["propose_selection"]
    assert not proposal["authority_granted"]
    assert store.conn.query_one("SELECT count(*) AS n FROM image_phase_work_claims")["n"] == 0


@pytest.mark.parametrize("outcome", ["abstain", "invalid"])
def test_other_negative_decisions_are_immutable_cached_terminal_results(outcome):
    store = AuthorityStore()
    store.set_mode("shadow")
    key = policy(store)
    image_id, run_id = image_run(tagged=outcome != "abstain")
    if outcome == "invalid":
        store.conn.execute(
            "INSERT INTO image_regions (localization_run_id,object_class,rank,confidence,x1,y1,x2,y2) "
            "VALUES (?,'animal',0,0.99,0,0,1,1)", (run_id,),
        )
    first = store.observe(image_id, key, source_observation=SOURCE)
    assert first["outcome"] == outcome
    assert store.complete(store.claim_next(), source_observation=SOURCE)
    assert store.observe(image_id, key, source_observation=SOURCE) == first
    assert store.claim_next() is None
