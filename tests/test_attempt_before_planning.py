"""Attempt-before planning (#407, spec 02 AC-3 to AC-5, AC-8, AC-13).

``insert_attempt_before`` is pure apart from two seams -- ``is_phase_enabled`` and the
``pending`` check -- so every case here stubs both and needs no database.  Whether a given
localization status counts as an attempt (AC-6, AC-7) is decided by the run planner and is
covered by the Postgres suites, not here.
"""

from __future__ import annotations

import inspect

import pytest

from modules.phases import (
    PHASE_ATTEMPT_BEFORE,
    insert_attempt_before,
    missing_prerequisites,
)

SCOPE = ["/photos/2026"]


@pytest.fixture
def localization_enabled(monkeypatch):
    monkeypatch.setattr("modules.phases.is_phase_enabled", lambda _phase: True)


def _pending(answer: bool, calls: list | None = None):
    def check(producer, paths):
        if calls is not None:
            calls.append((producer, list(paths)))
        return answer

    return check


def test_table_has_only_localization_before_scoring():
    assert PHASE_ATTEMPT_BEFORE == {"localization": ("scoring",)}


def test_inserts_producer_immediately_ahead_of_consumer(localization_enabled):
    calls: list = []
    plan = insert_attempt_before(
        ["indexing", "metadata", "scoring", "culling"], SCOPE, pending=_pending(True, calls)
    )
    assert plan == ["indexing", "metadata", "localization", "scoring", "culling"]
    assert calls == [("localization", SCOPE)]


def test_inserted_producer_can_lead_the_plan(localization_enabled):
    assert insert_attempt_before(["scoring"], SCOPE, pending=_pending(True)) == [
        "localization",
        "scoring",
    ]


def test_no_insertion_when_every_image_has_an_attempt(localization_enabled):
    assert insert_attempt_before(["metadata", "scoring"], SCOPE, pending=_pending(False)) == [
        "metadata",
        "scoring",
    ]


def test_disabled_producer_leaves_plan_unchanged(monkeypatch):
    monkeypatch.setattr(
        "modules.phases.is_phase_enabled", lambda phase: getattr(phase, "value", phase) != "localization"
    )
    calls: list = []
    assert insert_attempt_before(["metadata", "scoring"], SCOPE, pending=_pending(True, calls)) == [
        "metadata",
        "scoring",
    ]
    assert calls == []


def test_without_scope_paths_plan_is_unchanged(localization_enabled):
    calls: list = []
    assert insert_attempt_before(["scoring"], [], pending=_pending(True, calls)) == ["scoring"]
    assert calls == []


def test_no_consumer_or_already_planned_is_left_alone(localization_enabled):
    calls: list = []
    check = _pending(True, calls)
    assert insert_attempt_before(["metadata", "keywords"], SCOPE, pending=check) == ["metadata", "keywords"]
    assert insert_attempt_before(["localization", "scoring"], SCOPE, pending=check) == [
        "localization",
        "scoring",
    ]
    assert calls == []


def test_attempt_edge_is_never_a_missing_prerequisite():
    assert missing_prerequisites(["scoring"], {"indexing", "metadata"}) == {}


@pytest.mark.parametrize(
    "module_name",
    [
        "modules.api.routers.electron_runs_lifecycle",
        "modules.api.routers.pipeline_submit",
        "modules.workflow_healing",
    ],
)
def test_every_gate_inserts_before_checking_prerequisites(module_name):
    """AC-13: each submission path plans the same way, so each gate sees the inserted stage.

    Auto-drive is deliberately absent: localization reaches auto-drive folders through the
    idle-path lane (#527), which keeps scoring from waiting on it (AC-9 deferred).
    """
    import importlib

    source = inspect.getsource(importlib.import_module(module_name))
    # Last mention is the call (imports come first); /runs/submit passes it to to_thread.
    call = source.rindex("insert_attempt_before")
    assert "assert_prereqs_for_scope" in source[call:], module_name
