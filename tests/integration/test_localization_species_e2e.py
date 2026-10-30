"""Species lifecycle proofs use the isolated DB and synthetic SQL approvals; no models."""
import pytest

from modules import db
from modules.localization_species import SpeciesStore
from tests.integration.test_localization_active_e2e import active_work
from tests.integration.test_localization_authority_e2e import SOURCE

pytestmark=pytest.mark.postgres


@pytest.fixture(autouse=True)
def _clean(postgres_test_session,clean_postgres):
    yield


def selected():
    store,authority,key,iid,rid,_=active_work()
    assert authority.apply_claim(store.claim_next(),source_observation=SOURCE)
    species=SpeciesStore(store.conn)
    return store,authority,species,key,iid,rid


def predictions():
    return [('Carolina Wren',0.95)]


def keyword(conn,iid,norm,source='user'):
    key=conn.execute_returning("INSERT INTO keywords_dim (keyword_norm) VALUES (?) ON CONFLICT (keyword_norm) DO UPDATE SET keyword_norm=EXCLUDED.keyword_norm RETURNING keyword_id",(norm,))[0]['keyword_id']
    conn.execute("INSERT INTO image_keywords (image_id,keyword_id,source) VALUES (?,?,?) ON CONFLICT (image_id,keyword_id) DO UPDATE SET source=EXCLUDED.source",(iid,key,source))


def test_selection_only_admission_and_scope_exit_do_not_self_sustain():
    store,authority,species,key,iid,_=selected()
    work=species.observe(iid,source_observation=SOURCE)
    assert work['action']=='classify'
    assert species.publish(species.claim_next(image_id=iid),predictions=predictions(),embedding=[0.1]*768,source_observation=SOURCE)
    assert 'species:carolina wren' in db.get_resolved_image_keywords(iid).lower()
    assert species.observe(iid,source_observation=SOURCE)['id']==work['id']
    authority.revoke_policy(key,'scope exit')
    assert 'species:' not in db.get_resolved_image_keywords(iid).lower()
    cleanup=species.observe(iid,source_observation=SOURCE)
    assert cleanup['action']=='out_of_scope'
    assert species.publish(species.claim_next(image_id=iid),source_observation=SOURCE)
    assert not store.conn.query("SELECT * FROM image_keywords WHERE image_id=?",(iid,))
    assert not store.conn.query("SELECT * FROM image_embeddings_768 WHERE image_id=?",(iid,))
    assert not store.conn.query_one("SELECT localization_species_in_scope(?) AS ok",(iid,))['ok']


def test_independent_discovery_changes_scope_exit_to_fallback():
    store,authority,species,key,iid,_=selected()
    species.observe(iid,source_observation=SOURCE)
    assert species.publish(species.claim_next(image_id=iid),predictions=predictions(),embedding=[0.1]*768,source_observation=SOURCE)
    keyword(store.conn,iid,'birds')
    authority.revoke_policy(key,'independent fallback')
    assert species.observe(iid,source_observation=SOURCE)['action']=='fallback'
    assert species.publish(species.claim_next(image_id=iid),predictions=predictions(),embedding=[0.2]*768,space_code='bioclip_2_image',source_observation=SOURCE)
    assert store.conn.query_one("SELECT localization_species_in_scope(?) AS ok",(iid,))['ok']


def test_curated_species_is_preserved_without_inference():
    store,_,species,_,iid,_=selected()
    keyword(store.conn,iid,'species:curated bird')
    assert species.observe(iid,source_observation=SOURCE)['action']=='preserve'
    assert species.publish(species.claim_next(image_id=iid),source_observation=SOURCE)
    assert db.get_resolved_image_keywords(iid)=='species:curated bird'


def test_same_value_edit_during_inference_fences_publication_and_survives_cleanup():
    store,authority,species,key,iid,_=selected()
    species.observe(iid,source_observation=SOURCE)
    claim=species.claim_next(image_id=iid)
    keyword(store.conn,iid,'species:carolina wren')
    assert not species.publish(claim,predictions=predictions(),embedding=[0.1]*768,source_observation=SOURCE)
    assert not store.conn.query("SELECT * FROM localization_species_outputs")
    authority.revoke_policy(key,'preserve curated output')
    species.observe(iid,source_observation=SOURCE)
    assert species.publish(species.claim_next(image_id=iid),source_observation=SOURCE)
    assert 'species:carolina wren' in db.get_resolved_image_keywords(iid).lower()


