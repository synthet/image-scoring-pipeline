"""Images without ``image_hash`` must not be reported as current (#829).

Clustering skips an image that has no hash, so a folder of them used to be logged as
"all images current", finish with 0 images processed and leave the job ``completed``.
No PostgreSQL required: the DB is stubbed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from modules.clustering import ClusteringEngine, ClusteringRunner
from modules.selection import SelectionConfig, SelectionService
from modules.selection_runner import SelectionRunner

HASHED = {"id": 1, "image_hash": "abc", "score_general": 0.7, "file_path": "/photos/a/1.nef"}
UNHASHED = {"id": 2, "image_hash": None, "score_general": 0.6, "file_path": "/photos/a/2.nef"}
EMPTY_HASH = {"id": 3, "image_hash": "", "score_general": 0.5, "file_path": "/photos/a/3.nef"}


# --- SelectionRunner scope ---------------------------------------------------------------

def _resolve(monkeypatch, tmp_path, images, *, should_run=True, force_rescan=False):
    from modules import selection_runner

    monkeypatch.setattr(selection_runner.db, "list_folder_paths_under_scope", lambda _p: [str(tmp_path)])
    monkeypatch.setattr(selection_runner.db, "get_images_by_folder", lambda _f: list(images))
    monkeypatch.setattr(selection_runner.utils, "convert_path_to_local", lambda p: p)
    monkeypatch.setattr(selection_runner, "culling_requires_scoring", lambda: True)
    monkeypatch.setattr(
        selection_runner, "explain_phase_run_decision", lambda *_a, **_k: {"should_run": should_run}
    )
    messages: list[str] = []
    runner = SelectionRunner.__new__(SelectionRunner)
    result = runner._resolve_culling_scope(
        str(tmp_path), force_rescan, None, lambda message, *_a: messages.append(message)
    )
    return (*result, messages)


def test_scope_with_only_unhashed_images_is_blocked(monkeypatch, tmp_path):
    status, _images, eligible, _messages = _resolve(monkeypatch, tmp_path, [UNHASHED, EMPTY_HASH])

    assert status == "missing_image_hash"
    assert [img["id"] for img in eligible] == [2, 3]


def test_partly_hashed_scope_drops_and_reports_blocked_images(monkeypatch, tmp_path):
    status, images, eligible, messages = _resolve(monkeypatch, tmp_path, [HASHED, UNHASHED, EMPTY_HASH])

    assert status == "ok"
    assert [img["id"] for img in images] == [1]
    assert [img["id"] for img in eligible] == [1]
    assert any("2 image(s)" in message and "image_hash" in message for message in messages)


def test_current_images_are_not_blocked_even_without_a_hash(monkeypatch, tmp_path):
    status, images, eligible, messages = _resolve(monkeypatch, tmp_path, [UNHASHED], should_run=False)

    assert status == "ok"
    assert [img["id"] for img in images] == [2]
    assert eligible == []
    assert not any("image_hash" in message for message in messages)


def test_force_rescan_keeps_unhashed_images(monkeypatch, tmp_path):
    status, _images, eligible, _messages = _resolve(monkeypatch, tmp_path, [UNHASHED], force_rescan=True)

    assert status == "ok"
    assert [img["id"] for img in eligible] == [2]


def _run_batch(scope):
    runner = SelectionRunner()
    runner._service = MagicMock()
    with patch.object(runner, "_resolve_culling_scope", return_value=scope), patch.object(
        runner, "_complete_phase_and_advance"
    ) as advance, patch("modules.selection_runner.db") as mock_db, patch(
        "modules.selection_runner.event_manager"
    ) as events:
        runner._run_internal("/photos/a", False, job_id=7)
    return runner, mock_db, advance, events


def test_blocked_scope_fails_the_job_without_running_selection():
    runner, mock_db, advance, events = _run_batch(("missing_image_hash", [], [UNHASHED, EMPTY_HASH]))

    runner._service.run.assert_not_called()
    advance.assert_not_called()
    job_id, status, message = mock_db.update_job_status.call_args.args
    assert (job_id, status) == (7, "failed")
    assert "2 image(s)" in message and "image_hash" in message
    assert events.broadcast_threadsafe.call_args.args == ("job_completed", {"job_id": 7, "status": "failed"})


# --- ClusteringEngine --------------------------------------------------------------------

def _cluster(monkeypatch, rows, *, should_run=True):
    from modules import clustering

    monkeypatch.setattr(clustering.db, "get_clustered_folders", lambda: set())
    monkeypatch.setattr(clustering.db, "get_images_by_folder", lambda _f: list(rows))
    monkeypatch.setattr(clustering.db, "get_stack_count", lambda: 0)
    monkeypatch.setattr(clustering.db, "get_image_phase_statuses", lambda _i: {})
    monkeypatch.setattr(clustering, "filter_image_rows_for_nef_policy", lambda found: found)
    monkeypatch.setattr(
        clustering, "explain_phase_run_decision", lambda *_a, **_k: {"should_run": should_run, "reason": "x"}
    )
    engine = ClusteringEngine.__new__(ClusteringEngine)
    engine._load_capture_times = lambda _rows: None
    messages = [
        update[0]
        for update in engine.cluster_images(
            distance_threshold=0.2, time_gap_seconds=60, force_rescan=False, target_folder="/photos/a"
        )
    ]
    return engine, messages


def test_folder_of_unhashed_images_is_not_reported_as_current(monkeypatch):
    engine, messages = _cluster(monkeypatch, [UNHASHED, EMPTY_HASH])

    assert not any("all images current" in message for message in messages)
    assert any("2 image(s)" in message and "image_hash" in message for message in messages)
    assert engine.blocked_missing_hash == 2
    assert engine.all_blocked is True


def test_truly_current_folder_keeps_the_plain_skip(monkeypatch):
    engine, messages = _cluster(monkeypatch, [HASHED], should_run=False)

    assert any("all images current" in message for message in messages)
    assert engine.blocked_missing_hash == 0
    assert engine.all_blocked is False


# --- ClusteringRunner --------------------------------------------------------------------

@pytest.mark.parametrize(("all_blocked", "status"), [(True, "failed"), (False, "completed")])
def test_clustering_runner_fails_when_every_image_was_blocked(all_blocked, status):
    runner = ClusteringRunner()
    runner.engine = MagicMock()
    runner.engine.cluster_images.return_value = iter([("Done", 0, 0)])
    runner.engine.all_blocked = all_blocked
    runner.engine.blocked_missing_hash = 2 if all_blocked else 0
    with patch("modules.clustering.db") as mock_db, patch("modules.clustering.event_manager"):
        runner._run_internal("/photos/a", 0.2, 60, False, job_id=7)

    assert mock_db.update_job_status.call_args.args[:2] == (7, status)


# --- SelectionService --------------------------------------------------------------------

def _selection_images(monkeypatch, tmp_path, rows, *, force_rescan=False):
    """Return the ids SelectionService went on to rank after clustering."""
    from modules import selection

    monkeypatch.setattr(selection.utils, "convert_path_to_local", lambda p: p)
    monkeypatch.setattr(selection.db, "list_folder_paths_under_scope", lambda _p: [str(tmp_path)])
    monkeypatch.setattr(selection.db, "get_images_by_folder", lambda _f: [dict(row) for row in rows])
    monkeypatch.setattr(selection, "filter_image_rows_for_nef_policy", lambda found: found)
    ranked: list[int] = []

    def stop_after_ranking(image_ids):
        ranked.extend(image_ids)
        raise RuntimeError("stop after ranking input")

    monkeypatch.setattr(selection.db, "get_exif_fields_for_quality_tiebreak", stop_after_ranking)
    engine = MagicMock()
    engine.cluster_images.return_value = iter([])
    service = SelectionService.__new__(SelectionService)
    service._cluster_engine = engine
    service._stop_requested = MagicMock()
    service._stop_requested.is_set.return_value = False
    service.run(str(tmp_path), SelectionConfig(force_rescan=force_rescan))
    return ranked


def test_selection_leaves_unhashed_images_out_of_picks(monkeypatch, tmp_path):
    assert _selection_images(monkeypatch, tmp_path, [HASHED, UNHASHED, EMPTY_HASH]) == [1]


def test_force_rescan_selection_keeps_unhashed_images(monkeypatch, tmp_path):
    assert _selection_images(monkeypatch, tmp_path, [HASHED, UNHASHED], force_rescan=True) == [1, 2]
