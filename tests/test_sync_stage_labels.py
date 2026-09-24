"""Unit tests for scripts/ci/sync_stage_labels.py decision logic (no network / no gh)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def sync():
    path = ROOT / "scripts" / "ci" / "sync_stage_labels.py"
    spec = importlib.util.spec_from_file_location("sync_stage_labels", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sync_stage_labels"] = mod
    spec.loader.exec_module(mod)
    return mod


BOARD_AT = "2026-09-24T10:00:00Z"
BEFORE = "2026-09-24T09:00:00Z"
AFTER = "2026-09-24T11:00:00Z"


def test_label_names_round_trip(sync):
    assert sync.label_for("in_progress") == "stage:in-progress"
    assert sync.stage_for_label("stage:in-progress") == "in_progress"
    assert sync.stage_for_label("stage:bogus") is None
    assert sync.stage_for_label("priority:p1") is None
    assert {sync.label_for(k) for k in sync.STAGE_OPTIONS} == set(sync.STAGE_LABELS)


def test_agree_is_noop(sync):
    d = sync.decide("ready", BOARD_AT, {"ready": BEFORE})
    assert d == sync.Decision()
    assert d.is_noop


def test_missing_label_is_added_from_board(sync):
    d = sync.decide("ready", BOARD_AT, {})
    assert d == sync.Decision(add=("ready",))


def test_no_board_stage_and_no_label_is_noop(sync):
    assert sync.decide(None, None, {}).is_noop


def test_newer_label_moves_board(sync):
    d = sync.decide("ready", BOARD_AT, {"claimed": AFTER})
    assert d == sync.Decision(set_board="claimed")


def test_newer_label_moves_board_and_drops_stale_label(sync):
    # Agent added stage:claimed but forgot to remove stage:ready.
    d = sync.decide("ready", BOARD_AT, {"ready": BEFORE, "claimed": AFTER})
    assert d == sync.Decision(set_board="claimed", remove=("ready",))


def test_board_newer_than_label_wins(sync):
    # Maintainer moved the card on the board after the label was set.
    d = sync.decide("review", BOARD_AT, {"in_progress": BEFORE})
    assert d == sync.Decision(add=("review",), remove=("in_progress",))


def test_label_without_event_time_loses_to_board(sync):
    d = sync.decide("ready", BOARD_AT, {"blocked": None})
    assert d == sync.Decision(add=("ready",), remove=("blocked",))


def test_label_sets_board_when_board_has_no_stage(sync):
    d = sync.decide(None, None, {"ready": BEFORE, "backlog": AFTER})
    assert d == sync.Decision(set_board="backlog", remove=("ready",))


def test_duplicate_matching_label_extra_removed(sync):
    d = sync.decide("review", BOARD_AT, {"review": AFTER, "claimed": BEFORE})
    assert d == sync.Decision(remove=("claimed",))


def test_plan_skips_closed_issues_and_non_issues(sync):
    items = [
        {"id": "a", "stage": {"optionId": "ddaf7773", "updatedAt": BOARD_AT},
         "content": {"__typename": "Issue", "number": 1, "state": "CLOSED",
                     "repository": {"nameWithOwner": "synthet/image-scoring-backend"},
                     "labels": {"nodes": []}}},
        {"id": "b", "stage": {"optionId": "ddaf7773", "updatedAt": BOARD_AT},
         "content": {"__typename": "PullRequest", "number": 2}},
        {"id": "c", "stage": None, "content": None},
        {"id": "d", "stage": {"optionId": "ddaf7773", "updatedAt": BOARD_AT},
         "content": {"__typename": "Issue", "number": 3, "state": "OPEN",
                     "repository": {"nameWithOwner": "synthet/image-scoring-backend"},
                     "labels": {"nodes": [{"name": "type:bug"}]}}},
    ]
    planned = list(sync.plan(items, label_events=lambda _repo, _n: {}))
    assert [(p.repo, p.number, p.decision) for p in planned] == [
        ("synthet/image-scoring-backend", 3, sync.Decision(add=("ready",))),
    ]


def test_plan_only_fetches_events_on_mismatch(sync):
    calls = []

    def events(repo, number):
        calls.append((repo, number))
        return {"claimed": AFTER}

    items = [
        {"id": "x", "stage": {"optionId": "ddaf7773", "updatedAt": BOARD_AT},
         "content": {"__typename": "Issue", "number": 5, "state": "OPEN",
                     "repository": {"nameWithOwner": "synthet/image-scoring-gallery"},
                     "labels": {"nodes": [{"name": "stage:ready"}]}}},
        {"id": "y", "stage": {"optionId": "ddaf7773", "updatedAt": BOARD_AT},
         "content": {"__typename": "Issue", "number": 6, "state": "OPEN",
                     "repository": {"nameWithOwner": "synthet/image-scoring-gallery"},
                     "labels": {"nodes": [{"name": "stage:claimed"}]}}},
    ]
    planned = list(sync.plan(items, label_events=events))
    assert calls == [("synthet/image-scoring-gallery", 6)]
    assert [(p.number, p.item_id, p.decision) for p in planned] == [
        (6, "y", sync.Decision(set_board="claimed")),
    ]
