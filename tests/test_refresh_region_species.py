"""The rollout operator fails closed on list/cohort drift and preserves metadata."""

import hashlib
import importlib
import json
from pathlib import Path

import pytest

from modules import bird_species as bs


@pytest.fixture
def operator(monkeypatch, tmp_path):
    cli = importlib.import_module("scripts.maintenance.refresh_region_species")
    species = Path(bs._DEFAULT_SPECIES_LIST_PATH)
    frozen = {"selected_by": cli.SELECTED_BY,
              "rows": [{"id": 1, "x1": 0, "y1": 0, "x2": 0.1, "y2": 1}],
              "identities": [{"image_id": 1, "localization_run_id": 7, "region_id": 9}]}
    full = {"meta": {"selected_by": cli.SELECTED_BY, "species_sha256": cli.SPECIES_SHA256,
                     "threshold": 0.5, "species_count": 369},
            "images": [{"image_id": 1, "new": "Carolina Wren", "outcome": "same"}]}
    cohort, report = tmp_path / "cohort.json", tmp_path / "full.json"
    cohort.write_text(json.dumps(frozen))
    report.write_text(json.dumps(full))
    monkeypatch.setattr(cli, "COHORT_SHA256", hashlib.sha256(cohort.read_bytes()).hexdigest())
    monkeypatch.setattr(cli, "FULL_SHA256", hashlib.sha256(report.read_bytes()).hexdigest())
    live = {"run_id": 7, "region_id": 9, "selected_by": cli.SELECTED_BY,
            "x1": 0, "y1": 0, "x2": 0.1, "y2": 1}
    jobs = []

    class Connector:
        def query_one(self, sql, params):
            return live

    monkeypatch.setattr(bs.db, "get_connector", lambda: Connector())
    monkeypatch.setattr(bs.db, "create_job", lambda *a, **kw: jobs.append(a))
    monkeypatch.setattr(bs, "use_regions_enabled", lambda: True)
    monkeypatch.setattr(bs, "min_confidence", lambda: 0.5)
    return cli, species, cohort, report, live, jobs


def test_accepts_frozen_large_medium_cohort(operator):
    cli, species, cohort, report, _, jobs = operator
    names, predictions = cli.preflight([1], species, cohort, report)
    assert len(names) == 369 and predictions[1]["new"] == "Carolina Wren"
    assert jobs == []


@pytest.mark.parametrize("ids", [[], [1, 1], [2], [1, 2], [True], ["1"]])
def test_rejects_unvalidated_or_implicit_ids(operator, ids):
    cli, species, cohort, report, _, jobs = operator
    with pytest.raises(ValueError):
        cli.preflight(ids, species, cohort, report)
    assert jobs == []


@pytest.mark.parametrize("change", [{"x2": 0.0049}, {"x1": 0.0001}, {"region_id": 10},
                                    {"run_id": 8}, {"selected_by": "rule/4"}])
def test_rejects_small_geometry_or_selection_drift(operator, change):
    cli, species, cohort, report, live, jobs = operator
    live.update(change)
    with pytest.raises(ValueError):
        cli.preflight([1], species, cohort, report)
    assert jobs == []


def test_list_hash_mismatch_rejected_even_with_369_names(operator, tmp_path):
    cli, species, cohort, report, _, jobs = operator
    changed = tmp_path / "369.txt"
    changed.write_text(species.read_text().replace("American Robin", "Fake Robin"))
    with pytest.raises(ValueError, match="species"):
        cli.preflight([1], changed, cohort, report)
    assert jobs == []


@pytest.mark.parametrize("target", [2, 3])
def test_rejects_changed_frozen_artifact(operator, target):
    cli, species, cohort, report, _, jobs = operator
    path = operator[target]
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="hash"):
        cli.preflight([1], species, cohort, report)
    assert jobs == []


def test_metadata_restore_preserves_null_distinctions(operator, monkeypatch, tmp_path):
    cli, *_ = operator
    before = {"ids": [1], "rows": [{"image_id": 1, "keyword_norm": "birds", "source": "manual",
                                   "confidence": None, "relevance_weight": 0.7}]}
    snap = tmp_path / "baseline.json"
    snap.write_text(json.dumps(before))
    current = [{**before["rows"][0], "source": "auto", "confidence": 0.0, "relevance_weight": 1.0}]
    monkeypatch.setattr(cli, "_rows", lambda ids: current)
    writes = []
    connector = type("C", (), {"execute": lambda self, sql, params: writes.append(params)})()
    monkeypatch.setattr(bs.db, "get_connector", lambda: connector)
    assert cli.restore(snap) == {"restored_rows": 1}
    assert writes[0][:3] == ("manual", None, 0.7)


