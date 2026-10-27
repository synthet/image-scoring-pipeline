"""Culling before scoring with pending picks (#407, spec 02 AC-10 to AC-12).

Everything is behind ``pipeline.culling_requires_scoring`` (default true), so each test sets
the flag through ``config.get_config_value`` and stubs the DB.  No PostgreSQL required.
"""

from __future__ import annotations

import pytest

from modules import phases
from modules.phases import CULLING_REQUIRES_SCORING_KEY, missing_prerequisites, phase_prerequisites
from modules.selection import enqueue_pending_pick_runs, split_pending_stacks


@pytest.fixture
def flag(monkeypatch):
    def set_flag(value: bool):
        from modules import config

        real = config.get_config_value

        def fake(key, default=None):
            return value if key == CULLING_REQUIRES_SCORING_KEY else real(key, default)

        monkeypatch.setattr(config, "get_config_value", fake)

    return set_flag


# --- AC-10: prerequisite and runner scope ------------------------------------------------

def test_default_keeps_scoring_as_culling_prerequisite(flag):
    flag(True)
    assert phase_prerequisites("culling") == ("scoring",)
    assert missing_prerequisites(["culling"], {"indexing", "metadata"}) == {"culling": ["scoring"]}


def test_flag_off_lets_culling_follow_metadata(flag):
    flag(False)
    assert phase_prerequisites("culling") == ("metadata",)
    assert missing_prerequisites(["culling"], {"indexing", "metadata"}) == {}
    assert phases.pipeline_prefix_through("culling") == ["indexing", "metadata", "culling"]
    assert phase_prerequisites("scoring") == ("metadata",)  # other edges unchanged


def _resolve(monkeypatch, tmp_path, images):
    from modules import selection_runner
    from modules.selection_runner import SelectionRunner

    monkeypatch.setattr(selection_runner.db, "list_folder_paths_under_scope", lambda _p: [str(tmp_path)])
    monkeypatch.setattr(selection_runner.db, "get_images_by_folder", lambda _f: list(images))
    monkeypatch.setattr(selection_runner.utils, "convert_path_to_local", lambda p: p)
    monkeypatch.setattr(selection_runner, "explain_phase_run_decision", lambda *_a, **_k: {"should_run": True})
    runner = SelectionRunner.__new__(SelectionRunner)
    return runner._resolve_culling_scope(str(tmp_path), False, None, lambda *_a: None)


IMAGES = [{"id": 1, "score_general": 0.7}, {"id": 2, "score_general": None}]


def test_runner_drops_unscored_by_default(monkeypatch, tmp_path, flag):
    flag(True)
    status, images, eligible = _resolve(monkeypatch, tmp_path, IMAGES)
    assert status == "ok"
    assert [i["id"] for i in images] == [1]
    assert [i["id"] for i in eligible] == [1]


def test_runner_keeps_unscored_when_flag_off(monkeypatch, tmp_path, flag):
    flag(False)
    status, images, eligible = _resolve(monkeypatch, tmp_path, IMAGES)
    assert status == "ok"
    assert [i["id"] for i in images] == [1, 2]
    assert [i["id"] for i in eligible] == [1, 2]


# --- AC-11: pending stacks ---------------------------------------------------------------

def test_stack_with_an_unscored_member_waits_whole():
    by_stack = {
        10: [{"id": 1, "score_general": 0.9}, {"id": 2, "score_general": None}],
        11: [{"id": 3, "score_general": 0.4}, {"id": 4, "score_general": 0.5}],
        None: [{"id": 5, "score_general": None}, {"id": 6, "score_general": 0.2}],
    }
    pending = split_pending_stacks(by_stack)
    assert sorted(img["id"] for img in pending) == [1, 2, 5]
    assert set(by_stack) == {11, None}
    assert [img["id"] for img in by_stack[None]] == [6]


def test_fully_scored_folder_has_nothing_pending():
    by_stack = {10: [{"id": 1, "score_general": 0.0}], None: [{"id": 2, "score_general": 0.3}]}
    assert split_pending_stacks(by_stack) == []
    assert set(by_stack) == {10, None}


# --- AC-12: scoring completion re-runs pending picks -------------------------------------

class _Conn:
    def __init__(self, folder_rows):
        self.folder_rows = folder_rows
        self.queries: list[str] = []

    def query(self, sql, params=()):
        self.queries.append(sql)
        if "SELECT DISTINCT folder_id" in sql:
            return [{"folder_id": 7}]
        return self.folder_rows


@pytest.fixture
def stub_db(monkeypatch):
    from modules import selection, workflow_healing

    state = {"conn": _Conn([{"path": "/photos/a"}]), "phases": [], "active": [], "queued": []}
    monkeypatch.setattr(selection.db, "get_connector", lambda: state["conn"])
    monkeypatch.setattr(selection.db, "get_job_phases", lambda _job: state["phases"])
    monkeypatch.setattr(workflow_healing, "_get_active_jobs_snapshot", lambda: state["active"])

    def enqueue(folder, phase_code):
        state["queued"].append((folder, phase_code))
        return 900 + len(state["queued"]), 1

    monkeypatch.setattr(workflow_healing, "_enqueue_heal_run", enqueue)
    return state


def test_inert_while_culling_requires_scoring(stub_db, flag):
    flag(True)
    assert enqueue_pending_pick_runs(5, image_ids=[1]) == []
    assert stub_db["conn"].queries == []


def test_queues_culling_for_pending_folder(stub_db, flag):
    flag(False)
    assert enqueue_pending_pick_runs(5, image_ids=[1, 2]) == [901]
    assert stub_db["queued"] == [("/photos/a", "culling")]
    pending_sql = stub_db["conn"].queries[-1]
    assert "cull_decision IS NULL" in pending_sql and "cull_policy_version IS NOT NULL" in pending_sql


def test_skips_when_the_job_still_plans_culling(stub_db, flag):
    flag(False)
    stub_db["phases"] = [{"phase_code": "scoring", "state": "running"}, {"phase_code": "culling", "state": "pending"}]
    assert enqueue_pending_pick_runs(5, image_ids=[1]) == []
    assert stub_db["queued"] == []


def test_skips_a_folder_with_an_active_job(stub_db, flag):
    flag(False)
    stub_db["active"] = [{"id": 3, "input_path": "/photos/a", "status": "queued"}]
    assert enqueue_pending_pick_runs(5, image_ids=[1]) == []
    assert stub_db["queued"] == []
