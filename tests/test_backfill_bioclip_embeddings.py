"""Bounded full-frame repair must not fill unrelated missing embeddings."""

from unittest.mock import Mock

import pytest

from scripts.maintenance import backfill_bioclip_embeddings as backfill


def test_missing_rows_applies_manifest_before_limit(monkeypatch):
    from modules import db_postgres, embedding_spaces

    query = Mock(return_value=[{"id": 11, "file_path": "a.nef", "thumbnail_path": ""}])
    monkeypatch.setattr(embedding_spaces, "get_embedding_space_id", lambda _: 7)
    monkeypatch.setattr(db_postgres, "execute_select", query)

    assert backfill._missing_rows(9, 200, image_ids=[11, 13]) == [(11, "a.nef", "")]
    sql, params = query.call_args.args
    assert "i.id = ANY(%s)" in sql
    assert sql.index("i.id = ANY(%s)") < sql.index("LIMIT %s")
    assert params == (7, 9, [11, 13], 200)


def test_empty_manifest_selects_nothing(monkeypatch):
    from modules import db_postgres, embedding_spaces

    query = Mock()
    monkeypatch.setattr(embedding_spaces, "get_embedding_space_id", lambda _: 7)
    monkeypatch.setattr(db_postgres, "execute_select", query)
    assert backfill._missing_rows(None, None, image_ids=[]) == []
    query.assert_not_called()


def test_image_ids_file_retains_exact_ids(tmp_path):
    manifest = tmp_path / "ids.json"
    manifest.write_text("[13, 11]", encoding="utf-8")
    assert backfill._load_image_ids(str(manifest)) == [13, 11]


def test_cli_passes_frozen_ids_to_limited_dry_run(tmp_path, monkeypatch):
    from modules import db

    manifest = tmp_path / "ids.json"
    manifest.write_text("[13, 11]", encoding="utf-8")
    monkeypatch.setattr(db, "init_db", lambda: None)
    monkeypatch.setattr(db, "_get_db_engine", lambda: "postgres")
    select = Mock(return_value=[])
    embedder = Mock()
    monkeypatch.setattr(backfill, "_missing_rows", select)
    monkeypatch.setattr(backfill, "BioCLIPEmbedder", embedder)
    assert backfill.main(["--image-ids-file", str(manifest), "--limit", "200", "--dry-run"]) == 0
    select.assert_called_once_with(None, 200, image_ids=[13, 11])
    embedder.assert_not_called()


@pytest.mark.parametrize("contents", ["{}", "[true]", "[1.5]", "[0]", "[-2]", "[1, 1]", "broken"])
def test_invalid_manifest_is_rejected_before_database_access(tmp_path, monkeypatch, capsys, contents):
    from modules import db

    manifest = tmp_path / "ids.json"
    manifest.write_text(contents, encoding="utf-8")
    init = Mock(side_effect=AssertionError("must reject before database init"))
    monkeypatch.setattr(db, "init_db", init)
    with pytest.raises(SystemExit) as exc:
        backfill.main(["--image-ids-file", str(manifest), "--dry-run"])
    assert exc.value.code == 2
    init.assert_not_called()
    assert "distinct positive image IDs" in capsys.readouterr().err
