"""Tests for config.json + environment.json merge."""

import json

import pytest

import modules.config as cfg


def test_deep_merge_nested_and_scalar_override(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(cfg, "ENVIRONMENT_FILE", tmp_path / "environment.json")

    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "scoring_input_path": "/from/config",
                "database": {"postgres": {"host": "h1", "port": 5432}},
                "system": {"allowed_paths": ["C:/"]},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "environment.json").write_text(
        json.dumps(
            {
                "scoring_input_path": "/from/env",
                "database": {"postgres": {"host": "h2"}},
            }
        ),
        encoding="utf-8",
    )

    merged = cfg.load_config()
    assert merged["scoring_input_path"] == "/from/env"
    assert merged["database"]["postgres"]["host"] == "h2"
    assert merged["database"]["postgres"]["port"] == 5432
    assert merged["system"]["allowed_paths"] == ["C:/"]


def test_environment_replaces_list(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(cfg, "ENVIRONMENT_FILE", tmp_path / "environment.json")

    (tmp_path / "config.json").write_text(
        json.dumps({"system": {"allowed_paths": ["C:/"]}}),
        encoding="utf-8",
    )
    (tmp_path / "environment.json").write_text(
        json.dumps({"system": {"allowed_paths": ["/mnt/d/"]}}),
        encoding="utf-8",
    )

    merged = cfg.load_config()
    assert merged["system"]["allowed_paths"] == ["/mnt/d/"]


def test_save_config_value_writes_config_only_not_merged_env(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(cfg, "ENVIRONMENT_FILE", tmp_path / "environment.json")

    (tmp_path / "config.json").write_text(
        json.dumps({"foo": 1, "bar": {"x": 1}}),
        encoding="utf-8",
    )
    (tmp_path / "environment.json").write_text(
        json.dumps({"bar": {"x": 99}}),
        encoding="utf-8",
    )

    cfg.save_config_value("foo", 2)
    raw = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert raw["foo"] == 2
    assert raw["bar"]["x"] == 1


def test_validate_config_accepts_environment_only(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(cfg, "ENVIRONMENT_FILE", tmp_path / "environment.json")

    (tmp_path / "environment.json").write_text(
        json.dumps(
            {
                "database": {
                    "engine": "postgres",
                    "postgres": {
                        "host": "127.0.0.1",
                        "port": 5432,
                        "dbname": "image_scoring",
                        "user": "postgres",
                        "password": "postgres",
                    },
                },
                "processing": {
                    "prep_queue_size": 50,
                    "scoring_queue_size": 10,
                    "result_queue_size": 50,
                },
            }
        ),
        encoding="utf-8",
    )

    out = cfg.validate_config()
    assert out["ok"] is True
