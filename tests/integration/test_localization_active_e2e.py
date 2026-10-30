"""Active-mode proofs use synthetic approvals in the isolated test DB only."""
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event

import pytest

from modules.localization_active import ActiveAuthority
from modules.localization_authority_store import AuthorityStore
from modules.localization_legacy import read_bird_bbox
from modules.localization_policy_approval import register_runtime_policy
from tests.integration.test_localization_authority_e2e import RULE, SCOPE, SOURCE, image_run

pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def _clean(postgres_test_session, clean_postgres):
    yield


def active_work(*, tagged=False, runtime=True):
    store = AuthorityStore()
    authority = ActiveAuthority(store)
    key = register_runtime_policy(store, SCOPE) if runtime else store.register_policy(RULE.read_bytes(),SCOPE)
    # Deliberately no production approval bypass: fixtures write isolated SQL.
    store.conn.execute(
        "INSERT INTO localization_policy_approvals (policy_hash,revision,active,geometry_allowed,"
        "species_allowed,qualification_sha256,receipt,approved_by) "
        "VALUES (?,1,TRUE,TRUE,TRUE,?,?::jsonb,'synthetic-test-fixture')",
        (key, 'f'*64, json.dumps({'synthetic': True, 'geometry_bands': ['small','medium','large'], 'species_bands':['medium','large']})),
    )
    store.conn.execute("UPDATE localization_authority_control SET reservation_inventory_sha256=? WHERE id=1", ('a'*64,))
    authority.set_freshness(True)
    authority.activate(key, 'f'*64, confirmed=True)
    iid, rid = image_run(tagged=tagged)
    store.conn.execute("UPDATE image_localization_runs SET display_width=100,display_height=100 WHERE id=?", (rid,))
    work = store.observe(iid, key, source_observation=SOURCE)
    return store, authority, key, iid, rid, work


def test_active_runtime_can_select_untagged_image_and_off_keeps_valid_selection():
    store, authority, key, iid, _, observed = active_work()
    assert observed and observed['outcome'] == 'accept'
    assert authority.apply_claim(store.claim_next(), source_observation=SOURCE)
    row = store.conn.query_one("SELECT * FROM image_localization_selections WHERE image_id=? AND revoked_at IS NULL", (iid,))
    assert row['selected_by'] == 'authority:'+key
    assert read_bird_bbox(store.conn, iid) == row['projected_bird_bbox']
    store.set_mode('off')
    assert read_bird_bbox(store.conn, iid) == row['projected_bird_bbox']
    assert store.conn.query_one("SELECT selection_only FROM localization_discovery_state WHERE image_id=?", (iid,))['selection_only']


@pytest.mark.parametrize('change', ['mode','approval','source','ownership','reservation','lease'])
def test_changes_during_work_prevent_publication(change):
    store, authority, key, iid, _, observed = active_work()
    assert observed
    claim = store.claim_next()
    if change == 'mode':
        store.set_mode('off')
    elif change == 'approval':
        assert authority.revoke_policy(key, 'fixture revocation')
    elif change == 'source':
        pass
    elif change == 'ownership':
        # Same-value explicit edits must change identity too.
        store.conn.execute("UPDATE images SET bird_bbox=bird_bbox WHERE id=?", (iid,))
    elif change == 'reservation':
        store.conn.execute(
            "INSERT INTO localization_authority_reservations (inventory_sha256,image_id,original_run_id,original_region_id,evidence) "
            "VALUES (?,?,1,1,'{}'::jsonb)", ('a'*64,iid),
        )
    elif change == 'lease':
        store.conn.execute("UPDATE localization_authority_attempts SET lease_until=clock_timestamp()-interval '1 second' WHERE id=?", (claim['id'],))
    source = {**SOURCE, 'hash': 'changed'} if change == 'source' else SOURCE
    assert not authority.apply_claim(claim, source_observation=source)
    assert not store.conn.query("SELECT id FROM image_localization_selections WHERE image_id=?", (iid,))


def test_revocation_immediately_hides_and_bounded_cleanup_restores_baseline():
    store, authority, key, iid, _, _ = active_work()
    assert authority.apply_claim(store.claim_next(), source_observation=SOURCE)
    assert read_bird_bbox(store.conn, iid)
    authority.revoke_policy(key, 'fixture revoke')
    assert read_bird_bbox(store.conn, iid) is None
    assert authority.cleanup_invalid(limit=1) == 1
    assert store.conn.query_one("SELECT bird_bbox FROM images WHERE id=?", (iid,))['bird_bbox'] is None
    assert not store.conn.query("SELECT id FROM image_localization_selections WHERE image_id=? AND revoked_at IS NULL", (iid,))


def test_policy_owned_replacement_is_atomic_and_preserves_original_baseline():
    store, authority, key, iid, rid, _ = active_work()
    assert authority.apply_claim(store.claim_next(), source_observation=SOURCE)
    old = store.conn.query_one("SELECT id FROM image_localization_selections WHERE image_id=? AND revoked_at IS NULL", (iid,))['id']
    store.conn.execute("UPDATE image_localization_runs SET is_current=FALSE WHERE id=?", (rid,))
    new = store.conn.execute_returning(
        "INSERT INTO image_localization_runs (image_id,detector_key,detector_version,detector_config_hash,rendition_version,"
        "source_hash,source_hash_version,rendition_hash,status,is_current,coord_space,display_width,display_height) "
        "VALUES (?,'bird',?,?,?,'source','v1','rendition','detected',TRUE,'display_normalized',100,100) RETURNING id",
        (iid, SCOPE.detector_version, SCOPE.detector_config_hash, SCOPE.rendition_version),
    )[0]['id']
    store.conn.execute("INSERT INTO image_regions (localization_run_id,object_class,rank,confidence,x1,y1,x2,y2) VALUES (?,'bird',0,0.9,0,0,0.5,0.5)", (new,))
    store.observe(iid,key,source_observation=SOURCE)
    assert authority.apply_claim(store.claim_next(),source_observation=SOURCE)
    rows = store.conn.query("SELECT * FROM image_localization_selections WHERE image_id=? ORDER BY id", (iid,))
    assert len(rows) == 2 and rows[0]['id'] == old and rows[0]['revoked_at'] and rows[1]['revoked_at'] is None
    authority.revoke_policy(key,'rollback replacement')
    assert authority.cleanup_invalid(limit=1) == 1
    assert store.conn.query_one("SELECT bird_bbox FROM images WHERE id=?", (iid,))['bird_bbox'] is None


