"""
Tests for scripts/backfill_region_keypoints.py region choice (#492).

No DB/GPU: a fake connector records which query and parameters were used.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from modules.rendition import COORD_SPACE_DISPLAY

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backfill_region_keypoints.py"
RULE = "v1_regate_rule/3:a1c2e1f64b24cc79"


def _load_script():
    """Load the backfill script as a module (scripts/ is not a package)."""
    name = "backfill_region_keypoints_under_test"
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class _FakeConn:
    def __init__(self):
        self.calls = []

    def query_one(self, sql, params):
        self.calls.append((sql, params))
        return {"region_id": 7}

    def query(self, sql, params):
        self.calls.append((sql, params))
        return [{"id": 1, "file_path": "a"}, {"id": 2, "file_path": "b"}]


@pytest.fixture
def script(monkeypatch):
    from modules import db

    conn = _FakeConn()
    monkeypatch.setattr(db, "get_connector", lambda: conn)
    mod = _load_script()
    return mod, conn


def test_default_region_is_rank0_of_current_run(script):
    mod, conn = script
    mod.primary_region(42)
    sql, params = conn.calls[-1]
    assert sql is mod._SQL_PRIMARY_REGION
    assert params == (42, "bird")


def test_selected_by_uses_the_selections_region_and_run(script):
    mod, conn = script
    assert mod.primary_region(42, RULE) == {"region_id": 7}
    sql, params = conn.calls[-1]
    assert sql is mod._SQL_SELECTED_REGION
    assert params == (42, "bird", RULE)
    # The selected run is usually not the current one; region and run come from the selection.
    assert "is_current" not in sql
    assert "r.id = s.localization_run_id" in sql and "g.id = s.region_id" in sql
    assert "revoked_at IS NULL" in sql


def test_selected_by_candidates_are_active_selections_by_that_rule(script):
    mod, conn = script
    rows = mod.fetch_candidates("", [], 1, selected_by=RULE)
    sql, params = conn.calls[-1]
    assert sql is mod._SQL_SELECTION_CANDIDATES
    assert params == (RULE, "bird", "", "")
    assert rows == [{"id": 1, "file_path": "a"}]


def test_selected_by_refuses_localize_missing(script, monkeypatch):
    mod, _ = script
    monkeypatch.setattr(sys, "argv", ["x", "--selected-by", RULE, "--localize-missing"])
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2


def test_primary_region_reports_the_run_status(script):
    mod, _ = script
    assert "r.status" in mod._SQL_PRIMARY_REGION


@pytest.mark.parametrize(
    ("cur", "expected"),
    [
        ({"region_id": None, "coord_space": COORD_SPACE_DISPLAY, "status": "no_detection"}, True),
        ({"region_id": 7, "coord_space": COORD_SPACE_DISPLAY, "status": "detected"}, False),
        ({"region_id": None, "coord_space": COORD_SPACE_DISPLAY, "status": "retryable_error"}, False),
        ({"region_id": None, "coord_space": COORD_SPACE_DISPLAY, "status": "terminal_error"}, False),
        ({"region_id": None, "coord_space": COORD_SPACE_DISPLAY, "status": "disabled"}, False),
        ({"region_id": None, "coord_space": "original_pixels", "status": "no_detection"}, False),
        (None, False),
    ],
)
def test_current_no_detection_run_skips_the_decode(script, cur, expected):
    mod, _ = script
    # #691: a current no_detection run has nothing to infer on; decoding again only re-proves that.
    assert mod.is_current_no_detection(cur) is expected
