"""Regression coverage for the decomposed PostgreSQL schema bootstrap."""

import re

from modules.db_schema import initialize_schema


class _RecordingCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, sql: str, _params=None) -> None:
        self.statements.append(" ".join(str(sql).split()))

    def fetchone(self):
        return None


class _RecordingConnection:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _created_tables(statements: list[str]) -> list[str]:
    tables: list[str] = []
    for statement in statements:
        match = re.search(r"CREATE TABLE IF NOT EXISTS ([a-z0-9_]+)", statement)
        if match:
            tables.append(match.group(1))
    return tables


def test_initialize_schema_keeps_dependency_order_and_seed_statements() -> None:
    cursor = _RecordingCursor()
    connection = _RecordingConnection()
    default_seed = "INSERT INTO embedding_spaces(code, dim) VALUES ('default', 1280)"
    extra_seeds = [
        "INSERT INTO embedding_spaces(code, dim) VALUES ('clip', 512)",
        "INSERT INTO embedding_spaces(code, dim) VALUES ('blip', 768)",
    ]

    initialize_schema(
        cursor,
        conn=connection,
        default_embedding_space_sql=default_seed,
        extra_embedding_spaces_sql=extra_seeds,
    )

    assert cursor.statements[0] == "CREATE EXTENSION IF NOT EXISTS vector;"
    assert default_seed in cursor.statements
    assert all(seed in cursor.statements for seed in extra_seeds)

    tables = _created_tables(cursor.statements)
    expected_order = [
        "folders",
        "stacks",
        "jobs",
        "images",
        "embedding_spaces",
        "image_embeddings",
        "file_paths",
        "pipeline_phases",
        "image_phase_status",
        "keywords_dim",
        "image_keywords",
        "deleted_images",
        "auditlog",
        "agent_cull_review_groups",
        "image_localization_runs",
        "image_regions",
        "image_scene_labels",
    ]
    positions = [tables.index(table) for table in expected_order]
    assert positions == sorted(positions)
    assert connection.commits == 1
    assert connection.rollbacks == 0
