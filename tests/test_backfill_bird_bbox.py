"""
Tests for scripts/backfill_bird_bbox.py — queues localization instead of writing bird_bbox (#638).

No GPU/ML and no database: job creation and the connector are stubbed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backfill_bird_bbox.py"


def _load_script():
    """Load the backfill script as a module (scripts/ is not a package)."""
    name = "backfill_bird_bbox_under_test"
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def backfill():
    return _load_script()


def test_all_null_sql_omits_keyword_gate(backfill):
    assert "keyword_norm" in backfill._SQL_MISSING_BBOX
    assert "keyword_norm" not in backfill._SQL_MISSING_BBOX_ALL
    assert "bird_bbox IS NULL" in backfill._SQL_MISSING_BBOX_ALL


def test_script_has_no_detector_or_bbox_write_path():
    source = _SCRIPT.read_text(encoding="utf-8")
    for legacy in ("BirdDetector", "update_image_bird_bbox", "write_legacy_bird_bbox", "detect_best_box"):
        assert legacy not in source


def test_enqueue_queues_explicit_id_scoped_localization_jobs(backfill, monkeypatch):
    from modules import db

    calls = []

    def enqueue(input_path, **kwargs):
        calls.append((input_path, kwargs))
        return 100 + len(calls), len(calls)

    monkeypatch.setattr(db, "enqueue_job_with_phases", enqueue)
    assert backfill.enqueue_localization([1, 2, 3, 4, 5], chunk_size=2) == [101, 102, 103]

    assert [kwargs["queue_payload"]["resolved_image_ids"] for _, kwargs in calls] == [[1, 2], [3, 4], [5]]
    input_path, kwargs = calls[0]
    assert input_path == "SELECTOR_LOCALIZATION_BACKFILL"
    assert kwargs["phase_code"] == "localization"
    assert kwargs["phase_codes"] == ["localization"]
    assert kwargs["queue_payload"]["resolved_image_ids_by_stage"] == {"localization": [1, 2]}
    # Not the automatic lane: no bounded-repair limit and no lane outage accounting.
    assert "localization_lane" not in kwargs["queue_payload"]


def test_enqueue_failure_raises(backfill, monkeypatch):
    from modules import db

    monkeypatch.setattr(db, "enqueue_job_with_phases", lambda *a, **k: (None, 0))
    with pytest.raises(RuntimeError, match="failed to enqueue"):
        backfill.enqueue_localization([7], chunk_size=10)


def test_drop_already_localized_keeps_images_without_a_current_run(backfill, monkeypatch):
    from modules import db

    seen = []

    class Connector:
        def query(self, sql, params):
            seen.append((sql, params))
            return [{"image_id": 2}]

    monkeypatch.setattr(db, "get_connector", lambda: Connector())
    assert backfill.drop_already_localized([1, 2, 3]) == [1, 3]
    sql, params = seen[0]
    assert "is_current" in sql and "detector_key = 'bird'" in sql
    assert params == (1, 2, 3)


def test_dry_run_enqueues_nothing(backfill, monkeypatch, capsys):
    monkeypatch.setattr(backfill, "fetch_candidates", lambda **kw: [{"id": 5, "file_path": "a.nef"}])
    monkeypatch.setattr(backfill, "drop_already_localized", lambda ids: ids)
    monkeypatch.setattr(backfill, "enqueue_localization",
                        lambda *a, **k: pytest.fail("dry run must not enqueue"))
    assert backfill.main(["--dry-run", "--all-null"]) == 0
    assert "5\ta.nef" in capsys.readouterr().out


def test_main_queues_remaining_candidates(backfill, monkeypatch):
    monkeypatch.setattr(backfill, "fetch_candidates",
                        lambda **kw: [{"id": 5, "file_path": "a"}, {"id": 6, "file_path": "b"}])
    monkeypatch.setattr(backfill, "drop_already_localized", lambda ids: [6])
    queued = []
    monkeypatch.setattr(backfill, "enqueue_localization",
                        lambda ids, chunk_size: queued.append((ids, chunk_size)) or [42])
    assert backfill.main(["--chunk-size", "50"]) == 0
    assert queued == [([6], 50)]


def test_nothing_to_queue_returns_one(backfill, monkeypatch):
    monkeypatch.setattr(backfill, "fetch_candidates", lambda **kw: [{"id": 5, "file_path": "a"}])
    monkeypatch.setattr(backfill, "drop_already_localized", lambda ids: [])
    assert backfill.main([]) == 1