@pytest.mark.parametrize("keyword", ["birds:species-exhausted", "hand-added note"])
def test_restore_reinserts_missing_non_species_keyword_without_restoring_old_species(
    operator, monkeypatch, tmp_path, keyword,
):
    cli, *_ = operator
    missing = {"image_id": 1, "keyword_norm": keyword, "source": "manual",
               "confidence": None, "relevance_weight": 0.7}
    old_species = {**missing, "keyword_norm": "species:old"}
    new_species = {**missing, "keyword_norm": "species:new", "source": "bioclip_region",
                   "confidence": 0.9}
    snap = tmp_path / "baseline.json"
    snap.write_text(json.dumps({"ids": [1], "rows": [missing, old_species]}))
    current = [new_species]
    monkeypatch.setattr(cli, "_rows", lambda ids: current)
    writes = []

    class Connector:
        def execute(self, sql, params):
            writes.append((sql, params))

    monkeypatch.setattr(bs.db, "get_connector", lambda: Connector())
    assert cli.restore(snap) == {"restored_rows": 1}
    assert len(writes) == 1 and "INSERT INTO image_keywords" in writes[0][0]
    assert writes[0][1] == (1, "manual", None, 0.7, keyword)
    assert current == [new_species]


def test_restore_reinsert_keeps_supplied_created_at(operator, monkeypatch, tmp_path):
    cli, *_ = operator
    missing = {"image_id": 1, "keyword_norm": "birds:species-exhausted", "source": "auto",
               "confidence": 1.0, "relevance_weight": 1.0}
    snap = tmp_path / "baseline.json"
    snap.write_text(json.dumps({"ids": [1], "rows": [missing]}))
    monkeypatch.setattr(cli, "_rows", lambda ids: [])
    writes = []

    class Connector:
        def execute(self, sql, params):
            writes.append((sql, params))

    monkeypatch.setattr(bs.db, "get_connector", lambda: Connector())
    stamp = "2026-10-14 23:40:32.900621"
    assert cli._restore(json.loads(snap.read_text()), created_at={(1, missing["keyword_norm"]): stamp}) == {
        "restored_rows": 1}
    assert "created_at" in writes[0][0]
    assert writes[0][1] == (1, "auto", 1.0, 1.0, stamp, missing["keyword_norm"])


@pytest.mark.parametrize("change", ["keyword", "confidence", "source", "relevance_weight", "caption", "score",
                                    "species", "embedding", "phase"])
def test_geometry_only_verification_rejects_preservation_drift(operator, monkeypatch, tmp_path, change):
    cli, *_ = operator
    rows = [{"image_id": 1, "keyword_norm": "birds", "source": "manual", "confidence": None,
             "relevance_weight": 0.7},
            {"image_id": 1, "keyword_norm": "species:wren", "source": "bioclip", "confidence": 0.9,
             "relevance_weight": 1.0}]
    images = [{"id": 1, "data": {"caption": "bird", "score": 0.8, "bird_bbox": {"detected": False}}}]
    state = {"embedding": [0.1, 0.2], "phase": "done"}
    snap = tmp_path / "small-baseline.json"
    snap.write_text(json.dumps({"ids": [1], "rows": rows, "images": images, "preserve_species": True,
                               "species_state": state}))
    if change == "keyword":
        rows.pop(0)
    elif change in ("source", "confidence", "relevance_weight"):
        rows[0][change] = "auto" if change == "source" else 1.0
    elif change in ("caption", "score"):
        images[0]["data"][change] = "changed"
    elif change == "species":
        rows[1]["keyword_norm"] = "species:other"
    else:
        state[change] = "changed"
    monkeypatch.setattr(cli, "_rows", lambda ids: rows)
    monkeypatch.setattr(cli, "_images", lambda ids: images)
    monkeypatch.setattr(cli, "_species_state", lambda ids: state)
    with pytest.raises(ValueError):
        cli.verify(snap)


def test_rejects_mixed_cohort_before_creating_job(operator, tmp_path):
    cli, species, cohort, report, _, jobs = operator
    with pytest.raises(ValueError):
        cli.run([1, 2], species, cohort, report, tmp_path / "missing.json", tmp_path / "done.json")
    assert jobs == []


def test_even_frozen_small_rows_cannot_be_refreshed(operator, monkeypatch):
    cli, species, cohort, report, live, jobs = operator
    frozen = json.loads(cohort.read_text())
    frozen["rows"][0]["x2"] = live["x2"] = 0.004999
    cohort.write_text(json.dumps(frozen))
    monkeypatch.setattr(cli, "COHORT_SHA256", hashlib.sha256(cohort.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match="small"):
        cli.preflight([1], species, cohort, report)
    assert jobs == []


def test_offset_box_at_exact_area_boundary_is_refresh_eligible(operator, monkeypatch):
    cli, species, cohort, report, live, _ = operator
    frozen = json.loads(cohort.read_text())
    geometry = {"x1": 0.2, "y1": 0.2, "x2": 0.3, "y2": 0.25}
    frozen["rows"][0].update(geometry)
    live.update(geometry)
    cohort.write_text(json.dumps(frozen))
    monkeypatch.setattr(cli, "COHORT_SHA256", hashlib.sha256(cohort.read_bytes()).hexdigest())
    assert len(cli.preflight([1], species, cohort, report)[0]) == 369


def test_region_mode_disabled_prevents_job_creation(operator, monkeypatch, tmp_path):
    cli, species, cohort, report, _, jobs = operator
    monkeypatch.setattr(bs, "use_regions_enabled", lambda: False)
    with pytest.raises(ValueError, match="region mode"):
        cli.run([1], species, cohort, report, tmp_path / "baseline.json", tmp_path / "done.json")
    assert jobs == []