def test_cleanup_preserves_same_value_external_projection_edit():
    store, authority, key, iid, _, _ = active_work()
    assert authority.apply_claim(store.claim_next(),source_observation=SOURCE)
    box = read_bird_bbox(store.conn,iid)
    store.conn.execute("UPDATE images SET bird_bbox=bird_bbox WHERE id=?", (iid,))
    authority.revoke_policy(key,'preserve user edit')
    assert authority.cleanup_invalid(limit=1) == 1
    assert store.conn.query_one("SELECT bird_bbox FROM images WHERE id=?", (iid,))['bird_bbox'] == box
    assert read_bird_bbox(store.conn,iid) == box


def test_authority_worker_routes_active_publication_without_gpu(monkeypatch):
    from modules.localization_authority_worker import ShadowAuthorityWorker

    store, _, _, iid, _, _ = active_work()
    monkeypatch.setattr('modules.localization_authority_worker.observe_source',lambda _: SOURCE)
    assert ShadowAuthorityWorker(store).poll_once() == 1
    assert store.conn.query_one("SELECT id FROM image_localization_selections WHERE image_id=? AND revoked_at IS NULL",(iid,))


@pytest.mark.parametrize('transition',['off','revoke'])
def test_control_changes_serialize_after_in_progress_publication(monkeypatch,transition):
    store,authority,key,iid,_,_ = active_work()
    claim = store.claim_next()
    entered,release = Event(),Event()
    finish = ActiveAuthority._finish
    def paused(tx,*args):
        entered.set()
        assert release.wait(10)
        return finish(tx,*args)
    monkeypatch.setattr(ActiveAuthority,'_finish',staticmethod(paused))
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            applied = pool.submit(authority.apply_claim,claim,source_observation=SOURCE)
            assert entered.wait(10)
            other = ActiveAuthority(AuthorityStore())
            changed = pool.submit(other.store.set_mode,'off') if transition == 'off' else pool.submit(other.revoke_policy,key,'concurrent revocation')
            try:
                with pytest.raises(TimeoutError):
                    changed.result(timeout=0.1)
            finally:
                release.set()
            assert applied.result(timeout=10)
            changed.result(timeout=10)
    finally:
        release.set()
    assert bool(read_bird_bbox(store.conn,iid)) == (transition == 'off')


def test_lease_expiry_at_completion_rolls_back_selection_and_lineage(monkeypatch):
    store,authority,_,iid,_,_ = active_work()
    claim = store.claim_next()
    finish = ActiveAuthority._finish
    def expire(tx,*args):
        tx.execute("UPDATE localization_authority_attempts SET lease_until=clock_timestamp()-interval '1 second' WHERE id=?",(claim['id'],))
        return finish(tx,*args)
    monkeypatch.setattr(ActiveAuthority,'_finish',staticmethod(expire))
    assert not authority.apply_claim(claim,source_observation=SOURCE)
    assert not store.conn.query("SELECT id FROM image_localization_selections WHERE image_id=?",(iid,))
    assert not store.conn.query("SELECT * FROM localization_selection_lineage")
    assert store.conn.query_one("SELECT status FROM localization_authority_attempts WHERE id=?",(claim['id'],))['status'] == 'running'


def test_cached_r2_evaluation_does_not_broaden_original_population():
    store,authority,key,iid,_,first = active_work(tagged=True,runtime=False)
    store.conn.execute("DELETE FROM image_keywords WHERE image_id=?",(iid,))
    second = store.observe(iid,key,source_observation=SOURCE)
    assert second['evaluation_id'] == first['evaluation_id'] and second['outcome'] == 'accept'
    assert not authority.apply_claim(store.claim_next(),source_observation=SOURCE)
    assert not authority.apply_claim(store.claim_next(),source_observation=SOURCE)
    assert not store.conn.query("SELECT id FROM image_localization_selections WHERE image_id=?",(iid,))


def test_active_diagnostics_report_actual_permissions_and_freshness():
    store,authority,key,_,_,_=active_work()
    status=store.diagnostics()
    assert status['authority_granted'] and status['selection_freshness_enabled']
    assert status['approved_policies'][0]['policy_hash']==key
    authority.revoke_policy(key,'diagnostic fixture')
    assert store.diagnostics()['authority_granted'] is False


def test_path_change_invalidates_managed_selection_before_next_scan():
    store,authority,_,iid,_,_=active_work()
    assert authority.apply_claim(store.claim_next(),source_observation=SOURCE)
    assert read_bird_bbox(store.conn,iid)
    store.conn.execute("UPDATE images SET file_path=file_path||'.moved' WHERE id=?",(iid,))
    assert read_bird_bbox(store.conn,iid) is None
