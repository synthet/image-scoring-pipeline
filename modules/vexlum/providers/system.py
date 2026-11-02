"""Vexlum self-describing actions (status, catalog overview)."""

from __future__ import annotations

from typing import Any


def load_system_actions() -> list[dict[str, Any]]:
    base = {
        "source": "system",
        "category": "system",
        "tier": "read",
        "native_dry_run": False,
        "canonical_docs": ["docs/technical/VEXLUM_MCP.md"],
        "legacy_tool_name": None,
        "notes": [],
    }
    return [
        {
            **base,
            "action_id": "system.status",
            "title": "Vexlum status (catalog, DB, WebUI API, live SSE)",
            "description": "Catalog counts per source, DB reachability, REST base URL reachability, WebUI SSE probe.",
            "tags": ["status", "health", "webui", "sse", "reachable", "catalog"],
            "aliases": ["vexlum status", "sse status", "is webui up"],
            "intent_examples": ["is the webui running", "is the api reachable", "what can vexlum do"],
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            "executor": {"kind": "system", "op": "status"},
        },
        {
            **base,
            "action_id": "system.categories",
            "title": "List catalog categories and action counts",
            "description": "Browse the catalog by category/source without a search query.",
            "tags": ["catalog", "categories", "list", "browse", "help"],
            "aliases": ["list categories", "what actions exist"],
            "intent_examples": ["list all categories", "browse available actions"],
            "input_schema": {
                "type": "object",
                "properties": {"source": {"type": ["string", "null"], "description": "tool|api|db|browser|system"}},
                "additionalProperties": False,
            },
            "executor": {"kind": "system", "op": "categories"},
        },
    ]