def test_embedding_failure_rolls_back_keywords_lineage_and_completion():
    store,_,species,_,iid,_=selected()
    species.observe(iid,source_observation=SOURCE)
    claim=species.claim_next(image_id=iid)
    with pytest.raises(Exception):
        species.publish(claim,predictions=predictions(),embedding=[0.1]*7,source_observation=SOURCE)
    assert not store.conn.query("SELECT * FROM image_keywords WHERE image_id=?",(iid,))
    assert not store.conn.query("SELECT * FROM localization_species_outputs")
    assert store.conn.query_one("SELECT status FROM localization_species_work WHERE id=?",(claim['id'],))['status']=='running'
    assert species.publish(claim,predictions=predictions(),embedding=[0.1]*768,source_observation=SOURCE)
    assert not species.publish(claim,predictions=predictions(),embedding=[0.1]*768,source_observation=SOURCE)


def test_expired_species_worker_cannot_publish_after_reassignment():
    store,_,species,_,iid,_=selected()
    species.observe(iid,source_observation=SOURCE)
    old=species.claim_next(image_id=iid)
    store.conn.execute("UPDATE localization_species_work SET lease_until=clock_timestamp()-interval '1 second' WHERE id=?",(old['id'],))
    new=species.claim_next(image_id=iid)
    assert new['fencing_token']>old['fencing_token']
    assert not species.publish(old,predictions=predictions(),embedding=[0.1]*768,source_observation=SOURCE)
    assert species.publish(new,predictions=predictions(),embedding=[0.1]*768,source_observation=SOURCE)


def test_keyword_refresh_preserves_generated_tag_provenance():
    store,authority,species,key,iid,_=selected()
    species.observe(iid,source_observation=SOURCE)
    assert species.publish(species.claim_next(image_id=iid),predictions=predictions(),embedding=[0.1]*768,source_observation=SOURCE)
    db.update_image_keywords_for_image(iid,'landscape',scope='keywords')
    assert not store.conn.query_one("SELECT independent FROM localization_discovery_evidence WHERE image_id=?",(iid,))['independent']
    authority.revoke_policy(key,'after keyword refresh')
    assert species.observe(iid,source_observation=SOURCE)['action']=='out_of_scope'


def test_same_value_edit_of_published_species_transfers_ownership():
    store,authority,species,key,iid,_=selected()
    species.observe(iid,source_observation=SOURCE)
    assert species.publish(species.claim_next(image_id=iid),predictions=predictions(),embedding=[0.1]*768,source_observation=SOURCE)
    store.conn.execute("UPDATE image_keywords SET confidence=confidence WHERE image_id=? AND source='bioclip_region'",(iid,))
    authority.revoke_policy(key,'keep explicit edit')
    species.observe(iid,source_observation=SOURCE)
    assert species.publish(species.claim_next(image_id=iid),source_observation=SOURCE)
    assert db.get_resolved_image_keywords(iid).lower()=='species:carolina wren'


def test_rating_only_metadata_update_does_not_transfer_keyword_ownership():
    store,_,species,_,iid,_=selected()
    species.observe(iid,source_observation=SOURCE)
    assert species.publish(species.claim_next(image_id=iid),predictions=predictions(),embedding=[0.1]*768,source_observation=SOURCE)
    path=store.conn.query_one('SELECT file_path FROM images WHERE id=?',(iid,))['file_path']
    before=store.conn.query('SELECT * FROM localization_change_journal WHERE image_id=? ORDER BY id',(iid,))
    assert db.update_image_metadata(path,'birds,species:Carolina Wren','title','',4,'',keywords_changed=False)
    assert store.conn.query('SELECT * FROM localization_change_journal WHERE image_id=? ORDER BY id',(iid,))==before


def test_schema_bootstrap_is_repeatable_with_protected_views():
    from modules import db_postgres
    db_postgres.init_db()
    db_postgres.init_db()


def test_runner_scalar_and_sql_completeness_share_selection_only_scope():
    store,_,species,_,iid,_=selected()
    assert any(r['id']==iid for r in db.get_images_with_keyword(resolved_image_ids=[iid]))
    assert not db.is_image_bird_species_complete(iid,include_bbox=False)
    predicate=db.get_phase_incomplete_sql('bird_species','i')
    assert store.conn.query_one('SELECT id FROM images i WHERE id=? AND '+predicate,(iid,))
    species.observe(iid,source_observation=SOURCE)
    assert species.publish(species.claim_next(image_id=iid),predictions=predictions(),embedding=[0.1]*768,source_observation=SOURCE)
    assert db.is_image_bird_species_complete(iid,include_bbox=False)
    assert not store.conn.query_one('SELECT id FROM images i WHERE id=? AND '+predicate,(iid,))
    keyword(store.conn,iid,'birds')
    species.observe(iid,source_observation={**SOURCE,'hash':'changed'})
    assert not db.is_image_bird_species_complete(iid,include_bbox=False)
