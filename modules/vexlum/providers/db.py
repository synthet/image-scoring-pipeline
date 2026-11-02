"""Direct PostgreSQL actions: schema, read-only SELECT, write SQL."""

from __future__ import annotations

from typing import Any

_DOCS = ["docs/technical/DB_SCHEMA.md", "docs/DATABASE.md"]


def load_db_actions() -> list[dict[str, Any]]:
    return [
        {
            "action_id": "db.schema",
            "source": "db",
            "title": "PostgreSQL schema (tables, columns, types)",
            "description": "List tables and columns from information_schema. Run before writing SQL.",
            "category": "db",
            "tags": ["db", "postgres", "schema", "tables", "columns", "sql"],
            "aliases": ["db schema", "list tables", "describe table"],
            "intent_examples": ["what columns does images have", "list database tables"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "table_name_prefix": {"type": ["string", "null"], "description": "Filter tables by prefix"},
                    "max_tables": {"type": "integer", "default": 200},
                },
                "additionalProperties": False,
            },
            "tier": "read",
            "native_dry_run": False,
            "executor": {"kind": "sql", "op": "schema"},
            "canonical_docs": _DOCS,
            "legacy_tool_name": None,
            "notes": [],
        },
        {
            "action_id": "db.query",
            "source": "db",
            "title": "Run a read-only SQL query (SELECT / WITH)",
            "description": (
                "Single SELECT or WITH statement on PostgreSQL. Native %s placeholders with params[]. "
                "Rows are capped by max_rows."
            ),
            "category": "db",
            "tags": ["db", "postgres", "sql", "select", "query", "read"],
            "aliases": ["sql query", "select from", "count rows"],
            "intent_examples": ["count images in folder", "query the database", "select rows from table"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "SELECT or WITH statement"},
                    "params": {"type": ["array", "null"], "description": "Positional %s parameters"},
                    "max_rows": {"type": "integer", "default": 200, "minimum": 1, "maximum": 5000},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            "tier": "read",
            "native_dry_run": False,
            "executor": {"kind": "sql", "op": "query"},
            "canonical_docs": _DOCS,
            "legacy_tool_name": None,
            "notes": ["Runs in a READ ONLY transaction; writes are rejected by PostgreSQL."],
        },
        {
            "action_id": "db.execute",
            "source": "db",
            "title": "Execute write SQL (INSERT / UPDATE / DELETE / DDL)",
            "description": (
                "Single statement in one transaction. dry_run=true executes and ROLLS BACK, reporting rowcount "
                "and RETURNING rows, and issues the confirm_token required for the real run."
            ),
            "category": "db",
            "tags": ["db", "postgres", "sql", "update", "delete", "insert", "write", "ddl"],
            "aliases": ["update rows", "delete rows", "write sql"],
            "intent_examples": ["update image rows", "delete stale rows", "fix data in the database"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "One SQL statement"},
                    "params": {"type": ["array", "null"], "description": "Positional %s parameters"},
                    "max_rows": {"type": "integer", "default": 200, "minimum": 1, "maximum": 5000},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            "tier": "destructive",
            "native_dry_run": True,
            "executor": {"kind": "sql", "op": "execute"},
            "canonical_docs": _DOCS,
            "legacy_tool_name": None,
            "notes": ["Schema changes belong in Alembic migrations (migrations/versions/), not ad-hoc DDL."],
        },
    ]
