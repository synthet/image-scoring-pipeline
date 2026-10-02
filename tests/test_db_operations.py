"""Regression coverage through the DB facade for extracted domain operations."""

import datetime
import json
from unittest.mock import MagicMock

import pytest

from modules import db
from modules.db_operations import image_paths


@pytest.fixture
def connector(monkeypatch):
    connector = MagicMock()
    monkeypatch.setattr(db, "get_connector", lambda: connector)
    return connector


def test_resolve_windows_path_upgrades_existing_path_without_duplicate(
    connector, monkeypatch
):
    connector.query_one.return_value = {"id": 21}
    monkeypatch.setattr(db, "_convert_to_windows_path", lambda _path: "converted-path")
    monkeypatch.setattr("platform.system", lambda: "Linux")

    assert db.resolve_windows_path(7, "/mnt/d/p.jpg") == "converted-path"

    connector.query_one.assert_called_once()
    sql, params = connector.execute.call_args.args
    assert sql.startswith("UPDATE file_paths SET path_type = 'WIN'")
    assert params[0:2] == (0, None)
    assert isinstance(params[2], datetime.datetime)
    assert params[3] == 21


def test_resolve_path_without_image_id_does_not_open_database(monkeypatch):
    monkeypatch.setattr(db, "_convert_to_windows_path", lambda _path: "converted-path")
    monkeypatch.setattr(
        db,
        "get_connector",
        lambda: pytest.fail("a conversion-only call must not open the DB"),
    )
    assert (
        db.resolve_windows_path(None, "source-path", verify=False) == "converted-path"
    )


@pytest.mark.parametrize("exists", [True, False])
def test_verify_resolved_path_updates_verification_state(
    connector, monkeypatch, exists
):
    connector.query_one.return_value = {"id": 21, "path": "converted-path"}
    monkeypatch.setattr("platform.system", lambda: "Windows")
    monkeypatch.setattr("os.path.exists", lambda _path: exists)

    assert db.verify_resolved_path(7) is exists

    _sql, params = connector.execute.call_args.args
    assert params[0] == int(exists)
    assert params[1] == (params[2] if exists else None)
    assert params[3] == 21


def test_verify_resolved_path_on_linux_does_not_open_database(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr(
        db, "get_connector", lambda: pytest.fail("Linux must not verify Windows paths")
    )
    assert db.verify_resolved_path(7) is False


def test_resolved_paths_batch_keeps_windows_paths_and_binds_ids(connector):
    windows_path = "D:" + chr(92) + "p.jpg"
    connector.query.return_value = [
        {"image_id": 7, "path": windows_path},
        {"image_id": 8, "path": "D:/mixed.jpg"},
        {"image_id": 9, "path": None},
    ]
    assert db.get_resolved_paths_batch([7, 8, 9]) == {7: windows_path}
    sql, params = connector.query.call_args.args
    assert "is_verified = 1" in sql
    assert params == (7, 8, 9)


def test_empty_batches_do_not_open_database(monkeypatch):
    monkeypatch.setattr(
        db, "get_connector", lambda: pytest.fail("empty batches must not open the DB")
    )
    assert db.get_resolved_paths_batch([]) == {}
    assert db.insert_job_image_actions([]) is None


@pytest.mark.parametrize(
    "raw, expected",
    [
        ({"phases": {}}, {"phases": {}}),
        ('{"phases": {}}', {"phases": {}}),
        ("invalid-json", None),
        (None, None),
        ([], None),
    ],
)
def test_job_report_accepts_native_and_encoded_json(connector, raw, expected):
    connector.query_one.return_value = {"report_json": raw}
    assert db.get_job_report("11") == expected
    assert connector.query_one.call_args.args[1] == (11,)


def test_job_image_actions_preserve_empty_snapshots_and_sql_null(connector):
    db.insert_job_image_actions(
        [
            {
                "job_id": 11,
                "image_id": 7,
                "phase_code": "keywords",
                "action": "processed",
                "before_snapshot": {},
                "after_snapshot": None,
            },
            {
                "job_id": 11,
                "image_id": 8,
                "phase_code": "keywords",
                "action": "skipped",
                "before_snapshot": None,
                "after_snapshot": {"keywords": "bird"},
            },
        ]
    )
    sql, params = connector.execute.call_args.args
    assert sql.count("?::jsonb") == 4
    assert params[5:7] == ("{}", None)
    assert params[12] is None
    assert json.loads(params[13]) == {"keywords": "bird"}


def test_job_actions_normalize_filters_and_decode_snapshots(connector):
    connector.query_one.return_value = {"c": 2}
    connector.query.return_value = [
        {
            "id": 1,
            "image_id": 7,
            "phase_code": "keywords ",
            "action": "processed ",
            "before_snapshot": '{"keywords": "before"}',
            "after_snapshot": {"keywords": "after"},
        },
        {
            "id": 2,
            "image_id": 8,
            "phase_code": "keywords",
            "action": "processed",
            "before_snapshot": "malformed",
            "after_snapshot": None,
        },
    ]
    result = db.get_job_image_actions("11", " KEYWORDS ", " PROCESSED ", 5, 10)
    assert result["total"] == 2
    assert connector.query_one.call_args.args[1] == (11, "keywords", "processed")
    assert connector.query.call_args.args[1] == (11, "keywords", "processed", 5, 10)
    assert result["items"][0]["before_snapshot"] == {"keywords": "before"}
    assert result["items"][0]["after_snapshot"] == {"keywords": "after"}
    assert result["items"][0]["phase_code"] == "keywords"
    assert result["items"][1]["before_snapshot"] == "malformed"


def test_path_storage_failure_keeps_fail_open_contract(monkeypatch):
    connector = MagicMock()
    connector.query_one.side_effect = RuntimeError("DB unavailable")
    assert (
        image_paths.resolve_windows_path(
            7,
            "source-path",
            verify=False,
            get_connector=lambda: connector,
            to_windows=lambda _path: "converted-path",
        )
        is None
    )
