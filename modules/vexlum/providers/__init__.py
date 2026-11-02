"""Catalog providers. Each returns a list of normalized vexlum action records.

Record shape (all providers)::

    {
        "action_id": str,            # e.g. diagnostics.get_error_summary, api.scoring.start_scoring
        "source": "tool" | "api" | "db" | "browser" | "system",
        "title": str,
        "description": str,
        "category": str,
        "tags": list[str],
        "aliases": list[str],
        "intent_examples": list[str],
        "input_schema": dict,        # JSON Schema (object)
        "tier": "read" | "write" | "destructive",
        "native_dry_run": bool,      # executor implements a real preview
        "executor": dict,            # {"kind": ..., ...} — see modules/vexlum/executors/
        "canonical_docs": list[str],
        "legacy_tool_name": str | None,
        "notes": list[str],
    }
"""
