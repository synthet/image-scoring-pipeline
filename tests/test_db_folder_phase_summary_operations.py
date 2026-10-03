"""Folder phase summary cache and status contracts after extraction."""

import json

from modules import db_legacy
from modules.db_operations.folder_phase_summary import _rollup_phase_rows


class _Connector:
    def __init__(self, *, cache=None, rows=None, fail_cache_write=False):
        self.cache = cache
        self.rows = rows or []
        self.fail_cache_write = fail_cache_write
        self.query_calls = 0
        self.writes = []

    def query_one(self, _sql, _params):
        return self.cache

    def query(self, _sql, _params):
        self.query_calls += 1
        return self.rows

    def execute(self, sql, params):
        self.writes.append((sql, params))
        if self.fail_cache_write:
            raise RuntimeError("cache write unavailable")


def _row(code, *, total=2, done=0, skipped=0, failed=0, running=0, optional=0):
    return {
        "code": code,
        "name": code,
        "sort_order": 1,
        "total_images": total,
        "done_count": done,
        "failed_count": failed,
        "running_count": running,
        "queued_count": 0,
        "paused_count": 0,
        "cancel_requested_count": 0,
        "restarting_count": 0,
        "skipped_count": skipped,
        "optional": optional,
    }


def test_cache_hit_returns_without_query_or_rewrite(monkeypatch):
    cached = [{"code": "scoring", "status": "done"}]
    connector = _Connector(
        cache={"phase_agg_dirty": 0, "phase_agg_json": json.dumps(cached)}
    )
    monkeypatch.setattr(db_legacy, "get_or_create_folder", lambda _path: 17)
    monkeypatch.setattr(db_legacy, "get_connector", lambda: connector)

    assert db_legacy.get_folder_phase_summary("/photos") == cached
    assert connector.query_calls == 0
    assert connector.writes == []


def test_missing_folder_returns_empty_without_query(monkeypatch):
    monkeypatch.setattr(db_legacy, "get_or_create_folder", lambda _path: None)
    monkeypatch.setattr(db_legacy, "get_connector", lambda: 1 / 0)
    assert db_legacy.get_folder_phase_summary("/missing") == []


def test_force_refresh_heal_and_cache_write_failures_are_nonfatal(monkeypatch):
    connector = _Connector(rows=[_row("scoring", done=2)], fail_cache_write=True)
    healed = []
    monkeypatch.setattr(db_legacy, "get_or_create_folder", lambda _path: 17)
    monkeypatch.setattr(db_legacy, "get_connector", lambda: connector)
    monkeypatch.setattr(db_legacy, "_should_run_heal", lambda _path: True)

    def failing_heal(path):
        healed.append(path)
        raise RuntimeError("healing unavailable")

    monkeypatch.setattr(db_legacy, "_heal_stale_phase_flags", failing_heal)
    monkeypatch.setattr(db_legacy, "_sql_bird_species_in_scope", lambda _alias: "1=1")
    monkeypatch.setattr(db_legacy, "_sql_bird_bbox_needs_scan", lambda _alias: "1=0")

    result = db_legacy.get_folder_phase_summary("/photos", force_refresh=True)

    assert healed == ["/photos"]
    assert connector.query_calls == 1
    assert len(connector.writes) == 1
    assert result[0]["status"] == "done"


def test_rollup_preserves_terminal_status_and_failure_precedence():
    result, scoring_done = _rollup_phase_rows(
        [
            _row("bird_species", total=0, optional=1),
            _row("scoring", total=3, done=2, skipped=1),
            _row("indexing", total=10, failed=2),
            _row("keywords", total=2, running=1, failed=1),
        ]
    )

    assert [item["status"] for item in result] == [
        "skipped",
        "done",
        "partial",
        "running",
    ]
    assert result[1]["advance_ready"] is True
    assert scoring_done is True
