"""One chained lifecycle proof across authority, idle lane, species publication and readers (#710).

Isolated DB with synthetic SQL approvals; no models. Each stage has focused coverage in the
authority, active, species and lane suites; this test proves they compose in order.
"""
import pytest

from modules import db
from modules import localization_lane as lane
from tests.integration.test_localization_authority_e2e import SOURCE
from tests.integration.test_localization_species_e2e import predictions, selected

pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def _clean(postgres_test_session, clean_postgres):
    lane.reset_state()
    yield
    lane.reset_state()


def _compat_box(conn, iid):
    return conn.query_one("SELECT bird_bbox FROM image_bird_bbox_compat WHERE image_id=?", (iid,))["bird_bbox"]


def test_selection_to_species_to_revocation_survives_restart_with_reader_parity():
    store, authority, species, key, iid, _ = selected()
    conn = store.conn
    assert _compat_box(conn, iid) is not None                       # applied selection is visible

    assert species.observe(iid, source_observation=SOURCE)["action"] == "classify"
    assert lane.select_species_candidates() == [iid]                 # GPU work waits for the idle lane
    assert lane._enqueue_species([iid])
    lane.reset_state()                                               # simulated process restart
    assert lane.select_species_candidates() == [iid]                 # durable work is still due

    claim = species.claim_next(image_id=iid)
    assert species.publish(claim, predictions=predictions(), embedding=[0.1] * 768, source_observation=SOURCE)
    assert "species:carolina wren" in db.get_resolved_image_keywords(iid).lower()
    visible = conn.query("SELECT kd.keyword_norm FROM localization_visible_image_keywords ik "
                         "JOIN keywords_dim kd ON kd.keyword_id=ik.keyword_id WHERE ik.image_id=?", (iid,))
    assert "species:carolina wren" in {r["keyword_norm"] for r in visible}
    assert db.is_image_bird_species_complete(iid, include_bbox=False)
    assert lane.select_species_candidates() == []

    authority.revoke_policy(key, "chained rollback proof")
    assert _compat_box(conn, iid) is None                            # stale geometry hidden at once
    assert "species:" not in db.get_resolved_image_keywords(iid).lower()
    assert not conn.query_one("SELECT localization_species_in_scope(?) AS ok", (iid,))["ok"]

    lane.reset_state()                                               # restart before cleanup
    cleanup = species.observe(iid, source_observation=SOURCE)
    assert cleanup["action"] == "out_of_scope"
    assert species.publish(species.claim_next(image_id=iid), source_observation=SOURCE)
    assert not conn.query("SELECT 1 FROM image_keywords WHERE image_id=?", (iid,))
    assert not conn.query("SELECT 1 FROM image_embeddings_768 WHERE image_id=?", (iid,))
    status = store.diagnostics()["species"]
    assert status["refresh_pending"] == 0 and status["cleanup_pending"] == 0
