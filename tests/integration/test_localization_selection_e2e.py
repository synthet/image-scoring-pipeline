"""E2E: production localization selections and the bird_bbox projection (#484). ``pytest.mark.postgres``."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.postgres]

from modules import db  # noqa: E402
from modules.localization import write_run  # noqa: E402
from modules.localization_selection import (  # noqa: E402
    active_selection,
    revoke_selection,
    select_region,
)

SENTINEL = {"detected": False}
RULE = "v1_regate_rule/3:a1c2e1f64b24cc79"


@pytest.fixture(autouse=True)
def _postgres_clean(postgres_test_session, clean_postgres):
    yield


def _image(bbox=SENTINEL) -> int:
    import json
    import uuid

    row = db.get_connector().execute_returning(
        "INSERT INTO images (file_path, bird_bbox) VALUES (?, ?::jsonb) RETURNING id",
        (f"/tmp/sel-{uuid.uuid4().hex}.jpg", json.dumps(bbox) if bbox is not None else None))
    return int(row[0]["id"])


def _run(image_id: int, *, publish: bool, version: str = "v", boxes=((0.1, 0.2, 0.3, 0.4, 0.8),)) -> int:
    run = {"image_id": image_id, "detector_key": "bird", "detector_version": version,
           "detector_config_hash": "h", "coord_space": "display_normalized", "display_width": 1000,
           "display_height": 500, "status": "detected", "is_retryable": False, "is_current": publish}
    regions = [{"conf": c, "rank": i, "region": (x1, y1, x2, y2)} for i, (x1, y1, x2, y2, c) in enumerate(boxes)]
    return write_run(run, regions, publish=publish)


def _region(run_id: int, rank: int = 0) -> int:
    return int(db.get_connector().query_one(
        "SELECT id FROM image_regions WHERE localization_run_id = ? AND rank = ?", (run_id, rank))["id"])


def _bbox(image_id: int):
    return db.get_connector().query_one("SELECT bird_bbox FROM images WHERE id = ?", (image_id,))["bird_bbox"]


def test_unpublished_run_keeps_the_current_run():
    iid = _image()
    shadow = _run(iid, publish=True, version="shadow")
    _run(iid, publish=False, version="promoted")
    current = db.get_connector().query("SELECT id FROM image_localization_runs WHERE image_id = ? AND is_current",
                                       (iid,))
    assert [r["id"] for r in current] == [shadow]


def test_select_projects_bbox_and_revoke_restores_it():
    iid = _image()
    region = _region(_run(iid, publish=False))
    res = select_region(iid, region, RULE, {"stratum": "promote_large"}, expect_bird_bbox=SENTINEL)
    assert res["status"] == "selected"
    assert _bbox(iid) == {"x1": 100, "y1": 100, "x2": 300, "y2": 200, "conf": 0.8,
                          "img_w": 1000, "img_h": 500, "area_frac": 0.04}
    sel = active_selection(iid)
    assert sel["selected_by"] == RULE and sel["previous_bird_bbox"] == SENTINEL
    assert sel["evidence"] == {"stratum": "promote_large"}

    assert revoke_selection(iid, "test")["status"] == "revoked"
    assert _bbox(iid) == SENTINEL and active_selection(iid) is None


def test_select_refuses_changed_production_value():
    iid = _image({"x1": 1, "y1": 1, "x2": 5, "y2": 5, "conf": 0.5, "img_w": 10, "img_h": 10, "area_frac": 0.16})
    region = _region(_run(iid, publish=False))
    assert select_region(iid, region, RULE, expect_bird_bbox=SENTINEL)["status"] == "production_changed"
    assert active_selection(iid) is None


def test_one_active_selection_per_image():
    iid = _image()
    run = _run(iid, publish=False, boxes=((0.1, 0.1, 0.2, 0.2, 0.9), (0.5, 0.5, 0.6, 0.6, 0.7)))
    assert select_region(iid, _region(run, 0), RULE)["status"] == "selected"
    assert select_region(iid, _region(run, 0), RULE)["status"] == "already_selected"
    assert select_region(iid, _region(run, 1), RULE)["status"] == "other_selection_active"


def test_region_of_another_image_is_rejected():
    a, b = _image(), _image()
    region_b = _region(_run(b, publish=False))
    assert select_region(a, region_b, RULE)["status"] == "region_mismatch"


def test_revoke_keeps_a_bbox_changed_outside_the_selection():
    iid = _image()
    select_region(iid, _region(_run(iid, publish=False)), RULE)
    db.get_connector().execute("UPDATE images SET bird_bbox = '{\"detected\": false, \"error\": \"x\"}'::jsonb "
                               "WHERE id = ?", (iid,))
    assert revoke_selection(iid, "test")["status"] == "revoked_bbox_kept"
    assert _bbox(iid) == {"detected": False, "error": "x"} and active_selection(iid) is None


def test_selection_cascades_with_the_image():
    iid = _image()
    select_region(iid, _region(_run(iid, publish=False)), RULE)
    db.get_connector().execute("DELETE FROM images WHERE id = ?", (iid,))
    assert db.get_connector().query("SELECT id FROM image_localization_selections WHERE image_id = ?", (iid,)) == []


def test_promote_cli_dry_run_apply_rerun_and_revoke(tmp_path):
    """Manifest flow: only ready rows are promoted, re-apply is a no-op, revoke restores bird_bbox."""
    import json

    from scripts.maintenance import promote_localization_selections as cli

    ready, changed = _image(), _image({"x1": 1, "y1": 1, "x2": 2, "y2": 2, "conf": 0.5,
                                       "img_w": 10, "img_h": 10, "area_frac": 0.01})
    rows = []
    for iid in (ready, changed):
        v1 = _run(iid, publish=True, version="shadow-v1")
        rh = db.get_connector().query_one("SELECT rendition_hash FROM image_localization_runs WHERE id = ?",
                                          (v1,))["rendition_hash"]
        rows.append({"image_id": iid, "v1_run_id": v1, "rendition_hash": rh, "region": [0.5, 0.5, 0.7, 0.9],
                     "conf": 0.66, "source": "coco+refine:bird", "stratum": "promote_large"})
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"schema_version": 1, "selected_by": RULE, "detector_version": "v1_regate_rule/3",
                                "detector_config_hash": "a1c2e1f64b24cc79", "evidence": {"issue": 472},
                                "rows": rows}))
    manifest = cli.load_manifest(path)

    dry = cli.dry_run(manifest)
    assert dry["ready"] == 1 and dry["production_changed"] == 1
    assert cli.apply(manifest) == {"selected": 1, "skipped:production_changed": 1}
    assert _bbox(ready)["img_w"] == 1000 and _bbox(ready)["x1"] == 500
    sel = active_selection(ready)
    assert sel["evidence"] == {"issue": 472, "stratum": "promote_large", "source": "coco+refine:bird"}
    current = db.get_connector().query_one(
        "SELECT detector_version FROM image_localization_runs WHERE image_id = ? AND is_current", (ready,))
    assert current["detector_version"] == "shadow-v1"     # the shadow run stays current

    assert cli.apply(manifest)["skipped:already_selected"] == 1    # idempotent
    assert cli.revoke(manifest, "test") == {"revoked": 1, "not_ours": 1}
    assert _bbox(ready) == SENTINEL


@pytest.mark.parametrize("first", ["promotion", "legacy"])
def test_legacy_write_racing_promotion_cannot_overwrite_projection(monkeypatch, first):
    """Hold the first image lock until the other transaction attempts that same lock."""
    import threading
    from concurrent.futures import ThreadPoolExecutor, TimeoutError

    from modules.localization_selection import write_legacy_bird_bbox

    iid = _image()
    rid = _region(_run(iid, publish=False))
    connector = db.get_connector()
    locked, release, second_attempt = threading.Event(), threading.Event(), threading.Event()
    legacy = {"detected": False, "scan_failed": True}

    class Transaction:
        def __init__(self, tx):
            self.tx = tx

        def __getattr__(self, name):
            return getattr(self.tx, name)

        def query_one(self, sql, params):
            if "FOR UPDATE" not in sql:
                return self.tx.query_one(sql, params)
            if threading.current_thread().name.endswith("_1"):
                second_attempt.set()
                return self.tx.query_one(sql, params)
            result = self.tx.query_one(sql, params)
            locked.set()
            assert release.wait(5), "first transaction was not released"
            return result

    class Connector:
        def __getattr__(self, name):
            return getattr(connector, name)

        def run_transaction(self, callback):
            return connector.run_transaction(lambda tx: callback(Transaction(tx)))

    monkeypatch.setattr(db, "get_connector", lambda: Connector())
    actions = {"promotion": lambda: select_region(iid, rid, RULE),
               "legacy": lambda: write_legacy_bird_bbox(iid, legacy)}
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="race") as pool:
        a = pool.submit(actions[first])
        try:
            assert locked.wait(5)
            b = pool.submit(actions["legacy" if first == "promotion" else "promotion"])
            assert second_attempt.wait(5)
            with pytest.raises(TimeoutError):
                b.result(timeout=0.2)
        finally:
            release.set()
        results = [a.result(timeout=5), b.result(timeout=5)]
    assert any(isinstance(r, dict) and r["status"] == "selected" for r in results)
    assert _bbox(iid) == active_selection(iid)["projected_bird_bbox"]
    assert revoke_selection(iid, "race rollback")["status"] == "revoked"
    assert _bbox(iid) == (SENTINEL if first == "promotion" else legacy)


def test_revoked_selection_allows_legacy_species_again():
    from modules.bird_species import species_input_for_image
    from modules.localization_selection import write_legacy_bird_bbox

    iid = _image()
    select_region(iid, _region(_run(iid, publish=False)), RULE)
    assert species_input_for_image(iid)["mode"] == "region"
    assert write_legacy_bird_bbox(iid, SENTINEL) is False
    revoke_selection(iid, "test")
    assert species_input_for_image(iid)["mode"] == "legacy"
    assert write_legacy_bird_bbox(iid, SENTINEL) is True


def test_geometry_promotion_preserves_keywords_embeddings_and_phase_state(tmp_path):
    from scripts.maintenance import refresh_region_species as refresh

    iid = _image()
    rid = _region(_run(iid, publish=False, boxes=((0, 0, 0.0049, 1, 0.8),)))
    db.update_image_keywords_for_image(iid, "birds,species:wren", source="manual", confidence=0.9,
                                       relevance_weight=0.7)
    db.set_image_phase_status(iid, "bird_species", "done", executor_version="previous")
    baseline = tmp_path / "small.json"
    refresh.snapshot([iid], baseline, preserve_species=True)
    assert select_region(iid, rid, "rule/4")["status"] == "selected"
    assert refresh.verify(baseline)["metadata_preserved"] is True
    assert revoke_selection(iid, "rollback")["status"] == "revoked"
    assert refresh.verify(baseline)["metadata_preserved"] is True


def test_refresh_restores_removed_non_species_membership_and_metadata(tmp_path):
    from scripts.maintenance import refresh_region_species as refresh

    iid = _image()
    db.update_image_keywords_for_image(iid, "birds,birds:species-exhausted,travel,species:old",
                                       source="manual", confidence=0.9, relevance_weight=0.7)
    db.get_connector().execute(
        "UPDATE image_keywords SET confidence=NULL WHERE image_id=? AND keyword_id="
        "(SELECT keyword_id FROM keywords_dim WHERE keyword_norm='birds:species-exhausted')", (iid,))
    before = refresh._rows([iid])
    baseline = tmp_path / "before.json"
    refresh.snapshot([iid], baseline)
    db.update_image_keywords_for_image(iid, "birds,travel,species:new", source="auto")

    assert refresh.restore(baseline) == {"restored_rows": 3}
    after = refresh._rows([iid])
    assert sorted((r for r in before if not r["keyword_norm"].startswith("species:")),
                  key=lambda r: r["keyword_norm"]) == sorted(
        (r for r in after if not r["keyword_norm"].startswith("species:")), key=lambda r: r["keyword_norm"])
    assert [r["keyword_norm"] for r in after if r["keyword_norm"].startswith("species:")] == ["species:new"]
    assert refresh.restore(baseline) == {"restored_rows": 0}


def test_refresh_restores_metadata_and_continuation_skips_success(monkeypatch, tmp_path):
    import hashlib
    import json

    from modules import bird_species as bs
    from scripts.maintenance import refresh_region_species as refresh

    iid = _image()
    db.get_connector().execute("UPDATE images SET file_path = ? WHERE id = ?", (str(tmp_path / "bird.jpg"), iid))
    (tmp_path / "bird.jpg").write_bytes(b"fake classifier input")
    rid = _region(_run(iid, publish=False))
    select_region(iid, rid, refresh.SELECTED_BY)
    selection = active_selection(iid)
    db.update_image_keywords_for_image(iid, "birds,travel,species:old", source="manual", confidence=0.9,
                                       relevance_weight=0.7)
    region = db.get_connector().query_one("SELECT x1,y1,x2,y2 FROM image_regions WHERE id = ?", (rid,))
    cohort, full, baseline, completed = (tmp_path / name for name in ("cohort.json", "full.json", "baseline.json", "completed.json"))
    cohort.write_text(json.dumps({"selected_by": refresh.SELECTED_BY, "rows": [{"id": iid, **region}],
        "identities": [{"image_id": iid, "region_id": rid, "localization_run_id": selection["localization_run_id"]}]}))
    full.write_text(json.dumps({"meta": {"selected_by": refresh.SELECTED_BY},
                               "images": [{"image_id": iid, "new": "Carolina Wren"}]}))
    monkeypatch.setattr(refresh, "COHORT_SHA256", hashlib.sha256(cohort.read_bytes()).hexdigest())
    monkeypatch.setattr(refresh, "FULL_SHA256", hashlib.sha256(full.read_bytes()).hexdigest())
    monkeypatch.setattr(bs, "use_regions_enabled", lambda: True)
    monkeypatch.setattr(bs, "min_confidence", lambda: 0.5)
    calls = []

    class Classifier:
        last_bbox = None
        last_image_embedding = None

        def load_model(self):
            pass

        def classify(self, *args, **kwargs):
            calls.append(kwargs)
            return [("Carolina Wren", 0.9)]

    monkeypatch.setattr(bs, "new_bioclip_classifier", lambda: Classifier())
    refresh.snapshot([iid], baseline)
    result = refresh.run([iid], bs._DEFAULT_SPECIES_LIST_PATH, cohort, full, baseline, completed)
    assert result["completed_ids"] == [iid]
    assert refresh.verify(baseline, full)["metadata_preserved"] is True
    assert calls == [{"threshold": 0.5, "top_k": 1, "region": (0.1, 0.2, 0.3, 0.4), "use_detector": False}]
    assert _bbox(iid) == selection["projected_bird_bbox"]
    refresh.run([iid], bs._DEFAULT_SPECIES_LIST_PATH, cohort, full, baseline, completed)
    assert len(calls) == 1
    # A user pause of a maintenance job must stop inference and retain the pause.
    paused_baseline = tmp_path / "paused-baseline.json"
    refresh.snapshot([iid], paused_baseline)
    monkeypatch.setattr(db, "job_should_stop_processing", lambda job_id: True)
    monkeypatch.setattr(db, "get_job", lambda job_id: {"status": "paused"})
    statuses = []
    monkeypatch.setattr(db, "update_job_status", lambda *args: statuses.append(args[1]))
    with pytest.raises(RuntimeError, match="paused"):
        refresh.run([iid], bs._DEFAULT_SPECIES_LIST_PATH, cohort, full, paused_baseline, tmp_path / "paused-done.json")
    assert statuses == ["running"]
    assert len(calls) == 1
